from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.engine import Decision, ScheduleEngine


def test_returns_start_during_window() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "office-hours", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.START


def test_returns_stop_outside_window() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    now = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "office-hours", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.STOP


def test_returns_skip_on_skip_day() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    now = datetime(2026, 3, 7, 15, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "weekend-off", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.SKIP


def test_uses_default_timezone_when_tag_is_missing() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "office-hours"}

    result = engine.evaluate(tags, now_utc=now, default_timezone="America/Sao_Paulo")

    assert result.decision == Decision.START


def test_uses_configurable_schedule_tag_key() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml", schedule_tag_key="offhours")
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"offhours": "office-hours", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.START


def test_returns_stop_outside_split_period_gap() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    now = datetime(2026, 3, 5, 15, 30, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "lab", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.STOP


def test_returns_start_inside_split_period() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    now = datetime(2026, 3, 5, 16, 30, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "lab", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.START
