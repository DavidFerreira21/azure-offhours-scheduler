from __future__ import annotations

import logging
import sys
from pathlib import Path

import azure.functions as func

# Ensure imports work both:
# 1) in Azure (/home/site/wwwroot with app modules under cmd/function_app package contents),
# 2) locally from repository structure.
FUNCTION_APP_ROOT = Path(__file__).resolve().parents[1]
if (FUNCTION_APP_ROOT / "config" / "settings.py").exists() and str(FUNCTION_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(FUNCTION_APP_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
if (REPO_ROOT / "config" / "settings.py").exists() and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.settings import Settings
from discovery.resource_graph import ResourceGraphDiscovery
from handlers.registry import HandlerRegistry
from handlers.vm_handler import VirtualMachineHandler
from persistence.state_store import AzureTableStateStore, NoopStateStore
from scheduler.engine import ScheduleEngine
from scheduler.service import SchedulerService


def main(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("Timer is past due")

    settings = Settings.from_env()

    engine = ScheduleEngine(
        settings.schedules_file,
        schedule_tag_key=settings.schedule_tag_key,
    )
    discovery = ResourceGraphDiscovery(
        subscription_ids=settings.subscription_ids,
        schedule_tag_key=settings.schedule_tag_key,
    )

    registry = HandlerRegistry()
    vm_handler = VirtualMachineHandler()
    registry.register(vm_handler.SUPPORTED_TYPES, vm_handler)

    state_store = NoopStateStore()
    if (settings.retain_running or settings.retain_stopped) and settings.state_storage_connection_string:
        state_store = AzureTableStateStore(
            connection_string=settings.state_storage_connection_string,
            table_name=settings.state_storage_table_name,
        )
    elif settings.retain_running or settings.retain_stopped:
        logging.warning("retain flags enabled but state storage connection string is missing; using no-op state store")

    service = SchedulerService(
        engine=engine,
        discovery=discovery,
        registry=registry,
        dry_run=settings.dry_run,
        default_timezone=settings.default_timezone,
        retain_running=settings.retain_running,
        retain_stopped=settings.retain_stopped,
        max_workers=settings.max_workers,
        state_store=state_store,
    )
    summary = service.run()

    logging.info(
        "Cycle finished: total=%s started=%s stopped=%s skipped=%s dry_run=%s default_timezone=%s schedule_tag_key=%s retain_running=%s retain_stopped=%s max_workers=%s state_table=%s",
        summary.total,
        summary.started,
        summary.stopped,
        summary.skipped,
        settings.dry_run,
        settings.default_timezone,
        settings.schedule_tag_key,
        settings.retain_running,
        settings.retain_stopped,
        settings.max_workers,
        settings.state_storage_table_name,
    )
