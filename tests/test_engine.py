from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.engine import Decision, ScheduleEngine
from scheduler.models import ScheduleDefinition, SchedulePeriod, ScheduleScope


def _build_engine(schedule_tag_key: str = "schedule") -> ScheduleEngine:
    return ScheduleEngine(
        schedules={
            "office-hours": ScheduleDefinition(
                name="office-hours",
                periods=(SchedulePeriod(start="08:00", stop="23:13"),),
            ),
            "lab": ScheduleDefinition(
                name="lab",
                periods=(
                    SchedulePeriod(start="09:00", stop="12:00"),
                    SchedulePeriod(start="13:00", stop="18:00"),
                ),
            ),
            "weekend-off": ScheduleDefinition(
                name="weekend-off",
                periods=(SchedulePeriod(start="08:00", stop="19:00"),),
                skip_days=("saturday", "sunday"),
            ),
            "scoped": ScheduleDefinition(
                name="scoped",
                periods=(SchedulePeriod(start="08:00", stop="19:00"),),
                scope=ScheduleScope.from_values(
                    include_subscriptions=["sub-1"],
                    exclude_management_groups=["mg-blocked"],
                ),
            ),
        },
        schedule_tag_key=schedule_tag_key,
    )


def test_returns_start_during_window() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "office-hours", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.START


def test_returns_stop_outside_window() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "office-hours", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.STOP


def test_returns_skip_on_skip_day() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 7, 15, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "weekend-off", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.SKIP


def test_uses_default_timezone_when_tag_is_missing() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "office-hours"}

    result = engine.evaluate(tags, now_utc=now, default_timezone="America/Sao_Paulo")

    assert result.decision == Decision.START


def test_uses_configurable_schedule_tag_key() -> None:
    engine = _build_engine(schedule_tag_key="offhours")
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"offhours": "office-hours", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.START


def test_returns_stop_outside_split_period_gap() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 15, 30, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "lab", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.STOP


def test_returns_start_inside_split_period() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 16, 30, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "lab", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now)

    assert result.decision == Decision.START


def test_scope_includes_allowed_subscription() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "scoped", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now, subscription_id="sub-1", management_group_ids=["mg-a"])

    assert result.decision == Decision.START


def test_scope_excludes_win_over_includes() -> None:
    engine = _build_engine()
    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    tags = {"schedule": "scoped", "timezone": "America/Sao_Paulo"}

    result = engine.evaluate(tags, now_utc=now, subscription_id="sub-1", management_group_ids=["mg-blocked"])

    assert result.decision == Decision.SKIP
