#!/usr/bin/env python3
"""
Unified CI entry point for the docs-health-action GitHub Action.

Dispatches to individual checker modules, normalizes outputs into a
unified JSON schema, and writes results to a file.

Uses only standard library (no external dependencies). Python 3.8+.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Module path setup — allow sibling imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from shared import DEFAULT_DOC_PATTERNS, DEFAULT_EXCLUDE_PATTERNS, discover_markdown_files, read_yaml_section

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_CHECKS = ["links", "versions", "staleness", "claude-md", "cross-doc", "frontmatter"]

FINDING_PREFIX = {
    "links": "LNK",
    "versions": "VER",
    "staleness": "STL",
    "claude-md": "CMD",
    "cross-doc": "XDC",
    "frontmatter": "FMT",
}

OUTPUT_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Lazy module imports — each wrapped so a missing module doesn't block others
# ---------------------------------------------------------------------------


def _lazy_import(name: str):
    """Lazily import a sibling module by name."""
    return __import__(name)


# ---------------------------------------------------------------------------
# Severity normalizers — transform raw module output into unified findings
# ---------------------------------------------------------------------------


def _normalize_link_findings(
    raw: Dict[str, Any], check_name: str, counter: List[int]
) -> List[Dict[str, Any]]:
    """Normalize link_checker output.

    status "broken" -> error, status "warning" -> warning.
    """
    findings: List[Dict[str, Any]] = []
    prefix = FINDING_PREFIX[check_name]

    for f in raw.get("findings", []):
        status = f.get("status", "")
        if status == "broken":
            severity = "error"
        elif status == "warning":
            severity = "warning"
        else:
            continue  # skip ok

        counter[0] += 1
        findings.append({
            "id": f"{prefix}{counter[0]:03d}",
            "check": check_name,
            "severity": severity,
            "file": f.get("doc", ""),
            "line": f.get("line", 0),
            "message": f"{f.get('reason', 'Link issue')}: {f.get('target', '')}",
            "details": {
                "target": f.get("target", ""),
                "type": f.get("type", ""),
                "reason": f.get("reason", ""),
            },
        })

    return findings


def _normalize_version_findings(
    raw: Dict[str, Any], check_name: str, counter: List[int]
) -> List[Dict[str, Any]]:
    """Normalize version_checker output.

    status "mismatch" with major version difference -> error,
    status "mismatch" or "minor_mismatch" -> warning,
    status "ok" -> skip.
    """
    findings: List[Dict[str, Any]] = []
    prefix = FINDING_PREFIX[check_name]

    for f in raw.get("findings", []):
        status = f.get("status", "")
        if status == "ok":
            continue

        # Determine if major version differs
        doc_major = str(f.get("doc_value", "")).split(".")[0]
        actual_major = str(f.get("actual", "")).split(".")[0]
        if status == "mismatch" and doc_major != actual_major:
            severity = "error"
        elif status in ("mismatch", "minor_mismatch"):
            severity = "warning"
        else:
            continue

        counter[0] += 1
        findings.append({
            "id": f"{prefix}{counter[0]:03d}",
            "check": check_name,
            "severity": severity,
            "file": f.get("doc", ""),
            "line": f.get("line", 0),
            "message": (
                f"{f.get('name', 'unknown')} version mismatch: "
                f"doc says {f.get('doc_value', '?')}, "
                f"actual is {f.get('actual', '?')}"
            ),
            "details": {
                "name": f.get("name", ""),
                "doc_value": f.get("doc_value", ""),
                "actual": f.get("actual", ""),
                "status": status,
            },
        })

    return findings


def _normalize_staleness_findings(
    raw_list: List[Dict[str, Any]], check_name: str, counter: List[int]
) -> List[Dict[str, Any]]:
    """Normalize scan_freshness output.

    drift_score "stale"/"very_stale" -> warning,
    drift_score "aging" -> info,
    drift_score "fresh" -> skip.
    """
    findings: List[Dict[str, Any]] = []
    prefix = FINDING_PREFIX[check_name]

    for entry in raw_list:
        drift = entry.get("drift_score", "")
        if drift in ("stale", "very_stale"):
            severity = "warning"
        elif drift == "aging":
            severity = "info"
        else:
            continue  # fresh or unknown — skip

        counter[0] += 1
        doc_file = entry.get("file", entry.get("doc", ""))
        findings.append({
            "id": f"{prefix}{counter[0]:03d}",
            "check": check_name,
            "severity": severity,
            "file": doc_file,
            "line": 0,
            "message": f"Document is {drift} (drift score: {drift})",
            "details": {k: v for k, v in entry.items()},
        })

    return findings


def _normalize_claude_md_findings(
    raw: Dict[str, Any], check_name: str, counter: List[int]
) -> List[Dict[str, Any]]:
    """Normalize claude_md_checker output.

    severity "CRITICAL" -> error, severity "WARNING" -> warning,
    status "ok" -> skip.
    """
    findings: List[Dict[str, Any]] = []
    prefix = FINDING_PREFIX[check_name]

    for f in raw.get("findings", []):
        raw_severity = str(f.get("severity", "")).upper()
        status = str(f.get("status", "")).lower()

        if status == "ok":
            continue

        if raw_severity == "CRITICAL":
            severity = "error"
        elif raw_severity == "WARNING":
            severity = "warning"
        else:
            severity = "info"

        counter[0] += 1
        findings.append({
            "id": f"{prefix}{counter[0]:03d}",
            "check": check_name,
            "severity": severity,
            "file": f.get("file", f.get("doc", "")),
            "line": f.get("line", 0),
            "message": f.get("message", "CLAUDE.md issue"),
            "details": {k: v for k, v in f.items()
                        if k not in ("severity", "status")},
        })

    return findings


def _normalize_cross_doc_findings(
    raw: Dict[str, Any], check_name: str, counter: List[int]
) -> List[Dict[str, Any]]:
    """Normalize cross_doc_checker output.

    Maps severity from the checker directly.
    """
    findings: List[Dict[str, Any]] = []
    prefix = FINDING_PREFIX[check_name]

    for f in raw.get("findings", []):
        raw_severity = str(f.get("severity", "warning")).lower()
        if raw_severity in ("error", "critical"):
            severity = "error"
        elif raw_severity == "warning":
            severity = "warning"
        elif raw_severity == "info":
            severity = "info"
        else:
            severity = "info"

        counter[0] += 1
        findings.append({
            "id": f"{prefix}{counter[0]:03d}",
            "check": check_name,
            "severity": severity,
            "file": f.get("file", f.get("doc", "")),
            "line": f.get("line", 0),
            "message": f.get("message", "Cross-document issue"),
            "details": {k: v for k, v in f.items()
                        if k not in ("severity",)},
        })

    return findings


def _normalize_frontmatter_findings(
    raw: Dict[str, Any], check_name: str, counter: List[int]
) -> List[Dict[str, Any]]:
    """Normalize frontmatter_onboard output.

    Candidates found -> info (missing frontmatter is advisory).
    """
    findings: List[Dict[str, Any]] = []
    prefix = FINDING_PREFIX[check_name]

    for candidate in raw.get("candidates", []):
        counter[0] += 1
        findings.append({
            "id": f"{prefix}{counter[0]:03d}",
            "check": check_name,
            "severity": "info",
            "file": candidate.get("path", candidate.get("file", candidate.get("doc", ""))),
            "line": 0,
            "message": candidate.get("reason", "Missing frontmatter — consider adding metadata"),
            "details": {k: v for k, v in candidate.items()},
        })

    return findings


# ---------------------------------------------------------------------------
# Check runners
# ---------------------------------------------------------------------------


def _run_links(
    doc_paths: List[Path], project_root: Path, counter: List[int]
) -> List[Dict[str, Any]]:
    raw = _lazy_import("link_checker").check_all_links(doc_paths, project_root)
    return _normalize_link_findings(raw, "links", counter)


def _run_versions(
    doc_paths: List[Path], project_root: Path, counter: List[int]
) -> List[Dict[str, Any]]:
    raw = _lazy_import("version_checker").check_all_versions(doc_paths, project_root)
    return _normalize_version_findings(raw, "versions", counter)


def _run_staleness(
    doc_paths: List[Path], project_root: Path, counter: List[int],
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    raw_list = _lazy_import("scan_freshness").compute_staleness(doc_paths, project_root)
    return _normalize_staleness_findings(raw_list, "staleness", counter)


def _run_claude_md(
    doc_paths: List[Path], project_root: Path, counter: List[int]
) -> List[Dict[str, Any]]:
    raw = _lazy_import("claude_md_checker").check_claude_md(project_root)
    return _normalize_claude_md_findings(raw, "claude-md", counter)


def _run_cross_doc(
    doc_paths: List[Path], project_root: Path, counter: List[int]
) -> List[Dict[str, Any]]:
    raw = _lazy_import("cross_doc_checker").check_cross_doc(doc_paths, project_root)
    return _normalize_cross_doc_findings(raw, "cross-doc", counter)


def _run_frontmatter(
    doc_paths: List[Path], project_root: Path, counter: List[int]
) -> List[Dict[str, Any]]:
    raw = _lazy_import("frontmatter_onboard").suggest_onboarding(project_root)
    return _normalize_frontmatter_findings(raw, "frontmatter", counter)


# Map check name -> runner function
CHECK_RUNNERS = {
    "links": _run_links,
    "versions": _run_versions,
    "staleness": _run_staleness,
    "claude-md": _run_claude_md,
    "cross-doc": _run_cross_doc,
    "frontmatter": _run_frontmatter,
}


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------


def _build_summary(
    findings: List[Dict[str, Any]], checks_run: List[str]
) -> Dict[str, Any]:
    """Build summary from normalized findings."""
    errors = 0
    warnings = 0
    info = 0
    by_check: Dict[str, Dict[str, int]] = {}

    # Initialize by_check for all checks that ran
    for check in checks_run:
        by_check[check] = {"errors": 0, "warnings": 0, "info": 0}

    for f in findings:
        severity = f.get("severity", "info")
        check = f.get("check", "unknown")

        if check not in by_check:
            by_check[check] = {"errors": 0, "warnings": 0, "info": 0}

        if severity == "error":
            errors += 1
            by_check[check]["errors"] += 1
        elif severity == "warning":
            warnings += 1
            by_check[check]["warnings"] += 1
        else:
            info += 1
            by_check[check]["info"] += 1

    return {
        "total_issues": errors + warnings + info,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "by_check": by_check,
    }


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _load_config(config_file: Optional[str], project_root: Path) -> Optional[Dict[str, Any]]:
    """Load config from .arkhe.yaml if available."""
    if config_file:
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = project_root / config_path
    else:
        config_path = project_root / ".arkhe.yaml"

    if not config_path.exists():
        return None

    section = read_yaml_section(config_path, "doc-freshness")
    return section or None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Docs Health Action — unified CI entry point",
    )
    parser.add_argument(
        "project_root",
        nargs="?",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--checks",
        default="all",
        help=(
            "Comma-separated list of checks to run. "
            "Available: links, versions, staleness, claude-md, cross-doc, frontmatter, all. "
            "(default: all)"
        ),
    )
    parser.add_argument(
        "--doc-patterns",
        default=None,
        help="Comma-separated glob patterns for doc discovery (overrides defaults)",
    )
    parser.add_argument(
        "--exclude-patterns",
        default=None,
        help="Comma-separated glob patterns to exclude (overrides defaults)",
    )
    parser.add_argument(
        "--config-file",
        default=None,
        help="Path to .arkhe.yaml config file",
    )
    parser.add_argument(
        "--output",
        default="docs-health-report.json",
        help="Output JSON file path (default: docs-health-report.json)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    """Run selected checks and write unified JSON report."""
    args = parse_args(argv)

    project_root = Path(args.project_root).resolve()

    # Determine which checks to run
    if args.checks.strip().lower() == "all":
        checks_to_run = list(ALL_CHECKS)
    else:
        checks_to_run = [
            c.strip().lower()
            for c in args.checks.split(",")
            if c.strip().lower() in ALL_CHECKS
        ]

    if not checks_to_run:
        print("Warning: no valid checks specified, nothing to do.", file=sys.stderr)
        checks_to_run = []

    # Determine doc patterns
    doc_patterns: Optional[List[str]] = None
    if args.doc_patterns:
        doc_patterns = [p.strip() for p in args.doc_patterns.split(",") if p.strip()]

    exclude_patterns: Optional[List[str]] = None
    if args.exclude_patterns:
        exclude_patterns = [p.strip() for p in args.exclude_patterns.split(",") if p.strip()]

    # Discover markdown files
    doc_paths = discover_markdown_files(
        project_root,
        patterns=doc_patterns,
        exclude=exclude_patterns,
    )

    # Load config if available
    config = _load_config(args.config_file, project_root)

    # Run each check, collecting normalized findings
    all_findings: List[Dict[str, Any]] = []
    checks_run: List[str] = []

    for check_name in checks_to_run:
        runner = CHECK_RUNNERS.get(check_name)
        if runner is None:
            print(f"Warning: unknown check '{check_name}', skipping.", file=sys.stderr)
            continue

        # Per-check finding counter (mutable list for pass-by-reference)
        counter: List[int] = [0]

        try:
            if check_name == "staleness":
                findings = runner(doc_paths, project_root, counter, config=config)
            else:
                findings = runner(doc_paths, project_root, counter)
            all_findings.extend(findings)
            checks_run.append(check_name)
        except ImportError as exc:
            print(
                f"Warning: module for '{check_name}' not available ({exc}), skipping.",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"Warning: check '{check_name}' failed ({exc}), skipping.",
                file=sys.stderr,
            )
            checks_run.append(check_name)  # still mark as attempted

    # Build unified output
    summary = _build_summary(all_findings, checks_run)

    report = {
        "version": OUTPUT_VERSION,
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "checks_run": checks_run,
        "findings": all_findings,
        "summary": summary,
    }

    # Write output
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    # Print summary to stderr for CI visibility
    print(f"Docs health scan complete: {len(checks_run)} checks, "
          f"{summary['total_issues']} issues "
          f"({summary['errors']} errors, {summary['warnings']} warnings, "
          f"{summary['info']} info)", file=sys.stderr)
    print(f"Report written to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
