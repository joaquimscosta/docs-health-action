#!/usr/bin/env python3
"""
Frontmatter Onboarding Tool

Discovers markdown files that would benefit from tracking frontmatter
and suggests (or applies) minimal frontmatter using git history.

Generalized version for the docs-health-action GitHub Action. Candidate
patterns are configurable via CLI arg or function parameter, defaulting
to common project documentation locations.

Uses only standard library (no external dependencies). Python 3.8+.

Usage:
    python3 frontmatter_onboard.py <project_root>                        # Suggest mode
    python3 frontmatter_onboard.py --apply <project_root>                # Apply frontmatter
    python3 frontmatter_onboard.py <project_root> --patterns 'docs/**/*.md,README.md'

Output:
    JSON with candidates and suggested frontmatter.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import extract_frontmatter, git_last_modified, read_file_safe


# ---------------------------------------------------------------------------
# Default patterns: common project documentation locations
# ---------------------------------------------------------------------------

DEFAULT_CANDIDATE_PATTERNS: List[str] = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/**/*.md",
]


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------

def _find_candidates(
    project_root: Path, patterns: Optional[List[str]] = None
) -> List[Path]:
    """Find markdown files that need frontmatter onboarding.

    Uses the supplied patterns (or defaults). Skips files that already have
    frontmatter.
    """
    if patterns is None:
        patterns = DEFAULT_CANDIDATE_PATTERNS

    candidates: List[Path] = []

    for pattern in patterns:
        for md in sorted(project_root.glob(pattern)):
            if not md.is_file():
                continue
            content = read_file_safe(md)
            if not content:
                continue
            # Skip files that already have any frontmatter
            if extract_frontmatter(content) is not None:
                continue
            candidates.append(md)

    return candidates


# ---------------------------------------------------------------------------
# Frontmatter generation
# ---------------------------------------------------------------------------

def _extract_title(content: str) -> Optional[str]:
    """Extract the first heading from markdown content.

    Handles both markdown # headings and HTML <h1> tags.
    """
    # Try HTML <h1> first (some READMEs use this)
    html_match = re.search(r"<h1[^>]*>(.+?)</h1>", content, re.IGNORECASE | re.DOTALL)
    if html_match:
        title = html_match.group(1).strip()
        title = re.sub(r"<[^>]+>", "", title)  # Strip nested HTML tags
        return title

    # Fall back to markdown # heading
    md_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if md_match:
        title = md_match.group(1).strip()
        title = re.sub(r"\*\*(.+?)\*\*", r"\1", title)
        title = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", title)
        return title

    return None


def _git_last_date(path: Path, project_root: Path) -> str:
    """Get the last commit date (YYYY-MM-DD) for a file via git log."""
    rel = str(path.relative_to(project_root))
    iso_date = git_last_modified(rel, str(project_root))
    if iso_date:
        return iso_date[:10]
    return date.today().isoformat()


def _generate_frontmatter(path: Path, project_root: Path) -> Dict[str, str]:
    """Generate minimal 2-field frontmatter for a doc."""
    content = read_file_safe(path) or ""
    title = _extract_title(content) or path.stem
    last_updated = _git_last_date(path, project_root)

    return {
        "title": title,
        "last_updated": last_updated,
    }


def _format_frontmatter(fm: Dict[str, str]) -> str:
    """Format frontmatter dict as YAML block."""
    lines = ["---"]
    lines.append(f'title: "{fm["title"]}"')
    lines.append(f'last_updated: {fm["last_updated"]}')
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Apply frontmatter
# ---------------------------------------------------------------------------

def _apply_frontmatter(path: Path, fm: Dict[str, str]) -> bool:
    """Prepend frontmatter to a file. Returns True on success."""
    content = read_file_safe(path)
    if content is None:
        return False

    # Double-check: don't add if frontmatter already exists
    if extract_frontmatter(content) is not None:
        return False

    fm_block = _format_frontmatter(fm)
    new_content = fm_block + "\n\n" + content
    try:
        path.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def _count_skipped(
    project_root: Path, patterns: Optional[List[str]] = None
) -> int:
    """Count files matching patterns that already have frontmatter."""
    if patterns is None:
        patterns = DEFAULT_CANDIDATE_PATTERNS

    count = 0
    for pattern in patterns:
        for md in project_root.glob(pattern):
            if not md.is_file():
                continue
            content = read_file_safe(md)
            if content and extract_frontmatter(content) is not None:
                count += 1
    return count


def suggest_onboarding(
    project_root: Path, patterns: Optional[List[str]] = None
) -> dict:
    """Find candidates and generate suggested frontmatter.

    Args:
        project_root: Path to the project root.
        patterns: Optional list of glob patterns to search. Defaults to
                  DEFAULT_CANDIDATE_PATTERNS.

    Returns:
        Dict with candidates list and summary.
    """
    candidates = _find_candidates(project_root, patterns)

    results = []
    for path in candidates:
        rel = str(path.relative_to(project_root))
        fm = _generate_frontmatter(path, project_root)
        results.append({
            "path": rel,
            "suggested_frontmatter": fm,
        })

    skipped = _count_skipped(project_root, patterns)

    return {
        "candidates": results,
        "summary": {
            "total_scanned": len(results) + skipped,
            "already_has_frontmatter": skipped,
            "candidates": len(results),
        },
    }


def apply_onboarding(
    project_root: Path, patterns: Optional[List[str]] = None
) -> dict:
    """Apply frontmatter to all candidates.

    Args:
        project_root: Path to the project root.
        patterns: Optional list of glob patterns to search. Defaults to
                  DEFAULT_CANDIDATE_PATTERNS.

    Returns:
        Dict with results for each file.
    """
    candidates = _find_candidates(project_root, patterns)

    results = []
    applied = 0
    for path in candidates:
        rel = str(path.relative_to(project_root))
        fm = _generate_frontmatter(path, project_root)
        success = _apply_frontmatter(path, fm)
        results.append({
            "path": rel,
            "frontmatter": fm,
            "applied": success,
        })
        if success:
            applied += 1

    return {
        "results": results,
        "summary": {
            "candidates": len(candidates),
            "applied": applied,
            "failed": len(candidates) - applied,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suggest or apply frontmatter to docs that need tracking."
    )
    parser.add_argument(
        "project_root",
        help="Path to the project root directory",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply suggested frontmatter to candidate files",
    )
    parser.add_argument(
        "--patterns",
        default=None,
        help=(
            "Comma-separated glob patterns to search for candidate files. "
            "Overrides the default patterns. "
            'Example: "README.md,docs/**/*.md,wiki/**/*.md"'
        ),
    )

    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Parse patterns from CLI if provided
    patterns: Optional[List[str]] = None
    if args.patterns:
        patterns = [p.strip() for p in args.patterns.split(",") if p.strip()]

    if args.apply:
        result = apply_onboarding(root, patterns)
    else:
        result = suggest_onboarding(root, patterns)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
