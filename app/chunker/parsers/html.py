"""HTML parser — uses BeautifulSoup with the lxml backend.

Block extraction strategy:
  - Traverse the DOM; when a "block-level" element is encountered it is
    captured whole and the traversal does NOT recurse into its children.
  - Container elements (div, section, article, main, body, figure, …) are
    transparent: the traversal recurses into them.
  - Heading hierarchy is tracked to build breadcrumbs.

Block mapping:
  h1-h6          → HEADING   (level preserved)
  p              → PARAGRAPH
  table          → TABLE     (cells joined with ' | ', rows with '\\n')
  ul / ol        → LIST      (nested lists indented with spaces)
  pre            → CODE      (raw text preserved)
  figcaption     → CAPTION
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup, NavigableString, Tag

from app.chunker.models import Block, BlockType

# Tags that produce blocks and must NOT be recursed into
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = _HEADING_TAGS | {"p", "table", "ul", "ol", "pre", "figcaption"}

# Tags whose content is irrelevant to the document body
_SKIP_TAGS = {"script", "style", "head", "meta", "link", "noscript", "nav",
              "header", "footer", "aside"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _table_to_text(tag: Tag) -> str:
    rows: list[str] = []
    for tr in tag.find_all("tr"):
        cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(["th", "td"])]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _list_to_text(tag: Tag, depth: int = 0) -> str:
    indent = "  " * depth
    lines: list[str] = []
    for li in tag.find_all("li", recursive=False):
        # Collect direct text, excluding child <ul>/<ol>
        direct: list[str] = []
        for child in li.children:
            if isinstance(child, NavigableString):
                direct.append(str(child))
            elif child.name not in ("ul", "ol"):
                direct.append(child.get_text(separator=" ", strip=True))
        lines.append(f"{indent}- {' '.join(direct).strip()}")
        # Nested lists
        for sub in li.find_all(["ul", "ol"], recursive=False):
            lines.append(_list_to_text(sub, depth + 1))
    return "\n".join(lines)


def _update_headings(heading_levels: dict[int, str], level: int, text: str) -> list[str]:
    heading_levels[level] = text
    for lvl in [lv for lv in heading_levels if lv > level]:
        del heading_levels[lvl]
    return [heading_levels[lv] for lv in sorted(heading_levels)]


# ── Main traversal ────────────────────────────────────────────────────────────

def _walk(element: Tag, heading_levels: dict[int, str]) -> Iterator[tuple[BlockType, str, list[str], int | None, dict]]:
    """Yield (type, text, breadcrumbs, level, metadata) tuples."""
    for child in element.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue

        name = child.name.lower() if child.name else ""

        if name in _SKIP_TAGS:
            continue

        if name in _HEADING_TAGS:
            level = int(name[1])
            text = child.get_text(separator=" ", strip=True)
            if text:
                crumbs = _update_headings(heading_levels, level, text)
                yield BlockType.HEADING, text, crumbs[:-1], level, {}

        elif name == "p":
            text = child.get_text(separator=" ", strip=True)
            if text:
                crumbs = [heading_levels[lv] for lv in sorted(heading_levels)]
                yield BlockType.PARAGRAPH, text, crumbs, None, {}

        elif name == "table":
            text = _table_to_text(child)
            if text.strip():
                crumbs = [heading_levels[lv] for lv in sorted(heading_levels)]
                yield BlockType.TABLE, text, crumbs, None, {}

        elif name in ("ul", "ol"):
            text = _list_to_text(child)
            if text.strip():
                crumbs = [heading_levels[lv] for lv in sorted(heading_levels)]
                yield BlockType.LIST, text, crumbs, None, {}

        elif name == "pre":
            text = child.get_text()  # preserve internal whitespace
            if text.strip():
                # Try to detect language from a nested <code class="language-xxx">
                code_tag = child.find("code")
                lang = ""
                if code_tag and isinstance(code_tag, Tag):
                    for cls in code_tag.get("class", []):
                        if cls.startswith("language-"):
                            lang = cls[len("language-"):]
                            break
                crumbs = [heading_levels[lv] for lv in sorted(heading_levels)]
                meta = {"language": lang} if lang else {}
                yield BlockType.CODE, text, crumbs, None, meta

        elif name == "figcaption":
            text = child.get_text(separator=" ", strip=True)
            if text:
                crumbs = [heading_levels[lv] for lv in sorted(heading_levels)]
                yield BlockType.CAPTION, text, crumbs, None, {}

        else:
            # Container element — recurse transparently
            yield from _walk(child, heading_levels)


# ── Public entry point ────────────────────────────────────────────────────────

def parse_html(path: Path) -> list[Block]:
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    body = soup.find("body") or soup
    heading_levels: dict[int, str] = {}
    blocks: list[Block] = []

    for position, (btype, text, crumbs, level, meta) in enumerate(
        _walk(body, heading_levels)
    ):
        blocks.append(Block(
            position=position,
            type=btype,
            breadcrumbs=crumbs,
            text=text,
            level=level,
            metadata=meta,
        ))

    return blocks
