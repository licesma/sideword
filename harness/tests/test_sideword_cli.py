"""`sideword` is arm 2's only way in.

The mirror tree is outside glob range by design, so if this command misreports what
is documented, or dies on one of the 1,749 corpus paths whose sidedoc is empty, the
arm does not degrade — it produces a run that looks like the agent chose not to
retrieve. These tests hold the two properties that failure mode turns on: every
anchor the index advertises is fetchable, and nothing here ever prints a record the
caller did not ask for.

Fixtures are synthetic because the corpus has no `#param:` parts anywhere (the
converter folds `:param:` lines into the parent docstring), and a format feature with
no corpus coverage is exactly the one that rots.
"""

import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import sideword_cli  # noqa: E402
from harness.sidedoc import Record, write_index, write_sidedoc  # noqa: E402

CART = [
    Record("<module>", "doc", "Shopping cart and checkout."),
    Record("MAX_TOKENS", "trail", "hard cap"),
    Record("Cart", "doc", "A shopping cart.\nNot thread-safe; one per session."),
    Record("Cart.add", "doc", "Add an item to the cart."),
    Record("Cart.add#param:qty", "doc", "How many. Must be positive."),
    Record("Cart.add#returns", "doc", "The new total count."),
    Record("Cart.add#assign:self.total", "lead", "Recompute eagerly."),
    Record("Cart.add#if:qty < 0", "lead", "first of a tie"),
    Record("Cart.add#if:qty < 0", "lead", "second of a tie"),
]


def run(*argv):
    """`(status, stdout, stderr)` for one invocation, as a shell would see it."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = sideword_cli.main(list(argv))
    return status, out.getvalue(), err.getvalue()


class CliTestCase(unittest.TestCase):
    """A converted repository in a temporary directory, with the process inside it."""

    files = {"src/cart.py": CART, "src/empty.py": []}

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        for path, records in self.files.items():
            source = self.repo / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# placeholder\n", encoding="utf-8")
            mirror = self.repo / ".sideword" / path
            mirror.parent.mkdir(parents=True, exist_ok=True)
            sidedoc = write_sidedoc(records)
            mirror.with_suffix(".py.md").write_text(sidedoc, encoding="utf-8")
            mirror.with_suffix(".py.idx").write_text(
                write_index(path, records, sidedoc), encoding="utf-8")
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()


class TestIndex(CliTestCase):

    def test_prints_the_artifact_verbatim(self):
        status, out, _ = run("index", "src/cart.py")
        self.assertEqual(status, 0)
        on_disk = (self.repo / ".sideword/src/cart.py.idx").read_text(encoding="utf-8")
        self.assertEqual(out, on_disk)

    def test_header_counts_records_and_budgets_the_fetch(self):
        _, out, _ = run("index", "src/cart.py")
        header = out.splitlines()[0]
        self.assertTrue(header.startswith("sideword/1  src/cart.py  "), header)
        self.assertIn(" records  ~", header)

    def test_no_body_text_leaks_into_the_index(self):
        # FORMAT.md §4: the index says *that* an anchor is documented, never what it
        # says. A summary here would put every doc in every context.
        _, out, _ = run("index", "src/cart.py")
        for record in CART:
            self.assertNotIn(record.body.split("\n")[0], out)

    def test_parts_roll_up_onto_the_parent_row(self):
        _, out, _ = run("index", "src/cart.py")
        self.assertIn("+param:qty", out)
        self.assertIn("+returns", out)

    def test_empty_sidedoc_is_not_an_error(self):
        # 1,749 of the corpus's 15,126 converted paths document nothing at all.
        status, out, err = run("index", "src/empty.py")
        self.assertEqual(status, 0)
        self.assertEqual(err, "")
        self.assertEqual(out.strip(), "sideword/1  src/empty.py  0 records  ~5 tok")

    def test_unconverted_file_says_so(self):
        (self.repo / "src/other.py").write_text("x = 1\n", encoding="utf-8")
        status, _, err = run("index", "src/other.py")
        self.assertEqual(status, sideword_cli.EXIT_USAGE)
        self.assertIn("no index for src/other.py", err)
        self.assertNotIn("no such file", err)   # it exists; it was simply not converted

    def test_missing_file_says_that_instead(self):
        status, _, err = run("index", "src/nope.py")
        self.assertEqual(status, sideword_cli.EXIT_USAGE)
        self.assertIn("no such file", err)


class TestShow(CliTestCase):

    def test_prints_the_body_and_nothing_else(self):
        status, out, _ = run("show", "src/cart.py", "Cart")
        self.assertEqual(status, 0)
        self.assertEqual(out, "A shopping cart.\nNot thread-safe; one per session.\n")

    def test_one_anchor_does_not_pay_for_its_neighbours(self):
        # §1.2's claim, stated as a test: fetching `MAX_TOKENS` must not drag in the
        # other eight records of the file.
        _, out, _ = run("show", "src/cart.py", "MAX_TOKENS")
        self.assertEqual(out.strip(), "hard cap")
        self.assertNotIn("Shopping cart", out)

    def test_segment_anchor(self):
        _, out, _ = run("show", "src/cart.py", "Cart.add#assign:self.total")
        self.assertEqual(out.strip(), "Recompute eagerly.")

    def test_parent_carries_its_folded_parts(self):
        _, out, _ = run("show", "src/cart.py", "Cart.add")
        self.assertIn("Add an item to the cart.", out)
        self.assertIn("### #param:qty", out)
        self.assertIn("How many. Must be positive.", out)

    def test_a_part_is_fetchable_on_its_own(self):
        # The index advertises `+param:qty`, so that name has to work as an argument.
        status, out, _ = run("show", "src/cart.py", "Cart.add#param:qty")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "How many. Must be positive.")
        self.assertNotIn("Add an item", out)

    def test_every_indexed_anchor_is_fetchable(self):
        _, index, _ = run("index", "src/cart.py")
        anchors = []
        for line in index.splitlines()[1:]:
            anchor = line.split("  ")[0]
            anchors.append(anchor)
            for token in line.split():
                if token.startswith("+"):
                    anchors.append(anchor + "#" + token[1:])
        self.assertTrue(anchors)
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                self.assertEqual(run("show", "src/cart.py", anchor)[0], 0)

    def test_tied_records_all_come_back_labelled(self):
        status, out, _ = run("show", "src/cart.py", "Cart.add#if:qty < 0")
        self.assertEqual(status, 0)
        self.assertIn("{lead~1}", out)
        self.assertIn("{lead~2}", out)
        self.assertIn("first of a tie", out)
        self.assertIn("second of a tie", out)

    def test_kind_selects_one_of_a_tie(self):
        status, out, _ = run("show", "src/cart.py", "Cart.add#if:qty < 0",
                             "--kind", "lead~2")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "second of a tie")

    def test_untied_record_prints_no_heading(self):
        _, out, _ = run("show", "src/cart.py", "<module>")
        self.assertNotIn("##", out)

    def test_unknown_anchor_exits_non_zero_with_a_useful_message(self):
        status, out, err = run("show", "src/cart.py", "Cart.remove")
        self.assertEqual(status, sideword_cli.EXIT_NO_MATCH)
        self.assertEqual(out, "")
        self.assertIn("no record for Cart.remove in src/cart.py", err)
        self.assertIn("sideword index src/cart.py", err)

    def test_a_near_miss_gets_a_suggestion(self):
        _, _, err = run("show", "src/cart.py", "Cart.ad")
        self.assertIn("did you mean: Cart.add", err)

    def test_a_suggestion_never_carries_prose(self):
        _, _, err = run("show", "src/cart.py", "Cart.ad")
        self.assertNotIn("Add an item", err)

    def test_wrong_kind_names_the_kinds_that_exist(self):
        status, _, err = run("show", "src/cart.py", "Cart", "--kind", "lead")
        self.assertEqual(status, sideword_cli.EXIT_NO_MATCH)
        self.assertIn("documented as: doc", err)

    def test_empty_sidedoc_does_not_crash(self):
        status, out, err = run("show", "src/empty.py", "anything")
        self.assertEqual(status, sideword_cli.EXIT_NO_MATCH)
        self.assertEqual(out, "")
        self.assertIn("0 records documented", err)


class TestSearch(CliTestCase):

    def test_locates_a_record_and_shows_the_matched_line_only(self):
        status, out, _ = run("search", "thread-safe")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(),
                         "src/cart.py\tCart {doc}\tNot thread-safe; one per session.")
        self.assertNotIn("A shopping cart.", out)   # the record's other line

    def test_reports_the_anchor_show_would_take(self):
        _, out, _ = run("search", "Recompute")
        path, anchor, _ = out.strip().split("\t")
        self.assertEqual(path, "src/cart.py")
        self.assertEqual(run("show", path, anchor.split(" {")[0])[0], 0)

    def test_ignore_case(self):
        self.assertEqual(run("search", "THREAD-SAFE")[0], sideword_cli.EXIT_NO_MATCH)
        self.assertEqual(run("search", "THREAD-SAFE", "-i")[0], 0)

    def test_path_filter(self):
        self.assertEqual(run("search", "cart", "-i", "src/empty.py")[0],
                         sideword_cli.EXIT_NO_MATCH)
        self.assertEqual(run("search", "cart", "-i", "src")[0], 0)

    def test_no_match_exits_one_and_prints_nothing(self):
        status, out, err = run("search", "nowhere-in-this-repo")
        self.assertEqual(status, sideword_cli.EXIT_NO_MATCH)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_bad_pattern_is_a_usage_error(self):
        status, _, err = run("search", "cart(")
        self.assertEqual(status, sideword_cli.EXIT_USAGE)
        self.assertIn("bad pattern", err)


#: Raw artifacts copied byte-for-byte (bodies trimmed) from the converted corpus —
#: shapes the synthetic fixtures above cannot produce. Provenance, per record:
#:   Flask.debug~1        pallets__flask-5014-sw  src/flask/app.py — a tie the
#:                        *resolver* put on the anchor path itself, not a `{kind~n}`
#:   get_sign             astropy__astropy-14365-sw  astropy/coordinates/calculation.py
#:                        — a record whose entire body is one space (25 such anchors
#:                        across the 12-tree EST-166 sample)
#:   teme_to_itrs_mat     astropy__astropy-14365-sw  astropy/coordinates/builtin_frames/
#:                        intermediate_rotation_transforms.py — a body line starting
#:                        with `#`, stored escaped as `\#`
#:   Flask.run#if:...     pallets__flask-5014-sw  src/flask/app.py — a discriminator
#:                        carrying spaces and double quotes, overflowing the anchor column
#:   ConfigObj._parse#... astropy__astropy-14365-sw  astropy/extern/configobj/configobj.py
#:                        — a deep segment path routed through `/else/`
REAL_MD = '''---
style: sphinx
---

## Flask.debug~1 {doc}
Whether debug mode is enabled.

## get_sign {doc}
 

## teme_to_itrs_mat {lead}
\\# first define helper functions

## Flask.run#if:os.environ.get("FLASK_RUN_FROM_CLI") == "true" {lead}
Ignore this call so that it doesn't start another server if
the 'flask run' command is used.

## ConfigObj._parse#while:cur_index < maxline/if:mat is None/else/assign:key {lead}
we have a value
'''

REAL_IDX = '''sideword/1  src/app.py  5 records  ~90 tok
Flask.debug~1                                             doc   1L
get_sign                                                  doc   1L
teme_to_itrs_mat                                          lead  1L
Flask.run#if:os.environ.get("FLASK_RUN_FROM_CLI") == "true" lead  1L
ConfigObj._parse#while:cur_index < maxline/if:mat is None/else/assign:key lead  1L
'''


class TestRealCorpusShapes(unittest.TestCase):
    """The EST-166 corpus sweep (12 tags, 4,664 files, 78,864 anchors) found no verb
    failures — these tests pin the real anchor shapes that sweep proved and the
    synthetic `CART` fixture does not reach, from literal corpus bytes."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        repo = Path(self._tmp.name)
        (repo / "src").mkdir(parents=True)
        (repo / "src/app.py").write_text("# placeholder\n", encoding="utf-8")
        mirror = repo / ".sideword" / "src"
        mirror.mkdir(parents=True)
        (mirror / "app.py.md").write_text(REAL_MD, encoding="utf-8")
        (mirror / "app.py.idx").write_text(REAL_IDX, encoding="utf-8")
        os.chdir(repo)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_anchor_level_tie_suffix_is_fetched_verbatim(self):
        # `~1` here is part of the anchor path (resolver occurrence numbering, §1.6),
        # not a `--kind` tie; `show` must match it verbatim, never strip it.
        status, out, _ = run("show", "src/app.py", "Flask.debug~1")
        self.assertEqual(status, 0)
        self.assertEqual(out, "Whether debug mode is enabled.\n")

    def test_the_untied_spelling_misses_but_suggests_the_tied_one(self):
        status, _, err = run("show", "src/app.py", "Flask.debug")
        self.assertEqual(status, sideword_cli.EXIT_NO_MATCH)
        self.assertIn("did you mean: Flask.debug~1", err)

    def test_whitespace_only_body_is_returned_not_reported_missing(self):
        # The record exists and the index advertises it as 1L; empty prose is a
        # corpus fact the verb must relay, not an error it may invent.
        status, out, err = run("show", "src/app.py", "get_sign")
        self.assertEqual(status, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, " \n")

    def test_escaped_hash_line_comes_back_unescaped(self):
        status, out, _ = run("show", "src/app.py", "teme_to_itrs_mat")
        self.assertEqual(status, 0)
        self.assertEqual(out, "# first define helper functions\n")

    def test_search_sees_through_the_escaping(self):
        status, out, _ = run("search", "^# first define")
        self.assertEqual(status, 0)
        self.assertIn("teme_to_itrs_mat {lead}", out)
        self.assertNotIn("\\#", out)

    def test_quoted_spaced_discriminator_is_fetchable(self):
        anchor = 'Flask.run#if:os.environ.get("FLASK_RUN_FROM_CLI") == "true"'
        status, out, _ = run("show", "src/app.py", anchor)
        self.assertEqual(status, 0)
        self.assertEqual(out, "Ignore this call so that it doesn't start another "
                              "server if\nthe 'flask run' command is used.\n")

    def test_deep_else_segment_path_is_fetchable(self):
        anchor = ("ConfigObj._parse#while:cur_index < maxline"
                  "/if:mat is None/else/assign:key")
        status, out, _ = run("show", "src/app.py", anchor)
        self.assertEqual(status, 0)
        self.assertEqual(out, "we have a value\n")

    def test_every_row_of_the_real_index_is_fetchable(self):
        # Parse the rows the way the EST-166 sweep did: anchor text up to the
        # padded kind/line-count tail, spaces inside the anchor preserved.
        row = re.compile(r"^(.+?) +(?:doc|lead|trail|post|todo)(?:~\d+)? +\d+L$")
        anchors = [m.group(1).rstrip() for m in
                   (row.match(line) for line in REAL_IDX.splitlines()[1:]) if m]
        self.assertEqual(len(anchors), 5)
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                status, out, _ = run("show", "src/app.py", anchor)
                self.assertEqual(status, 0)
                self.assertTrue(out)


class TestPaths(CliTestCase):

    def test_runs_from_a_subdirectory(self):
        os.chdir(self.repo / "src")
        status, out, _ = run("index", "cart.py")
        self.assertEqual(status, 0)
        self.assertIn("src/cart.py", out.splitlines()[0])

    def test_accepts_the_mirror_path_an_agent_may_have_seen(self):
        for name in (".sideword/src/cart.py.md", ".sideword/src/cart.py.idx",
                     str(self.repo / "src/cart.py")):
            with self.subTest(name=name):
                self.assertEqual(run("index", name)[0], 0)

    def test_refuses_a_path_outside_the_repository(self):
        status, _, err = run("index", "../elsewhere/cart.py")
        self.assertEqual(status, sideword_cli.EXIT_USAGE)
        self.assertIn("outside the repository", err)

    def test_unconverted_repository_says_so_rather_than_guessing(self):
        with tempfile.TemporaryDirectory() as plain:
            os.chdir(plain)
            status, _, err = run("index", "cart.py")
            self.assertEqual(status, sideword_cli.EXIT_USAGE)
            self.assertIn("not converted", err)

    def test_no_verb_is_a_usage_error(self):
        status, out, err = run()
        self.assertEqual(status, sideword_cli.EXIT_USAGE)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
