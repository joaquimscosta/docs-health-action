#!/usr/bin/env python3
"""
Heuristic cross-document consistency checker for CI.

Detects mechanical contradictions between documentation files — specifically
version conflicts where different docs cite different version numbers for
the same tool or language.

Uses only standard library (no external dependencies). Python 3.8+.

Usage:
    python3 cross_doc_checker.py <project_root> <doc-file>...
"""

import json
import re
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import _update_fence_state, extract_headings, read_file_safe


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------

# Words to strip from headings when building topic keywords
_STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
    "is", "are", "be", "it", "its", "this", "that", "your", "my",
}


def _heading_to_topic(text: str) -> Optional[str]:
    """Normalize a heading to a lowercase topic keyword string.

    Strips markdown formatting, punctuation, stop words, and collapses whitespace.
    Returns None if the result is empty or a single character.
    """
    # Remove inline code, bold, italic markers
    cleaned = re.sub(r'[`*_~]', '', text)
    # Remove emoji shortcodes (:emoji:) and unicode emoji
    cleaned = re.sub(r':[a-z_]+:', '', cleaned)
    # Lowercase and strip punctuation except hyphens
    cleaned = cleaned.lower()
    cleaned = re.sub(r'[^a-z0-9\s-]', '', cleaned)
    # Split into words, remove stop words
    words = [w for w in cleaned.split() if w and w not in _STOP_WORDS]
    if not words:
        return None
    topic = " ".join(words)
    return topic if len(topic) > 1 else None


def extract_topics(content: str) -> Dict[str, int]:
    """Extract topic keywords from all headings in a document.

    Returns dict mapping normalized topic → heading line number.
    """
    headings = extract_headings(content)
    topics: Dict[str, int] = {}
    for h in headings:
        topic = _heading_to_topic(str(h["text"]))
        if topic and topic not in topics:
            topics[topic] = int(h.get("line", 0))
    return topics


def find_overlapping_pairs(
    doc_topics: Dict[str, Dict[str, int]],
) -> List[Tuple[str, str, Set[str]]]:
    """Find document pairs with overlapping topics.

    Args:
        doc_topics: Mapping of doc_path → {topic → line}.

    Returns:
        List of (doc_a, doc_b, shared_topics) tuples.
    """
    pairs: List[Tuple[str, str, Set[str]]] = []
    doc_keys = sorted(doc_topics.keys())
    for a, b in combinations(doc_keys, 2):
        shared = set(doc_topics[a].keys()) & set(doc_topics[b].keys())
        if shared:
            pairs.append((a, b, shared))
    return pairs


# ---------------------------------------------------------------------------
# Factual claim extraction
# ---------------------------------------------------------------------------

# Version patterns: Tool/Language followed by version number
# Matches: "Node.js 18", "Python: v3.11.2", "Java 21", "Go v1.22", "Ruby 3.2.1", "Rust 1.75"
_VERSION_CLAIM_RE = re.compile(
    r'(Node|Python|Java|Go|Ruby|Rust|NodeJS)(?:\.js)?'
    r'[\s:]+v?(\d+(?:\.\d+)*)',
    re.IGNORECASE,
)


def extract_version_claims(content: str) -> List[Dict[str, Any]]:
    """Extract version claims from document content.

    Returns list of dicts with keys: tool, version, line.
    Skips claims inside fenced code blocks.
    """
    claims: List[Dict[str, Any]] = []
    lines = content.splitlines()
    in_code_block = False
    open_fence = ""

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        prev_state = in_code_block
        in_code_block, open_fence = _update_fence_state(
            stripped, in_code_block, open_fence
        )
        if in_code_block or prev_state != in_code_block:
            continue

        for match in _VERSION_CLAIM_RE.finditer(line):
            tool = match.group(1).lower()
            # Normalize tool names
            if tool in ("node", "nodejs"):
                tool = "node"
            version = match.group(2)
            claims.append({
                "tool": tool,
                "version": version,
                "line": line_num,
            })

    return claims


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def _versions_conflict(ver_a: str, ver_b: str) -> bool:
    """Check if two version strings conflict (different major version).

    Compares major version numbers. If both have minor versions and major
    matches, also compares minor.

    Examples:
        "18" vs "20" → True (conflict)
        "18.0" vs "18.2" → False (close enough)
        "3.11" vs "3.9" → True (minor differs)
        "21" vs "21" → False (same)
    """
    parts_a = ver_a.split(".")
    parts_b = ver_b.split(".")

    # Major version mismatch is always a conflict
    if parts_a[0] != parts_b[0]:
        return True

    # If both have minor versions and major matches, check minor
    if len(parts_a) > 1 and len(parts_b) > 1:
        if parts_a[1] != parts_b[1]:
            return True

    return False


def detect_version_conflicts(
    doc_a_path: str,
    doc_a_claims: List[Dict[str, Any]],
    doc_b_path: str,
    doc_b_claims: List[Dict[str, Any]],
    shared_topics: Set[str],
) -> List[Dict[str, Any]]:
    """Detect version conflicts between two documents.

    Only flags conflicts for tools mentioned in both documents.

    Returns list of finding dicts.
    """
    findings: List[Dict[str, Any]] = []

    # Build tool → version mapping for each doc
    # Use the first occurrence of each tool
    tools_a: Dict[str, str] = {}
    for c in doc_a_claims:
        tool = c["tool"]
        if tool not in tools_a:
            tools_a[tool] = c["version"]

    tools_b: Dict[str, str] = {}
    for c in doc_b_claims:
        tool = c["tool"]
        if tool not in tools_b:
            tools_b[tool] = c["version"]

    # Find tools mentioned in both docs with conflicting versions
    common_tools = set(tools_a.keys()) & set(tools_b.keys())
    for tool in sorted(common_tools):
        ver_a = tools_a[tool]
        ver_b = tools_b[tool]
        if _versions_conflict(ver_a, ver_b):
            # Pick a representative shared topic for context
            topic = sorted(shared_topics)[0] if shared_topics else "shared content"
            # Capitalize tool name for display
            display_name = {
                "node": "Node.js",
                "python": "Python",
                "java": "Java",
                "go": "Go",
                "ruby": "Ruby",
                "rust": "Rust",
            }.get(tool, tool.capitalize())

            findings.append({
                "doc_a": doc_a_path,
                "doc_b": doc_b_path,
                "topic": topic,
                "type": "version_conflict",
                "detail": (
                    f"{display_name} version: {doc_a_path} says {ver_a}, "
                    f"{doc_b_path} says {ver_b}"
                ),
                "severity": "WARNING",
            })

    return findings


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_cross_doc(
    doc_paths: List[Path], project_root: Path
) -> Dict[str, Any]:
    """Run cross-document consistency checks.

    Args:
        doc_paths: List of markdown file paths to check.
        project_root: Project root for computing relative paths.

    Returns:
        Dict with keys: findings, summary.
    """
    all_findings: List[Dict[str, Any]] = []

    # Phase 1: Read all docs, extract topics and version claims
    doc_topics: Dict[str, Dict[str, int]] = {}
    doc_claims: Dict[str, List[Dict[str, Any]]] = {}
    docs_read = 0

    for doc_path in doc_paths:
        content = read_file_safe(doc_path)
        if content is None:
            continue

        rel_path = str(doc_path.relative_to(project_root))
        docs_read += 1

        doc_topics[rel_path] = extract_topics(content)
        doc_claims[rel_path] = extract_version_claims(content)

    # Phase 2: Find overlapping document pairs
    overlapping_pairs = find_overlapping_pairs(doc_topics)

    # Phase 3: Check each overlapping pair for contradictions
    for doc_a, doc_b, shared_topics in overlapping_pairs:
        claims_a = doc_claims.get(doc_a, [])
        claims_b = doc_claims.get(doc_b, [])

        if not claims_a or not claims_b:
            continue

        conflicts = detect_version_conflicts(
            doc_a, claims_a,
            doc_b, claims_b,
            shared_topics,
        )
        all_findings.extend(conflicts)

    return {
        "findings": all_findings,
        "summary": {
            "docs_compared": docs_read,
            "overlapping_pairs": len(overlapping_pairs),
            "conflicts": len(all_findings),
        },
    }


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 3:
        print(
            "Usage: cross_doc_checker.py <project_root> <doc-file>...",
            file=sys.stderr,
        )
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    doc_files = [Path(f).resolve() for f in sys.argv[2:]]

    result = check_cross_doc(doc_files, project_root)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
