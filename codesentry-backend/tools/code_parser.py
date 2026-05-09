"""
Code ingestion: parse from raw string, GitHub URL, or base64 zip.
Extracts file contents and builds a flat list of (path, content) tuples.
"""
from __future__ import annotations

import ast
import base64
import io
import os
import re
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

# ──────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────

FileEntry = Tuple[str, str]  # (relative_path, content)

SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java", ".rb", ".php", ".sh", ".yaml", ".yml", ".toml", ".json"}
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB per file
MAX_TOTAL_FILES = 500


# ──────────────────────────────────────────────
# Raw code string
# ──────────────────────────────────────────────

def parse_code_string(code: str, filename: str = "input.py") -> List[FileEntry]:
    """Wrap a raw code string as a single-file entry."""
    return [(filename, code)]


# ──────────────────────────────────────────────
# Base64-encoded zip
# ──────────────────────────────────────────────

def parse_zip_base64(b64_content: str) -> List[FileEntry]:
    """Decode a base64 zip and extract all supported source files."""
    try:
        raw = base64.b64decode(b64_content)
    except Exception as exc:
        raise ValueError(f"Invalid base64 zip content: {exc}") from exc

    entries: List[FileEntry] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        for name in names[:MAX_TOTAL_FILES]:
            ext = Path(name).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            info = zf.getinfo(name)
            if info.file_size > MAX_FILE_SIZE_BYTES:
                continue
            try:
                content = zf.read(name).decode("utf-8", errors="replace")
                entries.append((name, content))
            except Exception:
                continue
    return entries


# ──────────────────────────────────────────────
# Local directory (for cloned repos)
# ──────────────────────────────────────────────

def parse_directory(directory: str) -> List[FileEntry]:
    """Walk a local directory and collect all supported source files."""
    root = Path(directory)
    entries: List[FileEntry] = []

    # Directories to skip
    skip_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        "env", ".env", "dist", "build", ".mypy_cache", ".pytest_cache",
    }

    for path in root.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.stat().st_size > MAX_FILE_SIZE_BYTES:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            rel = str(path.relative_to(root))
            entries.append((rel, content))
        except Exception:
            continue

        if len(entries) >= MAX_TOTAL_FILES:
            break

    return entries


# ──────────────────────────────────────────────
# AST helpers (Python only)
# ──────────────────────────────────────────────

def extract_python_ast(code: str) -> Optional[ast.AST]:
    """Parse Python source and return the AST; returns None on parse failure."""
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def get_function_names(tree: ast.AST) -> List[str]:
    """Return all function/method names defined in an AST."""
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def get_imports(tree: ast.AST) -> List[str]:
    """Return all imported module names."""
    modules: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def get_line_content(code: str, line_number: int) -> str:
    """Return the content of a specific 1-indexed line."""
    lines = code.splitlines()
    if 1 <= line_number <= len(lines):
        return lines[line_number - 1]
    return ""


def get_snippet(code: str, line_number: int, context: int = 3) -> str:
    """Return a snippet of code around a given line number (1-indexed)."""
    lines = code.splitlines()
    start = max(0, line_number - 1 - context)
    end = min(len(lines), line_number + context)
    snippet_lines = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        prefix = ">>>" if i == line_number else "   "
        snippet_lines.append(f"{prefix} {i:4d} | {line}")
    return "\n".join(snippet_lines)


# ──────────────────────────────────────────────
# Regex-based pattern search across files
# ──────────────────────────────────────────────

def find_pattern_in_code(
    code: str,
    pattern: str,
    file_path: str = "unknown",
) -> List[dict]:
    """
    Search for a regex pattern in code.
    Returns a list of {line_number, line_content, snippet} dicts.
    """
    results = []
    try:
        compiled = re.compile(pattern, re.MULTILINE | re.DOTALL)
    except re.error:
        return results

    for match in compiled.finditer(code):
        line_number = code[: match.start()].count("\n") + 1
        results.append(
            {
                "file_path": file_path,
                "line_number": line_number,
                "line_content": get_line_content(code, line_number),
                "snippet": get_snippet(code, line_number),
            }
        )
    return results


def count_tokens_estimate(text: str) -> int:
    """Rough token count estimate (1 token ≈ 4 chars)."""
    return max(1, len(text) // 4)


def build_context_block(files: List[FileEntry], max_tokens: int = 3000) -> str:
    """
    Concatenate files into a single context block for the LLM.
    Respects an approximate token budget.
    """
    blocks: List[str] = []
    used_tokens = 0

    for path, content in files:
        header = f"\n\n# === FILE: {path} ===\n"
        chunk = header + content
        chunk_tokens = count_tokens_estimate(chunk)
        if used_tokens + chunk_tokens > max_tokens:
            break
        blocks.append(chunk)
        used_tokens += chunk_tokens

    return "".join(blocks)
