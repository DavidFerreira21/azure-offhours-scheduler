from __future__ import annotations

from persistence.table_entities import (
    ScheduleEntityRecord,
    normalize_global_config_entity,
    normalize_schedule_entity,
)
from scheduler.models import GlobalSchedulerConfig, ScheduleDefinition


class _AzureTableStoreBase:
    def __init__(
        self,
        connection_string: str = "",
        table_service_uri: str = "",
        table_name: str = "",
        credential=None,
        client=None,
    ) -> None:
        self.connection_string = connection_string
        self.table_service_uri = table_service_uri
        self.table_name = table_name
        self.credential = credential
        self._table_client = client

    def _client(self):
        if self._table_client:
            return self._table_client

        if self.connection_string:
            from azure.data.tables import TableServiceClient

            service = TableServiceClient.from_connection_string(self.connection_string)
            service.create_table_if_not_exists(self.table_name)
            self._table_client = service.get_table_client(self.table_name)
            return self._table_client

        if not self.table_service_uri:
            raise ValueError("table_service_uri is required when connection_string is not configured")

        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential

        credential = self.credential or DefaultAzureCredential()
        service = TableServiceClient(endpoint=self.table_service_uri, credential=credential)
        service.create_table_if_not_exists(self.table_name)
        self._table_client = service.get_table_client(self.table_name)
        return self._table_client


class AzureTableGlobalConfigStore(_AzureTableStoreBase):
    def __init__(
        self,
        connection_string: str = "",
        table_service_uri: str = "",
        table_name: str = "OffHoursSchedulerConfig",
        credential=None,
        partition_key: str = "GLOBAL",
        row_key: str = "runtime",
        client=None,
    ) -> None:
        super().__init__(
            connection_string=connection_string,
            table_service_uri=table_service_uri,
            table_name=table_name,
            credential=credential,
            client=client,
        )
        self.partition_key = partition_key
        self.row_key = row_key

    def load(self) -> GlobalSchedulerConfig:
        table = self._client()
        try:
            entity = table.get_entity(partition_key=self.partition_key, row_key=self.row_key)
        except Exception as error:
            if error.__class__.__name__ != "ResourceNotFoundError":
                raise
            raise ValueError(
                f"global scheduler configuration entity not found in table '{self.table_name}' "
                f"({self.partition_key}/{self.row_key})"
            ) from error
        return normalize_global_config_entity(entity)


class AzureTableScheduleStore(_AzureTableStoreBase):
    def __init__(
        self,
        connection_string: str = "",
        table_service_uri: str = "",
        table_name: str = "OffHoursSchedulerSchedules",
        credential=None,
        client=None,
    ) -> None:
        super().__init__(
            connection_string=connection_string,
            table_service_uri=table_service_uri,
            table_name=table_name,
            credential=credential,
            client=client,
        )

    def load_records(self) -> dict[str, ScheduleEntityRecord]:
        table = self._client()
        schedules: dict[str, ScheduleEntityRecord] = {}

        for entity in table.list_entities():
            record = normalize_schedule_entity(entity)
            schedules[record.definition.name] = record
        return schedules

    def load_all(self) -> dict[str, ScheduleDefinition]:
        return {
            name: record.definition
            for name, record in self.load_records().items()
            if record.enabled
        }
