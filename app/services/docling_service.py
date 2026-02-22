"""
Docling-based document text extraction.

Uses https://docling-project.github.io/docling/ for PDF and image parsing
with layout awareness and optional OCR. Injected via dependency injection
so it can be swapped or mocked in tests.
"""

import logging
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class IDoclingService(Protocol):
    """Protocol for Docling-backed OCR; allows swapping implementation or mocks."""

    def extract_text(self, file_path: str) -> str:
        """Extract plain text from a document (PDF or image). Returns empty string on failure."""
        ...


class DoclingService:
    """
    Service that uses Docling to convert documents to text.

    Handles PDFs and images with layout parsing and OCR when needed.
    """

    def __init__(self) -> None:
        self._converter = self._create_converter()

    def _create_converter(self):
        try:
            from docling.document_converter import DocumentConverter

            return DocumentConverter()
        except Exception as e:
            logger.warning("Docling DocumentConverter not available: %s", e)
            return None

    def extract_text(self, file_path: str) -> str:
        """
        Extract text from a document (PDF or image) using Docling.

        Returns extracted text or empty string if conversion fails or
        Docling is not available.
        """
        logger.info("Docling extract_text called for: %s", file_path)

        if self._converter is None:
            logger.warning("Docling not available (converter None), skipping")
            return ""

        path = Path(file_path)
        if not path.exists():
            logger.warning("Docling: file not found: %s", file_path)
            return ""

        try:
            result = self._converter.convert(str(path))
            if result.document is None:
                logger.warning("Docling returned no document for: %s", file_path)
                return ""

            text = (result.document.export_to_markdown() or "").strip()
            # Log what Docling returned (length + preview) — always visible
            preview_len = 500
            preview = text[:preview_len] + ("..." if len(text) > preview_len else "")
            logger.info(
                "Docling result for %s: length=%d chars, preview=%s",
                file_path,
                len(text),
                repr(preview),
            )
            if logger.isEnabledFor(logging.DEBUG) and text:
                logger.debug("Docling full markdown: %s", text)
            return text
        except Exception as e:
            logger.warning("Docling conversion failed for %s: %s", file_path, e)
            return ""
