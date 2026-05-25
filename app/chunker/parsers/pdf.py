"""PDF parser — uses PyMuPDF (fitz).

Extraction strategy:
  1. First pass across the whole document to identify the *body font size*
     (the most frequently occurring rounded font size).
  2. Page by page:
     a. Detect tables with page.find_tables() (requires PyMuPDF ≥ 1.23).
        Each table is captured as a TABLE block; its bounding box is recorded
        so that overlapping text blocks are skipped in the next step.
     b. Iterate text blocks from page.get_text("dict").  A text block is
        classified as a HEADING when its dominant font size exceeds the body
        size by more than 1 pt, or the text is bold, AND the content is short
        (< 200 chars).  Everything else becomes a PARAGRAPH.
  3. Within each page, all collected elements are sorted top-to-bottom by
     their y-coordinate so that the final position reflects reading order.

Metadata attached to every block: {"page": <1-based int>, "font_size": <float>}
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

from app.chunker.models import Block, BlockType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _body_font_size(doc: fitz.Document) -> float:
    sizes: list[float] = []
    for page in doc:
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0.0)
                    if s > 0:
                        sizes.append(round(s, 1))
    return Counter(sizes).most_common(1)[0][0] if sizes else 12.0


def _infer_heading_level(size: float, body_size: float) -> int:
    diff = size - body_size
    if diff >= 8:  return 1
    if diff >= 5:  return 2
    if diff >= 3:  return 3
    if diff >= 1.5: return 4
    return 5


def _update_headings(heading_levels: dict[int, str], level: int, text: str) -> list[str]:
    heading_levels[level] = text
    for lvl in [lv for lv in heading_levels if lv > level]:
        del heading_levels[lvl]
    return [heading_levels[lv] for lv in sorted(heading_levels)]


def _block_text(blk: dict) -> str:
    return "\n".join(
        " ".join(span.get("text", "") for span in line.get("spans", []))
        for line in blk.get("lines", [])
    ).strip()


def _dominant_span(blk: dict) -> dict:
    """Return the span with the largest font size in the block."""
    best: dict = {}
    best_size = 0.0
    for line in blk.get("lines", []):
        for span in line.get("spans", []):
            if span.get("size", 0.0) > best_size:
                best_size = span["size"]
                best = span
    return best


# ── Public entry point ────────────────────────────────────────────────────────

def parse_pdf(path: Path) -> list[Block]:
    doc = fitz.open(str(path))
    body_size = _body_font_size(doc)

    blocks: list[Block] = []
    position = 0
    heading_levels: dict[int, str] = {}

    def crumbs() -> list[str]:
        return [heading_levels[lv] for lv in sorted(heading_levels)]

    for page_num, page in enumerate(doc, start=1):
        # Elements collected on this page: (y0, block_type, text, level, meta)
        page_elements: list[tuple[float, BlockType, str, int | None, dict]] = []
        table_rects: list[fitz.Rect] = []

        # ── Tables (PyMuPDF ≥ 1.23) ──────────────────────────────────────
        try:
            for table in page.find_tables().tables:
                rows: list[str] = []
                for row in table.extract():
                    cells = [str(c or "").strip() for c in row]
                    rows.append(" | ".join(cells))
                text = "\n".join(rows).strip()
                if text:
                    bbox = fitz.Rect(table.bbox)
                    table_rects.append(bbox)
                    page_elements.append((
                        bbox.y0,
                        BlockType.TABLE,
                        text,
                        None,
                        {"page": page_num},
                    ))
        except AttributeError:
            # find_tables() unavailable in this PyMuPDF version
            pass

        # ── Text blocks ───────────────────────────────────────────────────
        for blk in page.get_text("dict").get("blocks", []):
            if blk.get("type") != 0:
                continue  # skip image blocks

            blk_rect = fitz.Rect(blk["bbox"])
            if any(blk_rect.intersects(tr) for tr in table_rects):
                continue  # already captured as a table

            text = _block_text(blk)
            if not text:
                continue

            span = _dominant_span(blk)
            size = span.get("size", body_size)
            flags = span.get("flags", 0)
            is_bold = bool(flags & (1 << 4))

            is_heading = (size > body_size + 1.0 or is_bold) and len(text) < 200

            if is_heading:
                level = _infer_heading_level(size, body_size)
                page_elements.append((
                    blk_rect.y0,
                    BlockType.HEADING,
                    text,
                    level,
                    {"page": page_num, "font_size": round(size, 2)},
                ))
            else:
                page_elements.append((
                    blk_rect.y0,
                    BlockType.PARAGRAPH,
                    text,
                    None,
                    {"page": page_num, "font_size": round(size, 2)},
                ))

        # Sort by vertical position to preserve reading order
        page_elements.sort(key=lambda e: e[0])

        for _, btype, text, level, meta in page_elements:
            if btype == BlockType.HEADING:
                all_crumbs = _update_headings(heading_levels, level, text)  # type: ignore[arg-type]
                blocks.append(Block(
                    position=position,
                    type=BlockType.HEADING,
                    breadcrumbs=all_crumbs[:-1],
                    text=text,
                    level=level,
                    metadata=meta,
                ))
            else:
                blocks.append(Block(
                    position=position,
                    type=btype,
                    breadcrumbs=crumbs(),
                    text=text,
                    level=None,
                    metadata=meta,
                ))
            position += 1

    doc.close()
    return blocks
