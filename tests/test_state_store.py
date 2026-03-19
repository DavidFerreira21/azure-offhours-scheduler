from dataclasses import dataclass

from persistence.state_store import AzureTableStateStore


@dataclass(frozen=True)
class FakeResource:
    id: str
    subscription_id: str
    resource_group: str
    type: str
    name: str


def test_state_store_row_key_is_stable_for_resource_id_casing_and_trailing_slash() -> None:
    lower_resource = FakeResource(
        id="/subscriptions/sub-1/resourcegroups/rg-1/providers/microsoft.compute/virtualmachines/vm-a",
        subscription_id="sub-1",
        resource_group="rg-1",
        type="microsoft.compute/virtualmachines",
        name="vm-a",
    )
    mixed_case_resource = FakeResource(
        id="/subscriptions/SUB-1/resourceGroups/RG-1/providers/Microsoft.Compute/virtualMachines/vm-a/",
        subscription_id="sub-1",
        resource_group="rg-1",
        type="microsoft.compute/virtualmachines",
        name="vm-a",
    )

    assert AzureTableStateStore._row_key(lower_resource) == AzureTableStateStore._row_key(mixed_case_resource)

