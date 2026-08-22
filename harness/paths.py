"""Test-path rule shared by pass 1 and pass 2 (harness/CONTRACT.md).

A path is a test path (never stripped) if ANY holds:
  - any path segment is ``tests``, ``test`` or ``testing``;
  - basename is ``conftest.py`` or ``tests.py``, or matches ``test_*.py`` / ``*_test.py``;
  - it appears in the caller-supplied ``extra`` set (the instance's ``test_patch_paths``).
"""

from __future__ import annotations

from collections.abc import Collection

TEST_SEGMENTS = frozenset({"tests", "test", "testing"})
TEST_BASENAMES = frozenset({"conftest.py", "tests.py"})


def _normalize(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def is_test_path(path: str, extra: Collection[str] = frozenset()) -> bool:
    """Return True if ``path`` (repo-relative, '/'-separated) must never be stripped."""
    norm = _normalize(path)
    if path in extra or norm in extra:
        return True
    if extra and any(_normalize(e) == norm for e in extra):
        return True
    segments = [s for s in norm.split("/") if s]
    if not segments:
        return False
    if any(seg in TEST_SEGMENTS for seg in segments):
        return True
    base = segments[-1]
    if base in TEST_BASENAMES:
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    return False
