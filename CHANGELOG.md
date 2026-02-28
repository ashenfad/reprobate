# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Cycle detection**: Added try/finally to discard IDs from seen-set after rendering subtree
- **render_child outside render()**: Raises RuntimeError with clear message
- **_render_primitive**: Fixed budget overflow for budget < 2
- **_render_bytes**: Slices from repr instead of attempting decode
- **render_attrs**: Produces well-formed `<Type...>` instead of truncated output
- **Polars extension**: Fixed truthiness check for series names

### Added
- **Pre-commit config**: Added .pre-commit-config.yaml with ruff lint and format
