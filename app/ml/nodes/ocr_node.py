import base64
import io
import logging
from typing import TYPE_CHECKING

import fitz  # pymupdf
import pdfplumber
import pytesseract
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from PIL import Image

from app.core.config import settings
from app.ml.state import InvoiceState, PipelineStatus

if TYPE_CHECKING:
    from app.services.docling_service import DoclingService

logger = logging.getLogger(__name__)

VISION_OCR_PROMPT = (
    "Transcribe all text from this document image exactly as it appears. "
    "Preserve layout, numbers, and structure. Output only the transcribed text, "
    "no commentary or explanation."
)


def _ocr_single_image_with_vision_llm(pil_image: Image.Image) -> str:
    """
    Run OCR on a single image using an Ollama vision model (e.g. LLaVA, Llama 3.2 Vision).
    Returns extracted text or empty string on failure.
    """
    buffered = io.BytesIO()
    pil_image.save(buffered, format="JPEG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    content_parts: list[dict] = [
        {"type": "image_url", "image_url": f"data:image/jpeg;base64,{img_b64}"},
        {"type": "text", "text": VISION_OCR_PROMPT},
    ]
    msg = HumanMessage(content=content_parts)
    llm = ChatOllama(
        model=settings.OLLAMA_VISION_MODEL,
        temperature=0,
        base_url=settings.OLLAMA_BASE_URL,
    )
    response = llm.invoke([msg])
    text = (response.content or "").strip()
    return text


def _ocr_pdf_pages_with_vision_llm(file_path: str) -> str:
    """OCR PDF by rendering each page and running vision LLM on each image."""
    parts: list[str] = []
    doc = fitz.open(file_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(
                dpi=200,
                alpha=False,
                colorspace=fitz.csRGB,
            )
            img = _pil_from_pixmap(pix)
            text = _ocr_single_image_with_vision_llm(img)
            if text:
                parts.append(text)
    finally:
        doc.close()
    return "\n\n".join(parts) if parts else ""


def _pil_from_pixmap(pix: "fitz.Pixmap") -> Image.Image:
    """Convert pymupdf Pixmap to PIL Image (RGB)."""
    if pix.n == 4:
        # RGBA: drop alpha for RGB
        img = Image.frombytes(
            "RGBA",
            (pix.width, pix.height),
            pix.samples,
        )
        return img.convert("RGB")
    if pix.n == 3:
        return Image.frombytes(
            "RGB",
            (pix.width, pix.height),
            pix.samples,
        )
    # Grayscale or other
    img = Image.frombytes(
        "L" if pix.n == 1 else "RGB",
        (pix.width, pix.height),
        pix.samples,
    )
    return img.convert("RGB") if img.mode != "RGB" else img


def _preprocess_for_ocr(pil_image: Image.Image) -> Image.Image:
    """Convert to grayscale and optionally resize for better Tesseract results."""
    img = pil_image.convert("L")  # Grayscale often improves OCR
    return img


def _ocr_pdf_pages_as_images(file_path: str) -> str:
    """
    Fallback for image-based PDFs: render each page to an image
    and run pytesseract. Used when pdfplumber extracts no text.
    """
    parts: list[str] = []
    doc = fitz.open(file_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(
                dpi=200,
                alpha=False,
                colorspace=fitz.csRGB,
            )
            img = _pil_from_pixmap(pix)
            img = _preprocess_for_ocr(img)
            # PSM 3 = fully automatic page segmentation (works well for invoices)
            text = pytesseract.image_to_string(
                img,
                config="--psm 3",
            )
            if text.strip():
                parts.append(text.strip())
    finally:
        doc.close()
    return "\n\n".join(parts) if parts else ""


def ocr_node(
    state: InvoiceState,
    docling_service: "DoclingService | None" = None,
) -> InvoiceState:
    file_path = state["file_path"]
    logger.info("Processing OCR for file: %s", file_path)
    try:
        raw_text = ""

        # Prefer Docling when enabled and service is injected (dependency injection)
        use_docling = (
            settings.OCR_USE_DOCLING
            and docling_service is not None
            and file_path.endswith((".pdf", ".png", ".jpg", ".jpeg"))
        )
        if use_docling:
            logger.info(
                "Using Docling for OCR: %s (OCR_USE_DOCLING=%s)",
                file_path,
                settings.OCR_USE_DOCLING,
            )
            raw_text = docling_service.extract_text(file_path)
            if raw_text:
                logger.info(
                    "Docling extracted %d characters from %s",
                    len(raw_text),
                    file_path,
                )
        else:
            logger.info(
                "Docling skipped: OCR_USE_DOCLING=%s, service_injected=%s, path=%s",
                settings.OCR_USE_DOCLING,
                docling_service is not None,
                file_path,
            )

        if not raw_text.strip():
            if file_path.endswith(".pdf"):
                with pdfplumber.open(file_path) as pdf:
                    raw_text = "\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
                if not raw_text.strip():
                    use_vision = (
                        settings.OCR_USE_VISION_LLM
                        and settings.OLLAMA_VISION_MODEL
                    )
                    logger.info(
                        "No text layer in PDF, using %s for OCR: %s",
                        f"vision LLM ({settings.OLLAMA_VISION_MODEL})"
                        if use_vision
                        else "Tesseract",
                        file_path,
                    )
                    if use_vision:
                        raw_text = _ocr_pdf_pages_with_vision_llm(file_path)
                    else:
                        raw_text = _ocr_pdf_pages_as_images(file_path)
            else:
                image = Image.open(file_path).convert("RGB")
                use_vision = (
                    settings.OCR_USE_VISION_LLM
                    and settings.OLLAMA_VISION_MODEL
                )
                logger.info(
                    "Image upload, using %s for OCR",
                    f"vision LLM ({settings.OLLAMA_VISION_MODEL})"
                    if use_vision
                    else "Tesseract",
                )
                if use_vision:
                    raw_text = _ocr_single_image_with_vision_llm(image)
                else:
                    image = _preprocess_for_ocr(image)
                    raw_text = pytesseract.image_to_string(
                        image,
                        config="--psm 3",
                    )

        if not raw_text.strip():
            logger.error(
                "No text extracted from %s. Tip: install Tesseract "
                "(brew install tesseract) or use vision LLM (OCR_USE_VISION_LLM=true, "
                "OLLAMA_VISION_MODEL=llava:7b)",
                file_path,
            )
            return {
                **state,
                "raw_text": "",
                "status": PipelineStatus.FAILED,
                "validation_errors": ["No text could be extracted from file"],
            }

        logger.info(f"OCR successful, extracted {len(raw_text)} characters")

        return {
            **state,
            "raw_text": raw_text.strip(),
        }

    except Exception as e:
        logger.error("OCR failed for %s: %s", file_path, e)
        return {
            **state,
            "raw_text": "",
            "status": PipelineStatus.FAILED,
            "validation_errors": [f"OCR failed: {str(e)}"],
        }


def make_ocr_node(docling_service: "DoclingService | None" = None):
    """Return an OCR node with optional DoclingService injected (for dependency injection)."""
    return lambda state: ocr_node(state, docling_service)


