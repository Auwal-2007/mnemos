"""Deterministic chunking (Phase 2C).

Strategy: **paragraph-window with sentence-boundary fallback.**

Why this strategy
-----------------
Retrieval quality for provenance-aware question answering depends less on
semantic cleverness than on chunks being (a) small enough to quote exactly and
(b) large enough to be self-contained. A fixed character window cuts sentences
in half, which makes claim verification (3C) compare against truncated
evidence. A pure paragraph split produces enormous chunks for unbroken prose.

The chosen rule is:

1. Split the extracted text into blocks on blank lines.
2. Accumulate blocks until adding the next would exceed ``target_chars``.
3. Close the chunk at the last sentence end inside the accumulated text, so a
   chunk never ends mid-sentence when a sentence end is available.
4. If a single block exceeds ``target_chars``, split it on sentence boundaries,
   and failing that, hard-split at the limit.
5. Overlap the tail of the previous chunk by ``overlap_chars`` at a sentence
   boundary, so a sentence spanning a boundary is retrievable from both sides.

Parameters and why they are these values
----------------------------------------
``target_chars = 900`` — roughly 150-220 English words. Large enough to hold a
complete argument, small enough that a citation is specific and the embedding
vector is not diluted across several topics. (Embedding models commonly cap at
512-8192 tokens; 900 characters is far below every candidate limit, so the
choice is driven by citation precision rather than by the model.)

``overlap_chars = 150`` — about one sentence. Overlap costs index size, so it is
kept to the minimum that still rescues boundary-spanning sentences.

``chunking_version = 1`` — recorded on every chunk. Any change to these rules
must bump it, so a re-index can be recognised as a *different* configuration
rather than silently mixing chunk shapes.

Determinism
-----------
Same input text + same parameters ⇒ identical chunks, identical offsets,
identical content hashes. There is no randomness and no model involvement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.knowledge import ChunkDraft, SourceLocation

CHUNKING_METHOD = "paragraph-window"
CHUNKING_VERSION = 1
TARGET_CHARS = 900
OVERLAP_CHARS = 150
#: Absolute guard so a pathological input cannot create one huge chunk.
HARD_MAX_CHARS = 4000

_SENTENCE_ENDS = (". ", "! ", "? ", ".\n", "!\n", "?\n", "\n\n")


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """The configuration recorded alongside every chunk set."""

    method: str = CHUNKING_METHOD
    version: int = CHUNKING_VERSION
    target_chars: int = TARGET_CHARS
    overlap_chars: int = OVERLAP_CHARS

    def __post_init__(self) -> None:
        # A window that does not advance would loop forever, and a negative
        # overlap is meaningless. Reject at construction rather than hang.
        if self.target_chars < 1:
            raise ValueError("target_chars must be positive")
        if self.overlap_chars >= self.target_chars:
            raise ValueError("overlap_chars must be smaller than target_chars")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must not be negative")
        if self.overlap_chars >= self.target_chars:
            raise ValueError("overlap_chars must be smaller than target_chars")

    def to_json(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "chunking_version": self.version,
            "target_chars": self.target_chars,
            "overlap_chars": self.overlap_chars,
        }


@dataclass(frozen=True, slots=True)
class PageRange:
    """A page's span in the extracted text, used to label a chunk's page."""

    number: int
    start_offset: int
    end_offset: int


def _last_sentence_end(text: str, limit: int) -> int:
    """Index just past the last sentence terminator before ``limit``."""
    best = -1
    for token in _SENTENCE_ENDS:
        index = text.rfind(token, 0, limit)
        if index != -1:
            best = max(best, index + len(token))
    return best


def _first_sentence_end(text: str, start: int) -> int:
    """Index just past the first sentence terminator at or after ``start``."""
    positions = [
        text.find(token, start) + len(token)
        for token in _SENTENCE_ENDS
        if text.find(token, start) != -1
    ]
    return min(positions) if positions else -1


def _window_bounds(text: str, start: int, target: int) -> tuple[int, int]:
    """Return the (start, end) of one window beginning at ``start``."""
    if len(text) - start <= target:
        return start, len(text)

    hard_limit = min(start + target, len(text))
    sentence_end = _last_sentence_end(text, hard_limit)
    if sentence_end > start:
        return start, sentence_end

    # No sentence boundary inside the window: allow up to the hard maximum so a
    # long unpunctuated block is still cut at *some* boundary.
    wider = min(start + HARD_MAX_CHARS, len(text))
    sentence_end = _last_sentence_end(text, wider)
    if sentence_end > start:
        return start, sentence_end

    # Truly unpunctuated: split on whitespace to avoid cutting a word.
    space = text.rfind(" ", start, wider)
    if space > start:
        return start, space + 1
    return start, wider


def chunk_text(
    text: str,
    *,
    pages: list[PageRange] | None = None,
    config: ChunkingConfig | None = None,
) -> list[ChunkDraft]:
    """Split extracted text into ordered, non-empty chunk drafts.

    Offsets are absolute character positions in ``text``, so a chunk always
    resolves back to the exact characters it was built from.
    """
    config = config or ChunkingConfig()
    if not text.strip():
        return []

    page_map = pages or []
    drafts: list[ChunkDraft] = []
    start = 0
    index = 0

    while start < len(text):
        end = _window_bounds(text, start, config.target_chars)[1]
        content = text[start:end]
        if content.strip():
            drafts.append(
                ChunkDraft(
                    chunk_index=index,
                    content=content,
                    content_hash=_sha256(content),
                    source_location=SourceLocation(
                        start_offset=start,
                        end_offset=end,
                        page=_page_for(start, end, page_map),
                        section=None,
                    ),
                )
            )
            index += 1

        if end >= len(text):
            break

        # Overlap: step back to a sentence boundary so the next chunk begins on
        # a readable boundary rather than mid-word.
        next_start = end - config.overlap_chars
        if next_start <= start:
            next_start = end
        else:
            boundary = _first_sentence_end(text, next_start)
            if boundary != -1 and boundary < end:
                next_start = boundary
        start = next_start

    return drafts


def _page_for(start: int, end: int, pages: list[PageRange]) -> int | None:
    """The page a chunk starts on, or None when the source has no pages."""
    for page in pages:
        if page.start_offset <= start < page.end_offset:
            return page.number
    if pages and start >= pages[-1].end_offset:
        return pages[-1].number
    return None


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
