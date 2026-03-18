# Changelog

All notable changes to this project should be documented in this file.

The format is inspired by Keep a Changelog.

## [Unreleased]

### Added

- Repository restructured into `function/` and `src/`
- Table-driven operational configuration with Azure Table Storage
- Management group based technical scope with subscription exclusion support
- Optional regional filtering with `targetResourceLocations`
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

### Fixed

- README license reference aligned with Apache License 2.0
