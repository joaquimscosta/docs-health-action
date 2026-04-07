# docs-health-action

> Detect broken links, version drift, staleness, and cross-document inconsistencies in any markdown project.

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-docs--health--action-blue?logo=github)](https://github.com/marketplace/actions/documentation-health-check)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

**docs-health-action** is a GitHub Action that scans your repository's markdown documentation and reports:

- **Broken links** -- internal links, anchor references, and backtick-quoted file paths that point to missing targets
- **Version drift** -- version numbers cited in docs that no longer match ground truth (`package.json`, `.nvmrc`, `pyproject.toml`, `go.mod`, `build.gradle`, `pom.xml`, etc.)
- **Staleness** -- documents whose git history suggests they have not been updated in a long time
- **CLAUDE.md drift** -- structural claims in `CLAUDE.md` (plugin counts, component inventories, file paths) that have fallen out of sync with the filesystem
- **Cross-doc inconsistencies** -- different documents citing conflicting version numbers for the same tool or language
- **Missing frontmatter** -- markdown files that would benefit from tracking metadata (`title`, `last_updated`)

Results appear as **inline annotations** in the PR diff, uploaded as a JSON artifact, and exposed as action outputs for downstream steps. Optionally, a PR comment summary can be enabled. Works on any repository with markdown files -- no special project structure or dependencies required.

## Why Automated Doc Health?

Documentation drifts silently. Links break after refactors, version numbers go stale after upgrades, files get abandoned as the codebase evolves. By the time someone notices, readers have already hit dead ends.

Manual audits do not scale. This action catches those issues automatically on every pull request -- before they reach your users.

## Quick Start

```yaml
# .github/workflows/docs-health.yml
name: Documentation Health
on:
  pull_request:
    paths: ['**/*.md']

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: joaquimscosta/docs-health-action@v1
```

That is all you need. The action will run the default checks (links, versions, staleness), annotate findings inline in the PR diff, and fail the workflow if any errors are detected.

> **Note:** To also post a summary PR comment, add `comment-on-pr: 'true'` and the `pull-requests: write` permission.

## Configuration

### Action Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `checks` | Comma-separated list of checks to run. Available: `links`, `versions`, `staleness`, `claude-md`, `cross-doc`, `frontmatter`, `all`. | `links,versions,staleness` |
| `fail-on` | When to fail the action. `errors`: fail on broken links and critical mismatches. `warnings`: also fail on staleness and minor mismatches. `none`: never fail (advisory only). | `errors` |
| `comment-on-pr` | Whether to post a summary comment on the PR. Only applies when triggered by `pull_request` event. Findings always appear as inline annotations regardless of this setting. | `false` |
| `comment-threshold` | Minimum severity to include in annotations and PR comment. Options: `error`, `warning`, `info`. | `warning` |
| `doc-patterns` | Comma-separated glob patterns for discovering docs. | `README.md,CLAUDE.md,CONTRIBUTING.md,CHANGELOG.md,INSTALL.md,INSTALLATION.md,SETUP.md,LICENSE.md,docs/**/*.md,wiki/**/*.md,plan/**/*.md,.github/**/*.md` |
| `exclude-patterns` | Comma-separated glob patterns to exclude from scanning. | `node_modules/**,.git/**,vendor/**,.venv/**,venv/**,dist/**,build/**,target/**,coverage/**` |
| `config-file` | Path to a config file (e.g., `.arkhe.yaml`) with a `doc-freshness` section. Overrides `doc-patterns` and `exclude-patterns` when present. | _(none)_ |
| `artifact-name` | Name for the uploaded JSON results artifact. | `docs-health-results` |

### Config File (`.arkhe.yaml`)

You can centralize configuration in a `.arkhe.yaml` file at your project root:

```yaml
doc-freshness:
  doc-patterns:
    - "README.md"
    - "CLAUDE.md"
    - "docs/**/*.md"
    - "wiki/**/*.md"
  exclude-patterns:
    - "node_modules/**"
    - "vendor/**"
    - ".git/**"
```

Then reference it in your workflow:

```yaml
- uses: joaquimscosta/docs-health-action@v1
  with:
    config-file: .arkhe.yaml
```

When a config file is specified and found, its `doc-patterns` and `exclude-patterns` values override the input defaults.

### Using Workflow Inputs

For simpler cases, pass patterns directly:

```yaml
- uses: joaquimscosta/docs-health-action@v1
  with:
    doc-patterns: 'README.md,docs/**/*.md,wiki/**/*.md'
    exclude-patterns: 'docs/archive/**'
```

## Outputs

| Output | Description |
|--------|-------------|
| `result-json` | Path to the JSON results file (also uploaded as an artifact). |
| `total-issues` | Total number of issues found (errors + warnings + info). |
| `errors` | Number of error-level issues. |
| `warnings` | Number of warning-level issues. |

## Checks Reference

### `links` -- Broken Link Detection

Parses every discovered markdown file for internal links (`[text](target)`), anchor references (`[text](#heading)`), image sources (`<img src="...">`), and backtick-quoted file paths (`` `src/foo.ts` ``). Verifies that each target exists on disk. Anchor references are validated against the heading slugs in the target file.

- **Error**: Target file does not exist, or anchor not found in target file.
- **Warning**: Backtick-quoted file path does not exist (may be illustrative).

### `versions` -- Version Drift Detection

Extracts version references from prose (e.g., "Node.js 18", "Python 3.11", "Java 21") and compares them against ground truth files in the repository: `package.json`, `.nvmrc`, `.python-version`, `pyproject.toml`, `go.mod`, `.tool-versions`, `build.gradle.kts`, `pom.xml`, and others.

- **Error**: Major version mismatch (e.g., doc says Node 18, project uses Node 20).
- **Warning**: Minor or patch version mismatch.

Also checks `last_updated` frontmatter dates against git history and flags docs where the dates diverge by more than 7 days.

### `staleness` -- Document Freshness Analysis

Uses git history to compute a drift score for each document. Documents that have not been updated for a long time relative to the rest of the project are flagged.

- **Warning**: Document is `stale` or `very_stale`.
- **Info**: Document is `aging`.

### `claude-md` -- CLAUDE.md Drift

Parses structural claims in `CLAUDE.md` -- plugin counts, component inventories (agents, commands, skills), version strings, and file path references -- and compares them against the filesystem.

If the project has a `plugins/` directory, plugin-specific checks run automatically. File path checks always run regardless of project structure.

- **Error**: Component documented in CLAUDE.md but not found on disk (phantom), or component on disk but not documented (undocumented).
- **Warning**: Plugin count mismatch, version mismatch, or referenced file path missing.

### `cross-doc` -- Cross-Document Consistency

Compares documents that cover overlapping topics (detected via heading analysis) and flags cases where they cite conflicting version numbers for the same tool or language.

- **Warning**: Two documents disagree on a version number (e.g., README says Python 3.11, CONTRIBUTING says Python 3.9).

### `frontmatter` -- Missing Frontmatter

Scans markdown files for YAML frontmatter. Files without frontmatter are flagged as candidates for onboarding with suggested `title` and `last_updated` fields derived from git history.

- **Info**: File has no frontmatter and would benefit from metadata.

## Examples

### Basic -- default checks

Runs link checking, version drift detection, and staleness analysis. Fails the workflow on errors. Findings appear as inline annotations in the PR diff.

```yaml
name: Documentation Health
on:
  pull_request:
    paths: ['**/*.md']

permissions:
  contents: read

jobs:
  docs-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for staleness analysis
      - uses: joaquimscosta/docs-health-action@v1
```

### Full suite -- all checks

Enables every check, including CLAUDE.md drift, cross-doc consistency, and frontmatter suggestions.

```yaml
name: Documentation Health (Full)
on:
  pull_request:
    paths: ['**/*.md', 'CLAUDE.md']

permissions:
  contents: read
  pull-requests: write

jobs:
  docs-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: joaquimscosta/docs-health-action@v1
        with:
          checks: all
          fail-on: warnings
          comment-threshold: info
```

### Advisory mode -- never fail

Runs all checks but never fails the workflow. Useful for initial adoption or monitoring.

```yaml
name: Documentation Health (Advisory)
on:
  pull_request:
    paths: ['**/*.md']
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9am

permissions:
  contents: read
  pull-requests: write

jobs:
  docs-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: joaquimscosta/docs-health-action@v1
        with:
          checks: all
          fail-on: none
          comment-on-pr: true
          comment-threshold: info
      - name: Use outputs in downstream steps
        run: |
          echo "Total issues: ${{ steps.docs-health.outputs.total-issues }}"
          echo "Errors: ${{ steps.docs-health.outputs.errors }}"
```

## Output Formats

### Inline Annotations (default)

When issues are found, the action emits GitHub workflow commands (`::error`, `::warning`, `::notice`) that appear as inline annotations in the **Files Changed** tab of a pull request, right on the affected line.

GitHub shows up to 10 annotations in the Actions summary panel, but **all** annotations are visible inline in the PR diff.

### PR Comment (opt-in)

Set `comment-on-pr: 'true'` to also post a summary comment on the PR (requires `pull-requests: write` permission). The comment includes tables grouped by severity:

```
## Documentation Health Report

**5 issues found** (1 error, 3 warnings, 1 info)

### Errors (1)

| File | Line | Check | Finding |
|------|------|-------|---------|
| `docs/setup.md` | 42 | broken-link | Target file does not exist: `../old-guide.md` |

### Warnings (3)

| File | Line | Check | Finding |
|------|------|-------|---------|
| `README.md` | 15 | version-drift | node: doc says 18, project uses 20 |
| `CONTRIBUTING.md` | 8 | version-drift | python: doc says 3.9, project uses 3.12 |
| `docs/api.md` | - | stale-date | Frontmatter says 2025-01-10, git says 2026-03-28 (443 days apart) |

---
Generated by docs-health-action | Checks: broken-link, version-drift, stale-date
```

The comment is idempotent -- on re-push, the existing comment is updated rather than creating a new one.

## Pairing with Claude Code

This action is part of a broader documentation health toolkit. The same detection algorithms also power the **doc-freshness** skill in the [Arkhe Claude Plugins](https://github.com/joaquimscosta/arkhe-claude-plugins) collection for [Claude Code](https://docs.claude.com/en/docs/overview).

| | GitHub Action (this repo) | Claude Code Skill |
|---|---|---|
| **When** | CI/CD -- every PR, scheduled runs | Interactive -- during development sessions |
| **Checks** | links, versions, staleness, claude-md, cross-doc, frontmatter | Same checks + AI-assisted code-doc drift analysis |
| **Output** | JSON artifact, PR comment, workflow pass/fail | Conversational findings, actionable suggestions |
| **Best for** | Enforcement, regression prevention | Exploration, triage, on-demand audits |

Use the action to enforce baseline doc health in CI. Use the skill during development to investigate drift before committing, triage findings interactively, and get AI-assisted suggestions for what needs updating. Together they form a **detect-in-dev, enforce-in-CI** loop.

The action is fully standalone -- it does not require Claude Code or the plugin system. Learn more about the doc-freshness skill in the [Arkhe Claude Plugins repository](https://github.com/joaquimscosta/arkhe-claude-plugins).

## Requirements

- **Python 3.8+** (set up automatically by the action via `actions/setup-python@v5`)
- **Git** (for staleness analysis and frontmatter date detection; available by default on GitHub-hosted runners)
- No external Python packages -- all scripts use the standard library only

## License

[MIT](LICENSE)
