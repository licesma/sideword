"""Strip every CPython 3.14 stdlib module in memory; assert astcheck.equal and idempotence.

Corpus: every .py under sysconfig stdlib, recursively, excluding test/, tests/, site-packages,
lib2to3, __pycache__.  Prints a summary line at the end.

Run: .venv/bin/python -m unittest harness.tests.test_stdlib_corpus
Set SIDEWORD_CORPUS_VERBOSE=1 to print per-failure details.
"""

import os
import sys
import sysconfig
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import astcheck, directives, strip  # noqa: E402

EXCLUDE_DIRS = {"test", "tests", "site-packages", "__pycache__", "lib2to3"}


def corpus_files():
    root = sysconfig.get_paths()["stdlib"]
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return out


class TestStdlibCorpus(unittest.TestCase):
    def test_corpus(self):
        d = directives.load()
        files = corpus_files()
        self.assertGreater(len(files), 500, "stdlib corpus not found")
        agg = {"comments_removed": 0, "docstrings_removed": 0, "doctest_docstrings_kept": 0,
               "directives_kept": 0, "stray_strings_kept": 0, "unresolved": 0,
               "bytes_before": 0, "bytes_after": 0, "lines_before": 0, "lines_after": 0}
        failures = []
        parse_errors = []
        not_idempotent = []
        t0 = time.perf_counter()
        strip_time = 0.0
        for path in files:
            src = Path(path).read_bytes()
            t1 = time.perf_counter()
            out, recs = strip.strip_source(src, d)
            strip_time += time.perf_counter() - t1
            self.assertEqual(recs[-1]["kind"], "stats", path)
            if recs[0].get("kind") == "parse_error":
                parse_errors.append((path, recs[0]["error"]))
                self.assertEqual(out, src, path)
                continue
            for k in agg:
                agg[k] += recs[-1][k]
            ok, detail = astcheck.equal(src, out, d)
            if not ok:
                failures.append((path, detail))
            out2, _ = strip.strip_source(out, d)
            if out2 != out:
                not_idempotent.append(path)
        wall = time.perf_counter() - t0
        summary = (f"\nstdlib corpus: files={len(files)} pass={len(files) - len(failures) - len(parse_errors)} "
                   f"fail={len(failures)} parse_errors={len(parse_errors)} "
                   f"not_idempotent={len(not_idempotent)}\n"
                   f"  comments_removed={agg['comments_removed']} docstrings_removed={agg['docstrings_removed']} "
                   f"doctest_kept={agg['doctest_docstrings_kept']} directives_kept={agg['directives_kept']} "
                   f"stray_kept={agg['stray_strings_kept']} unresolved={agg['unresolved']}\n"
                   f"  bytes {agg['bytes_before']} -> {agg['bytes_after']}, "
                   f"lines {agg['lines_before']} -> {agg['lines_after']}\n"
                   f"  strip time {strip_time:.2f}s, wall incl. astcheck+idempotence {wall:.2f}s")
        print(summary, file=sys.stderr)
        if os.environ.get("SIDEWORD_CORPUS_VERBOSE"):
            for p, detail in failures:
                print(f"FAIL {p}\n{detail}", file=sys.stderr)
            for p, e in parse_errors:
                print(f"PARSE_ERROR {p}: {e}", file=sys.stderr)
        self.assertEqual(failures, [], "\n".join(f"{p}: {det[:400]}" for p, det in failures[:5]))
        self.assertEqual(not_idempotent, [])
        self.assertEqual(parse_errors, [])


if __name__ == "__main__":
    unittest.main()
