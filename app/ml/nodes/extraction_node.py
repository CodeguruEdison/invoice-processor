from pathlib import Path

import logging
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from app.core.config import settings
from app.ml.state import InvoiceState, PipelineStatus

logger = logging.getLogger(__name__)


"""
WHY LANGCHAIN HERE:
LangChain gives us three things we need:
1. ChatOllama    — connects to our local Ollama server
2. PromptTemplate — structures our prompt consistently
3. JsonOutputParser — parses LLM response into a Python dict

WHY A CHAIN (prompt | llm | parser):
This is LangChain's LCEL (LangChain Expression Language).
It pipes the output of one component into the next —
just like Unix pipes. Clean, readable, and easy to swap
individual components later.

prompt → formats our text into a message
llm    → sends it to Ollama and gets a response
parser → converts the response string into a Python dict
"""

# ── LLM Setup ─────────────────────────────────────────────
# We initialize the LLM once at module level.
# WHY: Creating a new LLM instance per request is expensive.
# Module-level initialization means it's created once
# when the app starts and reused for every invoice.

# temperature=0 means deterministic output —
# we want consistent, reliable extraction not creative responses.

# format="json" tells Ollama to always return valid JSON.
# Without this, the LLM might add extra text around the JSON
# which would break our parser.
llm = ChatOllama(
    model=settings.OLLAMA_MODEL,
    temperature=0,
    format="json",
    base_url=settings.OLLAMA_BASE_URL,
)

# ── Prompt Template ───────────────────────────────────────
# WHY A TEMPLATE:
# We need to inject the raw_text into the prompt dynamically
# for each invoice. ChatPromptTemplate handles this cleanly
# with {variable} placeholders.

# WHY SUCH A DETAILED PROMPT:
# LLMs perform much better with explicit instructions.
# We tell it exactly what fields to extract, what format
# to use, and what to return when a field is missing.
#
# Prompt can be overridden via EXTRACTION_PROMPT_FILE so you can tune
# for different invoice types without changing code.
DEFAULT_EXTRACTION_PROMPT = """
You are an expert invoice parser with years of experience
extracting structured data from invoices.

Extract the following fields from the invoice text below.
Return ONLY valid JSON with these exact keys.
If a field is not found, return null for that field.

{{
    "vendor_name": "string or null",
    "invoice_number": "string or null",
    "invoice_date": "YYYY-MM-DD format or null",
    "line_items": [
        {{
            "description": "string",
            "quantity": number,
            "unit_price": number,
            "total": number
        }}
    ],
    "subtotal": number or null,
    "tax_amount": number or null,
    "total_amount": number or null,
    "confidence_score": number between 0.0 and 1.0
}}

Field mapping (use these to find vendor_name):
- vendor_name: the seller or biller. Extract from any of: "Account Name", "Bill From", "Seller", "Vendor", "From", "Company Name", "Client" (when it means the billing party), "Name" in the header/from section, or the main business name at the top of the invoice. Use the exact name as shown (e.g. "Samira Hadid" if the text says "Account Name: Samira Hadid").

Important rules:
- confidence_score should reflect how complete the extraction is
- All amounts should be numbers not strings
- invoice_date must be in YYYY-MM-DD format
- Return empty list for line_items if none found

Invoice Text:
{raw_text}
"""


def _load_extraction_prompt() -> str:
    """Use prompt from EXTRACTION_PROMPT_FILE if set and file exists, else default."""
    prompt_file = settings.EXTRACTION_PROMPT_FILE
    if prompt_file:
        path = Path(prompt_file)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if "{raw_text}" in text:
                logger.info("Using extraction prompt from file: %s", path)
                return text
            logger.warning(
                "EXTRACTION_PROMPT_FILE %s does not contain {raw_text}, using default prompt",
                path,
            )
        else:
            logger.warning(
                "EXTRACTION_PROMPT_FILE %s not found, using default prompt",
                path,
            )
    return DEFAULT_EXTRACTION_PROMPT


prompt = ChatPromptTemplate.from_template(_load_extraction_prompt())

# ── Chain ─────────────────────────────────────────────────
# WHY PIPE OPERATOR:
# This chains prompt → llm → parser together.
# When we call chain.invoke() it runs all three in sequence.
parser = JsonOutputParser()
chain = prompt | llm | parser


def extraction_node(state: InvoiceState) -> InvoiceState:
    """
    WHY THIS NODE EXISTS:
    The OCR node gives us messy raw text like:
    'ACME Corp\nINV-001\nJan 15 2024\n$1,000.00'

    This node uses the LLM to understand that text and
    convert it into clean structured data like:
    {
        vendor_name: 'ACME Corp',
        invoice_number: 'INV-001',
        total_amount: 1000.00
    }

    WHY WE CHECK STATUS FIRST:
    If the OCR node failed, there is no point running
    extraction on empty text. We skip early to save time.
    """

    # ── Early Exit ────────────────────────────────────────
    # If a previous node already failed, skip this node.
    # This is a common pattern in LangGraph pipelines —
    # always check if it makes sense to continue.
    if state["status"] == PipelineStatus.FAILED:
        logger.warning("Skipping extraction — pipeline already failed")
        return state

    logger.info("Starting LLM extraction")

    try:
        # ── LLM Call ──────────────────────────────────────
        # chain.invoke() runs:
        # 1. prompt.invoke({"raw_text": ...}) → formats prompt
        # 2. llm.invoke(formatted_prompt)     → calls Ollama
        # 3. parser.invoke(llm_response)      → parses JSON
        result: dict = chain.invoke({"raw_text": state["raw_text"]})

        logger.info(
            f"Extraction complete. "
            f"Confidence: {result.get('confidence_score', 0)}"
        )

        # ── Update State ──────────────────────────────────
        # We spread the existing state and update only
        # the fields this node is responsible for.
        return {
            **state,
            "vendor_name": result.get("vendor_name"),
            "invoice_number": result.get("invoice_number"),
            "invoice_date": result.get("invoice_date"),
            "line_items": result.get("line_items", []),
            "subtotal": result.get("subtotal"),
            "tax_amount": result.get("tax_amount"),
            "total_amount": result.get("total_amount"),
            "confidence_score": result.get("confidence_score", 0.0),
            "status": PipelineStatus.EXTRACTED,
        }

    except Exception as e:
        # ── Error Handling ────────────────────────────────
        # WHY WE DON'T RAISE:
        # In a pipeline, we want to handle errors gracefully
        # and let the validation node decide what to do next.
        # Raising an exception would crash the entire pipeline.
        logger.error(f"Extraction failed: {e}")
        return {
            **state,
            "status": PipelineStatus.FAILED,
            "validation_errors": [f"Extraction failed: {str(e)}"],
        }
