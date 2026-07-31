# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Keyword-only `inference` policy with `best_effort`, `exact`, and `off` modes
- Bounded aggregate type and literal-key record-shape inference
- Optional-field schema notation and type-aware container summaries

### Changed
- Replaced the recursive budget allocator with a bounded full-probe and structural refinement engine
- Complete supported values are preserved whenever they fit
- Strings and bytes retain escaped, single-line previews with opportunistic length metadata
- Sets preserve native iteration order instead of imposing a presentation order
- Optional table and array renderers share bounded semantic summaries, including authoritative column types
- Even allocation plans bounded sibling demand and redistributes unused shares

## [0.1.1] - 2026-02-28

### Fixed
- **Cycle detection**: Added try/finally to discard IDs from seen-set after rendering subtree
- **render_child outside render()**: Raises RuntimeError with clear message
- **_render_primitive**: Fixed budget overflow for budget < 2
- **_render_bytes**: Slices from repr instead of attempting decode
- **_render_bytes**: Fixed off-by-one in budget calculation that caused output to exceed budget by 1 character when truncating bytes with escape sequences
- **render_attrs**: Produces well-formed `<Type...>` instead of truncated output
- **Polars extension**: Fixed truthiness check for series names

### Added
- **Pre-commit config**: Added .pre-commit-config.yaml with ruff lint and format
