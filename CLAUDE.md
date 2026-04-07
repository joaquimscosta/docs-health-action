# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

GitHub Action that scans markdown documentation for broken links, version drift, staleness, CLAUDE.md drift, cross-document inconsistencies, and missing frontmatter. Pure Python 3.8+ with zero external dependencies (standard library only).

## Commands

```bash
# Run a specific check against a fixture or project directory
python3 scripts/orchestrate.py --checks links --output /tmp/results.json tests/fixtures/broken-links

# Run multiple checks
python3 scripts/orchestrate.py --checks links,versions,staleness --output /tmp/results.json .

# Run with config file (reads doc-patterns/exclude-patterns from .arkhe.yaml)
python3 scripts/orchestrate.py --checks links --config-file .arkhe.yaml --output /tmp/results.json .

# Check backtick-quoted file paths (e.g., `src/foo.ts`) in addition to markdown links
python3 scripts/orchestrate.py --checks links --check-backtick-paths --output /tmp/results.json .

# Format results as PR comment markdown
python3 scripts/format_comment.py /tmp/results.json

# Format results as GitHub workflow annotations
python3 scripts/format_annotations.py /tmp/results.json

# Verify all modules import cleanly (quick smoke test)
cd scripts && python3 -c "
import orchestrate, format_comment, format_annotations
import link_checker, version_checker, scan_freshness
import claude_md_checker, cross_doc_checker, frontmatter_onboard
import shared; print('OK')
"
```

There is no test runner -- tests are integration tests in `.github/workflows/test.yml` that run orchestrate.py against fixture directories and assert on JSON output.

## Architecture

**Data flow:** `action.yml` -> `orchestrate.py` -> checker modules -> JSON -> formatters

`orchestrate.py` is the sole entry point. It discovers markdown files via `shared.discover_markdown_files()`, dispatches to checker modules via the `CHECK_RUNNERS` dict (using `_lazy_import()` so one failing module doesn't block others), normalizes raw findings through `_normalize_*_findings()` functions, and writes unified JSON.

Two formatters consume the JSON independently:
- `format_annotations.py` emits `::error`/`::warning`/`::notice` workflow commands (default output)
- `format_comment.py` produces markdown tables for optional PR comments

**Available checks:** `links`, `versions`, `staleness`, `claude-md`, `cross-doc`, `frontmatter` (or `all`).

**Checker modules** each expose a single public function that takes `(doc_paths, project_root)` and returns raw findings:
- `link_checker.check_all_links` — broken markdown/backtick-path links
- `version_checker.check_all_versions` — version drift across docs
- `scan_freshness.compute_staleness` — stale/aging documents
- `claude_md_checker.check_claude_md` — CLAUDE.md drift from codebase
- `cross_doc_checker.check_cross_doc` — cross-document inconsistencies
- `frontmatter_onboard.check_frontmatter` (via orchestrator) — missing frontmatter

The orchestrator normalizes these into the unified schema with `{id, check, severity, file, line, message, details}`.

**Finding IDs** use prefixed counters: LNK (links), VER (versions), STL (staleness), CMD (claude-md), XDC (cross-doc), FMT (frontmatter).

**Severity levels**: `error` (broken links, major version mismatch), `warning` (staleness, minor mismatch), `info` (aging docs, missing frontmatter). Normalization and threshold logic live in `shared.py`.

## Key Conventions

- **No external dependencies.** All scripts use only the Python standard library. No pip packages, no requirements.txt.
- **Sibling imports** use this pattern at the top of every script:
  ```python
  _SCRIPT_DIR = str(Path(__file__).resolve().parent)
  if _SCRIPT_DIR not in sys.path:
      sys.path.insert(0, _SCRIPT_DIR)
  from shared import ...
  ```
- **YAML parsing** is done with a hand-rolled line parser in `shared.read_yaml_section()` -- no PyYAML.
- **Test fixtures** in `tests/fixtures/` are minimal standalone project directories (simple-project, broken-links, version-drift) with intentional issues for each check type.
- **CHANGELOG** follows Keep a Changelog format. Comparison links at the bottom must be maintained. The release workflow (`release.yml`) handles tagging, GitHub release creation, and floating major version tag (`v1`) updates.
