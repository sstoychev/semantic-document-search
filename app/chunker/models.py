from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    CODE = "code"
    CAPTION = "caption"


@dataclass
class Block:
    """A logical, unsplittable unit extracted from a document.

    Attributes:
        position:    0-based sequential index within the document.
        type:        Semantic type of the block.
        breadcrumbs: Heading hierarchy *above* this block, outermost first.
                     E.g. a paragraph under Chapter 1 > Intro has
                     breadcrumbs=["Chapter 1", "Intro"].
                     The heading block for "Intro" itself has
                     breadcrumbs=["Chapter 1"].
        text:        Plain-text content of the block.
        level:       Heading level 1–6 (HEADING blocks only, else None).
        metadata:    Parser-specific extras (page number, font size, …).
    """

    position: int
    type: BlockType
    breadcrumbs: list[str]
    text: str
    level: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
