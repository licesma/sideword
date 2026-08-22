"""Converter pilot (EST-111): the ONE model step of the EST-81 pipeline.

The model only names anchors. It receives the ORIGINAL file (numbered lines), the stripper's
documentation records (comments / docstrings / doctest docstrings / stray strings, ids r1..rN)
and FORMAT.md, and returns ``{anchors: [{id, anchor, kind}], unanchorable: [{id, reason}]}``.
Nothing else is model work; placement is scored mechanically with the Rust resolver.

Model calls go through headless Claude Code on the subscription (``claude -p``), never an
API key.  Everything is resumable: prompts, raw results and scores are files under
``corpus/convert-pilot/``.

CLI (always run with /Users/esteban/repos/sideword/.venv/bin/python)::

    convert_pilot.py sample                      -> corpus/convert-pilot/sample.json
    convert_pilot.py prompts                     -> corpus/convert-pilot/prompts/<sha>.txt (+ system-prompt.txt)
    convert_pilot.py run --effort low [--limit N] [--jobs 4] [--shas ...]
                                                 -> corpus/convert-pilot/runs/<effort>/<sha>.json
    convert_pilot.py score                       -> report.json, report.md, failures.md
"""

from __future__ import annotations

import argparse
import ast
import collections
import concurrent.futures as cf
import datetime as dt
import hashlib
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from harness import strip  # noqa: E402
from harness.strip import split_lines  # noqa: E402

CACHE = ROOT / "cache"
# FORMAT.md v1 §3 makes a documentation record a block rather than a line. That
# renumbers record ids, so the v0 run's saved outputs can only be re-scored with
# it off — `SIDEWORD_BLOCKS=0` does that, and is how the resolver-only lift was
# measured.
GROUP_BLOCKS = os.environ.get("SIDEWORD_BLOCKS", "1") != "0"
SNAPSHOTS = ROOT / "corpus" / "snapshots"
OUT = ROOT / "corpus" / "convert-pilot"
PROMPTS = OUT / "prompts"
RUNS = OUT / "runs"
SAMPLE = OUT / "sample.json"
SYSTEM_PROMPT_FILE = OUT / "system-prompt.txt"
FORMAT_MD = ROOT / "FORMAT.md"
RESOLVER = ROOT / "target" / "release" / "sideword-resolver"
MIRROR = Path.home() / "repos" / "sideword-corpus"

MODEL = "claude-opus-5"
EFFORTS = ("low", "medium", "high")
NODE_BIN = "/Users/esteban/.nvm/versions/node/v20.19.5/bin"
CALL_TIMEOUT_S = 15 * 60
MAX_RETRIES = 5

BIG_REPOS = ("sympy/sympy", "astropy/astropy", "scikit-learn/scikit-learn", "matplotlib/matplotlib")
QUOTAS = {
    "sympy/sympy": 10, "astropy/astropy": 10, "scikit-learn/scikit-learn": 10,
    "matplotlib/matplotlib": 10,
    "django/django": 8, "sphinx-doc/sphinx": 8, "pylint-dev/pylint": 8, "pydata/xarray": 8,
    "pytest-dev/pytest": 7, "psf/requests": 7, "mwaskom/seaborn": 7, "pallets/flask": 7,
}
SIZE_BUCKETS = (("small", 0, 8 * 1024), ("medium", 8 * 1024, 40 * 1024), ("large", 40 * 1024, 120 * 1024))
MAX_BYTES = 120 * 1024
MIN_REMOVED = 3

DOC_KINDS = ("comment", "docstring", "doctest_docstring", "stray_string")
TODO_RE = re.compile(r"^#\s*(?:TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "anchors": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "anchor": {"type": "string"},
            "kind": {"type": "string", "enum": ["doc", "lead", "trail", "todo", "post"]},
            # FORMAT.md §1.5: ties are derived, never authored. Two identical
            # siblings are indistinguishable in anchor text, so the model says
            # which *line* it meant and the resolver derives the `~n`.
            "line": {"type": "integer"}},
            "required": ["id", "anchor", "kind", "line"], "additionalProperties": False}},
        "unanchorable": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["id", "reason"], "additionalProperties": False}},
    },
    "required": ["anchors", "unanchorable"], "additionalProperties": False,
}

CONTRACT = """\
# Task

You name anchors for documentation records of a Python file. Anchors follow the grammar above
exactly. Output only JSON matching the schema. For each record give the anchor (verbatim grammar,
discriminators copied from source text with whitespace normalized as the spec says), the kind
(doc|lead|trail|todo|post) and the line. If no anchor in the grammar can name a record, put it in
unanchorable with a one-line reason. Never invent anchor kinds. Never quote or rewrite the record text.

`line` is the 1-based line number of the thing the anchor names — the statement, definition,
parameter or element the record documents — NOT the line the comment or docstring itself sits on
(for a `lead` comment those differ; for a `trail` comment they are the same line). It is a position
hint only: it never changes what the anchor text has to say, and an anchor that names the right
thing is still required. Its one job is §1.5. Ties are derived, never authored, so when two
textually identical siblings both match your anchor, no anchor text can say which you meant; the
line does, and the resolver assigns the `~n` from it. Still write the untied anchor.

Conventions that follow from the spec:
- Every record id (r1..rN) must appear exactly once, either in `anchors` or in `unanchorable`.
- A docstring / doctest docstring record has kind `doc` and its anchor is the symbol that owns it
  (`<module>`, `Cart`, `Cart.add`); a stray string documents the statement just above it.
- A comment on its own line has kind `lead` (or `todo` if it starts with TODO/FIXME/XXX/HACK) and
  is anchored to the statement it sits above; a comment at the end of a code line has kind `trail`
  (or `todo`) and is anchored to that statement.
- A comment block with no statement after it — the end of a file, or the end of the block it
  closes — has kind `post` and is anchored to the statement it follows.
- A record is a comment *block*, not a line: consecutive comment lines arrive as one record
  (`[comment block, lines 124–136, ...]`) and take one anchor and one kind.
- Statements at module level are anchored as `<module>#...` (e.g. `<module>#import:os`,
  `<module>#if:__name__=="__main__"`); statements inside a function or method as
  `Class.method#...`; module and class variables as symbols (`MAX_TOKENS`, `Cart.total`).
- The user prompt shows the file with 1-based line numbers (`   12| code`) followed by the records.
"""


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)


def blob_bytes(sha: str) -> bytes:
    return subprocess.run(["git", "-C", str(MIRROR), "cat-file", "blob", sha],
                          check=True, capture_output=True).stdout


def decode(src: bytes) -> str:
    try:
        enc, _ = tokenize.detect_encoding(io.BytesIO(src).readline)
        return src.decode(enc)
    except Exception:
        return src.decode("utf-8", errors="replace")


def read_sidecar(sha: str) -> list[dict]:
    p = CACHE / f"{sha}.jsonl"
    with p.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def squeeze(anchor: str) -> str:
    return "".join(anchor.split())


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0, "mean": None, "median": None, "p90": None, "total": 0}
    s = sorted(values)
    p90 = s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]
    return {"n": len(s), "mean": round(statistics.mean(s), 4), "median": statistics.median(s),
            "p90": p90, "total": sum(s), "min": s[0], "max": s[-1]}


# ---------------------------------------------------------------------------------------------
# 1. sample
# ---------------------------------------------------------------------------------------------

def bucket_of(nbytes: int) -> str | None:
    for name, lo, hi in SIZE_BUCKETS:
        if lo <= nbytes < hi or (name == "large" and nbytes == hi):
            return name
    return None


def build_sample() -> list[dict]:
    blobs: dict[str, dict] = {}
    for snap in sorted(SNAPSHOTS.glob("*.json")):
        d = json.loads(snap.read_text())
        for f in d["files"]:
            blobs.setdefault(f["blob_sha"], {"repo": d["repo"], "path": f["path"]})
    eligible: dict[str, list[dict]] = collections.defaultdict(list)
    for sha, info in blobs.items():
        p = CACHE / f"{sha}.jsonl"
        if not p.exists():
            continue
        recs = read_sidecar(sha)
        st = recs[-1]
        if st.get("kind") != "stats":
            continue
        if any(r.get("kind") == "parse_error" for r in recs):
            continue
        n_removed = st["comments_removed"] + st["docstrings_removed"]
        nbytes = st["bytes_before"]
        if n_removed < MIN_REMOVED or nbytes > MAX_BYTES:
            continue
        n_records = sum(1 for r in recs if r.get("kind") in DOC_KINDS)
        eligible[info["repo"]].append({
            "blob_sha": sha, "repo": info["repo"], "path": info["path"], "bytes": nbytes,
            "n_records": n_records, "n_removed": n_removed, "bucket": bucket_of(nbytes),
            "key": hashlib.sha1(sha.encode()).hexdigest()})
    for repo in eligible:
        eligible[repo].sort(key=lambda r: r["key"])

    def split_quota(q: int) -> dict[str, int]:
        small = round(0.4 * q)
        medium = round(0.4 * q)
        return {"small": small, "medium": medium, "large": q - small - medium}

    def draw(repo: str, q: int, taken: set[str]) -> list[dict]:
        want = split_quota(q)
        pools = {b: [r for r in eligible[repo] if r["bucket"] == b and r["blob_sha"] not in taken]
                 for b in ("small", "medium", "large")}
        chosen = []
        for b in ("small", "medium", "large"):
            take = pools[b][:want[b]]
            chosen.extend(take)
            pools[b] = pools[b][len(take):]
        short = q - len(chosen)
        for b in ("medium", "small", "large"):
            if short <= 0:
                break
            take = pools[b][:short]
            chosen.extend(take)
            pools[b] = pools[b][len(take):]
            short -= len(take)
        return chosen

    sample: list[dict] = []
    taken: set[str] = set()
    per_repo = {}
    for repo, q in QUOTAS.items():
        got = draw(repo, q, taken)
        per_repo[repo] = len(got)
        sample.extend(got)
        taken.update(r["blob_sha"] for r in got)
    total_wanted = sum(QUOTAS.values())
    # redistribute any shortfall to the big repos, round-robin, one blob at a time
    i = 0
    while len(sample) < total_wanted and i < 1000:
        repo = BIG_REPOS[i % len(BIG_REPOS)]
        i += 1
        extra = draw(repo, per_repo[repo] + 1, taken)
        new = [r for r in extra if r["blob_sha"] not in taken]
        if not new:
            continue
        sample.append(new[0])
        taken.add(new[0]["blob_sha"])
        per_repo[repo] += 1
    for r in sample:
        r.pop("key", None)
    return sample


# ---------------------------------------------------------------------------------------------
# 2. records
# ---------------------------------------------------------------------------------------------

def first_content_line(text: str) -> str:
    """First non-blank content line of a string literal's source text, quotes stripped."""
    body = text.strip()
    for q in ('"""', "'''"):
        if body.startswith(q):
            body = body[len(q):]
            if body.endswith(q):
                body = body[:-len(q)]
            break
    else:
        m = re.match(r"^[rRbBuUfF]{0,2}(\"\"\"|'''|\"|')", body)
        if m:
            body = body[m.end():]
            q = m.group(1)
            if body.endswith(q):
                body = body[:-len(q)]
    for line in body.splitlines():
        if line.strip():
            s = line.strip()
            return s if len(s) <= 100 else s[:97] + "..."
    return ""


def build_records(sha: str, text: str, lines: list[str]) -> list[dict]:
    """The documentation records of a blob in file order with ids r1..rN and expected kinds."""
    recs = [r for r in read_sidecar(sha) if r.get("kind") in DOC_KINDS]
    recs.sort(key=lambda r: (r["line"], r.get("col", 0)))
    # FORMAT.md v1 §3: a documentation record is a block, not a line. The
    # sidecar stays per-token; grouping is a format concern, applied here.
    if GROUP_BLOCKS:
        recs = strip.group_comment_blocks(recs, lines)
    out = []
    for i, r in enumerate(recs, 1):
        rec = {"id": f"r{i}", "rkind": r["kind"], "line": r["line"],
               "end_line": r.get("end_line", r["line"])}
        if r["kind"] == "comment":
            line_text = lines[r["line"] - 1] if r["line"] - 1 < len(lines) else ""
            full = line_text[:r["col"]].strip() == ""
            rec["col"] = r["col"]
            rec["text"] = r["text"]
            rec["block_lines"] = r.get("lines_in_block", 1)
            rec["placement"] = "full-line" if full else "trailing"
            todo = bool(TODO_RE.match(r["text"]))
            rec["expected_kind"] = "todo" if todo else ("lead" if full else "trail")
            rec["is_todo"] = todo
        else:
            rec["owner"] = r.get("owner")
            src = r.get("text")
            if src is None:
                src = "\n".join(lines[r["line"] - 1:r["end_line"]])
            rec["first_line"] = first_content_line(src)
            rec["expected_kind"] = "doc"
        out.append(rec)
    return out


def record_line(rec: dict) -> str:
    if rec["rkind"] == "comment":
        body = rec["text"].split("\n")
        if len(body) == 1:
            return f'{rec["id"]} [comment, line {rec["line"]}, col {rec["col"]}] {body[0]}'
        head = (f'{rec["id"]} [comment block, lines {rec["line"]}–{rec["end_line"]}, '
                f'col {rec["col"]}] {body[0]}')
        pad = " " * (len(rec["id"]) + 1)
        return "\n".join([head] + [pad + line for line in body[1:]])
    span = f'line {rec["line"]}' if rec["line"] == rec["end_line"] else f'lines {rec["line"]}–{rec["end_line"]}'
    if rec["rkind"] == "docstring":
        return f'{rec["id"]} [docstring, {span}, owner {rec["owner"]}] """{rec["first_line"]}'
    if rec["rkind"] == "doctest_docstring":
        return f'{rec["id"]} [doctest_docstring (kept in source), {span}, owner {rec["owner"]}] """{rec["first_line"]}'
    return f'{rec["id"]} [stray_string (kept in source), {span}] """{rec["first_line"]}'


def build_user_prompt(entry: dict, text: str, lines: list[str], records: list[dict]) -> str:
    buf = [f'File: {entry["path"]}  (repo {entry["repo"]})', "", "```"]
    for i, line in enumerate(lines, 1):
        buf.append(f"{i:>5}| {line.rstrip(chr(13) + chr(10))}")
    buf.append("```")
    buf.append("")
    buf.append(f"Records ({len(records)}):")
    buf.extend(record_line(r) for r in records)
    buf.append("")
    return "\n".join(buf)


def system_prompt_text() -> str:
    return FORMAT_MD.read_text() + "\n\n---\n\n" + CONTRACT


def load_sample() -> list[dict]:
    return json.loads(SAMPLE.read_text())


def blob_context(entry: dict) -> tuple[str, list[str], list[dict]]:
    src = blob_bytes(entry["blob_sha"])
    text = decode(src)
    lines = split_lines(text)
    records = build_records(entry["blob_sha"], text, lines)
    return text, lines, records


def write_prompts(sample: list[dict]) -> None:
    PROMPTS.mkdir(parents=True, exist_ok=True)
    SYSTEM_PROMPT_FILE.write_text(system_prompt_text())
    for e in sample:
        p = PROMPTS / f'{e["blob_sha"]}.txt'
        if p.exists():
            continue
        text, lines, records = blob_context(e)
        p.write_text(build_user_prompt(e, text, lines, records))
    log(f"prompts written: {len(sample)}; system prompt {len(SYSTEM_PROMPT_FILE.read_text())} chars")


# ---------------------------------------------------------------------------------------------
# 3. run
# ---------------------------------------------------------------------------------------------

RATE_LIMIT_RE = re.compile(r"rate.?limit|429|too many requests|overloaded|usage limit|hit your limit|"
                           r"limit reached|out of extra usage|529", re.IGNORECASE)
HARD_BLOCK_RE = re.compile(r"usage limit|hit your limit|limit reached|out of extra usage|spend limit|"
                           r"usage-credits|resets? at|5.hour", re.IGNORECASE)

_stop = threading.Event()


def claude_cmd(effort: str) -> list[str]:
    return ["claude", "-p", "--model", MODEL, "--effort", effort,
            "--system-prompt-file", str(SYSTEM_PROMPT_FILE),
            "--no-session-persistence", "--output-format", "json", "--tools", "",
            "--json-schema", json.dumps(JSON_SCHEMA, separators=(",", ":"))]


def clean_env() -> dict:
    """A minimal environment for the headless CLI.

    Inherited `CLAUDE_*` session variables break auth, so nothing is passed
    through — except `CLAUDE_CONFIG_DIR`, which is how the CLI picks *which
    account* to bill. Without it the call falls back to `~/.claude`, whichever
    account happens to be logged in there. Set `SIDEWORD_CLAUDE_CONFIG_DIR` to
    the config dir of the account the batch should run on.
    """
    env = {"HOME": os.environ["HOME"], "PATH": f"/usr/bin:/bin:{NODE_BIN}",
           "USER": os.environ.get("USER", ""), "TERM": "dumb"}
    config_dir = os.environ.get("SIDEWORD_CLAUDE_CONFIG_DIR")
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = config_dir
    return env


def call_model(prompt: str, effort: str) -> dict:
    """One headless call. Returns {"ok": bool, "result": <json>, "stderr": str, "wall_ms": int, ...}."""
    t0 = time.time()
    try:
        proc = subprocess.run(claude_cmd(effort), input=prompt, capture_output=True, text=True,
                              env=clean_env(), timeout=CALL_TIMEOUT_S, cwd=str(OUT))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "wall_ms": int(1000 * (time.time() - t0))}
    wall_ms = int(1000 * (time.time() - t0))
    stdout = proc.stdout.strip()
    result = None
    for candidate in (stdout, stdout.splitlines()[-1] if stdout else ""):
        try:
            result = json.loads(candidate)
            break
        except Exception:
            continue
    if result is None:
        return {"ok": False, "error": f"no-json (rc={proc.returncode})", "stdout": stdout[-2000:],
                "stderr": proc.stderr[-2000:], "wall_ms": wall_ms}
    if result.get("is_error") or result.get("structured_output") is None:
        return {"ok": False, "error": "is_error" if result.get("is_error") else "no-structured-output",
                "result": result, "stderr": proc.stderr[-2000:], "wall_ms": wall_ms}
    return {"ok": True, "result": result, "stderr": proc.stderr[-500:], "wall_ms": wall_ms}


def run_one(entry: dict, effort: str) -> str:
    sha = entry["blob_sha"]
    out_path = RUNS / effort / f"{sha}.json"
    if out_path.exists():
        return "skip"
    if _stop.is_set():
        return "stopped"
    prompt = (PROMPTS / f"{sha}.txt").read_text()
    attempts = []
    delay = 30
    for attempt in range(1, MAX_RETRIES + 1):
        if _stop.is_set():
            return "stopped"
        r = call_model(prompt, effort)
        attempts.append({"attempt": attempt, "ok": r["ok"], "error": r.get("error"),
                         "wall_ms": r["wall_ms"], "at": dt.datetime.now().isoformat(timespec="seconds")})
        if r["ok"]:
            payload = {"blob_sha": sha, "effort": effort, "model": MODEL, "attempts": attempts,
                       "wall_ms": r["wall_ms"], "result": r["result"]}
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=1))
            u = r["result"].get("usage", {})
            log(f"{effort} {sha[:8]} ok {r['wall_ms']/1000:.0f}s in={u.get('input_tokens')}+"
                f"cc={u.get('cache_creation_input_tokens')} cr={u.get('cache_read_input_tokens')} "
                f"out={u.get('output_tokens')} attempt={attempt}")
            return "ok"
        blob = json.dumps(r.get("result", {}))[:2000] + (r.get("stderr") or "") + (r.get("stdout") or "")
        rate_limited = bool(RATE_LIMIT_RE.search(blob))
        attempts[-1]["rate_limited"] = rate_limited
        attempts[-1]["detail"] = blob[:1500]
        log(f"{effort} {sha[:8]} FAIL attempt {attempt}: {r.get('error')} rate_limited={rate_limited} "
            f":: {blob[:300]!r}")
        if HARD_BLOCK_RE.search(blob) and (attempt >= 2 or "spend limit" in blob):
            log("hard block (usage/spend limit); stopping new work")
            _stop.set()
            break
        if attempt < MAX_RETRIES:
            time.sleep(delay if rate_limited else min(delay, 20))
            delay = min(delay * 2, 600)
    blocked = _stop.is_set()
    fail_path = RUNS / effort / f"{sha}.{'blocked' if blocked else 'failed'}.json"
    fail_path.parent.mkdir(parents=True, exist_ok=True)
    fail_path.write_text(json.dumps({"blob_sha": sha, "effort": effort, "attempts": attempts}, indent=1))
    return "blocked" if blocked else "failed"


def run_effort(sample: list[dict], effort: str, jobs: int) -> dict:
    counts = collections.Counter()
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_one, e, effort): e for e in sample}
        for fut in cf.as_completed(futs):
            try:
                counts[fut.result()] += 1
            except Exception as exc:  # noqa: BLE001
                counts["exception"] += 1
                log(f"exception: {exc!r}")
    log(f"effort {effort}: {dict(counts)}")
    return dict(counts)


# ---------------------------------------------------------------------------------------------
# 4. score
# ---------------------------------------------------------------------------------------------

class FileFacts:
    """Everything mechanical about one original file: AST-derived expected lines, resolver index."""

    def __init__(self, entry: dict):
        self.entry = entry
        self.sha = entry["blob_sha"]
        self.text, self.lines, self.records = blob_context(entry)
        self.utf8 = self.text.encode("utf-8")
        self.tree = ast.parse(self.text.replace("\r\n", "\n").replace("\r", "\n"))
        self.n_lines = len(self.lines)
        # docstring/string-expr line -> owner (def/class/module) line ; and previous sibling line
        self.doc_owner_line: dict[int, int] = {}
        self.prev_sibling_line: dict[int, int | None] = {}
        self.decorator_first_line: dict[int, int] = {}   # def line -> first decorator line
        self.stmt_spans: list[tuple[int, int, int]] = []  # (lineno, end_lineno, depth)
        self._walk(self.tree, 0)
        self.index_lines = self._index_lines()
        self.first_stmt_line = self.tree.body[0].lineno if self.tree.body else 1

    def _walk(self, node, depth):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                owner_line = 1 if isinstance(node, ast.Module) else getattr(node, "lineno", 1)
                prev = None
                for stmt in value:
                    self.stmt_spans.append((stmt.lineno, stmt.end_lineno, depth, stmt.col_offset))
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                            and isinstance(stmt.value.value, str):
                        self.doc_owner_line[stmt.lineno] = owner_line
                        self.prev_sibling_line[stmt.lineno] = prev
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                            and stmt.decorator_list:
                        self.decorator_first_line[stmt.lineno] = stmt.decorator_list[0].lineno
                    prev = stmt.lineno
                    self._walk(stmt, depth + 1)
            elif isinstance(value, list) and value and isinstance(value[0], (ast.excepthandler, ast.match_case)):
                for item in value:
                    self.stmt_spans.append((item.lineno, item.end_lineno, depth, item.col_offset))
                    self._walk(item, depth + 1)

    def enclosing_stmt_line(self, line: int) -> int | None:
        best = None
        for lo, hi, depth, _col in self.stmt_spans:
            if lo <= line <= hi and (best is None or depth > best[1] or (depth == best[1] and lo > best[0])):
                best = (lo, depth)
        return best[0] if best else None

    def prev_stmt_line(self, line: int, indent: int) -> int | None:
        """Start line of the last statement that starts before `line` at exactly `indent`."""
        best = None
        for lo, hi, depth, col in self.stmt_spans:
            if lo < line and col == indent and (best is None or lo > best):
                best = lo
        return best

    def is_comment_or_blank(self, i: int) -> bool:
        s = self.lines[i - 1].strip()
        return s == "" or s.startswith("#")

    def expected_lines(self, rec: dict) -> tuple[list[int], bool]:
        """Expected attachment line(s) for a record; (candidates, ambiguous)."""
        if rec["rkind"] == "comment":
            if rec["placement"] == "trailing":
                enc = self.enclosing_stmt_line(rec["line"])
                if enc is not None and enc < rec["line"]:
                    # trailing comment on a continuation line of a multi-line statement:
                    # the element (own line) or the statement (its first line) are both defensible
                    return [rec["line"], enc], True
                return [rec["line"]], False
            indent = indent_of(self.lines[rec["line"] - 1])
            # The scan starts after the whole block (§3), not after its first line.
            j = rec.get("end_line", rec["line"]) + 1
            while j <= self.n_lines and self.is_comment_or_blank(j):
                j += 1
            prev = self.prev_stmt_line(rec["line"], indent)
            enc = self.enclosing_stmt_line(rec["line"])
            if j > self.n_lines:
                # End of file. v1 gives this a rule: `post` on the statement it
                # follows (§3). The enclosing statement stays tolerated.
                if prev is not None:
                    return [prev], False
                cands = [c for c in (enc,) if c is not None]
                return (cands or [self.n_lines]), True
            nxt_indent = indent_of(self.lines[j - 1])
            if nxt_indent < indent:
                # The block closes a block: same rule, `post` on the last
                # statement inside it.
                if prev is not None:
                    return [prev], False
                cands = [c for c in (enc, j) if c is not None]
                return cands, True
            return [j], False
        # string records
        owner = self.doc_owner_line.get(rec["line"])
        if rec["rkind"] in ("docstring", "doctest_docstring"):
            return [owner if owner is not None else rec["line"]], owner is None
        prev = self.prev_sibling_line.get(rec["line"])
        cands = [c for c in (prev, owner) if c is not None]
        return (cands or [rec["line"]]), True

    def expected_kind(self, rec: dict) -> str:
        """`post` (§3) for a full-line comment block with nothing after it to
        lead — end of file, or end of the block it closes. Otherwise the kind
        the record was built with."""
        if rec["rkind"] != "comment" or rec["placement"] != "full-line":
            return rec["expected_kind"]
        if rec["expected_kind"] == "todo":
            return "todo"
        indent = indent_of(self.lines[rec["line"] - 1])
        j = rec.get("end_line", rec["line"]) + 1
        while j <= self.n_lines and self.is_comment_or_blank(j):
            j += 1
        if j > self.n_lines:
            return "post" if self.prev_stmt_line(rec["line"], indent) is not None else "lead"
        if indent_of(self.lines[j - 1]) < indent:
            return "post" if self.prev_stmt_line(rec["line"], indent) is not None else "lead"
        return "lead"

    def _index_lines(self) -> dict[int, int]:
        """line -> number of resolver anchors attached at that line (excluding <module>)."""
        with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=False) as fh:
            fh.write(self.utf8)
            path = fh.name
        try:
            proc = subprocess.run([str(RESOLVER), "index", path], capture_output=True, text=True)
            counts: dict[int, int] = collections.Counter()
            if proc.returncode == 0:
                for f in json.loads(proc.stdout):
                    for a in f["anchors"]:
                        if a["anchor"] != "<module>":
                            counts[a["line"]] += 1
            return counts
        finally:
            os.unlink(path)


def resolve_anchors(source_bytes: bytes, anchors: list[str], hints: list[int | None] | None = None) -> list[dict]:
    """Run the resolver on `anchors` against `source_bytes`; one outcome dict per anchor.

    `hints[i]` is the line the model said its anchor names. The resolver only
    looks at it when the anchor is `Ambiguous` (§1.5), and marks the outcome
    `disambiguated_by: "position"` when it does. Hints are only meaningful
    against the source they were written for: never pass them for the stripped
    file, whose line numbers are different.
    """
    cleaned = [" ".join(a.split()) for a in anchors]
    hints = [h if isinstance(h, int) and not isinstance(h, bool) and h >= 1 else None
             for h in (hints or [None] * len(anchors))]
    non_empty = [(i, a) for i, a in enumerate(cleaned) if a]
    outcomes: list[dict] = [{"status": "malformed", "error": "empty anchor"} for _ in anchors]
    if not non_empty:
        return outcomes
    with tempfile.NamedTemporaryFile("wb", suffix=".py", delete=False) as fh:
        fh.write(source_bytes)
        path = fh.name
    stdin = "".join(a + (f"\t{hints[i]}" if hints[i] is not None else "") + "\n" for i, a in non_empty)
    try:
        proc = subprocess.run([str(RESOLVER), "resolve", path], input=stdin,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            for i, _ in non_empty:
                outcomes[i] = {"status": "resolver-error", "error": proc.stderr[-300:]}
            return outcomes
        results = json.loads(proc.stdout)["results"]
        if len(results) != len(non_empty):
            for i, _ in non_empty:
                outcomes[i] = {"status": "resolver-error", "error": "result count mismatch"}
            return outcomes
        for (i, _), r in zip(non_empty, results):
            outcomes[i] = r["outcome"]
    finally:
        os.unlink(path)
    return outcomes


def anchor_depth(anchor: str) -> str:
    if "#" not in anchor:
        return "symbol"
    segs = anchor.split("#", 1)[1]
    n = 1 + sum(1 for m in re.finditer(r"/(?=[a-z]+(?:[:/~]|$))", segs))
    return "1-seg" if n == 1 else "2+seg"


def last_kind(anchor: str) -> str:
    if "#" not in anchor:
        return "symbol"
    segs = anchor.split("#", 1)[1]
    parts = re.split(r"/(?=[a-z]+(?:[:/~]|$))", segs)
    m = re.match(r"([a-z]+(?: [a-z]+)?)", parts[-1])
    return m.group(1) if m else "?"


def usage_of(result: dict) -> dict:
    u = result.get("usage", {})
    mu = (result.get("modelUsage") or {}).get(MODEL, {})
    thinking = (u.get("output_tokens_details") or {}).get("thinking_tokens")
    return {
        "input_tokens": u.get("input_tokens", 0),
        "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
        "output_tokens": u.get("output_tokens", 0),
        "thinking_tokens": thinking,
        "opus_cost_usd": mu.get("costUSD"),
        "total_cost_usd": result.get("total_cost_usd"),
        "duration_ms": result.get("duration_ms"),
        "duration_api_ms": result.get("duration_api_ms"),
        "num_turns": result.get("num_turns"),
    }


def score_run(facts: FileFacts, effort: str, stripped_bytes: bytes | None) -> dict | None:
    path = RUNS / effort / f"{facts.sha}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    result = payload["result"]
    so = result["structured_output"]
    by_id: dict[str, list] = collections.defaultdict(list)
    for a in so.get("anchors", []):
        by_id[a["id"]].append(("anchor", a))
    for u in so.get("unanchorable", []):
        by_id[u["id"]].append(("unanchorable", u))
    known_ids = {r["id"] for r in facts.records}
    extra_ids = sorted(set(by_id) - known_ids)

    anchored = [(r, by_id[r["id"]][0][1]) for r in facts.records
                if by_id.get(r["id"]) and by_id[r["id"]][0][0] == "anchor"]
    anchor_texts = [a["anchor"] for _, a in anchored]
    line_hints = [a.get("line") for _, a in anchored]
    outcomes = resolve_anchors(facts.utf8, anchor_texts, line_hints)
    # No hints here: the stripped file has different line numbers.
    outcomes_stripped = resolve_anchors(stripped_bytes, anchor_texts) if stripped_bytes else [None] * len(anchored)
    outcome_by_id = {r["id"]: (o, os_) for (r, _), o, os_ in zip(anchored, outcomes, outcomes_stripped)}

    per_record = []
    for rec in facts.records:
        entries = by_id.get(rec["id"], [])
        exp_lines, exp_amb = facts.expected_lines(rec)
        exp_lines = list(dict.fromkeys(exp_lines))
        row = {"id": rec["id"], "rkind": rec["rkind"], "line": rec["line"],
               "placement": rec.get("placement"), "expected_kind": facts.expected_kind(rec),
               # How many physical comment lines this record covers. v1 makes a
               # record a block, so record counts are no longer comparable to
               # the v0 run; weighting by this restores a like-for-like number.
               "block_lines": rec.get("block_lines", 1),
               "expected_lines": exp_lines, "expected_ambiguous": exp_amb,
               "enclosing_stmt_line": facts.enclosing_stmt_line(exp_lines[0]) if exp_lines else None,
               "coverage": ("dropped" if not entries else "dup" if len(entries) > 1 else "ok"),
               "nameable_at_expected": any(facts.index_lines.get(l, 0) > 0 for l in exp_lines)}
        if not entries:
            row["verdict"] = "dropped"
            per_record.append(row)
            continue
        tag, obj = entries[0]
        if tag == "unanchorable":
            row["verdict"] = "unanchorable"
            row["reason"] = obj["reason"]
            per_record.append(row)
            continue
        anchor = obj["anchor"]
        o, os_ = outcome_by_id[rec["id"]]
        row.update({"anchor": anchor, "kind": obj["kind"],
                    "kind_ok": obj["kind"] == facts.expected_kind(rec),
                    "depth": anchor_depth(anchor), "last_kind": last_kind(anchor),
                    "status": o["status"], "outcome": o, "line_hint": obj.get("line"),
                    # The anchor named several identical siblings and the model's
                    # line picked one (§1.5). Scored in its own bucket: the line
                    # came from the model, and the expected line comes from the
                    # same record, so comparing them proves almost nothing.
                    "position_disambiguated": o.get("disambiguated_by") == "position",
                    "n_candidates": len(o.get("candidates") or []) or None})
        if os_ is not None:
            row["status_stripped"] = os_["status"]
            row["stripped_line"] = os_.get("line")
        line = o.get("line")
        row["resolved_line"] = line
        correct = False
        if o["status"] == "found" and line is not None:
            if squeeze(anchor) == "<module>" and rec["rkind"] == "comment" and facts.first_stmt_line in exp_lines:
                correct = True  # header comment anchored to the module renders at the top of the file
            for e in exp_lines:
                if abs(line - e) <= 1:
                    correct = True
                # decorated symbol: comment above the decorator vs resolver's def line (and reverse)
                if facts.decorator_first_line.get(line) == e or facts.decorator_first_line.get(e) == line:
                    correct = True
        row["placement_ok"] = correct
        if o["status"] == "found":
            suffix = "-by-position" if row["position_disambiguated"] else ""
            row["verdict"] = ("correct" if correct else "wrong-place") + suffix
            if not correct:
                row["distance"] = min(abs(line - e) for e in exp_lines)
        elif o["status"] == "ambiguous":
            cands = [c.get("line") for c in o.get("candidates", [])]
            row["ambiguous_hit"] = any(abs(c - e) <= 1 for c in cands for e in exp_lines if c is not None)
            row["verdict"] = "ambiguous"
        elif o["status"] == "unverified":
            row["verdict"] = "unverified"
            row["unverified_hit"] = any(abs(line - e) <= 1 for e in exp_lines) if line is not None else False
        else:
            row["verdict"] = o["status"]  # missing | malformed | resolver-error
        if row["position_disambiguated"]:
            # The one thing about these rows that is NOT circular: whether the
            # expected line was among the candidates at all. That says the
            # anchor named the right family of identical siblings, which is
            # anchor work; which sibling of the family got picked is the hint's
            # work and is not evidence about the anchor.
            cands = [c.get("line") for c in o.get("candidates", [])]
            row["candidate_hit"] = any(abs(c - e) <= 1 for c in cands for e in exp_lines if c is not None)
        per_record.append(row)

    return {"blob_sha": facts.sha, "effort": effort, "repo": facts.entry["repo"], "path": facts.entry["path"],
            "bytes": facts.entry["bytes"], "n_records": len(facts.records), "extra_ids": extra_ids,
            "attempts": len(payload.get("attempts", [])), "wall_ms": payload.get("wall_ms"),
            "usage": usage_of(result), "records": per_record}


# ---------------------------------------------------------------------------------------------
# 5. aggregate + report
# ---------------------------------------------------------------------------------------------

def by_position(row: dict) -> bool:
    """Whether this record only resolved because the model also gave a line.

    Everything derived from these rows is circular to some degree — the model
    supplied the line, and the expected line comes from the same record — so
    they are counted apart from every "did the anchor name the right thing"
    number rather than folded into it.
    """
    return bool(row.get("position_disambiguated"))


def rec_group(row: dict) -> str:
    if row["rkind"] == "comment":
        return "comment-" + ("todo" if row["expected_kind"] == "todo" else row["placement"])
    return row["rkind"]


def aggregate(scored: dict[str, list[dict]], sample: list[dict]) -> dict:
    agg: dict = {"efforts": {}, "sample": {}}
    for effort in EFFORTS:
        runs = scored.get(effort, [])
        rows = [r for run in runs for r in run["records"]]
        n = len(rows)
        n_lines = sum(r.get("block_lines", 1) for r in rows)
        lines_correct = sum(r.get("block_lines", 1) for r in rows if r.get("placement_ok"))
        n_lines_strict = sum(r.get("block_lines", 1) for r in rows if not by_position(r))
        lines_correct_strict = sum(r.get("block_lines", 1) for r in rows
                                   if r.get("placement_ok") and not by_position(r))
        verdicts = collections.Counter(r["verdict"] for r in rows)
        anchored = [r for r in rows if "anchor" in r]
        pos_rows = [r for r in anchored if by_position(r)]
        strict_rows = [r for r in anchored if not by_position(r)]
        statuses = collections.Counter(r["status"] for r in anchored)
        by_group: dict[str, dict] = {}
        for g in sorted({rec_group(r) for r in rows}):
            rs = [r for r in rows if rec_group(r) == g]
            an = [r for r in rs if "anchor" in r]
            by_group[g] = {
                "records": len(rs),
                "anchored": len(an),
                "unanchorable": sum(1 for r in rs if r["verdict"] == "unanchorable"),
                "dropped": sum(1 for r in rs if r["verdict"] == "dropped"),
                "found": sum(1 for r in an if r["status"] == "found"),
                "correct": sum(1 for r in an if r.get("placement_ok")),
                "anchored_strict": sum(1 for r in an if not by_position(r)),
                "correct_strict": sum(1 for r in an if r.get("placement_ok") and not by_position(r)),
                "position": sum(1 for r in an if by_position(r)),
                "position_correct": sum(1 for r in an if by_position(r) and r.get("placement_ok")),
                "wrong_place": sum(1 for r in an if r["verdict"] == "wrong-place"),
                "ambiguous": sum(1 for r in an if r["status"] == "ambiguous"),
                "ambiguous_hit": sum(1 for r in an if r.get("ambiguous_hit")),
                "missing": sum(1 for r in an if r["status"] == "missing"),
                "malformed": sum(1 for r in an if r["status"] == "malformed"),
                "unverified": sum(1 for r in an if r["status"] == "unverified"),
                "kind_ok": sum(1 for r in an if r.get("kind_ok")),
                "expected_ambiguous": sum(1 for r in rs if r["expected_ambiguous"]),
            }
        by_depth: dict[str, dict] = {}
        for d in ("symbol", "1-seg", "2+seg"):
            an = [r for r in anchored if r["depth"] == d]
            by_depth[d] = {"anchored": len(an),
                           "found": sum(1 for r in an if r["status"] == "found"),
                           "correct": sum(1 for r in an if r.get("placement_ok")),
                           "anchored_strict": sum(1 for r in an if not by_position(r)),
                           "correct_strict": sum(1 for r in an if r.get("placement_ok") and not by_position(r)),
                           "position": sum(1 for r in an if by_position(r)),
                           "ambiguous": sum(1 for r in an if r["status"] == "ambiguous"),
                           "missing": sum(1 for r in an if r["status"] == "missing"),
                           "malformed": sum(1 for r in an if r["status"] == "malformed")}
        by_last_kind: dict[str, dict] = {}
        for k in sorted({r["last_kind"] for r in anchored}):
            an = [r for r in anchored if r["last_kind"] == k]
            by_last_kind[k] = {"anchored": len(an), "found": sum(1 for r in an if r["status"] == "found"),
                               "correct": sum(1 for r in an if r.get("placement_ok")),
                               "anchored_strict": sum(1 for r in an if not by_position(r)),
                               "correct_strict": sum(1 for r in an if r.get("placement_ok") and not by_position(r)),
                               "position": sum(1 for r in an if by_position(r)),
                               "ambiguous": sum(1 for r in an if r["status"] == "ambiguous"),
                               "missing": sum(1 for r in an if r["status"] == "missing"),
                               "malformed": sum(1 for r in an if r["status"] == "malformed")}
        # Position-disambiguated rows are excluded: the stripped file is resolved
        # without hints, so they would count as a strip regression that is really
        # just the missing hint.
        strip_only = [r for r in anchored if r.get("status_stripped") is not None
                      and r["status"] == "found" and r["status_stripped"] != "found"
                      and not by_position(r)]
        strip_moved = [r for r in anchored if r.get("status_stripped") == "found" and r["status"] == "found"
                       and r.get("stripped_line") != r.get("resolved_line")]
        kinds = collections.Counter((r["expected_kind"], r["kind"]) for r in anchored)
        usages = [run["usage"] for run in runs]
        walls = [run["wall_ms"] for run in runs]
        tok = {
            "input_uncached": stats([u["input_tokens"] + u["cache_creation_input_tokens"] for u in usages]),
            "input_tokens": stats([u["input_tokens"] for u in usages]),
            "cache_creation": stats([u["cache_creation_input_tokens"] for u in usages]),
            "cache_read": stats([u["cache_read_input_tokens"] for u in usages]),
            "output": stats([u["output_tokens"] for u in usages]),
            "thinking": stats([u["thinking_tokens"] for u in usages]),
            "duration_ms": stats([u["duration_ms"] for u in usages]),
            "duration_api_ms": stats([u["duration_api_ms"] for u in usages]),
            "wall_ms": stats(walls),
            "opus_cost_usd": stats([u["opus_cost_usd"] for u in usages]),
            "total_cost_usd": stats([u["total_cost_usd"] for u in usages]),
            "input_per_kb": stats([(u["input_tokens"] + u["cache_creation_input_tokens"]) / (run["bytes"] / 1024)
                                   for u, run in zip(usages, runs)]),
            "output_per_record": stats([u["output_tokens"] / run["n_records"] for u, run in zip(usages, runs)
                                        if run["n_records"]]),
        }
        per_file = []
        for run in runs:
            rs = run["records"]
            an = [r for r in rs if "anchor" in r]
            n_pos = sum(1 for r in an if by_position(r))
            n_correct = sum(1 for r in an if r.get("placement_ok"))
            n_pos_correct = sum(1 for r in an if by_position(r) and r.get("placement_ok"))
            per_file.append({"blob_sha": run["blob_sha"], "path": run["path"], "repo": run["repo"],
                             "bytes": run["bytes"], "records": len(rs), "anchored": len(an),
                             "found": sum(1 for r in an if r["status"] == "found"),
                             "correct": n_correct, "position": n_pos, "position_correct": n_pos_correct,
                             "unanchorable": sum(1 for r in rs if r["verdict"] == "unanchorable"),
                             "acc": (n_correct / len(rs)) if rs else None,
                             # Same accuracy with the position-disambiguated
                             # records taken out of both sides.
                             "acc_strict": ((n_correct - n_pos_correct) / (len(rs) - n_pos)
                                            if len(rs) - n_pos else None),
                             "unanch_rate": (sum(1 for r in rs if r["verdict"] == "unanchorable") / len(rs)) if rs else None})
        per_file.sort(key=lambda f: (f["acc"] if f["acc"] is not None else 2, -f["records"]))
        agg["efforts"][effort] = {
            "runs": len(runs), "records": n,
            # Line-weighted placement: the v0 run scored one record per comment
            # line, v1 scores one per block, so the record-level rate changes
            # denominator. These two are comparable across that change.
            "comment_lines": n_lines, "comment_lines_correct": lines_correct,
            "comment_lines_strict": n_lines_strict, "comment_lines_correct_strict": lines_correct_strict,
            "per_file": per_file,
            "macro_acc": stats([f["acc"] for f in per_file]),
            "macro_acc_strict": stats([f["acc_strict"] for f in per_file]),
            "macro_unanch": stats([f["unanch_rate"] for f in per_file]),
            "files_100pct": sum(1 for f in per_file if f["acc"] == 1.0),
            "files_ge_95pct": sum(1 for f in per_file if f["acc"] is not None and f["acc"] >= 0.95),
            "verdicts": dict(verdicts), "statuses": dict(statuses),
            "anchored": len(anchored),
            "coverage_ok": sum(1 for r in rows if r["coverage"] == "ok"),
            "dropped": verdicts.get("dropped", 0),
            "dup": sum(1 for r in rows if r["coverage"] == "dup"),
            "extra_ids": sum(len(run["extra_ids"]) for run in runs),
            "found": statuses.get("found", 0),
            "correct": sum(1 for r in anchored if r.get("placement_ok")),
            # The headline "did the model name the right thing" numbers. Strict
            # excludes every record the model's own line hint resolved (§1.5),
            # because there the expected line and the input line are the same
            # number and the comparison is circular.
            "anchored_strict": len(strict_rows),
            "correct_strict": sum(1 for r in strict_rows if r.get("placement_ok")),
            "position_disambiguated": len(pos_rows),
            "position_disambiguated_correct": sum(1 for r in pos_rows if r.get("placement_ok")),
            "position_disambiguated_wrong": sum(1 for r in pos_rows if not r.get("placement_ok")),
            "position_disambiguated_candidate_hit": sum(1 for r in pos_rows if r.get("candidate_hit")),
            "position_candidates": stats([r.get("n_candidates") for r in pos_rows]),
            "ambiguous_hit": sum(1 for r in anchored if r.get("ambiguous_hit")),
            "kind_ok": sum(1 for r in anchored if r.get("kind_ok")),
            "unanchorable": verdicts.get("unanchorable", 0),
            "false_unanchorable": sum(1 for r in rows if r["verdict"] == "unanchorable" and r["nameable_at_expected"]
                                      and not r["expected_ambiguous"]),
            "unanchorable_expected_ambiguous": sum(1 for r in rows if r["verdict"] == "unanchorable" and r["expected_ambiguous"]),
            "unanchorable_nameable_any": sum(1 for r in rows if r["verdict"] == "unanchorable" and r["nameable_at_expected"]),
            "strip_only_found": len(strip_only),
            "strip_moved": len(strip_moved),
            "retried_runs": sum(1 for run in runs if run["attempts"] > 1),
            "num_turns": dict(collections.Counter(u["num_turns"] for u in usages)),
            "cache_read_over_20k": sum(1 for u in usages if u["cache_read_input_tokens"] > 20000),
            "by_group": by_group, "by_depth": by_depth, "by_last_kind": by_last_kind,
            "kind_confusion": {f"{e}->{p}": c for (e, p), c in sorted(kinds.items())},
            "tokens": tok,
        }
    # paired subset: blobs that have a run at every effort with >= 1 run
    have = [e for e in EFFORTS if scored.get(e)]
    common = set.intersection(*[{run["blob_sha"] for run in scored[e]} for e in have]) if have else set()
    paired = {"blobs": len(common), "efforts": {}}
    for e in have:
        rows = [r for run in scored[e] if run["blob_sha"] in common for r in run["records"]]
        an = [r for r in rows if "anchor" in r]
        paired["efforts"][e] = {
            "records": len(rows), "anchored": len(an),
            "found": sum(1 for r in an if r["status"] == "found"),
            "correct": sum(1 for r in an if r.get("placement_ok")),
            "anchored_strict": sum(1 for r in an if not by_position(r)),
            "correct_strict": sum(1 for r in an if r.get("placement_ok") and not by_position(r)),
            "position_disambiguated": sum(1 for r in an if by_position(r)),
            "position_disambiguated_correct": sum(1 for r in an if by_position(r) and r.get("placement_ok")),
            "ambiguous_hit": sum(1 for r in an if r.get("ambiguous_hit")),
            "unanchorable": sum(1 for r in rows if r["verdict"] == "unanchorable"),
            "missing": sum(1 for r in an if r["status"] == "missing"),
            "ambiguous": sum(1 for r in an if r["status"] == "ambiguous"),
            "wrong_place": sum(1 for r in an if r["verdict"] == "wrong-place"),
            "kind_ok": sum(1 for r in an if r.get("kind_ok")),
            "by_group": {g: {"records": sum(1 for r in rows if rec_group(r) == g and not by_position(r)),
                             "correct": sum(1 for r in rows if rec_group(r) == g and not by_position(r)
                                            and r.get("placement_ok")),
                             "position": sum(1 for r in rows if rec_group(r) == g and by_position(r))}
                         for g in sorted({rec_group(r) for r in rows})},
            "tokens": {k: stats([run["usage"][k] for run in scored[e] if run["blob_sha"] in common])
                       for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                 "output_tokens", "thinking_tokens", "duration_ms")},
            "wall_ms": stats([run["wall_ms"] for run in scored[e] if run["blob_sha"] in common]),
        }
    agg["paired"] = paired
    # 3-way agreement
    per_record_eff: dict[tuple, dict] = collections.defaultdict(dict)
    for effort in EFFORTS:
        for run in scored.get(effort, []):
            for r in run["records"]:
                per_record_eff[(run["blob_sha"], r["id"])][effort] = r
    complete = {k: v for k, v in per_record_eff.items() if all(e in v for e in EFFORTS)}
    def label(r):
        return squeeze(r["anchor"]) if "anchor" in r else "<" + r["verdict"] + ">"
    agree3 = sum(1 for v in complete.values() if len({label(v[e]) for e in EFFORTS}) == 1)
    def pair(a, b):
        both = [v for v in per_record_eff.values() if a in v and b in v]
        return {"n": len(both), "agree": sum(1 for v in both if label(v[a]) == label(v[b])),
                "agree_and_correct_b": sum(1 for v in both if label(v[a]) == label(v[b]) and v[b].get("placement_ok")),
                "disagree_a_correct_b_not": sum(1 for v in both if label(v[a]) != label(v[b]) and v[a].get("placement_ok") and not v[b].get("placement_ok")),
                "disagree_b_correct_a_not": sum(1 for v in both if label(v[a]) != label(v[b]) and v[b].get("placement_ok") and not v[a].get("placement_ok"))}
    pairs = {"low-medium": pair("low", "medium"), "medium-high": pair("medium", "high"), "low-high": pair("low", "high")}
    agree_hm = pairs["medium-high"]["agree"]
    agree_lm = pairs["low-medium"]["agree"]
    agree_lh = pairs["low-high"]["agree"]
    all_diff = [{"blob_sha": k[0], "id": k[1], **{e: {"anchor": v[e].get("anchor"), "verdict": v[e]["verdict"],
                                                    "line": v[e].get("resolved_line")} for e in EFFORTS},
                 "expected_lines": v["low"]["expected_lines"], "rkind": v["low"]["rkind"], "line": v["low"]["line"]}
                for k, v in complete.items() if len({label(v[e]) for e in EFFORTS}) == 3]
    # is agreement predictive of correctness?
    agree_correct = sum(1 for v in complete.values() if len({label(v[e]) for e in EFFORTS}) == 1
                        and v["high"].get("placement_ok"))
    agg["agreement"] = {"records_with_3_runs": len(complete), "agree_3way": agree3,
                        "agree_high_medium": agree_hm, "agree_low_medium": agree_lm, "agree_low_high": agree_lh,
                        "all_three_differ": len(all_diff), "agree3_and_correct": agree_correct,
                        "pairs": pairs, "all_three_differ_list": all_diff}
    # sample composition
    agg["sample"] = {
        "n": len(sample),
        "per_repo": dict(collections.Counter(e["repo"] for e in sample)),
        "per_bucket": dict(collections.Counter(e["bucket"] for e in sample)),
        "bytes_total": sum(e["bytes"] for e in sample),
        "records_total": sum(e["n_records"] for e in sample),
        "records_stats": stats([e["n_records"] for e in sample]),
        "bytes_stats": stats([e["bytes"] for e in sample]),
    }
    return agg


def failure_groups(scored: dict[str, list[dict]]) -> dict:
    """Group failures by pattern across efforts (each item carries its effort)."""
    groups: dict[str, dict[str, list]] = {"unanchorable": collections.defaultdict(list),
                                          "malformed": collections.defaultdict(list),
                                          "missing": collections.defaultdict(list),
                                          "ambiguous": collections.defaultdict(list),
                                          "wrong_place": collections.defaultdict(list),
                                          "wrong_place_by_position": collections.defaultdict(list),
                                          "dropped": collections.defaultdict(list),
                                          "kind_mismatch": collections.defaultdict(list)}
    for effort in EFFORTS:
        for run in scored.get(effort, []):
            for r in run["records"]:
                item = {"effort": effort, "sha": run["blob_sha"][:10], "path": run["path"], "id": r["id"],
                        "rkind": r["rkind"], "line": r["line"], "expected": r["expected_lines"],
                        "anchor": r.get("anchor"), "resolved": r.get("resolved_line")}
                v = r["verdict"]
                if v == "unanchorable":
                    reason = r.get("reason", "")
                    key = classify_reason(reason)
                    item["reason"] = reason
                    item["nameable"] = r["nameable_at_expected"]
                    groups["unanchorable"][key].append(item)
                elif v == "malformed":
                    err = r["outcome"].get("error", "")
                    item["error"] = err
                    groups["malformed"][classify_malformed(err, r["anchor"])].append(item)
                elif v == "missing":
                    o = r["outcome"]
                    item["resolved_prefix"] = o.get("resolved_prefix")
                    item["suggestions"] = o.get("suggestions")
                    groups["missing"][classify_missing(r)].append(item)
                elif v == "ambiguous":
                    item["candidates"] = [c["line"] for c in r["outcome"].get("candidates", [])]
                    item["hit"] = r.get("ambiguous_hit")
                    groups["ambiguous"][("symbol path (F1/F2 rebinding)" if r["depth"] == "symbol"
                                         else f"segment `{r['last_kind']}` needs ~n")].append(item)
                elif v == "wrong-place":
                    item["distance"] = r.get("distance")
                    groups["wrong_place"][classify_wrong(r)].append(item)
                elif v == "wrong-place-by-position":
                    # The tie was settled by the model's line and the pick still
                    # missed: either the hint itself was wrong or the anchor named
                    # the wrong family of siblings.
                    item["distance"] = r.get("distance")
                    item["line_hint"] = r.get("line_hint")
                    item["candidates"] = [c["line"] for c in r["outcome"].get("candidates", [])]
                    groups["wrong_place_by_position"][classify_wrong(r)].append(item)
                elif v == "dropped":
                    groups["dropped"]["id missing from output"].append(item)
                if "anchor" in r and not r.get("kind_ok"):
                    item2 = dict(item)
                    item2["kind"] = r["kind"]
                    groups["kind_mismatch"][f"{r['expected_kind']} -> {r['kind']}"].append(item2)
    return {k: dict(sorted(v.items(), key=lambda kv: -len(kv[1]))) for k, v in groups.items()}


def classify_reason(reason: str) -> str:
    s = reason.lower()
    if "comprehension" in s or "lambda" in s or "generator" in s:
        return "inside comprehension/lambda (§1.6)"
    if "commented-out" in s or "commented out" in s or "dead code" in s or "disabled code" in s:
        return "commented-out code (also usually end-of-block)"
    if re.search(r"end of (the )?(file|module)|module.footer|footer|end-of-file|eof", s):
        return "end of file / module footer: no following statement"
    if re.search(r"no following statement|nothing (below|after)|end of (its |the |a |\w+ )*(body|block)|dangling|"
                 r"last (line|statement) (of|in) (its |the )?block|end-of-block|closes the block|after the last", s):
        return "end of block: no following statement in scope"
    if re.search(r"tuple|list literal|unnamed (row|element|item|int)|positional|row of|mid-literal|"
                 r"interior line|between (elements|unnamed)|starred|element segment|named element|no named", s):
        return "unnamed element inside a literal / positional argument (§1.4 gap)"
    if re.search(r"condition expression|test expression|multi-line (if|expression)|inside (a|the) .*expression|"
                 r"operand|sub-expression|part of (a|the) (test|call|expression)", s):
        return "inside a multi-line expression (condition / call args)"
    if re.search(r"bare (attribute|expression|name)|expression statement|no statement kind", s):
        return "bare expression statement (no `expr` kind in v0)"
    if re.search(r"section|banner|separator|divider|heading|=====|-----|prose block|narrative", s):
        return "section banner / prose block between statements"
    if re.search(r"else|finally|elif", s):
        return "else/elif/finally clause"
    if re.search(r"duplicate|identical|ambiguous|occurrence|~n", s):
        return "duplicate statements / tie"
    if re.search(r"decorator|signature|def line|class line|import|docstring", s):
        return "structural (signature/decorator/import/docstring)"
    if "continuation of" in s or "same block as" in s or "same as r" in s:
        return "continuation of a previous unanchorable comment"
    return "other"


def classify_malformed(err: str, anchor: str | None) -> str:
    e = err.lower()
    if "kind" in e or "unknown" in e:
        return "unknown segment kind"
    if "empty" in e:
        return "empty anchor"
    if "discriminator" in e or ":" in e:
        return "bad discriminator / separator"
    return f"other: {err[:60]}"


TIE_RE = re.compile(r"~\d+")


def classify_missing(r: dict) -> str:
    o = r["outcome"]
    a = r["anchor"]
    prefix = o.get("resolved_prefix")
    sugg = o.get("suggestions") or []
    sq = squeeze(a)
    if r["depth"] == "symbol":
        return "symbol path names nothing (attribute/import/local name/typo)"
    if re.search(r"/elif(~\d+)?(/|$)", a):
        return "elif written without its condition (FORMAT §1.3 table says none; resolver keys `elif:cond`) — anywhere in the path"
    if any(TIE_RE.sub("", squeeze(x)) == TIE_RE.sub("", sq) for x in sugg):
        if TIE_RE.search(a):
            return "authored ~n tie that the resolver does not derive (wrong n / no collision)"
        return "tie ~n missing on an INNER segment (resolver only aliases the last segment untied)"
    if r["last_kind"] == "import":
        return "import discriminator: imported name given, resolver keys from-imports by module"
    if prefix is None:
        return "symbol path of a segmented anchor names nothing"
    kind = r["last_kind"]
    sqs = [squeeze(x) for x in sugg]
    noparen = lambda t: t.replace("(", "").replace(")", "")
    noquote = lambda t: t.replace('"', "").replace("'", "")
    if any("#" in x.split("#", 1)[-1] or "\\" in x for x in sqs):
        return "resolver discriminator contains a comment or backslash continuation (resolver hazard: raw source)"
    if any(noparen(x) == noparen(sq) for x in sqs):
        return "parenthesization of the discriminator differs (multi-line condition)"
    if any(noquote(x) == noquote(sq) for x in sqs):
        return "string quoting of an item/key discriminator differs (§1.4 `key:retries` vs `item:\"x\"`)"
    if re.search(r"/except(/|$)", a) and any("except:*" in x for x in sqs):
        return "bare `except:` — resolver keys it `except:*`"
    if any(x.startswith(sq + ",") for x in sqs):
        return "tuple target: model named the first target only / resolver keeps trailing comma"
    if any(x.startswith(sq + "(") for x in sqs):
        return "callee is itself a call: `call:getattr` vs resolver `call:getattr(...)`"
    return f"segment `{kind}` names nothing under a resolved prefix (residual)"


def classify_wrong(r: dict) -> str:
    d = r.get("distance") or 0
    if r["rkind"] != "comment":
        return "docstring/string anchored to wrong symbol"
    enc = r.get("enclosing_stmt_line")
    if enc is not None and r.get("resolved_line") == enc and enc not in r["expected_lines"]:
        return "hoisted to the enclosing statement (comment sits on an element inside it)"
    if r["depth"] == "symbol":
        return "symbol anchor for a comment (points at first binding / definition)"
    if TIE_RE.search(r["anchor"]):
        return "authored ~n tie picked the wrong sibling (model miscounted)"
    if d <= 3:
        return "off by 2-3 lines (adjacent statement)"
    if r["placement"] == "full-line":
        return "lead comment attached to a distant statement"
    return "trail comment attached to a distant statement"


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def fmt_stat(s: dict, div: float = 1.0, digits: int = 0) -> str:
    if not s or s.get("n", 0) == 0:
        return "n/a"
    f = (lambda v: f"{v / div:,.{digits}f}")
    return f"{f(s['mean'])} / {f(s['median'])} / {f(s['p90'])} / {f(s['total'])}"


def write_reports(agg: dict, groups: dict, scored: dict[str, list[dict]], sample: list[dict],
                  run_log: dict) -> None:
    (OUT / "report.json").write_text(json.dumps({"aggregate": agg, "failure_groups": groups,
                                                  "runs": scored, "run_log": run_log,
                                                  "generated": dt.datetime.now().isoformat(timespec="seconds"),
                                                  "prompt_template": {"system_prompt_file": str(SYSTEM_PROMPT_FILE),
                                                                      "contract": CONTRACT,
                                                                      "user_prompt_shape": USER_PROMPT_SHAPE,
                                                                      "json_schema": JSON_SCHEMA,
                                                                      "command": " ".join(claude_cmd("<effort>"))}},
                                                 indent=1, default=str))
    L: list[str] = []
    L.append("# Converter pilot report (EST-111)\n")
    L.append(f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} · model `{MODEL}` via headless Claude Code "
             f"(`claude -p`, subscription) · resolver `{RESOLVER.name}` · sample {agg['sample']['n']} blobs")
    L.append("")
    s = agg["sample"]
    done = ", ".join(f"{e} {agg['efforts'][e]['runs']}/{agg['sample']['n']}" for e in EFFORTS)
    blocked = {e: len(list((RUNS / e).glob("*.blocked.json"))) if (RUNS / e).exists() else 0 for e in EFFORTS}
    L.append(f"**Runs on disk:** {done}. Blocked-by-spend-limit files: {blocked}. "
             "Runs are resumable (`convert_pilot.py run` skips finished blobs); rerun `score` after more runs land.\n")
    L.append("## Sample\n")
    L.append(md_table(["repo", "blobs"], [[k, v] for k, v in sorted(s["per_repo"].items())]))
    L.append("")
    L.append(md_table(["size bucket", "blobs"], [[k, v] for k, v in s["per_bucket"].items()]))
    L.append("")
    L.append(f"Total {s['bytes_total']:,} bytes, {s['records_total']:,} documentation records "
             f"(per file mean {s['records_stats']['mean']}, median {s['records_stats']['median']}, "
             f"max {s['records_stats']['max']}). Sample list: `corpus/convert-pilot/sample.json`.")
    L.append("")
    L.append("## Calls\n")
    L.append(md_table(["effort", "runs scored", "runs retried", "failed files"],
                      [[e, agg["efforts"][e]["runs"], agg["efforts"][e]["retried_runs"],
                        run_log.get(e, {}).get("failed_files", 0)] for e in EFFORTS]))
    L.append("")
    L.append("## Headline per effort\n")
    L.append("**Placement here is the strict number: it excludes every record that only resolved "
             "because of the model's line hint.** Those are counted on their own below. Scoring them "
             "as placement would be circular — the model is handed each record's position in the "
             "prompt, hands a line back, and the expected line is derived from the same record, so "
             "the comparison mostly measures copying, not anchoring.\n")
    rows = []
    for e in EFFORTS:
        a = agg["efforts"][e]
        n = a["records"] or 1
        n_strict = (a["records"] - a["position_disambiguated"]) or 1
        rows.append([e, a["records"], pct(a["coverage_ok"], n), pct(a["anchored"], n),
                     pct(a["found"], a["anchored"]),
                     pct(a["correct_strict"], a["anchored_strict"]), pct(a["correct_strict"], n_strict),
                     f'{a["position_disambiguated"]} ({pct(a["position_disambiguated"], n)})',
                     pct(a["correct"] + a["ambiguous_hit"], n),
                     pct(a["unanchorable"], n), f'{a["false_unanchorable"]} strict / {a["unanchorable_nameable_any"]} any',
                     pct(a["kind_ok"], a["anchored"]),
                     a["strip_only_found"]])
    L.append(md_table(["effort", "records", "coverage ok", "anchored",
                       "resolve=found (of anchored, incl. position-disambiguated)",
                       "placement correct (of anchored, EXCL. position)",
                       "placement correct (of records, EXCL. position)",
                       "position-disambiguated (own bucket, not in the two columns left of this)",
                       "lenient: all correct incl. position + ambiguous with expected among candidates (of all)",
                       "unanchorable", "false unanchorable (strict: unambiguous expected line has resolver anchors / any)", "kind ok",
                       "found on orig only (not on stripped)"], rows))
    L.append("")
    L.append("## Position disambiguation (§1.5)\n")
    L.append("Ties are derived, never authored: two textually identical siblings cannot be told apart "
             "by any anchor an author could write. Every anchor now carries the line the model says it "
             "names; the resolver uses it *only* when the anchor is `Ambiguous`, and marks the outcome "
             "`disambiguated_by: \"position\"` so it never merges with an unambiguous hit.\n")
    rows = []
    for e in EFFORTS:
        a = agg["efforts"][e]
        if not a["runs"]:
            continue
        cand = a["position_candidates"]
        rows.append([e, a["anchored"], a["position_disambiguated"],
                     pct(a["position_disambiguated"], a["anchored"]),
                     a["statuses"].get("ambiguous", 0),
                     a["position_disambiguated_candidate_hit"],
                     pct(a["position_disambiguated_candidate_hit"], a["position_disambiguated"]),
                     a["position_disambiguated_correct"], a["position_disambiguated_wrong"],
                     pct(a["position_disambiguated_correct"], a["position_disambiguated"]),
                     f'{cand["mean"]:.1f}' if cand["n"] else "n/a"])
    L.append(md_table(["effort", "anchored", "resolved by position", "share of anchored",
                       "still ambiguous (no usable hint)",
                       "expected among candidates", "candidate-set hit rate (anchor work)",
                       "hint agreed with expected", "hint disagreed with expected",
                       "agreement rate (CIRCULAR — see below)",
                       "mean candidates"], rows))
    L.append("")
    L.append("Two different things in that table, and only one of them is honest evidence about the "
             "model.\n")
    L.append("**Candidate-set hit rate is anchor work.** It asks whether the expected line was among "
             "the siblings the anchor named at all — that is the anchor naming the right family, and "
             "no line hint can fake it. Read this one.\n")
    L.append("**Agreement rate is circular. Do not read it as accuracy.** The line came from the model "
             "and the expected line is derived from the same record, so agreement mostly says the "
             "model copied the number the prompt showed it. Picking *which* sibling of a correctly "
             "named family is the hint's job, not the anchor's. The feature's real payoff is the "
             "coverage column — records that stop being unresolvable ambiguities — with the strict "
             "placement number above left untouched by it.\n")
    L.append("Line-weighted placement (one unit per physical comment line, excluding "
             "position-disambiguated records on both sides):\n")
    L.append(md_table(["effort", "comment lines (excl. position)", "correct", "rate"],
                      [[e, agg["efforts"][e]["comment_lines_strict"],
                        agg["efforts"][e]["comment_lines_correct_strict"],
                        pct(agg["efforts"][e]["comment_lines_correct_strict"],
                            agg["efforts"][e]["comment_lines_strict"])] for e in EFFORTS
                       if agg["efforts"][e]["runs"]]))
    L.append("")
    pr = agg["paired"]
    if pr["blobs"] and len(pr["efforts"]) > 1:
        L.append(f"Paired comparison on the {pr['blobs']} blobs that have a run at every effort listed "
                 "(the only like-for-like effort comparison when a batch is incomplete):\n")
        rows = []
        for e, a in pr["efforts"].items():
            n = a["records"] or 1
            n_strict = (a["records"] - a["position_disambiguated"]) or 1
            rows.append([e, a["records"], pct(a["anchored"], n), pct(a["found"], a["anchored"]),
                         pct(a["correct_strict"], n_strict), a["position_disambiguated"],
                         pct(a["correct"] + a["ambiguous_hit"], n), pct(a["unanchorable"], n),
                         a["missing"], a["ambiguous"], a["wrong_place"], pct(a["kind_ok"], a["anchored"]),
                         f'{a["tokens"]["output_tokens"]["mean"]:,.0f}', f'{(a["tokens"]["thinking_tokens"]["mean"] or 0):,.0f}',
                         f'{a["wall_ms"]["mean"]/1000:,.1f}'])
        L.append(md_table(["effort", "records", "anchored", "found (of anchored)",
                           "correct (of records, EXCL. position)", "position-disambiguated",
                           "lenient (of all)", "unanchorable", "missing", "ambiguous", "wrong place", "kind ok",
                           "mean output tok", "mean thinking tok", "mean wall s"], rows))
        L.append("")
        groups_ = sorted({g for a in pr["efforts"].values() for g in a["by_group"]})
        rows = [[g] + [f'{pr["efforts"][e]["by_group"].get(g, {}).get("correct", 0)}/'
                       f'{pr["efforts"][e]["by_group"].get(g, {}).get("records", 0)} '
                       f'({pct(pr["efforts"][e]["by_group"].get(g, {}).get("correct", 0), pr["efforts"][e]["by_group"].get(g, {}).get("records", 0))})'
                       f' +{pr["efforts"][e]["by_group"].get(g, {}).get("position", 0)} pos'
                       for e in pr["efforts"]] for g in groups_]
        L.append(md_table(["record kind (paired; correct/records excl. position, then position count)"]
                          + list(pr["efforts"]), rows))
        L.append("")
    L.append("Per-file (macro) view — accuracy = correct / records of that file. `strict` drops "
             "position-disambiguated records from both sides; the plain column keeps them and is the "
             "circular one:\n")
    rows = []
    for e in EFFORTS:
        a = agg["efforts"][e]
        m = a["macro_acc"]; ms = a["macro_acc_strict"]; u = a["macro_unanch"]
        if m["n"]:
            rows.append([e, m["n"], f'{100*ms["mean"]:.1f}%' if ms["n"] else "n/a",
                         f'{100*ms["median"]:.1f}%' if ms["n"] else "n/a",
                         f'{100*m["mean"]:.1f}%', f'{100*m["median"]:.1f}%', f'{100*m["min"]:.1f}%',
                         a["files_100pct"], a["files_ge_95pct"], f'{100*u["mean"]:.1f}%'])
    L.append(md_table(["effort", "files", "macro mean acc (strict)", "median acc (strict)",
                       "macro mean acc (incl. position)", "median acc (incl. position)", "min acc",
                       "files at 100% (incl. position)", "files >= 95% (incl. position)",
                       "macro mean unanchorable"], rows))
    L.append("")
    L.append("Worst files per effort (accuracy = correct / records):\n")
    rows = []
    for e in EFFORTS:
        for f in agg["efforts"][e]["per_file"][:6]:
            rows.append([e, f["path"], f["records"], f["correct"], f["unanchorable"], f'{100*(f["acc"] or 0):.1f}%'])
    L.append(md_table(["effort", "path", "records", "correct", "unanchorable", "acc"], rows))
    L.append("")
    L.append("Resolver status of anchored records:\n")
    st_keys = ["found", "unverified", "ambiguous", "missing", "malformed", "resolver-error"]
    L.append(md_table(["effort"] + st_keys, [[e] + [agg["efforts"][e]["statuses"].get(k, 0) for k in st_keys]
                                              for e in EFFORTS]))
    L.append("")
    L.append("## Placement accuracy per record kind (per effort)\n")
    all_groups = sorted({g for e in EFFORTS for g in agg["efforts"][e]["by_group"]})
    rows = []
    for g in all_groups:
        for e in EFFORTS:
            b = agg["efforts"][e]["by_group"].get(g)
            if not b:
                continue
            rows.append([g, e, b["records"], b["anchored"], b["unanchorable"], b["dropped"], b["found"],
                         b["correct_strict"], pct(b["correct_strict"], b["anchored_strict"]),
                         pct(b["correct_strict"], b["records"] - b["position"]),
                         f'{b["position"]} ({b["position_correct"]} agreed)',
                         b["wrong_place"], f'{b["ambiguous"]} ({b["ambiguous_hit"]} hit)', b["missing"],
                         b["malformed"], b["unverified"], pct(b["kind_ok"], b["anchored"]), b["expected_ambiguous"]])
    L.append(md_table(["record kind", "effort", "records", "anchored", "unanch.", "dropped", "found",
                       "correct (excl. position)", "acc (of anchored, excl. position)",
                       "acc (of records, excl. position)", "position-disambiguated",
                       "wrong place", "ambiguous", "missing",
                       "malformed", "unverified", "kind ok", "expected-ambiguous"], rows))
    L.append("")
    L.append("## Placement accuracy per anchor depth\n")
    rows = []
    for d in ("symbol", "1-seg", "2+seg"):
        for e in EFFORTS:
            b = agg["efforts"][e]["by_depth"][d]
            rows.append([d, e, b["anchored"], b["found"], b["correct_strict"],
                         pct(b["correct_strict"], b["anchored_strict"]), b["position"],
                         b["ambiguous"], b["missing"], b["malformed"]])
    L.append(md_table(["depth", "effort", "anchored", "found", "correct (excl. position)",
                       "acc (excl. position)", "position-disambiguated", "ambiguous", "missing", "malformed"], rows))
    L.append("")
    lk_effort = "high" if agg["efforts"]["high"]["runs"] else "low"
    L.append(f"## Placement accuracy per last segment kind (effort {lk_effort})\n")
    bl = agg["efforts"][lk_effort]["by_last_kind"]
    rows = [[k, b["anchored"], b["found"], b["correct_strict"], pct(b["correct_strict"], b["anchored_strict"]),
             b["position"], b["ambiguous"], b["missing"], b["malformed"]]
            for k, b in sorted(bl.items(), key=lambda kv: -kv[1]["anchored"])]
    L.append(md_table(["last kind", "anchored", "found", "correct (excl. position)", "acc (excl. position)",
                       "position-disambiguated", "ambiguous", "missing", "malformed"], rows))
    L.append("")
    L.append("## Kind prediction (expected -> predicted, counts)\n")
    rows = []
    keys = sorted({k for e in EFFORTS for k in agg["efforts"][e]["kind_confusion"]})
    for k in keys:
        rows.append([k] + [agg["efforts"][e]["kind_confusion"].get(k, 0) for e in EFFORTS])
    L.append(md_table(["expected->predicted"] + list(EFFORTS), rows))
    L.append("")
    L.append("## Tokens and latency per call (mean / median / p90 / total)\n")
    rows = []
    for e in EFFORTS:
        t = agg["efforts"][e]["tokens"]
        rows.append([e, t["input_uncached"]["n"], fmt_stat(t["input_uncached"]), fmt_stat(t["cache_read"]),
                     fmt_stat(t["output"]), fmt_stat(t["thinking"]), fmt_stat(t["duration_ms"], 1000, 1),
                     fmt_stat(t["wall_ms"], 1000, 1), fmt_stat(t["opus_cost_usd"], 1, 3)])
    L.append(md_table(["effort", "calls", "input (file+prompt, uncached = input+cache_creation)", "cache_read (CC overhead + system prompt)",
                       "output", "thinking", "duration_ms/1000 (s)", "wall (s)", "nominal cost USD (opus only)"], rows))
    L.append("")
    rows = []
    for e in EFFORTS:
        t = agg["efforts"][e]["tokens"]
        a = agg["efforts"][e]
        kb = sum(f["bytes"] for f in a["per_file"]) / 1024 or 1
        nrec = sum(f["records"] for f in a["per_file"]) or 1
        rows.append([e, f'{t["input_uncached"]["total"] / kb:,.0f}', fmt_stat(t["input_per_kb"], 1, 0),
                     f'{t["output"]["total"] / nrec:,.1f}', fmt_stat(t["output_per_record"], 1, 1),
                     fmt_stat(t["duration_api_ms"], 1000, 1)])
    L.append(md_table(["effort", "input tokens per KB (pooled)", "input tokens per KB per file (mean/median/p90/sum)",
                       "output tokens per record (pooled)", "output tokens per record per file", "duration_api (s)"], rows))
    L.append("")
    L.append("Projection per 1,000 files of this size mix (mean per call x 1000):\n")
    rows = []
    for e in EFFORTS:
        t = agg["efforts"][e]["tokens"]
        if not t["input_uncached"]["n"]:
            continue
        rows.append([e, f'{t["input_uncached"]["mean"] * 1000:,.0f}', f'{t["cache_read"]["mean"] * 1000:,.0f}',
                     f'{t["output"]["mean"] * 1000:,.0f}', f'{(t["thinking"]["mean"] or 0) * 1000:,.0f}',
                     f'{t["opus_cost_usd"]["mean"] * 1000:,.0f}', f'{t["wall_ms"]["mean"] * 1000 / 3.6e6:,.1f}'])
    L.append(md_table(["effort", "input tokens", "cache_read tokens", "output tokens", "thinking tokens",
                       "nominal USD", "wall hours at 1 call at a time"], rows))
    L.append("")
    L.append(md_table(["effort", "num_turns distribution", "calls with cache_read > 20k"],
                      [[e, agg["efforts"][e]["num_turns"], agg["efforts"][e]["cache_read_over_20k"]] for e in EFFORTS]))
    L.append("")
    L.append("Notes: `input` = `usage.input_tokens + usage.cache_creation_input_tokens` (the file, records, "
             "schema, and — on the first calls — the system prompt before it was cached). `cache_read` is the "
             "byte-identical system prompt (FORMAT.md + contract) plus Claude Code's own fixed overhead, read "
             "from cache. Costs are nominal API prices reported by the CLI; nothing was billed (subscription).")
    L.append("")
    ag = agg["agreement"]
    L.append("## Three-way agreement across efforts\n")
    n3 = ag["records_with_3_runs"] or 1
    L.append(md_table(["metric", "count", "rate"], [
        ["records with all three efforts", ag["records_with_3_runs"], ""],
        ["3-way agreement (same anchor or same non-anchor verdict)", ag["agree_3way"], pct(ag["agree_3way"], n3)],
        ["3-way agreement AND placement correct at high", ag["agree3_and_correct"], pct(ag["agree3_and_correct"], n3)],
        ["all three differ", ag["all_three_differ"], pct(ag["all_three_differ"], n3)],
    ]))
    L.append("")
    L.append("Pairwise (on records that have both runs):\n")
    L.append(md_table(["pair", "records", "same anchor", "rate", "same and correct (2nd)", "differ: 1st correct, 2nd not", "differ: 2nd correct, 1st not"],
                      [[k, v["n"], v["agree"], pct(v["agree"], v["n"]), v["agree_and_correct_b"],
                        v["disagree_a_correct_b_not"], v["disagree_b_correct_a_not"]] for k, v in ag["pairs"].items()]))
    L.append("")
    if ag["all_three_differ_list"]:
        L.append("Records where low ≠ medium ≠ high (first 40; full list in report.json):\n")
        rows = []
        for it in ag["all_three_differ_list"][:40]:
            rows.append([it["blob_sha"][:8], it["id"], it["rkind"], it["line"], it["expected_lines"]] +
                        [f'`{it[e]["anchor"]}` → {it[e]["verdict"]}@{it[e]["line"]}' if it[e]["anchor"] else it[e]["verdict"]
                         for e in EFFORTS])
        L.append(md_table(["sha", "id", "kind", "line", "expected", "low", "medium", "high"], rows))
        L.append("")
    L.append("## Failure patterns (all efforts pooled; see failures.md)\n")
    for cat, g in groups.items():
        total = sum(len(v) for v in g.values())
        L.append(f"### {cat} ({total})\n")
        if not g:
            L.append("none\n")
            continue
        L.append(md_table(["pattern", "count", "low", "medium", "high"],
                          [[k, len(v)] + [sum(1 for i in v if i["effort"] == e) for e in EFFORTS] for k, v in g.items()]))
        L.append("")
    L.append("## Prompt template\n")
    L.append("System prompt (byte-identical for every call; `corpus/convert-pilot/system-prompt.txt`) = "
             "the full text of `FORMAT.md` + `---` + the contract below.\n")
    L.append("```\n" + CONTRACT + "```\n")
    L.append("User prompt (`corpus/convert-pilot/prompts/<sha>.txt`):\n")
    L.append("```\n" + USER_PROMPT_SHAPE + "```\n")
    L.append("Command:\n")
    L.append("```\nenv -i HOME=$HOME PATH=/usr/bin:/bin:" + NODE_BIN + " USER=$USER TERM=dumb \\\n  " +
             " ".join(claude_cmd("<effort>")).replace("--json-schema ", "--json-schema '") + "'  < prompts/<sha>.txt\n```\n")
    (OUT / "report.md").write_text("\n".join(L))

    # failures.md
    F: list[str] = ["# Converter pilot — failure log (EST-81 deliverable)\n",
                    "Every record the model called unanchorable, every anchor the resolver rejected "
                    "(malformed / missing / ambiguous), and every anchor that resolved to the wrong place. "
                    "All three efforts pooled; each item is tagged with its effort. Grouped by pattern, "
                    "most frequent first. `expected` = line(s) the record should attach to; `resolved` = line "
                    "the resolver put the anchor on.\n"]
    for cat, g in groups.items():
        total = sum(len(v) for v in g.values())
        F.append(f"\n## {cat} ({total})\n")
        for pattern, items in g.items():
            F.append(f"\n### {pattern} ({len(items)})\n")
            uniq = {}
            for it in items:
                uniq.setdefault((it["sha"], it["id"], it.get("anchor")), it)
            for it in list(uniq.values())[:25]:
                extra = ""
                if cat == "unanchorable":
                    extra = f' — reason: {it["reason"]!r}; resolver has anchors at expected line: {it["nameable"]}'
                elif cat == "malformed":
                    extra = f' — error: {it["error"]}'
                elif cat == "missing":
                    extra = f' — resolved prefix: {it["resolved_prefix"]}; suggestions: {it["suggestions"]}'
                elif cat == "ambiguous":
                    extra = f' — candidates at lines {it["candidates"]}; one matches expected: {it["hit"]}'
                elif cat == "wrong_place":
                    extra = f' — resolved line {it["resolved"]}, distance {it["distance"]}'
                elif cat == "wrong_place_by_position":
                    extra = (f' — line hint {it["line_hint"]} picked line {it["resolved"]} out of '
                             f'{it["candidates"]}, distance {it["distance"]}')
                elif cat == "kind_mismatch":
                    extra = f' — predicted kind {it["kind"]}'
                anchor = f' `{it["anchor"]}`' if it.get("anchor") else ""
                F.append(f'- [{it["effort"]}] `{it["path"]}` ({it["sha"]}) {it["id"]} {it["rkind"]} line {it["line"]} '
                         f'expected {it["expected"]}{anchor}{extra}')
            if len(uniq) > 25:
                F.append(f"- … {len(uniq) - 25} more (see report.json)")
    (OUT / "failures.md").write_text("\n".join(F) + "\n")


USER_PROMPT_SHAPE = r'''\
File: <path>  (repo <owner/name>)

```
    1| <line 1 of the ORIGINAL file>
    2| <line 2>
  ...
```

Records (<N>):
r1 [comment, line 40, col 4] # verbatim comment text
r2 [docstring, lines 20–31, owner Cart.add] """first content line of the docstring
r3 [doctest_docstring (kept in source), lines 50–70, owner f] """first content line
r4 [stray_string (kept in source), line 90] """first content line
'''


def score_all(sample: list[dict]) -> tuple[dict, dict, dict]:
    scored: dict[str, list[dict]] = {e: [] for e in EFFORTS}
    run_log = {e: {"failed_files": len(list((RUNS / e).glob("*.failed.json"))) if (RUNS / e).exists() else 0}
               for e in EFFORTS}
    for i, entry in enumerate(sample, 1):
        facts = FileFacts(entry)
        stripped_path = CACHE / f'{entry["blob_sha"]}.py'
        stripped = decode(stripped_path.read_bytes()).encode("utf-8") if stripped_path.exists() else None
        for effort in EFFORTS:
            s = score_run(facts, effort, stripped)
            if s:
                scored[effort].append(s)
        if i % 10 == 0:
            log(f"scored {i}/{len(sample)}")
    agg = aggregate(scored, sample)
    groups = failure_groups(scored)
    write_reports(agg, groups, scored, sample, run_log)
    return agg, groups, run_log


# ---------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample")
    sub.add_parser("prompts")
    r = sub.add_parser("run")
    r.add_argument("--effort", choices=EFFORTS, action="append")
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--limit", type=int)
    r.add_argument("--shas", nargs="*")
    sub.add_parser("score")
    args = ap.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    if args.cmd == "sample":
        sample = build_sample()
        SAMPLE.write_text(json.dumps(sample, indent=1))
        c = collections.Counter(e["repo"] for e in sample)
        b = collections.Counter(e["bucket"] for e in sample)
        log(f"sample: {len(sample)} blobs; per repo {dict(c)}; buckets {dict(b)}; "
            f"records {sum(e['n_records'] for e in sample)}")
        return 0
    sample = load_sample()
    if args.cmd == "prompts":
        write_prompts(sample)
        return 0
    if args.cmd == "run":
        write_prompts(sample)
        sel = sample
        if args.shas:
            sel = [e for e in sel if any(e["blob_sha"].startswith(s) for s in args.shas)]
        if args.limit:
            sel = sel[:args.limit]
        for effort in (args.effort or list(EFFORTS)):
            if _stop.is_set():
                log("stopped early (hard block)")
                break
            run_effort(sel, effort, args.jobs)
        return 2 if _stop.is_set() else 0
    if args.cmd == "score":
        agg, groups, run_log = score_all(sample)
        for e in EFFORTS:
            a = agg["efforts"][e]
            if a["runs"]:
                log(f"{e}: runs={a['runs']} records={a['records']} anchored={a['anchored']} found={a['found']} "
                    f"correct_strict={a['correct_strict']}/{a['anchored_strict']} "
                    f"by_position={a['position_disambiguated']} "
                    f"(agreed {a['position_disambiguated_correct']}) "
                    f"unanchorable={a['unanchorable']} dropped={a['dropped']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
