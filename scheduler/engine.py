from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


class Decision(str, Enum):
    START = "START"
    STOP = "STOP"
    SKIP = "SKIP"


@dataclass(frozen=True)
class EvaluationResult:
    decision: Decision
    reason: str


class ScheduleEngine:
    def __init__(self, schedules_file: str, schedule_tag_key: str = "schedule") -> None:
        self.schedules_file = schedules_file
        self.schedule_tag_key = schedule_tag_key
        self._schedules = self._load_schedules(schedules_file)

    @staticmethod
    def _load_schedules(path: str) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Schedule file not found: {path}")

        with file_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        if not isinstance(data, dict):
            raise ValueError("Schedules file must define a mapping of schedule names.")

        return data

    def evaluate(
        self,
        tags: dict[str, str],
        now_utc: datetime | None = None,
        default_timezone: str = "UTC",
    ) -> EvaluationResult:
        schedule_name = (tags or {}).get(self.schedule_tag_key)
        if not schedule_name:
            return EvaluationResult(Decision.SKIP, f"resource has no '{self.schedule_tag_key}' tag")

        schedule = self._schedules.get(schedule_name)
        if not schedule:
            return EvaluationResult(Decision.SKIP, f"schedule '{schedule_name}' not found")

        timezone_name = (tags or {}).get("timezone") or default_timezone
        try:
            timezone = ZoneInfo(timezone_name)
        except Exception:
            return EvaluationResult(Decision.SKIP, f"invalid timezone '{timezone_name}'")

        current_utc = now_utc or datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
        now_local = current_utc.astimezone(timezone)
        weekday_name = now_local.strftime("%A").lower()

        skip_days = {day.lower() for day in schedule.get("skip_days", [])}
        if weekday_name in skip_days:
            return EvaluationResult(Decision.SKIP, f"weekday '{weekday_name}' configured as skip")

        current_minute = now_local.hour * 60 + now_local.minute
        periods = self._extract_periods(schedule)

        for period in periods:
            start_minute = self._hhmm_to_minutes(period.get("start"))
            stop_minute = self._hhmm_to_minutes(period.get("stop"))
            if start_minute <= current_minute < stop_minute:
                return EvaluationResult(Decision.START, "current time is within schedule period")

        return EvaluationResult(Decision.STOP, "current time is outside schedule periods")

    @staticmethod
    def _extract_periods(schedule: dict[str, Any]) -> list[dict[str, str]]:
        configured_periods = schedule.get("periods")
        if configured_periods is not None:
            if not isinstance(configured_periods, list) or not configured_periods:
                raise ValueError("Schedule 'periods' must be a non-empty list")
            return configured_periods

        # Backward-compatible format.
        return [{"start": schedule.get("start"), "stop": schedule.get("stop")}]

    @staticmethod
    def _hhmm_to_minutes(value: str | None) -> int:
        if not value:
            raise ValueError("Schedule must include 'start' and 'stop' in HH:MM format")

        hh_str, mm_str = value.split(":")
        hh = int(hh_str)
        mm = int(mm_str)

        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"Invalid HH:MM value: {value}")

        return hh * 60 + mm
