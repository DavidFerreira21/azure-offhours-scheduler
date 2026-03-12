from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledResource:
    id: str
    name: str
    type: str
    subscription_id: str
    resource_group: str
    tags: dict[str, str]


class ResourceGraphDiscovery:
    def __init__(
        self,
        subscription_ids: list[str],
        schedule_tag_key: str = "schedule",
        credential=None,
        client=None,
    ) -> None:
        self.subscription_ids = subscription_ids
        self.schedule_tag_key = schedule_tag_key
        self.credential = credential
        self.client = client

    def _build_query(self) -> str:
        escaped_key = self.schedule_tag_key.replace("'", "''")
        return f"""
Resources
| where tolower(type) == 'microsoft.compute/virtualmachines'
| where isnotempty(tostring(tags['{escaped_key}']))
| project id, name, type, subscriptionId, resourceGroup, tags
"""

    def _build_client(self):
        if self.client:
            return self.client

        from azure.identity import DefaultAzureCredential
        from azure.mgmt.resourcegraph import ResourceGraphClient

        credential = self.credential or DefaultAzureCredential()
        self.client = ResourceGraphClient(credential)
        return self.client

    def find_scheduled_resources(self) -> list[ScheduledResource]:
        client = self._build_client()

        from azure.mgmt.resourcegraph.models import QueryRequest

        request = QueryRequest(subscriptions=self.subscription_ids, query=self._build_query())
        result = client.resources(request)

        resources: list[ScheduledResource] = []
        for row in result.data or []:
            resources.append(
                ScheduledResource(
                    id=row["id"],
                    name=row["name"],
                    type=row["type"],
                    subscription_id=row["subscriptionId"],
                    resource_group=row["resourceGroup"],
                    tags=row.get("tags") or {},
                )
            )
        return resources
