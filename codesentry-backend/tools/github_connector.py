"""
GitHub repository connector.
Clones a public GitHub repo to a temporary local directory
and returns the path for downstream parsing.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Regex for validating GitHub URLs
GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.\-]+)/(?P<repo>[A-Za-z0-9_.\-]+?)(?:\.git)?(?:/.*)?$"
)


def _validate_github_url(url: str) -> re.Match:
    """Raise ValueError if the URL is not a valid public GitHub repo URL."""
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise ValueError(
            f"Invalid GitHub URL: {url!r}. "
            "Expected format: https://github.com/<owner>/<repo>"
        )
    return match


def clone_repo(url: str, target_dir: Optional[str] = None) -> str:
    """
    Clone a GitHub repository into *target_dir* (or a temp dir).
    Returns the path to the cloned repository root.

    Raises:
        ValueError: If the URL is invalid.
        RuntimeError: If git clone fails.
    """
    match = _validate_github_url(url)
    owner = match.group("owner")
    repo = match.group("repo")

    # Build a clean clone URL (strip any path suffix after repo name)
    clone_url = f"https://github.com/{owner}/{repo}.git"

    if target_dir is None:
        target_dir = tempfile.mkdtemp(prefix="codesentry_")

    dest = os.path.join(target_dir, repo)
    logger.info("Cloning %s → %s", clone_url, dest)

    # Use gitpython if available, fall back to subprocess
    try:
        import git  # type: ignore

        git.Repo.clone_from(
            clone_url,
            dest,
            depth=1,  # shallow clone — we only need the code, not history
            no_single_branch=True,
        )
    except ImportError:
        import subprocess  # noqa: S404

        result = subprocess.run(  # noqa: S603 S607
            ["git", "clone", "--depth", "1", clone_url, dest],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git clone failed (exit {result.returncode}): {result.stderr.strip()}"
            )

    return dest


def cleanup_repo(path: str) -> None:
    """Remove a cloned repository directory from disk."""
    try:
        shutil.rmtree(path, ignore_errors=True)
        logger.debug("Cleaned up repo dir: %s", path)
    except Exception as exc:
        logger.warning("Failed to clean up %s: %s", path, exc)


def get_repo_info(url: str) -> dict:
    """Extract owner and repo name from a GitHub URL without cloning."""
    match = _validate_github_url(url)
    return {
        "owner": match.group("owner"),
        "repo": match.group("repo"),
        "clone_url": f"https://github.com/{match.group('owner')}/{match.group('repo')}.git",
    }


class GitHubConnector:
    """
    Context-manager wrapper around clone/cleanup.

    Usage::

        async with GitHubConnector("https://github.com/foo/bar") as repo_dir:
            files = parse_directory(repo_dir)
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self._repo_dir: Optional[str] = None
        self._tmp_dir: Optional[str] = None

    def __enter__(self) -> str:
        self._tmp_dir = tempfile.mkdtemp(prefix="codesentry_")
        self._repo_dir = clone_repo(self.url, target_dir=self._tmp_dir)
        return self._repo_dir

    def __exit__(self, *_: object) -> None:
        if self._tmp_dir:
            cleanup_repo(self._tmp_dir)

    # Async support
    async def __aenter__(self) -> str:
        return self.__enter__()

    async def __aexit__(self, *args: object) -> None:
        self.__exit__(*args)
