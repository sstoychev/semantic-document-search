"""Tests for app.chunker.get_blocks() across all supported document formats."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.chunker import Block, BlockType, get_blocks

EXPECTED_H1 = "Python Web Frameworks"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _assert_sequential_positions(blocks: list[Block]) -> None:
    """Positions must be 0-based and increase by 1 each step."""
    assert [b.position for b in blocks] == list(range(len(blocks)))


def _assert_valid_breadcrumbs(blocks: list[Block]) -> None:
    """Every breadcrumbs field must be a list of strings."""
    for block in blocks:
        assert isinstance(block.breadcrumbs, list), (
            f"Block {block.position} breadcrumbs is not a list"
        )
        assert all(isinstance(c, str) for c in block.breadcrumbs), (
            f"Block {block.position} breadcrumbs contains non-strings"
        )


def _first_heading(blocks: list[Block]) -> Block:
    headings = [b for b in blocks if b.type == BlockType.HEADING]
    assert headings, "No HEADING blocks found"
    return headings[0]


# ---------------------------------------------------------------------------
# TXT — structured Markdown-style document
# ---------------------------------------------------------------------------

class TestTxt:
    def test_returns_blocks(self, sample_txt_path: Path) -> None:
        blocks = get_blocks(sample_txt_path)
        assert len(blocks) > 0

    def test_first_block_is_h1(self, sample_txt_path: Path) -> None:
        blocks = get_blocks(sample_txt_path)
        h1 = blocks[0]
        assert h1.type == BlockType.HEADING
        assert h1.level == 1
        assert h1.text == EXPECTED_H1
        assert h1.breadcrumbs == []

    def test_heading_breadcrumbs(self, sample_txt_path: Path) -> None:
        blocks = get_blocks(sample_txt_path)
        # The first H2 must carry the H1 text as its breadcrumb
        h2_blocks = [b for b in blocks if b.type == BlockType.HEADING and b.level == 2]
        assert h2_blocks, "No H2 blocks found"
        assert EXPECTED_H1 in h2_blocks[0].breadcrumbs

    def test_has_list_block(self, sample_txt_path: Path) -> None:
        blocks = get_blocks(sample_txt_path)
        assert any(b.type == BlockType.LIST for b in blocks), "No LIST block found"

    def test_has_code_block(self, sample_txt_path: Path) -> None:
        blocks = get_blocks(sample_txt_path)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        assert code_blocks, "No CODE block found"
        assert "flask" in code_blocks[0].text.lower()

    def test_no_table_block(self, sample_txt_path: Path) -> None:
        # The TXT parser does not recognise Markdown pipe-tables;
        # the table lines become a PARAGRAPH instead.
        blocks = get_blocks(sample_txt_path)
        assert not any(b.type == BlockType.TABLE for b in blocks)

    def test_sequential_positions(self, sample_txt_path: Path) -> None:
        _assert_sequential_positions(get_blocks(sample_txt_path))

    def test_valid_breadcrumbs(self, sample_txt_path: Path) -> None:
        _assert_valid_breadcrumbs(get_blocks(sample_txt_path))


# ---------------------------------------------------------------------------
# TXT — plain paragraphs only
# ---------------------------------------------------------------------------

class TestPlainTxt:
    def test_only_paragraph_blocks(self, plain_txt_path: Path) -> None:
        blocks = get_blocks(plain_txt_path)
        assert len(blocks) > 0
        non_para = [b for b in blocks if b.type != BlockType.PARAGRAPH]
        assert not non_para, (
            f"Expected only PARAGRAPH blocks, found: "
            f"{[b.type for b in non_para]}"
        )

    def test_block_count_in_range(self, plain_txt_path: Path) -> None:
        blocks = get_blocks(plain_txt_path)
        assert 5 <= len(blocks) <= 20, f"Expected 5–20 blocks, got {len(blocks)}"

    def test_sequential_positions(self, plain_txt_path: Path) -> None:
        _assert_sequential_positions(get_blocks(plain_txt_path))

    def test_empty_breadcrumbs(self, plain_txt_path: Path) -> None:
        # No headings → all breadcrumbs should be empty
        for block in get_blocks(plain_txt_path):
            assert block.breadcrumbs == []


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

class TestHtml:
    def test_returns_blocks(self, sample_html_path: Path) -> None:
        assert len(get_blocks(sample_html_path)) > 0

    def test_first_block_is_h1(self, sample_html_path: Path) -> None:
        blocks = get_blocks(sample_html_path)
        h1 = blocks[0]
        assert h1.type == BlockType.HEADING
        assert h1.level == 1
        assert h1.text == EXPECTED_H1
        assert h1.breadcrumbs == []

    def test_has_table_block(self, sample_html_path: Path) -> None:
        blocks = get_blocks(sample_html_path)
        table_blocks = [b for b in blocks if b.type == BlockType.TABLE]
        assert table_blocks, "No TABLE block found"
        # Cells should be pipe-separated
        assert "|" in table_blocks[0].text

    def test_has_list_block(self, sample_html_path: Path) -> None:
        blocks = get_blocks(sample_html_path)
        list_blocks = [b for b in blocks if b.type == BlockType.LIST]
        assert list_blocks, "No LIST block found"
        # Each item should start with "- "
        assert "- " in list_blocks[0].text

    def test_has_code_block_with_language(self, sample_html_path: Path) -> None:
        blocks = get_blocks(sample_html_path)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        assert code_blocks, "No CODE block found"
        assert code_blocks[0].metadata.get("language") == "python"
        assert "flask" in code_blocks[0].text.lower()

    def test_table_breadcrumbs(self, sample_html_path: Path) -> None:
        blocks = get_blocks(sample_html_path)
        table_block = next(b for b in blocks if b.type == BlockType.TABLE)
        # Table sits under "Comparison" (H2) → breadcrumbs must include H1 + H2
        assert EXPECTED_H1 in table_block.breadcrumbs
        assert "Comparison" in table_block.breadcrumbs

    def test_sequential_positions(self, sample_html_path: Path) -> None:
        _assert_sequential_positions(get_blocks(sample_html_path))

    def test_valid_breadcrumbs(self, sample_html_path: Path) -> None:
        _assert_valid_breadcrumbs(get_blocks(sample_html_path))


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

class TestPdf:
    def test_returns_blocks(self, sample_pdf_path: Path) -> None:
        assert len(get_blocks(sample_pdf_path)) > 0

    def test_first_heading_is_h1(self, sample_pdf_path: Path) -> None:
        blocks = get_blocks(sample_pdf_path)
        h1 = _first_heading(blocks)
        assert h1.level == 1
        assert h1.text == EXPECTED_H1

    def test_multiple_heading_levels(self, sample_pdf_path: Path) -> None:
        blocks = get_blocks(sample_pdf_path)
        levels = {b.level for b in blocks if b.type == BlockType.HEADING}
        assert len(levels) >= 2, f"Expected ≥2 heading levels, found: {levels}"

    def test_has_paragraph_blocks(self, sample_pdf_path: Path) -> None:
        blocks = get_blocks(sample_pdf_path)
        assert any(b.type == BlockType.PARAGRAPH for b in blocks)

    def test_metadata_has_page_number(self, sample_pdf_path: Path) -> None:
        blocks = get_blocks(sample_pdf_path)
        for b in blocks:
            assert "page" in b.metadata, f"Block {b.position} missing 'page' metadata"
            assert isinstance(b.metadata["page"], int)

    def test_sequential_positions(self, sample_pdf_path: Path) -> None:
        _assert_sequential_positions(get_blocks(sample_pdf_path))

    def test_valid_breadcrumbs(self, sample_pdf_path: Path) -> None:
        _assert_valid_breadcrumbs(get_blocks(sample_pdf_path))


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

class TestDocx:
    def test_returns_blocks(self, sample_docx_path: Path) -> None:
        assert len(get_blocks(sample_docx_path)) > 0

    def test_first_block_is_h1(self, sample_docx_path: Path) -> None:
        blocks = get_blocks(sample_docx_path)
        h1 = blocks[0]
        assert h1.type == BlockType.HEADING
        assert h1.level == 1
        assert h1.text == EXPECTED_H1
        assert h1.breadcrumbs == []

    def test_has_table_block(self, sample_docx_path: Path) -> None:
        blocks = get_blocks(sample_docx_path)
        table_blocks = [b for b in blocks if b.type == BlockType.TABLE]
        assert table_blocks, "No TABLE block found"
        assert "|" in table_blocks[0].text

    def test_has_list_block(self, sample_docx_path: Path) -> None:
        blocks = get_blocks(sample_docx_path)
        list_blocks = [b for b in blocks if b.type == BlockType.LIST]
        assert list_blocks, "No LIST block found"

    def test_has_code_block(self, sample_docx_path: Path) -> None:
        blocks = get_blocks(sample_docx_path)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        assert code_blocks, "No CODE block found"
        assert "flask" in code_blocks[0].text.lower()

    def test_code_block_is_merged(self, sample_docx_path: Path) -> None:
        # All consecutive Code-style paragraphs must be merged into one block
        blocks = get_blocks(sample_docx_path)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        assert len(code_blocks) == 1, (
            f"Expected 1 merged CODE block, got {len(code_blocks)}"
        )
        assert "\n" in code_blocks[0].text  # confirms multiple lines were merged

    def test_heading_breadcrumbs(self, sample_docx_path: Path) -> None:
        blocks = get_blocks(sample_docx_path)
        h2_blocks = [b for b in blocks if b.type == BlockType.HEADING and b.level == 2]
        assert h2_blocks
        assert EXPECTED_H1 in h2_blocks[0].breadcrumbs

    def test_sequential_positions(self, sample_docx_path: Path) -> None:
        _assert_sequential_positions(get_blocks(sample_docx_path))

    def test_valid_breadcrumbs(self, sample_docx_path: Path) -> None:
        _assert_valid_breadcrumbs(get_blocks(sample_docx_path))


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_blocks(tmp_path / "nonexistent.txt")

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "document.odt"
        f.touch()
        with pytest.raises(ValueError, match="Unsupported file type"):
            get_blocks(f)
