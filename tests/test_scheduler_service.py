from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from handlers.registry import HandlerRegistry
from persistence.state_store import SchedulerState
from scheduler.engine import ScheduleEngine
from scheduler.models import ScheduleDefinition, SchedulePeriod
from scheduler.service import SchedulerService


@dataclass(frozen=True)
class FakeResource:
    id: str
    name: str
    type: str
    subscription_id: str
    resource_group: str
    tags: dict[str, str]
    management_group_ids: tuple[str, ...] = ()


class FakeDiscovery:
    def __init__(self, resources):
        self._resources = resources

    def find_scheduled_resources(self):
        return self._resources


class FakeVmHandler:
    SUPPORTED_TYPES = {"microsoft.compute/virtualmachines"}

    def __init__(self, state: str = "stopped") -> None:
        self.state = state
        self.started = 0
        self.stopped = 0

    def get_state(self, resource) -> str:
        return self.state

    def start(self, resource) -> None:
        self.started += 1

    def stop(self, resource) -> None:
        self.stopped += 1


class FakeVmHandlerWithFailure(FakeVmHandler):
    def __init__(self, state: str = "stopped", fail_resource_ids: set[str] | None = None) -> None:
        super().__init__(state=state)
        self.fail_resource_ids = fail_resource_ids or set()

    def get_state(self, resource) -> str:
        if resource.id in self.fail_resource_ids:
            raise RuntimeError("simulated failure")
        return super().get_state(resource)


class FakeStateStore:
    def __init__(self, initial_started_by_scheduler: bool = False, initial_stopped_by_scheduler: bool = False) -> None:
        self.state_by_resource_id: dict[str, SchedulerState] = {}
        self.initial_started_by_scheduler = initial_started_by_scheduler
        self.initial_stopped_by_scheduler = initial_stopped_by_scheduler

    def get_state(self, resource):
        return self.state_by_resource_id.get(resource.id) or SchedulerState(
            started_by_scheduler=self.initial_started_by_scheduler,
            stopped_by_scheduler=self.initial_stopped_by_scheduler,
            last_observed_state="unknown",
            last_action="none",
            updated_at_utc="",
        )

    def save_state(
        self,
        resource,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
        last_observed_state: str,
        last_action: str,
    ) -> None:
        self.state_by_resource_id[resource.id] = SchedulerState(
            started_by_scheduler=started_by_scheduler,
            stopped_by_scheduler=stopped_by_scheduler,
            last_observed_state=last_observed_state,
            last_action=last_action,
            updated_at_utc="2026-03-06T00:00:00+00:00",
        )


def _build_engine() -> ScheduleEngine:
    return ScheduleEngine(
        schedules={
            "office-hours": ScheduleDefinition(
                name="office-hours",
                periods=(SchedulePeriod(start="08:00", stop="23:13"),),
            )
        }
    )


def test_service_dry_run_counts_actions_without_executing() -> None:
    engine = _build_engine()
    handler = FakeVmHandler()
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=True,
    )

    result = service.run(now_utc=now)

    assert result.run_id == "unknown"
    assert result.duration_sec >= 0
    assert len(result.resources) == 1
    assert result.resources[0].resource_id == resources[0].id
    assert result.resources[0].action == "START"
    assert result.resources[0].result == "DRY_RUN"
    assert result.resources[0].duration_sec >= 0
    assert result.started == 1
    assert handler.started == 0
    assert handler.stopped == 0


def test_service_skips_start_when_vm_already_running() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="running")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        state_store=FakeStateStore(),
    )

    result = service.run(now_utc=now)

    assert result.started == 0
    assert result.skipped == 1
    assert handler.started == 0


def test_service_skips_stop_when_vm_already_stopped() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="stopped")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        state_store=FakeStateStore(),
    )

    result = service.run(now_utc=now)

    assert result.stopped == 0
    assert result.skipped == 1
    assert handler.stopped == 0


def test_service_retain_running_skips_stop_when_running_outside_window() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="running")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        retain_running=True,
        state_store=FakeStateStore(initial_started_by_scheduler=False),
    )

    result = service.run(now_utc=now)

    assert result.stopped == 0
    assert result.skipped == 1
    assert handler.stopped == 0


def test_service_without_retain_running_stops_when_running_outside_window() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="running")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        retain_running=False,
        state_store=FakeStateStore(),
    )

    result = service.run(now_utc=now)

    assert result.stopped == 1
    assert handler.stopped == 1


def test_service_retain_running_stops_when_started_by_scheduler() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="running")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        retain_running=True,
        state_store=FakeStateStore(initial_started_by_scheduler=True),
    )

    result = service.run(now_utc=now)

    assert result.stopped == 1
    assert handler.stopped == 1


def test_service_retain_running_is_temporary_after_crossing_an_allowed_window() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="running")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)
    state_store = FakeStateStore(initial_started_by_scheduler=False)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        retain_running=True,
        state_store=state_store,
    )

    outside_window = datetime(2026, 3, 5, 3, 0, tzinfo=ZoneInfo("UTC"))
    inside_window = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    outside_window_again = datetime(2026, 3, 6, 3, 0, tzinfo=ZoneInfo("UTC"))

    first_result = service.run(now_utc=outside_window)
    stored_after_first = state_store.state_by_resource_id[resources[0].id]
    second_result = service.run(now_utc=inside_window)
    stored_after_second = state_store.state_by_resource_id[resources[0].id]
    third_result = service.run(now_utc=outside_window_again)

    assert first_result.skipped == 1
    assert stored_after_first.last_action == "SKIP_RETAIN_RUNNING"
    assert stored_after_first.started_by_scheduler is False

    assert second_result.skipped == 1
    assert stored_after_second.last_action == "SKIP_ALREADY_RUNNING"
    assert stored_after_second.started_by_scheduler is True

    assert third_result.stopped == 1
    assert handler.stopped == 1


def test_service_retain_stopped_skips_start_when_stopped_manually() -> None:
    engine = _build_engine()
    handler = FakeVmHandler(state="stopped")
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        retain_stopped=True,
        state_store=FakeStateStore(initial_stopped_by_scheduler=False),
    )

    result = service.run(now_utc=now)

    assert result.started == 0
    assert result.skipped == 1
    assert handler.started == 0


def test_service_propagates_run_id_into_run_result() -> None:
    engine = _build_engine()
    handler = FakeVmHandler()
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            name="vm-a",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        )
    ]

    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=True,
        run_id="run-123",
    )

    result = service.run(now_utc=datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC")))

    assert result.run_id == "run-123"
