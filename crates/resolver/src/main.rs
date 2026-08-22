//! `sideword-resolver` — the deterministic half of the pipeline, as a binary.
//!
//! ```text
//! sideword-resolver index <file.py>...     every anchor the file admits
//! sideword-resolver resolve <file.py>      anchors on stdin, one per line
//!                                          (optionally `<anchor>\t<line hint>`)
//! sideword-resolver audit <file.py>...     grammar evidence, aggregated
//! ```
//!
//! JSON on stdout so the throwaway Python harness can drive it.

use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use serde_json::{Value, json};
use sideword_resolver::enumerate::{AnchorIndex, Note, Target};
use sideword_resolver::resolve::{Resolution, index_source, resolve_hinted};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some((command, rest)) = args.split_first() else {
        eprintln!("usage: sideword-resolver <index|resolve|audit> <file.py>...");
        return ExitCode::FAILURE;
    };

    let files: Vec<PathBuf> = rest.iter().map(PathBuf::from).collect();
    if files.is_empty() {
        eprintln!("no input files");
        return ExitCode::FAILURE;
    }

    let result = match command.as_str() {
        "index" => run_index(&files),
        "resolve" => run_resolve(&files),
        "audit" => run_audit(&files),
        other => {
            eprintln!("unknown command `{other}`");
            return ExitCode::FAILURE;
        }
    };

    match result {
        Ok(value) => {
            println!("{}", serde_json::to_string_pretty(&value).expect("json"));
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn load(path: &Path) -> Result<(String, AnchorIndex), String> {
    let source = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let index = index_source(&source).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok((source, index))
}

fn note_json(note: &Note) -> Value {
    match note {
        Note::BeyondSpec(what) => json!({"kind": "beyond-spec", "detail": what}),
        Note::LongDiscriminator(len) => json!({"kind": "long-discriminator", "detail": len}),
        Note::Hazard(what) => json!({"kind": "hazard", "detail": what}),
        Note::ApproximatePosition => json!({"kind": "approximate-position"}),
    }
}

fn target_name(target: Target) -> &'static str {
    match target {
        Target::Module => "module",
        Target::Definition => "definition",
        Target::Variable => "variable",
        Target::Attribute => "attribute",
        Target::Part => "part",
        Target::Statement => "statement",
        Target::Element => "element",
    }
}

fn run_index(files: &[PathBuf]) -> Result<Value, String> {
    let mut out = Vec::new();
    for path in files {
        let (_, index) = load(path)?;
        let anchors: Vec<Value> = index
            .entries()
            .iter()
            .map(|entry| {
                json!({
                    "anchor": entry.anchor.to_string(),
                    "target": target_name(entry.target),
                    "line": entry.line,
                    "end_line": entry.end_line,
                    "notes": entry.notes.iter().map(note_json).collect::<Vec<_>>(),
                })
            })
            .collect();
        out.push(json!({"file": path.display().to_string(), "anchors": anchors}));
    }
    Ok(Value::Array(out))
}

fn run_resolve(files: &[PathBuf]) -> Result<Value, String> {
    let [path] = files else {
        return Err("resolve takes exactly one file".into());
    };
    let (_, index) = load(path)?;

    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).map_err(|e| e.to_string())?;

    let outcomes: Vec<Value> = input
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(|line| {
            let (text, hint) = split_hint(line);
            let hinted = resolve_hinted(&index, text, hint);
            let candidates = |entries: &[&sideword_resolver::Entry]| {
                entries
                    .iter()
                    .map(|e| json!({"anchor": e.anchor.to_string(), "line": e.line}))
                    .collect::<Vec<_>>()
            };
            let outcome = match hinted.resolution {
                // A hint-settled tie reports `found` — it names one node — but
                // never silently: `disambiguated_by` says the anchor text alone
                // did not get there, so a caller can score it apart.
                Resolution::Found(entry) => match hinted.disambiguated {
                    Some(entries) => json!({
                        "status": "found",
                        "line": entry.line,
                        "disambiguated_by": "position",
                        "candidates": candidates(&entries),
                    }),
                    None => json!({"status": "found", "line": entry.line}),
                },
                Resolution::Unverified { entry, why } => {
                    json!({"status": "unverified", "line": entry.line, "why": why})
                }
                Resolution::Ambiguous(entries) => json!({
                    "status": "ambiguous",
                    "candidates": candidates(&entries),
                }),
                Resolution::Missing { resolved_prefix, suggestions } => json!({
                    "status": "missing",
                    "resolved_prefix": resolved_prefix.map(|a| a.to_string()),
                    "suggestions": suggestions,
                }),
                Resolution::Malformed(error) => {
                    json!({"status": "malformed", "error": error.to_string()})
                }
            };
            match hint {
                Some(hint) => json!({"anchor": text, "line_hint": hint, "outcome": outcome}),
                None => json!({"anchor": text, "outcome": outcome}),
            }
        })
        .collect();

    Ok(json!({"file": path.display().to_string(), "results": outcomes}))
}

/// An input line is `<anchor>` or `<anchor>\t<line hint>`. Anchors never
/// contain a tab (whitespace inside one is insignificant, §1.6), so the split is
/// unambiguous; anything that does not parse as a line number is left as part of
/// the anchor rather than quietly dropped.
fn split_hint(line: &str) -> (&str, Option<u32>) {
    match line.rsplit_once('\t') {
        Some((anchor, hint)) => match hint.trim().parse::<u32>() {
            Ok(hint) => (anchor.trim(), Some(hint)),
            Err(_) => (line, None),
        },
        None => (line, None),
    }
}

/// What the grammar does badly, aggregated over many files. This is the shape
/// of the EST-81 deliverable: not a percentage, a list of places the format
/// cannot name cleanly.
fn run_audit(files: &[PathBuf]) -> Result<Value, String> {
    let mut anchors = 0usize;
    let mut failed_parse = Vec::new();
    let mut ambiguous = Vec::new();
    let mut ambiguity_totals: std::collections::BTreeMap<&str, usize> = Default::default();
    let mut root_by_target: std::collections::BTreeMap<&str, usize> = Default::default();
    let mut noted: Vec<Value> = Vec::new();
    let mut by_note: std::collections::BTreeMap<String, usize> = Default::default();
    let mut by_target: std::collections::BTreeMap<&str, usize> = Default::default();
    let mut tied = 0usize;
    let mut widest: Option<(usize, String, String)> = None;

    for path in files {
        let (_, index) = match load(path) {
            Ok(loaded) => loaded,
            Err(error) => {
                failed_parse.push(json!({"file": path.display().to_string(), "error": error}));
                continue;
            }
        };
        anchors += index.len();

        for entry in index.entries() {
            *by_target.entry(target_name(entry.target)).or_default() += 1;
            if entry.anchor.segments.iter().any(|s| s.tie.is_some()) {
                tied += 1;
            }
            for segment in &entry.anchor.segments {
                let Some(disc) = &segment.disc else { continue };
                if widest.as_ref().is_none_or(|(len, ..)| disc.len() > *len) {
                    widest = Some((
                        disc.len(),
                        entry.anchor.to_string(),
                        path.display().to_string(),
                    ));
                }
            }
            for note in &entry.notes {
                let label = match note {
                    Note::BeyondSpec(what) => format!("beyond-spec: {what}"),
                    Note::LongDiscriminator(_) => "long-discriminator".to_string(),
                    Note::Hazard(what) => format!("hazard: {what}"),
                    Note::ApproximatePosition => "approximate-position".to_string(),
                };
                *by_note.entry(label).or_default() += 1;
            }
            if !entry.notes.is_empty() && noted.len() < 40 {
                noted.push(json!({
                    "file": path.display().to_string(),
                    "anchor": entry.anchor.to_string(),
                    "line": entry.line,
                    "notes": entry.notes.iter().map(note_json).collect::<Vec<_>>(),
                }));
            }
        }

        // A canonical anchor naming two nodes is a grammar failure, not a usage
        // error: nothing an author could write would tell them apart.
        //
        // Most are inherited — `f#param:x` collides only because `f` does. Only
        // the roots are independent evidence, so they are counted apart.
        for (id, entry) in index.entries().iter().enumerate() {
            let ids = index.lookup(&entry.anchor.lookup_key());
            if ids.len() < 2 || ids.first() != Some(&id) {
                continue;
            }
            let inherited = has_ambiguous_prefix(&index, &entry.anchor);
            *ambiguity_totals.entry(if inherited { "inherited" } else { "root" }).or_default() += 1;
            if inherited {
                continue;
            }
            *root_by_target.entry(target_name(entry.target)).or_default() += 1;
            ambiguous.push(json!({
                "file": path.display().to_string(),
                "anchor": entry.anchor.to_string(),
                "target": target_name(entry.target),
                "lines": ids.iter().map(|id| index.entry(*id).line).collect::<Vec<_>>(),
            }));
        }
    }

    Ok(json!({
        "files": files.len(),
        "parse_failures": failed_parse,
        "anchors": anchors,
        "by_target": by_target,
        "tied_anchors": tied,
        "ambiguity": {
            "totals": ambiguity_totals,
            "root_by_target": root_by_target,
            "roots": ambiguous,
        },
        "notes_by_kind": by_note,
        "note_examples": noted,
        "widest_discriminator": widest.map(|(len, anchor, file)| json!({
            "chars": len, "anchor": anchor, "file": file,
        })),
    }))
}

/// Whether some shorter prefix of this anchor is itself ambiguous, in which
/// case this collision is a consequence of that one rather than new evidence.
fn has_ambiguous_prefix(index: &AnchorIndex, anchor: &sideword_resolver::Anchor) -> bool {
    (0..anchor.segments.len()).any(|take| {
        let prefix = sideword_resolver::Anchor {
            path: anchor.path.clone(),
            path_tie: anchor.path_tie,
            segments: anchor.segments[..take].to_vec(),
        };
        index.lookup(&prefix.lookup_key()).len() > 1
    })
}
