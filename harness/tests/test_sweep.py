"""Tests for `harness/sweep.py`.

Nothing here starts a container or calls a model: `evaluate.py`'s entry point is
stood in for by a fake that writes whatever record the test wants to find. What is
worth testing is the sweep's own decisions — which runs exist, in what order, which
are skipped, and when it stops — because each of those, wrong, would either bias the
comparison or spend the account on runs that cannot count.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from harness import sweep

ADMISSION = {
    "usable_instances": ["a__a-1", "b__b-2", "c__c-3", "d__d-4", "e__e-5"],
    "excluded_instances": [{"instance_id": "x__x-9", "arms_failed": ["sw", "nc"]}],
}


def _record(instance: str, arm: str, model: str, *, resolved=True, cost=0.5,
            tokens=None, files=10, sideword_files=0, sideword_calls=0, errors=None,
            scored=True) -> dict:
    tokens = tokens or {"input": 10, "output": 100, "cache_read": 1000, "cache_creation": 200}
    rec = {
        "schema": "sideword-eval-1", "instance_id": instance, "arm": arm, "model": model,
        "source": "agent", "errors": errors or [], "wall_s": 60.0,
        "agent": {"n_calls": 5, "cost_usd": cost, "tokens": tokens,
                  "tokens_billed": tokens["input"] + tokens["cache_creation"] + tokens["output"]},
        "files_read_count": files + sideword_files,
        "files_read_counts": {"source": files, "sideword": sideword_files},
    }
    if arm == "sw":
        rec["sideword_call_count"] = sideword_calls
    if scored:
        rec["scoring"] = {"resolved": resolved}
    return rec


def _write(root: Path, rec: dict) -> Path:
    path = sweep.record_file(root, rec)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


class TestSelection(unittest.TestCase):
    def test_default_is_every_usable_instance_and_nothing_else(self):
        self.assertEqual(sweep.select_instances(ADMISSION), ADMISSION["usable_instances"])

    def test_filter_keeps_admission_order(self):
        self.assertEqual(sweep.select_instances(ADMISSION, ["c__c-3", "a__a-1"]),
                         ["a__a-1", "c__c-3"])

    def test_an_excluded_instance_is_refused_not_dropped(self):
        with self.assertRaises(SystemExit) as ctx:
            sweep.select_instances(ADMISSION, ["a__a-1", "x__x-9"])
        self.assertIn("excluded by admission", str(ctx.exception))

    def test_an_unknown_instance_is_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            sweep.select_instances(ADMISSION, ["nope__nope-0"])
        self.assertIn("unknown", str(ctx.exception))

    def test_arms_default_to_all_three_in_canonical_order(self):
        self.assertEqual(sweep.select_arms(None), ["orig", "sw", "nc"])
        self.assertEqual(sweep.select_arms(["nc", "orig"]), ["orig", "nc"])
        with self.assertRaises(SystemExit):
            sweep.select_arms(["sideword"])

    def test_default_models_are_the_weak_and_strong_ends(self):
        self.assertEqual(sweep.DEFAULT_MODELS, ["claude-opus-4-1", "claude-opus-5"])


class TestOrdering(unittest.TestCase):
    ARMS = ["orig", "sw", "nc"]
    MODELS = ["m1", "m2"]

    def test_every_run_appears_exactly_once(self):
        items = sweep.order(ADMISSION["usable_instances"], self.ARMS, self.MODELS, seed=1)
        keys = {(i["instance_id"], i["arm"], i["model"]) for i in items}
        self.assertEqual(len(items), 5 * 3 * 2)
        self.assertEqual(len(keys), len(items))

    def test_all_arms_of_an_instance_are_adjacent(self):
        """Never all of arm 1 then all of arm 2: an instance's runs form one block."""
        items = sweep.order(ADMISSION["usable_instances"], self.ARMS, self.MODELS, seed=7)
        seen: list[str] = []
        for item in items:
            if not seen or seen[-1] != item["instance_id"]:
                seen.append(item["instance_id"])
        self.assertEqual(len(seen), len(set(seen)), "an instance's block was split: %s" % seen)
        # and within an instance, one model's three arms are contiguous too
        for k in range(0, len(items), 3):
            block = items[k:k + 3]
            self.assertEqual(len({(b["instance_id"], b["model"]) for b in block}), 1)
            self.assertEqual(sorted(b["arm"] for b in block), sorted(self.ARMS))

    def test_the_seed_fixes_the_order_and_shuffles_it(self):
        a = sweep.order(ADMISSION["usable_instances"], self.ARMS, self.MODELS, seed=2026)
        b = sweep.order(ADMISSION["usable_instances"], self.ARMS, self.MODELS, seed=2026)
        c = sweep.order(ADMISSION["usable_instances"], self.ARMS, self.MODELS, seed=2027)
        self.assertEqual(a, b)
        instances = lambda items: [i["instance_id"] for i in items[::6]]  # noqa: E731
        self.assertNotEqual(instances(a), ADMISSION["usable_instances"])
        self.assertNotEqual(instances(a), instances(c))

    def test_the_arm_that_goes_first_rotates(self):
        items = sweep.order(ADMISSION["usable_instances"], self.ARMS, ["m"], seed=3)
        firsts = [items[k]["arm"] for k in range(0, len(items), 3)]
        self.assertEqual(set(firsts), set(self.ARMS))


class TestResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_complete_record_is_done_and_skipped(self):
        _write(self.root, _record("a__a-1", "sw", "m"))
        items = sweep.plan(["a__a-1"], ["orig", "sw"], ["m"], seed=1, root=self.root)
        by_arm = {i["arm"]: i for i in items}
        self.assertEqual(by_arm["sw"]["state"], sweep.DONE)
        self.assertEqual(by_arm["orig"]["state"], sweep.TODO)
        self.assertEqual(by_arm["orig"]["why"], "missing")

        launched = []
        sweep.run_sweep(items, jobs=1, root=self.root, launch=lambda i: launched.append(i) or "ok",
                        logger=lambda *_: None)
        self.assertEqual([i["arm"] for i in launched], ["orig"])

    def test_a_blocked_record_is_rerun(self):
        """`evaluate.py` writes a record after an allowance block; it must not count."""
        _write(self.root, _record("a__a-1", "nc", "m",
                                  errors=[{"kind": "allowance-exhausted", "detail": "x"}]))
        state, why = sweep.record_state(sweep.record_file(
            self.root, {"instance_id": "a__a-1", "arm": "nc", "model": "m"}))
        self.assertEqual(state, sweep.TODO)
        self.assertIn("blocked", why)

    def test_unparsable_and_unscored_records_are_rerun(self):
        item = {"instance_id": "a__a-1", "arm": "orig", "model": "m"}
        path = sweep.record_file(self.root, item)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(sweep.record_state(path), (sweep.TODO, "unparsable"))
        _write(self.root, _record("a__a-1", "orig", "m", scored=False))
        self.assertEqual(sweep.record_state(path)[1], "never scored")

    def test_a_rerun_sets_the_old_record_aside_and_the_report_ignores_it(self):
        old = _write(self.root, _record("a__a-1", "sw", "m",
                                        errors=[{"kind": "allowance-exhausted", "detail": ""}]))
        moved = sweep.set_aside(old)
        self.assertFalse(old.exists())
        self.assertTrue(moved.name.startswith("a__a-1.stale-"))
        self.assertEqual(sweep.load_records(self.root), [])

    def test_launch_run_drives_evaluate_and_classifies_by_the_record(self):
        """The subprocess is `evaluate.py`'s entry point; here it is a fake that writes
        the record. `--out` must point at the sweep's root and the account must be
        in the environment, or the record would land elsewhere and bill elsewhere."""
        item = {"instance_id": "a__a-1", "arm": "sw", "model": "m"}
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            out = Path(cmd[cmd.index("--out") + 1])
            _write(out, _record("a__a-1", "sw", "m"))
            kwargs["stdout"].write("resolved=True\n")
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(sweep.subprocess, "run", fake_run):
            outcome = sweep.launch_run(item, root=self.root, extra=["--effort", "low"],
                                       env={"SIDEWORD_CLAUDE_CONFIG_DIR": "/x"},
                                       logger=lambda *_: None)
        self.assertEqual(outcome, "ok")
        cmd, kwargs = calls[0]
        self.assertEqual(cmd[1:3], ["-m", "harness.evaluate"])
        self.assertEqual(cmd[cmd.index("--instance") + 1], "a__a-1")
        self.assertEqual(cmd[cmd.index("--arm") + 1], "sw")
        self.assertEqual(cmd[cmd.index("--model") + 1], "m")
        self.assertEqual(cmd[-2:], ["--effort", "low"])
        self.assertEqual(kwargs["env"]["SIDEWORD_CLAUDE_CONFIG_DIR"], "/x")
        self.assertTrue((self.root / "m" / "sw" / "a__a-1.run.log").exists())

    def test_launch_run_skips_a_record_that_appeared_meanwhile(self):
        item = {"instance_id": "a__a-1", "arm": "sw", "model": "m"}
        _write(self.root, _record("a__a-1", "sw", "m"))
        with mock.patch.object(sweep.subprocess, "run",
                               side_effect=AssertionError("must not launch")):
            self.assertEqual(sweep.launch_run(item, root=self.root, extra=[], env={}), "skip")


class TestOutcome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_record_decides_when_there_is_one(self):
        path = _write(self.root, _record("a__a-1", "orig", "m"))
        self.assertEqual(sweep.outcome_of(path, "", 0), "ok")
        path = _write(self.root, _record("a__a-1", "sw", "m",
                                         errors=[{"kind": "allowance-exhausted"}]))
        # exit 0, as evaluate.py actually does after a block
        self.assertEqual(sweep.outcome_of(path, "", 0), "blocked")

    def test_the_output_decides_when_there_is_none(self):
        path = self.root / "m" / "nc" / "a__a-1.json"
        self.assertEqual(sweep.outcome_of(path, "Traceback ... ContainerError", 1), "failed")
        self.assertEqual(sweep.outcome_of(path, "error: You have hit your limit", 1), "blocked")
        self.assertEqual(sweep.outcome_of(path, '{"error":"rate_limited"}', 1), "blocked")


class TestStopping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.items = sweep.plan(ADMISSION["usable_instances"], ["orig", "sw", "nc"], ["m"],
                                seed=1, root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _launch(self, outcomes, *, write=False):
        launched = []

        def launch(item):
            launched.append(item)
            outcome = outcomes[len(launched) - 1] if len(launched) <= len(outcomes) else "ok"
            if write:
                _write(self.root, _record(item["instance_id"], item["arm"], item["model"]))
            return outcome
        return launch, launched

    def test_a_hard_block_stops_launching(self):
        launch, launched = self._launch(["ok", "blocked"])
        result = sweep.run_sweep(self.items, jobs=1, root=self.root, launch=launch,
                                 logger=lambda *_: None)
        self.assertEqual(len(launched), 2)
        self.assertEqual(result["stopped"], "blocked")
        self.assertEqual(result["counts"], {"ok": 1, "blocked": 1})

    def test_a_hard_block_stops_launching_with_workers(self):
        """With `jobs` workers, the block can cost at most the runs in flight."""
        launch, launched = self._launch(["blocked"])
        sweep.run_sweep(self.items, jobs=2, root=self.root, launch=launch,
                        logger=lambda *_: None)
        self.assertLessEqual(len(launched), 2)

    def test_execution_follows_the_plan_order(self):
        launch, launched = self._launch([])
        sweep.run_sweep(self.items, jobs=1, root=self.root, launch=launch,
                        logger=lambda *_: None)
        self.assertEqual(launched, self.items)

    def test_max_runs(self):
        launch, launched = self._launch([])
        result = sweep.run_sweep(self.items, jobs=2, root=self.root, max_runs=4, launch=launch,
                                 logger=lambda *_: None)
        self.assertEqual(len(launched), 4)
        self.assertEqual(result["stopped"], "max-runs")
        launch, launched = self._launch([])
        result = sweep.run_sweep(self.items, jobs=2, root=self.root, max_runs=0, launch=launch,
                                 logger=lambda *_: None)
        self.assertEqual(launched, [])

    def test_max_cost_counts_what_the_records_say(self):
        launch, launched = self._launch([], write=True)      # each record costs $0.5
        result = sweep.run_sweep(self.items, jobs=1, root=self.root, max_cost=1.0, launch=launch,
                                 logger=lambda *_: None)
        self.assertEqual(len(launched), 2)
        self.assertEqual(result["stopped"], "max-cost")

    def test_the_same_instance_and_arm_never_run_at_once(self):
        """Two models share `evaluate.py`'s scoring container name for an
        (instance, arm); the sweep keeps them apart even at high `--jobs`."""
        import threading
        items = sweep.plan(["a__a-1"], ["orig"], ["m1", "m2", "m3"], seed=1, root=self.root)
        active: set = set()
        overlap = []
        lock = threading.Lock()

        def launch(item):
            key = (item["instance_id"], item["arm"])
            with lock:
                if key in active:
                    overlap.append(key)
                active.add(key)
            threading.Event().wait(0.05)
            with lock:
                active.discard(key)
            return "ok"
        sweep.run_sweep(items, jobs=3, root=self.root, launch=launch, logger=lambda *_: None)
        self.assertEqual(overlap, [])


class TestReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        big = {"input": 20, "output": 400, "cache_read": 5000, "cache_creation": 800}
        for arm, tok in (("orig", big), ("sw", None), ("nc", None)):
            _write(self.root, _record("a__a-1", arm, "m", tokens=tok, files=30,
                                      sideword_files=4 if arm == "sw" else 0,
                                      sideword_calls=6 if arm == "sw" else 0))
        _write(self.root, _record("b__b-2", "orig", "m", resolved=False))   # unpaired
        _write(self.root, _record("x__x-9", "orig", "m"))                   # excluded
        _write(self.root, _record("a__a-1", "orig", "m", scored=False)
               | {"instance_id": "c__c-3"})                                # incomplete

    def tearDown(self):
        self.tmp.cleanup()

    def test_summary_and_paired_view(self):
        data = sweep.report(self.root, admission=ADMISSION)
        self.assertEqual(data["records"], 4)
        self.assertEqual(data["stray_records"], ["m/orig/x__x-9"])
        arms = data["per_model"]["m"]["arms"]
        self.assertEqual(arms["orig"]["n"], 2)
        self.assertEqual(arms["orig"]["resolved"], 1)
        self.assertEqual(arms["orig"]["resolve_rate"], 0.5)
        self.assertEqual(arms["orig"]["tokens"]["billed"]["median"], (1220 + 310) / 2)
        self.assertEqual(arms["sw"]["sideword_files_read"]["mean"], 4.0)
        self.assertEqual(arms["sw"]["sideword_calls"]["mean"], 6.0)
        self.assertNotIn("sideword_calls", arms["nc"])
        self.assertEqual(arms["orig"]["files_read"]["mean"], 20.0)
        self.assertEqual(data["per_model"]["m"]["paired_n"], 1)
        row = data["per_model"]["m"]["paired"][0]
        self.assertEqual(row["instance_id"], "a__a-1")
        self.assertEqual(row["arms"]["orig"]["billed"], 1220)
        self.assertEqual(row["arms"]["sw"]["billed"], 310)
        self.assertEqual(row["arms"]["sw"]["sideword_calls"], 6)

    def test_markdown_states_n_and_what_it_can_resolve(self):
        md = sweep.render_markdown(sweep.report(self.root, admission=ADMISSION))
        self.assertIn("m: n = 1", md.split("\n## ")[0])
        self.assertIn("resolve rate cannot", md)
        self.assertIn("token", md)
        self.assertIn("| a__a-1 | ✓ ✓ ✓ |", md)
        json_path, md_path = sweep.write_report(sweep.report(self.root, admission=ADMISSION),
                                                self.root)
        self.assertTrue(json_path.exists() and md_path.exists())

    def test_empty_root_reports_nothing(self):
        with tempfile.TemporaryDirectory() as empty:
            data = sweep.report(Path(empty), admission=ADMISSION)
            self.assertEqual(data["records"], 0)
            self.assertIn("No records yet", sweep.render_markdown(data))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.admission = self.root / "admission.json"
        self.admission.write_text(json.dumps(ADMISSION), encoding="utf-8")
        self.out = self.root / "eval"

    def tearDown(self):
        self.tmp.cleanup()

    def _main(self, *argv):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = sweep.main(["run", "--out", str(self.out), "--admission", str(self.admission),
                             *argv])
        return rc, out.getvalue(), err.getvalue()

    def test_dry_run_prints_the_plan_and_launches_nothing(self):
        _write(self.out, _record("a__a-1", "sw", "claude-opus-5"))
        with mock.patch.object(sweep, "launch_run", side_effect=AssertionError("launched")):
            rc, out, _ = self._main("--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("seed %d" % sweep.DEFAULT_SEED, out)
        self.assertIn("30 runs: 1 done, 29 to run", out)
        self.assertIn("skip  a__a-1  sw    claude-opus-5     recorded", out)
        self.assertFalse((self.out / "sweeps").exists())

    def test_the_billing_account_must_be_set(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(sweep.CONFIG_DIR_VAR, None)
            with mock.patch.object(sweep, "launch_run", side_effect=AssertionError("launched")):
                with self.assertRaises(SystemExit) as ctx:
                    self._main("--max-runs", "0")
        self.assertIn(sweep.CONFIG_DIR_VAR, str(ctx.exception))

    def test_a_run_goes_through_launch_run_with_the_account(self):
        seen = []

        def fake(item, *, root, extra, env, logger):
            seen.append((item, env[sweep.CONFIG_DIR_VAR], extra))
            _write(root, _record(item["instance_id"], item["arm"], item["model"]))
            return "ok"
        with mock.patch.dict(os.environ, {sweep.CONFIG_DIR_VAR: self.tmp.name}):
            with mock.patch.object(sweep, "launch_run", fake):
                rc, _, err = self._main("--max-runs", "2", "--jobs", "1", "--instances", "b__b-2",
                                        "--arms", "nc", "orig", "--models", "m", "--effort", "low")
        self.assertEqual(rc, 0)
        self.assertEqual([(i["arm"], i["model"]) for i, _, _ in seen], [("orig", "m"), ("nc", "m")])
        self.assertEqual({acct for _, acct, _ in seen}, {self.tmp.name})
        self.assertEqual(seen[0][2], ["--effort", "low"])
        manifests = list((self.out / "sweeps").glob("*.json"))
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text())
        self.assertEqual(manifest["seed"], sweep.DEFAULT_SEED)
        self.assertEqual(manifest["result"]["launched"], 2)
        self.assertTrue((self.out / "report.md").exists())
        self.assertIn("spent", err)

    def test_a_block_exits_nonzero(self):
        with mock.patch.dict(os.environ, {sweep.CONFIG_DIR_VAR: self.tmp.name}):
            with mock.patch.object(sweep, "launch_run", return_value="blocked"):
                rc, _, _ = self._main("--jobs", "1", "--instances", "a__a-1", "--models", "m")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
