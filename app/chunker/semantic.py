"""Semantic chunking: groups document blocks into sections, splits oversized
sections, and adds overlap between consecutive chunks.

Public API
----------
    build_chunks(blocks, max_tokens, overlap_tokens, tokenizer) -> list[Chunk]

`tokenizer` must be a HuggingFace ``PreTrainedTokenizerBase`` instance
(e.g. ``AutoTokenizer.from_pretrained(model_name)``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.chunker.models import Block, BlockType

logger = logging.getLogger(__name__)

# Block types that may be split by sentence when they exceed max_tokens.
_SPLITTABLE = {BlockType.PARAGRAPH, BlockType.CAPTION}

# Block types that must never be split (warn instead).
_UNSPLITTABLE = {BlockType.TABLE, BlockType.LIST, BlockType.CODE}

# Lazy-loaded spaCy pipeline (en_core_web_sm).
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


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
    """Return the last `max_tokens` tokens of `text` decoded back to a string."""
    ids = tokenizer.encode(text, add_special_tokens=False)
    if len(ids) <= max_tokens:
        return text
    return tokenizer.decode(ids[-max_tokens:], skip_special_tokens=True).strip()


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

def _split_by_sentences(tokenizer, text: str, max_tokens: int) -> list[str]:
    """Split a paragraph into chunks of at most max_tokens by sentence boundaries."""
    nlp = _get_nlp()
    sentences = [s.text.strip() for s in nlp(text).sents if s.text.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tc = 0

    for sent in sentences:
        sent_tc = _count(tokenizer, sent)
        # Cost of joining: a single space between sentences.
        sep_tc = _count(tokenizer, " ") if current else 0

        if current_tc + sep_tc + sent_tc <= max_tokens:
            current.append(sent)
            current_tc += sep_tc + sent_tc
        else:
            if current:
                chunks.append(" ".join(current))
            if sent_tc > max_tokens:
                logger.warning(
                    "Single sentence exceeds max_tokens (%d > %d); keeping as-is.",
                    sent_tc, max_tokens,
                )
                chunks.append(sent)
                current, current_tc = [], 0
            else:
                current, current_tc = [sent], sent_tc

    if current:
        chunks.append(" ".join(current))

    return chunks or [text]  # fallback: keep original


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
    Returns a list of (breadcrumbs, text) pairs for a single section.

    `breadcrumbs` includes the section heading itself (full path).
    `text` is the content text only (heading excluded — it lives in breadcrumbs).
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
            # Block is larger than the entire chunk budget.
            if block.type in _SPLITTABLE:
                _flush()
                current_tc = 0
                for sentence_chunk in _split_by_sentences(tokenizer, text, max_tokens):
                    result.append((section_crumbs, sentence_chunk))
            else:
                # TABLE / LIST / CODE — warn and keep as single oversized chunk.
                logger.warning(
                    "%s block exceeds max_tokens (%d > %d); keeping as-is.",
                    block.type.value, block_tc, max_tokens,
                )
                _flush()
                current_tc = 0
                result.append((section_crumbs, text))

        elif current_tc + join_tc + block_tc <= max_tokens:
            # Fits in the current accumulator.
            current_parts.append(text)
            current_tc += join_tc + block_tc

        else:
            # Doesn't fit here — flush and start fresh.
            _flush()
            current_parts.append(text)
            current_tc = block_tc

    _flush()
    return result


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------

def _apply_overlap(
    tokenizer,
    raw: list[tuple[list[str], str]],
    overlap_tokens: int,
) -> list[Chunk]:
    """Prepend the tail of the previous chunk as overlap, then build Chunk objects."""
    chunks: list[Chunk] = []

    for i, (crumbs, text) in enumerate(raw):
        if i > 0 and overlap_tokens > 0:
            prev_text = raw[i - 1][1]
            overlap = _tail_text(tokenizer, prev_text, overlap_tokens)
            full_text = (overlap + "\n\n" + text) if overlap else text
        else:
            full_text = text

        tc = _count(tokenizer, full_text)
        embedding_input = "\n".join(crumbs[-3:]) + "\n\n" + full_text

        chunks.append(Chunk(
            position=i,
            breadcrumbs=crumbs,
            text=full_text,
            token_count=tc,
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
) -> list[Chunk]:
    """
    Convert a flat list of Block objects into overlap-aware Chunk objects.

    Parameters
    ----------
    blocks:
        Output of ``app.chunker.get_blocks()``.
    max_tokens:
        Target maximum token count per chunk (excluding overlap).
    overlap_tokens:
        Number of tokens from the tail of the previous chunk prepended to
        each chunk as context.
    tokenizer:
        A HuggingFace ``PreTrainedTokenizerBase`` used for token counting
        and overlap reconstruction.
    """
    sections = _group_into_sections(blocks)

    raw: list[tuple[list[str], str]] = []
    for section in sections:
        raw.extend(_split_section(tokenizer, section, max_tokens))

    return _apply_overlap(tokenizer, raw, overlap_tokens)
