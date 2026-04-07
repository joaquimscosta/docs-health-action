# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.3] - 2026-04-07

### Added
- Inline annotations in PR diff via GitHub workflow commands (`::error`, `::warning`, `::notice`)
- New `scripts/format_annotations.py` formatter

### Changed
- Default for `comment-on-pr` changed from `true` to `false` -- annotations are now the default output
- Moved severity normalization functions to `shared.py` for reuse across formatters

## [1.0.2] - 2026-04-05

### Fixed
- `data:` URIs no longer flagged as broken links ([#1](https://github.com/joaquimscosta/docs-health-action/issues/1))
- Backtick-quoted code paths (e.g., `` `src/lib/cn.ts` ``) no longer produce false positives by default ([#2](https://github.com/joaquimscosta/docs-health-action/issues/2))

### Added
- `check-backtick-paths` action input to opt into backtick path validation (default: `false`)
- `--check-backtick-paths` CLI flag for `orchestrate.py`
- Path heuristics to filter git branches, IAM roles, and owner/repo patterns from backtick path checks ([#3](https://github.com/joaquimscosta/docs-health-action/issues/3))

## [1.0.1] - 2026-04-03

### Fixed
- Add `scan_freshness.py` for staleness check support — without it the staleness check silently skipped (c1aa8ae)
- Frontmatter findings now use the correct `path` key from `frontmatter_onboard` output (9207f4d)
- Pass `project_root` to `load_config` to fix TypeError on path concatenation (00e54a9)

### Changed
- Replace 6 lazy-import wrappers in `orchestrate.py` with single `_lazy_import()` helper
- Simplify `_load_config` to use `shared.read_yaml_section` directly, removing circular dependency on `scan_freshness`
- Use `shared.git_last_modified` in `frontmatter_onboard` and `version_checker` instead of inline subprocess calls
- Use `shared._is_fence_line` for consistent fence detection in `version_checker` and `cross_doc_checker`
- Eliminate double file reads in `check_all_links` and `check_all_versions`
- Compute same-file heading slugs once in `check_links` instead of per anchor link

## [1.0.0] - 2026-04-03

### Added
- Initial docs-health-action implementation with 6 checks: links, versions, staleness, claude-md, cross-doc, frontmatter
- Unified CI entry point (`orchestrate.py`) with normalized JSON output
- Broken link and file reference detection (`link_checker.py`)
- Version staleness detection against ground truth sources (`version_checker.py`)
- Git-based documentation staleness analysis (`scan_freshness.py`)
- CLAUDE.md structural drift checker (`claude_md_checker.py`)
- Cross-document consistency checker for version conflicts (`cross_doc_checker.py`)
- Frontmatter onboarding tool (`frontmatter_onboard.py`)
- Shared utilities for markdown parsing, git operations, and file handling (`shared.py`)
- GitHub Action composite definition (`action.yml`)
- Sync documentation (`SYNC.md`) mapping action scripts to plugin source

[Unreleased]: https://github.com/joaquimscosta/docs-health-action/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/joaquimscosta/docs-health-action/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/joaquimscosta/docs-health-action/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/joaquimscosta/docs-health-action/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/joaquimscosta/docs-health-action/releases/tag/v1.0.0
