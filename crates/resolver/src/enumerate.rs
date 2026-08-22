//! Walk a parsed module and emit every anchor the format can name.
//!
//! Resolution is a lookup, not an interpretation: the walk produces the whole
//! anchor space of a file once, and an anchor either appears in it or names
//! nothing. Three things fall out of that choice.
//!
//! * Occurrence suffixes (`FORMAT.md` §1.5) are **derived** here, never
//!   authored. An author cannot be relied on to notice a collision it has just
//!   created; a walk that sees both siblings always does.
//! * "Names nothing" and "names two things" are the same cheap check.
//! * Every place a comment *could* attach is enumerable, so a comment with no
//!   anchor is provably unanchorable rather than merely unnamed.
//!
//! Where the walk names a position that `FORMAT.md` v0 does not describe, the
//! entry carries a [`Note`]. Those notes are the v1 evidence.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, ExceptHandler, Mod, Stmt};
use ruff_source_file::LineIndex;
use ruff_text_size::{Ranged, TextRange};

use crate::anchor::{Anchor, Kind, Segment};

/// A discriminator longer than this is legal but unreadable in an index.
const LONG_DISCRIMINATOR: usize = 80;

/// How deep element segments (§1.4) may nest before the walk stops.
const MAX_ELEMENT_DEPTH: usize = 6;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Target {
    Module,
    /// A `def` or `class`.
    Definition,
    /// A name bound at module or class scope.
    Variable,
    /// `self.x = ...`, addressed on the class (§Open 2).
    Attribute,
    Part,
    Statement,
    Element,
}

impl Target {
    pub fn is_symbol(self) -> bool {
        matches!(self, Target::Definition | Target::Variable | Target::Attribute)
    }
}

/// Something true about an anchor that the v0 spec does not account for.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Note {
    /// The walk named a position `FORMAT.md` v0 does not describe.
    BeyondSpec(&'static str),
    /// Legal, but too long to read in an index.
    LongDiscriminator(usize),
    /// The grammar cannot round-trip this discriminator.
    Hazard(String),
    /// The anchor's position is approximate: the construct has no node of its
    /// own, so the range belongs to the first statement under it.
    ApproximatePosition,
}

#[derive(Debug, Clone)]
pub struct Entry {
    pub anchor: Anchor,
    pub target: Target,
    pub range: TextRange,
    /// 1-based line of the named construct.
    pub line: u32,
    pub end_line: u32,
    pub notes: Vec<Note>,
}

/// Every anchor in one file, with a lookup table over canonical text and
/// aliases. Built once per parse.
#[derive(Debug, Default)]
pub struct AnchorIndex {
    entries: Vec<Entry>,
    by_key: HashMap<String, Vec<usize>>,
    /// The same entries keyed with every occurrence suffix stripped. §1.5 says
    /// ties are derived rather than authored, so this is the form an author
    /// actually writes; an exact miss falls back to it.
    by_untied: HashMap<String, Vec<usize>>,
}

impl AnchorIndex {
    pub fn entries(&self) -> &[Entry] {
        &self.entries
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn entry(&self, id: usize) -> &Entry {
        &self.entries[id]
    }

    /// Entry ids registered under a lookup key, canonical or aliased.
    pub fn lookup(&self, key: &str) -> &[usize] {
        self.by_key.get(key).map_or(&[], Vec::as_slice)
    }

    /// Entry ids whose anchor matches `key` once every tie is stripped from
    /// both sides (§1.5).
    pub fn lookup_untied(&self, key: &str) -> &[usize] {
        self.by_untied.get(key).map_or(&[], Vec::as_slice)
    }

    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.by_key.keys().map(String::as_str)
    }

    /// Anchors carrying notes — the v1 evidence for one file.
    pub fn noted(&self) -> impl Iterator<Item = &Entry> {
        self.entries.iter().filter(|e| !e.notes.is_empty())
    }
}

pub fn index(module: &Mod, source: &str) -> AnchorIndex {
    let body: &[Stmt] = match module {
        Mod::Module(m) => &m.body,
        Mod::Expression(_) => &[],
    };

    let mut def_totals = HashMap::new();
    count_definitions(body, "", &mut def_totals);

    let mut walker = Walker {
        source,
        lines: LineIndex::from_source_text(source),
        index: AnchorIndex::default(),
        def_totals,
        def_seen: HashMap::new(),
        bound: HashSet::new(),
    };

    let whole = TextRange::new(0.into(), (source.len() as u32).into());
    walker.push(Anchor::module(), Target::Module, whole, Vec::new());

    let ctx = Ctx {
        symbol_prefix: String::new(),
        owner: Anchor::module(),
        self_class: None,
        class_scope: false,
        names_are_symbols: true,
    };
    walker.walk_body(body, &ctx, true);
    walker.index
}

#[derive(Clone)]
struct Ctx {
    /// Dotted symbol path of the enclosing scope; empty at module level.
    symbol_prefix: String,
    /// Anchor that statement segments hang under.
    owner: Anchor,
    /// Class whose `self` is in scope, for attribute anchors (§Open 2).
    self_class: Option<String>,
    class_scope: bool,
    /// Whether a plain `name = ...` here is a symbol rather than a statement.
    names_are_symbols: bool,
}

impl Ctx {
    fn symbol(&self, name: &str) -> String {
        if self.symbol_prefix.is_empty() {
            name.to_string()
        } else {
            format!("{}.{name}", self.symbol_prefix)
        }
    }

    /// Context for the body of a compound statement.
    fn under(&self, owner: Anchor) -> Ctx {
        Ctx { owner, ..self.clone() }
    }
}

struct Walker<'a> {
    source: &'a str,
    lines: LineIndex,
    index: AnchorIndex,
    /// How many times each qualified name is *defined* in this file. A name
    /// defined twice takes an occurrence suffix on the path (§1.1, F2), so the
    /// count has to be known before the first of them is pushed.
    def_totals: HashMap<String, u32>,
    /// Definitions pushed so far, numbering them in source order.
    def_seen: HashMap<String, u32>,
    /// Symbol paths already bound by an assignment. A path names a name, not a
    /// binding (§1.1, F1): the first write owns the anchor and every later one
    /// is reachable only as a statement.
    bound: HashSet<String>,
}

impl<'a> Walker<'a> {
    fn slice(&self, range: TextRange) -> &'a str {
        &self.source[usize::from(range.start())..usize::from(range.end())]
    }

    /// Source text reduced to a discriminator (§1.6). Code wraps and code
    /// carries comments; an anchor should do neither, so line continuations and
    /// any trailing `#` comment come out before whitespace is collapsed.
    fn text(&self, range: TextRange) -> String {
        let raw = strip_inline_comments(self.slice(range));
        raw.split_whitespace().collect::<Vec<_>>().join(" ")
    }

    /// The anchor for a `def` or `class`. A qualified name defined more than
    /// once in one file — a property and its setter, two platform branches,
    /// an `@overload` set — takes an occurrence suffix on the path (§1.1).
    fn definition_anchor(&mut self, path: &str) -> Anchor {
        let anchor = Anchor::symbol(path);
        if self.def_totals.get(path).copied().unwrap_or(0) < 2 {
            return anchor;
        }
        let seen = self.def_seen.entry(path.to_string()).or_default();
        *seen += 1;
        anchor.with_path_tie(Some(*seen))
    }

    fn line_of(&self, offset: ruff_text_size::TextSize) -> u32 {
        self.lines.line_index(offset).get() as u32
    }

    fn push(&mut self, anchor: Anchor, target: Target, range: TextRange, notes: Vec<Note>) -> usize {
        self.push_at(anchor, target, range, range.start(), notes)
    }

    /// A decorated symbol's range starts at its first decorator, but the line a
    /// reader means by "the class" is the `class` keyword — and a comment above
    /// the decorator is already addressable as `#decorator:`. So symbols carry
    /// an attachment point distinct from their extent.
    fn push_at(
        &mut self,
        anchor: Anchor,
        target: Target,
        range: TextRange,
        at: ruff_text_size::TextSize,
        mut notes: Vec<Note>,
    ) -> usize {
        for segment in &anchor.segments {
            if let Some(disc) = &segment.disc {
                if disc.len() > LONG_DISCRIMINATOR {
                    notes.push(Note::LongDiscriminator(disc.len()));
                }
            }
        }
        notes.extend(anchor.hazards().into_iter().map(Note::Hazard));

        let id = self.index.entries.len();
        let entry = Entry {
            line: self.line_of(at),
            end_line: self.line_of(range.end()),
            anchor: anchor.clone(),
            target,
            range,
            notes,
        };
        self.index.entries.push(entry);
        self.register(&anchor.lookup_key(), id);
        self.register_untied(&anchor.untied_key(), id);

        // v0's table said `elif` took no discriminator, so sidedocs written
        // against it spell the whole chain `if:x/elif`. That form is accepted
        // as an alias — like the short `except:E` — and a chain of more than
        // one `elif` makes it ambiguous, which is the honest answer.
        if anchor.segments.iter().any(|s| s.kind == Kind::Elif) {
            let mut bare = anchor.clone();
            for segment in &mut bare.segments {
                if segment.kind == Kind::Elif {
                    *segment = Segment::bare(Kind::Elif);
                }
            }
            self.register(&bare.lookup_key(), id);
            self.register_untied(&bare.untied_key(), id);
        }
        id
    }

    fn register(&mut self, key: &str, id: usize) {
        let slot = self.index.by_key.entry(key.to_string()).or_default();
        if !slot.contains(&id) {
            slot.push(id);
        }
    }

    fn register_untied(&mut self, key: &str, id: usize) {
        let slot = self.index.by_untied.entry(key.to_string()).or_default();
        if !slot.contains(&id) {
            slot.push(id);
        }
    }

    /// An extra name for an entry that already exists — the short `except:E`
    /// form, an imported name standing in for its module. Aliases join both
    /// tables, so the untied fallback reaches them too.
    fn alias(&mut self, anchor: &Anchor, id: usize) {
        self.register(&anchor.lookup_key(), id);
        self.register_untied(&anchor.untied_key(), id);
    }

    // ---- bodies -----------------------------------------------------------

    fn walk_body(&mut self, body: &[Stmt], ctx: &Ctx, skip_docstring: bool) {
        let mut segments: Vec<Option<Segment>> = body
            .iter()
            .enumerate()
            .map(|(i, stmt)| {
                let is_docstring = skip_docstring && i == 0 && is_string_literal(stmt);
                if is_docstring { None } else { self.segment_for(stmt) }
            })
            .collect();
        apply_ties(&mut segments);

        for (stmt, segment) in body.iter().zip(segments) {
            self.visit_stmt(stmt, segment, ctx);
        }
    }

    /// The statement's own segment, or `None` when it is addressed as a symbol
    /// (a definition) or is the enclosing symbol's docstring.
    fn segment_for(&self, stmt: &Stmt) -> Option<Segment> {
        let segment = match stmt {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => return None,
            Stmt::Return(_) => Segment::bare(Kind::Return),
            Stmt::Pass(_) => Segment::bare(Kind::Pass),
            Stmt::Break(_) => Segment::bare(Kind::Break),
            Stmt::Continue(_) => Segment::bare(Kind::Continue),
            Stmt::Try(_) => Segment::bare(Kind::Try),
            Stmt::Delete(d) => {
                let range = span(d.targets.iter().map(Ranged::range))?;
                self.segment(Kind::Del, range)
            }
            Stmt::Assign(a) => self.segment(Kind::Assign, a.targets.first()?.range()),
            Stmt::AugAssign(a) => self.segment(Kind::Assign, a.target.range()),
            Stmt::AnnAssign(a) => self.segment(Kind::Assign, a.target.range()),
            Stmt::TypeAlias(t) => self.segment(Kind::Assign, t.name.range()),
            Stmt::For(f) => {
                let kind = if f.is_async { Kind::AsyncFor } else { Kind::For };
                self.segment(kind, TextRange::new(f.target.start(), f.iter.end()))
            }
            Stmt::While(w) => self.segment(Kind::While, w.test.range()),
            Stmt::If(i) => self.segment(Kind::If, i.test.range()),
            Stmt::With(w) => {
                let kind = if w.is_async { Kind::AsyncWith } else { Kind::With };
                let range = span(w.items.iter().map(|i| i.context_expr.range()))?;
                self.segment(kind, range)
            }
            Stmt::Match(m) => self.segment(Kind::Match, m.subject.range()),
            Stmt::Raise(r) => match &r.exc {
                Some(exc) => self.segment(Kind::Raise, exception_name(exc)),
                None => Segment::bare(Kind::Raise),
            },
            Stmt::Assert(a) => self.segment(Kind::Assert, a.test.range()),
            Stmt::Import(i) => {
                Segment::new(Kind::Import, Some(i.names.first()?.name.as_str())).ok()?
            }
            Stmt::ImportFrom(f) => {
                let dots = ".".repeat(f.level as usize);
                let module = f.module.as_ref().map_or("", |m| m.as_str());
                Segment::new(Kind::Import, Some(format!("{dots}{module}"))).ok()?
            }
            Stmt::Global(g) => Segment::new(Kind::Global, Some(g.names.first()?.as_str())).ok()?,
            Stmt::Nonlocal(n) => {
                Segment::new(Kind::Nonlocal, Some(n.names.first()?.as_str())).ok()?
            }
            Stmt::Expr(e) => match e.value.as_ref() {
                Expr::Call(call) => self.segment(Kind::Call, call.func.range()),
                Expr::Await(await_) => match await_.value.as_ref() {
                    Expr::Call(call) => self.segment(Kind::Call, call.func.range()),
                    other => self.segment(Kind::Expr, other.range()),
                },
                Expr::Yield(_) | Expr::YieldFrom(_) => Segment::bare(Kind::Yield),
                other => self.segment(Kind::Expr, other.range()),
            },
            Stmt::IpyEscapeCommand(_) => return None,
        };
        Some(segment)
    }

    fn segment(&self, kind: Kind, range: TextRange) -> Segment {
        Segment::new(kind, Some(self.text(range))).expect("discriminator from source is non-empty")
    }

    // ---- statements -------------------------------------------------------

    fn visit_stmt(&mut self, stmt: &Stmt, segment: Option<Segment>, ctx: &Ctx) {
        match stmt {
            Stmt::FunctionDef(f) => {
                let path = ctx.symbol(f.name.as_str());
                let anchor = self.definition_anchor(&path);
                self.push_at(anchor.clone(), Target::Definition, f.range(), f.name.start(), Vec::new());
                self.function_parts(&anchor, f);

                let inner = Ctx {
                    symbol_prefix: path,
                    owner: anchor,
                    self_class: if ctx.class_scope {
                        Some(ctx.symbol_prefix.clone())
                    } else {
                        ctx.self_class.clone()
                    },
                    class_scope: false,
                    names_are_symbols: false,
                };
                self.walk_body(&f.body, &inner, true);
            }

            Stmt::ClassDef(c) => {
                let path = ctx.symbol(c.name.as_str());
                let anchor = self.definition_anchor(&path);
                self.push_at(anchor.clone(), Target::Definition, c.range(), c.name.start(), Vec::new());
                for decorator in &c.decorator_list {
                    let name = exception_name(&decorator.expression);
                    let part = anchor.child(self.segment(Kind::Decorator, name));
                    self.push(part, Target::Part, decorator.range(), Vec::new());
                }

                let inner = Ctx {
                    symbol_prefix: path,
                    owner: anchor,
                    self_class: ctx.self_class.clone(),
                    class_scope: true,
                    names_are_symbols: true,
                };
                self.walk_body(&c.body, &inner, true);
            }

            _ => {
                let Some(segment) = segment else { return };
                let statement = ctx.owner.child(segment);

                // A symbol path names a name, not a binding (§1.1): only the
                // first assignment claims it. A rebinding forty lines later is
                // the same doc, and is still reachable as a statement anchor.
                let symbol = self.symbol_for_assignment(stmt, ctx);
                let claims_symbol = match &symbol {
                    Some((anchor, ..)) => self.bound.insert(anchor.lookup_key()),
                    None => false,
                };

                let id = match (symbol, claims_symbol) {
                    (Some((symbol, target, range)), true) => {
                        let id = self.push(symbol, target, range, Vec::new());
                        self.alias(&statement, id);
                        id
                    }
                    _ => self.push(statement.clone(), Target::Statement, stmt.range(), Vec::new()),
                };

                let root = self.index.entries[id].anchor.clone();
                if let Some(value) = element_root(stmt) {
                    self.walk_elements(&root, value, 1);
                }
                self.import_names(stmt, &statement, id);
                self.walk_children(stmt, &statement, ctx);
            }
        }
    }

    /// The names an `import` binds (§1.3). The statement keys on the *module*,
    /// which is the stable half — but a comment sits next to a name, and a
    /// reader reaches for the name first. So every imported name becomes an
    /// element of the import, and also aliases it.
    ///
    /// ```python
    /// from .prefixes import (
    ///     yotta,        # <module>#import:.prefixes/item:yotta, or #import:yotta
    /// )
    /// ```
    fn import_names(&mut self, stmt: &Stmt, statement: &Anchor, id: usize) {
        let names: Vec<(String, TextRange)> = match stmt {
            Stmt::ImportFrom(f) => f
                .names
                .iter()
                .map(|a| (a.name.to_string(), a.range()))
                .collect(),
            // `import a.b` already keys on the dotted name; only the extra
            // names of `import a, b` need an alias, and they have no element
            // of their own to sit on.
            Stmt::Import(i) => i
                .names
                .iter()
                .skip(1)
                .map(|a| (a.name.to_string(), a.range()))
                .collect(),
            _ => return,
        };

        let from_import = matches!(stmt, Stmt::ImportFrom(_));
        for (name, range) in names {
            let short = match Segment::new(Kind::Import, Some(name.as_str())) {
                Ok(segment) => statement.parent().child(segment),
                Err(_) => continue,
            };
            // `from gettext import gettext` — the name alias *is* the module
            // key. Registering it would make the import ambiguous with itself.
            if short.lookup_key() == statement.lookup_key() {
                continue;
            }
            if from_import {
                let Ok(item) = Segment::new(Kind::Item, Some(name.as_str())) else { continue };
                let element = statement.child(item);
                let element_id = self.push(element, Target::Element, range, Vec::new());
                self.alias(&short, element_id);
            } else {
                self.alias(&short, id);
            }
        }
    }

    /// An assignment that is addressed as a symbol: a bare name at module or
    /// class scope, or `self.attr` inside a method.
    ///
    /// The attribute anchor wins over the statement anchor (§Open 2) — a reader
    /// looks up `Cart.total`, not the line in `__init__` that happens to set it.
    fn symbol_for_assignment(&self, stmt: &Stmt, ctx: &Ctx) -> Option<(Anchor, Target, TextRange)> {
        let (target, range) = match stmt {
            Stmt::Assign(a) if a.targets.len() == 1 => (&a.targets[0], a.range()),
            Stmt::AnnAssign(a) => (a.target.as_ref(), a.range()),
            _ => return None,
        };

        match target {
            Expr::Name(name) if ctx.names_are_symbols => {
                let path = ctx.symbol(name.id.as_str());
                self.claimable(&path)
                    .then(|| (Anchor::symbol(path), Target::Variable, range))
            }
            Expr::Attribute(attribute) => {
                let value = attribute.value.as_ref();
                let is_self = matches!(value, Expr::Name(n) if n.id.as_str() == "self");
                let class = ctx.self_class.as_ref()?;
                if !is_self || class.is_empty() {
                    return None;
                }
                let path = format!("{class}.{}", attribute.attr);
                self.claimable(&path)
                    .then(|| (Anchor::symbol(path), Target::Attribute, range))
            }
            _ => None,
        }
    }

    /// Whether an assignment may claim this symbol path. A `def` outranks an
    /// assignment for the same name however they are ordered — `def reduce`
    /// followed by `reduce = _warn(reduce)` is one name with one doc, and the
    /// definition is what a reader looks up. The assignment stays reachable as
    /// a statement, like any other rebinding (§1.1).
    fn claimable(&self, path: &str) -> bool {
        !self.def_totals.contains_key(path)
    }

    fn function_parts(&mut self, anchor: &Anchor, f: &ruff_python_ast::StmtFunctionDef) {
        for decorator in &f.decorator_list {
            let name = exception_name(&decorator.expression);
            let part = anchor.child(self.segment(Kind::Decorator, name));
            self.push(part, Target::Part, decorator.range(), Vec::new());
        }

        let p = &f.parameters;
        let plain = p.posonlyargs.iter().chain(&p.args).chain(&p.kwonlyargs);
        for parameter in plain {
            let name = &parameter.parameter.name;
            let part = anchor.child(self.segment(Kind::Param, name.range()));
            self.push(part, Target::Part, parameter.range(), Vec::new());
        }
        for variadic in [p.vararg.as_deref(), p.kwarg.as_deref()].into_iter().flatten() {
            let part = anchor.child(self.segment(Kind::Param, variadic.name.range()));
            self.push(part, Target::Part, variadic.range(), Vec::new());
        }

        let returns = anchor.child(Segment::bare(Kind::Returns));
        let range = f.returns.as_ref().map_or_else(|| f.name.range(), |r| r.range());
        self.push(returns, Target::Part, range, Vec::new());

        let mut seen = Vec::new();
        for (name, range) in raised_in(&f.body) {
            let text = self.text(name);
            if seen.contains(&text) {
                continue;
            }
            seen.push(text);
            let part = anchor.child(self.segment(Kind::Raises, name));
            self.push(part, Target::Part, range, Vec::new());
        }
    }

    /// Recurse into the bodies a compound statement owns.
    fn walk_children(&mut self, stmt: &Stmt, statement: &Anchor, ctx: &Ctx) {
        match stmt {
            Stmt::If(node) => {
                self.walk_body(&node.body, &ctx.under(statement.clone()), false);

                let mut clauses: Vec<Option<Segment>> = node
                    .elif_else_clauses
                    .iter()
                    .map(|clause| {
                        Some(match &clause.test {
                            Some(test) => self.segment(Kind::Elif, test.range()),
                            None => Segment::bare(Kind::Else),
                        })
                    })
                    .collect();
                apply_ties(&mut clauses);

                for (clause, segment) in node.elif_else_clauses.iter().zip(clauses) {
                    let anchor = statement.child(segment.expect("clause always has a segment"));
                    self.push(anchor.clone(), Target::Statement, clause.range(), Vec::new());
                    self.walk_body(&clause.body, &ctx.under(anchor), false);
                }
            }

            Stmt::For(node) => {
                self.walk_body(&node.body, &ctx.under(statement.clone()), false);
                self.walk_else(&node.orelse, statement, ctx);
            }

            Stmt::While(node) => {
                self.walk_body(&node.body, &ctx.under(statement.clone()), false);
                self.walk_else(&node.orelse, statement, ctx);
            }

            Stmt::With(node) => {
                self.walk_body(&node.body, &ctx.under(statement.clone()), false);
            }

            Stmt::Try(node) => {
                self.walk_body(&node.body, &ctx.under(statement.clone()), false);

                let mut handlers: Vec<Option<Segment>> = node
                    .handlers
                    .iter()
                    .map(|ExceptHandler::ExceptHandler(h)| {
                        Some(match &h.type_ {
                            Some(exc) => self.segment(Kind::Except, exception_name(exc)),
                            None => Segment::new(Kind::Except, Some("*")).expect("literal"),
                        })
                    })
                    .collect();
                apply_ties(&mut handlers);

                for (ExceptHandler::ExceptHandler(handler), segment) in
                    node.handlers.iter().zip(handlers)
                {
                    let anchor = statement.child(segment.expect("handler always has a segment"));
                    let id = self.push(anchor.clone(), Target::Statement, handler.range(), Vec::new());

                    // FORMAT.md §1.3 shows both `try/except:E` and a bare
                    // `except:E`. Canonical form keeps the `try`; the shorter
                    // form is accepted so the spec's own example resolves.
                    let mut short = ctx.owner.clone();
                    short.segments.extend(anchor.segments.iter().skip(ctx.owner.segments.len() + 1).cloned());
                    self.alias(&short, id);

                    self.walk_body(&handler.body, &ctx.under(anchor), false);
                }

                self.walk_else(&node.orelse, statement, ctx);
                self.walk_clause(&node.finalbody, statement, ctx, Kind::Finally);
            }

            Stmt::Match(node) => {
                let mut cases: Vec<Option<Segment>> = node
                    .cases
                    .iter()
                    .map(|case| Some(self.segment(Kind::Case, case.pattern.range())))
                    .collect();
                apply_ties(&mut cases);

                for (case, segment) in node.cases.iter().zip(cases) {
                    let anchor = statement.child(segment.expect("case always has a segment"));
                    self.push(anchor.clone(), Target::Statement, case.range(), Vec::new());
                    self.walk_body(&case.body, &ctx.under(anchor), false);
                }
            }

            _ => {}
        }
    }

    fn walk_else(&mut self, body: &[Stmt], statement: &Anchor, ctx: &Ctx) {
        self.walk_clause(body, statement, ctx, Kind::Else);
    }

    /// `else` and `finally` have no node of their own in the AST, so the clause
    /// anchor borrows the range of the first statement under it.
    fn walk_clause(&mut self, body: &[Stmt], statement: &Anchor, ctx: &Ctx, kind: Kind) {
        let Some(first) = body.first() else { return };
        let anchor = statement.child(Segment::bare(kind));
        let range = span(body.iter().map(Ranged::range)).unwrap_or_else(|| first.range());
        self.push(anchor.clone(), Target::Statement, range, vec![Note::ApproximatePosition]);
        self.walk_body(body, &ctx.under(anchor), false);
    }

    // ---- elements (§1.4) --------------------------------------------------

    fn walk_elements(&mut self, root: &Anchor, expr: &Expr, depth: usize) {
        if depth > MAX_ELEMENT_DEPTH {
            return;
        }
        let mut children: Vec<(Segment, TextRange, &Expr, Vec<Note>)> = Vec::new();
        self.collect_children(expr, &mut children);

        // Ties are derived across *every* child at this level, not per
        // container. `f(x).g(x)` contributes two `arg:x` siblings from two
        // different calls, and they are as much duplicates as two arguments of
        // one call would be.
        let mut segments: Vec<Option<Segment>> =
            children.iter().map(|(s, ..)| Some(s.clone())).collect();
        apply_ties(&mut segments);

        for ((_, range, value, notes), segment) in children.into_iter().zip(segments) {
            let anchor = root.child(segment.expect("element always has a segment"));
            self.push(anchor.clone(), Target::Element, range, notes);
            self.walk_elements(&anchor, value, depth + 1);
        }
    }

    /// Every element one level inside `expr` (§1.4).
    ///
    /// Containers contribute their own elements. Wrappers that introduce no
    /// naming level — a subscript, an attribute access, a `*splat` — are walked
    /// through into the same list, so `Tuple[str, Type[Index]]` names its
    /// elements and `{...}.get(k, k)` names the receiver's keys. Collecting
    /// into one list rather than recursing separately is what lets ties be
    /// derived across the whole level.
    fn collect_children<'e>(
        &self,
        expr: &'e Expr,
        out: &mut Vec<(Segment, TextRange, &'e Expr, Vec<Note>)>,
    ) {
        match expr {
            Expr::Dict(dict) => {
                for item in &dict.items {
                    let Some(key) = &item.key else {
                        continue; // `**spread` has no name to key on
                    };
                    let text = literal_key(self.slice(key.range()));
                    let Ok(segment) = Segment::new(Kind::Key, Some(text)) else { continue };
                    out.push((segment, key.range(), &item.value, Vec::new()));
                }
            }
            Expr::Call(call) => {
                // `{...}.get(k, k)` puts the literal in the receiver, not in an
                // argument, so the callee is walked before the arguments.
                self.collect_children(&call.func, out);
                for argument in &call.arguments.args {
                    let segment = self.segment(Kind::Arg, argument.range());
                    out.push((segment, argument.range(), argument, Vec::new()));
                }
                for keyword in &call.arguments.keywords {
                    let Some(name) = &keyword.arg else { continue };
                    let segment = self.segment(Kind::Arg, name.range());
                    out.push((segment, keyword.range(), &keyword.value, Vec::new()));
                }
            }
            Expr::List(list) => self.collect_items(&list.elts, out),
            Expr::Set(set) => self.collect_items(&set.elts, out),
            Expr::Tuple(tuple) => self.collect_items(&tuple.elts, out),
            Expr::Subscript(subscript) => {
                self.collect_children(&subscript.value, out);
                self.collect_children(&subscript.slice, out);
            }
            Expr::Attribute(attribute) => self.collect_children(&attribute.value, out),
            Expr::Starred(starred) => self.collect_children(&starred.value, out),
            _ => {}
        }
    }

    fn collect_items<'e>(
        &self,
        elements: &'e [Expr],
        out: &mut Vec<(Segment, TextRange, &'e Expr, Vec<Note>)>,
    ) {
        for element in elements {
            out.push((self.segment(Kind::Item, element.range()), element.range(), element, Vec::new()));
        }
    }
}

/// Assign occurrence suffixes to siblings identical in kind *and* discriminator
/// (§1.5). Everything else keeps a bare segment, so unrelated edits never
/// renumber anything.
fn apply_ties(segments: &mut [Option<Segment>]) {
    let mut totals: HashMap<(Kind, Option<String>), u32> = HashMap::new();
    for segment in segments.iter().flatten() {
        *totals.entry(segment.sibling_key()).or_default() += 1;
    }

    let mut seen: HashMap<(Kind, Option<String>), u32> = HashMap::new();
    for slot in segments.iter_mut() {
        let Some(segment) = slot else { continue };
        let key = segment.sibling_key();
        if totals[&key] < 2 {
            continue;
        }
        let index = seen.entry(key).or_default();
        *index += 1;
        *slot = Some(segment.with_tie(Some(*index)));
    }
}

/// The name a `raise` or decorator is about: the callee for `Error(...)`, the
/// expression itself otherwise.
fn exception_name(expr: &Expr) -> TextRange {
    match expr {
        Expr::Call(call) => call.func.range(),
        other => other.range(),
    }
}

/// Exception ranges raised directly in a body, not descending into nested
/// definitions — those raises belong to the nested symbol.
fn raised_in(body: &[Stmt]) -> Vec<(TextRange, TextRange)> {
    let mut found = Vec::new();
    for stmt in body {
        match stmt {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {}
            Stmt::Raise(raise) => {
                if let Some(exc) = &raise.exc {
                    found.push((exception_name(exc), raise.range()));
                }
            }
            other => {
                for child in child_bodies(other) {
                    found.extend(raised_in(child));
                }
            }
        }
    }
    found
}

fn child_bodies(stmt: &Stmt) -> Vec<&[Stmt]> {
    match stmt {
        Stmt::If(node) => {
            let mut bodies: Vec<&[Stmt]> = vec![&node.body];
            bodies.extend(node.elif_else_clauses.iter().map(|c| &*c.body));
            bodies
        }
        Stmt::For(node) => vec![&node.body, &node.orelse],
        Stmt::While(node) => vec![&node.body, &node.orelse],
        Stmt::With(node) => vec![&node.body],
        Stmt::Match(node) => node.cases.iter().map(|c| &*c.body).collect(),
        Stmt::Try(node) => {
            let mut bodies: Vec<&[Stmt]> = vec![&node.body, &node.orelse, &node.finalbody];
            bodies.extend(
                node.handlers
                    .iter()
                    .map(|ExceptHandler::ExceptHandler(h)| &*h.body),
            );
            bodies
        }
        _ => Vec::new(),
    }
}

/// The expression element segments walk into, for the statements where a
/// comment realistically lands on an element.
fn element_root(stmt: &Stmt) -> Option<&Expr> {
    match stmt {
        Stmt::Assign(a) => Some(&a.value),
        Stmt::AnnAssign(a) => a.value.as_deref(),
        Stmt::AugAssign(a) => Some(&a.value),
        Stmt::Return(r) => r.value.as_deref(),
        Stmt::Expr(e) => Some(&e.value),
        _ => None,
    }
}

/// `"retries"` keys on `retries`, per `FORMAT.md` §1.4. Other keys use their
/// source text.
fn literal_key(text: &str) -> String {
    let trimmed = text.trim();
    for quote in ['"', '\''] {
        if let Some(inner) = trimmed.strip_prefix(quote).and_then(|t| t.strip_suffix(quote)) {
            if !inner.contains(quote) {
                return inner.to_string();
            }
        }
    }
    trimmed.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn is_string_literal(stmt: &Stmt) -> bool {
    matches!(stmt, Stmt::Expr(e) if matches!(e.value.as_ref(), Expr::StringLiteral(_)))
}

fn span(ranges: impl Iterator<Item = TextRange>) -> Option<TextRange> {
    let mut ranges = ranges;
    let first = ranges.next()?;
    Some(ranges.fold(first, |acc, next| acc.cover(next)))
}

/// How many times each qualified name is defined, over the whole file. Run
/// before the walk, because a definition needs its occurrence suffix (§1.1) at
/// the moment it is pushed and cannot wait to discover a later twin.
///
/// Scoping mirrors the walk: a `def` or `class` extends the prefix, every other
/// compound statement keeps it, so the two branches of an `if _mswindows:` both
/// name the same path.
fn count_definitions(body: &[Stmt], prefix: &str, out: &mut HashMap<String, u32>) {
    for stmt in body {
        match stmt {
            Stmt::FunctionDef(f) => {
                let path = qualify(prefix, f.name.as_str());
                *out.entry(path.clone()).or_default() += 1;
                count_definitions(&f.body, &path, out);
            }
            Stmt::ClassDef(c) => {
                let path = qualify(prefix, c.name.as_str());
                *out.entry(path.clone()).or_default() += 1;
                count_definitions(&c.body, &path, out);
            }
            other => {
                for child in child_bodies(other) {
                    count_definitions(child, prefix, out);
                }
            }
        }
    }
}

fn qualify(prefix: &str, name: &str) -> String {
    if prefix.is_empty() {
        name.to_string()
    } else {
        format!("{prefix}.{name}")
    }
}

/// Remove `#` comments and `\` line continuations from a slice of source, so a
/// discriminator taken from a wrapped expression is the expression (§1.6).
/// String literals are tracked, so a `#` inside one survives.
fn strip_inline_comments(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut out = String::with_capacity(text.len());
    let mut quote: Option<(char, bool)> = None;
    let mut i = 0;

    while i < chars.len() {
        let c = chars[i];
        match quote {
            Some((delimiter, triple)) => {
                out.push(c);
                if c == '\\' && i + 1 < chars.len() {
                    out.push(chars[i + 1]);
                    i += 2;
                    continue;
                }
                if c == delimiter {
                    let closes = !triple
                        || (chars.get(i + 1) == Some(&delimiter)
                            && chars.get(i + 2) == Some(&delimiter));
                    if closes {
                        if triple {
                            out.push(delimiter);
                            out.push(delimiter);
                            i += 2;
                        }
                        quote = None;
                    }
                }
                i += 1;
            }
            None => match c {
                '#' => {
                    while i < chars.len() && chars[i] != '\n' {
                        i += 1;
                    }
                }
                '\\' if chars.get(i + 1) == Some(&'\n') => {
                    out.push(' ');
                    i += 2;
                }
                '"' | '\'' => {
                    let triple =
                        chars.get(i + 1) == Some(&c) && chars.get(i + 2) == Some(&c);
                    quote = Some((c, triple));
                    out.push(c);
                    if triple {
                        out.push(c);
                        out.push(c);
                        i += 3;
                    } else {
                        i += 1;
                    }
                }
                _ => {
                    out.push(c);
                    i += 1;
                }
            },
        }
    }
    out
}
