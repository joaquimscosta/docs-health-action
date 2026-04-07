#!/usr/bin/env python3
"""
GitHub workflow command annotation formatter for docs-health-action.

Reads JSON results from orchestrate.py and emits ::error, ::warning, ::notice
commands that appear as inline annotations in the PR diff.

Uses only standard library (no external dependencies). Python 3.8+.

Usage:
    python3 format_annotations.py [--threshold LEVEL] results.json

Arguments:
    results.json       Path to JSON results file from orchestrate.py.
    --threshold LEVEL  Minimum severity to include: critical, warning, info.
                       Default: warning.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from shared import normalize_severity, severity_meets_threshold

SEVERITY_TO_COMMAND = {
    "error": "error",
    "warning": "warning",
    "info": "notice",
}

MAX_MESSAGE_LEN = 1000


def escape_workflow_message(msg: str) -> str:
    """Escape special characters for GitHub workflow commands."""
    msg = msg.replace("%", "%25")
    msg = msg.replace("\r", "%0D")
    msg = msg.replace("\n", "%0A")
    return msg


def make_relative(file_path: str, project_root: str) -> str:
    """Strip project_root prefix to get repo-relative path."""
    if not file_path or not project_root:
        return file_path
    try:
        return str(Path(file_path).relative_to(project_root))
    except ValueError:
        return file_path


def format_annotations(results: Dict[str, Any], threshold: str) -> List[str]:
    """Generate workflow command lines from orchestrator results.

    Args:
        results: Parsed JSON from orchestrate.py.
        threshold: Minimum severity to include (error, warning, info).

    Returns:
        List of workflow command strings, one per finding.
    """
    project_root = results.get("project_root", "")
    lines: List[str] = []

    for f in results.get("findings", []):
        severity = normalize_severity(str(f.get("severity", "info")))
        if not severity_meets_threshold(severity, threshold):
            continue

        command = SEVERITY_TO_COMMAND.get(severity, "notice")
        message = str(f.get("message", ""))
        if len(message) > MAX_MESSAGE_LEN:
            message = message[:MAX_MESSAGE_LEN] + "... (truncated)"
        message = escape_workflow_message(message)

        file_path = make_relative(str(f.get("file", "")), project_root)
        line_num = f.get("line", 0) or 0

        if file_path:
            effective_line = max(line_num, 1)
            lines.append(f"::{command} file={file_path},line={effective_line}::{message}")
        else:
            lines.append(f"::{command}::{message}")

    return lines


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Format docs-health-action results as GitHub annotations."
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
        with open(results_path, encoding="utf-8") as fh:
            results = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading results file: {exc}", file=sys.stderr)
        sys.exit(1)

    for line in format_annotations(results, threshold):
        print(line)


if __name__ == "__main__":
    main()
