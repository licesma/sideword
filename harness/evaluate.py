#!/usr/bin/env python3
"""EST-165: one instance, one arm, one model — the unit the experiment is made of.

    uv run --extra eval python -m harness.evaluate --instance <id> --arm <arm> --model <m>

Three arms, all tagged in the mirror at `~/repos/sideword-corpus`:

    orig   the instance's `base_commit`             original code, comments intact
    sw     `<instance_id>-sw`                        stripped code + `.sideword/` docs
    nc     `<instance_id>-nc`                        stripped code, no docs

`-sw` and `-nc` carry byte-identical `.py` blobs and differ only under `.sideword/`,
so arm 3 separates "documentation helped" from "less context helped".

What one invocation does
------------------------
1. Start the instance's official image, `swebench/sweb.eval.x86_64.<id>`. The
   environment is a property of the instance, not of the arm: one image, three runs.
2. Replace `/testbed`'s working tree with the arm's tree and commit it, so that
   `git diff <baseline>` afterwards is exactly what the agent changed. The commit
   is also what keeps `.sideword/` — 66 to 1,766 files — out of the extracted patch.
   The image's own edits to tracked configuration are captured before the wipe and
   replayed after it, as a second commit: SWE-bench does not ship a pristine
   checkout, and two of the twelve repositories depend on what its build changed.
3. For arm 2 only, install the `sideword` command and splice `corpus/arm2-prompt.md`
   into the task message — one contiguous insertion, at the point where the message
   stops describing the task and starts describing the repository. Nothing else
   differs between arms; see "The confound budget".
4. Run mini-swe-agent, driven by `claude -p` on the subscription.
5. Score in a *fresh* container of the same image, using SWE-bench's own eval script,
   log parsers and definition of "resolved".
6. Write `corpus/eval/<model>/<arm>/<instance_id>.json`.

The confound budget
-------------------
The agent, its tool surface, its prompt, its limits and its timeouts are identical
across arms. Exactly two things are not, and both are the thing being measured:

  * the source tree at `/testbed`;
  * for arm 2, the `sideword` command on `PATH` and the block of prompt text that
    says what it does.

Everything else is held fixed on purpose, including the deviations from upstream
defaults: they are applied to all three arms or to none.

  * `--action-timeout` defaults to 180 s, not mini-swe-agent's 60 s. These images are
    x86_64 and this is an arm64 Mac, so everything inside them is emulated.
  * `BASH_ENV=/root/.bashrc` is added to mini-swe-agent's `swebench_backticks.yaml`
    environment. That config runs `bash -c`, which is non-login and never sources
    `.bashrc`, so without it the image's `conda activate testbed` does not happen and
    every command runs against the wrong interpreter. `swebench.yaml`, the toolcall
    sibling of the same config, sets it; the backticks variant appears to have been
    missed upstream.
  * The prompt is mini-swe-agent 2.4.6's `swebench_backticks.yaml`, embedded verbatim
    below rather than read from the installed package, so that a dependency bump
    cannot change the prompt underneath a half-finished sweep.
    `harness/tests/test_evaluate.py` fails if the two ever drift apart.

Not measuring the model call
----------------------------
Four ways to run this without one, in increasing coverage:

  `--dry-run`            container up, arm's tree landed and verified by tree hash,
                         `sideword` installed and answering, prompts rendered, stop.
  `--score-only empty`   the scoring path against no answer at all.
  `--score-only gold`    the scoring path against the right answer. The dataset's
                         patch cannot apply to a stripped tree — 27 of the 30
                         instances reject it outright — so for arms 2 and 3 it is
                         re-derived by `arm_gold_patch`.
  `--script <file>`      the entire agent loop, patch extraction and scoring, with a
                         recorded list of replies standing in for `claude -p`.

Checking the arm, not the run
-----------------------------
`gold` and `empty` are assertions, and they exit non-zero when the assertion fails.
Together they are a per-instance, per-arm admission test that costs no model time.
Run them across the corpus *before* a sweep. Of the twelve instances whose images
were on hand, four do not survive, and not one of the four is a harness bug:

  * **Repositories that read their own docstrings at runtime.**
    `astropy/io/ascii/core.py` does `func.__doc__ += inspect.cleandoc(cls.__doc__)`;
    seaborn's `_docstrings.py` assembles its public API out of docstring fragments.
    Stripped, both raise at import and every test in arms 2 and 3 errors during
    collection.
  * **A docstring that is executable configuration.** `pytest-10051` keeps
    `PYTEST_DONT_REWRITE` — the opt-out its own assertion rewriter greps for, in
    `mark_rewrite`'s `is_rewrite_disabled(mod.__doc__ or "")` — in `pytester.py`'s
    *module docstring* and nowhere else. Strip it and the warning fires; the repo
    sets `filterwarnings = error`, so pytest does not start at all. This is the
    sharpest case in the corpus: prose the interpreter reads.
  * **A repository that lints itself.** `pylint-6528`'s suite runs pylint over
    pylint, and a stripped tree reports `missing-module-docstring` and friends.
  * **An instance that cannot discriminate.** `django-7530` scores resolved on an
    empty patch — under stock SWE-bench, in an untouched image, with none of this
    harness involved.

The first three are arms 2 and 3 only; the fourth spoils all three arms. The first
two are also the interesting ones for the format: a stripper that keeps a docstring
when something reads it back would recover them, and `corpus/directives.toml`'s
allowlist governs comments, not docstrings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import paths as pathrules

# ---- where things live ------------------------------------------------------------------

MIRROR = Path(os.environ.get("SIDEWORD_MIRROR", Path.home() / "repos" / "sideword-corpus"))
INSTANCES_JSON = ROOT / "corpus" / "instances.json"
ARM2_PROMPT_FILE = ROOT / "corpus" / "arm2-prompt.md"
EVAL_ROOT = ROOT / "corpus" / "eval"

#: The dataset row carries three fields `corpus/instances.json` deliberately does not
#: (problem statement, gold patch, test patch); it is the same parquet `harness/instances.py`
#: selected from, and it is already in the Hugging Face cache.
DATASET = "princeton-nlp/SWE-bench_Verified"
DATASET_PARQUET = "data/test-00000-of-00001.parquet"

ARMS = ("orig", "sw", "nc")
TESTBED = "/testbed"
PLATFORM = "linux/amd64"

#: Marker file whose atime the sweep compares against. Outside `/testbed` so it is
#: neither collected by a test run nor visible in a patch.
ATIME_MARKER = "/tmp/sideword-t0"
SIDEWORD_CALL_LOG = "/tmp/sideword-calls.log"
SIDEWORD_DIR = "/opt/sideword"

#: Timestamp stamped on every file we land in `/testbed`. A git tree carries no
#: mtimes, so one has to be invented, and the obvious choice — tarfile's default of
#: 0 — is wrong in a way that takes a while to see: several of these repositories
#: build a wheel during evaluation (`pip install -e .` on a flit_core or setuptools
#: backend), a wheel is a ZIP, and ZIP cannot encode a timestamp before 1980. The
#: build fails, pip leaves the *previously installed* package in place, and the test
#: suite then runs pre-patch code while reporting nothing worse than a buried
#: traceback. sphinx-11445 failed its own gold patch that way in all three arms.
#:
#: A fixed constant rather than the commit's own date: the `-sw` and `-nc` tags were
#: written later than `base_commit`, so a commit-derived mtime would differ by arm.
TAR_MTIME = 1262304000                 # 2010-01-01T00:00:00Z

#: `diff --git a/<old> b/<new>` — the only part of a patch that names files.
_DIFF_HEADER = re.compile(r"^diff --git a/(.*?) b/(.*)$", re.M)

#: SWE-bench's own ladder, in its own order (`swebench.harness.run_evaluation`).
GIT_APPLY_CMDS = [
    "git apply --verbose",
    "git apply --verbose --reject",
    "patch --batch --fuzz=5 -p1 -i",
]


# ---- instances --------------------------------------------------------------------------

def load_instances() -> list[dict]:
    with open(INSTANCES_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def get_instance(instance_id: str) -> dict:
    for entry in load_instances():
        if entry["instance_id"] == instance_id:
            return entry
    raise SystemExit("no such instance in corpus/instances.json: %s" % instance_id)


def dataset_parquet() -> str:
    """The Verified parquet, from the Hugging Face cache if it is already there.

    `harness/instances.py` lists the repo to find this file, which needs the network.
    An evaluation run should not: the file is 30 MB, it never changes, and a sweep
    that dies mid-instance because DNS blinked is a sweep that has to be re-run.
    """
    override = os.environ.get("SIDEWORD_SWEBENCH_PARQUET")
    if override:
        return override
    from huggingface_hub import hf_hub_download
    try:
        return hf_hub_download(repo_id=DATASET, repo_type="dataset",
                               filename=DATASET_PARQUET, local_files_only=True)
    except Exception:
        from huggingface_hub import list_repo_files
        files = [f for f in list_repo_files(DATASET, repo_type="dataset")
                 if f.endswith(".parquet")]
        return hf_hub_download(repo_id=DATASET, repo_type="dataset", filename=sorted(files)[0])


def load_row(instance_id: str) -> dict:
    """The full SWE-bench Verified row: problem statement, gold patch, test patch."""
    import pyarrow.parquet as pq

    table = pq.read_table(dataset_parquet())
    for row in table.to_pylist():
        if row["instance_id"] == instance_id:
            return row
    raise SystemExit("instance not in %s: %s" % (DATASET, instance_id))


def image_name(instance_id: str) -> str:
    """The official per-instance image. `__` is spelled `_1776_` in the tag."""
    return "swebench/sweb.eval.x86_64.%s:latest" % instance_id.replace("__", "_1776_").lower()


def arm_ref(instance: dict, arm: str) -> str:
    """The mirror ref holding this arm's tree."""
    if arm not in ARMS:
        raise ValueError("unknown arm %r (expected one of %s)" % (arm, ", ".join(ARMS)))
    if arm == "orig":
        return instance["base_commit"]
    return "%s-%s" % (instance["instance_id"], arm)


# ---- the mirror -------------------------------------------------------------------------

def git_mirror(*args: str, binary: bool = False, check: bool = True):
    proc = subprocess.run(["git", "-C", str(MIRROR), *args],
                          capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError("git -C %s %s failed: %s"
                           % (MIRROR, " ".join(args), proc.stderr.decode("utf-8", "replace")))
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def tree_sha(ref: str) -> str:
    return git_mirror("rev-parse", "%s^{tree}" % ref).strip()


def tree_blobs(ref: str) -> list[str]:
    """Every blob path in `ref`, in git's order.

    Gitlinks are dropped: a submodule entry is not a file, so it is neither written
    into the tar nor named to `git add`. One of the 30 instances has one --
    `astropy__astropy-7336`'s `astropy_helpers` -- and `materialize` puts it back into
    the index by hand (`tree_gitlinks`) so the committed tree still hashes to the
    mirror's.
    """
    return [path for _, _, path in tree_entries(ref)]


def tree_gitlinks(ref: str) -> list[tuple[str, str]]:
    """`(sha, path)` for every submodule entry (mode 160000) in `ref`."""
    raw = git_mirror("ls-tree", "-r", "-z", ref, binary=True)
    out = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) == 3 and parts[1] == b"commit":
            out.append((parts[2].decode(), path.decode("utf-8", "surrogateescape")))
    return out


def show_blob(ref: str, path: str) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(MIRROR), "show", "%s:%s" % (ref, path)],
                          capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def tree_entries(ref: str) -> list[tuple[str, str, str]]:
    """`(mode, sha, path)` for every blob in `ref`, gitlinks dropped."""
    raw = git_mirror("ls-tree", "-r", "-z", ref, binary=True)
    out = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) != 3 or parts[1] != b"blob":
            continue
        out.append((parts[0].decode(), parts[2].decode(),
                    path.decode("utf-8", "surrogateescape")))
    return out


def write_arm_tar(ref: str, dest: Path) -> int:
    """A tar of `ref`, built from raw blobs rather than by `git archive`.

    `git archive` is the obvious tool and it is the wrong one. It honours the
    `.gitattributes` in the tree it is archiving, and setuptools-scm projects —
    matplotlib, seaborn, xarray, pytest — ship

        .git_archival.txt export-subst

    which makes `git archive` rewrite that file's `$Format:%H$` placeholders on the
    way out. The extracted tree then hashes differently from the commit it came from,
    and arm 1 would be running against a `/testbed` that is not `base_commit`. Other
    attributes (`export-ignore`, `eol`) would bite the same way.

    `git cat-file --batch` hands over the stored bytes and applies nothing, so the
    tree hash check downstream is a real check rather than a check of two filters
    agreeing with each other.
    """
    import io
    import tarfile

    entries = tree_entries(ref)
    proc = subprocess.Popen(["git", "-C", str(MIRROR), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        with tarfile.open(dest, "w") as tar:
            for mode, sha, path in entries:
                proc.stdin.write((sha + "\n").encode())
                proc.stdin.flush()
                header = proc.stdout.readline().split()
                if len(header) != 3 or header[1] != b"blob":
                    raise RuntimeError("cat-file lost %s (%s): %r" % (path, sha, header))
                data = proc.stdout.read(int(header[2]))
                proc.stdout.read(1)                     # the record's trailing newline
                info = tarfile.TarInfo(path)
                info.mtime = TAR_MTIME
                if mode == "120000":
                    info.type = tarfile.SYMTYPE
                    info.linkname = data.decode("utf-8", "surrogateescape")
                    tar.addfile(info)
                    continue
                info.mode = 0o755 if mode == "100755" else 0o644
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait()
    return len(entries)


# ---- the container ----------------------------------------------------------------------

class ContainerError(RuntimeError):
    pass


class Container:
    """A long-lived container, addressed by name, driven with `docker exec`.

    Deliberately thin: mini-swe-agent brings its own `DockerEnvironment` for the
    agent's commands and this class must not compete with it. Everything here is
    harness plumbing that runs before the agent starts or after it stops.
    """

    def __init__(self, name: str, image: str, log=None):
        self.name = name
        self.image = image
        self.container_id: str | None = None
        self._log = log or (lambda *_: None)

    # -- lifecycle
    def start(self, container_timeout: str = "4h") -> str:
        subprocess.run(["docker", "rm", "-f", self.name],
                       capture_output=True, check=False)
        cmd = ["docker", "run", "--platform", PLATFORM, "-d", "--name", self.name,
               "-w", TESTBED, self.image, "sleep", container_timeout]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ContainerError("could not start %s from %s: %s"
                                 % (self.name, self.image, proc.stderr.strip()))
        self.container_id = proc.stdout.strip()
        self._log("container %s (%s) up" % (self.name, self.container_id[:12]))
        return self.container_id

    def stop(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, check=False)

    def __enter__(self) -> "Container":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- running things
    def exec(self, script: str, *, check: bool = True, timeout: int = 600,
             workdir: str = TESTBED, env: dict | None = None,
             stdin: bytes | None = None,
             merge_streams: bool = False) -> subprocess.CompletedProcess:
        """Run a script. `merge_streams` puts stderr inline, where SWE-bench expects it.

        The eval script runs under `set -x`, so its trace — including the
        `>>>>> Start Test Output` markers the log parser splits on — goes to stderr
        while the test output goes to stdout. Captured separately and concatenated,
        the markers end up *after* everything they were supposed to bracket and the
        parser sees an empty test region. SWE-bench's own runner merges the two, so
        anything that reads its logs has to as well.
        """
        cmd = ["docker", "exec", "-w", workdir]
        if stdin is not None:
            cmd.append("-i")
        for key, value in (env or {}).items():
            cmd.extend(["-e", "%s=%s" % (key, value)])
        cmd.extend([self.name, "bash", "-c", script])
        proc = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT if merge_streams else subprocess.PIPE,
                              timeout=timeout, check=False)
        result = subprocess.CompletedProcess(
            proc.args, proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            (proc.stderr or b"").decode("utf-8", "replace"))
        if check and result.returncode != 0:
            raise ContainerError("in %s: %s\n-- stdout --\n%s\n-- stderr --\n%s"
                                 % (self.name, script, result.stdout[-4000:], result.stderr[-4000:]))
        return result

    def out(self, script: str, **kwargs) -> str:
        return self.exec(script, **kwargs).stdout.strip()

    # -- moving bytes
    def put_bytes(self, data: bytes, dest: str, mode: str | None = None) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(data)
            tmp = handle.name
        try:
            proc = subprocess.run(["docker", "cp", tmp, "%s:%s" % (self.name, dest)],
                                  capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise ContainerError("docker cp -> %s failed: %s" % (dest, proc.stderr.strip()))
        finally:
            os.unlink(tmp)
        if mode:
            self.exec("chmod %s %s" % (mode, dest), workdir="/")

    def put_text(self, text: str, dest: str, mode: str | None = None) -> None:
        self.put_bytes(text.encode("utf-8"), dest, mode)

    def put_file(self, src: Path, dest: str, mode: str | None = None) -> None:
        self.put_bytes(Path(src).read_bytes(), dest, mode)

    def extract_tar(self, tar_stream, dest: str) -> None:
        """Stream a tar archive straight into the container (no host temp copy)."""
        proc = subprocess.Popen(
            ["docker", "exec", "-i", "-w", "/", self.name, "tar", "-x", "-C", dest],
            stdin=tar_stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise ContainerError("tar -x into %s failed: %s"
                                 % (dest, err.decode("utf-8", "replace")))


# ---- putting the arm's tree in /testbed --------------------------------------------------

#: Remove every tracked *file* from the working tree. Read from `ls-files --stage`
#: rather than `ls-files` so that a submodule entry (mode 160000, a directory to `rm`)
#: is skipped instead of aborting the whole run -- which is what `xargs rm -f` did on
#: `astropy__astropy-7336` in all three arms.
WIPE_TRACKED_FILES = (
    "git ls-files -s -z | while IFS= read -r -d '' entry; do "
    "case \"$entry\" in 160000*) ;; *) rm -f -- \"${entry#*$'\\t'}\" ;; esac; done")


def materialize(container: Container, instance: dict, arm: str, log=print) -> str:
    """Replace `/testbed`'s tracked files with the arm's tree; return the baseline commit.

    Three things this has to get right, and each of them is a way the experiment
    could quietly go wrong instead of loudly failing:

    **Only tracked files are removed.** These images install the package *from*
    `/testbed`, and for matplotlib, scikit-learn and friends that leaves compiled
    extensions (`lib/matplotlib/_path.cpython-311-x86_64-linux-gnu.so`, `build/`,
    `*.egg-info/`) sitting untracked in the tree. Wiping the directory would take the
    environment with it, and rebuilding it is explicitly not on the table.

    **The index is rebuilt from the arm's file list, not from `git add -A`.** An
    `-A` would sweep those same build artifacts into the baseline commit, and the
    first time an agent recompiled anything the extracted patch would carry a binary
    blob. Naming the arm's paths keeps the commit's tree exactly the arm's tree.

    **The result is verified by tree hash.** Git object names are content-addressed
    and identical across repositories, so `HEAD^{tree}` inside the container must
    equal `<ref>^{tree}` in the mirror. That is a byte-for-byte check on the whole
    tree for the price of one `rev-parse`, and it is the check that says "the arm's
    tree landed correctly" without trusting tar, docker cp, or line endings.

    Committing is also what defuses the `.sideword/` trap: arm 2 adds up to 1,766
    files, and any `git add -A` before a diff — the agent's or ours — would put every
    one of them in the prediction patch. Committed, they cannot appear in `git diff`.
    """
    ref = arm_ref(instance, arm)
    want_tree = tree_sha(ref)
    base = instance["base_commit"]

    container.exec("git config --global --add safe.directory %s" % TESTBED, workdir="/")

    # The eval script resets test files with `git checkout <base_commit> -- <files>`,
    # so the base commit's objects have to survive whatever we do to the working tree.
    container.exec("git cat-file -e %s^{commit}" % base)

    env_delta = image_environment_delta(container, base)

    container.exec(WIPE_TRACKED_FILES)

    log("landing %s (%s)" % (ref, want_tree[:12]))
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as handle:
        tar_path = Path(handle.name)
    try:
        write_arm_tar(ref, tar_path)
        with open(tar_path, "rb") as stream:
            container.extract_tar(stream, TESTBED)
    finally:
        tar_path.unlink(missing_ok=True)

    listing = b"\0".join(p.encode("utf-8", "surrogateescape") for p in tree_blobs(ref))
    container.put_bytes(listing, "/tmp/arm-files")
    # `--force` because a repo's own .gitignore has no reason to expect `.sideword/`
    # or, for that matter, any path we are re-adding after `git rm --cached`.
    container.exec("git rm -r --cached -q . && "
                   "git add --force --pathspec-from-file=/tmp/arm-files --pathspec-file-nul")
    # A submodule is part of the tree but not a file: it went into neither the tar nor
    # the pathspec, so the index entry is restored directly and the hash check below
    # stays a check of the whole tree.
    for gitlink_sha, gitlink_path in tree_gitlinks(ref):
        container.exec("git update-index --add --cacheinfo 160000,%s,%s"
                       % (gitlink_sha, shlex.quote(gitlink_path)))
    container.exec("git -c user.name=sideword -c user.email=sideword@invalid "
                   "commit -q --allow-empty -m 'sideword baseline: arm %s (%s)'" % (arm, ref))

    got_tree = container.out("git rev-parse HEAD^{tree}")
    if got_tree != want_tree:
        raise ContainerError(
            "arm %s landed wrong in %s: tree %s in the container, %s in the mirror"
            % (arm, TESTBED, got_tree, want_tree))
    log("arm tree verified (%s)" % got_tree[:12])

    # Only now, so the hash check above compares the arm's tree and nothing else.
    if env_delta.strip():
        applied, detail = apply_patch(container, env_delta, log=lambda *_: None)
        if not applied:
            raise ContainerError(
                "the image's environment delta will not apply to arm %s. Without it "
                "this container is not the container SWE-bench evaluates in.\n%s"
                % (arm, detail[-2000:]))
        # Exactly the delta's own paths, never `git add -A`: at this point the
        # untracked files in `/testbed` are the image's build artifacts, and an `-A`
        # would commit them — the same trap `.sideword/` sets, wearing a different hat.
        touched = sorted({old for old, _ in _DIFF_HEADER.findall(env_delta)} |
                         {new for _, new in _DIFF_HEADER.findall(env_delta)})
        container.put_bytes(b"\0".join(t.encode("utf-8", "surrogateescape") for t in touched),
                            "/tmp/env-files")
        container.exec("git add --force --pathspec-from-file=/tmp/env-files "
                       "--pathspec-file-nul && "
                       "git -c user.name=sideword -c user.email=sideword@invalid "
                       "commit -q --allow-empty -m 'image environment'")
        log("image environment restored: %s" % ", ".join(touched[:4]))

    baseline = container.out("git rev-parse HEAD")
    log("baseline %s" % baseline[:12])
    return baseline


def image_environment_delta(container: Container, base_commit: str) -> str:
    """What the image build changed in `/testbed` relative to `base_commit`.

    SWE-bench does not ship a pristine checkout. Building an instance image runs a
    per-repo setup script, and for some repos that script edits tracked configuration
    so the official harness can read the results: sphinx-11445's `tox.ini` gains the
    `-rA` that turns pytest's compact progress dots into the `PASSED <nodeid>` lines
    its log parser needs; astropy-14598's `pyproject.toml` gains a pin.

    Landing an arm's tree wipes those edits, and the failure they cause is quiet.
    Sphinx's gold patch made all ten tests pass and still scored unresolved, because
    without `-rA` the parser found no test results at all — and it looked exactly
    like a stripped tree breaking the suite.

    So the delta is captured before the wipe and replayed after it. It is a property
    of the *image*, which is a property of the instance, so all three arms get the
    same one and none of them gains anything the others do not.

    `core.fileMode=false` because Docker Desktop's VM reports executable bits that
    the index disagrees with; without it this returns a mode-only diff of every file
    in the repository — 4,433 of them for matplotlib.
    """
    return container.exec("git -c core.fileMode=false diff %s" % base_commit,
                          check=False, timeout=300).stdout


def arm_test_files_match_base(instance: dict, arm: str) -> list[str]:
    """Test files that differ between the arm's tree and `base_commit`. Should be empty.

    The converter never strips a test path, and the eval script restores test files
    from `base_commit` regardless — but if a test file *were* stripped, arms 2 and 3
    would be running different tests than arm 1 right up to the moment of scoring.
    """
    ref = arm_ref(instance, arm)
    base = instance["base_commit"]
    if ref == base:
        return []
    extra = set(instance.get("test_patch_paths") or [])
    changed = git_mirror("diff", "--name-only", base, ref).split("\n")
    return sorted(p for p in changed if p and pathrules.is_test_path(p, extra))


def reset_atimes(container: Container) -> None:
    """Zero every atime under `/testbed`, then plant the marker the sweep compares against.

    Docker Desktop's VM mounts with `relatime`, which updates atime whenever the
    stored atime is older than mtime. Setting it to the epoch guarantees the first
    read of any file moves it, so a single `find -anewer` at the end names every file
    the agent opened. Without the reset, setup's own `git add` has already read the
    whole tree and the sweep returns everything.

    `core.trustctime=false` is the other half, and without it the measurement is
    worthless. `touch -a` writes atime, and writing any inode field also bumps ctime;
    git stores ctime in the index's stat cache, so every file suddenly looks
    possibly-modified and the agent's very first `git status` or `git diff` re-reads
    the entire repository to find out. That is a real read of a real file and the
    sweep counts it: on flask it turned 5 files read into 248. Telling git not to
    trust ctime restores the cache the reset invalidated and changes nothing else —
    mtime and size still decide whether a file is dirty, and it is set identically in
    all three arms.
    """
    container.exec("git config --global core.trustctime false", workdir="/")
    container.exec(
        "find %s -path %s/.git -prune -o -type f -print0 | "
        "xargs -0 -r touch -a -t 197001010001 2>/dev/null; true" % (TESTBED, TESTBED))
    container.exec("touch %s" % ATIME_MARKER, workdir="/")
    # The install probe is a read too, and it is ours, not the agent's.
    container.exec(": > %s 2>/dev/null || true" % SIDEWORD_CALL_LOG, workdir="/")


def files_read(container: Container) -> list[str]:
    """Repo-relative paths whose atime moved after the marker was planted.

    "Read" here means opened, by anything: `cat` and `grep` of course, but also an
    `import` during a test run and, for a file the agent created, its own write. It
    is an upper bound on what reached the model's context and a lower bound on
    nothing, which is the right side to err on for the ablation.
    """
    out = container.out(
        "find %s -path %s/.git -prune -o -type f -anewer %s -print"
        % (TESTBED, TESTBED, ATIME_MARKER), check=False)
    prefix = TESTBED + "/"
    return sorted(line[len(prefix):] if line.startswith(prefix) else line
                  for line in out.split("\n") if line.strip())


# ---- arm 2's retrieval surface -----------------------------------------------------------

#: `/usr/bin/python3` and not `python3`: under the agent's shell `conda activate testbed`
#: has already happened, and a testbed interpreter can be as old as 3.5 (django-7530).
#: Every one of these images is Ubuntu 22.04 underneath, so the system interpreter is
#: 3.10 and identical across instances — one fewer thing that varies by repo.
SIDEWORD_SHIM = """#!/bin/sh
# Logging wrapper: arm 2's whole claim is that retrieval is cheap and targeted, so
# every call has to be on the record. The log lives outside /testbed so it can never
# reach a patch or a test collector.
/usr/bin/python3 %s/sideword_cli.py "$@"
rc=$?
printf '%%s\\t%%s\\t%%s\\n' "$(date +%%s)" "$rc" "$*" >> %s
exit $rc
""" % (SIDEWORD_DIR, SIDEWORD_CALL_LOG)


def install_sideword(container: Container, log=print) -> str:
    """Drop `sideword` into the container and prove it answers. Returns the smoke-test line.

    `harness/sideword_cli.py` and `harness/sidedoc.py` go to `/opt`, not into the
    repository: anything under `/testbed` would show up in `git diff` and, worse,
    would be a `.py` file the repository's own collector might find.
    """
    container.exec("mkdir -p %s" % SIDEWORD_DIR, workdir="/")
    container.put_file(ROOT / "harness" / "sideword_cli.py", "%s/sideword_cli.py" % SIDEWORD_DIR)
    container.put_file(ROOT / "harness" / "sidedoc.py", "%s/sidedoc.py" % SIDEWORD_DIR)
    container.put_text(SIDEWORD_SHIM, "/usr/local/bin/sideword", mode="0755")
    container.exec(": > %s" % SIDEWORD_CALL_LOG, workdir="/")

    probe = container.exec(
        'f=$(cd %s/.sideword && find . -name "*.idx" | sort | head -1); '
        'f=${f#./}; f=${f%%.idx}; echo "PROBE $f"; sideword index "$f" | head -3' % TESTBED)
    log("sideword: %s" % probe.stdout.strip().replace("\n", " | ")[:200])
    return probe.stdout.strip()


def sideword_calls(container: Container) -> list[dict]:
    raw = container.out("cat %s 2>/dev/null || true" % SIDEWORD_CALL_LOG, check=False)
    calls = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        at, _, rest = line.partition("\t")
        rc, _, args = rest.partition("\t")
        calls.append({"at": int(at) if at.isdigit() else None,
                      "returncode": int(rc) if rc.lstrip("-").isdigit() else None,
                      "args": args})
    return calls


# ---- the prompt -------------------------------------------------------------------------
#
# Verbatim from mini-swe-agent 2.4.6, `minisweagent/config/benchmarks/swebench_backticks.yaml`.
# The backticks variant, not the toolcall one, because `claude -p --tools ""` returns
# text and nothing else: the action protocol has to live in the text.
# `harness/tests/test_evaluate.py::TestPromptFidelity` re-reads the installed YAML and
# fails if a single character has moved.

SYSTEM_TEMPLATE = """\
You are a helpful assistant that can interact multiple times with a computer shell to solve programming tasks.
Your response must contain exactly ONE bash code block with ONE command (or commands connected with && or ||).

Include a THOUGHT section before your command where you explain your reasoning process.
Format your response as shown in <format_example>.

<format_example>
THOUGHT: Your reasoning and analysis here

```mswea_bash_command
your_command_here
```
</format_example>

Failure to follow these rules will cause your response to be rejected.
"""

#: Where arm 2's block goes, and the only edit made to upstream's instance template.
#: It sits after the boundaries section because that is where the message stops being
#: about the task and starts being about the repository the task lives in.
SIDEWORD_MARKER = "@@SIDEWORD_BLOCK@@"

_UPSTREAM_INSTANCE_TEMPLATE = """\
<pr_description>
Consider the following PR description:
{{task}}
</pr_description>

<instructions>
# Task Instructions

## Overview

You're a software engineer interacting continuously with a computer by submitting commands.
You'll be helping implement necessary changes to meet requirements in the PR description.
Your task is specifically to make changes to non-test files in the current directory in order to fix the issue described in the PR description in a way that is general and consistent with the codebase.

<IMPORTANT>This is an interactive process where you will think and issue ONE command, see its result, then think and issue your next command.</IMPORTANT>

For each response:

1. Include a THOUGHT section explaining your reasoning and what you're trying to accomplish
2. Provide exactly ONE bash command to execute

## Important Boundaries

- MODIFY: Regular source code files in /testbed (this is the working directory for all your subsequent commands)
- DO NOT MODIFY: Tests, configuration files (pyproject.toml, setup.cfg, etc.)

## Recommended Workflow

1. Analyze the codebase by finding and reading relevant files
2. Create a script to reproduce the issue
3. Edit the source code to resolve the issue
4. Verify your fix works by running your script again
5. Test edge cases to ensure your fix is robust

## Command Execution Rules

You are operating in an environment where

1. You write a single command
2. The system executes that command in a subshell
3. You see the result
4. You write your next command

Each response should include:

1. A **THOUGHT** section where you explain your reasoning and plan
2. A single bash code block with your command

Format your responses like demonstrated within the <format_example> block:

<format_example>
THOUGHT: Here I explain my reasoning process, analysis of the current situation,
and what I'm trying to accomplish with the command below.

```mswea_bash_command
your_command_here
```
</format_example>

Commands must be specified in a single bash code block:

```mswea_bash_command
your_command_here
```

**CRITICAL REQUIREMENTS:**

- Your response SHOULD include a THOUGHT section explaining your reasoning
- Your response MUST include EXACTLY ONE bash code block
- This bash block MUST contain EXACTLY ONE command (or a set of commands connected with && or ||)
- If you include zero or multiple bash blocks, or no command at all, YOUR RESPONSE WILL FAIL
- Do NOT try to run multiple independent commands in separate blocks in one response
- Directory or environment variable changes are not persistent. Every action is executed in a new subshell.
- However, you can prefix any action with `MY_ENV_VAR=MY_VALUE cd /path/to/working/dir && ...` or write/load environment variables from files

Example of a CORRECT response:
<example_response>
THOUGHT: I need to understand the structure of the repository first. Let me check what files are in the current directory to get a better understanding of the codebase.

```mswea_bash_command
ls -la
```
</example_response>

Example of an INCORRECT response:

<example_response>
THOUGHT: I need to examine the codebase and then look at a specific file. I'll run multiple commands to do this.

```mswea_bash_command
ls -la
```

Now I'll read the file:

```mswea_bash_command
cat file.txt
```
</example_response>

If you need to run multiple commands, either:

1. Combine them in one block using && or ||
```mswea_bash_command
command1 && command2 || echo "Error occurred"
```

2. Wait for the first command to complete, see its output, then issue the next command in your following response.

## Environment Details

- You have a full Linux shell environment
- Always use non-interactive flags (-y, -f) for commands
- Avoid interactive tools like vi, nano, or any that require user input
- You can use bash commands or invoke any tool that is available in the environment
- You can also create new tools or scripts to help you with the task
- If a tool isn't available, you can also install it

## Submission

When you've completed your work, you MUST submit your changes as a git patch.
Follow these steps IN ORDER, with SEPARATE commands:

Step 1: Create the patch file
Run `git diff -- path/to/file1 path/to/file2 > patch.txt` listing only the source files you modified.
Do NOT commit your changes.

<IMPORTANT>
The patch must only contain changes to the specific source files you modified to fix the issue.
Do not submit file creations or changes to any of the following files:

- test and reproduction files
- helper scripts, tests, or tools that you created
- installation, build, packaging, configuration, or setup scripts unless they are directly part of the issue you were fixing (you can assume that the environment is already set up for your client)
- binary or compiled files
</IMPORTANT>

Step 2: Verify your patch
Inspect patch.txt to confirm it only contains your intended changes and headers show `--- a/` and `+++ b/` paths.

Step 3: Submit (EXACT command required)
You MUST use this EXACT command to submit:

```mswea_bash_command
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt
```

If the command fails (nonzero exit status), it will not submit.

<CRITICAL>
- Creating/viewing the patch and submitting it MUST be separate commands (not combined with &&).
- If you modify patch.txt after verifying, you SHOULD verify again before submitting.
- You CANNOT continue working (reading, editing, testing) in any way on this task after submitting.
</CRITICAL>
</instructions>
"""

_BOUNDARIES_ANCHOR = (
    "- DO NOT MODIFY: Tests, configuration files (pyproject.toml, setup.cfg, etc.)\n"
    "\n"
    "## Recommended Workflow\n"
)

INSTANCE_TEMPLATE = _UPSTREAM_INSTANCE_TEMPLATE.replace(
    _BOUNDARIES_ANCHOR,
    "- DO NOT MODIFY: Tests, configuration files (pyproject.toml, setup.cfg, etc.)\n"
    "\n" + SIDEWORD_MARKER + "## Recommended Workflow\n")

OBSERVATION_TEMPLATE = """\
{% if output.exception_info -%}
<exception>{{output.exception_info}}</exception>
{% endif -%}
<returncode>{{output.returncode}}</returncode>
{% if output.output | length < 10000 -%}
<output>
{{ output.output -}}
</output>
{%- else -%}
<warning>
The output of your last command was too long.
Please try a different command that produces less output.
If you're looking at a file you can try use head, tail or sed to view a smaller number of lines selectively.
If you're using grep or find and it produced too much output, you can use a more selective search pattern.
If you really need to see something from the full command's output, you can redirect output to a file and then search in that file.
</warning>
{%- set elided_chars = output.output | length - 10000 -%}
<output_head>
{{ output.output[:5000] }}
</output_head>
<elided_chars>
{{ elided_chars }} characters elided
</elided_chars>
<output_tail>
{{ output.output[-5000:] }}
</output_tail>
{%- endif -%}
"""

FORMAT_ERROR_TEMPLATE = """\
{% if finish_reason is defined and finish_reason in ["length", "tool_calls"] -%}
Your previous response reached the output token limit (finish_reason={{ finish_reason }}) before you produced a complete action, so it was cut off. Respond more concisely and provide exactly one action in the required format. If you need to think more, do so briefly.
{%- else -%}
Format error:

<error>
{{error}}
</error>

Here is general guidance on how to format your response:

Please always provide EXACTLY ONE action in triple backticks, found {{actions|length}} actions.

Please format your action in triple backticks as shown in <response_example>.

<response_example>
Here are some thoughts about why you want to perform the action.

```mswea_bash_command
<action>
```
</response_example>

If you have completed your assignment, please consult the first message about how to
submit your solution (you will not be able to continue working on this task after that).
{%- endif %}
"""

ACTION_REGEX = r"```mswea_bash_command\s*\n(.*?)\n```"

#: Upstream `swebench_backticks.yaml`'s environment, plus the one addition documented
#: in the module docstring.
AGENT_ENV = {
    "PAGER": "cat",
    "MANPAGER": "cat",
    "LESS": "-R",
    "PIP_PROGRESS_BAR": "off",
    "TQDM_DISABLE": "1",
    "BASH_ENV": "/root/.bashrc",
}
AGENT_INTERPRETER = ["bash", "-c"]


def sideword_block(arm: str) -> str:
    """Arm 2's prompt block, and nothing at all for the other two."""
    if arm != "sw":
        return ""
    text = ARM2_PROMPT_FILE.read_text(encoding="utf-8").strip("\n")
    return text + "\n\n"


def instance_template(arm: str) -> str:
    """The task message template for this arm.

    For arms 1 and 3 the substitution is empty and the result is byte-identical to
    mini-swe-agent's own template; the only permitted difference between arms is the
    block itself.
    """
    return INSTANCE_TEMPLATE.replace(SIDEWORD_MARKER, sideword_block(arm))


def agent_config(arm: str, *, step_limit: int, cost_limit: float,
                 wall_limit: int, action_timeout: int) -> dict:
    return {
        "system_template": SYSTEM_TEMPLATE,
        "instance_template": instance_template(arm),
        "step_limit": step_limit,
        "cost_limit": cost_limit,
        "wall_time_limit_seconds": wall_limit,
        "action_regex": ACTION_REGEX,
        "observation_template": OBSERVATION_TEMPLATE,
        "format_error_template": FORMAT_ERROR_TEMPLATE,
        "environment": {
            "cwd": TESTBED,
            "timeout": action_timeout,
            "interpreter": list(AGENT_INTERPRETER),
            "env": dict(AGENT_ENV),
        },
    }


def config_digest(config: dict) -> str:
    """A hash over everything that shapes the run, so two records can be compared."""
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---- the model: `claude -p` as a mini-swe-agent Model -------------------------------------

RATE_LIMIT_RE = re.compile(r"rate.?limit|429|too many requests|overloaded|usage limit|"
                           r"hit your limit|limit reached|out of extra usage|529", re.IGNORECASE)
HARD_BLOCK_RE = re.compile(r"usage limit|hit your limit|limit reached|out of extra usage|"
                           r"spend limit|usage-credits|resets? at|5.hour", re.IGNORECASE)


#: Exit statuses of an agent run. 0 is a run that finished and was scored; a run
#: that ended in an `allowance-exhausted` error (the account's spend limit) exits
#: EXIT_ALLOWANCE_EXHAUSTED, and any other recorded error EXIT_AGENT_ERROR -- the
#: record is still written in both cases, but the exit code no longer says "fine".
EXIT_AGENT_ERROR = 2
EXIT_ALLOWANCE_EXHAUSTED = 3


class AllowanceExhausted(RuntimeError):
    """The account is blocked, not merely throttled. Retrying only wastes the run."""


def claude_env() -> dict:
    """A minimal environment for the headless CLI.

    Inherited `CLAUDE_*` session variables break auth, so nothing is passed through
    except `CLAUDE_CONFIG_DIR` — which is how the CLI chooses *which account to bill*.
    Getting that wrong is not a slow failure: it silently spends the wrong allowance.
    `harness/convert_pilot.py` established this shape; the mandatory-ness is new.
    """
    config_dir = os.environ.get("SIDEWORD_CLAUDE_CONFIG_DIR")
    if not config_dir:
        raise SystemExit(
            "SIDEWORD_CLAUDE_CONFIG_DIR is not set. It selects the account the run bills, "
            "and without it the CLI falls back to ~/.claude. Set it explicitly, e.g.\n"
            "    export SIDEWORD_CLAUDE_CONFIG_DIR=$HOME/.claude2")
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("`claude` is not on PATH")
    # Both the directory the shim lives in and the directory it resolves to. Under
    # nvm those differ: `which claude` is `~/.nvm/.../bin/claude`, whose realpath is
    # `~/.nvm/.../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`. Keeping
    # only the resolved one drops `node` off the PATH of a stripped environment.
    bins = [os.path.dirname(claude), os.path.dirname(os.path.realpath(claude))]
    path = ":".join(["/usr/bin", "/bin"] + list(dict.fromkeys(bins)))
    return {"HOME": os.environ["HOME"], "PATH": path,
            "USER": os.environ.get("USER", ""), "TERM": "dumb",
            "CLAUDE_CONFIG_DIR": config_dir}


class ClaudeCliModel:
    """mini-swe-agent's `Model` protocol, served by `claude -p` on the subscription.

    The CLI is a session, not a completion endpoint, so the conversation is carried
    by `--session-id` on the first call and `--resume` after it, and each call sends
    only the messages the session has not seen. Replaying the whole transcript every
    turn would work too and would cost a quadratic number of tokens — which matters
    here, because tokens are one of the things being measured.

    `--tools ""` is load-bearing. mini-swe-agent supplies the shell; if the CLI kept
    its own Read, Edit and Bash, arm 2's `sideword` would be one tool among many and
    the tool surface would no longer be the same object across arms.
    """

    def __init__(self, *, model_name: str, action_regex: str, format_error_template: str,
                 observation_template: str, effort: str | None = None,
                 call_timeout: int = 900, max_attempts: int = 3, log=print):
        self.config = _ModelConfig(
            model_name=model_name, action_regex=action_regex,
            format_error_template=format_error_template,
            observation_template=observation_template,
            effort=effort, call_timeout=call_timeout, max_attempts=max_attempts)
        self.session_id = str(uuid.uuid4())
        self.calls: list[dict] = []
        self.cost = 0.0
        self._cursor = 0
        self._started = False
        self._system_prompt_file: str | None = None
        self._workdir = tempfile.mkdtemp(prefix="sideword-claude-")
        self._log = log

    # -- protocol
    def format_message(self, **kwargs) -> dict:
        return dict(kwargs)

    def get_template_vars(self, **kwargs) -> dict:
        out = self.config.as_dict()
        out.update(kwargs)
        return out

    def serialize(self) -> dict:
        return {"info": {"config": {"model": self.config.as_dict(),
                                    "model_type": "%s.%s" % (type(self).__module__,
                                                             type(self).__name__),
                                    "session_id": self.session_id,
                                    "workdir": self._workdir}}}

    def format_observation_messages(self, message: dict, outputs: list[dict],
                                    template_vars: dict | None = None) -> list[dict]:
        from minisweagent.models.utils.actions_text import format_observation_messages
        return format_observation_messages(
            outputs, observation_template=self.config.observation_template,
            template_vars=template_vars)

    def query(self, messages: list[dict], **kwargs) -> dict:
        from minisweagent.exceptions import FormatError
        from minisweagent.models.utils.actions_text import parse_regex_actions

        delta = messages[self._cursor:]
        self._cursor = len(messages)
        # Anything the model produced is already in the CLI's own session; only the
        # system prompt and the user turns need sending. Slicing this way rather than
        # by index arithmetic keeps the two views in step across the format-error
        # path, where the agent appends a user message and no assistant message.
        system = "\n\n".join(m.get("content", "") for m in delta if m.get("role") == "system")
        user = "\n\n".join(m.get("content", "") for m in delta if m.get("role") == "user")
        if system and not self._started:
            self._system_prompt_file = os.path.join(self._workdir, "system-prompt.txt")
            Path(self._system_prompt_file).write_text(system, encoding="utf-8")

        result = self._call(user)
        self._started = True

        content = result.get("result") or ""
        usage = result.get("usage") or {}
        cost = float(result.get("total_cost_usd") or 0.0)
        self.cost += cost
        extra = {
            "cost": cost,
            "usage": usage,
            "model_usage": result.get("modelUsage"),
            "num_turns": result.get("num_turns"),
            "duration_ms": result.get("duration_ms"),
            "session_id": result.get("session_id"),
            "timestamp": time.time(),
        }
        try:
            actions = parse_regex_actions(
                content, action_regex=self.config.action_regex,
                format_error_template=self.config.format_error_template,
                template_kwargs={"finish_reason": result.get("stop_reason")})
        except FormatError as exc:
            # The call was billed before parsing failed; the agent adds this back to
            # its running total only if it finds it here.
            exc.messages[0]["extra"].update(extra)
            raise
        return {"role": "assistant", "content": content, "extra": dict(extra, actions=actions)}

    # -- the subprocess
    def _cmd(self) -> list[str]:
        cmd = ["claude", "-p", "--model", self.config.model_name,
               "--output-format", "json", "--tools", "", "--safe-mode"]
        if self.config.effort:
            cmd += ["--effort", self.config.effort]
        if self._started:
            cmd += ["--resume", self.session_id]
        else:
            cmd += ["--session-id", self.session_id]
            if self._system_prompt_file:
                cmd += ["--system-prompt-file", self._system_prompt_file]
        return cmd

    def _call(self, prompt: str) -> dict:
        env = claude_env()
        delay = 30
        last = ""
        for attempt in range(1, self.config.max_attempts + 1):
            started = time.time()
            try:
                proc = subprocess.run(self._cmd(), input=prompt, capture_output=True, text=True,
                                      env=env, timeout=self.config.call_timeout,
                                      cwd=self._workdir)
                stdout, stderr, rc = proc.stdout.strip(), proc.stderr, proc.returncode
            except subprocess.TimeoutExpired:
                stdout, stderr, rc = "", "timeout after %ds" % self.config.call_timeout, -1
            wall_ms = int(1000 * (time.time() - started))

            parsed = None
            for candidate in (stdout, stdout.splitlines()[-1] if stdout else ""):
                try:
                    parsed = json.loads(candidate)
                    break
                except Exception:
                    continue
            ok = bool(parsed) and not parsed.get("is_error")
            self.calls.append({
                "attempt": attempt, "ok": ok, "wall_ms": wall_ms, "returncode": rc,
                "usage": (parsed or {}).get("usage"),
                "cost_usd": (parsed or {}).get("total_cost_usd"),
                "model_usage": (parsed or {}).get("modelUsage"),
                "at": dt.datetime.now().isoformat(timespec="seconds"),
                "error": None if ok else (stderr or stdout)[-500:],
            })
            if ok:
                return parsed
            last = "%s %s" % (stderr[-2000:], stdout[-2000:])
            if HARD_BLOCK_RE.search(last):
                raise AllowanceExhausted(
                    "the account is blocked, not throttled — stopping rather than "
                    "burning the run: %s" % last.strip()[-400:])
            if attempt < self.config.max_attempts and RATE_LIMIT_RE.search(last):
                if not self._started:
                    # The failed attempt may have created the session before dying,
                    # and `--session-id` on an id that already exists is an error.
                    # Nothing has been said yet, so a fresh id costs nothing.
                    self.session_id = str(uuid.uuid4())
                self._log("model call throttled, retrying in %ds" % delay)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("claude -p failed after %d attempts: %s"
                           % (self.config.max_attempts, last.strip()[-800:]))


class ScriptedModel(ClaudeCliModel):
    """`ClaudeCliModel` with the subprocess replaced by a recorded list of replies.

    Not a mock of the agent: everything downstream of the subprocess — the action
    regex, the format-error path, the cursor, the cost arithmetic, the record — is
    the same code a real run executes. Only `claude -p` is stood in for.

    That makes it the way to exercise the whole loop, and the whole scoring path
    behind it, while the allowance is out; and afterwards, the way to replay a
    trajectory against a changed harness and see whether the change moved anything.
    """

    def __init__(self, script: list, **kwargs):
        super().__init__(**kwargs)
        self._script = list(script)

    def _call(self, prompt: str) -> dict:
        if not self._script:
            raise RuntimeError(
                "the script ran out after %d replies; the agent wanted another"
                % len(self.calls))
        reply = self._script.pop(0)
        text = reply if isinstance(reply, str) else reply.get("result", "")
        result = {"result": text, "usage": {}, "total_cost_usd": 0.0,
                  "session_id": self.session_id, "num_turns": 1, "duration_ms": 0}
        if isinstance(reply, dict):
            result.update({k: v for k, v in reply.items() if k != "result"})
        self.calls.append({"attempt": 1, "ok": True, "wall_ms": 0, "returncode": 0,
                           "usage": result["usage"], "cost_usd": result["total_cost_usd"],
                           "model_usage": None, "scripted": True,
                           "at": dt.datetime.now().isoformat(timespec="seconds"),
                           "error": None})
        return result


class _ModelConfig:
    """A stand-in for the pydantic config mini-swe-agent's own models carry.

    Plain attributes, so that importing `harness.evaluate` needs nothing but the
    standard library and the corpus — the agent's dependencies load when a run
    actually starts, not when a test imports this module.
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def as_dict(self) -> dict:
        return dict(self.__dict__)

    # mini-swe-agent calls `.model_dump()` on model configs in a couple of places.
    def model_dump(self, **_) -> dict:
        return self.as_dict()


# ---- the environment: mini-swe-agent's DockerEnvironment, on our container -----------------

def prepared_environment(container: Container, config: dict, actions: list) -> object:
    """mini-swe-agent's `DockerEnvironment`, attached to a container we already built.

    Subclassing rather than reimplementing is the point: `execute` — the entire tool
    surface the agent sees — stays upstream's code, byte for byte, in all three arms.
    Only two things are overridden, and neither touches a command: where the container
    comes from, and who is allowed to kill it.
    """
    from minisweagent.environments.docker import DockerEnvironment

    class PreparedDockerEnvironment(DockerEnvironment):
        def _start_container(self):
            self.container_id = container.container_id

        def cleanup(self):
            pass

        def execute(self, action, cwd: str = "", *, timeout: int | None = None):
            started = time.time()
            output = super().execute(action, cwd, timeout=timeout)
            actions.append({
                "i": len(actions),
                "command": action.get("command", ""),
                "returncode": output.get("returncode"),
                "output_bytes": len(output.get("output", "")),
                "output_tokens_est": estimate_tokens(output.get("output", "")),
                "duration_s": round(time.time() - started, 3),
            })
            return output

    env_config = config["environment"]
    return PreparedDockerEnvironment(
        image=container.image, cwd=env_config["cwd"], env=env_config["env"],
        timeout=env_config["timeout"], interpreter=env_config["interpreter"],
        run_args=[])


def estimate_tokens(text: str) -> int:
    """Four characters to a token. A ruler, not a scale.

    Every number in the record that matters — input, output, cache reads — comes from
    the CLI's own `usage`. This is only for attributing bytes to individual commands,
    where no per-call ground truth exists.
    """
    return (len(text) + 3) // 4


# ---- patches ------------------------------------------------------------------------------

def extract_patch(container: Container, baseline: str) -> str:
    """What the agent changed, as `git diff` against the arm's baseline commit.

    Diffing against a *commit* rather than the index is what SWE-bench does, and it
    means untracked files — the agent's reproduction scripts, `patch.txt`, `build/` —
    are structurally incapable of reaching the prediction.
    """
    return container.exec("git -c core.fileMode=false diff %s" % baseline,
                          timeout=300).stdout


def strip_bytes(src: bytes, like: bytes | None = None) -> bytes:
    """Strip `src` the way pass 1 stripped the file `like` is the arm's copy of.

    Pass 1 keeps some docstrings for reasons outside the file -- the consumption
    analysis and the per-repo tier, handed to the stripper as `keep_owners`. The arm's
    blob is the record of that decision: whatever docstring still sits in it was kept,
    so the same owners are kept here and the derived patch does not delete them.
    """
    import ast
    import re
    from harness import astcheck as astcheck_mod
    from harness import directives as directives_mod
    from harness import strip as strip_mod
    keep_owners = []
    if like is not None:
        try:
            tree = ast.parse(like)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            keep_owners = [(re.escape(owner), "arm-tree")
                           for _, owner, _ in astcheck_mod.remaining_docstrings(tree)]
    out, _ = strip_mod.strip_source(src, directives_mod.load(directives_mod.DEFAULT_PATH),
                                    keep_owners)
    return out


def arm_gold_patch(instance: dict, row: dict, arm: str) -> str:
    """The instance's gold patch, expressed against *this arm's* tree.

    A patch is a set of context lines, and arms 2 and 3 deleted most of the context:
    the dataset's gold patch cannot apply to a stripped file. So it is re-derived —
    apply gold to the original blobs, strip the result the same way pass 1 stripped
    the tree, and diff that against the arm's own blobs.

    Which files get stripped is decided by comparing the arm's blob to the base blob
    rather than by re-running the test-path rule. If the converter left a file alone,
    whatever its reason, this leaves it alone too, and the derivation cannot disagree
    with the tree it has to apply to.

    This exists to check the scoring path, not to run the experiment. Arm 1 gets the
    dataset's patch untouched.
    """
    if arm == "orig":
        return row["patch"]

    base = instance["base_commit"]
    ref = arm_ref(instance, arm)
    touched = _DIFF_HEADER.findall(row["patch"])
    paths = sorted({old for old, _ in touched} | {new for _, new in touched})

    with tempfile.TemporaryDirectory(prefix="sideword-gold-") as work:
        work_dir = Path(work)
        orig_dir = work_dir / "orig"
        for path in paths:
            blob = show_blob(base, path)
            if blob is None:
                continue
            target = orig_dir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        orig_dir.mkdir(parents=True, exist_ok=True)

        patch_file = work_dir / "gold.patch"
        patch_file.write_text(row["patch"], encoding="utf-8")
        proc = subprocess.run(["git", "apply", "-p1", "--verbose", str(patch_file)],
                              cwd=orig_dir, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError("gold patch will not apply to %s's base blobs: %s"
                               % (instance["instance_id"], proc.stderr[-2000:]))

        # A throwaway repository, rather than `git diff --no-index` on two
        # directories: --no-index folds the directory names into the paths, and the
        # result is a patch against `a/a/src/...` that applies nowhere. One commit
        # for the arm's side, the stripped result on top, and `git diff` writes the
        # `a/<path>`/`b/<path>` headers the container's `git apply -p1` expects.
        repo = work_dir / "repo"
        repo.mkdir()
        run_git = lambda *a: subprocess.run(["git", "-C", str(repo), *a],
                                            capture_output=True, text=True, check=True)
        run_git("init", "-q")
        extra_tests = set(instance.get("test_patch_paths") or [])
        for path in paths:
            arm_blob = show_blob(ref, path)
            if arm_blob is None:
                continue
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_bytes(arm_blob)
        run_git("add", "--force", "-A")
        run_git("-c", "user.name=sideword", "-c", "user.email=sideword@invalid",
                "commit", "-q", "--allow-empty", "-m", "arm side")

        for path in paths:
            arm_blob = show_blob(ref, path)
            base_blob = show_blob(base, path)
            patched = orig_dir / path
            target = repo / path
            if not patched.exists():
                if target.exists():
                    target.unlink()
                continue
            data = patched.read_bytes()
            # Strip iff the converter stripped this file. Asking the tree rather than
            # re-deriving the test-path rule means the derivation cannot disagree with
            # the tree it has to apply to — including for files pass 1 declined.
            was_stripped = (arm_blob is not None and base_blob is not None
                            and arm_blob != base_blob)
            is_new = arm_blob is None
            if was_stripped or (is_new and path.endswith(".py")
                                and not pathrules.is_test_path(path, extra_tests)):
                data = strip_bytes(data, arm_blob)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        run_git("add", "--force", "-A")
        diff = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.fileMode=false", "diff", "--no-color", "HEAD"],
            capture_output=True, text=True, check=False)
        if diff.returncode != 0:
            raise RuntimeError("git diff failed: %s" % diff.stderr[-2000:])
        return diff.stdout


def apply_patch(container: Container, patch: str, log=print) -> tuple[bool, str]:
    """SWE-bench's own apply ladder, in SWE-bench's own order."""
    if not patch.strip():
        return True, "(empty patch, nothing applied)"
    container.put_text(patch, "/tmp/patch.diff")
    last = ""
    for cmd in GIT_APPLY_CMDS:
        proc = container.exec("%s /tmp/patch.diff" % cmd, check=False, timeout=300)
        if proc.returncode == 0:
            log("patch applied with `%s`" % cmd)
            return True, proc.stdout[-4000:]
        last = (proc.stdout + proc.stderr)[-4000:]
    return False, last


# ---- scoring ------------------------------------------------------------------------------

def eval_script(test_spec, baseline: str, base_commit: str) -> str:
    """SWE-bench's eval script, with its two informational lines re-pointed.

    `git show` and `git diff <base_commit>` are marked in SWE-bench's own source as
    "just informational, so we have a record". Left alone they are a problem here and
    only here: our baseline is a fresh commit, so `git show` prints the entire arm
    tree as a diff and `git diff <base_commit>` prints the whole strip — tens of
    megabytes of log for arms 2 and 3, before a single test has run.

    Re-pointed, they print what they were meant to print: the commit under test, and
    the change the model made. Nothing that decides an outcome is touched — the test
    reset still comes from `base_commit`, because test files are the one thing the
    conversion never altered and all three arms must run byte-identical tests.
    """
    lines = []
    for line in test_spec.eval_script_list:
        if line == "git show":
            lines.append("git log -1 --format='%H %s'")
        elif line == "git -c core.fileMode=false diff %s" % base_commit:
            lines.append("git -c core.fileMode=false diff %s" % baseline)
        else:
            lines.append(line)
    return "\n".join(["#!/bin/bash", "set -uxo pipefail"] + lines) + "\n"


def score(instance: dict, row: dict, arm: str, patch: str, *, out_dir: Path,
          model_label: str, keep: bool = False, test_timeout: int = 1800,
          log=print) -> dict:
    """Apply the patch in a clean container and run SWE-bench's evaluation.

    A *fresh* container, not the agent's: an agent that pip-installs something, edits
    a conftest or leaves a stray `sitecustomize.py` behind would otherwise be scored
    in the environment it just disturbed. SWE-bench evaluates in a new container for
    the same reason, and re-using `materialize` here means the tree under test is
    built by exactly the code that built the tree the agent saw.
    """
    from swebench.harness.grading import get_eval_report
    from swebench.harness.test_spec.test_spec import make_test_spec
    try:
        from importlib.metadata import version as _dist_version
        swebench_version = _dist_version("swebench")
    except Exception:
        swebench_version = "unknown"

    spec = make_test_spec(row)
    name = "sweval-score-%s-%s" % (instance["instance_id"].replace("__", "-"), arm)
    log_path = out_dir / ("%s.%s.eval.log" % (instance["instance_id"], arm))
    out_dir.mkdir(parents=True, exist_ok=True)

    container = Container(name, image_name(instance["instance_id"]), log=log)
    started = time.time()
    try:
        container.start()
        baseline = materialize(container, instance, arm, log=log)
        applied, detail = apply_patch(container, patch, log=log)
        if not applied:
            log("patch did not apply:\n%s" % detail[-1500:])
            log_path.write_text("SWEBENCH_HARNESS: patch failed to apply\n" + detail,
                                encoding="utf-8")
            return {
                "swebench": swebench_version,
                "baseline_commit": baseline,
                "resolved": False, "patch_applied": False, "apply_output": detail,
                "log_path": _rel(log_path),
                "test_cmd": _test_cmd(spec), "status_map": {},
                "FAIL_TO_PASS": {"success": [], "failure": list(instance["FAIL_TO_PASS"])},
                "PASS_TO_PASS": {"success": [], "failure": list(instance["PASS_TO_PASS"])},
                "wall_s": round(time.time() - started, 1),
            }
        container.put_text(eval_script(spec, baseline, instance["base_commit"]), "/eval.sh")
        try:
            proc = container.exec("/bin/bash /eval.sh", check=False, timeout=test_timeout,
                                  merge_streams=True)
            log_path.write_text(proc.stdout, encoding="utf-8")
        except subprocess.TimeoutExpired as exc:
            # A hung test suite is a result, not a crash. SWE-bench's own parser reads
            # this marker and reports the instance unresolved; writing it keeps the
            # record shaped like every other record.
            partial = (exc.output or b"").decode("utf-8", "replace") if exc.output else ""
            log_path.write_text(partial + "\n>>>>> Tests Timed Out after %d seconds\n"
                                % test_timeout, encoding="utf-8")
            log("evaluation timed out after %ds" % test_timeout)

        report = get_eval_report(
            test_spec=spec,
            prediction={"instance_id": instance["instance_id"],
                        "model_name_or_path": model_label,
                        "model_patch": patch},
            test_log_path=str(log_path),
            include_tests_status=True)
        entry = report[instance["instance_id"]]
        tests = entry.get("tests_status", {})
        return {
            "swebench": swebench_version,
            "baseline_commit": baseline,
            "resolved": bool(entry.get("resolved")),
            "patch_applied": bool(entry.get("patch_successfully_applied")),
            "apply_output": detail,
            "log_path": _rel(log_path),
            "test_cmd": _test_cmd(spec),
            "status_map": _status_map(spec, log_path),
            "FAIL_TO_PASS": tests.get("FAIL_TO_PASS", {"success": [], "failure": []}),
            "PASS_TO_PASS": tests.get("PASS_TO_PASS", {"success": [], "failure": []}),
            "wall_s": round(time.time() - started, 1),
        }
    finally:
        if keep:
            log("keeping scoring container %s" % name)
        else:
            container.stop()


def _test_cmd(spec) -> str:
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    cmd = MAP_REPO_VERSION_TO_SPECS[spec.repo][spec.version]["test_cmd"]
    return cmd[-1] if isinstance(cmd, list) else cmd


def _status_map(spec, log_path: Path) -> dict:
    """Every test the run reported, not just the ones on the two lists."""
    from swebench.harness.grading import get_logs_eval
    try:
        status_map, _ = get_logs_eval(spec, str(log_path))
        return status_map
    except Exception:
        return {}


# ---- the run ------------------------------------------------------------------------------

def _rel(path: Path) -> str:
    """Repo-relative when it can be, absolute when the caller pointed `--out` elsewhere."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def record_path(out_root: Path, model: str, arm: str, instance_id: str, source: str) -> Path:
    suffix = "" if source == "agent" else ".%s" % source
    return out_root / model / arm / ("%s%s.json" % (instance_id, suffix))


def run(args) -> int:
    def log(message: str) -> None:
        print("[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), message), flush=True)

    instance = get_instance(args.instance)
    arm = args.arm
    ref = arm_ref(instance, arm)
    image = image_name(instance["instance_id"])
    out_root = Path(args.out) if args.out else EVAL_ROOT
    out_dir = out_root / args.model / arm
    out_dir.mkdir(parents=True, exist_ok=True)

    config = agent_config(arm, step_limit=args.step_limit, cost_limit=args.cost_limit,
                          wall_limit=args.wall_limit, action_timeout=args.action_timeout)

    leaking = arm_test_files_match_base(instance, arm)
    if leaking:
        raise SystemExit("arm %s changes test files, which no arm may do: %s"
                         % (arm, ", ".join(leaking[:5])))

    row = None
    if not args.dry_run or args.show_prompt:
        row = load_row(instance["instance_id"])

    started_at = dt.datetime.now(dt.timezone.utc)
    record = {
        "schema": "sideword-eval-1",
        "instance_id": instance["instance_id"],
        "repo": instance["repo"],
        "version": instance["version"],
        "arm": arm,
        "arm_ref": ref,
        "tree_sha": tree_sha(ref),
        "model": args.model,
        "image": image,
        "source": args.score_only or "agent",
        "started_at": started_at.isoformat(timespec="seconds"),
        "harness": {
            "config_sha256": config_digest(config),
            "limits": {"step_limit": args.step_limit, "cost_limit": args.cost_limit,
                       "wall_limit_s": args.wall_limit, "action_timeout_s": args.action_timeout,
                       "call_timeout_s": args.call_timeout, "test_timeout_s": args.test_timeout},
            "effort": args.effort,
            "sideword_prompt_bytes": len(sideword_block(arm)),
            "sideword_prompt_sha256": hashlib.sha256(
                sideword_block(arm).encode("utf-8")).hexdigest(),
        },
        "errors": [],
    }

    # -- the paths that never touch a model
    if args.score_only:
        patch = _patch_for(args.score_only, instance, row, arm)
        record["patch"] = patch
        record["patch_source"] = args.score_only
        record["scoring"] = score(instance, row, arm, patch, out_dir=out_dir,
                                  model_label=args.model, keep=args.keep,
                                  test_timeout=args.test_timeout, log=log)
        record["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        target = record_path(out_root, args.model, arm, instance["instance_id"], args.score_only)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        resolved = record["scoring"]["resolved"]
        log("%s: resolved=%s -> %s" % (args.score_only, resolved, _rel(target)))
        # `gold` and `empty` are assertions about the arm, not runs of it: the arm's
        # own answer must score, and no answer must not. Anything else is a fact about
        # that tree — a repository that reads its own docstrings, an instance whose
        # tests pass unpatched — and the exit status is how a sweep notices.
        expected = {"gold": True, "empty": False}.get(args.score_only)
        if expected is None:
            return 0
        return 0 if resolved == expected else 1

    # -- the agent path
    name = "sweval-%s-%s-%s" % (instance["instance_id"].replace("__", "-"), arm,
                                re.sub(r"[^a-zA-Z0-9]+", "-", args.model))
    container = Container(name, image, log=log)
    actions: list[dict] = []
    trajectory = None
    try:
        container.start()
        baseline = materialize(container, instance, arm, log=log)
        record["baseline_commit"] = baseline
        if arm == "sw":
            record["sideword_probe"] = install_sideword(container, log=log)
        reset_atimes(container)

        if args.dry_run:
            record["dry_run"] = True
            record["prompt"] = {
                "system": SYSTEM_TEMPLATE,
                "instance_template": config["instance_template"],
            }
            if args.show_prompt:
                print("=" * 78)
                print(_render_offline(config["instance_template"], row["problem_statement"]))
                print("=" * 78)
            log("dry run complete: tree verified%s, no model called"
                % (", sideword installed and answering" if arm == "sw" else ""))
            record["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            target = record_path(out_root, args.model, arm, instance["instance_id"], "dryrun")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
            log("wrote %s" % _rel(target))
            return 0

        from minisweagent import __version__ as mswea_version
        from minisweagent.agents.default import DefaultAgent

        model_kwargs = dict(
            model_name=args.model, action_regex=config["action_regex"],
            format_error_template=config["format_error_template"],
            observation_template=config["observation_template"],
            effort=args.effort, call_timeout=args.call_timeout, log=log)
        if args.script:
            script = json.loads(Path(args.script).read_text(encoding="utf-8"))
            model = ScriptedModel(script, **model_kwargs)
            log("scripted run: %d replies, no model will be called" % len(script))
        else:
            claude_env()                       # fail now, not 40 minutes in
            model = ClaudeCliModel(**model_kwargs)
        record["harness"]["mini_swe_agent"] = mswea_version
        record["harness"]["session_id"] = model.session_id
        record["harness"]["model_source"] = "script" if args.script else "claude-cli"
        record["harness"]["claude_workdir"] = model._workdir

        environment = prepared_environment(container, config, actions)
        agent = DefaultAgent(
            model, environment,
            system_template=config["system_template"],
            instance_template=config["instance_template"],
            step_limit=config["step_limit"],
            cost_limit=config["cost_limit"],
            wall_time_limit_seconds=config["wall_time_limit_seconds"],
            output_path=out_dir / ("%s.traj.json" % instance["instance_id"]))

        agent_started = time.time()
        try:
            exit_info = agent.run(row["problem_statement"])
        except AllowanceExhausted as exc:
            record["errors"].append({"kind": "allowance-exhausted", "detail": str(exc)})
            exit_info = {"exit_status": "AllowanceExhausted", "submission": ""}
        except Exception as exc:                     # the record is worth more than the traceback
            record["errors"].append({"kind": type(exc).__name__, "detail": str(exc)[:4000]})
            exit_info = {"exit_status": type(exc).__name__, "submission": ""}
        agent_wall = time.time() - agent_started
        trajectory = agent.messages

        submission = exit_info.get("submission") or ""
        git_patch = extract_patch(container, baseline)
        # The submission is what mini-swe-agent hands SWE-bench, so it is the
        # prediction. When the agent never got to submit — step limit, wall clock,
        # a blocked account — the work it did is still in the tree, and scoring it is
        # strictly more informative than scoring nothing. The fallback is arm-blind.
        patch, patch_source = ((submission, "submission") if submission.strip()
                               else (git_patch, "git-diff"))

        record["agent"] = _agent_block(agent, model, exit_info, agent_wall)
        record["actions"] = actions
        record["files_read"] = files_read(container)
        record["files_read_count"] = len(record["files_read"])
        # Split, because the two halves answer different questions: the source count
        # is what the agent looked at in the repository, the mirror count is what arm
        # 2's retrieval touched on disk — and `sideword search` reads every sidedoc
        # under its path while showing the model one line from each match.
        record["files_read_counts"] = {
            "source": sum(1 for f in record["files_read"]
                          if not f.startswith(".sideword/")),
            "sideword": sum(1 for f in record["files_read"]
                            if f.startswith(".sideword/")),
        }
        record["files_modified"] = sorted(
            p for p in container.out("git diff --name-only %s" % baseline,
                                     check=False).split("\n") if p.strip())
        if arm == "sw":
            record["sideword_calls"] = sideword_calls(container)
            record["sideword_call_count"] = len(record["sideword_calls"])
        record["patch"] = patch
        record["patch_source"] = patch_source
        record["submission_patch"] = submission
        record["git_diff_patch"] = git_patch
    finally:
        if args.keep:
            log("keeping agent container %s" % name)
        else:
            container.stop()

    if record.get("patch") is not None:
        record["scoring"] = score(instance, row, arm, record["patch"], out_dir=out_dir,
                                  model_label=args.model, keep=args.keep,
                                  test_timeout=args.test_timeout, log=log)

    record["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    record["wall_s"] = round((dt.datetime.now(dt.timezone.utc) - started_at).total_seconds(), 1)
    target = record_path(out_root, args.model, arm, instance["instance_id"],
                         "script" if args.script else "agent")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    log("resolved=%s  steps=%s  files_read=%s  -> %s"
        % (record.get("scoring", {}).get("resolved"),
           record.get("agent", {}).get("n_calls"),
           record.get("files_read_count"), _rel(target)))
    if trajectory is not None:
        log("trajectory: %s" % _rel(out_dir / ("%s.traj.json" % instance["instance_id"])))
    kinds = [e.get("kind") for e in record["errors"]]
    if "allowance-exhausted" in kinds:
        return EXIT_ALLOWANCE_EXHAUSTED
    if kinds:
        return EXIT_AGENT_ERROR
    return 0


def _agent_block(agent, model: ClaudeCliModel, exit_info: dict, wall: float) -> dict:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    for call in model.calls:
        usage = call.get("usage") or {}
        totals["input"] += usage.get("input_tokens", 0) or 0
        totals["output"] += usage.get("output_tokens", 0) or 0
        totals["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
        totals["cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0
    return {
        "exit_status": exit_info.get("exit_status", ""),
        "n_calls": getattr(agent, "n_calls", len(model.calls)),
        "n_messages": len(getattr(agent, "messages", [])),
        "cost_usd": round(model.cost, 6),
        "tokens": totals,
        "tokens_billed": totals["input"] + totals["cache_creation"] + totals["output"],
        "wall_s": round(wall, 1),
        "calls": model.calls,
    }


def _patch_for(source: str, instance: dict, row: dict, arm: str) -> str:
    if source == "gold":
        return arm_gold_patch(instance, row, arm)
    if source == "empty":
        return ""
    return Path(source).read_text(encoding="utf-8")


def _render_offline(template: str, task: str) -> str:
    """Render the task message without the agent, for `--show-prompt`."""
    from jinja2 import StrictUndefined, Template
    return Template(template, undefined=StrictUndefined).render(
        task=task, n_model_calls=0, model_cost=0.0, elapsed_seconds=0)


# ---- CLI ----------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness.evaluate",
        description="Run one instance of the Sideword experiment: one instance, one arm, "
                    "one model.")
    parser.add_argument("--instance", required=True, help="instance_id from corpus/instances.json")
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--model", required=True,
                        help="model id passed to `claude -p --model`, e.g. claude-opus-5. "
                             "Also names the output directory.")
    parser.add_argument("--effort", default=None,
                        choices=["low", "medium", "high", "xhigh", "max"],
                        help="`claude -p --effort`; omitted entirely when unset")
    parser.add_argument("--dry-run", action="store_true",
                        help="everything except the model call: start the container, land and "
                             "verify the arm's tree, install and probe arm 2's `sideword`, "
                             "render the prompt, stop")
    parser.add_argument("--show-prompt", action="store_true",
                        help="with --dry-run, print the fully rendered task message")
    parser.add_argument("--score-only", default=None, metavar="gold|empty|PATH",
                        help="skip the agent and score this patch instead. `gold` re-derives "
                             "the instance's own patch for the arm; `empty` scores nothing. "
                             "Exits non-zero if gold is unresolved or empty is resolved.")
    parser.add_argument("--script", default=None, metavar="PATH",
                        help="JSON list of assistant replies to use instead of calling the "
                             "model. Runs the whole agent loop, the patch extraction and the "
                             "scoring for real; only `claude -p` is stood in for.")
    parser.add_argument("--out", default=None, help="output root (default corpus/eval)")
    parser.add_argument("--keep", action="store_true", help="leave containers running")
    parser.add_argument("--step-limit", type=int, default=250,
                        help="mini-swe-agent step limit (upstream default: 250)")
    parser.add_argument("--cost-limit", type=float, default=5.0,
                        help="stop the agent above this reported cost in USD; 0 disables")
    parser.add_argument("--wall-limit", type=int, default=3600,
                        help="stop the agent after this many seconds; 0 disables")
    parser.add_argument("--action-timeout", type=int, default=180,
                        help="per-command timeout inside the container. 180 rather than "
                             "upstream's 60 because these x86_64 images are emulated here.")
    parser.add_argument("--call-timeout", type=int, default=900,
                        help="timeout for one `claude -p` call")
    parser.add_argument("--test-timeout", type=int, default=1800,
                        help="timeout for the whole evaluation script")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    chosen = [name for name, value in (("--score-only", args.score_only),
                                       ("--dry-run", args.dry_run),
                                       ("--script", args.script)) if value]
    if len(chosen) > 1:
        raise SystemExit("%s are different ways of not calling a model; pick one"
                         % " and ".join(chosen))
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
