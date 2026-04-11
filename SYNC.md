# Sync Guide

This document explains the relationship between the scripts in this GitHub Action and their origin in the `arkhe-claude-plugins` repository.

## Origin

The checker scripts originated in the **doc-freshness** skill of the `doc` plugin:

```
arkhe-claude-plugins/plugins/doc/skills/doc-freshness/scripts/
```

They were extracted into this standalone GitHub Action to make documentation health checks available to any repository, not just projects that use the Arkhe plugin system.

## Sync Direction

The scripts originated in the plugin, but the action has since diverged with bug fixes and improvements (CommonMark-compliant fence tracking, minimum-version handling, reference-link regex fixes). **The action is now the source of truth** for shared logic. Sync direction is **action → plugin**.

## File Mapping

### Shared files (action is source of truth)

These files are shared between the action and the plugin. Copy them from the action to the plugin during sync.

| Action file | Plugin file | Divergence notes |
|-------------|------------|------------------|
| `scripts/shared.py` | `.../scripts/shared.py` | Action adds `_update_fence_state()` with CommonMark-compliant fence tracking (replaces naive toggle), fixes reference-link regex for angle brackets, strips inline backtick spans before img-tag matching. |
| `scripts/link_checker.py` | `.../scripts/link_checker.py` | Trivial (one comment line). |
| `scripts/version_checker.py` | `.../scripts/version_checker.py` | Action adds `is_minimum` field for `>=`/`+` notation, uses `_update_fence_state`, adds `try/except` guard on version parsing. |
| `scripts/scan_freshness.py` | `.../scripts/scan_freshness.py` | Currently identical. |

### Generalized from plugin source

These files exist in both repos but have intentional structural differences. The action versions are generalized; the plugin versions have project-specific configuration. Bug fixes and new checks should be manually merged.

| Action file | Plugin file | Differences |
|-------------|------------|-------------|
| `scripts/claude_md_checker.py` | `.../scripts/claude_md_checker.py` | Action: empty `_NAME_OVERRIDES`, `--name-overrides` CLI arg, `has_plugins` guard. Plugin: arkhe-specific `_NAME_OVERRIDES` dict, no guard. |
| `scripts/frontmatter_onboard.py` | `.../scripts/frontmatter_onboard.py` | Action: `DEFAULT_CANDIDATE_PATTERNS` (generic), `patterns` parameter on public functions, `--patterns` CLI arg, single `_count_skipped()` call. Plugin: `CANDIDATE_PATTERNS` with arkhe-specific whitelist, double `_count_skipped()` call (efficiency bug). |

### Action-only files (no plugin equivalent)

| Action file | Purpose |
|-------------|---------|
| `scripts/orchestrate.py` | Unified CI entry point. Dispatches to checker modules, normalizes outputs into a single JSON schema with severity levels, and writes the report. |
| `scripts/format_comment.py` | Reads JSON report and produces markdown for GitHub PR comments. Handles severity grouping, table rendering, and truncation. |
| `scripts/format_annotations.py` | Reads JSON report and emits `::error`/`::warning`/`::notice` GitHub workflow commands for inline diff annotations. |
| `scripts/cross_doc_checker.py` | Heuristic cross-document consistency checker. Detects version conflicts between documents that cover overlapping topics. |
| `action.yml` | GitHub Action composite definition (inputs, outputs, steps). |

## How to Sync

### Using the sync script (recommended)

The plugin repo contains a sync script that automates verbatim copies and shows diffs for files that need manual review:

```bash
cd arkhe-claude-plugins/plugins/doc/skills/doc-freshness/scripts
./sync-from-action.sh /path/to/docs-health-action

# Or skip confirmation prompts:
./sync-from-action.sh /path/to/docs-health-action --yes
```

The script will:
1. **Verbatim-copy** `shared.py`, `link_checker.py`, `version_checker.py`, and `scan_freshness.py` from the action (with confirmation prompts).
2. **Show diffs** for `claude_md_checker.py` and `frontmatter_onboard.py` so you can manually merge new logic while preserving plugin-specific configuration.

### Manual sync

If you prefer to sync manually:

1. **Shared files** — copy from action to plugin:

   ```bash
   ACTION=path/to/docs-health-action/scripts
   PLUGIN=plugins/doc/skills/doc-freshness/scripts

   cp $ACTION/shared.py          $PLUGIN/
   cp $ACTION/link_checker.py    $PLUGIN/
   cp $ACTION/version_checker.py $PLUGIN/
   cp $ACTION/scan_freshness.py  $PLUGIN/
   ```

2. **Generalized files** — diff and manually merge:

   ```bash
   diff $ACTION/claude_md_checker.py   $PLUGIN/claude_md_checker.py
   diff $ACTION/frontmatter_onboard.py $PLUGIN/frontmatter_onboard.py
   ```

   Preserve in the plugin during merge:
   - `claude_md_checker.py`: Arkhe-specific `_NAME_OVERRIDES` values
   - `frontmatter_onboard.py`: Arkhe-specific `CANDIDATE_PATTERNS` whitelist

3. **Action-only files**: `orchestrate.py`, `format_comment.py`, `format_annotations.py`, and `cross_doc_checker.py` have no upstream source. Changes to these files are action-only.

4. **Test after sync**: Run the action's integration tests to verify nothing broke.

   ```bash
   cd docs-health-action
   # Tests are in .github/workflows/test.yml — run orchestrate.py against fixtures:
   python3 scripts/orchestrate.py --checks links --output /tmp/results.json tests/fixtures/broken-links
   ```
