from discovery.resource_graph import ResourceGraphDiscovery


def test_build_query_uses_configurable_schedule_tag_key() -> None:
    discovery = ResourceGraphDiscovery(subscription_ids=["sub-1"], schedule_tag_key="offhours")

    query = discovery._build_query()

    assert "tags['offhours']" in query
    assert "tolower(type) == 'microsoft.compute/virtualmachines'" in query
