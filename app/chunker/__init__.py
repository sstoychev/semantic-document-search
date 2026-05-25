"""Document chunker — public API.

Usage:
    from app.chunker import get_blocks, Block, BlockType

    blocks = get_blocks("/path/to/document.pdf")
    for block in blocks:
        print(block.position, block.type, block.breadcrumbs, block.text[:80])
"""
from __future__ import annotations

from pathlib import Path

from app.chunker.models import Block, BlockType

__all__ = ["get_blocks", "Block", "BlockType"]

_SUPPORTED_EXTENSIONS = {".txt", ".html", ".htm", ".pdf", ".docx"}


def get_blocks(file_path: str | Path) -> list[Block]:
    """Extract all logical blocks from a local document file.

    Dispatches to the format-specific parser based on the file extension.
    Parser dependencies are imported lazily, so only the library for the
    requested format needs to be installed.

    Args:
        file_path: Absolute or relative path to a .txt, .html, .htm,
                   .pdf, or .docx file.

    Returns:
        Ordered list of :class:`Block` objects.  Each block represents one
        unsplittable logical unit (heading, paragraph, table, list, code
        block, or caption).  ``position`` is a 0-based index that reflects
        reading order within the document.

    Raises:
        FileNotFoundError: The file does not exist.
        ValueError:        The file extension is not supported.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".txt":
        from app.chunker.parsers.txt import parse_txt
        return parse_txt(path)

    if suffix in (".html", ".htm"):
        from app.chunker.parsers.html import parse_html
        return parse_html(path)

    if suffix == ".pdf":
        from app.chunker.parsers.pdf import parse_pdf
        return parse_pdf(path)

    if suffix == ".docx":
        from app.chunker.parsers.docx import parse_docx
        return parse_docx(path)

    raise ValueError(
        f"Unsupported file type: {suffix!r}. "
        f"Supported extensions: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
    )
