"""Plain-text parser.

Recognises Markdown-style structure:
  - ATX headings:      # H1  /  ## H2  /  …
  - Setext headings:   underlined with === or ---
  - Fenced code:       ``` … ```  or  ~~~ … ~~~  (with optional language tag)
  - Unordered lists:   -, *, + prefixed items (including indented continuations)
  - Ordered lists:     1. 2. … prefixed items
  - Paragraphs:        blank-line-separated runs of text
"""
from __future__ import annotations

import re
from pathlib import Path

from app.chunker.models import Block, BlockType

_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_SETEXT_H1 = re.compile(r"^={2,}\s*$")
_SETEXT_H2 = re.compile(r"^-{3,}\s*$")          # 3+ dashes avoids clash with list items
_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(\w*)")  # ```python, ~~~, etc.
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+\.)\s+\S")


def _update_headings(heading_levels: dict[int, str], level: int, text: str) -> list[str]:
    heading_levels[level] = text
    for lvl in [lv for lv in heading_levels if lv > level]:
        del heading_levels[lvl]
    return [heading_levels[lv] for lv in sorted(heading_levels)]


def parse_txt(path: Path) -> list[Block]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: list[Block] = []
    position = 0
    heading_levels: dict[int, str] = {}

    def crumbs() -> list[str]:
        return [heading_levels[lv] for lv in sorted(heading_levels)]

    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ─────────────────────────────────────────────
        m_fence = _FENCE_OPEN.match(line)
        if m_fence:
            fence_marker = m_fence.group(1)
            language = m_fence.group(2)
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith(fence_marker):
                code_lines.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            blocks.append(Block(
                position=position,
                type=BlockType.CODE,
                breadcrumbs=crumbs(),
                text="\n".join(code_lines),
                metadata={"language": language} if language else {},
            ))
            position += 1
            continue

        # ── ATX heading ───────────────────────────────────────────────────
        m_atx = _ATX_HEADING.match(line)
        if m_atx:
            level = len(m_atx.group(1))
            text = m_atx.group(2).strip()
            all_crumbs = _update_headings(heading_levels, level, text)
            blocks.append(Block(
                position=position,
                type=BlockType.HEADING,
                breadcrumbs=all_crumbs[:-1],
                text=text,
                level=level,
            ))
            position += 1
            i += 1
            continue

        # ── Setext heading (look-ahead) ────────────────────────────────────
        if line.strip() and i + 1 < len(lines):
            under = lines[i + 1]
            setext_level: int | None = None
            if _SETEXT_H1.match(under):
                setext_level = 1
            elif _SETEXT_H2.match(under):
                setext_level = 2
            if setext_level is not None:
                text = line.strip()
                all_crumbs = _update_headings(heading_levels, setext_level, text)
                blocks.append(Block(
                    position=position,
                    type=BlockType.HEADING,
                    breadcrumbs=all_crumbs[:-1],
                    text=text,
                    level=setext_level,
                ))
                position += 1
                i += 2
                continue

        # ── List block ────────────────────────────────────────────────────
        if _LIST_ITEM.match(line):
            list_lines: list[str] = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if _LIST_ITEM.match(nxt):
                    list_lines.append(nxt)
                    i += 1
                elif nxt.startswith(("  ", "\t")) and list_lines:
                    # Indented continuation / nested list content
                    list_lines.append(nxt)
                    i += 1
                else:
                    break
            blocks.append(Block(
                position=position,
                type=BlockType.LIST,
                breadcrumbs=crumbs(),
                text="\n".join(list_lines),
            ))
            position += 1
            continue

        # ── Blank line ────────────────────────────────────────────────────
        if not line.strip():
            i += 1
            continue

        # ── Paragraph ─────────────────────────────────────────────────────
        para_lines: list[str] = []
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            if _ATX_HEADING.match(nxt) or _FENCE_OPEN.match(nxt) or _LIST_ITEM.match(nxt):
                break
            # Stop before a setext underline (the current line becomes a heading)
            if para_lines and i + 1 < len(lines):
                under = lines[i + 1]
                if _SETEXT_H1.match(under) or _SETEXT_H2.match(under):
                    break
            para_lines.append(nxt)
            i += 1

        if para_lines:
            blocks.append(Block(
                position=position,
                type=BlockType.PARAGRAPH,
                breadcrumbs=crumbs(),
                text="\n".join(para_lines),
            ))
            position += 1

    return blocks
