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
    def __init__(
        self,
        connection_string: str = "",
        table_service_uri: str = "",
        table_name: str = "OffHoursSchedulerState",
        credential=None,
    ) -> None:
        self.connection_string = connection_string
        self.table_service_uri = table_service_uri
        self.table_name = table_name
        self.credential = credential
        self._table_client = None

    def _client(self):
        if self._table_client:
            return self._table_client

        if self.connection_string:
            from azure.data.tables import TableServiceClient

            service = TableServiceClient.from_connection_string(self.connection_string)
            service.create_table_if_not_exists(self.table_name)
            table = service.get_table_client(self.table_name)
            self._table_client = table
            return self._table_client

        if not self.table_service_uri:
            raise ValueError("table_service_uri is required when connection_string is not configured")

        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential

        credential = self.credential or DefaultAzureCredential()
        service = TableServiceClient(endpoint=self.table_service_uri, credential=credential)
        service.create_table_if_not_exists(self.table_name)
        table = service.get_table_client(self.table_name)
        self._table_client = table
        return self._table_client

    @staticmethod
    def _canonical_resource_id(resource) -> str:
        resource_id = str(getattr(resource, "id", "") or "").strip()
        if resource_id:
            return canonical_resource_id(resource_id)

        subscription_id = str(getattr(resource, "subscription_id", "") or "").strip().lower()
        resource_group = str(getattr(resource, "resource_group", "") or "").strip().lower()
        resource_type = str(getattr(resource, "type", "") or "").strip().lower()
        resource_name = str(getattr(resource, "name", "") or "").strip().lower()
        return "|".join((subscription_id, resource_group, resource_type, resource_name))

    @staticmethod
    def _partition_key(resource) -> str:
        return resource.subscription_id

    @classmethod
    def _row_key(cls, resource) -> str:
        return hashlib.sha1(
            cls._canonical_resource_id(resource).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()

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
            "CanonicalResourceId": self._canonical_resource_id(resource),
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


def canonical_resource_id(resource_id: str) -> str:
    return str(resource_id or "").strip().rstrip("/").lower()


def state_entity_keys_from_resource_id(resource_id: str) -> tuple[str, str]:
    normalized_resource_id = canonical_resource_id(resource_id)
    marker = "/subscriptions/"
    if marker not in normalized_resource_id:
        raise ValueError("resource_id must contain '/subscriptions/<subscription-id>'")

    subscription_id = normalized_resource_id.split(marker, 1)[1].split("/", 1)[0].strip()
    if not subscription_id:
        raise ValueError("resource_id must include a subscription id")

    row_key = hashlib.sha1(normalized_resource_id.encode("utf-8"), usedforsecurity=False).hexdigest()
    return subscription_id, row_key
