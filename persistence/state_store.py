from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SchedulerState:
    started_by_scheduler: bool
    stopped_by_scheduler: bool
    last_observed_state: str
    last_action: str
    updated_at_utc: str


class NoopStateStore:
    def get_state(self, resource) -> SchedulerState | None:
        return None

    def save_state(
        self,
        resource,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
        last_observed_state: str,
        last_action: str,
    ) -> None:
        return None


class AzureTableStateStore:
    def __init__(self, connection_string: str, table_name: str = "OffHoursSchedulerState") -> None:
        self.connection_string = connection_string
        self.table_name = table_name
        self._table_client = None

    def _client(self):
        if self._table_client:
            return self._table_client

        from azure.data.tables import TableServiceClient

        service = TableServiceClient.from_connection_string(self.connection_string)
        service.create_table_if_not_exists(self.table_name)
        table = service.get_table_client(self.table_name)
        self._table_client = table
        return self._table_client

    @staticmethod
    def _partition_key(resource) -> str:
        return resource.subscription_id

    @staticmethod
    def _row_key(resource) -> str:
        return hashlib.sha1(resource.id.encode("utf-8")).hexdigest()

    def get_state(self, resource) -> SchedulerState | None:
        from azure.core.exceptions import ResourceNotFoundError

        table = self._client()

        try:
            entity = table.get_entity(
                partition_key=self._partition_key(resource),
                row_key=self._row_key(resource),
            )
        except ResourceNotFoundError:
            return None

        return SchedulerState(
            started_by_scheduler=bool(entity.get("StartedByScheduler", False)),
            stopped_by_scheduler=bool(entity.get("StoppedByScheduler", False)),
            last_observed_state=entity.get("LastObservedState", "unknown"),
            last_action=entity.get("LastAction", "none"),
            updated_at_utc=entity.get("UpdatedAtUtc", ""),
        )

    def save_state(
        self,
        resource,
        started_by_scheduler: bool,
        stopped_by_scheduler: bool,
        last_observed_state: str,
        last_action: str,
    ) -> None:
        from azure.data.tables import UpdateMode

        table = self._client()

        entity = {
            "PartitionKey": self._partition_key(resource),
            "RowKey": self._row_key(resource),
            "ResourceId": resource.id,
            "ResourceGroup": resource.resource_group,
            "ResourceName": resource.name,
            "ResourceType": resource.type,
            "StartedByScheduler": bool(started_by_scheduler),
            "StoppedByScheduler": bool(stopped_by_scheduler),
            "LastObservedState": last_observed_state,
            "LastAction": last_action,
            "UpdatedAtUtc": datetime.now(timezone.utc).isoformat(),
        }

        table.upsert_entity(mode=UpdateMode.MERGE, entity=entity)
