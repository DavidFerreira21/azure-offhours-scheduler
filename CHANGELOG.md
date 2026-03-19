# Changelog

All notable changes to this project should be documented in this file.

The format is inspired by Keep a Changelog.

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
