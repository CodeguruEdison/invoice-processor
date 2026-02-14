import pdfplumber
import pytesseract
from PIL import Image
from app.ml.state import InvoiceState, PipelineStatus
import logging

logger = logging.getLogger(__name__)

def ocr_node(state: InvoiceState) -> InvoiceState:
    file_path = state['file_path']
    logger.info(f"Processing OCR for file: {file_path}")
    try:
       if file_path.endswith('.pdf'):
            with pdfplumber.open(file_path) as pdf:
                raw_text = "\n".join(
                        page.extract_text() or ""
                        for page in pdf.pages)

       else:
            image = Image.open(file_path)
            raw_text = pytesseract.image_to_string(image)

       if not raw_text.strip():
           logger.error(f"No text extracted from: {file_path}")
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
        logger.error(f"OCR failed for {file_path}: {e}")
        return {
            **state,
            "raw_text": "",
            "status": PipelineStatus.FAILED,
            "validation_errors": [f"OCR failed: {str(e)}"],
        }


