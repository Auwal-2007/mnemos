"""Chunking configuration manifest test (Phase 2C).

The chunking parameters are recorded on every chunk. This test pins the values
so a silent change to a default is caught, because changing them without
bumping `CHUNKING_VERSION` would mix chunk shapes in one corpus.
"""

from __future__ import annotations

from app.services.chunking import (
    CHUNKING_METHOD,
    CHUNKING_VERSION,
    HARD_MAX_CHARS,
    OVERLAP_CHARS,
    TARGET_CHARS,
    ChunkingConfig,
)


def test_chunking_parameters_are_pinned() -> None:
    assert CHUNKING_METHOD == "paragraph-window"
    assert CHUNKING_VERSION == 1
    assert TARGET_CHARS == 900
    assert OVERLAP_CHARS == 150
    assert HARD_MAX_CHARS == 4000


def test_overlap_is_smaller_than_the_target() -> None:
    # Otherwise a window could step backwards and loop forever.
    assert OVERLAP_CHARS < TARGET_CHARS


def test_config_is_frozen() -> None:
    import dataclasses

    import pytest

    config = ChunkingConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.target_chars = 100  # type: ignore[misc]


def test_settings_reject_an_overlap_that_would_not_advance() -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(chunk_target_chars=900, chunk_overlap_chars=900)

    with pytest.raises(ValidationError):
        Settings(chunk_target_chars=10, chunk_overlap_chars=0)


def test_settings_accept_the_documented_defaults() -> None:
    from app.core.config import Settings

    settings = Settings()
    assert settings.chunk_target_chars == 900
    assert settings.chunk_overlap_chars == 150


def test_configured_values_are_what_the_indexer_uses() -> None:
    from app.core.config import Settings
    from app.services.chunking import ChunkingConfig

    settings = Settings(chunk_target_chars=700, chunk_overlap_chars=120)
    config = ChunkingConfig(
        target_chars=settings.chunk_target_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    assert config.to_json()["target_chars"] == 700
    assert config.to_json()["overlap_chars"] == 120
