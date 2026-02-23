"""Unit tests for file content validation."""

from app.core.file_validation import content_matches_extension, MAGIC_BYTE_SIGNATURES


def test_content_matches_extension_pdf_valid() -> None:
    assert content_matches_extension(b"%PDF-1.4 rest of file", "pdf") is True
    assert content_matches_extension(b"%PDF-", "pdf") is True


def test_content_matches_extension_pdf_invalid() -> None:
    assert content_matches_extension(b"not a pdf", "pdf") is False
    assert content_matches_extension(b"", "pdf") is False
    assert content_matches_extension(b"PD", "pdf") is False


def test_content_matches_extension_png_valid() -> None:
    sig = MAGIC_BYTE_SIGNATURES["png"][0]
    assert content_matches_extension(sig + b"more", "png") is True


def test_content_matches_extension_png_invalid() -> None:
    assert content_matches_extension(b"\x89PNG", "png") is False  # too short
    assert content_matches_extension(b"XXXXXXXX", "png") is False


def test_content_matches_extension_jpeg_valid() -> None:
    assert content_matches_extension(b"\xff\xd8\xff\xe0\x00\x10", "jpg") is True
    assert content_matches_extension(b"\xff\xd8\xff", "jpeg") is True


def test_content_matches_extension_jpeg_invalid() -> None:
    assert content_matches_extension(b"\xff\xd8", "jpg") is False
    assert content_matches_extension(b"not jpeg", "jpg") is False


def test_content_matches_extension_unknown_extension_returns_true() -> None:
    """Unknown extensions skip magic-byte check (caller validates extension)."""
    assert content_matches_extension(b"anything", "xyz") is True
