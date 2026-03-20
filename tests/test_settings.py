import pytest

from config.settings import Settings


@pytest.fixture(autouse=True)
def clear_scheduler_env(monkeypatch):
    for env_name in (
        "AZURE_SUBSCRIPTION_IDS",
        "TARGET_RESOURCE_LOCATIONS",
        "SCHEDULER_STORAGE_CONNECTION_STRING",
        "STATE_STORAGE_CONNECTION_STRING",
        "AzureWebJobsStorage",
        "CONFIG_STORAGE_TABLE_NAME",
        "SCHEDULE_STORAGE_TABLE_NAME",
        "STATE_STORAGE_TABLE_NAME",
        "MAX_WORKERS",
        "ENABLE_VERBOSE_AZURE_SDK_LOGS",
        "RESOURCE_RESULT_LOG_MODE",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_settings_reads_target_resource_locations_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_IDS", "sub-1,sub-2")
    monkeypatch.setenv("TARGET_RESOURCE_LOCATIONS", "EastUS, BrazilSouth ")
    monkeypatch.setenv("AzureWebJobsStorage", "UseDevelopmentStorage=true")

    result = Settings.from_env()

    assert result.subscription_ids == ["sub-1", "sub-2"]
    assert result.target_resource_locations == ("eastus", "brazilsouth")


def test_settings_keeps_all_regions_when_target_locations_is_blank(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_IDS", "sub-1")
    monkeypatch.setenv("TARGET_RESOURCE_LOCATIONS", "")
    monkeypatch.setenv("AzureWebJobsStorage", "UseDevelopmentStorage=true")

    result = Settings.from_env()

    assert result.target_resource_locations == ()


def test_settings_disable_verbose_azure_sdk_logs_by_default(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_IDS", "sub-1")
    monkeypatch.setenv("AzureWebJobsStorage", "UseDevelopmentStorage=true")

    result = Settings.from_env()

    assert result.enable_verbose_azure_sdk_logs is False


def test_settings_reads_verbose_azure_sdk_logs_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_IDS", "sub-1")
    monkeypatch.setenv("AzureWebJobsStorage", "UseDevelopmentStorage=true")
    monkeypatch.setenv("ENABLE_VERBOSE_AZURE_SDK_LOGS", "true")

    result = Settings.from_env()

    assert result.enable_verbose_azure_sdk_logs is True


def test_settings_resource_result_log_mode_defaults_to_executed_and_errors(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_IDS", "sub-1")
    monkeypatch.setenv("AzureWebJobsStorage", "UseDevelopmentStorage=true")

    result = Settings.from_env()

    assert result.resource_result_log_mode == "executed-and-errors"


def test_settings_reads_resource_result_log_mode_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SUBSCRIPTION_IDS", "sub-1")
    monkeypatch.setenv("AzureWebJobsStorage", "UseDevelopmentStorage=true")
    monkeypatch.setenv("RESOURCE_RESULT_LOG_MODE", "all")

    result = Settings.from_env()

    assert result.resource_result_log_mode == "all"
