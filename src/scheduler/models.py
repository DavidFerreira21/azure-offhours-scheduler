from __future__ import annotations

from dataclasses import dataclass


def _normalize_subscription_id(value: str) -> str:
    normalized = (value or "").strip().lower()
    marker = "/subscriptions/"
    if marker in normalized:
        normalized = normalized.split(marker, 1)[1]
    return normalized.strip("/")


def _normalize_management_group_id(value: str) -> str:
    normalized = (value or "").strip().lower()
    marker = "/managementgroups/"
    if marker in normalized:
        normalized = normalized.split(marker, 1)[1]
    return normalized.strip("/")


@dataclass(frozen=True)
class SchedulePeriod:
    start: str
    stop: str


@dataclass(frozen=True)
class ScheduleScope:
    include_management_groups: tuple[str, ...] = ()
    include_subscriptions: tuple[str, ...] = ()
    exclude_management_groups: tuple[str, ...] = ()
    exclude_subscriptions: tuple[str, ...] = ()

    def matches(self, subscription_id: str, management_group_ids: list[str] | tuple[str, ...] | None = None) -> bool:
        normalized_subscription_id = _normalize_subscription_id(subscription_id)
        normalized_management_groups = {
            _normalize_management_group_id(value)
            for value in (management_group_ids or ())
            if _normalize_management_group_id(value)
        }

        if normalized_subscription_id in self.exclude_subscriptions:
            return False
        if normalized_management_groups.intersection(self.exclude_management_groups):
            return False

        includes_configured = bool(self.include_subscriptions or self.include_management_groups)
        if not includes_configured:
            return True

        if normalized_subscription_id in self.include_subscriptions:
            return True
        if normalized_management_groups.intersection(self.include_management_groups):
            return True

        return False

    @classmethod
    def from_values(
        cls,
        include_management_groups: list[str] | tuple[str, ...] | None = None,
        include_subscriptions: list[str] | tuple[str, ...] | None = None,
        exclude_management_groups: list[str] | tuple[str, ...] | None = None,
        exclude_subscriptions: list[str] | tuple[str, ...] | None = None,
    ) -> "ScheduleScope":
        return cls(
            include_management_groups=tuple(
                value
                for value in (_normalize_management_group_id(item) for item in (include_management_groups or ()))
                if value
            ),
            include_subscriptions=tuple(
                value
                for value in (_normalize_subscription_id(item) for item in (include_subscriptions or ()))
                if value
            ),
            exclude_management_groups=tuple(
                value
                for value in (_normalize_management_group_id(item) for item in (exclude_management_groups or ()))
                if value
            ),
            exclude_subscriptions=tuple(
                value
                for value in (_normalize_subscription_id(item) for item in (exclude_subscriptions or ()))
                if value
            ),
        )


@dataclass(frozen=True)
class ScheduleDefinition:
    name: str
    periods: tuple[SchedulePeriod, ...]
    skip_days: tuple[str, ...] = ()
    scope: ScheduleScope = ScheduleScope()
    version: str = ""
    updated_at_utc: str = ""
    updated_by: str = ""


@dataclass(frozen=True)
class GlobalSchedulerConfig:
    dry_run: bool
    default_timezone: str
    schedule_tag_key: str
    retain_running: bool
    retain_stopped: bool
    version: str
    updated_at_utc: str
    updated_by: str
