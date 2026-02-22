"""
File content validation using magic bytes.
Rejects mislabeled or wrong-format files before processing.
"""

# Extension -> (magic_bytes_prefix, description)
MAGIC_BYTE_SIGNATURES: dict[str, tuple[bytes, str]] = {
    "pdf": (b"%PDF-", "PDF"),
    "png": (b"\x89PNG\r\n\x1a\n", "PNG"),
    "jpg": (b"\xff\xd8\xff", "JPEG"),
    "jpeg": (b"\xff\xd8\xff", "JPEG"),
}


def content_matches_extension(contents: bytes, extension: str) -> bool:
    """
    Return True if the first bytes of contents match the expected
    signature for the given file extension.
    """
    ext = extension.lower().strip()
    if ext not in MAGIC_BYTE_SIGNATURES:
        return True  # unknown extension, skip check
    signature, _ = MAGIC_BYTE_SIGNATURES[ext]
    return len(contents) >= len(signature) and contents[: len(signature)] == signature
