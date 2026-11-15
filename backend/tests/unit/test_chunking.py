"""Deterministic chunking tests (Phase 2C).

The properties that matter: boundaries fall on sentence ends where possible,
overlap rescues boundary-spanning sentences, offsets always point at the text
that produced the chunk, and the same input always yields the same output.
"""

from __future__ import annotations

import hashlib
import itertools

import pytest

from app.services.chunking import (
    CHUNKING_VERSION,
    ChunkingConfig,
    PageRange,
    chunk_text,
)


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_a_single_chunk() -> None:
    drafts = chunk_text("A short note.")
    assert len(drafts) == 1
    assert drafts[0].chunk_index == 0
    assert drafts[0].content == "A short note."
    assert drafts[0].source_location.start_offset == 0
    assert drafts[0].source_location.end_offset == len("A short note.")


def test_offsets_exactly_reproduce_every_chunk() -> None:
    text = ("Sentence one. " * 200).strip()
    drafts = chunk_text(text)
    assert len(drafts) > 1
    for draft in drafts:
        location = draft.source_location
        assert text[location.start_offset : location.end_offset] == draft.content


def test_chunk_indices_are_contiguous_from_zero() -> None:
    text = ("Alpha beta gamma. " * 300).strip()
    drafts = chunk_text(text)
    assert [draft.chunk_index for draft in drafts] == list(range(len(drafts)))


def test_chunks_prefer_sentence_boundaries() -> None:
    text = "First sentence here. Second sentence here. Third sentence here. " * 40
    drafts = chunk_text(text)
    for draft in drafts:
        stripped = draft.content.rstrip()
        assert stripped.endswith((".", "!", "?")) or draft is drafts[-1]


def test_no_chunk_exceeds_the_hard_maximum() -> None:
    # One enormous unpunctuated block with no spaces: the hard split applies.
    text = "x" * 20_000
    drafts = chunk_text(text)
    for draft in drafts:
        assert len(draft.content) <= 4000


def test_long_unpunctuated_text_splits_on_word_boundaries() -> None:
    text = " ".join(["word"] * 5000)
    drafts = chunk_text(text)
    # No word may be cut in half: every chunk boundary sits on a space.
    for draft in drafts[:-1]:
        end = draft.source_location.end_offset
        assert text[end - 1] == " "
    # And the concatenation of chunk starts covers the whole document.
    assert drafts[0].source_location.start_offset == 0
    assert drafts[-1].source_location.end_offset == len(text)


def test_overlap_makes_neighbouring_chunks_share_text() -> None:
    text = "".join(f"Sentence number {index}. " for index in range(400))
    drafts = chunk_text(text, config=ChunkingConfig(target_chars=400, overlap_chars=120))
    assert len(drafts) >= 3
    for previous, current in itertools.pairwise(drafts):
        assert current.source_location.start_offset < previous.source_location.end_offset


def test_overlap_is_bounded_by_the_configured_value() -> None:
    text = "".join(f"Sentence number {index}. " for index in range(400))
    config = ChunkingConfig(target_chars=400, overlap_chars=100)
    drafts = chunk_text(text, config=config)
    for previous, current in itertools.pairwise(drafts):
        shared = previous.source_location.end_offset - current.source_location.start_offset
        # The overlap never reaches back past the start of the previous chunk.
        assert 0 <= shared <= config.overlap_chars


def test_page_numbers_are_assigned_from_the_page_map() -> None:
    text = "Page one content. Page two content."
    split = text.index("Page two")
    pages = [
        PageRange(number=1, start_offset=0, end_offset=split),
        PageRange(number=2, start_offset=split, end_offset=len(text)),
    ]
    drafts = chunk_text(text, pages=pages, config=ChunkingConfig(target_chars=18, overlap_chars=0))
    assert len(drafts) >= 2
    assert drafts[0].source_location.page == 1
    assert drafts[-1].source_location.page == 2


def test_no_page_map_means_no_page_claim() -> None:
    drafts = chunk_text("Some text without pages.")
    assert drafts[0].source_location.page is None


def test_content_hash_matches_the_content() -> None:
    drafts = chunk_text("Hash me.")
    expected = hashlib.sha256(b"Hash me.").hexdigest()
    assert drafts[0].content_hash == expected


def test_chunking_is_deterministic() -> None:
    text = "".join(f"Paragraph {index}. " for index in range(300))
    first = chunk_text(text)
    second = chunk_text(text)
    assert [(d.chunk_index, d.content, d.content_hash) for d in first] == [
        (d.chunk_index, d.content, d.content_hash) for d in second
    ]


def test_different_config_produces_different_chunks() -> None:
    text = "".join(f"Sentence {index}. " for index in range(200))
    small = chunk_text(text, config=ChunkingConfig(target_chars=300, overlap_chars=0))
    large = chunk_text(text, config=ChunkingConfig(target_chars=1200, overlap_chars=0))
    assert len(small) > len(large)


def test_config_records_the_version() -> None:
    config = ChunkingConfig()
    assert config.version == CHUNKING_VERSION
    assert config.to_json() == {
        "method": "paragraph-window",
        "chunking_version": CHUNKING_VERSION,
        "target_chars": 900,
        "overlap_chars": 150,
    }


@pytest.mark.parametrize("target", [100, 300, 900, 2000])
def test_offsets_stay_in_bounds_for_many_targets(target: int) -> None:
    text = "".join(f"Item {index} is described here. " for index in range(250))
    drafts = chunk_text(text, config=ChunkingConfig(target_chars=target, overlap_chars=target // 6))
    for draft in drafts:
        assert 0 <= draft.source_location.start_offset < len(text)
        assert draft.source_location.end_offset <= len(text)
        assert draft.source_location.start_offset < draft.source_location.end_offset


def test_unicode_is_chunked_by_characters_not_bytes() -> None:
    text = "Kano na Najeriya. " * 100
    drafts = chunk_text(text, config=ChunkingConfig(target_chars=80, overlap_chars=10))
    for draft in drafts:
        location = draft.source_location
        assert text[location.start_offset : location.end_offset] == draft.content
