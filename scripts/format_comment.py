#!/usr/bin/env python3
"""
PR comment markdown formatter for docs-health-action.

Reads JSON results from orchestrate.py and produces a markdown comment body
suitable for posting to a GitHub pull request.

Uses only standard library (no external dependencies). Python 3.8+.

Usage:
    python3 format_comment.py [--threshold LEVEL] results.json

Arguments:
    results.json       Path to JSON results file from orchestrate.py.
    --threshold LEVEL  Minimum severity to include: critical, warning, info.
                       Default: warning.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from shared import SEVERITY_ORDER, normalize_severity, severity_meets_threshold

# Maximum findings per section before truncation
MAX_PER_SECTION = 25

# Display labels for severity groups
SEVERITY_LABELS = {
    "error": "Errors",
    "warning": "Warnings",
    "info": "Info",
}


def extract_findings(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract findings from orchestrator JSON results.

    The orchestrator produces a unified format with a flat findings[] array.
    Each finding has: id, check, severity, file, line, message, details.

    Returns list of dicts with keys: file, line, check, message, severity.
    """
    unified: List[Dict[str, Any]] = []

    for f in results.get("findings", []):
        unified.append({
            "file": str(f.get("file", "")),
            "line": f.get("line", 0),
            "check": str(f.get("check", "unknown")),
            "message": str(f.get("message", "")),
            "severity": normalize_severity(str(f.get("severity", "info"))),
        })

    return unified


def group_by_severity(
    findings: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group findings by severity level, ordered: error, warning, info."""
    groups: Dict[str, List[Dict[str, Any]]] = {
        "error": [],
        "warning": [],
        "info": [],
    }
    for f in findings:
        sev = f.get("severity", "info")
        if sev in groups:
            groups[sev].append(f)
        else:
            groups["info"].append(f)
    return groups


def collect_checks(findings: List[Dict[str, Any]]) -> List[str]:
    """Collect unique check names from findings, sorted."""
    checks = sorted({f.get("check", "unknown") for f in findings})
    return checks


def format_line(line: Any) -> str:
    """Format a line number for display. Null/0 becomes '-'."""
    if line is None or line == 0:
        return "-"
    return str(line)


def render_table(findings: List[Dict[str, Any]]) -> str:
    """Render a findings table, capping at MAX_PER_SECTION."""
    lines: List[str] = []
    lines.append("| File | Line | Check | Finding |")
    lines.append("|------|------|-------|---------|")

    displayed = findings[:MAX_PER_SECTION]
    for f in displayed:
        file_col = f"`{f['file']}`" if not f["file"].startswith("`") else f["file"]
        lines.append(
            f"| {file_col} "
            f"| {format_line(f.get('line'))} "
            f"| {f.get('check', '')} "
            f"| {f.get('message', '')} |"
        )

    overflow = len(findings) - MAX_PER_SECTION
    if overflow > 0:
        lines.append(f"| | | | ...and {overflow} more |")

    return "\n".join(lines)


def format_comment(results: Dict[str, Any], threshold: str) -> str:
    """Format the full markdown comment from orchestrator results.

    Args:
        results: Parsed JSON from orchestrate.py.
        threshold: Minimum severity to include (error, warning, info).

    Returns:
        Markdown string for the PR comment body.
    """
    all_findings = extract_findings(results)

    # Filter by threshold
    filtered = [
        f for f in all_findings
        if severity_meets_threshold(f["severity"], threshold)
    ]

    # Zero findings → all clear
    if not filtered:
        return "## Documentation Health Report\n\nAll checks passed."

    # Group and count
    groups = group_by_severity(filtered)
    error_count = len(groups["error"])
    warning_count = len(groups["warning"])
    info_count = len(groups["info"])
    total = len(filtered)

    # Build summary counts string (only non-zero buckets)
    count_parts: List[str] = []
    if error_count:
        count_parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
    if warning_count:
        count_parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
    if info_count:
        count_parts.append(f"{info_count} info")
    counts_str = ", ".join(count_parts)

    sections: List[str] = []
    sections.append("## Documentation Health Report")
    sections.append("")
    sections.append(f"**{total} issue{'s' if total != 1 else ''} found** ({counts_str})")

    # Render each severity section (only non-empty)
    for sev_key in ("error", "warning", "info"):
        sev_findings = groups[sev_key]
        if not sev_findings:
            continue
        label = SEVERITY_LABELS[sev_key]
        sections.append("")
        sections.append(f"### {label} ({len(sev_findings)})")
        sections.append("")
        sections.append(render_table(sev_findings))

    # Footer
    all_checks = collect_checks(all_findings)
    if not all_checks:
        all_checks = collect_checks(filtered)
    checks_str = ", ".join(all_checks) if all_checks else "docs-health"

    sections.append("")
    sections.append("---")
    sections.append(
        f'<sub>Generated by <a href="https://github.com/joaquimscosta/docs-health-action">'
        f"docs-health-action</a> | Checks: {checks_str}</sub>"
    )

    return "\n".join(sections)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Format docs-health-action results as a PR comment."
    )
    parser.add_argument(
        "results_file",
        type=str,
        help="Path to JSON results file from orchestrate.py.",
    )
    parser.add_argument(
        "--threshold",
        choices=["critical", "warning", "info"],
        default="warning",
        help="Minimum severity to include (default: warning).",
    )
    args = parser.parse_args()

    # Normalize "critical" to "error" for internal use
    threshold = "error" if args.threshold == "critical" else args.threshold

    results_path = Path(args.results_file)
    if not results_path.is_file():
        print(f"Error: results file not found: {args.results_file}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(results_path, encoding="utf-8") as f:
            results = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading results file: {exc}", file=sys.stderr)
        sys.exit(1)

    markdown = format_comment(results, threshold)
    print(markdown)


if __name__ == "__main__":
    main()
