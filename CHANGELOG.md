# Changelog

All notable changes to this project should be documented in this file.

The format is inspired by Keep a Changelog.

## [1.1.0] - 2026-03-27

### Added

- Repository-local operational CLI through `./offhours` and `python -m offhours_cli`
- CLI commands for:
  - `config get|apply`
  - `schedule list|get|apply|delete`
  - `state list|get|delete`
  - `function trigger`
- Shared table-entity normalization in `src/persistence/table_entities.py` to keep CLI and runtime aligned
- Local example files for day-2 operations:
  - `runtime.yaml`
  - `business-hours.yaml`
- Deterministic Function App zip packaging through `scripts/build_function_app_package.sh`
- Post-deploy `.offhours.env` generation for automatic CLI context loading

### Changed

- Deploy wrapper now defaults to `infra/bicep/main.parameters.json`
- Deploy wrapper can auto-generate `resourceGroupName` as `rg-<namePrefix>-<suffix>` when the parameter is left empty
- Deploy wrapper now:
  - validates subscription-scope deployment by default
  - prints clearer progress messages for long Azure steps
  - writes operational next steps at the end of the run
- Function publish flow moved to explicit zip deploy with remote build, trigger sync, and function registration checks
- Documentation now treats `tableOperatorsGroupObjectId` as a practical requirement for human CLI operators using Microsoft Entra ID
- Main and example parameter files were reorganized:
  - `main.parameters.json` for the common path
  - `main.parameters.example.json` for broader template options
- READMEs and detailed docs were aligned to the CLI-first operational model, YAML examples, post-deploy seed steps, and Azure RBAC refresh guidance

### Removed

- Automatic bootstrap of default config and schedule during deploy
- `scripts/bootstrap_scheduler_tables.sh`
- Legacy CLI aliases `show` and `set`

### Fixed

- Function publish reliability by replacing the previous publish path with explicit bundle preparation and zip deployment
- Trigger synchronization resilience with retries during Function publish
- Storage table operator guidance and deploy outputs so post-deploy CLI usage is clearer
- Resource naming collisions during repeated deploy/delete cycles by allowing automatic resource group suffix generation

## [1.0.0] - 2026-03-19

### Added

- Repository restructured into `function/` and `src/`
- Table-driven operational configuration with Azure Table Storage
- Management group based technical scope with subscription exclusion support
- Optional regional filtering with `targetResourceLocations`
- Technical timer configuration via `TIMER_SCHEDULE` with 15-minute default
- Stable state row key normalization for resource IDs
- Temporary `retain_running` behavior after crossing the next valid window
- Sticky `retain_stopped` behavior documented explicitly
- Community files:
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `CODE_OF_CONDUCT.md`
  - `LICENSE`
  - GitHub issue templates
  - GitHub pull request template
  - CI workflow
- Documentation set expanded with:
  - architecture
  - developer guide
  - repository map
  - code components
  - examples
  - troubleshooting
  - release policy
  - docs index

### Changed

- README simplified into a more objective project landing page
- Root `requirements.txt` is now the single source of truth for runtime dependencies
- `function/requirements.txt` is generated during publish bundle preparation
- `local.settings.json` is no longer versioned
- `Periods` documented as the preferred schedule format, while `Start/Stop` remains supported
- Timer trigger moved from hardcoded cron to app setting based configuration
- Documentation aligned with the 1.0 baseline and current operational behavior

### Fixed

- README license reference aligned with Apache License 2.0
- Subscription-scope role assignment naming updated to avoid redeploy collisions with recreated managed identities
- Resource Graph discovery fixed to preserve management group support without relying on invalid VM projection fields
- State table duplicate rows reduced by canonicalizing resource IDs before generating row keys
