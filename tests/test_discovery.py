from discovery.resource_graph import ResourceGraphDiscovery


def test_build_query_uses_configurable_schedule_tag_key() -> None:
    discovery = ResourceGraphDiscovery(subscription_ids=["sub-1"], schedule_tag_key="offhours")

    query = discovery._build_query()

    assert "tags['offhours']" in query
    assert "tolower(type) == 'microsoft.compute/virtualmachines'" in query
    assert "project id, name, type, location, subscriptionId, resourceGroup" in query
    assert "managementGroupAncestorsChain" not in query


def test_build_subscription_scope_query_projects_management_group_ancestry() -> None:
    query = ResourceGraphDiscovery._build_subscription_scope_query()

    assert "ResourceContainers" in query
    assert "microsoft.resources/subscriptions" in query
    assert "properties.managementGroupAncestorsChain" in query


def test_extracts_management_group_ids_from_resource_graph_row() -> None:
    row = {
        "managementGroupAncestorsChain": [
            {"name": "mg-platform"},
            {"id": "/providers/Microsoft.Management/managementGroups/mg-apps"},
        ]
    }

    result = ResourceGraphDiscovery._extract_management_group_ids(row)

    assert result == ("mg-platform", "/providers/Microsoft.Management/managementGroups/mg-apps")


class FakeResourceGraphClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def resources(self, request):
        self.requests.append(request)

        class Result:
            data = self.responses.pop(0)

        return Result()


def test_filters_resources_by_target_locations_when_configured() -> None:
    client = FakeResourceGraphClient(
        [
            [
                {
                    "subscriptionId": "sub-1",
                    "managementGroupAncestorsChain": [
                        {"name": "mg-platform"},
                        {"name": "mg-apps"},
                    ],
                }
            ],
            [
                {
                    "id": (
                        "/subscriptions/sub-1/resourceGroups/rg-1/providers/"
                        "Microsoft.Compute/virtualMachines/vm-east"
                    ),
                    "name": "vm-east",
                    "type": "microsoft.compute/virtualmachines",
                    "location": "eastus",
                    "subscriptionId": "sub-1",
                    "resourceGroup": "rg-1",
                    "tags": {"schedule": "business-hours"},
                },
                {
                    "id": (
                        "/subscriptions/sub-1/resourceGroups/rg-1/providers/"
                        "Microsoft.Compute/virtualMachines/vm-brazil"
                    ),
                    "name": "vm-brazil",
                    "type": "microsoft.compute/virtualmachines",
                    "location": "brazilsouth",
                    "subscriptionId": "sub-1",
                    "resourceGroup": "rg-1",
                    "tags": {"schedule": "business-hours"},
                },
            ],
        ]
    )

    discovery = ResourceGraphDiscovery(
        subscription_ids=["sub-1"],
        target_resource_locations=("eastus",),
        client=client,
        query_request_factory=lambda **kwargs: kwargs,
    )

    result = discovery.find_scheduled_resources()

    assert len(result) == 1
    assert result[0].name == "vm-east"
    assert result[0].location == "eastus"
    assert result[0].management_group_ids == ("mg-platform", "mg-apps")
