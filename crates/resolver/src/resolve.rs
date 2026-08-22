//! Anchor text plus source, in; the node it names, out.
//!
//! Every way an anchor can fail is a distinct outcome, because the point of
//! `EST-81` is the failure log. "Malformed", "names nothing", and "names two
//! things" are three different pieces of evidence about the grammar and must
//! not collapse into one `None`.

use ruff_python_ast::Mod;
use ruff_python_parser::{Mode, ParseError, ParseOptions, Parsed, parse};

use crate::anchor::{self, Anchor, Kind, SyntaxError};
use crate::enumerate::{AnchorIndex, Entry, Target};

const MAX_SUGGESTIONS: usize = 3;

#[derive(Debug)]
pub enum Resolution<'i> {
    /// Exactly one node.
    Found(&'i Entry),
    /// The anchor names a part the walk cannot confirm — most often a
    /// `raises:` whose exception is thrown by a callee rather than here.
    /// Resolves to the owning symbol.
    Unverified { entry: &'i Entry, why: &'static str },
    /// Two or more nodes. The anchor needs an occurrence suffix (§1.5).
    Ambiguous(Vec<&'i Entry>),
    /// Nothing. `resolved_prefix` is the longest leading part of the anchor
    /// that did exist, which is where it stopped matching the code.
    Missing {
        resolved_prefix: Option<Anchor>,
        suggestions: Vec<String>,
    },
    /// Not an anchor at all.
    Malformed(SyntaxError),
}

impl Resolution<'_> {
    pub fn entry(&self) -> Option<&Entry> {
        match self {
            Resolution::Found(entry) | Resolution::Unverified { entry, .. } => Some(entry),
            _ => None,
        }
    }

    pub fn is_found(&self) -> bool {
        matches!(self, Resolution::Found(_))
    }
}

pub fn parse_module(source: &str) -> Result<Parsed<Mod>, ParseError> {
    parse(source, ParseOptions::from(Mode::Module))
}

/// Parse and enumerate in one step.
pub fn index_source(source: &str) -> Result<AnchorIndex, ParseError> {
    let parsed = parse_module(source)?;
    Ok(crate::enumerate::index(parsed.syntax(), source))
}

pub fn resolve<'i>(index: &'i AnchorIndex, text: &str) -> Resolution<'i> {
    let anchor = match anchor::parse(text) {
        Ok(anchor) => anchor,
        Err(error) => return Resolution::Malformed(error),
    };
    resolve_anchor(index, &anchor)
}

/// A resolution plus the ambiguity a position hint had to settle, if any.
///
/// `disambiguated` is `Some(candidates)` exactly when the anchor was
/// `Ambiguous` and the hint chose one of them. The caller must keep that case
/// apart from a plain `Found`: it is the anchor *and the position* that named
/// the node, so it is not evidence that the anchor text alone was right.
#[derive(Debug)]
pub struct Hinted<'i> {
    pub resolution: Resolution<'i>,
    pub disambiguated: Option<Vec<&'i Entry>>,
}

/// Resolve `text`, and when it names several nodes, let `hint` — the source
/// line the doc record attaches to — pick one.
///
/// §1.5: ties are derived, never authored. Two textually identical siblings
/// therefore cannot be told apart by any anchor an author could write; the only
/// thing that distinguishes them is where in the file the record sat. Nothing
/// else about resolution changes: a hint on an unambiguous anchor is ignored,
/// and no hint means the ambiguity stands.
pub fn resolve_hinted<'i>(
    index: &'i AnchorIndex,
    text: &str,
    hint: Option<u32>,
) -> Hinted<'i> {
    match (resolve(index, text), hint) {
        (Resolution::Ambiguous(candidates), Some(line)) => match nearest(&candidates, line) {
            Some(pick) => Hinted {
                resolution: Resolution::Found(pick),
                disambiguated: Some(candidates),
            },
            None => Hinted {
                resolution: Resolution::Ambiguous(candidates),
                disambiguated: None,
            },
        },
        (resolution, _) => Hinted { resolution, disambiguated: None },
    }
}

/// The candidate nearest `line`. A candidate whose own range contains the hint
/// wins outright; otherwise the nearest endpoint wins, earliest line first on a
/// draw so the choice is deterministic.
pub fn nearest<'i>(candidates: &[&'i Entry], line: u32) -> Option<&'i Entry> {
    candidates.iter().copied().min_by_key(|entry| (distance(entry, line), entry.line))
}

fn distance(entry: &Entry, line: u32) -> u32 {
    if entry.line <= line && line <= entry.end_line {
        0
    } else {
        entry.line.abs_diff(line).min(entry.end_line.abs_diff(line))
    }
}

pub fn resolve_anchor<'i>(index: &'i AnchorIndex, anchor: &Anchor) -> Resolution<'i> {
    match index.lookup(&anchor.lookup_key()) {
        [] => {}
        [id] => return Resolution::Found(index.entry(*id)),
        ids => return Resolution::Ambiguous(ids.iter().map(|id| index.entry(*id)).collect()),
    }

    // Ties are derived, not authored (§1.5), so the form an author writes is
    // the untied one — at any depth. Matching on it recovers the anchor whose
    // `for:x in xs` the walk happened to number, and does so uniformly whether
    // the author omitted every suffix or only the inner ones.
    match index.lookup_untied(&anchor.untied_key()) {
        [] => {}
        [id] => return Resolution::Found(index.entry(*id)),
        ids => return Resolution::Ambiguous(ids.iter().map(|id| index.entry(*id)).collect()),
    }

    if let Some(entry) = unverified_part(index, anchor) {
        return Resolution::Unverified {
            entry,
            why: "exception is not raised directly in this symbol",
        };
    }

    Resolution::Missing {
        resolved_prefix: longest_prefix(index, anchor),
        suggestions: suggestions(index, &anchor.lookup_key()),
    }
}

/// A `raises:` on a symbol that exists but does not raise that exception here.
/// Sphinx docstrings document what a call chain can throw, so refusing these
/// would report a format failure where there is only an indirect raise.
fn unverified_part<'i>(index: &'i AnchorIndex, anchor: &Anchor) -> Option<&'i Entry> {
    let last = anchor.segments.last()?;
    if last.kind != Kind::Raises || anchor.segments.len() != 1 {
        return None;
    }
    let owner = Anchor::symbol(&anchor.path);
    let ids = index.lookup(&owner.lookup_key());
    let [id] = ids else { return None };
    let entry = index.entry(*id);
    (entry.target == Target::Definition).then_some(entry)
}

/// The longest leading part of the anchor that resolves, so a caller can say
/// *where* the anchor stopped matching rather than only that it did.
fn longest_prefix(index: &AnchorIndex, anchor: &Anchor) -> Option<Anchor> {
    for take in (0..anchor.segments.len()).rev() {
        let prefix = Anchor {
            path: anchor.path.clone(),
            path_tie: anchor.path_tie,
            segments: anchor.segments[..take].to_vec(),
        };
        if !index.lookup(&prefix.lookup_key()).is_empty() {
            return Some(prefix);
        }
    }
    None
}

fn suggestions(index: &AnchorIndex, key: &str) -> Vec<String> {
    let budget = (key.len() / 4).max(3);
    let mut scored: Vec<(usize, &str)> = index
        .keys()
        .filter_map(|candidate| {
            let distance = edit_distance(key, candidate, budget)?;
            Some((distance, candidate))
        })
        .collect();
    scored.sort_unstable();
    scored.into_iter().take(MAX_SUGGESTIONS).map(|(_, k)| k.to_string()).collect()
}

/// Levenshtein distance, abandoned once it exceeds `budget`.
fn edit_distance(a: &str, b: &str, budget: usize) -> Option<usize> {
    if a.len().abs_diff(b.len()) > budget {
        return None;
    }
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();

    let mut previous: Vec<usize> = (0..=b.len()).collect();
    let mut current = vec![0; b.len() + 1];

    for (i, ca) in a.iter().enumerate() {
        current[0] = i + 1;
        let mut row_best = current[0];
        for (j, cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            current[j + 1] = (previous[j] + cost)
                .min(previous[j + 1] + 1)
                .min(current[j] + 1);
            row_best = row_best.min(current[j + 1]);
        }
        if row_best > budget {
            return None;
        }
        std::mem::swap(&mut previous, &mut current);
    }

    let distance = previous[b.len()];
    (distance <= budget).then_some(distance)
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"
"""Shopping cart and checkout."""

MAX_TOKENS = 4096

CONFIG = {
    "retries": 3,
    "backoff": {"base": 2},
}


@dataclass
class Cart:
    """A shopping cart."""

    limit: int = 10

    def __init__(self, owner):
        self.total = 0
        self.owner = owner

    @property
    def kind(self):
        return "cart"

    @kind.setter
    def kind(self, value):
        self._kind = value

    def add(self, item, qty=1, *rest, **options):
        for item in items:
            if qty < 0:
                raise ValueError("negative")
            elif qty == 0:
                continue
            else:
                pass
        try:
            db.commit()
        except LookupError:
            pass
        except OSError:
            raise
        else:
            log.info("ok")
        finally:
            db.close()
        client = Client(pool_size=10, retries=CONFIG)
        with open(path) as handle:
            handle.read()
        self.total = compute(item, qty)
        for row in rows:
            log.debug(row)
        for row in rows:
            while True:
                seen = row
        return self.total


from .prefixes import (
    yotta,
    zetta,
)
import os.path

DOMAIN_INDEX_TYPE = Tuple[
    str,
    Type[Index],
]

SHORTCUT = {
    "return": "enter",
    "prior": "pageup",
}.get(key, key)
"#;

    fn index() -> AnchorIndex {
        index_source(SAMPLE).expect("sample parses")
    }

    fn found(index: &AnchorIndex, text: &str) -> u32 {
        match resolve(index, text) {
            Resolution::Found(entry) => entry.line,
            other => panic!("{text} did not resolve: {other:?}"),
        }
    }

    /// The line a piece of source text sits on, so tests assert against the
    /// code rather than against hand-counted numbers.
    fn line_of(needle: &str) -> u32 {
        let at = SAMPLE.find(needle).unwrap_or_else(|| panic!("{needle} not in sample"));
        SAMPLE[..at].matches('\n').count() as u32 + 1
    }

    #[test]
    fn symbols() {
        let index = index();
        assert_eq!(found(&index, "<module>"), 1);
        assert_eq!(found(&index, "MAX_TOKENS"), line_of("MAX_TOKENS = 4096"));
        assert_eq!(found(&index, "Cart"), line_of("class Cart:"));
        assert_eq!(found(&index, "Cart.add"), line_of("def add"));
        // `kind` is a property plus a setter, so the bare path names both (§1.1).
        assert_eq!(found(&index, "Cart.kind~1"), line_of("def kind"));
        assert_eq!(found(&index, "Cart.limit"), line_of("limit: int = 10"));
    }

    #[test]
    fn self_attributes_anchor_on_the_class() {
        let index = index();
        // §Open 2: the attribute anchor wins over the statement anchor.
        assert_eq!(found(&index, "Cart.owner"), line_of("self.owner = owner"));
        // ...and the statement form still resolves, to the same node.
        assert_eq!(
            found(&index, "Cart.__init__#assign:self.owner"),
            line_of("self.owner = owner")
        );
    }

    #[test]
    fn symbol_parts() {
        let index = index();
        assert_eq!(found(&index, "Cart.add#param:qty"), line_of("def add"));
        assert_eq!(found(&index, "Cart.add#param:rest"), line_of("def add"));
        assert_eq!(found(&index, "Cart.add#param:options"), line_of("def add"));
        assert_eq!(found(&index, "Cart.add#returns"), line_of("def add"));
        assert_eq!(found(&index, "Cart.add#raises:ValueError"), line_of("raise ValueError"));
        assert_eq!(found(&index, "Cart#decorator:dataclass"), line_of("@dataclass"));
    }

    #[test]
    fn statements_nest() {
        let index = index();
        assert_eq!(found(&index, "Cart.add#for:item in items"), line_of("for item in items"));
        assert_eq!(
            found(&index, "Cart.add#for:item in items/if:qty<0"),
            line_of("if qty < 0")
        );
        assert_eq!(
            found(&index, "Cart.add#for:item in items/if:qty<0/raise:ValueError"),
            line_of("raise ValueError")
        );
        assert_eq!(
            found(&index, "Cart.add#for:item in items/if:qty<0/elif:qty==0"),
            line_of("elif qty == 0")
        );
        assert_eq!(
            found(&index, "Cart.add#for:item in items/if:qty<0/else"),
            line_of("else:")
        );
    }

    #[test]
    fn try_clauses() {
        let index = index();
        assert_eq!(found(&index, "Cart.add#try"), line_of("try:"));
        assert_eq!(found(&index, "Cart.add#try/except:LookupError"), line_of("except LookupError"));
        assert_eq!(found(&index, "Cart.add#try/finally"), line_of("db.close()"));
        // FORMAT.md §1.3 writes this one without the `try`; both must work.
        assert_eq!(found(&index, "Cart.add#except:LookupError"), line_of("except LookupError"));
        assert_eq!(
            found(&index, "Cart.add#try/except:LookupError/pass"),
            line_of("except LookupError:\n            pass") + 1
        );
    }

    #[test]
    fn elements() {
        let index = index();
        assert_eq!(found(&index, "CONFIG#key:retries"), line_of("\"retries\""));
        assert_eq!(found(&index, "CONFIG#key:backoff/key:base"), line_of("\"backoff\""));
        assert_eq!(
            found(&index, "Cart.add#assign:client/arg:pool_size"),
            line_of("client = Client")
        );
    }

    #[test]
    fn whitespace_in_the_anchor_does_not_matter() {
        let index = index();
        assert_eq!(
            found(&index, "Cart.add#for: item in items / if: qty < 0"),
            line_of("if qty < 0")
        );
    }

    #[test]
    fn missing_reports_where_it_stopped() {
        let index = index();
        let Resolution::Missing { resolved_prefix, .. } =
            resolve(&index, "Cart.add#for:item in items/if:qty>99")
        else {
            panic!("expected a miss");
        };
        assert_eq!(
            resolved_prefix.map(|a| a.to_string()).as_deref(),
            Some("Cart.add#for:item in items")
        );
    }

    #[test]
    fn near_misses_get_suggestions() {
        let index = index();
        let Resolution::Missing { suggestions, .. } = resolve(&index, "Cart.add#param:qt") else {
            panic!("expected a miss");
        };
        assert!(
            suggestions.iter().any(|s| s == "Cart.add#param:qty"),
            "got {suggestions:?}"
        );
    }

    #[test]
    fn a_rebound_attribute_is_one_anchor() {
        let index = index();
        // §1.1 F1: `self.total` is written in two methods; the name is one
        // anchor and the first binding renders it.
        assert_eq!(found(&index, "Cart.total"), line_of("self.total = 0"));
        // The later write is still addressable, as the statement it is.
        assert_eq!(
            found(&index, "Cart.add#assign:self.total"),
            line_of("self.total = compute")
        );
    }

    #[test]
    fn a_redefined_name_ties_on_the_path() {
        let index = index();
        // §1.1 F2: a property and its setter say different things, so they get
        // one anchor each.
        assert_eq!(found(&index, "Cart.kind~1"), line_of("def kind(self):"));
        assert_eq!(found(&index, "Cart.kind~2"), line_of("def kind(self, value):"));
        // The untied form names both, which is the useful failure.
        assert!(matches!(resolve(&index, "Cart.kind"), Resolution::Ambiguous(e) if e.len() == 2));
        // Segments under a tied path resolve.
        assert_eq!(
            found(&index, "Cart.kind~2#assign:self._kind"),
            line_of("self._kind = value")
        );
    }

    #[test]
    fn an_inner_tie_does_not_have_to_be_written() {
        let index = index();
        // §1.5: the walk numbered the two identical `for` loops; an author
        // cannot see that and writes the untied form, at any depth.
        assert_eq!(
            found(&index, "Cart.add#for:row in rows~2/while:True/assign:seen"),
            line_of("seen = row")
        );
        assert_eq!(
            found(&index, "Cart.add#for:row in rows/while:True/assign:seen"),
            line_of("seen = row")
        );
    }

    #[test]
    fn imports_key_on_the_module_and_the_names_are_elements() {
        let index = index();
        // §1.3: the module is canonical...
        assert_eq!(found(&index, "<module>#import:.prefixes"), line_of("from .prefixes"));
        // ...each name is an element, on its own line...
        assert_eq!(found(&index, "<module>#import:.prefixes/item:yotta"), line_of("    yotta,"));
        // ...and the bare name is an alias for it, which is what the model writes.
        assert_eq!(found(&index, "<module>#import:zetta"), line_of("    zetta,"));
        // A plain dotted import already keys on its name.
        assert_eq!(found(&index, "<module>#import:os.path"), line_of("import os.path"));
    }

    #[test]
    fn elif_carries_its_condition() {
        let index = index();
        // The single largest failure in the pilot: v0's table said `elif` had
        // no discriminator, so nothing under one could be named.
        assert_eq!(
            found(&index, "Cart.add#for:item in items/if:qty<0/elif:qty==0"),
            line_of("elif qty == 0")
        );
        assert_eq!(
            found(&index, "Cart.add#for:item in items/if:qty<0/elif:qty==0/continue"),
            line_of("continue")
        );
    }

    #[test]
    fn wrappers_that_name_nothing_are_walked_through() {
        let index = index();
        // §1.4: a subscript introduces no naming level, so the elements of
        // `Tuple[...]` stay addressable.
        assert_eq!(found(&index, "DOMAIN_INDEX_TYPE#item:str"), line_of("    str,"));
        assert_eq!(
            found(&index, "DOMAIN_INDEX_TYPE#item:Type[Index]"),
            line_of("    Type[Index],")
        );
        // ...and a method call's receiver names its own elements, which an
        // argument walk alone would never reach.
        assert_eq!(found(&index, "SHORTCUT#key:prior"), line_of("\"prior\""));
        // The call's own arguments still resolve, alongside them.
        assert!(matches!(resolve(&index, "SHORTCUT#arg:key"), Resolution::Ambiguous(e) if e.len() == 2));
    }

    #[test]
    fn malformed_is_its_own_outcome() {
        let index = index();
        assert!(matches!(resolve(&index, "Cart.add#loop:x"), Resolution::Malformed(_)));
        assert!(matches!(resolve(&index, "Cart..add"), Resolution::Malformed(_)));
    }

    #[test]
    fn indirect_raises_resolves_as_unverified() {
        let index = index();
        match resolve(&index, "Cart.add#raises:KeyError") {
            Resolution::Unverified { entry, .. } => assert_eq!(entry.line, line_of("def add")),
            other => panic!("expected unverified, got {other:?}"),
        }
    }

    #[test]
    fn a_position_hint_settles_a_tie_the_anchor_cannot() {
        let index = index();
        let first = line_of("def kind(self):");
        let second = line_of("def kind(self, value):");
        // Without a hint the untied path names both, which is the useful failure.
        assert!(matches!(
            resolve_hinted(&index, "Cart.kind", None).resolution,
            Resolution::Ambiguous(e) if e.len() == 2
        ));
        for (hint, want) in [(first, first), (first + 1, first), (second, second)] {
            let hinted = resolve_hinted(&index, "Cart.kind", Some(hint));
            match hinted.resolution {
                Resolution::Found(entry) => assert_eq!(entry.line, want, "hint {hint}"),
                other => panic!("hint {hint} did not resolve: {other:?}"),
            }
            // The candidates it chose from come back, so a caller can never
            // mistake this for an anchor that was unambiguous on its own.
            assert_eq!(hinted.disambiguated.map(|c| c.len()), Some(2));
        }
    }

    #[test]
    fn a_hint_changes_nothing_that_was_not_ambiguous() {
        let index = index();
        // Unambiguous: the hint is ignored, however wrong it is.
        let hinted = resolve_hinted(&index, "Cart.add", Some(1));
        assert!(matches!(hinted.resolution, Resolution::Found(e) if e.line == line_of("def add")));
        assert!(hinted.disambiguated.is_none());
        // Missing stays missing; a hint is not a fallback for a bad anchor.
        let hinted = resolve_hinted(&index, "Basket.add", Some(line_of("def add")));
        assert!(matches!(hinted.resolution, Resolution::Missing { .. }));
        assert!(hinted.disambiguated.is_none());
    }

    #[test]
    fn nearest_prefers_the_candidate_whose_range_contains_the_hint() {
        let index = index();
        let Resolution::Ambiguous(candidates) = resolve(&index, "Cart.kind") else {
            panic!("expected an ambiguity");
        };
        // The getter's body, not its `def` line: containment beats raw distance
        // to the other candidate's first line.
        let inside = line_of("return \"cart\"");
        assert_eq!(nearest(&candidates, inside).map(|e| e.line), Some(line_of("def kind(self):")));
        assert_eq!(nearest(&[], 1).map(|e| e.line), None);
    }

    #[test]
    fn unknown_symbol_is_a_plain_miss() {
        let index = index();
        assert!(matches!(
            resolve(&index, "Basket.add"),
            Resolution::Missing { resolved_prefix: None, .. }
        ));
    }
}
