"""The writers' safety net: prose must survive the round trip.

`harness/sidedoc.py`, `harness/anchoring.py` and `harness/inline.py` had no test
file, which is how they shipped with the record accounting broken. The check
that matters is not byte-exactness — `FORMAT.md` is normative about how a record
renders, so legacy source comes back normalised and that is a format finding,
not a bug. What must never happen is prose going missing with nobody saying so.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import anchoring, directives as directives_mod, inline, roundtrip, strip  # noqa: E402

D = directives_mod.load()
SAMPLE = ROOT / "corpus" / "convert-pilot" / "sample.json"
CACHE = ROOT / "cache"


def prose(sidecar, source: bytes) -> list[str]:
    lines = strip.split_lines(anchoring._decode(source))
    return [t for t in roundtrip.documentation(sidecar, lines) if t]


def lost_prose(source: bytes) -> list[str]:
    """Documentation in `source` that is nowhere in its reconstruction and was
    never declared unanchorable. Anything else — a block re-split, a marker
    re-rendered, a quote style normalised — moves prose without losing it."""
    art = anchoring.convert(source, D)
    clean, anchored = art["source"], art["anchored"]
    entries = anchoring.resolver.index_text(anchoring._decode(clean))
    rebuilt, _ = inline.reconstruct(clean, art["sidedoc"], entries=entries)
    _, resid = strip.strip_source(rebuilt, D)

    declared = {roundtrip.doc_text(u["kind"], u.get("text", "")) for u in anchored.unanchorable}
    haystack = roundtrip._squash(" \0 ".join(prose(resid, rebuilt)))
    return [t for t in prose(art["sidecar"], source)
            if t not in declared and roundtrip._squash(t) not in haystack]


SHAPES = {
    "block_is_one_record": b"""
# first paragraph, line one
# first paragraph, line two

# second paragraph, same statement
rats = {}
""",
    "post_at_end_of_block_and_file": b"""
def render(ani):
    ani.save("out.gif")

    # nothing follows this inside the function


# and nothing follows this in the file
""",
    "banner_comment_keeps_its_hashes": b"""
######################## BEGIN LICENSE BLOCK ########################
# The Original Code is a test.
######################### END LICENSE BLOCK #########################
value = 1
""",
    "elements_reached_through_wrappers": b"""
DOMAIN_INDEX_TYPE = Tuple[
    str,                  # index name
    Type[Index],          # index class
]
key = {
    "prior": "pageup",    # used by tk
}.get(key, key)
""",
    "lead_above_else_and_finally": b"""
def f(x):
    try:
        go()
    except ValueError:
        pass
    # why we fall back here
    else:
        done()
    # cleanup always runs
    finally:
        close()
""",
    "identical_siblings_tie": b"""
def f(rows):
    for row in rows:
        # about the first loop
        log(row)
    for row in rows:
        # about the second loop
        log(row)
""",
    "docstring_and_trailing_together": b'''
class Cart:
    """A shopping cart."""

    def add(self, item, qty=1):
        """Add an item."""
        self.total += qty  # recompute eagerly
        return self.total
''',
}


class TestProseSurvives(unittest.TestCase):
    """One case per rule the format states about records and kinds."""

    def test_shapes(self):
        for name, source in sorted(SHAPES.items()):
            with self.subTest(shape=name):
                self.assertEqual(lost_prose(source), [], f"prose lost: {name}")

    def test_real_code(self):
        """Hand-written shapes cover the rules; real files cover what people
        actually wrote. Originals come from the corpus mirror, so this skips
        cleanly on a machine that has not built it."""
        if not SAMPLE.exists():
            self.skipTest("corpus sample not present")
        sample = json.loads(SAMPLE.read_text())
        shas = [e["blob_sha"] for e in sample if (CACHE / f"{e['blob_sha']}.jsonl").exists()][:10]
        if not shas:
            self.skipTest("strip cache not present")
        try:
            sources = roundtrip.blobs(shas)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("corpus mirror not available")
        if not sources:
            self.skipTest("corpus mirror has no blobs")
        by_sha = {e["blob_sha"]: e.get("path") for e in sample}
        for sha, source in sources.items():
            with self.subTest(path=by_sha.get(sha)):
                self.assertEqual(lost_prose(source), [])


class TestAccounting(unittest.TestCase):
    def test_unanchorable_carries_its_text(self):
        """A dropped record can only be told apart from an unanchorable one if
        the rejection says what it rejected. It did not, once, and the round
        trip reported 15 failing files where nothing had been lost."""
        source = b"x = [i for i in range(3)  # inside a comprehension\n     ]\n"
        anchored = anchoring.convert(source, D)["anchored"]
        for item in anchored.unanchorable:
            self.assertTrue(item.get("text"), "unanchorable record must report its text")

    def test_banner_markers_are_not_loss(self):
        """`#### BEGIN ####` comes back as `# ### BEGIN ####` once the writer
        re-renders the marker. That moves a `#` into the body without changing a
        word, and must not be counted as a lost record."""
        a = roundtrip.doc_text("comment", "######## BEGIN LICENSE BLOCK ########")
        b = roundtrip.doc_text("comment", "# ####### BEGIN LICENSE BLOCK ########")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()


class TestMigrate(unittest.TestCase):
    """`harness/migrate.py` — a whole repo, not one file."""

    def test_converts_a_tree_and_leaves_the_code_alone(self):
        import shutil
        import tempfile

        from harness import migrate

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "repo"
            (src / "pkg").mkdir(parents=True)
            (src / "pkg" / "mod.py").write_bytes(SHAPES["docstring_and_trailing_together"])
            (src / "pkg" / "__init__.py").write_bytes(b"")
            # Never converted: a test file, and a non-Python file.
            (src / "tests").mkdir()
            (src / "tests" / "test_mod.py").write_bytes(b"# a test comment\nassert True\n")
            (src / "README.md").write_bytes(b"# readme\n")

            out = Path(tmp) / "out"
            rc = migrate.main([str(src), "--out", str(out), "--jobs", "1"])
            self.assertEqual(rc, 0)

            # The three artifacts, in the places FORMAT.md names.
            self.assertTrue((out / "pkg" / "mod.py").exists())
            self.assertTrue((out / ".sideword" / "pkg" / "mod.py.idx").exists())
            self.assertTrue((out / ".sideword" / "pkg" / "mod.py.md").exists())

            # The clean source still parses and has lost its prose to the sidedoc.
            import ast
            clean = (out / "pkg" / "mod.py").read_text()
            ast.parse(clean)
            self.assertNotIn("recompute eagerly", clean)
            self.assertIn("recompute eagerly", (out / ".sideword" / "pkg" / "mod.py.md").read_text())

            # Test files and everything else are copied untouched.
            self.assertEqual((out / "tests" / "test_mod.py").read_bytes(),
                             b"# a test comment\nassert True\n")
            self.assertEqual((out / "README.md").read_bytes(), b"# readme\n")
            self.assertFalse((out / ".sideword" / "tests" / "test_mod.py.md").exists())
            shutil.rmtree(out, ignore_errors=True)

    def test_check_writes_nothing(self):
        import tempfile

        from harness import migrate

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "repo"
            src.mkdir()
            original = SHAPES["block_is_one_record"]
            (src / "mod.py").write_bytes(original)
            self.assertEqual(migrate.main([str(src), "--check", "--jobs", "1"]), 0)
            self.assertEqual((src / "mod.py").read_bytes(), original)
            self.assertFalse((src / ".sideword").exists())
