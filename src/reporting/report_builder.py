from __future__ import annotations


def build_execution_report(run_result) -> dict:
    return {
        "run_id": run_result.run_id,
        "timestamp": run_result.timestamp,
        "dry_run": run_result.dry_run,
        "summary": {
            "total": run_result.summary.total,
            "started": run_result.summary.started,
            "stopped": run_result.summary.stopped,
            "skipped": run_result.summary.skipped,
        },
        "duration_sec": run_result.duration_sec,
        "resources": [
            {
                "resource_id": resource.resource_id,
                "name": resource.name,
                "type": resource.type,
                "action": resource.action,
                "result": resource.result,
                "reason": resource.reason,
                "duration_sec": resource.duration_sec,
            }
            for resource in run_result.resources
        ],
    }
