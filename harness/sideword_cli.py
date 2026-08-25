#!/usr/bin/env python3
"""`sideword` — the retrieval surface for arm 2 of the experiment.

A converted repository keeps its prose in a mirror tree that is deliberately outside
glob range (`FORMAT.md` §0): `.sideword/<path>.py.idx` says *which* anchors are
documented, `.sideword/<path>.py.md` holds the prose. An ordinary file read of the
`.md` pulls every record in the file, which is the thing §1.2 says retrieval should
not cost — "an agent reasoning about `qty` pays for one line, not thirty". This
command is what makes that sentence true in practice.

Three verbs, and the count is the point: every verb arm 2 has and arms 1/3 do not is
something the experiment has to explain.

    index   the file's `.idx`, verbatim — the artifact, not a re-derivation
    show    one anchor's record, nothing else
    search  locate records by pattern; one matched line each, never a body

`search` exists for parity, not convenience. In arm 1 the prose is in the source, so
`grep -r "thread-safe" src/` finds it; in arm 2 that grep cannot match anything and
`.sideword/` is out of glob range. Without `search`, arm 2 would be missing a
capability arm 1 has, and the measurement would confound "retrieval on demand" with
"documentation became ungreppable".

Deliberately absent: a whole-file dump (that is the weaker claim the split exists to
avoid) and a repo-wide listing of documented files (it invites doc-first exploration,
which arms 1 and 3 cannot do).

Parsing is `harness/sidedoc.py`'s job; this file only locates, selects and prints.
It is kept import-light and free of 3.10+ syntax so it can be dropped into a
SWE-bench task container next to `sidedoc.py` and run on that image's interpreter.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys

try:                                   # installed as a package
    from harness.sidedoc import Record, parse_sidedoc, part_of
except ImportError:                    # dropped in a directory next to sidedoc.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sidedoc import Record, parse_sidedoc, part_of  # type: ignore

MIRROR = ".sideword"

EXIT_OK = 0
EXIT_NO_MATCH = 1                      # grep's convention: the query was valid, nothing matched
EXIT_USAGE = 2                         # no mirror, no such file, bad arguments


class CliError(Exception):
    """A message for the user and the status to leave with."""

    def __init__(self, message: str, status: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.status = status


# ---- locating ---------------------------------------------------------------------------

def find_root(start: str) -> str:
    """The nearest ancestor of `start` holding a `.sideword/` mirror.

    Walking up rather than demanding the repository root means the command behaves the
    same wherever an agent happens to have `cd`-ed to.
    """
    # `realpath`, not `abspath`: a container's working directory is routinely reached
    # through a symlink, and comparing a symlinked path against a resolved one makes
    # a file inside the repository look like a file outside it.
    here = os.path.realpath(start)
    while True:
        if os.path.isdir(os.path.join(here, MIRROR)):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise CliError(
                "no %s/ directory found from %s — this repository is not converted"
                % (MIRROR, os.path.realpath(start)))
        here = parent


def normalize(root: str, path: str) -> str:
    """Repo-relative source path, from anything that names the file.

    An agent that has just read `.sideword/src/cart.py.md` will reach for that name, and
    refusing it teaches nothing; the mirror prefix and the artifact suffix are stripped
    rather than rejected.
    """
    absolute = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    rel = os.path.relpath(os.path.realpath(absolute), root).replace(os.sep, "/")
    if rel == ".." or rel.startswith("../"):
        raise CliError("%s is outside the repository at %s" % (path, root))
    if rel.startswith(MIRROR + "/"):
        rel = rel[len(MIRROR) + 1:]
    for suffix in (".idx", ".md"):
        if rel.endswith(suffix):
            rel = rel[:-len(suffix)]
    return rel


def artifact(root: str, rel: str, suffix: str) -> str:
    return os.path.join(root, MIRROR, rel.replace("/", os.sep) + suffix)


#: What to call each artifact when it is missing. `.idx` and `.md` are the file
#: names; an agent reading the error should not have to know which is which.
ARTIFACT_NAMES = {".idx": "index", ".md": "sidedoc"}


def read_artifact(root: str, rel: str, suffix: str) -> str:
    target = artifact(root, rel, suffix)
    if not os.path.isfile(target):
        source = os.path.join(root, rel.replace("/", os.sep))
        # Two different failures wear the same missing file: a path that does not
        # exist, and a real source file that was never converted (test files are
        # left alone). Saying which one saves a round trip.
        hint = ("" if os.path.exists(source)
                else " (no such file in the repository either)")
        raise CliError("no %s for %s%s"
                       % (ARTIFACT_NAMES.get(suffix, suffix), rel, hint))
    with open(target, encoding="utf-8") as handle:
        return handle.read()


# ---- selecting --------------------------------------------------------------------------

def candidates(records):
    """Every anchor a `show` could name: top-level records and folded parts (§5).

    A part is reachable both on its own (`Cart.add#param:qty`, as the index's `+param:qty`
    rollup advertises it) and as part of its parent's record, so it appears in both.
    """
    out = []
    for rec in records:
        out.append(rec.anchor)
        for part in rec.parts:
            out.append(rec.anchor + part.anchor)
    return out


def select(records, anchor: str, kind=None):
    """Records matching `anchor`, filtered by slot if `kind` is given.

    Several records can share an anchor — ties (§3) are numbered `{lead~1}`, `{lead~2}`
    and the index shows them as identical rows in the anchor column. Returning all of
    them, rather than the first, is the only reading that does not silently drop prose.
    """
    hits = [r for r in records if r.anchor == anchor]
    if not hits:
        split = part_of(anchor)        # `Cart.add#param:qty` -> ("Cart.add", "#param:qty")
        if split:
            for rec in records:
                if rec.anchor != split[0]:
                    continue
                hits.extend(Record(anchor, None, p.body)
                            for p in rec.parts if p.anchor == split[1])
    if kind is not None:
        hits = [r for r in hits if r.slot == kind]
    return hits


def render(rec, heading: bool) -> str:
    """One record's text: the body, plus the parts folded under it (§5)."""
    buf = []
    if heading:
        buf.append("## %s {%s}" % (rec.anchor, rec.slot))
    buf.append(rec.body)
    for part in rec.parts:
        buf.append("")
        buf.append("### " + part.anchor)
        buf.append(part.body)
    return "\n".join(buf)


# ---- verbs ------------------------------------------------------------------------------

def cmd_index(args) -> int:
    root = find_root(os.getcwd())
    rel = normalize(root, args.path)
    sys.stdout.write(read_artifact(root, rel, ".idx"))
    return EXIT_OK


def cmd_show(args) -> int:
    root = find_root(os.getcwd())
    rel = normalize(root, args.path)
    _, records = parse_sidedoc(read_artifact(root, rel, ".md"))
    hits = select(records, args.anchor, args.kind)
    if not hits:
        raise CliError(not_found_message(rel, args.anchor, args.kind, records),
                       EXIT_NO_MATCH)
    # A heading only when one is needed to tell two records apart: an unambiguous
    # anchor should cost exactly its prose and not a line of ceremony.
    heading = len(hits) > 1
    print("\n\n".join(render(rec, heading) for rec in hits))
    return EXIT_OK


def not_found_message(rel: str, anchor: str, kind, records) -> str:
    known = candidates(records)
    if kind is not None and any(r.anchor == anchor for r in records):
        slots = sorted(set(r.slot for r in records if r.anchor == anchor))
        return ("no record %s {%s} in %s — that anchor is documented as: %s"
                % (anchor, kind, rel, ", ".join(slots)))
    lines = ["no record for %s in %s" % (anchor, rel)]
    # Anchors are index content and already free to read, so a suggestion leaks no
    # prose; a mistyped discriminator is otherwise an expensive thing to recover from.
    near = difflib.get_close_matches(anchor, known, n=3, cutoff=0.6)
    if near:
        lines.append("did you mean: " + ", ".join(near))
    lines.append("%d record%s documented; run: sideword index %s"
                 % (len(known), "" if len(known) == 1 else "s", rel))
    return "\n".join(lines)


def sidedoc_paths(root: str, prefixes):
    """Every sidedoc under the mirror, repo-relative, optionally filtered by prefix."""
    base = os.path.join(root, MIRROR)
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")[:-len(".md")]
            if prefixes and not any(rel == p or rel.startswith(p.rstrip("/") + "/")
                                    for p in prefixes):
                continue
            found.append(rel)
    return found


def cmd_search(args) -> int:
    root = find_root(os.getcwd())
    prefixes = [normalize(root, p) for p in args.path]
    try:
        pattern = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
    except re.error as exc:
        raise CliError("bad pattern %r: %s" % (args.pattern, exc))
    matched = False
    for rel in sidedoc_paths(root, prefixes):
        with open(artifact(root, rel, ".md"), encoding="utf-8") as handle:
            _, records = parse_sidedoc(handle.read())
        for rec in records:
            for owner, body in [(rec, rec.body)] + [(rec, p.body) for p in rec.parts]:
                for line in body.split("\n"):
                    if pattern.search(line):
                        # Location plus the one line that matched — grep's contract.
                        # Anything more and `search` becomes the whole-file dump that
                        # `show` exists to avoid.
                        print("%s\t%s {%s}\t%s" % (rel, owner.anchor, owner.slot,
                                                   line.strip()))
                        matched = True
    return EXIT_OK if matched else EXIT_NO_MATCH


# ---- entry point ------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="sideword",
        description="Read the documentation stored beside this repository's source.")
    subs = parser.add_subparsers(dest="verb")

    p_index = subs.add_parser(
        "index", help="list which anchors in a file are documented")
    p_index.add_argument("path", help="source file, repository-relative")
    p_index.set_defaults(func=cmd_index)

    p_show = subs.add_parser("show", help="print one anchor's documentation")
    p_show.add_argument("path", help="source file, repository-relative")
    p_show.add_argument("anchor", help="anchor as it appears in the index")
    p_show.add_argument("--kind", default=None,
                        help="disambiguate an anchor with several records, "
                             "e.g. doc, lead, lead~2")
    p_show.set_defaults(func=cmd_show)

    p_search = subs.add_parser(
        "search", help="find records whose text matches a regular expression")
    p_search.add_argument("pattern", help="Python regular expression")
    p_search.add_argument("path", nargs="*", help="limit to these files or directories")
    p_search.add_argument("-i", "--ignore-case", action="store_true")
    p_search.set_defaults(func=cmd_search)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        return args.func(args)
    except CliError as exc:
        sys.stderr.write("sideword: %s\n" % exc)
        return exc.status
    except BrokenPipeError:            # `sideword show ... | head`
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
