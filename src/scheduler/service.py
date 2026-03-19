from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter

from handlers.registry import HandlerRegistry
from persistence.state_store import NoopStateStore
from scheduler.engine import Decision, ScheduleEngine


@dataclass(frozen=True)
class SchedulerSummary:
    total: int
    started: int
    stopped: int
    skipped: int


@dataclass(frozen=True)
class ActionOutcome:
    action: str
    result: str
    reason: str
    started: int = 0
    stopped: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class ResourceExecutionResult:
    resource_id: str
    name: str
    type: str
    action: str
    result: str
    reason: str
    duration_sec: float
    started: int = 0
    stopped: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class SchedulerRunResult:
    run_id: str
    timestamp: str
    dry_run: bool
    summary: SchedulerSummary
    duration_sec: float
    resources: tuple[ResourceExecutionResult, ...]

    @property
    def total(self) -> int:
        return self.summary.total

    @property
    def started(self) -> int:
        return self.summary.started

    @property
    def stopped(self) -> int:
        return self.summary.stopped

    @property
    def skipped(self) -> int:
        return self.summary.skipped


class SchedulerService:
    def __init__(
        self,
        engine: ScheduleEngine,
        discovery,
        registry: HandlerRegistry,
        dry_run: bool = True,
        default_timezone: str = "UTC",
        retain_running: bool = False,
        retain_stopped: bool = False,
        max_workers: int = 5,
        state_store=None,
        run_id: str = "",
    ) -> None:
        self.engine = engine
        self.discovery = discovery
        self.registry = registry
        self.dry_run = dry_run
        self.default_timezone = default_timezone
        self.retain_running = retain_running
        self.retain_stopped = retain_stopped
        self.max_workers = max(1, max_workers)
        self.state_store = state_store or NoopStateStore()
        self.run_id = run_id or "unknown"

    def run(self, now_utc: datetime | None = None) -> SchedulerRunResult:
        started_at = datetime.now(timezone.utc)
        cycle_started = perf_counter()
        resources = self.discovery.find_scheduled_resources()
        if not resources:
            return SchedulerRunResult(
                run_id=self.run_id,
                timestamp=started_at.isoformat().replace("+00:00", "Z"),
                dry_run=self.dry_run,
                summary=SchedulerSummary(total=0, started=0, stopped=0, skipped=0),
                duration_sec=round(perf_counter() - cycle_started, 6),
                resources=(),
            )

        started = stopped = skipped = 0
        resource_results: list[ResourceExecutionResult] = []
        workers = min(self.max_workers, len(resources))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self._process_resource, resource, now_utc) for resource in resources]
            for future in as_completed(futures):
                resource_result = future.result()
                resource_results.append(resource_result)
                started += resource_result.started
                stopped += resource_result.stopped
                skipped += resource_result.skipped

        return SchedulerRunResult(
            run_id=self.run_id,
            timestamp=started_at.isoformat().replace("+00:00", "Z"),
            dry_run=self.dry_run,
            summary=SchedulerSummary(total=len(resources), started=started, stopped=stopped, skipped=skipped),
            duration_sec=round(perf_counter() - cycle_started, 6),
            resources=tuple(sorted(resource_results, key=lambda item: item.resource_id)),
        )

    def _process_resource(self, resource, now_utc: datetime | None) -> ResourceExecutionResult:
        started_at = perf_counter()
        try:
            result = self._evaluate_resource(resource, now_utc)
            handler = self.registry.get_handler(resource.type)

            if result.decision == Decision.SKIP:
                self._log_info("SKIP %s (%s)", resource.id, result.reason)
                return self._build_resource_result(
                    resource=resource,
                    outcome=ActionOutcome(
                        action=Decision.SKIP.value,
                        result="SKIPPED",
                        reason=result.reason,
                        skipped=1,
                    ),
                    started_at=started_at,
                )

            if not handler:
                reason = f"no handler for {resource.type}"
                self._log_info("SKIP %s (%s)", resource.id, reason)
                return self._build_resource_result(
                    resource=resource,
                    outcome=ActionOutcome(action=result.decision.value, result="SKIPPED", reason=reason, skipped=1),
                    started_at=started_at,
                )

            if self.dry_run:
                return self._build_resource_result(
                    resource=resource,
                    outcome=self._dry_run_outcome(resource, result.decision),
                    started_at=started_at,
                )

            current_state = handler.get_state(resource)
            stored_state = self.state_store.get_state(resource)
            started_by_scheduler = stored_state.started_by_scheduler if stored_state else False
            stopped_by_scheduler = stored_state.stopped_by_scheduler if stored_state else False

            if result.decision == Decision.START:
                return self._build_resource_result(
                    resource=resource,
                    outcome=self._handle_start_decision(
                        resource=resource,
                        handler=handler,
                        current_state=current_state,
                        stored_state=stored_state,
                        started_by_scheduler=started_by_scheduler,
                        stopped_by_scheduler=stopped_by_scheduler,
                    ),
                    started_at=started_at,
                )

            return self._build_resource_result(
                resource=resource,
                outcome=self._handle_stop_decision(
                    resource=resource,
                    handler=handler,
                    current_state=current_state,
                    started_by_scheduler=started_by_scheduler,
                    stopped_by_scheduler=stopped_by_scheduler,
                ),
                started_at=started_at,
            )
        except Exception as error:
            self._log_exception("Failed to process resource %s: %s", getattr(resource, "id", "<unknown>"), error)
            return self._build_resource_result(
                resource=resource,
                outcome=ActionOutcome(action="ERROR", result="FAILED", reason=str(error), skipped=1),
                started_at=started_at,
            )

    def _evaluate_resource(self, resource, now_utc: datetime | None):
        return self.engine.evaluate(
            resource.tags,
            now_utc=now_utc,
            default_timezone=self.default_timezone,
            subscription_id=resource.subscription_id,
            management_group_ids=getattr(resource, "management_group_ids", ()),
        )

    def _log_info(self, message: str, *args) -> None:
        logging.info("[run_id=%s] " + message, self.run_id, *args)

    def _log_exception(self, message: str, *args) -> None:
        logging.exception("[run_id=%s] " + message, self.run_id, *args)

    def _log_structured_resource_result(self, resource_result: ResourceExecutionResult) -> None:
        logging.info(
            json.dumps(
                {
                    "event": "resource_result",
                    "run_id": self.run_id,
                    "resource_id": resource_result.resource_id,
                    "name": resource_result.name,
                    "type": resource_result.type,
                    "action": resource_result.action,
                    "result": resource_result.result,
                    "reason": resource_result.reason,
                    "duration_sec": resource_result.duration_sec,
                },
                sort_keys=True,
            )
        )

    def _build_resource_result(
        self,
        *,
        resource,
        outcome: ActionOutcome,
        started_at: float,
    ) -> ResourceExecutionResult:
        resource_result = ResourceExecutionResult(
            resource_id=getattr(resource, "id", "<unknown>"),
            name=getattr(resource, "name", "<unknown>"),
            type=getattr(resource, "type", "<unknown>"),
            action=outcome.action,
            result=outcome.result,
            reason=outcome.reason,
            duration_sec=round(perf_counter() - started_at, 6),
            started=outcome.started,
            stopped=outcome.stopped,
            skipped=outcome.skipped,
        )
        self._log_structured_resource_result(resource_result)
        return resource_result

    @staticmethod
    def _skip_outcome(action: str, reason: str) -> ActionOutcome:
        return ActionOutcome(action=action, result="SKIPPED", reason=reason, skipped=1)

    def _dry_run_outcome(self, resource, decision: Decision) -> ActionOutcome:
        self._log_info("DRY_RUN %s %s", decision.value, resource.id)
        if decision == Decision.START:
            return ActionOutcome(
                action=Decision.START.value,
                result="DRY_RUN",
                reason="dry run enabled",
                started=1,
            )
        return ActionOutcome(
            action=Decision.STOP.value,
            result="DRY_RUN",
            reason="dry run enabled",
            stopped=1,
        )

    def _save_state(
        self,
        *,
        resource,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
        last_observed_state: str,
        last_action: str,
    ) -> None:
        self.state_store.save_state(
            resource=resource,
            started_by_scheduler=started_by_scheduler,
            stopped_by_scheduler=stopped_by_scheduler,
            last_observed_state=last_observed_state,
            last_action=last_action,
        )

    def _handle_start_decision(
        self,
        *,
        resource,
        handler,
        current_state: str,
        stored_state,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
    ) -> ActionOutcome:
        if current_state == "running":
            retain_running_consumed = (
                self.retain_running
                and not started_by_scheduler
                and stored_state is not None
                and stored_state.last_action == "SKIP_RETAIN_RUNNING"
            )
            self._log_info("SKIP %s (already running)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=True if retain_running_consumed else started_by_scheduler,
                stopped_by_scheduler=False if retain_running_consumed else stopped_by_scheduler,
                last_observed_state=current_state,
                last_action="SKIP_ALREADY_RUNNING",
            )
            return self._skip_outcome(Decision.START.value, "already running")

        if self.retain_stopped and current_state == "stopped" and not stopped_by_scheduler:
            self._log_info("SKIP %s (retain_stopped enabled)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=started_by_scheduler,
                stopped_by_scheduler=False,
                last_observed_state=current_state,
                last_action="SKIP_RETAIN_STOPPED",
            )
            return self._skip_outcome(Decision.START.value, "retain_stopped enabled")

        handler.start(resource)
        self._log_info("START %s", resource.id)
        self._save_state(
            resource=resource,
            started_by_scheduler=True,
            stopped_by_scheduler=False,
            last_observed_state="running",
            last_action="START",
        )
        return ActionOutcome(
            action=Decision.START.value,
            result="EXECUTED",
            reason="resource started",
            started=1,
        )

    def _handle_stop_decision(
        self,
        *,
        resource,
        handler,
        current_state: str,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
    ) -> ActionOutcome:
        if self.retain_running and current_state == "running" and not started_by_scheduler:
            self._log_info("SKIP %s (retain_running enabled)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=False,
                stopped_by_scheduler=stopped_by_scheduler,
                last_observed_state=current_state,
                last_action="SKIP_RETAIN_RUNNING",
            )
            return self._skip_outcome(Decision.STOP.value, "retain_running enabled")

        if current_state == "stopped":
            self._log_info("SKIP %s (already stopped)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=started_by_scheduler,
                stopped_by_scheduler=stopped_by_scheduler,
                last_observed_state=current_state,
                last_action="SKIP_ALREADY_STOPPED",
            )
            return self._skip_outcome(Decision.STOP.value, "already stopped")

        handler.stop(resource)
        self._log_info("STOP %s", resource.id)
        self._save_state(
            resource=resource,
            started_by_scheduler=False,
            stopped_by_scheduler=True,
            last_observed_state="stopped",
            last_action="STOP",
        )
        return ActionOutcome(
            action=Decision.STOP.value,
            result="EXECUTED",
            reason="resource stopped",
            stopped=1,
        )
