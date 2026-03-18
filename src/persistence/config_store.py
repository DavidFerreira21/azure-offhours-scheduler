from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from scheduler.models import GlobalSchedulerConfig, ScheduleDefinition, SchedulePeriod, ScheduleScope


def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    raise ValueError(f"{field_name} must be a boolean-compatible value")


def _parse_iso_datetime(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")

    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from error

    return text


def _parse_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()

    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            try:
                items = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"{field_name} must be valid JSON when using array syntax") from error
        else:
            items = [item.strip() for item in stripped.split(",")]
    else:
        raise ValueError(f"{field_name} must be a list or string")

    normalized_items = [str(item).strip() for item in items if str(item).strip()]
    return tuple(normalized_items)


def _parse_periods(entity: dict[str, Any], schedule_name: str) -> tuple[SchedulePeriod, ...]:
    raw_periods = entity.get("Periods") or entity.get("PeriodsJson")
    if raw_periods is not None:
        if isinstance(raw_periods, str):
            try:
                parsed_periods = json.loads(raw_periods)
            except json.JSONDecodeError as error:
                raise ValueError(f"schedule '{schedule_name}' has invalid Periods JSON") from error
        else:
            parsed_periods = raw_periods

        if not isinstance(parsed_periods, list) or not parsed_periods:
            raise ValueError(f"schedule '{schedule_name}' must define at least one period")

        periods: list[SchedulePeriod] = []
        for item in parsed_periods:
            if not isinstance(item, dict):
                raise ValueError(f"schedule '{schedule_name}' period entries must be objects")
            start = str(item.get("start") or item.get("Start") or "").strip()
            stop = str(item.get("stop") or item.get("Stop") or "").strip()
            if not start or not stop:
                raise ValueError(f"schedule '{schedule_name}' periods must include start and stop")
            periods.append(SchedulePeriod(start=start, stop=stop))
        return tuple(periods)

    start = str(entity.get("Start") or "").strip()
    stop = str(entity.get("Stop") or "").strip()
    if not start or not stop:
        raise ValueError(f"schedule '{schedule_name}' must define Start/Stop or Periods")
    return (SchedulePeriod(start=start, stop=stop),)


def _require_audit_fields(entity: dict[str, Any], entity_name: str) -> tuple[str, str, str]:
    version = str(entity.get("Version") or "").strip()
    if not version:
        raise ValueError(f"{entity_name} is missing Version")

    updated_at_utc = _parse_iso_datetime(entity.get("UpdatedAtUtc"), f"{entity_name}.UpdatedAtUtc")
    updated_by = str(entity.get("UpdatedBy") or "").strip()
    if not updated_by:
        raise ValueError(f"{entity_name} is missing UpdatedBy")

    return version, updated_at_utc, updated_by


class _AzureTableStoreBase:
    def __init__(self, connection_string: str, table_name: str, client=None) -> None:
        self.connection_string = connection_string
        self.table_name = table_name
        self._table_client = client

    def _client(self):
        if self._table_client:
            return self._table_client

        from azure.data.tables import TableServiceClient

        service = TableServiceClient.from_connection_string(self.connection_string)
        service.create_table_if_not_exists(self.table_name)
        self._table_client = service.get_table_client(self.table_name)
        return self._table_client


class AzureTableGlobalConfigStore(_AzureTableStoreBase):
    def __init__(
        self,
        connection_string: str,
        table_name: str = "OffHoursSchedulerConfig",
        partition_key: str = "GLOBAL",
        row_key: str = "runtime",
        client=None,
    ) -> None:
        super().__init__(connection_string=connection_string, table_name=table_name, client=client)
        self.partition_key = partition_key
        self.row_key = row_key

    def load(self) -> GlobalSchedulerConfig:
        table = self._client()
        try:
            entity = table.get_entity(partition_key=self.partition_key, row_key=self.row_key)
        except Exception as error:
            if error.__class__.__name__ != "ResourceNotFoundError":
                raise
            raise ValueError(
                f"global scheduler configuration entity not found in table '{self.table_name}' "
                f"({self.partition_key}/{self.row_key})"
            ) from error

        version, updated_at_utc, updated_by = _require_audit_fields(entity, "global scheduler configuration")
        default_timezone = str(entity.get("DEFAULT_TIMEZONE") or "").strip()
        schedule_tag_key = str(entity.get("SCHEDULE_TAG_KEY") or "").strip()

        if not default_timezone:
            raise ValueError("global scheduler configuration is missing DEFAULT_TIMEZONE")
        if not schedule_tag_key:
            raise ValueError("global scheduler configuration is missing SCHEDULE_TAG_KEY")

        return GlobalSchedulerConfig(
            dry_run=_parse_bool(entity.get("DRY_RUN"), "DRY_RUN"),
            default_timezone=default_timezone,
            schedule_tag_key=schedule_tag_key,
            retain_running=_parse_bool(entity.get("RETAIN_RUNNING"), "RETAIN_RUNNING"),
            retain_stopped=_parse_bool(entity.get("RETAIN_STOPPED"), "RETAIN_STOPPED"),
            version=version,
            updated_at_utc=updated_at_utc,
            updated_by=updated_by,
        )


class AzureTableScheduleStore(_AzureTableStoreBase):
    def __init__(self, connection_string: str, table_name: str = "OffHoursSchedulerSchedules", client=None) -> None:
        super().__init__(connection_string=connection_string, table_name=table_name, client=client)

    def load_all(self) -> dict[str, ScheduleDefinition]:
        table = self._client()
        schedules: dict[str, ScheduleDefinition] = {}

        for entity in table.list_entities():
            enabled = entity.get("Enabled", True)
            if not _parse_bool(enabled, "Enabled"):
                continue

            schedule_name = str(entity.get("RowKey") or entity.get("ScheduleName") or "").strip()
            if not schedule_name:
                raise ValueError(f"schedule entity in table '{self.table_name}' is missing RowKey/ScheduleName")

            version, updated_at_utc, updated_by = _require_audit_fields(entity, f"schedule '{schedule_name}'")
            periods = _parse_periods(entity, schedule_name)
            skip_days = tuple(day.lower() for day in _parse_string_list(entity.get("SkipDays"), "SkipDays"))
            scope = ScheduleScope.from_values(
                include_management_groups=_parse_string_list(
                    entity.get("IncludeManagementGroups"),
                    "IncludeManagementGroups",
                ),
                include_subscriptions=_parse_string_list(
                    entity.get("IncludeSubscriptions"),
                    "IncludeSubscriptions",
                ),
                exclude_management_groups=_parse_string_list(
                    entity.get("ExcludeManagementGroups"),
                    "ExcludeManagementGroups",
                ),
                exclude_subscriptions=_parse_string_list(
                    entity.get("ExcludeSubscriptions"),
                    "ExcludeSubscriptions",
                ),
            )

            schedules[schedule_name] = ScheduleDefinition(
                name=schedule_name,
                periods=periods,
                skip_days=skip_days,
                scope=scope,
                version=version,
                updated_at_utc=updated_at_utc,
                updated_by=updated_by,
            )

        return schedules
