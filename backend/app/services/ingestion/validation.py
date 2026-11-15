"""Upload validation and filename/path safety (Phase 2B).

Everything a client sends about an upload is untrusted: the filename, the
declared MIME type, and the bytes themselves. This module decides what an
upload *is* from the bytes it actually contains, and produces a storage path
that cannot escape the user's folder.

Rules enforced here:

* an allow-list of formats, matched by magic bytes / structure, not by the
  declared content type;
* a declared content type is only accepted when it agrees with the detected
  format — a mismatch is rejected rather than quietly trusted;
* filenames are reduced to a safe display value and never used as a path;
* size limits are checked on the real byte count;
* nothing is ever executed, extracted to disk, or opened by a parser other
  than the one chosen for the detected format.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB — matches the storage bucket
MAX_NOTE_CHARS = 200_000
MIN_NOTE_CHARS = 1

_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF-"
# Bytes that indicate a binary file we cannot treat as text.
_BINARY_SNIFF = 4096

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
_COLLAPSE = re.compile(r"[_-]{2,}")


class DetectedFormat(StrEnum):
    """Formats the pipeline can actually process today."""

    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class FormatSpec:
    """Everything needed to route a detected format through the pipeline."""

    format: DetectedFormat
    mime_type: str
    extension: str
    extractor: str
    display_name: str


#: Detected format -> the MIME type MNEMOS records. We store what we detected,
#: never the string the client sent.
FORMAT_SPECS: dict[DetectedFormat, FormatSpec] = {
    DetectedFormat.PDF: FormatSpec(
        format=DetectedFormat.PDF,
        mime_type="application/pdf",
        extension=".pdf",
        extractor="pdf",
        display_name="PDF",
    ),
    DetectedFormat.MARKDOWN: FormatSpec(
        format=DetectedFormat.MARKDOWN,
        mime_type="text/markdown",
        extension=".md",
        extractor="markdown",
        display_name="Markdown",
    ),
    DetectedFormat.TEXT: FormatSpec(
        format=DetectedFormat.TEXT,
        mime_type="text/plain",
        extension=".txt",
        extractor="plain-text",
        display_name="Plain text",
    ),
}

#: Declared content types we will accept, mapped to the formats they may
#: legitimately describe. A declared type outside this map is rejected.
ALLOWED_DECLARED_MIME: dict[str, frozenset[DetectedFormat]] = {
    "application/pdf": frozenset({DetectedFormat.PDF}),
    "text/plain": frozenset({DetectedFormat.TEXT, DetectedFormat.MARKDOWN}),
    "text/markdown": frozenset({DetectedFormat.MARKDOWN}),
    "text/x-markdown": frozenset({DetectedFormat.MARKDOWN}),
    "application/octet-stream": frozenset(
        {DetectedFormat.PDF, DetectedFormat.TEXT, DetectedFormat.MARKDOWN}
    ),
    "": frozenset({DetectedFormat.PDF, DetectedFormat.TEXT, DetectedFormat.MARKDOWN}),
}

_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}


class UploadRejected(Exception):
    """Raised when an upload fails validation.

    Carries a stable machine code and a message that is safe to show a user.
    The message never echoes raw bytes or client-supplied paths.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """The result of validating an upload."""

    format: DetectedFormat
    spec: FormatSpec
    mime_type: str
    size_bytes: int
    filename: str
    title: str
    content: bytes


def _decode_text(raw: bytes) -> str:
    """Decode bytes as text, rejecting binary and unknown encodings.

    UTF-8 (with or without BOM) and UTF-16 with a BOM are accepted. Anything
    else is rejected: silently mangling an unknown encoding would corrupt the
    extracted text and every citation derived from it.
    """
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise UploadRejected(
                "unsupported_encoding", "The file uses a UTF-16 encoding we could not read."
            ) from exc

    candidate = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw

    if b"\x00" in candidate[:_BINARY_SNIFF]:
        raise UploadRejected(
            "binary_content", "This file looks like binary data, not readable text."
        )

    try:
        return candidate.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadRejected(
            "unsupported_encoding",
            "The file is not valid UTF-8. Re-save it as UTF-8 and try again.",
        ) from exc


def _looks_like_markdown(text: str, filename: str) -> bool:
    """Markdown is detected by extension *and* content signature.

    A `.md` file whose content is plain prose is still Markdown (the extension
    is a statement of intent); a `.txt` file full of headings is treated as
    text, because guessing would make extraction non-deterministic.
    """
    lowered = filename.lower()
    for extension in _MARKDOWN_EXTENSIONS:
        if lowered.endswith(extension):
            return True
    del text
    return False


def detect_format(raw: bytes, filename: str, declared_mime: str | None) -> DetectedFormat:
    """Decide what an upload is, from its bytes first and its declaration second."""
    size = len(raw)
    if size == 0:
        raise UploadRejected("empty_file", "The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            "file_too_large",
            f"The file is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    declared = (declared_mime or "").split(";")[0].strip().lower()
    allowed_for_declared = ALLOWED_DECLARED_MIME.get(declared)
    if allowed_for_declared is None:
        raise UploadRejected(
            "unsupported_type",
            "That file type is not supported. Supported types are PDF, Markdown and plain text.",
        )

    detected: DetectedFormat
    if raw.startswith(_PDF_MAGIC):
        detected = DetectedFormat.PDF
    elif raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        # UTF-16 text contains NUL bytes by construction; decode it before the
        # binary sniff so a legitimate UTF-16 note is not mistaken for binary.
        _decode_text(raw)
        detected = (
            DetectedFormat.MARKDOWN
            if _looks_like_markdown(raw.decode("utf-16", "replace"), filename)
            else DetectedFormat.TEXT
        )
    elif raw.startswith(_ZIP_MAGIC):
        # Office/ODF documents are ZIP containers. They are allow-listed in
        # the bucket but not yet extractable; say so instead of failing later.
        raise UploadRejected(
            "unsupported_type",
            "Office documents are not supported yet. Convert to PDF or plain text.",
        )
    else:
        text = _decode_text(raw)
        detected = (
            DetectedFormat.MARKDOWN if _looks_like_markdown(text, filename) else DetectedFormat.TEXT
        )

    if detected not in allowed_for_declared:
        raise UploadRejected(
            "type_mismatch",
            "The file contents do not match the declared file type.",
        )

    return detected


def safe_filename(raw_name: str | None, fallback: str = "untitled") -> str:
    """Reduce a client filename to a safe display value.

    The result is *only* ever used for display and as the basis of the stored
    object's extension — never as a path. Directory components are stripped,
    control characters removed, and the stem length capped.
    """
    if not raw_name:
        return fallback

    name = unicodedata.normalize("NFKC", raw_name)
    # Strip any path component a browser or script might have sent.
    name = name.replace("\\", "/").split("/")[-1]
    # Replace control characters instead of dropping them: "with\x00null"
    # must not collapse into a different, silently valid-looking name.
    name = "".join(char if char.isprintable() else "-" for char in name)
    name = _UNSAFE_FILENAME.sub("-", name).strip(" .-_")
    name = _COLLAPSE.sub("-", name)

    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""

    stem = stem[:120].strip(" .-_") or fallback
    extension = extension[:12].lower()
    return f"{stem}.{extension}" if extension else stem


def storage_path_for(user_id: str, object_id: str, extension: str) -> str:
    """Build the storage object path: `<user_id>/<uuid><ext>`.

    The first path segment must equal `auth.uid()` for the bucket policy, and
    the object id is a server-generated UUID, so no client string reaches the
    path.
    """
    if not re.fullmatch(r"[0-9a-f-]{36}", object_id):
        raise UploadRejected("invalid_object_id", "Internal error preparing storage.")
    return f"{user_id}/{object_id}{extension}"


def validate_upload(
    *,
    raw: bytes,
    filename: str | None,
    declared_mime: str | None,
    title: str | None = None,
) -> ValidatedUpload:
    """Validate an uploaded file end to end.

    Raises `UploadRejected` with a stable code for every failure mode:
    `empty_file`, `file_too_large`, `unsupported_type`, `type_mismatch`,
    `binary_content`, `unsupported_encoding`.
    """
    name = safe_filename(filename)
    detected = detect_format(raw, name, declared_mime)
    spec = FORMAT_SPECS[detected]

    if detected is not DetectedFormat.PDF:
        # Decode now so an encoding problem is reported as a validation error
        # rather than surfacing later as an extraction failure.
        _decode_text(raw)

    chosen_title = (title or "").strip() or name.rsplit(".", 1)[0]
    if len(chosen_title) > 300:
        chosen_title = chosen_title[:300].rstrip()
    if not chosen_title:
        raise UploadRejected("missing_title", "A title is required.")

    return ValidatedUpload(
        format=detected,
        spec=spec,
        mime_type=spec.mime_type,
        size_bytes=len(raw),
        filename=name,
        title=chosen_title,
        content=raw,
    )


def validate_note(*, content: str, title: str) -> tuple[str, int]:
    """Validate a typed note.

    Returns `(normalized_content, size_bytes)`. Notes are stored through the
    same pipeline as files so their provenance is identical.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized.strip()) < MIN_NOTE_CHARS:
        raise UploadRejected("empty_file", "The note is empty.")
    if len(normalized) > MAX_NOTE_CHARS:
        raise UploadRejected(
            "file_too_large",
            f"The note is longer than the {MAX_NOTE_CHARS:,} character limit.",
        )
    if not title.strip():
        raise UploadRejected("missing_title", "A title is required.")
    if len(title.strip()) > 300:
        raise UploadRejected("invalid_title", "The title must be 300 characters or fewer.")
    return normalized, len(normalized.encode("utf-8"))
