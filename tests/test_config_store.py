import pytest

from persistence.config_store import AzureTableGlobalConfigStore, AzureTableScheduleStore


class FakeConfigTableClient:
    def __init__(self, entity):
        self.entity = entity

    def get_entity(self, partition_key: str, row_key: str):
        return self.entity


class FakeScheduleTableClient:
    def __init__(self, entities):
        self.entities = entities

    def list_entities(self):
        return self.entities


def test_loads_global_scheduler_configuration_from_table() -> None:
    store = AzureTableGlobalConfigStore(
        connection_string="UseDevelopmentStorage=true",
        client=FakeConfigTableClient(
            {
                "PartitionKey": "GLOBAL",
                "RowKey": "runtime",
                "DRY_RUN": True,
                "DEFAULT_TIMEZONE": "America/Sao_Paulo",
                "SCHEDULE_TAG_KEY": "schedule",
                "RETAIN_RUNNING": False,
                "RETAIN_STOPPED": True,
                "Version": "7",
                "UpdatedAtUtc": "2026-03-17T12:00:00+00:00",
                "UpdatedBy": "ops@example.com",
            }
        ),
    )

    result = store.load()

    assert result.dry_run is True
    assert result.default_timezone == "America/Sao_Paulo"
    assert result.retain_stopped is True
    assert result.version == "7"


def test_rejects_global_configuration_without_audit_fields() -> None:
    store = AzureTableGlobalConfigStore(
        connection_string="UseDevelopmentStorage=true",
        client=FakeConfigTableClient(
            {
                "PartitionKey": "GLOBAL",
                "RowKey": "runtime",
                "DRY_RUN": True,
                "DEFAULT_TIMEZONE": "America/Sao_Paulo",
                "SCHEDULE_TAG_KEY": "schedule",
                "RETAIN_RUNNING": False,
                "RETAIN_STOPPED": False,
            }
        ),
    )

    with pytest.raises(ValueError, match="Version"):
        store.load()


def test_loads_schedules_with_scope_and_audit_metadata() -> None:
    store = AzureTableScheduleStore(
        connection_string="UseDevelopmentStorage=true",
        client=FakeScheduleTableClient(
            [
                {
                    "PartitionKey": "SCHEDULE",
                    "RowKey": "office-hours",
                    "Periods": '[{"start":"08:00","stop":"18:00"}]',
                    "SkipDays": "saturday,sunday",
                    "IncludeSubscriptions": "sub-1,sub-2",
                    "ExcludeManagementGroups": '["mg-blocked"]',
                    "Version": "3",
                    "UpdatedAtUtc": "2026-03-17T12:00:00+00:00",
                    "UpdatedBy": "ops@example.com",
                }
            ]
        ),
    )

    schedules = store.load_all()

    schedule = schedules["office-hours"]
    assert schedule.periods[0].start == "08:00"
    assert schedule.skip_days == ("saturday", "sunday")
    assert schedule.scope.include_subscriptions == ("sub-1", "sub-2")
    assert schedule.scope.exclude_management_groups == ("mg-blocked",)
    assert schedule.updated_by == "ops@example.com"


def test_disabled_schedule_is_not_loaded() -> None:
    store = AzureTableScheduleStore(
        connection_string="UseDevelopmentStorage=true",
        client=FakeScheduleTableClient(
            [
                {
                    "PartitionKey": "SCHEDULE",
                    "RowKey": "disabled",
                    "Enabled": False,
                    "Start": "08:00",
                    "Stop": "18:00",
                    "Version": "1",
                    "UpdatedAtUtc": "2026-03-17T12:00:00+00:00",
                    "UpdatedBy": "ops@example.com",
                }
            ]
        ),
    )

    schedules = store.load_all()

    assert schedules == {}
