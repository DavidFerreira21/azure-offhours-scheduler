from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from src.offhours_cli.main import build_parser, main
from src.offhours_cli.storage import StorageSettings

from persistence.state_store import state_entity_keys_from_resource_id


class FakeTableClient:
    def __init__(self, entities=None):
        self.entities = dict(entities or {})
        self.upserts = []
        self.last_get = None
        self.deletes = []

    def get_entity(self, partition_key: str, row_key: str):
        self.last_get = (partition_key, row_key)
        key = (partition_key, row_key)
        if key not in self.entities:
            raise ValueError(f"missing entity: {key}")
        return self.entities[key]

    def list_entities(self):
        return list(self.entities.values())

    def upsert_entity(self, *, entity, mode):
        key = (entity["PartitionKey"], entity["RowKey"])
        self.entities[key] = dict(entity)
        self.upserts.append({"entity": dict(entity), "mode": mode})

    def delete_entity(self, *, partition_key: str, row_key: str):
        self.deletes.append((partition_key, row_key))
        self.entities.pop((partition_key, row_key), None)


@dataclass
class FakeSession:
    settings: StorageSettings
    config_client: FakeTableClient
    schedule_client: FakeTableClient
    state_client: FakeTableClient
    token_error: Exception | None = None
    table_names: set[str] | None = None

    @property
    def auth_mode(self) -> str:
        return "defaultazurecredential"

    def config_store(self):
        class _Store:
            def __init__(self, client):
                self._client = client

            def load(self):
                entity = self._client.get_entity("GLOBAL", "runtime")
                return type(
                    "Config",
                    (),
                    {
                        "dry_run": entity["DRY_RUN"],
                        "default_timezone": entity["DEFAULT_TIMEZONE"],
                        "schedule_tag_key": entity["SCHEDULE_TAG_KEY"],
                        "retain_running": entity["RETAIN_RUNNING"],
                        "retain_stopped": entity["RETAIN_STOPPED"],
                        "version": entity["Version"],
                        "updated_at_utc": entity["UpdatedAtUtc"],
                        "updated_by": entity["UpdatedBy"],
                    },
                )()

        return _Store(self.config_client)

    def schedule_store(self):
        class _Store:
            def __init__(self, client):
                self._client = client

            def load_records(self):
                from persistence.table_entities import normalize_schedule_entity

                return {
                    entity["RowKey"]: normalize_schedule_entity(entity)
                    for entity in self._client.list_entities()
                }

        return _Store(self.schedule_client)

    def table_client(self, table_name: str):
        mapping = {
            self.settings.config_table_name: self.config_client,
            self.settings.schedule_table_name: self.schedule_client,
            self.settings.state_table_name: self.state_client,
        }
        return mapping[table_name]

    def check_token(self):
        if self.token_error:
            raise self.token_error
        return {"credential_class": "FakeCredential", "status": "ok"}

    def list_table_names(self):
        return set(self.table_names or set())


def make_session() -> FakeSession:
    settings = StorageSettings(
        table_service_uri="https://example.table.core.windows.net",
        connection_string="",
        config_table_name="OffHoursSchedulerConfig",
        schedule_table_name="OffHoursSchedulerSchedules",
        state_table_name="OffHoursSchedulerState",
    )
    config_client = FakeTableClient(
        {
            (
                "GLOBAL",
                "runtime",
            ): {
                "PartitionKey": "GLOBAL",
                "RowKey": "runtime",
                "DRY_RUN": True,
                "DEFAULT_TIMEZONE": "America/Sao_Paulo",
                "SCHEDULE_TAG_KEY": "schedule",
                "RETAIN_RUNNING": False,
                "RETAIN_STOPPED": False,
                "Version": "1",
                "UpdatedAtUtc": "2026-03-17T12:00:00Z",
                "UpdatedBy": "ops@example.com",
            }
        }
    )
    schedule_client = FakeTableClient(
        {
            (
                "SCHEDULE",
                "business-hours",
            ): {
                "PartitionKey": "SCHEDULE",
                "RowKey": "business-hours",
                "Start": "08:00",
                "Stop": "18:00",
                "Enabled": True,
                "Version": "1",
                "UpdatedAtUtc": "2026-03-17T12:00:00Z",
                "UpdatedBy": "ops@example.com",
            }
        }
    )
    state_partition, state_row = state_entity_keys_from_resource_id(
        "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-a"
    )
    state_client = FakeTableClient(
        {
            (
                state_partition,
                state_row,
            ): {
                "PartitionKey": state_partition,
                "RowKey": state_row,
                "ResourceId": (
                    "/subscriptions/sub-1/resourceGroups/rg-1/providers/"
                    "Microsoft.Compute/virtualMachines/vm-a"
                ),
                "ResourceName": "vm-a",
                "StartedByScheduler": False,
                "StoppedByScheduler": True,
                "LastObservedState": "stopped",
                "LastAction": "STOP",
                "UpdatedAtUtc": "2026-03-17T12:15:00Z",
            }
        }
    )
    return FakeSession(
        settings=settings,
        config_client=config_client,
        schedule_client=schedule_client,
        state_client=state_client,
        table_names={
            settings.config_table_name,
            settings.schedule_table_name,
            settings.state_table_name,
        },
    )


def test_parser_requires_config_apply_file() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["config", "apply"])


def test_storage_settings_accepts_cli_specific_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("OFFHOURS_TABLE_SERVICE_URI", "https://short.table.core.windows.net")
    monkeypatch.delenv("SCHEDULER_TABLE_SERVICE_URI", raising=False)
    monkeypatch.delenv("SCHEDULER_STORAGE_CONNECTION_STRING", raising=False)
    args = SimpleNamespace(
        table_service_uri="",
        connection_string="",
        config_table="",
        schedule_table="",
        state_table="",
    )

    settings = StorageSettings.from_args(args)

    assert settings.table_service_uri == "https://short.table.core.windows.net"


def test_schedule_apply_preview_does_not_write(monkeypatch, tmp_path, capsys) -> None:
    session = make_session()
    payload_file = tmp_path / "schedule.yaml"
    payload_file.write_text(
        "\n".join(
            [
                "RowKey: office-hours",
                "Periods:",
                "  - start: '09:00'",
                "    stop: '17:00'",
                "Enabled: true",
                "Version: '4'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)
    monkeypatch.setattr("src.offhours_cli.main.resolve_updated_by", lambda value: "ops@example.com")

    exit_code = main(
        [
            "schedule",
            "apply",
            "--file",
            str(payload_file),
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    assert session.schedule_client.upserts == []
    assert "Preview only" in capsys.readouterr().out


def test_config_apply_execute_upserts_entity(monkeypatch, tmp_path) -> None:
    session = make_session()
    payload_file = tmp_path / "config.yaml"
    payload_file.write_text(
        "\n".join(
            [
                "DRY_RUN: false",
                "DEFAULT_TIMEZONE: America/Sao_Paulo",
                "SCHEDULE_TAG_KEY: schedule",
                "RETAIN_RUNNING: true",
                "RETAIN_STOPPED: false",
                "Version: '5'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)
    monkeypatch.setattr("src.offhours_cli.main.resolve_updated_by", lambda value: "ops@example.com")

    exit_code = main(
        [
            "config",
            "apply",
            "--file",
            str(payload_file),
            "--execute",
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    assert len(session.config_client.upserts) == 1
    entity = session.config_client.upserts[0]["entity"]
    assert entity["DRY_RUN"] is False
    assert entity["RETAIN_RUNNING"] is True
    assert entity["Version"] == "5"


def test_schedule_apply_accepts_json_payload(monkeypatch, tmp_path) -> None:
    session = make_session()
    payload_file = tmp_path / "schedule.json"
    payload_file.write_text(
        json.dumps(
            {
                "RowKey": "office-hours",
                "Periods": [{"start": "08:00", "stop": "18:00"}],
                "Enabled": True,
                "Version": "3",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)
    monkeypatch.setattr("src.offhours_cli.main.resolve_updated_by", lambda value: "ops@example.com")

    exit_code = main(
        [
            "schedule",
            "apply",
            "--file",
            str(payload_file),
            "--execute",
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    entity = session.schedule_client.upserts[0]["entity"]
    assert entity["RowKey"] == "office-hours"
    assert "Periods" in entity


def test_schedule_delete_removes_entity(monkeypatch) -> None:
    session = make_session()
    schedule_key = ("SCHEDULE", "business-hours")
    assert schedule_key in session.schedule_client.entities
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)

    exit_code = main(
        [
            "schedule",
            "delete",
            "business-hours",
            "--execute",
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    assert session.schedule_client.deletes == [schedule_key]
    assert schedule_key not in session.schedule_client.entities


def test_state_get_uses_keys_derived_from_resource_id(monkeypatch) -> None:
    session = make_session()
    resource_id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-a"
    expected_keys = state_entity_keys_from_resource_id(resource_id)
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)

    exit_code = main(
        [
            "state",
            "get",
            "--resource-id",
            resource_id,
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    assert session.state_client.last_get == expected_keys


def test_removed_show_alias_is_rejected() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "state",
                "show",
                "--resource-id",
                "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            ]
        )


class FakeUrlOpenResponse:
    def __init__(self, body: str = '{"invoked":true}', status: int = 202) -> None:
        self._body = body.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_function_trigger_uses_offhours_context(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {"commands": []}

    def fake_run(command, check, capture_output, text):
        captured["commands"].append(command)
        assert check is False
        assert capture_output is True
        assert text is True
        if command[2:4] == ["function", "list"]:
            return SimpleNamespace(returncode=0, stdout='["func-offhours/OffHoursTimer"]\n', stderr="")
        return SimpleNamespace(returncode=0, stdout="master-key\n", stderr="")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data.decode("utf-8")
        return FakeUrlOpenResponse()

    monkeypatch.setenv("OFFHOURS_RESOURCE_GROUP", "rg-offhours")
    monkeypatch.setenv("OFFHOURS_FUNCTION_APP_NAME", "func-offhours")
    monkeypatch.delenv("OFFHOURS_FUNCTION_NAME", raising=False)
    monkeypatch.setattr("src.offhours_cli.main.subprocess.run", fake_run)
    monkeypatch.setattr("src.offhours_cli.main.urllib.request.urlopen", fake_urlopen)

    exit_code = main(["function", "trigger"])

    assert exit_code == 0
    assert captured["commands"][0][1:] == [
        "functionapp",
        "function",
        "list",
        "--resource-group",
        "rg-offhours",
        "--name",
        "func-offhours",
        "--query",
        "[].name",
        "-o",
        "json",
    ]
    assert captured["commands"][1][1:] == [
        "functionapp",
        "keys",
        "list",
        "--resource-group",
        "rg-offhours",
        "--name",
        "func-offhours",
        "--query",
        "masterKey",
        "-o",
        "tsv",
    ]
    assert captured["url"] == "https://func-offhours.azurewebsites.net/admin/functions/OffHoursTimer"
    assert captured["timeout"] == 30.0
    assert captured["body"] == "{}"
    assert captured["headers"]["X-functions-key"] == "master-key"
    assert "FunctionAppName: func-offhours" in capsys.readouterr().out


def test_function_trigger_requires_context(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OFFHOURS_RESOURCE_GROUP", raising=False)
    monkeypatch.delenv("OFFHOURS_FUNCTION_APP_NAME", raising=False)

    exit_code = main(["function", "trigger"])

    assert exit_code == 1
    assert "resource group could not be resolved" in capsys.readouterr().err


def test_function_trigger_requires_published_function(monkeypatch, capsys) -> None:
    def fake_run(command, check, capture_output, text):
        assert command[2:4] == ["function", "list"]
        return SimpleNamespace(returncode=0, stdout="[]\n", stderr="")

    monkeypatch.setenv("OFFHOURS_RESOURCE_GROUP", "rg-offhours")
    monkeypatch.setenv("OFFHOURS_FUNCTION_APP_NAME", "func-offhours")
    monkeypatch.setattr("src.offhours_cli.main.subprocess.run", fake_run)

    exit_code = main(["function", "trigger"])

    assert exit_code == 1
    assert "No published functions were found" in capsys.readouterr().err


def test_state_delete_preview_does_not_write(monkeypatch, capsys) -> None:
    session = make_session()
    resource_id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-a"
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)

    exit_code = main(
        [
            "state",
            "delete",
            "--resource-id",
            resource_id,
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    assert session.state_client.deletes == []
    assert "Preview only" in capsys.readouterr().out


def test_state_delete_execute_removes_entity(monkeypatch) -> None:
    session = make_session()
    resource_id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-a"
    state_key = state_entity_keys_from_resource_id(resource_id)
    assert state_key in session.state_client.entities
    monkeypatch.setattr("src.offhours_cli.main.create_session", lambda args: session)

    exit_code = main(
        [
            "state",
            "delete",
            "--resource-id",
            resource_id,
            "--execute",
            "--table-service-uri",
            session.settings.table_service_uri,
        ]
    )

    assert exit_code == 0
    assert session.state_client.deletes == [state_key]
    assert state_key not in session.state_client.entities
