"""Validation and filename-safety tests (Phase 2B).

These are the "trust nothing the client sent" tests: declared types, filenames,
encodings and binary payloads.
"""

from __future__ import annotations

import pytest

from app.services.ingestion.validation import (
    MAX_NOTE_CHARS,
    MAX_UPLOAD_BYTES,
    DetectedFormat,
    UploadRejected,
    detect_format,
    safe_filename,
    storage_path_for,
    validate_note,
    validate_upload,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def test_text_upload_detected_as_text() -> None:
    result = validate_upload(
        raw=b"Just some prose.", filename="notes.txt", declared_mime="text/plain", title=None
    )
    assert result.format is DetectedFormat.TEXT
    assert result.mime_type == "text/plain"
    assert result.title == "notes"


def test_markdown_detected_by_extension() -> None:
    result = validate_upload(
        raw=b"# Heading\n\nBody.", filename="doc.md", declared_mime="text/markdown"
    )
    assert result.format is DetectedFormat.MARKDOWN


def test_markdown_declared_as_plain_text_is_accepted() -> None:
    result = validate_upload(raw=b"# Heading", filename="doc.md", declared_mime="text/plain")
    assert result.format is DetectedFormat.MARKDOWN


def test_pdf_detected_by_magic_bytes() -> None:
    result = validate_upload(raw=PDF_BYTES, filename="paper.bin", declared_mime="application/pdf")
    assert result.format is DetectedFormat.PDF
    assert result.mime_type == "application/pdf"


def test_client_cannot_lie_about_pdf() -> None:
    """Declaring a text file as a PDF is a mismatch, not a PDF."""
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=b"plain text", filename="x.pdf", declared_mime="application/pdf")
    assert error.value.code == "type_mismatch"


def test_client_cannot_lie_about_text() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=PDF_BYTES, filename="x.txt", declared_mime="text/plain")
    assert error.value.code == "type_mismatch"


@pytest.mark.parametrize(
    "mime",
    [
        "application/zip",
        "image/png",
        "application/msword",
        "text/html",
        "application/x-msdownload",
    ],
)
def test_disallowed_declared_types_rejected(mime: str) -> None:
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=b"data", filename="x.dat", declared_mime=mime)
    assert error.value.code == "unsupported_type"


def test_office_document_rejected_with_actionable_message() -> None:
    """A ZIP container is recognised and refused honestly, not misparsed."""
    with pytest.raises(UploadRejected) as error:
        validate_upload(
            raw=b"PK\x03\x04rest-of-zip",
            filename="report.docx",
            declared_mime="application/octet-stream",
        )
    assert error.value.code == "unsupported_type"
    assert "PDF" in error.value.message


def test_empty_file_rejected() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=b"", filename="empty.txt", declared_mime="text/plain")
    assert error.value.code == "empty_file"


def test_oversized_file_rejected() -> None:
    oversized = b"a" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=oversized, filename="big.txt", declared_mime="text/plain")
    assert error.value.code == "file_too_large"


def test_binary_content_rejected() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=b"\x00\x01\x02binary", filename="weird.txt", declared_mime="text/plain")
    assert error.value.code == "binary_content"


def test_non_utf8_encoding_rejected() -> None:
    latin1 = "café".encode("latin-1")
    with pytest.raises(UploadRejected) as error:
        validate_upload(raw=latin1, filename="x.txt", declared_mime="text/plain")
    assert error.value.code == "unsupported_encoding"


def test_utf8_bom_accepted() -> None:
    result = validate_upload(raw=b"\xef\xbb\xbfHello", filename="x.txt", declared_mime="text/plain")
    assert result.format is DetectedFormat.TEXT


def test_utf16_with_bom_accepted() -> None:
    """UTF-16 contains NUL bytes; it must be decoded, not rejected as binary."""
    result = validate_upload(
        raw="hello".encode("utf-16"), filename="x.txt", declared_mime="text/plain"
    )
    assert result.format is DetectedFormat.TEXT


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("/absolute/path/file.txt", "file.txt"),
        ("normal-file.txt", "normal-file.txt"),
        ("with\x00null.txt", "with-null.txt"),
        ("  spaced  .txt  ", "spaced.txt"),
        ("", "untitled"),
        (None, "untitled"),
        ("....", "untitled"),
    ],
)
def test_safe_filename_strips_paths_and_control_chars(raw_name: str | None, expected: str) -> None:
    assert safe_filename(raw_name) == expected


def test_safe_filename_caps_length() -> None:
    long_name = "a" * 400 + ".txt"
    result = safe_filename(long_name)
    assert len(result) <= 132
    assert result.endswith(".txt")


def test_storage_path_is_user_scoped_and_server_named() -> None:
    user = "11111111-1111-4111-8111-111111111111"
    path = storage_path_for(user, "22222222-2222-4222-8222-222222222222", ".txt")
    assert path == f"{user}/22222222-2222-4222-8222-222222222222.txt"
    assert path.split("/")[0] == user


def test_storage_path_rejects_non_uuid_object_id() -> None:
    with pytest.raises(UploadRejected):
        storage_path_for("11111111-1111-4111-8111-111111111111", "../../evil", ".txt")


def test_title_falls_back_to_filename_stem() -> None:
    result = validate_upload(
        raw=b"content", filename="Quarterly Report.txt", declared_mime="text/plain"
    )
    assert result.title == "Quarterly Report"


def test_explicit_title_wins() -> None:
    result = validate_upload(
        raw=b"content", filename="a.txt", declared_mime="text/plain", title="  My title  "
    )
    assert result.title == "My title"


def test_detect_format_is_content_first() -> None:
    """A PDF named .txt is detected as a PDF and then rejected as a mismatch."""
    with pytest.raises(UploadRejected) as error:
        detect_format(PDF_BYTES, "not-really.txt", "text/plain")
    assert error.value.code == "type_mismatch"


# --- notes ---------------------------------------------------------------


def test_note_normalizes_newlines() -> None:
    content, size = validate_note(content="line1\r\nline2\rline3", title="Note")
    assert content == "line1\nline2\nline3"
    assert size == len(content.encode("utf-8"))


def test_empty_note_rejected() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_note(content="   \n  ", title="Note")
    assert error.value.code == "empty_file"


def test_note_over_limit_rejected() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_note(content="x" * (MAX_NOTE_CHARS + 1), title="Note")
    assert error.value.code == "file_too_large"


def test_note_without_title_rejected() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_note(content="content", title="   ")
    assert error.value.code == "missing_title"


def test_note_title_over_300_chars_rejected() -> None:
    with pytest.raises(UploadRejected) as error:
        validate_note(content="content", title="t" * 301)
    assert error.value.code == "invalid_title"
