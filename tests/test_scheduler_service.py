from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from handlers.registry import HandlerRegistry
from persistence.state_store import SchedulerState
from scheduler.engine import ScheduleEngine
from scheduler.service import SchedulerService


@dataclass(frozen=True)
class FakeResource:
    id: str
    name: str
    type: str
    subscription_id: str
    resource_group: str
    tags: dict[str, str]


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


def test_service_dry_run_counts_actions_without_executing() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
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

    assert result.started == 1
    assert handler.started == 0
    assert handler.stopped == 0


def test_service_skips_start_when_vm_already_running() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
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
    engine = ScheduleEngine("schedules/schedules.yaml")
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
    engine = ScheduleEngine("schedules/schedules.yaml")
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
    engine = ScheduleEngine("schedules/schedules.yaml")
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
    engine = ScheduleEngine("schedules/schedules.yaml")
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


def test_service_retain_stopped_skips_start_when_stopped_manually() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
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


def test_service_retain_stopped_starts_when_previously_stopped_by_scheduler() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
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
        state_store=FakeStateStore(initial_stopped_by_scheduler=True),
    )

    result = service.run(now_utc=now)

    assert result.started == 1
    assert handler.started == 1


def test_service_continues_processing_when_one_resource_fails() -> None:
    engine = ScheduleEngine("schedules/schedules.yaml")
    failing_id = "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-fail"
    handler = FakeVmHandlerWithFailure(state="stopped", fail_resource_ids={failing_id})
    registry = HandlerRegistry()
    registry.register(handler.SUPPORTED_TYPES, handler)

    resources = [
        FakeResource(
            id=failing_id,
            name="vm-fail",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        ),
        FakeResource(
            id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-ok",
            name="vm-ok",
            type="microsoft.compute/virtualmachines",
            subscription_id="sub-1",
            resource_group="rg",
            tags={"schedule": "office-hours", "timezone": "America/Sao_Paulo"},
        ),
    ]

    now = datetime(2026, 3, 5, 13, 0, tzinfo=ZoneInfo("UTC"))
    service = SchedulerService(
        engine=engine,
        discovery=FakeDiscovery(resources),
        registry=registry,
        dry_run=False,
        max_workers=2,
        state_store=FakeStateStore(),
    )

    result = service.run(now_utc=now)

    assert result.total == 2
    assert result.started == 1
    assert result.skipped == 1
