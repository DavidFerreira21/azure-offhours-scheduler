from reporting.report_builder import build_execution_report
from scheduler.service import ResourceExecutionResult, SchedulerRunResult, SchedulerSummary


def test_build_execution_report_returns_expected_structure() -> None:
    run_result = SchedulerRunResult(
        run_id="run-123",
        timestamp="2026-03-19T12:00:00Z",
        dry_run=True,
        summary=SchedulerSummary(total=1, started=1, stopped=0, skipped=0),
        duration_sec=1.234,
        resources=(
            ResourceExecutionResult(
                resource_id="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                name="vm-a",
                type="microsoft.compute/virtualmachines",
                action="START",
                result="DRY_RUN",
                reason="dry run enabled",
                duration_sec=0.456,
                started=1,
            ),
        ),
    )

    report = build_execution_report(run_result)

    assert report == {
        "run_id": "run-123",
        "timestamp": "2026-03-19T12:00:00Z",
        "dry_run": True,
        "summary": {"total": 1, "started": 1, "stopped": 0, "skipped": 0},
        "duration_sec": 1.234,
        "resources": [
            {
                "resource_id": (
                    "/subscriptions/sub-1/resourceGroups/rg/providers/"
                    "Microsoft.Compute/virtualMachines/vm-a"
                ),
                "name": "vm-a",
                "type": "microsoft.compute/virtualmachines",
                "action": "START",
                "result": "DRY_RUN",
                "reason": "dry run enabled",
                "duration_sec": 0.456,
            }
        ],
    }
