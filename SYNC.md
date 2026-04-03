# Sync Guide

This document explains the relationship between the scripts in this GitHub Action and their origin in the `arkhe-claude-plugins` repository.

## Origin

The checker scripts originated in the **doc-freshness** skill of the `doc` plugin:

```
arkhe-claude-plugins/plugins/doc/skills/doc-freshness/scripts/
```

They were extracted into this standalone GitHub Action to make documentation health checks available to any repository, not just projects that use the Arkhe plugin system.

## File Mapping

### Verbatim copies (identical to source)

These files are unchanged from the plugin. Copy them directly during sync.

| Action file | Source file |
|-------------|------------|
| `scripts/shared.py` | `plugins/doc/skills/doc-freshness/scripts/shared.py` |
| `scripts/link_checker.py` | `plugins/doc/skills/doc-freshness/scripts/link_checker.py` |
| `scripts/version_checker.py` | `plugins/doc/skills/doc-freshness/scripts/version_checker.py` |

### Generalized from source

These files exist in the plugin but were modified for the action to remove project-specific assumptions.

| Action file | Source file | Changes |
|-------------|------------|---------|
| `scripts/claude_md_checker.py` | `plugins/doc/skills/doc-freshness/scripts/claude_md_checker.py` | Empty `_NAME_OVERRIDES` dict (source has arkhe-specific mappings like `"design intent": "design-intent"`). Added `--name-overrides` CLI arg so any project can supply its own. Plugin-specific checks are gated behind `(project_root / "plugins").is_dir()` so the checker works on projects without a `plugins/` directory. |
| `scripts/frontmatter_onboard.py` | `plugins/doc/skills/doc-freshness/scripts/frontmatter_onboard.py` | Renamed `CANDIDATE_PATTERNS` to `DEFAULT_CANDIDATE_PATTERNS` with generic defaults (`README.md`, `CONTRIBUTING.md`, `docs/**/*.md`) instead of the arkhe-specific whitelist. Added `patterns` parameter to `_find_candidates()`, `suggest_onboarding()`, and `apply_onboarding()` so patterns are configurable at runtime. Added `--patterns` CLI arg. |

### New files (no source equivalent)

These files were written specifically for the GitHub Action.

| Action file | Purpose |
|-------------|---------|
| `scripts/orchestrate.py` | Unified CI entry point. Dispatches to individual checker modules, normalizes their outputs into a single JSON schema with severity levels, and writes the report. Replaces the role of `scan_freshness.py` from the plugin (which is not copied). |
| `scripts/format_comment.py` | Reads the JSON report from `orchestrate.py` and produces markdown suitable for a GitHub PR comment. Handles severity grouping, table rendering, and truncation. |
| `scripts/cross_doc_checker.py` | Heuristic cross-document consistency checker. Detects version conflicts between documents that cover overlapping topics. Entirely new -- the plugin does not have this check. |
| `action.yml` | GitHub Action composite definition (inputs, outputs, steps). |

### Verbatim copies (additional)

| Action file | Source file | Notes |
|-------------|------------|-------|
| `scripts/scan_freshness.py` | `plugins/doc/skills/doc-freshness/scripts/scan_freshness.py` | Used as a library by `orchestrate.py` for `compute_staleness()` and `load_config()`. Not called directly as the main orchestrator. |

## How to Sync

Syncing is manual. There is no automated script.

1. **Verbatim files**: Copy `shared.py`, `link_checker.py`, and `version_checker.py` directly from the plugin source. No review needed unless the plugin has added new functions that the action's generalized files also need.

   ```bash
   SRC=plugins/doc/skills/doc-freshness/scripts
   DST=../docs-health-action/scripts

   cp $SRC/shared.py $DST/
   cp $SRC/link_checker.py $DST/
   cp $SRC/version_checker.py $DST/
   cp $SRC/scan_freshness.py $DST/
   ```

2. **Generalized files**: Diff the plugin source against the action version. Apply new logic (bug fixes, new checks) while preserving the generalizations listed above.

   ```bash
   diff $SRC/claude_md_checker.py $DST/claude_md_checker.py
   diff $SRC/frontmatter_onboard.py $DST/frontmatter_onboard.py
   ```

   Key things to preserve during merge:
   - `claude_md_checker.py`: Empty `_NAME_OVERRIDES`, `--name-overrides` CLI arg, `has_plugins` guard
   - `frontmatter_onboard.py`: `DEFAULT_CANDIDATE_PATTERNS` (generic), `patterns` parameter on public functions, `--patterns` CLI arg

3. **New files**: `orchestrate.py`, `format_comment.py`, and `cross_doc_checker.py` have no upstream source. Changes to these files are action-only.

4. **Test after sync**: Run the action's test suite to verify nothing broke.

   ```bash
   cd docs-health-action
   python3 -m pytest tests/ -v
   ```
