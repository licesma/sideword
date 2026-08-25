"""Static detection of docstring consumption: which docstrings a repository reads back.

    from harness import docuse
    result = docuse.analyze({path: source_bytes, ...}, directives)
    result.keep      {path: {owner_qualname: "consumed"}}   docstrings that must survive
    result.sites     one dict per consumption site: where, what, how it resolved

A stripped tree must still import, and a repository that reads its own docstrings at
runtime -- ``inspect.cleandoc(cls.__doc__)``, ``pydoc.getdoc(func)`` -- does not. The
consuming expression names its target, so the docstring that has to stay is statically
visible; this module follows that name. It is a *general* rule: nothing here knows a
repository, only Python.

What counts as a consumption site
---------------------------------
* a read of ``X.__doc__`` (``Load`` context, or the target of an augmented assignment);
* a read of the bare name ``__doc__`` (the enclosing module's own docstring);
* a call to one of the ``[consumption] getdoc`` functions of directives.toml
  (``inspect.getdoc``, ``pydoc.getdoc``) -- the first argument is the target.

A site is *tolerant*, and ignored, when a missing docstring cannot hurt there: the value
is copied straight into another ``__doc__`` (``a.__doc__ = b.__doc__``), tested for truth
or against ``None``, or read under an ``if`` that tests it first, or inside a ``try`` that
catches ``AttributeError``/``TypeError``. Everything else is taken at face value.

How a target resolves
---------------------
* a module-level class/function, or an imported name, possibly with attribute steps
  (``EstimateAggregator.__init__``): the definition, following imports across the tree
  and inherited methods up the in-tree class hierarchy;
* the first parameter of a method (``self``/``cls``): the class and its in-tree
  subclasses; for a *metaclass* every class built by it (``MetaBaseReader.__init__``
  reading ``cls.__doc__``); for ``__init_subclass__`` every subclass;
* any other parameter of a function ``F``: every call of ``F`` in the tree is found and
  the matching argument resolved in turn (``from_function_params(EstimateAggregator
  .__init__)``), decorators included, to a bounded depth;
* a local assigned once in the same function: its right-hand side.

Anything else -- ``type(x).__doc__``, a loop variable, a subscript, an external import
-- is reported as unresolved. Unresolved sites are the analysis's blind spot and are
listed in the report so the count is visible; the admission check is what decides
whether one mattered.

The whole tree is the unit of analysis (a consumer in one module keeps docstrings in
another), which is why the result travels to the stripper as ``keep_owners`` rather
than being computed inside it: the strip cache is content-addressed by blob and stays
that way, with the context echoed into each sidecar so a disagreement is detectable.
"""

from __future__ import annotations

import ast
import re
import warnings
from dataclasses import dataclass, field
from pathlib import PurePosixPath

DEFAULT_GETDOC = ("inspect.getdoc", "pydoc.getdoc")
RULE = "consumed"
MAX_DEPTH = 4
LAYOUT_PREFIXES = ("src", "lib")
EXTERNAL_METACLASSES = {"type", "ABCMeta", "EnumMeta", "EnumType", "NamedTupleMeta"}
TOLERANT_EXCEPTIONS = {"AttributeError", "TypeError", "Exception", "BaseException"}

DEFS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)


# ---- modules ------------------------------------------------------------------------------

def module_name(path: str) -> str:
    """``a/b/c.py`` -> ``a.b.c``; ``a/b/__init__.py`` -> ``a.b``; a leading ``src``/``lib``
    layout directory is dropped."""
    parts = list(PurePosixPath(path).parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts.pop()
    if len(parts) > 1 and parts[0] in LAYOUT_PREFIXES:
        parts = parts[1:]
    return ".".join(parts)


class Module:
    """One source file, parsed on first use."""

    def __init__(self, path: str, data: bytes):
        self.path = path
        self.data = data
        self.name = module_name(path)
        self.is_package = path.endswith("__init__.py")
        self.package = self.name if self.is_package else self.name.rpartition(".")[0]
        self._tree = None
        self._failed = False
        self.defs: dict[str, ast.AST] = {}
        self.classes: dict[str, ast.ClassDef] = {}
        self.imports: dict[str, tuple[str, str | None]] = {}
        self.parents: dict[int, ast.AST] = {}
        self.chains: dict[int, tuple[ast.AST, ...]] = {}
        self.calls: list[ast.Call] = []
        self.decorated: list[tuple[ast.expr, ast.AST]] = []   # (decorator expr, decorated def)

    def contains(self, token: str) -> bool:
        return token.encode("utf-8") in self.data

    @property
    def tree(self):
        if self._tree is None and not self._failed:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self._tree = ast.parse(self.data)
            except (SyntaxError, ValueError, RecursionError, MemoryError, UnicodeDecodeError):
                self._failed = True
                return None
            self._index()
        return self._tree

    def _index(self) -> None:
        tree = self._tree
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    local = alias.asname or alias.name.split(".")[0]
                    target = alias.name if alias.asname else alias.name.split(".")[0]
                    self.imports[local] = (target, None)
            elif isinstance(stmt, ast.ImportFrom):
                base = self._relative_base(stmt.level, stmt.module)
                for alias in stmt.names:
                    if alias.name == "*":
                        continue
                    self.imports[alias.asname or alias.name] = (base, alias.name)

        def walk(node, chain):
            self.chains[id(node)] = chain
            if isinstance(node, DEFS):
                qual = ".".join(n.name for n in chain + (node,))
                self.defs.setdefault(qual, node)
                if isinstance(node, ast.ClassDef):
                    self.classes.setdefault(qual, node)
                for deco in node.decorator_list:
                    self.decorated.append((deco, node))
                inner = chain + (node,)
            else:
                inner = chain
            if isinstance(node, ast.Call):
                self.calls.append(node)
            for child in ast.iter_child_nodes(node):
                self.parents[id(child)] = node
                walk(child, inner)
        walk(tree, ())

    def _relative_base(self, level: int, module: str | None) -> str:
        if not level:
            return module or ""
        parts = self.package.split(".") if self.package else []
        up = level - 1
        base = parts[:len(parts) - up] if up <= len(parts) else []
        if module:
            base = base + module.split(".")
        return ".".join(base)

    def qualname_of(self, node: ast.AST) -> str:
        chain = self.chains.get(id(node), ())
        return ".".join(n.name for n in chain + (node,))

    def chain_of(self, node: ast.AST) -> tuple[ast.AST, ...]:
        return self.chains.get(id(node), ())

    def parent(self, node: ast.AST):
        return self.parents.get(id(node))

    def segment(self, node: ast.AST) -> str:
        try:
            seg = ast.get_source_segment(self.data.decode("utf-8", "replace"), node)
        except Exception:
            seg = None
        return (seg or ast.dump(node))[:120]


# ---- resolutions --------------------------------------------------------------------------

@dataclass(frozen=True)
class Def:
    module: Module
    qual: str                      # "" for the module itself


@dataclass(frozen=True)
class Classes:
    module: Module
    qual: str
    mode: str                      # "self_and_subclasses" | "subclasses" | "metaclass_instances"
    suffix: tuple[str, ...] = ()


@dataclass(frozen=True)
class Param:
    module: Module
    func: ast.AST
    index: int | None
    name: str
    suffix: tuple[str, ...] = ()


@dataclass(frozen=True)
class Unresolved:
    reason: str


@dataclass
class Result:
    keep: dict[str, dict[str, str]] = field(default_factory=dict)
    sites: list[dict] = field(default_factory=list)
    parse_failures: list[str] = field(default_factory=list)

    @property
    def kept(self) -> int:
        return sum(len(v) for v in self.keep.values())

    def keep_owners(self, path: str) -> list[tuple[str, str]]:
        """``[(owner_regex, rule)]`` for the stripper: exact names, escaped."""
        return sorted((re.escape(owner), rule) for owner, rule in self.keep.get(path, {}).items())


def _last_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _dotted(expr: ast.expr) -> list[str] | None:
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return parts[::-1]
    return None


def _params(func: ast.AST) -> list[str]:
    a = func.args
    return [p.arg for p in a.posonlyargs + a.args] + [p.arg for p in a.kwonlyargs]


def _positional(func: ast.AST) -> list[str]:
    a = func.args
    return [p.arg for p in a.posonlyargs + a.args]


def _is_static(func: ast.AST) -> bool:
    return any(_last_name(d) == "staticmethod" for d in func.decorator_list)


def _is_classmethod(func: ast.AST) -> bool:
    return any(_last_name(d) == "classmethod" for d in func.decorator_list)


# ---- the analysis -------------------------------------------------------------------------

class Analyzer:
    def __init__(self, blobs: dict[str, bytes], getdoc=DEFAULT_GETDOC):
        self.modules = {path: Module(path, data) for path, data in blobs.items()}
        self.by_name: dict[str, Module] = {}
        for m in self.modules.values():
            self.by_name.setdefault(m.name, m)
        self.getdoc = tuple(getdoc)
        self.getdoc_last = {g.rsplit(".", 1)[-1] for g in self.getdoc}
        self.result = Result()
        self._subclasses: dict[tuple[str, str], set[tuple[str, str]]] = {}
        self._metaclass: dict[tuple[str, str], tuple[str, str] | None | str] = {}
        self._is_meta: dict[tuple[str, str], bool] = {}

    # -- lookups
    def module(self, dotted: str) -> Module | None:
        """The in-tree module for a dotted import path, parsed; None when external."""
        m = self.by_name.get(dotted)
        if m is None:
            tail = "." + dotted
            hits = [mod for name, mod in self.by_name.items() if name.endswith(tail)]
            m = hits[0] if len(hits) == 1 else None
        if m is not None and m.tree is None:
            return None
        return m

    def key(self, module: Module, qual: str) -> tuple[str, str]:
        return (module.path, qual)

    def class_at(self, key: tuple[str, str]) -> ast.ClassDef | None:
        m = self.modules.get(key[0])
        if m is None or m.tree is None:
            return None
        return m.classes.get(key[1])

    # -- resolution
    def resolve_dotted(self, module: Module, parts: list[str], depth: int = 0):
        """A dotted name read in ``module``'s global scope."""
        if module.tree is None or not parts or depth > MAX_DEPTH + 4:
            return Unresolved("unparseable module" if module.tree is None else "empty name")
        first, rest = parts[0], parts[1:]
        if first in module.defs:
            qual = first
            for step in rest:
                nxt = qual + "." + step
                if nxt in module.defs:
                    qual = nxt
                    continue
                if qual in module.classes and len(rest) == 1 or rest[-1] == step:
                    found = self.find_attr(module, qual, step)
                    if found is not None:
                        return Def(*found)
                return Unresolved(f"{'.'.join(parts)}: no {step} in {module.path}:{qual}")
            return Def(module, qual)
        if first in module.imports:
            target, attr = module.imports[first]
            if attr is None:                      # import pkg[.sub] [as name]
                target_mod = self.module(target)
                if target_mod is None:
                    return Unresolved(f"external module {target}")
                return self.resolve_in_module(target_mod, rest, depth + 1)
            # from target import attr
            target_mod = self.module(target)
            if target_mod is not None:
                if attr in target_mod.defs or attr in target_mod.imports:
                    return self.resolve_in_module(target_mod, [attr] + rest, depth + 1)
                sub = self.module(target + "." + attr)
                if sub is not None:
                    return self.resolve_in_module(sub, rest, depth + 1)
                if target_mod.is_package and not rest:
                    return Unresolved(f"{target}.{attr}: not defined in {target_mod.path}")
                return Unresolved(f"{target}.{attr}: not found")
            sub = self.module(target + "." + attr)
            if sub is not None:
                return self.resolve_in_module(sub, rest, depth + 1)
            return Unresolved(f"external import {target}.{attr}")
        if first == "__doc__" and not rest:
            return Def(module, "")
        # a module-level binding that is neither a definition nor an import
        for stmt in module.tree.body:
            if isinstance(stmt, ast.For) and isinstance(stmt.target, ast.Name) and stmt.target.id == first:
                return Unresolved(f"loop variable {first}")
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                    isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == first:
                if depth >= MAX_DEPTH:
                    return Unresolved(f"module-level {first}: too deep")
                r = self.resolve_expr(stmt.value, module, (), depth + 1)
                for step in rest:
                    r = self.step(r, step, depth + 1)
                return r
        return Unresolved(f"unbound name {first} in {module.path}")

    def resolve_in_module(self, module: Module, parts: list[str], depth: int):
        if not parts:
            return Def(module, "")
        return self.resolve_dotted(module, parts, depth)

    def find_attr(self, module: Module, cls_qual: str, attr: str,
                  seen: set | None = None) -> tuple[Module, str] | None:
        """Where ``cls_qual.attr`` is defined: the class itself, else its in-tree bases."""
        seen = seen if seen is not None else set()
        k = self.key(module, cls_qual)
        if k in seen or module.tree is None:
            return None
        seen.add(k)
        if cls_qual + "." + attr in module.defs:
            return (module, cls_qual + "." + attr)
        node = module.classes.get(cls_qual)
        if node is None:
            return None
        for base in node.bases:
            r = self.resolve_expr(base, module, (), 0)
            if isinstance(r, Def) and r.qual and r.qual in r.module.classes:
                found = self.find_attr(r.module, r.qual, attr, seen)
                if found is not None:
                    return found
        return None

    def resolve_expr(self, expr: ast.expr, module: Module, chain: tuple[ast.AST, ...], depth: int):
        """An expression read at a point whose enclosing definitions are ``chain``."""
        if depth > MAX_DEPTH + 4:
            return Unresolved("resolution too deep")
        if isinstance(expr, ast.Name):
            return self.resolve_name(expr.id, module, chain, depth)
        if isinstance(expr, ast.Attribute):
            inner = self.resolve_expr(expr.value, module, chain, depth)
            return self.step(inner, expr.attr, depth)
        if isinstance(expr, ast.Call):
            name = _last_name(expr.func)
            return Unresolved(f"call result ({name or 'expression'}(...))")
        if isinstance(expr, ast.Subscript):
            return Unresolved("subscript")
        return Unresolved(type(expr).__name__.lower())

    def step(self, base, attr: str, depth: int):
        if isinstance(base, Def):
            if base.module.tree is None:
                return Unresolved(f"unparseable module {base.module.path}")
            if base.qual == "":
                if attr in base.module.defs or attr in base.module.imports:
                    return self.resolve_dotted(base.module, [attr], depth + 1)
                sub = self.module(base.module.name + "." + attr)
                if sub is not None:
                    return Def(sub, "")
                if attr == "__doc__":
                    return base
                return Unresolved(f"{base.module.path}: no {attr}")
            return self.resolve_dotted(base.module, base.qual.split(".") + [attr], depth + 1)
        if isinstance(base, Classes):
            return Classes(base.module, base.qual, base.mode, base.suffix + (attr,))
        if isinstance(base, Param):
            return Param(base.module, base.func, base.index, base.name, base.suffix + (attr,))
        return base

    def resolve_name(self, name: str, module: Module, chain: tuple[ast.AST, ...], depth: int):
        if module.tree is None:
            return Unresolved(f"unparseable module {module.path}")
        funcs = [(i, n) for i, n in enumerate(chain) if isinstance(n, FUNCS)]
        for i, func in reversed(funcs):
            params = _params(func)
            if name in params:
                positional = _positional(func)
                is_method = i > 0 and isinstance(chain[i - 1], ast.ClassDef) and not _is_static(func)
                if is_method and positional and name == positional[0]:
                    cls = chain[i - 1]
                    cls_qual = ".".join(n.name for n in chain[:i])
                    if func.name == "__init_subclass__":
                        return Classes(module, cls_qual, "subclasses")
                    if self.is_metaclass(module, cls_qual):
                        return Classes(module, cls_qual, "metaclass_instances")
                    return Classes(module, cls_qual, "self_and_subclasses")
                index = positional.index(name) if name in positional else None
                return Param(module, func, index, name)
            # a local assigned in this function
            assigned = None
            for stmt in ast.walk(func):
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and \
                        isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == name:
                    assigned = stmt.value
                    break
                if isinstance(stmt, (ast.For, ast.comprehension)) and \
                        isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                    return Unresolved(f"loop variable {name}")
                if isinstance(stmt, ast.With):
                    for item in stmt.items:
                        if isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == name:
                            return Unresolved(f"with-target {name}")
            if assigned is not None:
                if depth >= MAX_DEPTH:
                    return Unresolved(f"local {name}: too deep")
                return self.resolve_expr(assigned, module, chain, depth + 1)
        if name == "__doc__":
            return Def(module, "")
        return self.resolve_dotted(module, [name], depth)

    # -- class hierarchy
    def is_metaclass(self, module: Module, qual: str, seen: set | None = None) -> bool:
        k = self.key(module, qual)
        if k in self._is_meta:
            return self._is_meta[k]
        seen = seen if seen is not None else set()
        if k in seen:
            return False
        seen.add(k)
        node = module.classes.get(qual) if module.tree is not None else None
        out = False
        if node is not None:
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "type" and "type" not in module.defs \
                        and "type" not in module.imports:
                    out = True
                    break
                r = self.resolve_expr(base, module, (), 0)
                if isinstance(r, Def) and r.qual in r.module.classes:
                    if self.is_metaclass(r.module, r.qual, seen):
                        out = True
                        break
                elif isinstance(r, Unresolved) and (_last_name(base) in EXTERNAL_METACLASSES):
                    out = True
                    break
        self._is_meta[k] = out
        return out

    def subclasses(self, module: Module, qual: str) -> set[tuple[str, str]]:
        """Transitive in-tree subclasses of ``qual`` (keys ``(path, qual)``)."""
        root = self.key(module, qual)
        if root in self._subclasses:
            return self._subclasses[root]
        out: set[tuple[str, str]] = set()
        self._subclasses[root] = out              # cycle guard
        frontier = [(module, qual)]
        while frontier:
            m, q = frontier.pop()
            name = q.rsplit(".", 1)[-1]
            for cand in self.modules.values():
                if not cand.contains(name) or cand.tree is None:
                    continue
                for cq, node in cand.classes.items():
                    for base in node.bases:
                        if _last_name(base) != name:
                            continue
                        r = self.resolve_expr(base, cand, cand.chain_of(node), 0)
                        if isinstance(r, Def) and r.module is m and r.qual == q:
                            k = self.key(cand, cq)
                            if k not in out and k != root:
                                out.add(k)
                                frontier.append((cand, cq))
        return out

    def metaclass_users(self, module: Module, qual: str) -> set[tuple[str, str]]:
        """Every in-tree class whose metaclass is ``qual`` or a subclass of it."""
        metas = {self.key(module, qual)} | self.subclasses(module, qual)
        explicit: set[tuple[str, str]] = set()
        for mk in metas:
            mm = self.modules[mk[0]]
            name = mk[1].rsplit(".", 1)[-1]
            for cand in self.modules.values():
                if not cand.contains(name) or cand.tree is None:
                    continue
                for cq, node in cand.classes.items():
                    for kw in node.keywords:
                        if kw.arg != "metaclass" or _last_name(kw.value) != name:
                            continue
                        r = self.resolve_expr(kw.value, cand, cand.chain_of(node), 0)
                        if isinstance(r, Def) and self.key(r.module, r.qual) == mk:
                            explicit.add(self.key(cand, cq))
        out = set(explicit)
        for k in explicit:
            out |= self.subclasses(self.modules[k[0]], k[1])
        return out

    # -- from a resolution to docstrings to keep
    def materialize(self, res, depth: int, visited: set) -> tuple[list[tuple[str, str]], list[str]]:
        """-> (kept [(path, owner)], unresolved reasons)."""
        if isinstance(res, Unresolved):
            return [], [res.reason]
        if isinstance(res, Def):
            m, q = res.module, res.qual
            if q == "":
                return [(m.path, "<module>")], []
            if q in m.defs:
                return [(m.path, q)], []
            return [], [f"{m.path}: no definition {q}"]
        if isinstance(res, Classes):
            if res.mode == "self_and_subclasses":
                keys = {self.key(res.module, res.qual)} | self.subclasses(res.module, res.qual)
            elif res.mode == "subclasses":
                keys = self.subclasses(res.module, res.qual)
            else:
                keys = self.metaclass_users(res.module, res.qual)
            if len(res.suffix) > 1:
                return [], [f"{res.qual}: attribute chain {'.'.join(res.suffix)} on a class set"]
            kept: list[tuple[str, str]] = []
            for path, cq in sorted(keys):
                m = self.modules[path]
                if not res.suffix:
                    kept.append((path, cq))
                    continue
                found = self.find_attr(m, cq, res.suffix[0])
                if found is not None:
                    kept.append((found[0].path, found[1]))
            if not keys:
                return [], [f"{res.module.path}:{res.qual}: no in-tree classes for {res.mode}"]
            return kept, []
        if isinstance(res, Param):
            return self.materialize_param(res, depth, visited)
        return [], [f"unknown resolution {res!r}"]

    def materialize_param(self, p: Param, depth: int, visited: set):
        fkey = (p.module.path, p.module.qualname_of(p.func), p.name)
        if fkey in visited or depth >= MAX_DEPTH:
            return [], [f"parameter {p.name} of {fkey[1]}: " +
                        ("already followed" if fkey in visited else "too deep")]
        visited = visited | {fkey}
        chain = p.module.chain_of(p.func)
        is_method = bool(chain) and isinstance(chain[-1], ast.ClassDef) and not _is_static(p.func)
        cls_qual = ".".join(n.name for n in chain) if is_method else None
        kept: list[tuple[str, str]] = []
        reasons: list[str] = []
        n_calls = 0
        fname = p.func.name
        for cand in self.modules.values():
            if not cand.contains(fname) or cand.tree is None:
                continue
            applications = [(c.func, c.args, c.keywords, c) for c in cand.calls
                            if _last_name(c.func) == fname]
            applications += [(deco, [target], [], deco) for deco, target in cand.decorated
                             if _last_name(deco) == fname]
            for callee, args, keywords, site in applications:
                scope_chain = cand.chain_of(site)
                r = self.resolve_expr(callee, cand, scope_chain, 0)
                bound = False
                if isinstance(r, Def):
                    if not (r.module is p.module and r.qual == p.module.qualname_of(p.func)):
                        continue
                    bound = is_method and isinstance(callee, ast.Attribute)
                elif isinstance(r, Classes) and is_method and r.suffix == (fname,):
                    owner = self.key(r.module, r.qual)
                    mine = self.key(p.module, cls_qual)
                    if owner != mine and mine not in self.subclasses(r.module, r.qual) \
                            and owner not in self.subclasses(p.module, cls_qual):
                        continue
                    bound = True
                else:
                    continue
                n_calls += 1
                arg = None
                if p.index is not None:
                    idx = p.index - (1 if bound else 0)
                    if 0 <= idx < len(args) and not any(isinstance(a, ast.Starred) for a in args[:idx + 1]):
                        arg = args[idx]
                if arg is None:
                    for kw in keywords:
                        if kw.arg == p.name:
                            arg = kw.value
                if arg is None:
                    reasons.append(f"{cand.path}:{site.lineno}: call of {fname} without {p.name}")
                    continue
                if isinstance(arg, DEFS):            # `@F` applied to this definition
                    rr = Def(cand, cand.qualname_of(arg))
                else:
                    rr = self.resolve_expr(arg, cand, scope_chain, 0)
                for s in p.suffix:
                    rr = self.step(rr, s, 0)
                k, why = self.materialize(rr, depth + 1, visited)
                kept.extend(k)
                reasons.extend(f"{cand.path}:{site.lineno}: {w}" for w in why)
        if n_calls == 0:
            reasons.append(f"parameter {p.name} of {fkey[1]}: no in-tree call found")
        return kept, reasons

    # -- consumption sites
    def sites_in(self, module: Module):
        if module.tree is None:
            return
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Attribute) and node.attr == "__doc__":
                parent = module.parent(node)
                if isinstance(node.ctx, ast.Load) or isinstance(parent, ast.AugAssign):
                    yield node, node.value, "attribute"
            elif isinstance(node, ast.Name) and node.id == "__doc__" and isinstance(node.ctx, ast.Load):
                yield node, node, "name"
            elif isinstance(node, ast.Call) and _last_name(node.func) in self.getdoc_last:
                dotted = _dotted(node.func)
                if not dotted:
                    continue
                r = None
                if dotted[0] in module.imports:
                    target, attr = module.imports[dotted[0]]
                    full = ".".join(([target] if attr is None else [target, attr]) + dotted[1:])
                elif len(dotted) > 1:
                    full = ".".join(dotted)
                else:
                    full = None
                if full in self.getdoc and node.args:
                    yield node, node.args[0], "getdoc"

    def tolerant(self, node: ast.AST, module: Module) -> str | None:
        """Why a missing docstring cannot hurt at this site, or None."""
        parent = module.parent(node)
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and getattr(parent, "value", None) is node:
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            if targets and all((isinstance(t, ast.Attribute) and t.attr == "__doc__")
                               or (isinstance(t, ast.Name) and t.id == "__doc__") for t in targets):
                return "copied into __doc__"
        if isinstance(parent, ast.Compare) and all(isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq))
                                                   for op in parent.ops):
            if any(isinstance(c, ast.Constant) and c.value is None for c in parent.comparators):
                return "compared with None"
        if isinstance(parent, (ast.If, ast.IfExp, ast.While)) and parent.test is node:
            return "truth-tested"
        if isinstance(parent, ast.BoolOp):
            return "boolean operand"
        if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.Not):
            return "negated"
        if isinstance(parent, ast.Call) and _last_name(parent.func) in ("bool", "str", "repr", "print"):
            return f"argument of {_last_name(parent.func)}()"
        target = ast.dump(node)
        child = node
        anc = parent
        while anc is not None and not isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                        ast.ClassDef, ast.Module, ast.Lambda)):
            if isinstance(anc, (ast.If, ast.IfExp)):
                body = anc.body if isinstance(anc.body, list) else [anc.body]
                orelse = anc.orelse if isinstance(anc.orelse, list) else [anc.orelse]
                if child in body and self._guards(anc.test, target, positive=True):
                    return "guarded by if"
                if child in orelse and self._guards(anc.test, target, positive=False):
                    return "guarded by else"
            if isinstance(anc, ast.Try) and child in anc.body:
                for h in anc.handlers:
                    names = ({h.type.id} if isinstance(h.type, ast.Name) else
                             {e.id for e in h.type.elts if isinstance(e, ast.Name)}
                             if isinstance(h.type, ast.Tuple) else set()) if h.type else {"BaseException"}
                    if names & TOLERANT_EXCEPTIONS:
                        return "inside try/except " + ",".join(sorted(names & TOLERANT_EXCEPTIONS))
            child, anc = anc, module.parent(anc)
        return None

    def _guards(self, test: ast.expr, target: str, positive: bool) -> bool:
        """Does ``test`` being true (positive) / false (negative) imply the target is present?"""
        if isinstance(test, ast.BoolOp):
            if positive and isinstance(test.op, ast.And):
                return any(self._guards(v, target, True) for v in test.values)
            if not positive and isinstance(test.op, ast.Or):
                return any(self._guards(v, target, False) for v in test.values)
            return False
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return self._guards(test.operand, target, not positive)
        if positive:
            if ast.dump(test) == target:
                return True
            if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot) \
                    and ast.dump(test.left) == target and isinstance(test.comparators[0], ast.Constant) \
                    and test.comparators[0].value is None:
                return True
            if isinstance(test, ast.Call) and _last_name(test.func) == "hasattr":
                return False
        else:
            if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Is) \
                    and ast.dump(test.left) == target and isinstance(test.comparators[0], ast.Constant) \
                    and test.comparators[0].value is None:
                return True
        return False

    def run(self) -> Result:
        needles = ["__doc__"] + sorted(self.getdoc_last)
        for module in self.modules.values():
            if not any(module.contains(n) for n in needles):
                continue
            if module.tree is None:
                self.result.parse_failures.append(module.path)
                continue
            for node, target_expr, how in self.sites_in(module):
                site = {"path": module.path, "line": node.lineno, "how": how,
                        "expr": module.segment(node)}
                why = self.tolerant(node, module)
                if why:
                    site["tolerant"] = why
                    self.result.sites.append(site)
                    continue
                res = self.resolve_expr(target_expr, module, module.chain_of(node), 0)
                kept, reasons = self.materialize(res, 0, set())
                # only owners that actually carry a docstring are worth naming
                kept = sorted({(p, q) for p, q in kept if self.has_docstring(p, q)})
                site["kept"] = [f"{p}:{q}" for p, q in kept]
                if reasons:
                    site["unresolved"] = sorted(set(reasons))[:20]
                self.result.sites.append(site)
                for path, owner in kept:
                    self.result.keep.setdefault(path, {})[owner] = RULE
        self.result.sites.sort(key=lambda s: (s["path"], s["line"]))
        return self.result

    def has_docstring(self, path: str, owner: str) -> bool:
        m = self.modules[path]
        if m.tree is None:
            return False
        node = m.tree if owner == "<module>" else m.defs.get(owner)
        return bool(node is not None and node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str))


def analyze(blobs: dict[str, bytes], directives=None) -> Result:
    """Run the analysis over ``{repo_relative_path: source_bytes}`` (non-test ``.py`` only)."""
    conf = getattr(directives, "consumption", None) or {}
    if not conf.get("enabled", True):
        return Result()
    return Analyzer(blobs, tuple(conf.get("getdoc", DEFAULT_GETDOC))).run()


def summarize(result: Result) -> dict:
    sites = result.sites
    return {
        "sites": len(sites),
        "tolerant": sum(1 for s in sites if s.get("tolerant")),
        "resolved": sum(1 for s in sites if s.get("kept") and not s.get("unresolved")),
        "partly_resolved": sum(1 for s in sites if s.get("kept") and s.get("unresolved")),
        "unresolved": sum(1 for s in sites if not s.get("tolerant") and not s.get("kept")),
        "files_with_kept_docstrings": len(result.keep),
        "docstrings_kept": result.kept,
        "parse_failures": len(result.parse_failures),
    }
