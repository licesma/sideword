"""Tests for `harness/evaluate.py`.

Two things are worth testing here and one thing is not.

Worth testing: **that the arms are the same experiment.** Everything the agent sees
apart from the source tree — prompt, action protocol, observation format, limits,
environment — has to be byte-identical across arms 1 and 3 and to differ from arm 2
by exactly one insertion. Most of the tests below are that claim, stated in the
several ways it could quietly stop being true.

Also worth testing: the two places where the harness re-derives something rather than
using it as given — `arm_gold_patch`, which re-expresses a patch against a stripped
tree, and `ClaudeCliModel`'s cursor, which decides what the CLI session has already
been told. Both are silent when wrong.

Not worth testing here: anything that needs Docker. Those paths are exercised by
`--dry-run`, `--score-only` and `--script`, which is what they exist for — a unit
test that started a container would be slower than the run it was standing in for.
"""

from __future__ import annotations

import difflib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness import evaluate


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


HAS_MSWEA = _has("minisweagent")
HAS_YAML = _has("yaml")
HAS_MIRROR = evaluate.MIRROR.is_dir()
HAS_PARQUET = _has("pyarrow") and _has("huggingface_hub")


class TestArmAddressing(unittest.TestCase):
    def test_image_name_spells_the_double_underscore(self):
        self.assertEqual(
            evaluate.image_name("pallets__flask-5014"),
            "swebench/sweb.eval.x86_64.pallets_1776_flask-5014:latest")
        self.assertEqual(
            evaluate.image_name("scikit-learn__scikit-learn-25102"),
            "swebench/sweb.eval.x86_64.scikit-learn_1776_scikit-learn-25102:latest")

    def test_one_image_serves_all_three_arms(self):
        """The environment belongs to the instance, not the arm."""
        names = {evaluate.image_name("sympy__sympy-22714") for _ in evaluate.ARMS}
        self.assertEqual(len(names), 1)

    def test_arm_ref(self):
        instance = {"instance_id": "x__y-1", "base_commit": "deadbeef"}
        self.assertEqual(evaluate.arm_ref(instance, "orig"), "deadbeef")
        self.assertEqual(evaluate.arm_ref(instance, "sw"), "x__y-1-sw")
        self.assertEqual(evaluate.arm_ref(instance, "nc"), "x__y-1-nc")

    def test_unknown_arm_is_refused(self):
        with self.assertRaises(ValueError):
            evaluate.arm_ref({"instance_id": "x", "base_commit": "c"}, "sideword")

    def test_record_path_separates_sources(self):
        root = Path("/tmp/eval")
        self.assertEqual(evaluate.record_path(root, "m", "sw", "i", "agent"),
                         root / "m" / "sw" / "i.json")
        self.assertEqual(evaluate.record_path(root, "m", "sw", "i", "gold"),
                         root / "m" / "sw" / "i.gold.json")


class TestArmsAreOneExperiment(unittest.TestCase):
    """The confound budget, asserted."""

    def test_arms_1_and_3_get_the_upstream_prompt_unchanged(self):
        self.assertEqual(evaluate.instance_template("orig"),
                         evaluate._UPSTREAM_INSTANCE_TEMPLATE)
        self.assertEqual(evaluate.instance_template("nc"),
                         evaluate._UPSTREAM_INSTANCE_TEMPLATE)

    def test_only_arm_2_carries_a_block(self):
        self.assertEqual(evaluate.sideword_block("orig"), "")
        self.assertEqual(evaluate.sideword_block("nc"), "")
        self.assertIn("sideword index", evaluate.sideword_block("sw"))

    def test_the_marker_never_survives_into_a_prompt(self):
        for arm in evaluate.ARMS:
            self.assertNotIn(evaluate.SIDEWORD_MARKER, evaluate.instance_template(arm))

    def test_arm_2_differs_by_exactly_one_insertion(self):
        """Not "differs a bit" — one contiguous block, nothing moved, nothing deleted."""
        base = evaluate.instance_template("orig").splitlines(keepends=True)
        arm2 = evaluate.instance_template("sw").splitlines(keepends=True)
        opcodes = [op for op in difflib.SequenceMatcher(None, base, arm2).get_opcodes()
                   if op[0] != "equal"]
        self.assertEqual([op[0] for op in opcodes], ["insert"])
        inserted = "".join(arm2[opcodes[0][3]:opcodes[0][4]])
        # `strip`, because the matcher is free to pick either of two identical blank
        # lines as the seam; what matters is that the inserted body is the block.
        self.assertEqual(inserted.strip("\n"), evaluate.sideword_block("sw").strip("\n"))

    def test_the_block_is_the_committed_prompt_file(self):
        text = evaluate.ARM2_PROMPT_FILE.read_text(encoding="utf-8").strip("\n")
        self.assertTrue(evaluate.sideword_block("sw").startswith(text))

    def _config(self, arm):
        return evaluate.agent_config(arm, step_limit=250, cost_limit=5.0,
                                     wall_limit=3600, action_timeout=180)

    def test_configs_for_arms_1_and_3_are_identical(self):
        self.assertEqual(self._config("orig"), self._config("nc"))
        self.assertEqual(evaluate.config_digest(self._config("orig")),
                         evaluate.config_digest(self._config("nc")))

    def test_arm_2_config_differs_only_in_the_instance_template(self):
        one, two = self._config("orig"), self._config("sw")
        differing = [k for k in one if one[k] != two[k]]
        self.assertEqual(differing, ["instance_template"])
        self.assertNotEqual(evaluate.config_digest(one), evaluate.config_digest(two))

    def test_limits_and_environment_do_not_depend_on_the_arm(self):
        for key in ("step_limit", "cost_limit", "wall_time_limit_seconds",
                    "action_regex", "observation_template", "format_error_template",
                    "system_template", "environment"):
            values = {json.dumps(self._config(arm)[key], sort_keys=True)
                      for arm in evaluate.ARMS}
            self.assertEqual(len(values), 1, "%s varies by arm" % key)


@unittest.skipUnless(HAS_MSWEA and HAS_YAML,
                     "needs the eval extra (uv run --extra eval)")
class TestPromptFidelity(unittest.TestCase):
    """The embedded prompt must still be mini-swe-agent's.

    It is embedded rather than loaded so a dependency bump cannot change the prompt
    under a half-finished sweep. The cost of embedding is that it can drift; this is
    the test that makes the drift loud instead of silent.
    """

    def setUp(self):
        import yaml

        import minisweagent
        config_dir = Path(minisweagent.package_dir) / "config" / "benchmarks"
        self.backticks = yaml.safe_load(
            (config_dir / "swebench_backticks.yaml").read_text(encoding="utf-8"))
        self.toolcall = yaml.safe_load(
            (config_dir / "swebench.yaml").read_text(encoding="utf-8"))

    def test_templates_match_upstream_verbatim(self):
        self.assertEqual(self.backticks["agent"]["system_template"],
                         evaluate.SYSTEM_TEMPLATE)
        self.assertEqual(self.backticks["agent"]["instance_template"],
                         evaluate._UPSTREAM_INSTANCE_TEMPLATE)
        self.assertEqual(self.backticks["model"]["observation_template"],
                         evaluate.OBSERVATION_TEMPLATE)
        self.assertEqual(self.backticks["model"]["format_error_template"],
                         evaluate.FORMAT_ERROR_TEMPLATE)

    def test_interpreter_matches_upstream(self):
        self.assertEqual(self.backticks["environment"]["interpreter"],
                         evaluate.AGENT_INTERPRETER)

    def test_the_only_environment_addition_is_bash_env(self):
        """And its value is upstream's own, taken from the toolcall sibling config.

        `swebench_backticks.yaml` runs `bash -c`, which never sources `.bashrc`, and
        omits BASH_ENV; `swebench.yaml` runs the same interpreter and sets it. Without
        it these images never `conda activate testbed`.
        """
        upstream = self.backticks["environment"]["env"]
        added = {k: v for k, v in evaluate.AGENT_ENV.items() if upstream.get(k) != v}
        self.assertEqual(added, {"BASH_ENV": "/root/.bashrc"})
        self.assertEqual(self.toolcall["environment"]["env"]["BASH_ENV"], "/root/.bashrc")
        self.assertEqual(set(upstream) - set(evaluate.AGENT_ENV), set())

    def test_action_regex_matches_upstream(self):
        from minisweagent.models.litellm_textbased_model import LitellmTextbasedModelConfig
        self.assertEqual(LitellmTextbasedModelConfig.model_fields["action_regex"].default,
                         evaluate.ACTION_REGEX)


class TestEvalScript(unittest.TestCase):
    """SWE-bench's eval script, with its two informational lines re-pointed."""

    class _Spec:
        def __init__(self, lines):
            self.eval_script_list = lines

    def _script(self):
        base = "b" * 40
        spec = self._Spec([
            "source /opt/miniconda3/bin/activate",
            "conda activate testbed",
            "cd /testbed",
            "git status",
            "git show",
            "git -c core.fileMode=false diff %s" % base,
            "python -m pip install -e .",
            "git checkout %s tests/test_x.py" % base,
            "git apply -v - <<'EOF_1'",
            ": '>>>>> Start Test Output'",
            "pytest -rA tests/test_x.py",
            ": '>>>>> End Test Output'",
            "git checkout %s tests/test_x.py" % base,
        ])
        return evaluate.eval_script(spec, "a" * 40, base), base

    def test_git_show_would_print_the_whole_arm_tree_so_it_does_not(self):
        script, _ = self._script()
        self.assertNotIn("\ngit show\n", script)
        self.assertIn("git log -1 --format='%H %s'", script)

    def test_the_informational_diff_points_at_the_baseline(self):
        script, base = self._script()
        self.assertIn("git -c core.fileMode=false diff %s" % ("a" * 40), script)
        self.assertNotIn("git -c core.fileMode=false diff %s" % base, script)

    def test_the_test_reset_still_comes_from_base_commit(self):
        """All three arms must run byte-identical tests, and those live at base_commit."""
        script, base = self._script()
        self.assertEqual(script.count("git checkout %s tests/test_x.py" % base), 2)

    def test_everything_that_decides_an_outcome_is_untouched(self):
        script, _ = self._script()
        for line in ("python -m pip install -e .", "pytest -rA tests/test_x.py",
                     ": '>>>>> Start Test Output'", ": '>>>>> End Test Output'",
                     "conda activate testbed"):
            self.assertIn(line, script)

    def test_it_is_a_bash_script_that_does_not_exit_early(self):
        script, _ = self._script()
        self.assertTrue(script.startswith("#!/bin/bash\nset -uxo pipefail\n"))
        self.assertTrue(script.endswith("\n"))


@unittest.skipUnless(HAS_MIRROR, "needs the corpus mirror at %s" % evaluate.MIRROR)
class TestMirror(unittest.TestCase):
    INSTANCE = "pallets__flask-5014"

    def setUp(self):
        self.instance = evaluate.get_instance(self.INSTANCE)

    def test_every_instance_has_all_three_arms(self):
        for entry in evaluate.load_instances():
            for arm in evaluate.ARMS:
                ref = evaluate.arm_ref(entry, arm)
                self.assertRegex(evaluate.tree_sha(ref), r"^[0-9a-f]{40}$",
                                 "%s has no %s tree" % (entry["instance_id"], arm))

    def test_sw_and_nc_differ_only_under_the_mirror_directory(self):
        """The claim arm 3 rests on: same code, docs or no docs."""
        changed = evaluate.git_mirror(
            "diff", "--name-status", "%s-nc" % self.INSTANCE, "%s-sw" % self.INSTANCE)
        rows = [line.split("\t") for line in changed.strip().split("\n") if line]
        self.assertTrue(rows)
        self.assertEqual({row[0] for row in rows}, {"A"})
        self.assertTrue(all(row[1].startswith(".sideword/") for row in rows))

    def test_tree_blobs_drops_nothing_and_invents_nothing(self):
        sw = evaluate.tree_blobs("%s-sw" % self.INSTANCE)
        nc = evaluate.tree_blobs("%s-nc" % self.INSTANCE)
        self.assertEqual(sorted(set(sw) - set(nc)),
                         sorted(p for p in sw if p.startswith(".sideword/")))
        self.assertEqual(set(nc) - set(sw), set())

    def test_the_one_gitlink_is_kept_out_of_the_file_list_and_put_back_by_hand(self):
        """astropy-7336 carries `astropy_helpers` as a submodule. It is not a file, so it
        is in neither the tar nor the pathspec, and it is re-added as a cacheinfo entry so
        the committed tree still hashes to the mirror's."""
        entry = evaluate.get_instance("astropy__astropy-7336")
        for arm in evaluate.ARMS:
            ref = evaluate.arm_ref(entry, arm)
            links = evaluate.tree_gitlinks(ref)
            self.assertEqual([path for _, path in links], ["astropy_helpers"], arm)
            self.assertRegex(links[0][0], r"^[0-9a-f]{40}$")
            self.assertNotIn("astropy_helpers", evaluate.tree_blobs(ref))
        self.assertEqual(evaluate.tree_gitlinks(evaluate.arm_ref(self.instance, "orig")), [])

    def test_no_arm_touches_a_test_file(self):
        """If it did, arms would be running different tests until scoring reset them."""
        for instance_id in (self.INSTANCE, "sympy__sympy-22714", "django__django-7530"):
            entry = evaluate.get_instance(instance_id)
            for arm in evaluate.ARMS:
                self.assertEqual(evaluate.arm_test_files_match_base(entry, arm), [],
                                 "%s/%s alters a test file" % (instance_id, arm))


@unittest.skipUnless(HAS_MIRROR and HAS_PARQUET, "needs the mirror and the dataset cache")
class TestArmGoldPatch(unittest.TestCase):
    """The known-good answer, re-expressed for a tree that deleted its own context."""

    INSTANCE = "pallets__flask-5014"

    @classmethod
    def setUpClass(cls):
        try:
            cls.row = evaluate.load_row(cls.INSTANCE)
        except Exception as exc:                       # no cached parquet, no network
            raise unittest.SkipTest("dataset unavailable: %s" % exc)
        cls.instance = evaluate.get_instance(cls.INSTANCE)

    def test_arm_1_gets_the_dataset_patch_untouched(self):
        self.assertEqual(evaluate.arm_gold_patch(self.instance, self.row, "orig"),
                         self.row["patch"])

    def test_derived_patches_name_the_same_files(self):
        def files(patch):
            return sorted({m for _, m in
                           __import__("re").findall(r"^diff --git a/(.*?) b/(.*)$",
                                                    patch, __import__("re").M)})
        gold = files(self.row["patch"])
        for arm in ("sw", "nc"):
            self.assertEqual(files(evaluate.arm_gold_patch(self.instance, self.row, arm)),
                             gold, "arm %s changed which files the fix touches" % arm)

    def test_arms_2_and_3_get_the_same_patch(self):
        """They have byte-identical `.py` blobs, so a code patch cannot tell them apart.

        If this ever differs, the two trees have drifted and arm 3 has stopped being
        arm 2's control.
        """
        self.assertEqual(evaluate.arm_gold_patch(self.instance, self.row, "sw"),
                         evaluate.arm_gold_patch(self.instance, self.row, "nc"))

    def test_the_derived_patch_never_touches_the_mirror_directory(self):
        self.assertNotIn(".sideword/",
                         evaluate.arm_gold_patch(self.instance, self.row, "sw"))

    def test_the_derived_patch_applies_to_the_arm_it_was_derived_for(self):
        """`git apply --check` against the arm's own blobs, which is the whole point."""
        for arm in ("sw", "nc"):
            patch = evaluate.arm_gold_patch(self.instance, self.row, arm)
            ref = evaluate.arm_ref(self.instance, arm)
            with tempfile.TemporaryDirectory() as work:
                work = Path(work)
                import re as _re
                paths = {new for _, new in
                         _re.findall(r"^diff --git a/(.*?) b/(.*)$", patch, _re.M)}
                for path in paths:
                    blob = evaluate.show_blob(ref, path)
                    if blob is None:
                        continue
                    (work / path).parent.mkdir(parents=True, exist_ok=True)
                    (work / path).write_bytes(blob)
                (work / "p.diff").write_text(patch, encoding="utf-8")
                proc = subprocess.run(["git", "apply", "-p1", "--check", "p.diff"],
                                      cwd=work, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0,
                                 "arm %s gold patch will not apply: %s" % (arm, proc.stderr))

    def test_the_original_patch_does_not_apply_to_a_stripped_tree(self):
        """Which is why the derivation exists at all.

        Not a universal truth — for 3 of the 30 instances the fix happens to land far
        enough from any comment that the original context still matches. For the other
        27, including this one, feeding the dataset's patch to arms 2 and 3 would score
        every one of them as a failed apply.
        """
        other = "sphinx-doc__sphinx-11445"
        instance = evaluate.get_instance(other)
        row = evaluate.load_row(other)
        ref = evaluate.arm_ref(instance, "nc")
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            import re as _re
            paths = {new for _, new in
                     _re.findall(r"^diff --git a/(.*?) b/(.*)$", row["patch"], _re.M)}
            for path in paths:
                blob = evaluate.show_blob(ref, path)
                if blob is None:
                    continue
                (work / path).parent.mkdir(parents=True, exist_ok=True)
                (work / path).write_bytes(blob)
            (work / "p.diff").write_text(row["patch"], encoding="utf-8")
            proc = subprocess.run(["git", "apply", "-p1", "--check", "p.diff"],
                                  cwd=work, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            derived = evaluate.arm_gold_patch(instance, row, "nc")
            (work / "d.diff").write_text(derived, encoding="utf-8")
            ok = subprocess.run(["git", "apply", "-p1", "--check", "d.diff"],
                                cwd=work, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)


class TestWipeTrackedFiles(unittest.TestCase):
    """The wipe before an arm lands: every tracked file goes, a submodule entry does not."""

    def test_gitlinks_are_skipped_and_files_removed(self):
        with tempfile.TemporaryDirectory() as td:
            git = lambda *a: subprocess.run(["git", "-C", td, *a], check=True, capture_output=True)
            git("init", "-q")
            Path(td, "a.txt").write_text("a")
            Path(td, "d").mkdir()
            Path(td, "d", "b c.txt").write_text("b")
            Path(td, "sub").mkdir()
            git("add", "a.txt", "d")
            git("update-index", "--add", "--cacheinfo", "160000,%s,sub" % ("1" * 40))
            proc = subprocess.run(["bash", "-c", evaluate.WIPE_TRACKED_FILES], cwd=td,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(Path(td, "a.txt").exists())
            self.assertFalse(Path(td, "d", "b c.txt").exists())
            self.assertTrue(Path(td, "sub").is_dir())
            self.assertIn("160000", git("ls-files", "-s").stdout.decode())

    def test_it_is_the_command_materialize_runs(self):
        import inspect
        self.assertIn("container.exec(WIPE_TRACKED_FILES)", inspect.getsource(evaluate.materialize))
        self.assertIn("tree_gitlinks(ref)", inspect.getsource(evaluate.materialize))


class TestExitStatus(unittest.TestCase):
    """A blocked or errored agent run must not exit 0."""

    def test_codes_are_distinct_and_non_zero(self):
        self.assertNotEqual(evaluate.EXIT_ALLOWANCE_EXHAUSTED, 0)
        self.assertNotEqual(evaluate.EXIT_AGENT_ERROR, 0)
        self.assertNotEqual(evaluate.EXIT_ALLOWANCE_EXHAUSTED, evaluate.EXIT_AGENT_ERROR)

    def test_run_returns_them_from_the_record(self):
        import inspect
        src = inspect.getsource(evaluate.run)
        self.assertIn('if "allowance-exhausted" in kinds:\n        return EXIT_ALLOWANCE_EXHAUSTED', src)
        self.assertIn("return EXIT_AGENT_ERROR", src)


class TestLandedFileTimestamps(unittest.TestCase):
    """A git tree has no mtimes, so one is invented — and it cannot be the epoch."""

    def test_the_stamp_is_after_1980(self):
        """Several of these repos build a wheel during evaluation, and a wheel is a ZIP.

        `tarfile`'s default mtime of 0 makes `zipfile` raise "ZIP does not support
        timestamps before 1980"; `pip install -e .` then fails, leaves the previously
        installed package in place, and the suite runs pre-patch code while reporting
        nothing worse than a buried traceback.
        """
        import datetime as _dt
        stamp = _dt.datetime.fromtimestamp(evaluate.TAR_MTIME, _dt.timezone.utc)
        self.assertGreater(stamp.year, 1980)
        self.assertLess(stamp.year, 2038)

    def test_it_is_a_constant_and_not_derived_from_the_ref(self):
        """The `-sw` and `-nc` tags were written later than `base_commit`.

        Anything commit-derived would give the three arms different mtimes, which is
        a difference between arms that is not the source tree.
        """
        self.assertIsInstance(evaluate.TAR_MTIME, int)

    @unittest.skipUnless(HAS_MIRROR, "needs the corpus mirror")
    def test_every_entry_in_a_real_tar_carries_it(self):
        import tarfile
        instance = evaluate.get_instance("pallets__flask-5014")
        with tempfile.TemporaryDirectory() as work:
            dest = Path(work) / "arm.tar"
            evaluate.write_arm_tar(evaluate.arm_ref(instance, "orig"), dest)
            with tarfile.open(dest) as tar:
                stamps = {m.mtime for m in tar.getmembers()}
        self.assertEqual(stamps, {evaluate.TAR_MTIME})


class TestImageEnvironmentDelta(unittest.TestCase):
    """SWE-bench edits tracked config when it builds an image; landing an arm wipes it."""

    def test_the_capture_ignores_file_modes(self):
        """Docker Desktop's VM disagrees with the index about executable bits.

        Without `core.fileMode=false` this returns a mode-only diff of every file in
        the repository — 4,433 of them for matplotlib — and none of it is real.
        """
        container = _FakeContainer()
        evaluate.image_environment_delta(container, "b" * 40)
        self.assertIn("core.fileMode=false", container.calls[0])
        self.assertIn("diff %s" % ("b" * 40), container.calls[0])

    def test_it_is_captured_against_the_base_commit(self):
        container = _FakeContainer({"diff": (0, "diff --git a/tox.ini b/tox.ini\n")})
        self.assertIn("tox.ini", evaluate.image_environment_delta(container, "c" * 40))


class _FakeContainer:
    """Enough of `Container` for the pure logic, and nothing that could reach Docker."""

    def __init__(self, replies=None):
        self.replies = replies or {}
        self.calls = []
        self.puts = []

    def exec(self, script, **kwargs):
        self.calls.append(script)
        for needle, (rc, out) in self.replies.items():
            if needle in script:
                return subprocess.CompletedProcess(script, rc, out, "")
        return subprocess.CompletedProcess(script, 0, "", "")

    def out(self, script, **kwargs):
        return self.exec(script, **kwargs).stdout.strip()

    def put_text(self, text, dest, mode=None):
        self.puts.append((dest, text))


class TestContainerReadback(unittest.TestCase):
    def test_files_read_is_repo_relative(self):
        container = _FakeContainer({"find": (0, "/testbed/src/a.py\n/testbed/b.py\n\n")})
        self.assertEqual(evaluate.files_read(container), ["b.py", "src/a.py"])

    def test_files_read_excludes_the_git_directory(self):
        container = _FakeContainer()
        evaluate.files_read(container)
        self.assertIn("-path /testbed/.git -prune", container.calls[0])

    def test_the_marker_lives_outside_the_repository(self):
        """Anything under /testbed can end up in a patch or a test collection."""
        for path in (evaluate.ATIME_MARKER, evaluate.SIDEWORD_CALL_LOG,
                     evaluate.SIDEWORD_DIR):
            self.assertFalse(path.startswith(evaluate.TESTBED + "/"))

    def test_atime_reset_precedes_the_marker(self):
        """Reversed, setup's own reads would look like the agent's."""
        container = _FakeContainer()
        evaluate.reset_atimes(container)
        script = "\n".join(container.calls)
        self.assertLess(script.index("touch -a -t 197001010001"),
                        script.index("touch %s" % evaluate.ATIME_MARKER))

    def test_git_is_told_not_to_trust_ctime(self):
        """`touch -a` bumps ctime, which invalidates git's stat cache.

        Left alone, the agent's first `git status` re-reads the whole repository to
        rebuild it and the sweep counts every one of those as a file the agent read —
        248 instead of 2, on flask.
        """
        container = _FakeContainer()
        evaluate.reset_atimes(container)
        script = "\n".join(container.calls)
        self.assertIn("core.trustctime false", script)
        self.assertLess(script.index("core.trustctime false"),
                        script.index("touch -a -t 197001010001"))

    def test_the_install_probe_is_not_counted_as_an_agent_call(self):
        container = _FakeContainer()
        evaluate.reset_atimes(container)
        self.assertIn(": > %s" % evaluate.SIDEWORD_CALL_LOG, "\n".join(container.calls))

    def test_sideword_calls_are_parsed(self):
        container = _FakeContainer({"cat": (0, "1700000000\t0\tindex src/a.py\n"
                                               "1700000005\t1\tshow src/a.py Missing\n")})
        self.assertEqual(evaluate.sideword_calls(container), [
            {"at": 1700000000, "returncode": 0, "args": "index src/a.py"},
            {"at": 1700000005, "returncode": 1, "args": "show src/a.py Missing"},
        ])

    def test_sideword_calls_tolerates_an_empty_log(self):
        self.assertEqual(evaluate.sideword_calls(_FakeContainer()), [])


class TestSidewordShim(unittest.TestCase):
    def test_it_uses_the_system_interpreter(self):
        """`python3` under the agent's shell is conda's, which can be 3.5."""
        self.assertIn("/usr/bin/python3", evaluate.SIDEWORD_SHIM)
        self.assertNotIn("\npython3 ", evaluate.SIDEWORD_SHIM)

    def test_percent_escaping_survived(self):
        self.assertIn(r"printf '%s\t%s\t%s\n'", evaluate.SIDEWORD_SHIM)
        self.assertNotIn("%%", evaluate.SIDEWORD_SHIM)

    def test_it_forwards_the_exit_status(self):
        self.assertIn("rc=$?", evaluate.SIDEWORD_SHIM)
        self.assertIn("exit $rc", evaluate.SIDEWORD_SHIM)

    def test_it_runs_under_sh(self):
        self.assertTrue(evaluate.SIDEWORD_SHIM.startswith("#!/bin/sh\n"))


class TestApplyPatch(unittest.TestCase):
    def test_an_empty_patch_never_reaches_the_container(self):
        container = _FakeContainer()
        applied, detail = evaluate.apply_patch(container, "   \n", log=lambda *_: None)
        self.assertTrue(applied)
        self.assertEqual(container.calls, [])
        self.assertIn("empty", detail)

    def test_the_ladder_is_swe_benchs_own(self):
        self.assertEqual(evaluate.GIT_APPLY_CMDS, [
            "git apply --verbose",
            "git apply --verbose --reject",
            "patch --batch --fuzz=5 -p1 -i",
        ])

    def test_it_stops_at_the_first_command_that_works(self):
        container = _FakeContainer({"git apply --verbose": (0, "applied")})
        applied, _ = evaluate.apply_patch(container, "diff --git a/x b/x\n",
                                          log=lambda *_: None)
        self.assertTrue(applied)
        self.assertEqual(len(container.calls), 1)

    def test_it_reports_failure_after_the_whole_ladder(self):
        container = _FakeContainer({"apply": (1, "nope"), "patch --batch": (1, "nope")})
        applied, _ = evaluate.apply_patch(container, "diff --git a/x b/x\n",
                                          log=lambda *_: None)
        self.assertFalse(applied)
        self.assertEqual(len(container.calls), 3)


class TestClaudeEnv(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("SIDEWORD_CLAUDE_CONFIG_DIR")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("SIDEWORD_CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["SIDEWORD_CLAUDE_CONFIG_DIR"] = self._saved

    def test_an_unset_config_dir_is_fatal_rather_than_defaulted(self):
        """Defaulting to ~/.claude spends an account nobody chose."""
        os.environ.pop("SIDEWORD_CLAUDE_CONFIG_DIR", None)
        with self.assertRaises(SystemExit) as caught:
            evaluate.claude_env()
        self.assertIn("SIDEWORD_CLAUDE_CONFIG_DIR", str(caught.exception))

    def test_the_path_keeps_the_directory_the_shim_lives_in(self):
        """Under nvm, `which claude` and its realpath are in different trees.

        The shim is `~/.nvm/versions/node/<v>/bin/claude`; it resolves into
        `lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`. Keeping only the
        resolved path drops `node` off a stripped PATH and the CLI never starts.
        """
        import shutil
        os.environ["SIDEWORD_CLAUDE_CONFIG_DIR"] = "/tmp/claude-x"
        claude = shutil.which("claude")
        if not claude:
            self.skipTest("no `claude` on PATH")
        parts = evaluate.claude_env()["PATH"].split(":")
        self.assertIn(os.path.dirname(claude), parts)
        self.assertIn(os.path.dirname(os.path.realpath(claude)), parts)

    def test_the_config_dir_is_passed_and_nothing_else_claude_shaped(self):
        os.environ["SIDEWORD_CLAUDE_CONFIG_DIR"] = "/tmp/claude-x"
        try:
            env = evaluate.claude_env()
        except SystemExit as exc:                      # no `claude` on PATH here
            self.skipTest(str(exc))
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/tmp/claude-x")
        self.assertEqual([k for k in env if k.startswith("CLAUDE_")],
                         ["CLAUDE_CONFIG_DIR"])


class TestEstimateTokens(unittest.TestCase):
    def test_four_characters_to_a_token(self):
        self.assertEqual(evaluate.estimate_tokens(""), 0)
        self.assertEqual(evaluate.estimate_tokens("abcd"), 1)
        self.assertEqual(evaluate.estimate_tokens("abcde"), 2)


@unittest.skipUnless(HAS_MSWEA, "needs the eval extra (uv run --extra eval)")
class TestClaudeCliModelSession(unittest.TestCase):
    """The cursor, which decides what the CLI session has not yet been told.

    Getting this wrong does not raise: it silently re-sends turns the session already
    has, or drops one it does not, and the transcript quietly diverges from the
    trajectory the record claims.
    """

    def _model(self, replies):
        model = evaluate.ClaudeCliModel(
            model_name="test-model", action_regex=evaluate.ACTION_REGEX,
            format_error_template=evaluate.FORMAT_ERROR_TEMPLATE,
            observation_template=evaluate.OBSERVATION_TEMPLATE, log=lambda *_: None)
        sent = []

        def fake_call(prompt):
            sent.append((prompt, model._cmd()))
            return replies.pop(0)

        model._call = fake_call
        return model, sent

    @staticmethod
    def _reply(command):
        return {"result": "THOUGHT: go\n\n```mswea_bash_command\n%s\n```" % command,
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "total_cost_usd": 0.5, "session_id": "s"}

    def test_the_first_call_opens_a_session_and_carries_the_system_prompt(self):
        model, sent = self._model([self._reply("ls")])
        messages = [{"role": "system", "content": "SYSTEM"},
                    {"role": "user", "content": "TASK"}]
        out = model.query(messages)
        prompt, cmd = sent[0]
        self.assertEqual(prompt, "TASK")
        self.assertIn("--session-id", cmd)
        self.assertNotIn("--resume", cmd)
        self.assertIn("--system-prompt-file", cmd)
        path = cmd[cmd.index("--system-prompt-file") + 1]
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "SYSTEM")
        self.assertEqual(out["extra"]["actions"], [{"command": "ls"}])

    def test_later_calls_resume_and_send_only_what_is_new(self):
        model, sent = self._model([self._reply("ls"), self._reply("cat x")])
        messages = [{"role": "system", "content": "SYSTEM"},
                    {"role": "user", "content": "TASK"}]
        first = model.query(messages)
        messages.append(first)                          # the agent appends the reply
        messages.append({"role": "user", "content": "OBSERVATION"})
        model.query(messages)
        prompt, cmd = sent[1]
        self.assertEqual(prompt, "OBSERVATION")
        self.assertIn("--resume", cmd)
        self.assertNotIn("--session-id", cmd)
        self.assertNotIn("--system-prompt-file", cmd)

    def test_assistant_turns_are_never_replayed(self):
        """The session already has them; resending doubles the bill and the transcript."""
        model, sent = self._model([self._reply("ls"), self._reply("cat x")])
        messages = [{"role": "system", "content": "SYSTEM"},
                    {"role": "user", "content": "TASK"}]
        first = model.query(messages)
        messages.append(first)
        messages.append({"role": "user", "content": "OBSERVATION"})
        model.query(messages)
        self.assertNotIn("THOUGHT", sent[1][0])

    def test_tools_are_disabled_on_every_call(self):
        """mini-swe-agent supplies the shell; a second tool surface is a confound."""
        model, sent = self._model([self._reply("ls"), self._reply("cat x")])
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "T"}]
        first = model.query(messages)
        messages += [first, {"role": "user", "content": "O"}]
        model.query(messages)
        for _, cmd in sent:
            self.assertEqual(cmd[cmd.index("--tools") + 1], "")
            self.assertIn("--safe-mode", cmd)
            self.assertEqual(cmd[cmd.index("--model") + 1], "test-model")

    def test_a_format_error_still_reports_what_the_call_cost(self):
        from minisweagent.exceptions import FormatError
        model, _ = self._model([{"result": "no action here", "usage": {},
                                 "total_cost_usd": 0.25}])
        with self.assertRaises(FormatError) as caught:
            model.query([{"role": "system", "content": "S"},
                         {"role": "user", "content": "T"}])
        self.assertEqual(caught.exception.messages[0]["extra"]["cost"], 0.25)
        self.assertEqual(model.cost, 0.25)

    def test_the_cursor_survives_a_format_error(self):
        """After one, the agent appends a user message and no assistant message."""
        from minisweagent.exceptions import FormatError
        model, sent = self._model([{"result": "nothing", "usage": {}, "total_cost_usd": 0.1},
                                   self._reply("ls")])
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "T"}]
        with self.assertRaises(FormatError):
            model.query(messages)
        messages.append({"role": "user", "content": "RETRY"})
        model.query(messages)
        self.assertEqual(sent[1][0], "RETRY")

    def test_a_retried_opening_call_gets_a_fresh_session_id(self):
        """A failed first attempt may have created the session before dying."""
        model = evaluate.ClaudeCliModel(
            model_name="m", action_regex=evaluate.ACTION_REGEX,
            format_error_template="", observation_template="", max_attempts=2,
            log=lambda *_: None)
        seen = []

        def fake_run(cmd, **kwargs):
            seen.append(cmd[cmd.index("--session-id") + 1])
            return subprocess.CompletedProcess(cmd, 1, "", "Error 529: overloaded")

        import time as _time
        real_run, real_sleep = subprocess.run, _time.sleep
        subprocess.run, _time.sleep = fake_run, lambda *_: None
        try:
            os.environ.setdefault("SIDEWORD_CLAUDE_CONFIG_DIR", "/tmp/claude-x")
            with self.assertRaises(RuntimeError):
                model._call("hello")
        except SystemExit as exc:                      # no `claude` on PATH here
            self.skipTest(str(exc))
        finally:
            subprocess.run, _time.sleep = real_run, real_sleep
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1])

    def test_effort_is_omitted_when_unset(self):
        model, _ = self._model([])
        self.assertNotIn("--effort", model._cmd())
        model.config.effort = "high"
        self.assertEqual(model._cmd()[model._cmd().index("--effort") + 1], "high")


@unittest.skipUnless(HAS_MSWEA, "needs the eval extra (uv run --extra eval)")
class TestAllowanceGuard(unittest.TestCase):
    def test_a_blocked_account_stops_the_run_instead_of_retrying(self):
        self.assertTrue(evaluate.HARD_BLOCK_RE.search(
            "Claude usage limit reached. Your limit will reset at 2:30pm"))

    def test_a_throttle_is_not_a_block(self):
        self.assertTrue(evaluate.RATE_LIMIT_RE.search("Error 529: overloaded"))
        self.assertFalse(evaluate.HARD_BLOCK_RE.search("Error 529: overloaded"))


class TestCli(unittest.TestCase):
    def test_the_two_no_model_modes_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            evaluate.main(["--instance", "pallets__flask-5014", "--arm", "sw",
                           "--model", "m", "--dry-run", "--score-only", "gold"])

    def test_arm_is_constrained_to_the_three(self):
        with self.assertRaises(SystemExit):
            evaluate.build_parser().parse_args(
                ["--instance", "i", "--arm", "arm4", "--model", "m"])

    def test_defaults_are_the_ones_the_record_will_claim(self):
        args = evaluate.build_parser().parse_args(
            ["--instance", "i", "--arm", "sw", "--model", "m"])
        self.assertEqual(args.step_limit, 250)          # upstream's
        self.assertEqual(args.action_timeout, 180)      # ours, for emulation
        self.assertIsNone(args.effort)
        self.assertIsNone(args.score_only)


if __name__ == "__main__":
    unittest.main()
