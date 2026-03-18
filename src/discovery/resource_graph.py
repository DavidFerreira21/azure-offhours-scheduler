from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledResource:
    id: str
    name: str
    type: str
    location: str
    subscription_id: str
    resource_group: str
    tags: dict[str, str]
    management_group_ids: tuple[str, ...] = ()


class ResourceGraphDiscovery:
    def __init__(
        self,
        subscription_ids: list[str],
        schedule_tag_key: str = "schedule",
        target_resource_locations: tuple[str, ...] = (),
        credential=None,
        client=None,
        query_request_factory=None,
    ) -> None:
        self.subscription_ids = subscription_ids
        self.schedule_tag_key = schedule_tag_key
        self.target_resource_locations = tuple(location.lower() for location in target_resource_locations)
        self.credential = credential
        self.client = client
        self.query_request_factory = query_request_factory

    def _build_query(self) -> str:
        escaped_key = self.schedule_tag_key.replace("'", "''")
        return f"""
Resources
| where tolower(type) == 'microsoft.compute/virtualmachines'
| where isnotempty(tostring(tags['{escaped_key}']))
| project id, name, type, location, subscriptionId, resourceGroup, tags, managementGroupAncestorsChain
"""

    def _build_client(self):
        if self.client:
            return self.client

        from azure.identity import DefaultAzureCredential
        from azure.mgmt.resourcegraph import ResourceGraphClient

        credential = self.credential or DefaultAzureCredential()
        self.client = ResourceGraphClient(credential)
        return self.client

    @staticmethod
    def _extract_management_group_ids(row: dict) -> tuple[str, ...]:
        raw_chain = row.get("managementGroupAncestorsChain") or []
        management_group_ids: list[str] = []

        for item in raw_chain:
            if isinstance(item, dict):
                candidate = item.get("name") or item.get("id") or item.get("displayName")
            else:
                candidate = str(item)

            candidate_text = str(candidate or "").strip()
            if candidate_text and candidate_text not in management_group_ids:
                management_group_ids.append(candidate_text)

        return tuple(management_group_ids)

    def find_scheduled_resources(self) -> list[ScheduledResource]:
        client = self._build_client()

        if self.query_request_factory:
            request_factory = self.query_request_factory
        else:
            from azure.mgmt.resourcegraph.models import QueryRequest

            request_factory = QueryRequest

        request = request_factory(subscriptions=self.subscription_ids, query=self._build_query())
        result = client.resources(request)

        resources: list[ScheduledResource] = []
        for row in result.data or []:
            location = str(row.get("location") or "").strip().lower()
            if self.target_resource_locations and location not in self.target_resource_locations:
                continue

            resources.append(
                ScheduledResource(
                    id=row["id"],
                    name=row["name"],
                    type=row["type"],
                    location=location,
                    subscription_id=row["subscriptionId"],
                    resource_group=row["resourceGroup"],
                    tags=row.get("tags") or {},
                    management_group_ids=self._extract_management_group_ids(row),
                )
            )
        return resources
