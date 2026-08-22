//! The anchor grammar of `FORMAT.md` §1.
//!
//! ```text
//! anchor   := path [ "#" segments ]
//! path     := ( "<module>" | name ( "." name )* ) [ "~" n ]
//! segments := segment ( "/" segment )*
//! segment  := kind [ ":" discriminator ] [ "~" n ]
//! ```
//!
//! Parsing is strict about structure and lenient about whitespace. A
//! discriminator is copied out of source code, so `if:qty<0` and `if: qty < 0`
//! name the same branch; comparison happens on a whitespace-squeezed key.

use std::fmt;

pub const MODULE_PATH: &str = "<module>";

/// Every segment kind in the format. Ordering of the `KINDS` table matters:
/// prefix matching walks it longest-first so `raises` wins over `raise`.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug, PartialOrd, Ord)]
pub enum Kind {
    // §1.2 — parts of a symbol
    Param,
    Returns,
    Raises,
    Decorator,
    // §1.3 — statements
    Assign,
    Call,
    Raise,
    Assert,
    Del,
    Import,
    Global,
    Nonlocal,
    Return,
    Pass,
    Break,
    Continue,
    Yield,
    If,
    Elif,
    Else,
    For,
    While,
    Try,
    Except,
    Finally,
    With,
    Match,
    Case,
    AsyncFor,
    AsyncWith,
    /// Not in v0. A bare expression statement that is not a call — a lone
    /// comparison, a string that is not a docstring. Recorded so the walk never
    /// silently loses a place a comment could sit.
    Expr,
    // §1.4 — elements
    Key,
    Arg,
    Item,
}

use Kind::*;

const KINDS: &[(Kind, &str)] = &[
    (AsyncWith, "async with"),
    (AsyncFor, "async for"),
    (Decorator, "decorator"),
    (Continue, "continue"),
    (Nonlocal, "nonlocal"),
    (Finally, "finally"),
    (Returns, "returns"),
    (Import, "import"),
    (Global, "global"),
    (Assert, "assert"),
    (Except, "except"),
    (Raises, "raises"),
    (Assign, "assign"),
    (Return, "return"),
    (While, "while"),
    (Match, "match"),
    (Param, "param"),
    (Break, "break"),
    (Yield, "yield"),
    (Raise, "raise"),
    (Case, "case"),
    (Call, "call"),
    (Pass, "pass"),
    (Elif, "elif"),
    (Else, "else"),
    (Expr, "expr"),
    (Item, "item"),
    (With, "with"),
    (For, "for"),
    (Try, "try"),
    (Del, "del"),
    (Key, "key"),
    (Arg, "arg"),
    (If, "if"),
];

impl Kind {
    pub fn as_str(self) -> &'static str {
        KINDS
            .iter()
            .find_map(|&(kind, text)| (kind == self).then_some(text))
            .expect("every kind is in the table")
    }

    /// Kinds that never carry a discriminator: `else`/`finally`/`try` hang off
    /// their opener, and the valueless statements are unique by where they sit.
    pub fn is_bare(self) -> bool {
        matches!(
            self,
            Returns | Return | Pass | Break | Continue | Yield | Else | Finally | Try
        )
    }

    pub fn is_symbol_part(self) -> bool {
        matches!(self, Param | Returns | Raises | Decorator)
    }

    pub fn is_element(self) -> bool {
        matches!(self, Key | Arg | Item)
    }

    /// Match a kind at the start of `text`, requiring a delimiter after it so
    /// `if` does not match inside `if_ready`.
    fn matched_at(text: &str) -> Option<(Kind, usize)> {
        KINDS.iter().find_map(|&(kind, name)| {
            let rest = text.strip_prefix(name)?;
            let delimited = matches!(rest.chars().next(), None | Some(':') | Some('/') | Some('~'));
            delimited.then_some((kind, name.len()))
        })
    }
}

impl fmt::Display for Kind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SyntaxError(pub String);

impl fmt::Display for SyntaxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for SyntaxError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Segment {
    pub kind: Kind,
    pub disc: Option<String>,
    /// Occurrence suffix (§1.5), 1-based. Derived, never authored.
    pub tie: Option<u32>,
}

impl Segment {
    pub fn new(kind: Kind, disc: Option<impl Into<String>>) -> Result<Self, SyntaxError> {
        let disc = disc.map(Into::into);
        if let Some(text) = &disc {
            if kind.is_bare() {
                return Err(SyntaxError(format!("kind `{kind}` takes no discriminator")));
            }
            if text.trim().is_empty() {
                return Err(SyntaxError(format!("empty discriminator on `{kind}`")));
            }
        }
        Ok(Segment { kind, disc, tie: None })
    }

    pub fn bare(kind: Kind) -> Self {
        Segment { kind, disc: None, tie: None }
    }

    pub fn with_tie(&self, tie: Option<u32>) -> Self {
        Segment { tie, ..self.clone() }
    }

    /// Identity for sibling comparison, before ties are applied.
    pub fn sibling_key(&self) -> (Kind, Option<String>) {
        let kind = self.kind;
        (kind, self.disc.as_deref().map(|d| canon_for(kind, d)))
    }
}

impl fmt::Display for Segment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.kind)?;
        if let Some(disc) = &self.disc {
            write!(f, ":{disc}")?;
        }
        if let Some(tie) = self.tie {
            write!(f, "~{tie}")?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Anchor {
    pub path: String,
    /// Occurrence suffix on the *path* (§1.1), for a qualified name defined
    /// more than once — `@property` plus its setter, platform branches,
    /// `@overload`. Derived like any other tie.
    pub path_tie: Option<u32>,
    pub segments: Vec<Segment>,
}

impl Anchor {
    pub fn symbol(path: impl Into<String>) -> Self {
        Anchor { path: path.into(), path_tie: None, segments: Vec::new() }
    }

    pub fn with_path_tie(&self, tie: Option<u32>) -> Self {
        Anchor { path_tie: tie, ..self.clone() }
    }

    pub fn module() -> Self {
        Anchor::symbol(MODULE_PATH)
    }

    pub fn is_module(&self) -> bool {
        self.path == MODULE_PATH
    }

    pub fn child(&self, segment: Segment) -> Self {
        let mut segments = self.segments.clone();
        segments.push(segment);
        Anchor { path: self.path.clone(), path_tie: self.path_tie, segments }
    }

    /// The anchor one step up: the same path with the last segment dropped.
    /// A symbol path is already the root, so it is its own parent.
    pub fn parent(&self) -> Self {
        let mut up = self.clone();
        up.segments.pop();
        up
    }

    /// Whitespace-insensitive identity used for lookup.
    pub fn lookup_key(&self) -> String {
        self.key(true)
    }

    /// The lookup key with every occurrence suffix removed, on the path and on
    /// every segment. §1.5 makes ties derived rather than authored, so an
    /// author writes this form and the resolver matches it against whatever it
    /// numbered — at any depth, not only on the last segment.
    pub fn untied_key(&self) -> String {
        self.key(false)
    }

    fn key(&self, ties: bool) -> String {
        let mut key = self.path.clone();
        if ties {
            if let Some(tie) = self.path_tie {
                key.push_str(&format!("~{tie}"));
            }
        }
        for (i, segment) in self.segments.iter().enumerate() {
            key.push(if i == 0 { '#' } else { '/' });
            key.push_str(segment.kind.as_str());
            if let Some(disc) = &segment.disc {
                key.push(':');
                key.push_str(&canon_for(segment.kind, disc));
            }
            if ties {
                if let Some(tie) = segment.tie {
                    key.push_str(&format!("~{tie}"));
                }
            }
        }
        key
    }

    /// Whether any occurrence suffix is present, on the path or a segment.
    pub fn has_tie(&self) -> bool {
        self.path_tie.is_some() || self.segments.iter().any(|s| s.tie.is_some())
    }

    /// Discriminators the grammar cannot round-trip: a `/` collides with the
    /// segment separator, a trailing `~<digits>` with the tie suffix. Callers
    /// record these as v1 evidence rather than failing on them.
    pub fn hazards(&self) -> Vec<String> {
        let mut found = Vec::new();
        for segment in &self.segments {
            let Some(disc) = &segment.disc else { continue };
            if split_positions(disc).next().is_some() {
                found.push(format!(
                    "`{}`: discriminator contains a segment separator `/`",
                    segment.kind
                ));
            }
            if segment.tie.is_none() && trailing_tie(disc).is_some() {
                found.push(format!(
                    "`{}`: discriminator ends in a tie-like `~n`",
                    segment.kind
                ));
            }
        }
        found
    }
}

impl fmt::Display for Anchor {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.path)?;
        if let Some(tie) = self.path_tie {
            write!(f, "~{tie}")?;
        }
        for (i, segment) in self.segments.iter().enumerate() {
            f.write_str(if i == 0 { "#" } else { "/" })?;
            write!(f, "{segment}")?;
        }
        Ok(())
    }
}

/// Drop all whitespace. `qty < 0` and `qty<0` name the same branch.
pub fn squeeze(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join("")
}

/// A discriminator over this many characters is legal but defeats the point of
/// a cheap index (`FORMAT.md` §1.6). The stdlib has 2,457 of them.
pub const MAX_DISCRIMINATOR: usize = 80;

/// Canonical form of a discriminator (§1.6), applied to both sides of a lookup
/// so an author and the walk converge on one key.
///
/// Whitespace goes; parentheses that only wrapped a line continuation go; the
/// trailing comma of a one-element tuple target goes; anything past the length
/// budget is truncated, and whatever collides then ties under §1.5.
pub fn canon(text: &str) -> String {
    let mut out = squeeze(text);

    while let Some(inner) = strip_wrapping_parens(&out) {
        out = inner.to_string();
    }
    if let Some(head) = out.strip_suffix(',') {
        out = head.to_string();
    }

    match out.char_indices().nth(MAX_DISCRIMINATOR) {
        Some((at, _)) => out[..at].to_string(),
        None => out,
    }
}

/// Canonical form of a discriminator for a given kind (§1.6).
///
/// `with` is the one kind whose source text carries something the anchor does
/// not name: the `as` binding. §1.3 keys a `with` on its *context expression*,
/// so `with:open(p) as f` and `with:open(p)` are the same statement — and an
/// author reading the code writes the first. Dropping the binding on both sides
/// of the lookup makes them converge, at every depth, with no alias needed.
pub fn canon_for(kind: Kind, text: &str) -> String {
    match kind {
        With | AsyncWith => canon(&drop_as_bindings(text)),
        _ => canon(text),
    }
}

/// `open(a) as f, open(b) as g` → `open(a), open(b)`. Only an ` as ` outside
/// brackets binds the item; one inside is somebody's argument.
fn drop_as_bindings(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut out = String::with_capacity(text.len());
    let mut depth = 0i32;
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '(' | '[' | '{' => depth += 1,
            ')' | ']' | '}' => depth -= 1,
            _ => {}
        }
        if depth == 0 && chars[i].is_whitespace() {
            let rest: String = chars[i..].iter().collect();
            let trimmed = rest.trim_start();
            if let Some(after) = trimmed.strip_prefix("as ").or_else(|| trimmed.strip_prefix("as\t")) {
                // Skip the target: everything up to the next top-level comma.
                let mut skipped = 0;
                let mut inner = 0i32;
                for c in after.chars() {
                    match c {
                        '(' | '[' | '{' => inner += 1,
                        ')' | ']' | '}' => inner -= 1,
                        ',' if inner == 0 => break,
                        _ => {}
                    }
                    skipped += 1;
                }
                let consumed = rest.len() - after.len() + after[..skipped].len();
                i += rest[..consumed].chars().count();
                continue;
            }
        }
        out.push(chars[i]);
        i += 1;
    }
    out
}

/// `(a and b)` → `a and b`, but `(a) and (b)` is left alone: the leading paren
/// has to close at the very end for it to be a wrapper.
fn strip_wrapping_parens(text: &str) -> Option<&str> {
    let inner = text.strip_prefix('(')?.strip_suffix(')')?;
    if inner.is_empty() {
        return None;
    }
    let mut depth = 0i32;
    for c in inner.chars() {
        match c {
            '(' | '[' | '{' => depth += 1,
            ')' | ']' | '}' => depth -= 1,
            _ => {}
        }
        if depth < 0 {
            return None;
        }
    }
    (depth == 0).then_some(inner)
}

/// Byte offsets of the `/` characters that separate segments. A slash only
/// separates when a known kind opens right after it, so `if:n/2>1` stays one
/// segment while `if:n>1/pass` is two.
fn split_positions(text: &str) -> impl Iterator<Item = usize> + '_ {
    text.char_indices().filter_map(|(i, c)| {
        (c == '/' && Kind::matched_at(text[i + 1..].trim_start()).is_some()).then_some(i)
    })
}

/// Byte offset of a trailing `~<digits>`, with the parsed index.
fn trailing_tie(text: &str) -> Option<(usize, u32)> {
    let start = text.rfind('~')?;
    let digits = &text[start + 1..];
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    digits.parse().ok().map(|tie| (start, tie))
}

fn valid_name(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some(c) if c.is_alphabetic() || c == '_')
        && chars.all(|c| c.is_alphanumeric() || c == '_')
}

/// Parse anchor text. Errors here mean malformed syntax; an anchor that parses
/// but names nothing is the resolver's business, not the grammar's.
pub fn parse(text: &str) -> Result<Anchor, SyntaxError> {
    let raw = text.trim();
    if raw.is_empty() {
        return Err(SyntaxError("empty anchor".into()));
    }

    let (path, rest) = match raw.split_once('#') {
        Some((path, rest)) => (path.trim(), Some(rest)),
        None => (raw, None),
    };

    // A path may carry an occurrence suffix of its own (§1.1): `Cart.add~2`.
    let mut path_tie = None;
    let mut path = path;
    if let Some((at, index)) = trailing_tie(path) {
        if index == 0 {
            return Err(SyntaxError("tie index starts at 1".into()));
        }
        path_tie = Some(index);
        path = path[..at].trim_end();
    }

    if path != MODULE_PATH && (path.is_empty() || !path.split('.').all(valid_name)) {
        return Err(SyntaxError(format!("bad symbol path `{path}`")));
    }

    let Some(rest) = rest else {
        return Ok(Anchor::symbol(path).with_path_tie(path_tie));
    };
    if rest.trim().is_empty() {
        return Err(SyntaxError("trailing `#` with no segments".into()));
    }

    let mut segments = Vec::new();
    let mut start = 0;
    let cuts: Vec<usize> = split_positions(rest).collect();
    for cut in cuts.iter().copied().chain([rest.len()]) {
        segments.push(parse_segment(&rest[start..cut])?);
        start = cut + 1;
    }

    Ok(Anchor { path: path.to_string(), path_tie, segments })
}

fn parse_segment(raw: &str) -> Result<Segment, SyntaxError> {
    let part = raw.trim();
    if part.is_empty() {
        return Err(SyntaxError("empty segment".into()));
    }
    let Some((kind, width)) = Kind::matched_at(part) else {
        return Err(SyntaxError(format!(
            "segment `{part}` does not start with a known kind"
        )));
    };

    let mut remainder = &part[width..];
    let mut tie = None;
    if let Some((at, index)) = trailing_tie(remainder) {
        if index == 0 {
            return Err(SyntaxError("tie index starts at 1".into()));
        }
        tie = Some(index);
        remainder = &remainder[..at];
    }

    let mut segment = match remainder {
        "" => Segment::bare(kind),
        _ => {
            let Some(disc) = remainder.strip_prefix(':') else {
                return Err(SyntaxError(format!("expected `:` after kind in `{part}`")));
            };
            Segment::new(kind, Some(disc.trim()))?
        }
    };
    segment.tie = tie;
    Ok(segment)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn round_trip(text: &str) -> String {
        parse(text).expect("parses").to_string()
    }

    #[test]
    fn symbol_paths() {
        assert_eq!(parse("<module>").unwrap(), Anchor::module());
        assert_eq!(round_trip("Cart.add.helper"), "Cart.add.helper");
        assert!(parse("Cart..add").is_err());
        assert!(parse("2fast").is_err());
        assert!(parse("").is_err());
        assert!(parse("Cart#").is_err());
    }

    #[test]
    fn segments_from_the_spec() {
        for text in [
            "Cart.add#param:qty",
            "Cart.add#returns",
            "Cart.add#raises:ValueError",
            "Cart.add#decorator:retry",
            "Cart.add#for:item in items/if:qty<0/raise:ValueError",
            "Cart.add#except:ValueError/pass",
            "CONFIG#key:retries",
            "Cart.add#assign:client/arg:pool_size",
            "Robot.step#match:cmd/case:Move()",
            "Cart.add#async with:session.begin()",
        ] {
            assert_eq!(round_trip(text), text, "round trip of {text}");
        }
    }

    #[test]
    fn whitespace_is_not_significant() {
        let spaced = parse("Cart.add#if: qty < 0").unwrap();
        let tight = parse("Cart.add#if:qty<0").unwrap();
        assert_eq!(spaced.lookup_key(), tight.lookup_key());
        assert_ne!(spaced.to_string(), tight.to_string(), "display keeps the text as written");
    }

    #[test]
    fn longest_kind_wins() {
        assert_eq!(parse("f#raises:E").unwrap().segments[0].kind, Raises);
        assert_eq!(parse("f#raise:E").unwrap().segments[0].kind, Raise);
        assert_eq!(parse("f#returns").unwrap().segments[0].kind, Returns);
        assert_eq!(parse("f#return").unwrap().segments[0].kind, Return);
    }

    #[test]
    fn ties_parse_and_derive() {
        let anchor = parse("f#if:x~2").unwrap();
        assert_eq!(anchor.segments[0].tie, Some(2));
        assert_eq!(anchor.segments[0].disc.as_deref(), Some("x"));
        assert_eq!(anchor.untied_key(), "f#if:x");
        assert!(parse("f#if:x~0").is_err());
    }

    #[test]
    fn ties_strip_at_every_depth_not_just_the_last() {
        // The pilot's third-largest failure: the model writes the untied form
        // and the tie the walk derived sits on an *inner* segment.
        let anchor = parse("f#for:x in xs~2/while:True/assign:total").unwrap();
        assert_eq!(anchor.untied_key(), "f#for:xinxs/while:True/assign:total");
        assert!(anchor.has_tie());

        let plain = parse("f#for:x in xs/while:True/assign:total").unwrap();
        assert_eq!(plain.untied_key(), anchor.untied_key());
        assert!(!plain.has_tie());
    }

    #[test]
    fn a_path_can_be_tied() {
        let anchor = parse("SSLContext.minimum_version~2").unwrap();
        assert_eq!(anchor.path, "SSLContext.minimum_version");
        assert_eq!(anchor.path_tie, Some(2));
        assert_eq!(anchor.to_string(), "SSLContext.minimum_version~2");
        assert_eq!(anchor.untied_key(), "SSLContext.minimum_version");
        assert!(parse("Cart.add~0").is_err());
        // A tie on the path survives walking into it.
        let inner = parse("Popen._get_handles~1#return").unwrap();
        assert_eq!(inner.path_tie, Some(1));
        assert_eq!(inner.lookup_key(), "Popen._get_handles~1#return");
    }

    #[test]
    fn discriminators_are_canonicalised() {
        // Parentheses that only wrapped a continuation, and the trailing comma
        // of a one-element tuple target (§1.6).
        assert_eq!(
            parse("f#if:(a and\n b)").unwrap().lookup_key(),
            parse("f#if:a and b").unwrap().lookup_key()
        );
        assert_eq!(
            parse("f#assign:x,").unwrap().lookup_key(),
            parse("f#assign:x").unwrap().lookup_key()
        );
        // ...but a paren that closes early is not a wrapper.
        assert_eq!(parse("f#if:(a) and (b)").unwrap().lookup_key(), "f#if:(a)and(b)");
    }

    #[test]
    fn with_drops_its_as_binding() {
        // §1.3 keys a `with` on its context expression; a reader looking at the
        // code writes the `as` too, and both must name the same statement.
        assert_eq!(
            parse("f#with:contextlib.ExitStack() as stack").unwrap().lookup_key(),
            parse("f#with:contextlib.ExitStack()").unwrap().lookup_key()
        );
        // Several items, each with a binding.
        assert_eq!(
            parse("f#with:open(a) as fh, open(b) as gh").unwrap().lookup_key(),
            parse("f#with:open(a), open(b)").unwrap().lookup_key()
        );
        // Deeper segments keep resolving under the normalised prefix.
        assert_eq!(
            parse("f#with:open(p) as fh/assign:x").unwrap().lookup_key(),
            parse("f#with:open(p)/assign:x").unwrap().lookup_key()
        );
        // An `as` inside the call is an argument, not a binding.
        assert_eq!(
            parse("f#with:ctx(cast(x as int))").unwrap().lookup_key(),
            "f#with:ctx(cast(xasint))"
        );
        // `async with` too.
        assert_eq!(
            parse("f#async with:session() as s").unwrap().lookup_key(),
            parse("f#async with:session()").unwrap().lookup_key()
        );
    }

    #[test]
    fn long_discriminators_are_truncated_to_the_budget() {
        let long = "x".repeat(MAX_DISCRIMINATOR + 40);
        let key = parse(&format!("f#call:{long}")).unwrap().lookup_key();
        assert_eq!(key.len(), "f#call:".len() + MAX_DISCRIMINATOR);
        // Multi-byte text truncates on a character boundary, not a byte one.
        let wide = "é".repeat(MAX_DISCRIMINATOR + 10);
        assert_eq!(
            parse(&format!("f#call:{wide}")).unwrap().lookup_key().chars().count(),
            "f#call:".chars().count() + MAX_DISCRIMINATOR
        );
    }

    #[test]
    fn division_is_not_a_separator() {
        let anchor = parse("f#if:n/2>1").unwrap();
        assert_eq!(anchor.segments.len(), 1);
        assert_eq!(anchor.segments[0].disc.as_deref(), Some("n/2>1"));

        let split = parse("f#if:n>1/pass").unwrap();
        assert_eq!(split.segments.len(), 2);
        assert_eq!(split.segments[1].kind, Pass);
    }

    #[test]
    fn kind_needs_a_delimiter_after_it() {
        let anchor = parse("f#for:x in a/if_ready").unwrap();
        assert_eq!(anchor.segments.len(), 1, "`if_ready` is not the kind `if`");
    }

    #[test]
    fn bare_kinds_reject_discriminators() {
        assert!(parse("f#pass:x").is_err());
        assert!(parse("f#returns:int").is_err());
        assert!(parse("f#try:ValueError").is_err());
    }

    #[test]
    fn a_division_ending_in_a_kind_name_does_mis_split() {
        // The delimiter rule saves most real code: in `reduce(a/item)` the
        // slash is followed by `item)`, and the `)` disqualifies it.
        let safe = parse("f#call:reduce(a/item)").unwrap();
        assert_eq!(safe.segments.len(), 1);

        // It only breaks when the right operand *ends* the discriminator and
        // is spelled exactly like a kind.
        let broken = parse("f#assign:total/item").unwrap();
        assert_eq!(broken.segments.len(), 2, "read as assign:total then item");
    }

    #[test]
    fn hazards_are_reported_not_raised() {
        let built = Anchor::symbol("f").child(Segment::new(Assign, Some("total/item")).unwrap());
        assert_eq!(built.hazards().len(), 1, "flagged, not rejected");
        assert!(Anchor::symbol("f")
            .child(Segment::new(Assign, Some("total/items")).unwrap())
            .hazards()
            .is_empty());
    }

    #[test]
    fn unknown_kind_is_malformed() {
        assert!(parse("f#loop:x").is_err());
        assert!(parse("f#if").is_ok());
    }
}
