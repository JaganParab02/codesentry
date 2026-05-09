"""
GitHub Repo Fetcher — clones a GitHub repo to temp dir and extracts source files.
"""

import os
import tempfile
import shutil
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".cs", ".php", ".rb", ".kt",
}

MAX_FILE_SIZE = 100_000  # bytes
MAX_FILES = 50


def fetch_github_repo(url: str) -> dict[str, str]:
    """Clone a GitHub repo and return {filename: content} dict."""
    import git  # gitpython

    tmp_dir = tempfile.mkdtemp(prefix="codesentry_")
    try:
        repo = git.Repo.clone_from(url, tmp_dir, depth=1, single_branch=True)
        files = {}

        for path in Path(tmp_dir).rglob("*"):
            if len(files) >= MAX_FILES:
                break
            if not path.is_file():
                continue
            if path.suffix not in SUPPORTED_EXTENSIONS:
                continue
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
            # Skip common non-source dirs
            parts = path.parts
            if any(p in parts for p in ("node_modules", ".git", "__pycache__", "dist", "build", ".venv")):
                continue

            try:
                relative = str(path.relative_to(tmp_dir))
                files[relative] = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

        return files
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
