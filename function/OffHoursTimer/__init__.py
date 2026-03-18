from __future__ import annotations

import logging
import sys
from pathlib import Path

import azure.functions as func


def _configure_import_paths() -> None:
    # Support imports:
    # 1) in Azure, where the bundle is copied into the function root
    # 2) locally, where source code lives under src/
    function_root = Path(__file__).resolve().parents[1]
    if (function_root / "config" / "settings.py").exists() and str(function_root) not in sys.path:
        sys.path.insert(0, str(function_root))

    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if (src_root / "config" / "settings.py").exists() and str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


_configure_import_paths()

from config.settings import Settings
from discovery.resource_graph import ResourceGraphDiscovery
from handlers.registry import HandlerRegistry
from handlers.vm_handler import VirtualMachineHandler
from persistence.config_store import AzureTableGlobalConfigStore, AzureTableScheduleStore
from persistence.state_store import AzureTableStateStore, NoopStateStore
from scheduler.engine import ScheduleEngine
from scheduler.service import SchedulerService


def main(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("Timer is past due")

    settings = Settings.from_env()
    global_config = AzureTableGlobalConfigStore(
        connection_string=settings.table_storage_connection_string,
        table_name=settings.config_storage_table_name,
    ).load()
    schedules = AzureTableScheduleStore(
        connection_string=settings.table_storage_connection_string,
        table_name=settings.schedule_storage_table_name,
    ).load_all()

    engine = ScheduleEngine(
        schedules=schedules,
        schedule_tag_key=global_config.schedule_tag_key,
    )
    discovery = ResourceGraphDiscovery(
        subscription_ids=settings.subscription_ids,
        schedule_tag_key=global_config.schedule_tag_key,
        target_resource_locations=settings.target_resource_locations,
    )

    registry = HandlerRegistry()
    vm_handler = VirtualMachineHandler()
    registry.register(vm_handler.SUPPORTED_TYPES, vm_handler)

    state_store = NoopStateStore()
    if global_config.retain_running or global_config.retain_stopped:
        state_store = AzureTableStateStore(
            connection_string=settings.table_storage_connection_string,
            table_name=settings.state_storage_table_name,
        )

    service = SchedulerService(
        engine=engine,
        discovery=discovery,
        registry=registry,
        dry_run=global_config.dry_run,
        default_timezone=global_config.default_timezone,
        retain_running=global_config.retain_running,
        retain_stopped=global_config.retain_stopped,
        max_workers=settings.max_workers,
        state_store=state_store,
    )
    summary = service.run()

    logging.info(
        (
            "Cycle finished: total=%s started=%s stopped=%s skipped=%s "
            "dry_run=%s default_timezone=%s schedule_tag_key=%s "
            "retain_running=%s retain_stopped=%s max_workers=%s "
            "state_table=%s target_resource_locations=%s"
        ),
        summary.total,
        summary.started,
        summary.stopped,
        summary.skipped,
        global_config.dry_run,
        global_config.default_timezone,
        global_config.schedule_tag_key,
        global_config.retain_running,
        global_config.retain_stopped,
        settings.max_workers,
        settings.state_storage_table_name,
        ",".join(settings.target_resource_locations) or "<all>",
    )
