from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from scheduler.models import ScheduleDefinition


class Decision(str, Enum):
    START = "START"
    STOP = "STOP"
    SKIP = "SKIP"


@dataclass(frozen=True)
class EvaluationResult:
    decision: Decision
    reason: str


class ScheduleEngine:
    def __init__(self, schedules: dict[str, ScheduleDefinition], schedule_tag_key: str = "schedule") -> None:
        self.schedules = schedules
        self.schedule_tag_key = schedule_tag_key

    def evaluate(
        self,
        tags: dict[str, str],
        now_utc: datetime | None = None,
        default_timezone: str = "UTC",
        subscription_id: str = "",
        management_group_ids: list[str] | tuple[str, ...] | None = None,
    ) -> EvaluationResult:
        schedule_name = (tags or {}).get(self.schedule_tag_key)
        if not schedule_name:
            return EvaluationResult(Decision.SKIP, f"resource has no '{self.schedule_tag_key}' tag")

        schedule = self.schedules.get(schedule_name)
        if not schedule:
            return EvaluationResult(Decision.SKIP, f"schedule '{schedule_name}' not found")

        if not schedule.scope.matches(subscription_id=subscription_id, management_group_ids=management_group_ids):
            return EvaluationResult(Decision.SKIP, f"resource is outside schedule '{schedule_name}' scope")

        timezone_name = (tags or {}).get("timezone") or default_timezone
        try:
            timezone = ZoneInfo(timezone_name)
        except Exception:
            return EvaluationResult(Decision.SKIP, f"invalid timezone '{timezone_name}'")

        current_utc = now_utc or datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
        now_local = current_utc.astimezone(timezone)
        weekday_name = now_local.strftime("%A").lower()

        skip_days = set(schedule.skip_days)
        if weekday_name in skip_days:
            return EvaluationResult(Decision.SKIP, f"weekday '{weekday_name}' configured as skip")

        current_minute = now_local.hour * 60 + now_local.minute
        for period in schedule.periods:
            start_minute = self._hhmm_to_minutes(period.start)
            stop_minute = self._hhmm_to_minutes(period.stop)
            if start_minute <= current_minute < stop_minute:
                return EvaluationResult(Decision.START, "current time is within schedule period")

        return EvaluationResult(Decision.STOP, "current time is outside schedule periods")

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
