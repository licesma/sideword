//! Sideword resolver — anchor text to a position in Python source.
//!
//! Documentation lives outside the `.py`, keyed by anchors (`FORMAT.md` §1).
//! Putting it back, and checking that it still fits, both reduce to one
//! question: which node does this anchor name?

pub mod anchor;
pub mod enumerate;
pub mod resolve;

pub use anchor::{Anchor, Kind, Segment, SyntaxError};
pub use enumerate::{AnchorIndex, Entry, Note, Target};
pub use resolve::{Resolution, index_source, resolve};
