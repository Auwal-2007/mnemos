"""Text extraction (Phase 2B).

One interface, one implementation per format, registered in a table so a new
parser is a new class rather than a change to the pipeline. Extraction is
pure: bytes in, structured result out, no database and no filesystem.

Location is never flattened away. Every extractor reports:

* the full text;
* a segment list — pages for PDF, one segment for single-part text — with
  half-open character offsets into that text;
* the method name recorded on the version so the origin of the text is
  auditable.

Failure is explicit. A PDF with no text layer, an encrypted PDF, a corrupt
file and an oversized document each produce a distinct error code, because
"failed" alone cannot tell a user what to do next.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from app.services.ingestion.validation import DetectedFormat

logger = logging.getLogger("mnemos.ingestion.extraction")

MAX_EXTRACTED_CHARS = 2_000_000


class ExtractionError(Exception):
    """Extraction failed with a stable, user-safe code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Segment:
    """A page or contiguous part of the extracted text."""

    number: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Text plus where it came from."""

    text: str
    segments: list[Segment]
    method: str
    page_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def char_count(self) -> int:
        return len(self.text)


class Extractor(Protocol):
    """A format-specific text extractor."""

    method: str

    def extract(self, raw: bytes) -> ExtractionResult: ...


def _normalize(text: str) -> str:
    """Normalize newlines and trim trailing whitespace per line.

    Trailing spaces would make chunk hashes unstable across re-extraction of
    the same document, which would break the "re-indexing does not create
    duplicates" guarantee.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip("\n")


class PlainTextExtractor:
    """UTF-8 text, one segment covering the whole document."""

    method = "plain-text"

    def extract(self, raw: bytes) -> ExtractionResult:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ExtractionError(
                "unsupported_encoding", "The file is not valid UTF-8 text."
            ) from exc
        text = _normalize(text)
        _guard_size(text)
        return ExtractionResult(
            text=text,
            segments=[Segment(number=1, start_offset=0, end_offset=len(text))],
            method=self.method,
            page_count=1,
            metadata={"format": "text"},
        )


class MarkdownExtractor:
    """Markdown is stored as-is; structure is preserved for later retrieval.

    Headings become section labels on segments so a citation can say
    "section: Results" without a second parse.
    """

    method = "markdown"

    def extract(self, raw: bytes) -> ExtractionResult:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ExtractionError(
                "unsupported_encoding", "The file is not valid UTF-8 text."
            ) from exc
        text = _normalize(text)
        _guard_size(text)

        segments: list[Segment] = []
        headings: list[dict[str, Any]] = []
        offset = 0
        segment_start = 0
        segment_heading: str | None = None
        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                hashes = len(stripped) - len(stripped.lstrip("#"))
                label = stripped[hashes:].strip()
                if label:
                    headings.append({"char_offset": offset, "level": hashes, "title": label[:200]})
                    if offset > segment_start:
                        segments.append(
                            Segment(
                                number=len(segments) + 1,
                                start_offset=segment_start,
                                end_offset=offset,
                            )
                        )
                    segment_start = offset
                    segment_heading = label[:200]
            offset += len(line) + 1

        if text and (len(segments) == 0 or segment_start < len(text)):
            segments.append(
                Segment(
                    number=len(segments) + 1,
                    start_offset=segment_start,
                    end_offset=len(text),
                )
            )

        metadata: dict[str, Any] = {"format": "markdown", "headings": headings}
        if segment_heading is not None:
            metadata["last_heading"] = segment_heading
        return ExtractionResult(
            text=text,
            segments=segments or [Segment(number=1, start_offset=0, end_offset=0)],
            method=self.method,
            page_count=len(segments),
            metadata=metadata,
        )


class PdfExtractor:
    """PDF text extraction with page boundaries preserved.

    `pypdf` is a pure-Python reader: it never executes PDF JavaScript, never
    renders, and never writes files. Each page's text is appended to one
    buffer and the page's `[start, end)` range is recorded, so a chunk can be
    traced to a page without storing the page separately.
    """

    method = "pdf"

    def extract(self, raw: bytes) -> ExtractionResult:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(raw), strict=False)
        except PdfReadError as exc:
            raise ExtractionError("corrupt_pdf", "The PDF could not be parsed.") from exc
        except Exception as exc:
            logger.warning("PDF open failed (%s)", type(exc).__name__)
            raise ExtractionError("corrupt_pdf", "The PDF could not be parsed.") from exc

        if reader.is_encrypted:
            # An empty user password is common and legitimate; try it once.
            try:
                # cast: pypdf returns a PasswordType enum, which is truthy for
                # the successful cases and 0 for failure.
                unlocked = bool(cast("Any", reader.decrypt("")))
            except Exception:
                unlocked = False
            if not unlocked:
                raise ExtractionError(
                    "encrypted_pdf",
                    "This PDF is password-protected and cannot be read.",
                )

        parts: list[str] = []
        segments: list[Segment] = []
        empty_pages: list[int] = []
        offset = 0

        for index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                logger.warning("PDF page %d failed to extract (%s)", index, type(exc).__name__)
                page_text = ""
            page_text = _normalize(page_text)

            if not page_text:
                empty_pages.append(index)

            if parts:
                parts.append("\n")
                offset += 1
            start = offset
            parts.append(page_text)
            offset += len(page_text)
            segments.append(Segment(number=index, start_offset=start, end_offset=offset))

            if offset > MAX_EXTRACTED_CHARS:
                raise ExtractionError(
                    "too_much_text",
                    "The extracted text exceeds the supported size.",
                )

        text = _normalize("".join(parts))
        if not text.strip():
            raise ExtractionError(
                "no_text_layer",
                "This PDF has no extractable text. It may be a scanned image.",
            )

        # Recompute offsets against the normalized text so they stay valid.
        segments = _rebase_segments(text, segments)
        return ExtractionResult(
            text=text,
            segments=segments,
            method=self.method,
            page_count=len(reader.pages),
            metadata={
                "format": "pdf",
                "empty_pages": empty_pages,
                "pages_without_text": len(empty_pages),
            },
        )


def _rebase_segments(text: str, segments: list[Segment]) -> list[Segment]:
    """Clamp segment offsets to the final text length.

    Only the trailing whitelist matters: `_normalize` strips the ends, so the
    last segment's end may now be past the end of the string.
    """
    rebased: list[Segment] = []
    for segment in segments:
        start = min(segment.start_offset, len(text))
        end = min(segment.end_offset, len(text))
        if end < start:
            end = start
        rebased.append(Segment(number=segment.number, start_offset=start, end_offset=end))
    return rebased


def _guard_size(text: str) -> None:
    if len(text) > MAX_EXTRACTED_CHARS:
        raise ExtractionError("too_much_text", "The extracted text exceeds the supported size.")


_EXTRACTORS: dict[DetectedFormat, Extractor] = {
    DetectedFormat.TEXT: PlainTextExtractor(),
    DetectedFormat.MARKDOWN: MarkdownExtractor(),
    DetectedFormat.PDF: PdfExtractor(),
}


def extractor_for(detected: DetectedFormat) -> Extractor:
    """Look up the extractor for a detected format.

    Adding a format means adding a spec, an extractor and a registry entry —
    no change to the pipeline.
    """
    try:
        return _EXTRACTORS[detected]
    except KeyError as exc:  # pragma: no cover - registry and enum move together
        raise ExtractionError(
            "unsupported_type", "No extractor is registered for this file type."
        ) from exc


def extract(detected: DetectedFormat, raw: bytes) -> ExtractionResult:
    """Extract text, converting unexpected parser errors into a stable code."""
    extractor = extractor_for(detected)
    try:
        return extractor.extract(raw)
    except ExtractionError:
        raise
    except Exception as exc:
        logger.error("Extraction failed unexpectedly (%s)", type(exc).__name__)
        raise ExtractionError("extraction_failed", "The document could not be read.") from exc
