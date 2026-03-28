from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from persistence.config_store import AzureTableGlobalConfigStore, AzureTableScheduleStore


@dataclass(frozen=True)
class StorageSettings:
    table_service_uri: str
    connection_string: str
    config_table_name: str
    schedule_table_name: str
    state_table_name: str

    @classmethod
    def from_args(cls, args) -> "StorageSettings":
        table_service_uri = (
            getattr(args, "table_service_uri", "")
            or os.getenv("OFFHOURS_TABLE_SERVICE_URI", "")
            or os.getenv("SCHEDULER_TABLE_SERVICE_URI", "")
        ).strip()
        connection_string = (
            getattr(args, "connection_string", "")
            or os.getenv("OFFHOURS_CONNECTION_STRING", "")
            or os.getenv("SCHEDULER_STORAGE_CONNECTION_STRING", "")
            or os.getenv("STATE_STORAGE_CONNECTION_STRING", "")
            or os.getenv("AzureWebJobsStorage", "")
        ).strip()

        if not table_service_uri and not connection_string:
            raise ValueError("Provide --table-service-uri or --connection-string, or configure the equivalent env vars")

        return cls(
            table_service_uri=table_service_uri,
            connection_string=connection_string,
            config_table_name=(
                getattr(args, "config_table", "")
                or os.getenv("CONFIG_STORAGE_TABLE_NAME", "OffHoursSchedulerConfig")
            ).strip()
            or "OffHoursSchedulerConfig",
            schedule_table_name=(
                getattr(args, "schedule_table", "")
                or os.getenv("SCHEDULE_STORAGE_TABLE_NAME", "OffHoursSchedulerSchedules")
            ).strip()
            or "OffHoursSchedulerSchedules",
            state_table_name=(
                getattr(args, "state_table", "")
                or os.getenv("STATE_STORAGE_TABLE_NAME", "OffHoursSchedulerState")
            ).strip()
            or "OffHoursSchedulerState",
        )


class AzureTableSession:
    def __init__(self, settings: StorageSettings, credential=None, service_client=None) -> None:
        self.settings = settings
        self._credential = credential
        self._service_client = service_client

    @property
    def auth_mode(self) -> str:
        if self.settings.connection_string:
            return "connection-string"
        return "defaultazurecredential"

    def credential(self):
        if self.settings.connection_string:
            return None

        if self._credential is None:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
        return self._credential

    def check_token(self) -> dict[str, Any]:
        if self.settings.connection_string:
            return {
                "auth_mode": self.auth_mode,
                "credential_class": "connection-string",
                "status": "skipped",
            }

        credential = self.credential()
        token = credential.get_token("https://storage.azure.com/.default")
        return {
            "auth_mode": self.auth_mode,
            "credential_class": credential.__class__.__name__,
            "status": "ok",
            "expires_on": token.expires_on,
        }

    def service_client(self):
        if self._service_client is not None:
            return self._service_client

        from azure.data.tables import TableServiceClient

        if self.settings.connection_string:
            self._service_client = TableServiceClient.from_connection_string(self.settings.connection_string)
        else:
            self._service_client = TableServiceClient(
                endpoint=self.settings.table_service_uri,
                credential=self.credential(),
            )
        return self._service_client

    def list_table_names(self) -> set[str]:
        table_names: set[str] = set()
        for item in self.service_client().list_tables():
            if isinstance(item, dict):
                name = item.get("name")
            else:
                name = getattr(item, "name", None)
            if name:
                table_names.add(str(name))
        return table_names

    def table_client(self, table_name: str):
        return self.service_client().get_table_client(table_name)

    def config_store(self) -> AzureTableGlobalConfigStore:
        return AzureTableGlobalConfigStore(
            connection_string=self.settings.connection_string,
            table_service_uri=self.settings.table_service_uri,
            table_name=self.settings.config_table_name,
            credential=self.credential(),
            client=self.table_client(self.settings.config_table_name),
        )

    def schedule_store(self) -> AzureTableScheduleStore:
        return AzureTableScheduleStore(
            connection_string=self.settings.connection_string,
            table_service_uri=self.settings.table_service_uri,
            table_name=self.settings.schedule_table_name,
            credential=self.credential(),
            client=self.table_client(self.settings.schedule_table_name),
        )
