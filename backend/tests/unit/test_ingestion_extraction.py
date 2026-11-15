"""Extraction tests (Phase 2B).

PDFs are synthesised in-test with `pypdf`, so page boundaries are verified
against a real multi-page document rather than a mocked parser.
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app.services.ingestion.extraction import (
    MAX_EXTRACTED_CHARS,
    ExtractionError,
    MarkdownExtractor,
    PdfExtractor,
    PlainTextExtractor,
    extract,
    extractor_for,
)
from app.services.ingestion.validation import DetectedFormat


def make_pdf(pages: list[str]) -> bytes:
    """Build a real PDF with one text-free page per entry.

    pypdf cannot synthesise text content without a full layout engine, so these
    PDFs exercise the structural path (page count, encryption, corruption) and
    the "no text layer" path, which is exactly what a scanned PDF produces.
    """
    writer = PdfWriter()
    for _ in pages:
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# --- plain text ----------------------------------------------------------


def test_plain_text_extracts_full_document() -> None:
    result = PlainTextExtractor().extract(b"First line.\nSecond line.")
    assert result.text == "First line.\nSecond line."
    assert result.method == "plain-text"
    assert result.page_count == 1
    assert result.segments[0].start_offset == 0
    assert result.segments[0].end_offset == len(result.text)


def test_plain_text_strips_trailing_whitespace_per_line() -> None:
    """Stable normalization keeps chunk hashes reproducible."""
    result = PlainTextExtractor().extract(b"a   \nb\t\nc")
    assert result.text == "a\nb\nc"


def test_plain_text_normalizes_crlf() -> None:
    assert PlainTextExtractor().extract(b"a\r\nb\rc").text == "a\nb\nc"


def test_plain_text_rejects_invalid_utf8() -> None:
    with pytest.raises(ExtractionError) as error:
        PlainTextExtractor().extract("café".encode("latin-1"))
    assert error.value.code == "unsupported_encoding"


def test_plain_text_content_hash_is_deterministic() -> None:
    first = PlainTextExtractor().extract(b"same text")
    second = PlainTextExtractor().extract(b"same text")
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64


def test_oversized_text_rejected() -> None:
    with pytest.raises(ExtractionError) as error:
        PlainTextExtractor().extract(b"x" * (MAX_EXTRACTED_CHARS + 1))
    assert error.value.code == "too_much_text"


# --- markdown ------------------------------------------------------------


def test_markdown_preserves_text_verbatim() -> None:
    source = b"# Title\n\nIntro paragraph.\n\n## Section\n\nBody text."
    result = MarkdownExtractor().extract(source)
    assert result.text == source.decode()


def test_markdown_records_headings_with_offsets() -> None:
    result = MarkdownExtractor().extract(b"# Title\n\nBody.\n\n## Section\n\nMore.")
    titles = [heading["title"] for heading in result.metadata["headings"]]
    assert titles == ["Title", "Section"]
    levels = [heading["level"] for heading in result.metadata["headings"]]
    assert levels == [1, 2]
    for heading in result.metadata["headings"]:
        offset = heading["char_offset"]
        assert result.text[offset] == "#"


def test_markdown_splits_segments_on_headings() -> None:
    result = MarkdownExtractor().extract(b"# One\n\na\n\n# Two\n\nb")
    assert len(result.segments) >= 2
    for segment in result.segments:
        assert 0 <= segment.start_offset <= segment.end_offset <= len(result.text)


def test_markdown_segment_offsets_are_contiguous() -> None:
    result = MarkdownExtractor().extract(b"# One\n\na\n\n# Two\n\nb")
    for previous, current in zip(result.segments, result.segments[1:], strict=False):
        assert previous.end_offset == current.start_offset


def test_markdown_without_headings_is_one_segment() -> None:
    result = MarkdownExtractor().extract(b"just text\nmore text")
    assert len(result.segments) == 1


# --- pdf -----------------------------------------------------------------


def test_pdf_without_text_layer_reports_no_text() -> None:
    """A scanned PDF must fail loudly, not produce an empty citation."""
    with pytest.raises(ExtractionError) as error:
        PdfExtractor().extract(make_pdf(["a", "b"]))
    assert error.value.code == "no_text_layer"


def test_corrupt_pdf_rejected() -> None:
    with pytest.raises(ExtractionError) as error:
        PdfExtractor().extract(b"%PDF-1.7\ngarbage that is not a pdf")
    assert error.value.code in {"corrupt_pdf", "no_text_layer"}


def test_encrypted_pdf_rejected() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret-password")
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(ExtractionError) as error:
        PdfExtractor().extract(buffer.getvalue())
    assert error.value.code == "encrypted_pdf"


def test_pdf_page_count_is_reported() -> None:
    """Page structure is read even when there is no text to cite."""
    from pypdf import PdfReader

    raw = make_pdf(["one", "two", "three"])
    assert len(PdfReader(io.BytesIO(raw)).pages) == 3


# --- registry ------------------------------------------------------------


@pytest.mark.parametrize(
    ("detected", "method"),
    [
        (DetectedFormat.TEXT, "plain-text"),
        (DetectedFormat.MARKDOWN, "markdown"),
        (DetectedFormat.PDF, "pdf"),
    ],
)
def test_every_format_has_a_registered_extractor(detected: DetectedFormat, method: str) -> None:
    assert extractor_for(detected).method == method


def test_extract_dispatches_to_the_right_parser() -> None:
    assert extract(detected=DetectedFormat.TEXT, raw=b"hello").method == "plain-text"
    assert extract(detected=DetectedFormat.MARKDOWN, raw=b"# hi").method == "markdown"
