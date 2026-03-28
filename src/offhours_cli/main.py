from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Sequence

from persistence.state_store import state_entity_keys_from_resource_id
from persistence.table_entities import (
    DEFAULT_SCHEDULE_PARTITION_KEY,
    build_global_config_entity,
    build_schedule_entity,
    global_config_to_payload,
    normalize_schedule_entity,
    schedule_record_to_payload,
)

from .files import load_mapping_file
from .formatting import emit_output
from .storage import AzureTableSession, StorageSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m offhours_cli")
    subparsers = parser.add_subparsers(dest="domain", required=True)

    storage_parent = argparse.ArgumentParser(add_help=False)
    add_storage_args(storage_parent)

    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="action", required=True)

    config_get = config_subparsers.add_parser("get", parents=[storage_parent])
    config_get.add_argument("--format", choices=("table", "json", "yaml"), default="table")
    config_get.set_defaults(handler=handle_config_get)

    config_apply = config_subparsers.add_parser("apply", parents=[storage_parent])
    config_apply.add_argument("--file", required=True)
    config_apply.add_argument("--updated-by", default="")
    config_apply.add_argument("--execute", action="store_true")
    config_apply.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    config_apply.set_defaults(handler=handle_config_apply)

    schedule_parser = subparsers.add_parser("schedule")
    schedule_subparsers = schedule_parser.add_subparsers(dest="action", required=True)

    schedule_list = schedule_subparsers.add_parser("list", parents=[storage_parent])
    schedule_list.add_argument("--format", choices=("table", "json", "yaml"), default="table")
    schedule_list.set_defaults(handler=handle_schedule_list)

    schedule_get = schedule_subparsers.add_parser("get", parents=[storage_parent])
    schedule_get.add_argument("name")
    schedule_get.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    schedule_get.set_defaults(handler=handle_schedule_get)

    schedule_apply = schedule_subparsers.add_parser("apply", parents=[storage_parent])
    schedule_apply.add_argument("--file", required=True)
    schedule_apply.add_argument("--updated-by", default="")
    schedule_apply.add_argument("--execute", action="store_true")
    schedule_apply.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    schedule_apply.set_defaults(handler=handle_schedule_apply)

    schedule_delete = schedule_subparsers.add_parser("delete", parents=[storage_parent])
    schedule_delete.add_argument("name")
    schedule_delete.add_argument("--execute", action="store_true")
    schedule_delete.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    schedule_delete.set_defaults(handler=handle_schedule_delete)

    state_parser = subparsers.add_parser("state")
    state_subparsers = state_parser.add_subparsers(dest="action", required=True)

    state_list = state_subparsers.add_parser("list", parents=[storage_parent])
    state_list.add_argument("--subscription-id", action="append", dest="subscription_ids", default=[])
    state_list.add_argument("--limit", type=int, default=50)
    state_list.add_argument("--result", choices=("table", "json"), default="table")
    state_list.set_defaults(handler=handle_state_list)

    state_get = state_subparsers.add_parser("get", parents=[storage_parent])
    state_get.add_argument("--resource-id", required=True)
    state_get.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    state_get.set_defaults(handler=handle_state_get)

    state_delete = state_subparsers.add_parser("delete", parents=[storage_parent])
    state_delete.add_argument("--resource-id", required=True)
    state_delete.add_argument("--execute", action="store_true")
    state_delete.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    state_delete.set_defaults(handler=handle_state_delete)

    function_parser = subparsers.add_parser("function")
    function_subparsers = function_parser.add_subparsers(dest="action", required=True)

    function_trigger = function_subparsers.add_parser("trigger")
    function_trigger.add_argument("--resource-group", default="")
    function_trigger.add_argument("--function-app-name", default="")
    function_trigger.add_argument("--function-name", default="")
    function_trigger.add_argument("--slot", default="")
    function_trigger.add_argument("--input", default="")
    function_trigger.add_argument("--timeout", type=float, default=30.0)
    function_trigger.add_argument("--format", choices=("table", "json", "yaml"), default="yaml")
    function_trigger.set_defaults(handler=handle_function_trigger)

    return parser


def add_storage_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--table-service-uri", default="")
    parser.add_argument("--connection-string", default="")
    parser.add_argument("--config-table", default="")
    parser.add_argument("--schedule-table", default="")
    parser.add_argument("--state-table", default="")


def create_session(args) -> AzureTableSession:
    return AzureTableSession(StorageSettings.from_args(args))


def replace_update_mode():
    try:
        from azure.data.tables import UpdateMode
    except ModuleNotFoundError:
        return "REPLACE"
    return UpdateMode.REPLACE


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_updated_by(explicit_value: str) -> str:
    candidate = explicit_value.strip() or os.getenv("OFFHOURS_UPDATED_BY", "").strip()
    if candidate:
        return candidate

    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "user.name", "-o", "tsv"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise ValueError("UpdatedBy could not be resolved. Use --updated-by or set OFFHOURS_UPDATED_BY.") from error

    candidate = result.stdout.strip()
    if candidate:
        return candidate
    raise ValueError("UpdatedBy could not be resolved. Use --updated-by or set OFFHOURS_UPDATED_BY.")


def resolve_required_value(explicit_value: str, env_name: str, description: str) -> str:
    candidate = explicit_value.strip() or os.getenv(env_name, "").strip()
    if candidate:
        return candidate
    raise ValueError(f"{description} could not be resolved. Use --{description.replace(' ', '-')} or set {env_name}.")


def resolve_function_name(explicit_value: str) -> str:
    return explicit_value.strip() or os.getenv("OFFHOURS_FUNCTION_NAME", "").strip() or "OffHoursTimer"


def fetch_function_master_key(*, resource_group: str, function_app_name: str, slot: str = "") -> str:
    command = [
        "az",
        "functionapp",
        "keys",
        "list",
        "--resource-group",
        resource_group,
        "--name",
        function_app_name,
        "--query",
        "masterKey",
        "-o",
        "tsv",
    ]
    if slot:
        command.extend(["--slot", slot])

    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise ValueError(
            "Azure CLI could not be found. Install 'az' or run the command from a configured environment."
        ) from error

    if result.returncode != 0:
        error_output = result.stderr.strip() or result.stdout.strip() or "failed to retrieve Function App keys"
        raise ValueError(f"Unable to retrieve Function App master key: {error_output}")

    master_key = result.stdout.strip()
    if not master_key:
        raise ValueError(
            "Function App master key was empty. Check the Function App name, resource group, and Azure access."
        )
    return master_key


def fetch_published_function_names(*, resource_group: str, function_app_name: str) -> list[str]:
    command = [
        "az",
        "functionapp",
        "function",
        "list",
        "--resource-group",
        resource_group,
        "--name",
        function_app_name,
        "--query",
        "[].name",
        "-o",
        "json",
    ]

    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return []

    if result.returncode != 0:
        return []

    try:
        names = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []

    if not isinstance(names, list):
        return []

    return [str(name).split("/", 1)[-1].strip() for name in names if str(name).strip()]


def invoke_function_trigger(
    *,
    resource_group: str,
    function_app_name: str,
    function_name: str,
    slot: str = "",
    input_payload: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    master_key = fetch_function_master_key(
        resource_group=resource_group,
        function_app_name=function_app_name,
        slot=slot,
    )
    host_name = f"{function_app_name}-{slot}.azurewebsites.net" if slot else f"{function_app_name}.azurewebsites.net"
    url = f"https://{host_name}/admin/functions/{function_name}"
    request_payload = {"input": input_payload} if input_payload else {}
    request = urllib.request.Request(
        url,
        data=json.dumps(request_payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-functions-key": master_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", None)
            if status_code is None:
                status_code = response.getcode()
            response_text = response.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"Function trigger failed with HTTP {error.code}: {detail or getattr(error, 'reason', 'unknown error')}"
        ) from error
    except urllib.error.URLError as error:
        raise ValueError(f"Function trigger request failed: {error.reason}") from error

    payload: dict[str, Any] = {
        "ResourceGroup": resource_group,
        "FunctionAppName": function_app_name,
        "FunctionName": function_name,
        "Slot": slot or "production",
        "Url": url,
        "HttpStatus": status_code,
        "Status": "Accepted" if status_code in {200, 202, 204} else "Completed",
    }
    if response_text:
        try:
            payload["Response"] = json.loads(response_text)
        except json.JSONDecodeError:
            payload["ResponseText"] = response_text
    return payload


def _preview_or_apply(
    *,
    normalized_payload: dict[str, Any],
    execute: bool,
    output_format: str,
    table_name: str,
    write_callback,
) -> int:
    emit_output(normalized_payload, output_format=output_format)
    if not execute:
        print(f"\nPreview only. Re-run with --execute to apply changes to table '{table_name}'.")
        return 0

    write_callback()
    print(f"\nApplied changes to table '{table_name}'.")
    return 0


def handle_config_get(args) -> int:
    session = create_session(args)
    config = session.config_store().load()
    emit_output(global_config_to_payload(config), output_format=args.format)
    return 0


def handle_config_apply(args) -> int:
    payload = load_mapping_file(args.file)
    session = create_session(args)
    updated_by = resolve_updated_by(args.updated_by)
    entity = build_global_config_entity(payload, updated_at_utc=utc_now_iso(), updated_by=updated_by)

    def write_callback() -> None:
        session.table_client(session.settings.config_table_name).upsert_entity(
            entity=entity,
            mode=replace_update_mode(),
        )

    return _preview_or_apply(
        normalized_payload=entity,
        execute=args.execute,
        output_format=args.format,
        table_name=session.settings.config_table_name,
        write_callback=write_callback,
    )


def _load_schedule_record(session: AzureTableSession, name: str):
    entity = session.table_client(session.settings.schedule_table_name).get_entity(
        partition_key=DEFAULT_SCHEDULE_PARTITION_KEY,
        row_key=name,
    )
    return normalize_schedule_entity(entity)


def handle_schedule_list(args) -> int:
    session = create_session(args)
    rows = []
    for name, record in sorted(session.schedule_store().load_records().items()):
        payload = schedule_record_to_payload(record)
        rows.append(
            {
                "Name": name,
                "Enabled": payload["Enabled"],
                "Periods": ", ".join(f"{period['start']}-{period['stop']}" for period in payload["Periods"]),
                "SkipDays": ", ".join(payload.get("SkipDays", [])),
                "Version": payload["Version"],
                "UpdatedAtUtc": payload["UpdatedAtUtc"],
                "UpdatedBy": payload["UpdatedBy"],
            }
        )

    emit_output(
        rows if args.format == "table" else [row for row in rows],
        output_format=args.format,
        table_columns=["Name", "Enabled", "Periods", "SkipDays", "Version", "UpdatedAtUtc", "UpdatedBy"],
    )
    return 0


def handle_schedule_get(args) -> int:
    session = create_session(args)
    record = _load_schedule_record(session, args.name)
    emit_output(schedule_record_to_payload(record), output_format=args.format)
    return 0


def handle_schedule_apply(args) -> int:
    payload = load_mapping_file(args.file)
    session = create_session(args)
    updated_by = resolve_updated_by(args.updated_by)
    entity = build_schedule_entity(payload, updated_at_utc=utc_now_iso(), updated_by=updated_by)
    normalized_payload = schedule_record_to_payload(normalize_schedule_entity(entity))

    def write_callback() -> None:
        session.table_client(session.settings.schedule_table_name).upsert_entity(
            entity=entity,
            mode=replace_update_mode(),
        )

    return _preview_or_apply(
        normalized_payload=normalized_payload,
        execute=args.execute,
        output_format=args.format,
        table_name=session.settings.schedule_table_name,
        write_callback=write_callback,
    )


def handle_schedule_delete(args) -> int:
    session = create_session(args)
    record = _load_schedule_record(session, args.name)
    normalized_payload = schedule_record_to_payload(record)

    def write_callback() -> None:
        session.table_client(session.settings.schedule_table_name).delete_entity(
            partition_key=DEFAULT_SCHEDULE_PARTITION_KEY,
            row_key=args.name,
        )

    return _preview_or_apply(
        normalized_payload=normalized_payload,
        execute=args.execute,
        output_format=args.format,
        table_name=session.settings.schedule_table_name,
        write_callback=write_callback,
    )


def _state_entity_to_payload(entity: dict[str, Any]) -> dict[str, Any]:
    preferred_keys = (
        "PartitionKey",
        "RowKey",
        "ResourceId",
        "CanonicalResourceId",
        "ResourceGroup",
        "ResourceName",
        "ResourceType",
        "StartedByScheduler",
        "StoppedByScheduler",
        "LastObservedState",
        "LastAction",
        "UpdatedAtUtc",
    )
    payload = {key: entity.get(key) for key in preferred_keys if key in entity}
    for key, value in entity.items():
        if key not in payload:
            payload[key] = value
    return payload


def handle_state_list(args) -> int:
    session = create_session(args)
    entities = session.table_client(session.settings.state_table_name).list_entities()
    subscription_filter = {item.strip().lower() for item in args.subscription_ids if item.strip()}
    rows: list[dict[str, Any]] = []

    for entity in entities:
        payload = _state_entity_to_payload(entity)
        partition_key = str(payload.get("PartitionKey") or "").strip().lower()
        if subscription_filter and partition_key not in subscription_filter:
            continue
        rows.append(payload)
        if args.limit > 0 and len(rows) >= args.limit:
            break

    if args.result == "table":
        emit_output(
            [
                {
                    "Subscription": row.get("PartitionKey", ""),
                    "ResourceName": row.get("ResourceName", ""),
                    "LastObservedState": row.get("LastObservedState", ""),
                    "LastAction": row.get("LastAction", ""),
                    "StartedByScheduler": row.get("StartedByScheduler", ""),
                    "StoppedByScheduler": row.get("StoppedByScheduler", ""),
                    "UpdatedAtUtc": row.get("UpdatedAtUtc", ""),
                }
                for row in rows
            ],
            output_format="table",
            table_columns=[
                "Subscription",
                "ResourceName",
                "LastObservedState",
                "LastAction",
                "StartedByScheduler",
                "StoppedByScheduler",
                "UpdatedAtUtc",
            ],
        )
    else:
        emit_output(rows, output_format="json")
    return 0


def handle_state_get(args) -> int:
    session = create_session(args)
    partition_key, row_key = state_entity_keys_from_resource_id(args.resource_id)
    entity = session.table_client(session.settings.state_table_name).get_entity(
        partition_key=partition_key,
        row_key=row_key,
    )
    emit_output(_state_entity_to_payload(entity), output_format=args.format)
    return 0


def handle_state_delete(args) -> int:
    session = create_session(args)
    partition_key, row_key = state_entity_keys_from_resource_id(args.resource_id)
    entity = session.table_client(session.settings.state_table_name).get_entity(
        partition_key=partition_key,
        row_key=row_key,
    )
    normalized_payload = _state_entity_to_payload(entity)

    def write_callback() -> None:
        session.table_client(session.settings.state_table_name).delete_entity(
            partition_key=partition_key,
            row_key=row_key,
        )

    return _preview_or_apply(
        normalized_payload=normalized_payload,
        execute=args.execute,
        output_format=args.format,
        table_name=session.settings.state_table_name,
        write_callback=write_callback,
    )


def handle_function_trigger(args) -> int:
    resource_group = resolve_required_value(args.resource_group, "OFFHOURS_RESOURCE_GROUP", "resource group")
    function_app_name = resolve_required_value(
        args.function_app_name,
        "OFFHOURS_FUNCTION_APP_NAME",
        "function app name",
    )
    explicit_function_name = args.function_name.strip() or os.getenv("OFFHOURS_FUNCTION_NAME", "").strip()
    published_function_names = fetch_published_function_names(
        resource_group=resource_group,
        function_app_name=function_app_name,
    )
    if explicit_function_name:
        function_name = explicit_function_name
    elif "OffHoursTimer" in published_function_names:
        function_name = "OffHoursTimer"
    elif len(published_function_names) == 1:
        function_name = published_function_names[0]
    else:
        function_name = resolve_function_name("")

    if not published_function_names:
        raise ValueError(
            "No published functions were found in the target Function App. "
            "Publish the app first or pass --function-name explicitly."
        )

    payload = invoke_function_trigger(
        resource_group=resource_group,
        function_app_name=function_app_name,
        function_name=function_name,
        slot=args.slot.strip(),
        input_payload=args.input,
        timeout=args.timeout,
    )
    emit_output(payload, output_format=args.format)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(argv_list)

    try:
        return args.handler(args)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
