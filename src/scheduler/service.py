from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

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
class ResourceOutcome:
    started: int = 0
    stopped: int = 0
    skipped: int = 0


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

    def run(self, now_utc: datetime | None = None) -> SchedulerSummary:
        resources = self.discovery.find_scheduled_resources()
        if not resources:
            return SchedulerSummary(total=0, started=0, stopped=0, skipped=0)

        started = stopped = skipped = 0
        workers = min(self.max_workers, len(resources))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self._process_resource, resource, now_utc) for resource in resources]
            for future in as_completed(futures):
                outcome = future.result()
                started += outcome.started
                stopped += outcome.stopped
                skipped += outcome.skipped

        return SchedulerSummary(total=len(resources), started=started, stopped=stopped, skipped=skipped)

    def _process_resource(self, resource, now_utc: datetime | None) -> ResourceOutcome:
        try:
            result = self._evaluate_resource(resource, now_utc)
            handler = self.registry.get_handler(resource.type)

            if result.decision == Decision.SKIP:
                logging.info("SKIP %s (%s)", resource.id, result.reason)
                return ResourceOutcome(skipped=1)

            if not handler:
                logging.info("SKIP %s (no handler for %s)", resource.id, resource.type)
                return ResourceOutcome(skipped=1)

            if self.dry_run:
                return self._dry_run_outcome(resource, result.decision)

            current_state = handler.get_state(resource)
            stored_state = self.state_store.get_state(resource)
            started_by_scheduler = stored_state.started_by_scheduler if stored_state else False
            stopped_by_scheduler = stored_state.stopped_by_scheduler if stored_state else False

            if result.decision == Decision.START:
                return self._handle_start_decision(
                    resource=resource,
                    handler=handler,
                    current_state=current_state,
                    stored_state=stored_state,
                    started_by_scheduler=started_by_scheduler,
                    stopped_by_scheduler=stopped_by_scheduler,
                )

            return self._handle_stop_decision(
                resource=resource,
                handler=handler,
                current_state=current_state,
                started_by_scheduler=started_by_scheduler,
                stopped_by_scheduler=stopped_by_scheduler,
            )
        except Exception as error:
            logging.exception("Failed to process resource %s: %s", getattr(resource, "id", "<unknown>"), error)
            return ResourceOutcome(skipped=1)

    def _evaluate_resource(self, resource, now_utc: datetime | None):
        return self.engine.evaluate(
            resource.tags,
            now_utc=now_utc,
            default_timezone=self.default_timezone,
            subscription_id=resource.subscription_id,
            management_group_ids=getattr(resource, "management_group_ids", ()),
        )

    @staticmethod
    def _skip_outcome() -> ResourceOutcome:
        return ResourceOutcome(skipped=1)

    def _dry_run_outcome(self, resource, decision: Decision) -> ResourceOutcome:
        logging.info("DRY_RUN %s %s", decision.value, resource.id)
        if decision == Decision.START:
            return ResourceOutcome(started=1)
        return ResourceOutcome(stopped=1)

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
    ) -> ResourceOutcome:
        if current_state == "running":
            retain_running_consumed = (
                self.retain_running
                and not started_by_scheduler
                and stored_state is not None
                and stored_state.last_action == "SKIP_RETAIN_RUNNING"
            )
            logging.info("SKIP %s (already running)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=True if retain_running_consumed else started_by_scheduler,
                stopped_by_scheduler=False if retain_running_consumed else stopped_by_scheduler,
                last_observed_state=current_state,
                last_action="SKIP_ALREADY_RUNNING",
            )
            return self._skip_outcome()

        if self.retain_stopped and current_state == "stopped" and not stopped_by_scheduler:
            logging.info("SKIP %s (retain_stopped enabled)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=started_by_scheduler,
                stopped_by_scheduler=False,
                last_observed_state=current_state,
                last_action="SKIP_RETAIN_STOPPED",
            )
            return self._skip_outcome()

        handler.start(resource)
        logging.info("START %s", resource.id)
        self._save_state(
            resource=resource,
            started_by_scheduler=True,
            stopped_by_scheduler=False,
            last_observed_state="running",
            last_action="START",
        )
        return ResourceOutcome(started=1)

    def _handle_stop_decision(
        self,
        *,
        resource,
        handler,
        current_state: str,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
    ) -> ResourceOutcome:
        if self.retain_running and current_state == "running" and not started_by_scheduler:
            logging.info("SKIP %s (retain_running enabled)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=False,
                stopped_by_scheduler=stopped_by_scheduler,
                last_observed_state=current_state,
                last_action="SKIP_RETAIN_RUNNING",
            )
            return self._skip_outcome()

        if current_state == "stopped":
            logging.info("SKIP %s (already stopped)", resource.id)
            self._save_state(
                resource=resource,
                started_by_scheduler=started_by_scheduler,
                stopped_by_scheduler=stopped_by_scheduler,
                last_observed_state=current_state,
                last_action="SKIP_ALREADY_STOPPED",
            )
            return self._skip_outcome()

        handler.stop(resource)
        logging.info("STOP %s", resource.id)
        self._save_state(
            resource=resource,
            started_by_scheduler=False,
            stopped_by_scheduler=True,
            last_observed_state="stopped",
            last_action="STOP",
        )
        return ResourceOutcome(stopped=1)
