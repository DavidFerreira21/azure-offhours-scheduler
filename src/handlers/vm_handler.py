from __future__ import annotations

from handlers.base_handler import ResourceHandler


class VirtualMachineHandler(ResourceHandler):
    SUPPORTED_TYPES = {
        "microsoft.compute/virtualmachines",
    }

    def __init__(self, credential=None, compute_client_factory=None) -> None:
        self.credential = credential
        self.compute_client_factory = compute_client_factory
        self._clients: dict[str, object] = {}

    def _client(self, subscription_id: str):
        if subscription_id in self._clients:
            return self._clients[subscription_id]

        if self.compute_client_factory:
            client = self.compute_client_factory(subscription_id)
        else:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.compute import ComputeManagementClient

            credential = self.credential or DefaultAzureCredential()
            client = ComputeManagementClient(credential, subscription_id)

        self._clients[subscription_id] = client
        return client

    def get_state(self, resource) -> str:
        client = self._client(resource.subscription_id)
        vm = client.virtual_machines.instance_view(resource.resource_group, resource.name)
        statuses = getattr(vm, "statuses", []) or []

        power_status = ""
        for status in statuses:
            code = (getattr(status, "code", "") or "").lower()
            if code.startswith("powerstate/"):
                power_status = code
                break

        if power_status in {"powerstate/running", "powerstate/starting"}:
            return "running"

        if power_status in {
            "powerstate/deallocated",
            "powerstate/deallocating",
            "powerstate/stopped",
            "powerstate/stopping",
        }:
            return "stopped"

        return "unknown"

    def start(self, resource) -> None:
        client = self._client(resource.subscription_id)
        poller = client.virtual_machines.begin_start(resource.resource_group, resource.name)
        poller.result()

    def stop(self, resource) -> None:
        client = self._client(resource.subscription_id)
        poller = client.virtual_machines.begin_deallocate(resource.resource_group, resource.name)
        poller.result()
