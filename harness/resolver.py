"""Thin wrapper over the Rust resolver binary (``crates/resolver``).

The anchor space of a file is enumerated in exactly one place — ``sideword-resolver
index`` — so the writer, the reader and the harness all agree on which anchors exist
and how ties (``FORMAT.md`` §1.5) are numbered.  Nothing here re-derives an anchor.

An entry is the JSON the binary emits::

    {"anchor": "Cart.add#assign:self.total", "target": "statement",
     "line": 12, "end_line": 12, "notes": []}
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY = Path(os.environ.get("SIDEWORD_RESOLVER", ROOT / "target" / "release" / "sideword-resolver"))

# argv is cheap but not free; the binary holds one parse at a time either way.
CHUNK = 128

SYMBOL_TARGETS = frozenset({"definition", "variable", "attribute"})
PART_TARGETS = frozenset({"part"})


class ResolverError(RuntimeError):
    """The binary refused a file: unreadable, or it does not parse."""


class ResolverMissing(ResolverError):
    """The binary is not built. Distinct from a rejected file because
    `index_files` treats a rejection as "this source does not parse" and moves
    on — which, when the binary is simply absent, turns one clear error into a
    parse failure on every file in the corpus."""


def _run(args: list[str]) -> str:
    if not BINARY.exists():
        raise ResolverMissing(
            f"resolver binary not built: {BINARY}\n"
            f"build it first: cargo build --release -p sideword-resolver")
    proc = subprocess.run([str(BINARY), *args], capture_output=True)
    if proc.returncode != 0:
        raise ResolverError(proc.stderr.decode("utf-8", "replace").strip() or "resolver failed")
    return proc.stdout.decode("utf-8")


def index_files(paths) -> dict[str, list[dict]]:
    """``{path: [entry, ...]}`` for every file that parses.

    ``index`` fails the whole invocation on the first bad file, so a failing chunk is
    retried one file at a time and the offenders are simply left out of the result.
    """
    out: dict[str, list[dict]] = {}
    paths = [str(p) for p in paths]
    for i in range(0, len(paths), CHUNK):
        chunk = paths[i:i + CHUNK]
        try:
            payload = json.loads(_run(["index", *chunk]))
        except ResolverMissing:
            raise                      # not a bad file; nothing here can work
        except ResolverError:
            if len(chunk) == 1:
                continue
            for path in chunk:
                out.update(index_files([path]))
            continue
        for item in payload:
            out[item["file"]] = item["anchors"]
    return out


def index_text(text: str) -> list[dict]:
    """Anchors of a module held in memory.

    The binary reads UTF-8, so the caller's already-decoded text is what gets written;
    line numbers are per physical line and survive the re-encoding untouched.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "module.py"
        path.write_text(text, encoding="utf-8")
        indexed = index_files([path])
        if str(path) not in indexed:
            raise ResolverError("source does not parse")
        return indexed[str(path)]


def by_anchor(entries: list[dict]) -> dict[str, dict]:
    """First entry under each canonical anchor text."""
    out: dict[str, dict] = {}
    for entry in entries:
        out.setdefault(entry["anchor"], entry)
    return out
