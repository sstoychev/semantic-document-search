"""Semantic chunking: groups document blocks into sections, splits oversized
sections, and adds overlap between consecutive chunks.

Public API
----------
    build_chunks(blocks, max_tokens, overlap_tokens, tokenizer,
                 model_max_tokens=None) -> list[Chunk]

`tokenizer` must be a HuggingFace ``PreTrainedTokenizerBase`` instance
(e.g. ``AutoTokenizer.from_pretrained(model_name)``).

Split hierarchy
---------------
Every block that exceeds the effective text budget is split using the most
appropriate strategy for its type, with progressively coarser fallbacks:

    PARAGRAPH / CAPTION
        1. spaCy sentence boundaries
        2. Punctuation splits  (. ; : ,)
        3. Newline splits
        4. Hard token-count split  ← always succeeds

    TABLE
        1. Markdown row splits  (lines containing |)
        2. Hard token-count split

    LIST / CODE
        1. Line splits  (each physical line)
        2. Punctuation splits  (for run-on lines)
        3. Hard token-count split

    HEADING / fallback
        1. Newline splits
        2. Hard token-count split

Model-limit enforcement
-----------------------
``build_chunks`` accepts an optional ``model_max_tokens`` parameter (auto-
detected from the tokenizer's ``model_max_length``, capped at 512).  The
effective per-chunk text budget is:

    safe_max = min(max_tokens,
                   model_max_tokens - overlap_tokens
                                    - _BREADCRUMB_RESERVE
                                    - _SEP_TOKENS)

After overlap is prepended a final clamp pass trims any ``embedding_input``
that still exceeds the model limit (removing overlap first, then trimming
the text head as a last resort).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.chunker.models import Block, BlockType

logger = logging.getLogger(__name__)

# Conservative token budget reserved for breadcrumbs (last 3 headings) +
# the two "\n\n" separators that appear in embedding_input.
_BREADCRUMB_RESERVE = 70
_SEP_TOKENS = 4

# Lazy-loaded spaCy pipeline (en_core_web_sm).
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def preload_nlp() -> None:
    """Eagerly load the spaCy pipeline during app startup."""
    _get_nlp()


# ---------------------------------------------------------------------------
# Public data structure
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    position: int           # 0-based position of this chunk within the document
    breadcrumbs: list[str]  # full heading path (includes section heading)
    text: str               # raw text stored in SQLite (includes overlap prefix)
    token_count: int        # token count of `text`
    embedding_input: str    # "\n".join(breadcrumbs[-3:]) + "\n\n" + text


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _count(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def _tail_text(tokenizer, text: str, max_tokens: int) -> str:
    """Return the last ``max_tokens`` tokens of *text* decoded to a string."""
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= max_tokens:
        return text
    return tokenizer.decode(ids[-max_tokens:], skip_special_tokens=True).strip()


def _head_text(tokenizer, text: str, max_tokens: int) -> str:
    """Return the first ``max_tokens`` tokens of *text* decoded to a string."""
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= max_tokens:
        return text
    return tokenizer.decode(ids[:max_tokens], skip_special_tokens=True).strip()


# ---------------------------------------------------------------------------
# Level 4 (ultimate fallback) — hard split by token count
# ---------------------------------------------------------------------------

def _hard_split_by_tokens(tokenizer, text: str, max_tokens: int) -> list[str]:
    """Encode the full text and yield fixed-size token windows."""
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= max_tokens:
        return [text]
    pieces = []
    for start in range(0, len(ids), max_tokens):
        piece = tokenizer.decode(
            ids[start : start + max_tokens], skip_special_tokens=True
        ).strip()
        if piece:
            pieces.append(piece)
    return pieces or [text]


# ---------------------------------------------------------------------------
# Level 3 — split by punctuation  (. ; : ,)
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"(?<=[.;:,])\s+")


def _split_by_punctuation(tokenizer, text: str, max_tokens: int) -> list[str]:
    """Split on sentence-final punctuation; fall back to hard split."""
    pieces = [p.strip() for p in _PUNCT_RE.split(text) if p.strip()]
    if len(pieces) <= 1:
        return _hard_split_by_tokens(tokenizer, text, max_tokens)

    chunks: list[str] = []
    current: list[str] = []
    current_tc = 0

    for piece in pieces:
        piece_tc = _count(tokenizer, piece)
        sep_tc = _count(tokenizer, " ") if current else 0

        if current_tc + sep_tc + piece_tc <= max_tokens:
            current.append(piece)
            current_tc += sep_tc + piece_tc
        else:
            if current:
                chunks.append(" ".join(current))
            if piece_tc > max_tokens:
                chunks.extend(_hard_split_by_tokens(tokenizer, piece, max_tokens))
                current, current_tc = [], 0
            else:
                current, current_tc = [piece], piece_tc

    if current:
        chunks.append(" ".join(current))
    return chunks or _hard_split_by_tokens(tokenizer, text, max_tokens)


# ---------------------------------------------------------------------------
# Level 2 — split by newlines  (universal accumulator)
# ---------------------------------------------------------------------------

def _split_by_newlines(tokenizer, text: str, max_tokens: int) -> list[str]:
    """Accumulate lines; fall back to punctuation split for oversized lines."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return _hard_split_by_tokens(tokenizer, text, max_tokens)

    chunks: list[str] = []
    current: list[str] = []
    current_tc = 0

    for line in lines:
        line_tc = _count(tokenizer, line)
        sep_tc = _count(tokenizer, "\n") if current else 0

        if current_tc + sep_tc + line_tc <= max_tokens:
            current.append(line)
            current_tc += sep_tc + line_tc
        else:
            if current:
                chunks.append("\n".join(current))
            if line_tc > max_tokens:
                chunks.extend(_split_by_punctuation(tokenizer, line, max_tokens))
                current, current_tc = [], 0
            else:
                current, current_tc = [line], line_tc

    if current:
        chunks.append("\n".join(current))
    return chunks or _hard_split_by_tokens(tokenizer, text, max_tokens)


# ---------------------------------------------------------------------------
# Table row splitting
# ---------------------------------------------------------------------------

_TABLE_SEP_RE = re.compile(r"^\|[-| :]+\|$")


def _split_table_by_rows(tokenizer, text: str, max_tokens: int) -> list[str]:
    """
    Split a markdown table by accumulating data rows.

    The header (all lines up to and including the ``|---|`` separator) is
    prepended to every chunk so each piece is independently readable.
    Falls back to newline split if the table has no recognisable structure.
    """
    lines = text.splitlines()

    # Identify header lines (everything up to and including the separator row).
    header_lines: list[str] = []
    data_lines: list[str] = []
    in_header = True

    for line in lines:
        if in_header:
            header_lines.append(line)
            if _TABLE_SEP_RE.match(line.strip()):
                in_header = False
        else:
            data_lines.append(line)

    if not data_lines:
        return _split_by_newlines(tokenizer, text, max_tokens)

    header_text = "\n".join(header_lines)
    header_tc = _count(tokenizer, header_text)

    if header_tc >= max_tokens:
        # Header alone is too large — treat the whole table as plain lines.
        return _split_by_newlines(tokenizer, text, max_tokens)

    chunks: list[str] = []
    current_rows: list[str] = []
    current_tc = header_tc

    for row in data_lines:
        row = row.rstrip()
        if not row:
            continue
        row_tc = _count(tokenizer, "\n" + row)

        if current_tc + row_tc <= max_tokens:
            current_rows.append(row)
            current_tc += row_tc
        else:
            if current_rows:
                chunks.append(header_text + "\n" + "\n".join(current_rows))
            current_rows = [row]
            current_tc = header_tc + _count(tokenizer, "\n" + row)

    if current_rows:
        chunks.append(header_text + "\n" + "\n".join(current_rows))

    return chunks or _split_by_newlines(tokenizer, text, max_tokens)


# ---------------------------------------------------------------------------
# Sentence splitting  (with punctuation + hard-split fallback)
# ---------------------------------------------------------------------------

def _split_by_sentences(tokenizer, text: str, max_tokens: int) -> list[str]:
    """
    Split a paragraph by spaCy sentence boundaries.

    Oversized individual sentences cascade to punctuation split → hard split.
    """
    nlp = _get_nlp()
    sentences = [s.text.strip() for s in nlp(text).sents if s.text.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tc = 0

    for sent in sentences:
        sent_tc = _count(tokenizer, sent)
        sep_tc = _count(tokenizer, " ") if current else 0

        if current_tc + sep_tc + sent_tc <= max_tokens:
            current.append(sent)
            current_tc += sep_tc + sent_tc
        else:
            if current:
                chunks.append(" ".join(current))
            if sent_tc > max_tokens:
                chunks.extend(_split_by_punctuation(tokenizer, sent, max_tokens))
                current, current_tc = [], 0
            else:
                current, current_tc = [sent], sent_tc

    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


# ---------------------------------------------------------------------------
# Block-type dispatcher
# ---------------------------------------------------------------------------

def _split_block(tokenizer, block: Block, max_tokens: int) -> list[str]:
    """
    Split a single block's text to fit within ``max_tokens`` using the
    strategy most appropriate for its type.
    """
    text = block.text.strip()
    if _count(tokenizer, text) <= max_tokens:
        return [text]

    if block.type == BlockType.TABLE:
        return _split_table_by_rows(tokenizer, text, max_tokens)

    if block.type in (BlockType.LIST, BlockType.CODE):
        return _split_by_newlines(tokenizer, text, max_tokens)

    if block.type in (BlockType.PARAGRAPH, BlockType.CAPTION):
        return _split_by_sentences(tokenizer, text, max_tokens)

    # HEADING or unknown — newlines then hard split.
    return _split_by_newlines(tokenizer, text, max_tokens)


# ---------------------------------------------------------------------------
# Section grouping
# ---------------------------------------------------------------------------

def _group_into_sections(blocks: list[Block]) -> list[list[Block]]:
    """Each HEADING starts a new section; preceding content forms a preamble."""
    sections: list[list[Block]] = []
    current: list[Block] = []

    for block in blocks:
        if block.type == BlockType.HEADING and current:
            sections.append(current)
            current = [block]
        else:
            current.append(block)

    if current:
        sections.append(current)

    return sections


# ---------------------------------------------------------------------------
# Per-section splitting
# ---------------------------------------------------------------------------

def _split_section(
    tokenizer,
    section: list[Block],
    max_tokens: int,
) -> list[tuple[list[str], str]]:
    """
    Returns a list of ``(breadcrumbs, text)`` pairs for a single section.

    ``breadcrumbs`` includes the section heading itself (full path).
    ``text`` is the content text only (heading excluded — it lives in
    breadcrumbs).
    """
    if not section:
        return []

    first = section[0]

    if first.type == BlockType.HEADING:
        section_crumbs: list[str] = first.breadcrumbs + [first.text]
        content_blocks = section[1:]
    else:
        section_crumbs = first.breadcrumbs
        content_blocks = section

    # Section has only a heading — emit the heading text as a stub chunk.
    if not content_blocks:
        if first.type == BlockType.HEADING:
            return [(section_crumbs, first.text)]
        return []

    sep_tc = _count(tokenizer, "\n\n")
    result: list[tuple[list[str], str]] = []
    current_parts: list[str] = []
    current_tc = 0

    def _flush() -> None:
        if current_parts:
            result.append((section_crumbs, "\n\n".join(current_parts)))
            current_parts.clear()

    for block in content_blocks:
        text = block.text.strip()
        if not text:
            continue

        block_tc = _count(tokenizer, text)
        join_tc = sep_tc if current_parts else 0

        if block_tc > max_tokens:
            # Block exceeds budget — split it with the type-appropriate strategy.
            _flush()
            current_tc = 0
            for piece in _split_block(tokenizer, block, max_tokens):
                result.append((section_crumbs, piece))
        elif current_tc + join_tc + block_tc <= max_tokens:
            current_parts.append(text)
            current_tc += join_tc + block_tc
        else:
            _flush()
            current_parts.append(text)
            current_tc = block_tc

    _flush()
    return result


# ---------------------------------------------------------------------------
# Overlap + model-limit clamp
# ---------------------------------------------------------------------------

def _apply_overlap(
    tokenizer,
    raw: list[tuple[list[str], str]],
    overlap_tokens: int,
    model_max_tokens: int,
) -> list[Chunk]:
    """
    Prepend the tail of the previous chunk as overlap, build Chunk objects,
    then clamp any ``embedding_input`` that still exceeds ``model_max_tokens``.

    Clamping priority:
        1. Drop the overlap prefix (keeps full chunk text).
        2. Trim the leading tokens of the text itself (last resort).
    """
    chunks: list[Chunk] = []

    for i, (crumbs, text) in enumerate(raw):
        if i > 0 and overlap_tokens > 0:
            overlap = _tail_text(tokenizer, raw[i - 1][1], overlap_tokens)
            full_text = (overlap + "\n\n" + text) if overlap else text
        else:
            full_text = text

        crumb_prefix = "\n".join(crumbs[-3:]) + "\n\n"
        embedding_input = crumb_prefix + full_text

        # --- enforce model limit -------------------------------------------
        if _count(tokenizer, embedding_input) > model_max_tokens:
            # Try without overlap first.
            embedding_input_no_ov = crumb_prefix + text
            if _count(tokenizer, embedding_input_no_ov) <= model_max_tokens:
                full_text = text
                embedding_input = embedding_input_no_ov
            else:
                # Even the text alone (+ crumbs) is too large: trim text head.
                crumb_tc = _count(tokenizer, crumb_prefix)
                budget = max(model_max_tokens - crumb_tc, 32)
                full_text = _head_text(tokenizer, text, budget)
                embedding_input = crumb_prefix + full_text

        chunks.append(Chunk(
            position=i,
            breadcrumbs=crumbs,
            text=full_text,
            token_count=_count(tokenizer, full_text),
            embedding_input=embedding_input,
        ))

    return chunks


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_chunks(
    blocks: list[Block],
    max_tokens: int,
    overlap_tokens: int,
    tokenizer,
    model_max_tokens: int | None = None,
) -> list[Chunk]:
    """
    Convert a flat list of Block objects into overlap-aware Chunk objects.

    Parameters
    ----------
    blocks:
        Output of ``app.chunker.get_blocks()``.
    max_tokens:
        Target maximum token count per chunk (for the raw text body, before
        overlap and breadcrumbs are added).
    overlap_tokens:
        Number of tokens from the tail of the previous chunk prepended to
        each chunk as context.
    tokenizer:
        A HuggingFace ``PreTrainedTokenizerBase`` used for token counting
        and overlap reconstruction.
    model_max_tokens:
        Hard token limit of the embedding model.  Auto-detected from
        ``tokenizer.model_max_length`` (capped at 512) when not supplied.
    """
    if model_max_tokens is None:
        raw_limit = getattr(tokenizer, "model_max_length", 512)
        # Some tokenizers report absurdly large values (e.g. 1 000 000).
        model_max_tokens = min(int(raw_limit), 512)

    # Leave room for breadcrumbs + separators + overlap so the final
    # embedding_input always fits within the model's context window.
    safe_max = min(
        max_tokens,
        model_max_tokens - overlap_tokens - _BREADCRUMB_RESERVE - _SEP_TOKENS,
    )
    safe_max = max(safe_max, 32)  # never go below 32 tokens per chunk

    sections = _group_into_sections(blocks)

    raw: list[tuple[list[str], str]] = []
    for section in sections:
        raw.extend(_split_section(tokenizer, section, safe_max))

    return _apply_overlap(tokenizer, raw, overlap_tokens, model_max_tokens)
