from __future__ import annotations

import os
from dataclasses import dataclass


def _read_csv_env(name: str, normalize_lower: bool = False) -> tuple[str, ...]:
    raw_value = os.getenv(name, "")
    items: list[str] = []

    for item in raw_value.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        if normalize_lower:
            normalized = normalized.lower()
        items.append(normalized)

    return tuple(items)


def _read_required_subscription_ids() -> list[str]:
    subscription_ids = list(_read_csv_env("AZURE_SUBSCRIPTION_IDS"))
    if not subscription_ids:
        raise ValueError("AZURE_SUBSCRIPTION_IDS is required")
    return subscription_ids


def _read_target_resource_locations() -> tuple[str, ...]:
    return _read_csv_env("TARGET_RESOURCE_LOCATIONS", normalize_lower=True)


def _read_table_storage_connection_string() -> str:
    connection_string = (
        os.getenv("SCHEDULER_STORAGE_CONNECTION_STRING", "").strip()
        or os.getenv("STATE_STORAGE_CONNECTION_STRING", "").strip()
        or os.getenv("AzureWebJobsStorage", "").strip()
    )
    if not connection_string:
        raise ValueError(
            "SCHEDULER_STORAGE_CONNECTION_STRING is required when AzureWebJobsStorage is not configured"
        )
    return connection_string


def _read_table_name(env_name: str, default_value: str) -> str:
    return os.getenv(env_name, default_value).strip() or default_value


def _read_max_workers() -> int:
    raw_value = os.getenv("MAX_WORKERS", "5").strip() or "5"
    try:
        return max(1, int(raw_value))
    except ValueError as error:
        raise ValueError("MAX_WORKERS must be an integer") from error


def _read_bool_env(name: str, default_value: bool = False) -> bool:
    raw_value = os.getenv(name, str(default_value)).strip().lower()
    if raw_value in {"true", "1", "yes", "y", "on"}:
        return True
    if raw_value in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _read_resource_result_log_mode() -> str:
    raw_value = os.getenv("RESOURCE_RESULT_LOG_MODE", "executed-and-errors").strip().lower()
    allowed_values = {"executed-and-errors", "all"}
    if raw_value not in allowed_values:
        raise ValueError("RESOURCE_RESULT_LOG_MODE must be one of: executed-and-errors, all")
    return raw_value


@dataclass(frozen=True)
class Settings:
    subscription_ids: list[str]
    target_resource_locations: tuple[str, ...]
    table_storage_connection_string: str
    config_storage_table_name: str
    schedule_storage_table_name: str
    state_storage_table_name: str
    max_workers: int
    enable_verbose_azure_sdk_logs: bool
    resource_result_log_mode: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            subscription_ids=_read_required_subscription_ids(),
            target_resource_locations=_read_target_resource_locations(),
            table_storage_connection_string=_read_table_storage_connection_string(),
            config_storage_table_name=_read_table_name("CONFIG_STORAGE_TABLE_NAME", "OffHoursSchedulerConfig"),
            schedule_storage_table_name=_read_table_name(
                "SCHEDULE_STORAGE_TABLE_NAME",
                "OffHoursSchedulerSchedules",
            ),
            state_storage_table_name=_read_table_name("STATE_STORAGE_TABLE_NAME", "OffHoursSchedulerState"),
            max_workers=_read_max_workers(),
            enable_verbose_azure_sdk_logs=_read_bool_env("ENABLE_VERBOSE_AZURE_SDK_LOGS", default_value=False),
            resource_result_log_mode=_read_resource_result_log_mode(),
        )
