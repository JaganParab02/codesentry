"""
Unified diff generator for producing git-compatible patch output.
Used by the Fix Agent to generate per-file diffs.
"""
from __future__ import annotations

import difflib
from typing import List, Tuple


def generate_unified_diff(
    original: str,
    fixed: str,
    filename: str = "file.py",
    context_lines: int = 3,
) -> str:
    """
    Generate a unified diff string between *original* and *fixed* code.
    Compatible with `git apply` and standard patch utilities.
    """
    original_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )
    )

    if not diff_lines:
        return ""  # No changes

    return "".join(diff_lines)


def generate_inline_diff(original: str, fixed: str) -> List[Tuple[str, str]]:
    """
    Return a list of (tag, line) tuples using difflib opcodes.
    Tags: 'equal', 'replace', 'delete', 'insert'
    Useful for rich HTML/JSON diff rendering.
    """
    matcher = difflib.SequenceMatcher(None, original.splitlines(), fixed.splitlines())
    result: List[Tuple[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in original.splitlines()[i1:i2]:
                result.append(("equal", line))
        elif tag in ("replace", "delete"):
            for line in original.splitlines()[i1:i2]:
                result.append(("delete", f"- {line}"))
            if tag == "replace":
                for line in fixed.splitlines()[j1:j2]:
                    result.append(("insert", f"+ {line}"))
        elif tag == "insert":
            for line in fixed.splitlines()[j1:j2]:
                result.append(("insert", f"+ {line}"))

    return result


def apply_line_fix(
    original: str,
    line_number: int,
    replacement_line: str,
) -> str:
    """
    Replace a single line (1-indexed) in *original* with *replacement_line*.
    Returns the modified code string.
    """
    lines = original.splitlines(keepends=True)
    if 1 <= line_number <= len(lines):
        # Preserve original line ending
        ending = "\n"
        if lines[line_number - 1].endswith("\r\n"):
            ending = "\r\n"
        lines[line_number - 1] = replacement_line.rstrip("\r\n") + ending
    return "".join(lines)


def insert_before_line(
    original: str,
    line_number: int,
    new_lines: str,
) -> str:
    """
    Insert *new_lines* before the given 1-indexed *line_number*.
    """
    lines = original.splitlines(keepends=True)
    insert_text = new_lines if new_lines.endswith("\n") else new_lines + "\n"
    idx = max(0, line_number - 1)
    lines.insert(idx, insert_text)
    return "".join(lines)


def count_diff_stats(diff_text: str) -> dict:
    """Return additions, deletions, and net change counts from a unified diff."""
    additions = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))
    return {
        "additions": additions,
        "deletions": deletions,
        "net_change": additions - deletions,
    }


def format_pr_diff_block(diffs: List[Tuple[str, str]]) -> str:
    """
    Format a list of (filename, diff) tuples as a markdown code block
    suitable for GitHub PR descriptions.
    """
    blocks: List[str] = []
    for filename, diff in diffs:
        if diff:
            blocks.append(f"**`{filename}`**\n```diff\n{diff}\n```")
    return "\n\n".join(blocks)
