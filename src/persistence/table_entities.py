from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from scheduler.engine import ScheduleEngine
from scheduler.models import GlobalSchedulerConfig, ScheduleDefinition, SchedulePeriod, ScheduleScope

DEFAULT_CONFIG_PARTITION_KEY = "GLOBAL"
DEFAULT_CONFIG_ROW_KEY = "runtime"
DEFAULT_SCHEDULE_PARTITION_KEY = "SCHEDULE"


@dataclass(frozen=True)
class ScheduleEntityRecord:
    definition: ScheduleDefinition
    enabled: bool


def parse_bool(value: Any, field_name: str) -> bool:
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
    raise ValueError(
        f"{field_name} must be a boolean-compatible value. "
        "Use true/false boolean values when editing table entities."
    )


def parse_iso_datetime(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")

    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from error

    return text


def parse_string_list(value: Any, field_name: str) -> tuple[str, ...]:
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


def require_audit_fields(entity: Mapping[str, Any], entity_name: str) -> tuple[str, str, str]:
    version = str(entity.get("Version") or "").strip()
    if not version:
        raise ValueError(f"{entity_name} is missing Version")

    updated_at_utc = parse_iso_datetime(entity.get("UpdatedAtUtc"), f"{entity_name}.UpdatedAtUtc")
    updated_by = str(entity.get("UpdatedBy") or "").strip()
    if not updated_by:
        raise ValueError(f"{entity_name} is missing UpdatedBy")

    return version, updated_at_utc, updated_by


def parse_periods(entity: Mapping[str, Any], schedule_name: str) -> tuple[SchedulePeriod, ...]:
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
            validate_hhmm(start, field_name=f"schedule '{schedule_name}'.start")
            validate_hhmm(stop, field_name=f"schedule '{schedule_name}'.stop")
            periods.append(SchedulePeriod(start=start, stop=stop))
        return tuple(periods)

    start = str(entity.get("Start") or "").strip()
    stop = str(entity.get("Stop") or "").strip()
    if not start or not stop:
        raise ValueError(f"schedule '{schedule_name}' must define Start/Stop or Periods")
    validate_hhmm(start, field_name=f"schedule '{schedule_name}'.Start")
    validate_hhmm(stop, field_name=f"schedule '{schedule_name}'.Stop")
    return (SchedulePeriod(start=start, stop=stop),)


def validate_hhmm(value: str, field_name: str) -> str:
    try:
        ScheduleEngine._hhmm_to_minutes(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid HH:MM value") from error
    return value


def validate_timezone(value: str, field_name: str) -> str:
    timezone_name = str(value or "").strip()
    if not timezone_name:
        raise ValueError(f"{field_name} is required")
    try:
        ZoneInfo(timezone_name)
    except Exception as error:
        raise ValueError(f"{field_name} must be a valid IANA timezone") from error
    return timezone_name


def normalize_global_config_entity(entity: Mapping[str, Any]) -> GlobalSchedulerConfig:
    version, updated_at_utc, updated_by = require_audit_fields(entity, "global scheduler configuration")
    default_timezone = validate_timezone(entity.get("DEFAULT_TIMEZONE"), "DEFAULT_TIMEZONE")
    schedule_tag_key = str(entity.get("SCHEDULE_TAG_KEY") or "").strip()

    if not schedule_tag_key:
        raise ValueError("global scheduler configuration is missing SCHEDULE_TAG_KEY")

    return GlobalSchedulerConfig(
        dry_run=parse_bool(entity.get("DRY_RUN"), "DRY_RUN"),
        default_timezone=default_timezone,
        schedule_tag_key=schedule_tag_key,
        retain_running=parse_bool(entity.get("RETAIN_RUNNING"), "RETAIN_RUNNING"),
        retain_stopped=parse_bool(entity.get("RETAIN_STOPPED"), "RETAIN_STOPPED"),
        version=version,
        updated_at_utc=updated_at_utc,
        updated_by=updated_by,
    )


def normalize_schedule_entity(entity: Mapping[str, Any]) -> ScheduleEntityRecord:
    schedule_name = str(entity.get("RowKey") or entity.get("ScheduleName") or "").strip()
    if not schedule_name:
        raise ValueError("schedule entity is missing RowKey/ScheduleName")

    version, updated_at_utc, updated_by = require_audit_fields(entity, f"schedule '{schedule_name}'")
    enabled = parse_bool(entity.get("Enabled", True), "Enabled")
    periods = parse_periods(entity, schedule_name)
    skip_days = tuple(day.lower() for day in parse_string_list(entity.get("SkipDays"), "SkipDays"))
    scope = ScheduleScope.from_values(
        include_management_groups=parse_string_list(
            entity.get("IncludeManagementGroups"),
            "IncludeManagementGroups",
        ),
        include_subscriptions=parse_string_list(
            entity.get("IncludeSubscriptions"),
            "IncludeSubscriptions",
        ),
        exclude_management_groups=parse_string_list(
            entity.get("ExcludeManagementGroups"),
            "ExcludeManagementGroups",
        ),
        exclude_subscriptions=parse_string_list(
            entity.get("ExcludeSubscriptions"),
            "ExcludeSubscriptions",
        ),
    )

    return ScheduleEntityRecord(
        definition=ScheduleDefinition(
            name=schedule_name,
            periods=periods,
            skip_days=skip_days,
            scope=scope,
            version=version,
            updated_at_utc=updated_at_utc,
            updated_by=updated_by,
        ),
        enabled=enabled,
    )


def global_config_to_payload(config: GlobalSchedulerConfig) -> dict[str, Any]:
    return {
        "PartitionKey": DEFAULT_CONFIG_PARTITION_KEY,
        "RowKey": DEFAULT_CONFIG_ROW_KEY,
        "DRY_RUN": config.dry_run,
        "DEFAULT_TIMEZONE": config.default_timezone,
        "SCHEDULE_TAG_KEY": config.schedule_tag_key,
        "RETAIN_RUNNING": config.retain_running,
        "RETAIN_STOPPED": config.retain_stopped,
        "Version": config.version,
        "UpdatedAtUtc": config.updated_at_utc,
        "UpdatedBy": config.updated_by,
    }


def schedule_record_to_payload(record: ScheduleEntityRecord) -> dict[str, Any]:
    definition = record.definition
    payload: dict[str, Any] = {
        "PartitionKey": DEFAULT_SCHEDULE_PARTITION_KEY,
        "RowKey": definition.name,
        "Periods": [{"start": period.start, "stop": period.stop} for period in definition.periods],
        "Enabled": record.enabled,
        "Version": definition.version,
        "UpdatedAtUtc": definition.updated_at_utc,
        "UpdatedBy": definition.updated_by,
    }

    if definition.skip_days:
        payload["SkipDays"] = list(definition.skip_days)
    if definition.scope.include_management_groups:
        payload["IncludeManagementGroups"] = list(definition.scope.include_management_groups)
    if definition.scope.include_subscriptions:
        payload["IncludeSubscriptions"] = list(definition.scope.include_subscriptions)
    if definition.scope.exclude_management_groups:
        payload["ExcludeManagementGroups"] = list(definition.scope.exclude_management_groups)
    if definition.scope.exclude_subscriptions:
        payload["ExcludeSubscriptions"] = list(definition.scope.exclude_subscriptions)

    return payload


def build_global_config_entity(
    payload: Mapping[str, Any],
    *,
    updated_at_utc: str,
    updated_by: str,
) -> dict[str, Any]:
    partition_key = str(payload.get("PartitionKey") or DEFAULT_CONFIG_PARTITION_KEY).strip()
    row_key = str(payload.get("RowKey") or DEFAULT_CONFIG_ROW_KEY).strip()

    if partition_key != DEFAULT_CONFIG_PARTITION_KEY:
        raise ValueError(f"PartitionKey must be '{DEFAULT_CONFIG_PARTITION_KEY}' for global config")
    if row_key != DEFAULT_CONFIG_ROW_KEY:
        raise ValueError(f"RowKey must be '{DEFAULT_CONFIG_ROW_KEY}' for global config")

    entity = {
        "PartitionKey": partition_key,
        "RowKey": row_key,
        "DRY_RUN": parse_bool(payload.get("DRY_RUN"), "DRY_RUN"),
        "DEFAULT_TIMEZONE": validate_timezone(payload.get("DEFAULT_TIMEZONE"), "DEFAULT_TIMEZONE"),
        "SCHEDULE_TAG_KEY": str(payload.get("SCHEDULE_TAG_KEY") or "").strip(),
        "RETAIN_RUNNING": parse_bool(payload.get("RETAIN_RUNNING"), "RETAIN_RUNNING"),
        "RETAIN_STOPPED": parse_bool(payload.get("RETAIN_STOPPED"), "RETAIN_STOPPED"),
        "Version": str(payload.get("Version") or "").strip(),
        "UpdatedAtUtc": parse_iso_datetime(updated_at_utc, "UpdatedAtUtc"),
        "UpdatedBy": str(updated_by or "").strip(),
    }

    normalize_global_config_entity(entity)
    return entity


def build_schedule_entity(
    payload: Mapping[str, Any],
    *,
    updated_at_utc: str,
    updated_by: str,
    enabled_override: bool | None = None,
) -> dict[str, Any]:
    partition_key = str(payload.get("PartitionKey") or DEFAULT_SCHEDULE_PARTITION_KEY).strip()
    if partition_key != DEFAULT_SCHEDULE_PARTITION_KEY:
        raise ValueError(f"PartitionKey must be '{DEFAULT_SCHEDULE_PARTITION_KEY}' for schedules")

    row_key = str(payload.get("RowKey") or payload.get("ScheduleName") or "").strip()
    if not row_key:
        raise ValueError("RowKey is required for schedule payloads")

    entity: dict[str, Any] = {
        "PartitionKey": partition_key,
        "RowKey": row_key,
        "Enabled": parse_bool(
            enabled_override if enabled_override is not None else payload.get("Enabled", True),
            "Enabled",
        ),
        "Version": str(payload.get("Version") or "").strip(),
        "UpdatedAtUtc": parse_iso_datetime(updated_at_utc, "UpdatedAtUtc"),
        "UpdatedBy": str(updated_by or "").strip(),
    }

    periods = payload.get("Periods")
    if periods is not None:
        parsed_periods = parse_periods({"Periods": periods}, row_key)
        entity["Periods"] = json.dumps(
            [{"start": period.start, "stop": period.stop} for period in parsed_periods],
            separators=(",", ":"),
        )
    else:
        entity["Start"] = validate_hhmm(str(payload.get("Start") or "").strip(), "Start")
        entity["Stop"] = validate_hhmm(str(payload.get("Stop") or "").strip(), "Stop")

    list_fields = (
        "SkipDays",
        "IncludeManagementGroups",
        "IncludeSubscriptions",
        "ExcludeManagementGroups",
        "ExcludeSubscriptions",
    )
    for field_name in list_fields:
        values = parse_string_list(payload.get(field_name), field_name)
        if values:
            entity[field_name] = ",".join(values)

    normalize_schedule_entity(entity)
    return entity
