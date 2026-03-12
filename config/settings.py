from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    schedules_file: str
    subscription_ids: list[str]
    dry_run: bool
    default_timezone: str
    schedule_tag_key: str
    retain_running: bool
    retain_stopped: bool
    state_storage_connection_string: str
    state_storage_table_name: str
    max_workers: int

    @classmethod
    def from_env(cls) -> "Settings":
        subscriptions_raw = os.getenv("AZURE_SUBSCRIPTION_IDS", "")
        subscription_ids = [value.strip() for value in subscriptions_raw.split(",") if value.strip()]
        if not subscription_ids:
            raise ValueError("AZURE_SUBSCRIPTION_IDS is required")

        dry_run = os.getenv("DRY_RUN", "true").strip().lower() in {"1", "true", "yes"}
        default_timezone = os.getenv("DEFAULT_TIMEZONE", "UTC").strip() or "UTC"
        schedule_tag_key = os.getenv("SCHEDULE_TAG_KEY", "schedule").strip() or "schedule"
        retain_running = os.getenv("RETAIN_RUNNING", "false").strip().lower() in {"1", "true", "yes"}
        retain_stopped = os.getenv("RETAIN_STOPPED", "false").strip().lower() in {"1", "true", "yes"}
        state_storage_connection_string = (
            os.getenv("STATE_STORAGE_CONNECTION_STRING", "").strip()
            or os.getenv("AzureWebJobsStorage", "").strip()
        )
        state_storage_table_name = os.getenv("STATE_STORAGE_TABLE_NAME", "OffHoursSchedulerState").strip() or "OffHoursSchedulerState"
        max_workers_raw = os.getenv("MAX_WORKERS", "5").strip() or "5"
        try:
            max_workers = int(max_workers_raw)
        except ValueError as error:
            raise ValueError("MAX_WORKERS must be an integer") from error
        schedules_file_raw = os.getenv("SCHEDULES_FILE", "schedules/schedules.yaml")
        schedules_file_path = cls._resolve_schedules_path(schedules_file_raw)

        return cls(
            schedules_file=str(schedules_file_path),
            subscription_ids=subscription_ids,
            dry_run=dry_run,
            default_timezone=default_timezone,
            schedule_tag_key=schedule_tag_key,
            retain_running=retain_running,
            retain_stopped=retain_stopped,
            state_storage_connection_string=state_storage_connection_string,
            state_storage_table_name=state_storage_table_name,
            max_workers=max(1, max_workers),
        )

    @staticmethod
    def _resolve_schedules_path(value: str) -> Path:
        raw_path = Path(value)
        if raw_path.is_absolute():
            return raw_path

        # 1) Resolve from current working directory (expected when running func in cmd/function_app).
        cwd_candidate = (Path.cwd() / raw_path).resolve()
        if cwd_candidate.exists():
            return cwd_candidate

        # 2) Resolve from repository root (expected when running from repo root).
        repo_root = Path(__file__).resolve().parents[1]
        repo_candidate = (repo_root / raw_path).resolve()
        if repo_candidate.exists():
            return repo_candidate

        # Fallback to CWD resolution for consistent error messages downstream.
        return cwd_candidate
