# Azure OffHours Scheduler

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)

Versão em português: [README.md](README.md)

**Automatically turn off non-production Azure resources outside business hours in a centralized, auditable, and safe way.**

Azure OffHours Scheduler is a production-ready open source automation project built to reduce Azure cost through table-driven schedules, controlled scope, and safe execution.

## Why This Project?

- Reduces compute cost without requiring a different automation per team
- Lets operators update schedules after deployment
- Supports enterprise environments with multiple subscriptions and centralized governance
- Respects manual intervention through retain rules
- Keeps the solution lean, predictable, and easy to operate

## The Problem

Most off-hours solutions fail in the same places:

- schedules are hardcoded in files or app settings
- changing business windows requires code changes or redeploy
- scope control across subscriptions becomes fragile manual work
- manual overrides are reverted too aggressively
- logs show that something ran, but not clearly what happened

## The Solution

Azure OffHours Scheduler centralizes scheduler behavior without mixing business rules with technical runtime configuration:

- runtime stays in Function app settings and Bicep
- schedules and global behavior live in Azure Table Storage
- resources opt in through tags such as `schedule=business-hours`
- scope can be controlled by subscription, management group, and exclusions
- every execution produces a structured report with per-resource outcomes

## Simplified Architecture

```text
Timer Trigger
  ↓
Config + Schedules in Table Storage
  ↓
Discovery via Azure Resource Graph
  ↓
Rule and scope evaluation
  ↓
Action: START | STOP | SKIP
  ↓
State persistence
  ↓
Structured execution report
```

Core tables:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

## Quick Start

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
az login
```

Use `infra/bicep/main.parameters.json` as the main deployment file.
If you need to inspect more advanced template options, see `infra/bicep/main.parameters.example.json`.
If `resourceGroupName` is left empty, the deployment wrapper automatically generates `rg-<namePrefix>-<suffix>`.

Deploy:

```bash
make deploy
```

Or:

```bash
./scripts/deploy_scheduler.sh
```

Minimum parameters:

- `location`
- `namePrefix`
- `subscriptionIds` or `managementGroupIds`

Useful optional parameter:

- `resourceGroupName`
  If set, it forces a stable resource group name. If left empty, the deployment generates one automatically from `namePrefix`.

Required for CLI-based operations:

- `tableOperatorsGroupObjectId`

Without this group, the Function can still run, but human operators will not be able to apply `config` and `schedule` changes through `./offhours` using Microsoft Entra ID.

Recommended models:

- use an existing Microsoft Entra group that already contains the operators
- create a dedicated group such as `azure-offhours-operators`, add the users, and pass its `objectId` in the deployment

The recommended flow already publishes the Function, syncs triggers, registers `OffHoursTimer` in Azure, and writes `.offhours.env` for the local CLI.

Recommended initial seed through the CLI:

```bash
az logout
az login
./offhours config apply --file runtime.yaml --execute
./offhours schedule apply --file business-hours.yaml --execute
```

- `az logout` / `az login`
  If the deployment just created table RBAC for the operator group, you may need to refresh local Azure CLI credentials before the first `apply`.
- `config apply --file runtime.yaml --execute`
  Creates or updates the global scheduler configuration in `OffHoursSchedulerConfig`, including behavior such as `DRY_RUN`, default timezone, schedule tag key, and retain rules.
- `schedule apply --file business-hours.yaml --execute`
  Creates or updates the `business-hours` schedule in `OffHoursSchedulerSchedules`, with the operating window that will be referenced by resource tags.

## Operational CLI

Daily operation is done through the repository-local CLI:

```bash
./offhours --help
```

The CLI uses `DefaultAzureCredential` by default, so operator access to the scheduler tables normally comes from the group configured in `tableOperatorsGroupObjectId`.

Typical commands:

```bash
./offhours config get
./offhours config apply --file runtime.yaml
./offhours schedule list
./offhours schedule get business-hours
./offhours schedule apply --file business-hours.yaml
./offhours schedule delete business-hours
./offhours state list
./offhours function trigger
```

Recommended post-deploy validation:

```bash
./offhours state list
./offhours function trigger
./offhours state list
```

## Example Usage

Tag a VM:

```text
schedule=business-hours
```

Simple schedule example:

```yaml
RowKey: business-hours
Start: "08:00"
Stop: "18:00"
SkipDays:
  - saturday
  - sunday
Enabled: true
Version: "1"
```

Preferred format for richer schedule windows:

```yaml
RowKey: office-hours-split
Periods:
  - start: "08:00"
    stop: "12:00"
  - start: "13:00"
    stop: "18:00"
Enabled: true
Version: "1"
```

## Use Cases

- Development and sandbox environments with predictable schedules
- Enterprise environments with multiple subscriptions and centralized governance
- FinOps initiatives focused on reducing idle compute cost

## Features

- Table-driven schedules and global configuration
- Multi-subscription support with optional management group scope
- Include/exclude rules with explicit exclude precedence
- Retain behavior for manual operator overrides
- Regional filtering with `targetResourceLocations`
- Technical timer configuration via `TIMER_SCHEDULE`
- Clean deployment flow with Bicep

## Observability

The solution already provides execution-level operational visibility without requiring extra tooling to get started:

- Correlation ID per run through `run_id`
- Total cycle timing and per-resource `duration_sec`
- Final report emitted as a single JSON line on every cycle
- Structured per-resource outcome with action, result, and reason
- Recommended production default is `RESOURCE_RESULT_LOG_MODE=executed-and-errors`
- Verbose Azure SDK request/response logs are disabled by default

Example report shape:

```json
{
  "run_id": "...",
  "timestamp": "...",
  "dry_run": true,
  "summary": {
    "total": 2,
    "started": 1,
    "stopped": 0,
    "skipped": 1
  },
  "duration_sec": 1.234,
  "resources": []
}
```

## Design Goals

- Allow operational changes without redeploy
- Automate safely before automating aggressively
- Separate technical runtime configuration from scheduler rules
- Keep scope explicit, auditable, and governable
- Deliver useful observability without extra infrastructure

## Documentation

- Documentation index: [docs/README.md](docs/README.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Operator guide: [docs/operator-guide.md](docs/operator-guide.md)
- Examples: [docs/examples.md](docs/examples.md)
- Developer guide: [docs/developer-guide.md](docs/developer-guide.md)
- Code components: [docs/code-components.md](docs/code-components.md)
- Repository map: [docs/repository-map.md](docs/repository-map.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- Release policy: [docs/release-policy.md](docs/release-policy.md)

## Supported Resources

Today:

- `Microsoft.Compute/virtualMachines`

Roadmap:

- `VirtualMachineScaleSets`
- `App Services`
- other resource types suitable for off-hours automation

## Design Principles

- Operational data belongs in tables, not in code
- Technical runtime configuration stays separate from business rules
- Operational defaults should be explicit
- Scope should be explicit and auditable
- The solution should remain simple to operate
- Observability should improve without adding unnecessary complexity

## Contributing

- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Security policy: [SECURITY.md](SECURITY.md)
- License: [LICENSE](LICENSE)
- CI validates lint, SAST, dependency audit, tests, shell scripts, and Bicep compilation

Current version:

- `1.0.0`
