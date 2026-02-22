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

Line items (required when the invoice has an itemized list or table):
- line_items: list of rows from the invoice table/section. Look for: a table with columns like "Description", "Item", "Qty", "Quantity", "Unit Price", "Rate", "Amount", "Total", "Line Total"; or itemized rows with description and price. Extract EVERY row as an object with "description" (string), "quantity" (number), "unit_price" (number), "total" (number). Use 1 for quantity if not stated. If the invoice has no itemized lines at all, return [].

Important rules:
- confidence_score should reflect how complete the extraction is
- All amounts should be numbers not strings
- invoice_date must be in YYYY-MM-DD format
- Return empty list for line_items ONLY when there are no itemized lines; when there is a table or list of items, extract every row

Invoice Text:
{raw_text}
"""


def _normalize_line_items(value: object) -> list[dict]:
    """Ensure line_items is a list of dicts with description, quantity, unit_price, total."""
    if value is None:
        return []
    if isinstance(value, list):
        out: list[dict] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            # Accept common LLM variants: "amount" -> "total", etc.
            total_val = item.get("total") if item.get("total") is not None else item.get("amount")
            try:
                total = float(total_val) if total_val is not None else 0.0
            except (TypeError, ValueError):
                total = 0.0
            qty = _num(item.get("quantity") or item.get("qty"), 1)
            unit = _num(item.get("unit_price") or item.get("rate") or item.get("price"), 0.0)
            out.append({
                "description": str(item.get("description") or item.get("item") or "").strip() or "",
                "quantity": qty,
                "unit_price": unit,
                "total": total,
            })
        return _fix_line_item_math(out)
    return []


def _fix_line_item_math(items: list[dict]) -> list[dict]:
    """
    Fix line items where LLM left unit_price or total as 0.
    Infer total = quantity * unit_price or unit_price = total / quantity when possible.
    """
    result: list[dict] = []
    for it in items:
        qty, unit, total = it["quantity"], it["unit_price"], it["total"]
        if qty <= 0:
            result.append(it)
            continue
        # Fix missing/zero total from quantity and unit_price
        if (total is None or total == 0.0) and unit and unit > 0:
            total = round(qty * unit, 2)
        # Fix missing/zero unit_price from total and quantity
        if (unit is None or unit == 0.0) and total and total > 0:
            unit = round(total / qty, 2) if qty else 0.0
        result.append({
            "description": it["description"],
            "quantity": qty,
            "unit_price": unit,
            "total": total,
        })
    return result


def _fix_line_items_with_subtotal(
    items: list[dict], subtotal: float | None
) -> list[dict]:
    """
    When subtotal is known and line item totals don't match (e.g. LLM copied
    previous row's values into the last row), fix the last line so its total
    = subtotal - sum(others), then set unit_price = total / quantity.
    """
    if not items or subtotal is None:
        return items
    try:
        sub = float(subtotal)
    except (TypeError, ValueError):
        return items
    line_total = sum(it["total"] for it in items)
    if abs(line_total - sub) < 0.02:
        return items
    # Fix last line: total = subtotal - sum(rest)
    rest_total = sum(it["total"] for it in items[:-1])
    correct_last_total = round(sub - rest_total, 2)
    if correct_last_total < 0:
        return items
    last = items[-1].copy()
    qty = last["quantity"]
    last["total"] = correct_last_total
    last["unit_price"] = round(correct_last_total / qty, 2) if qty else 0.0
    return items[:-1] + [last]


def _num(val: object, default: float) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


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

        line_items = _normalize_line_items(result.get("line_items"))
        line_items = _fix_line_items_with_subtotal(
            line_items, result.get("subtotal")
        )
        logger.info(
            "Extraction complete. Confidence: %s, line_items: %d",
            result.get("confidence_score", 0),
            len(line_items),
        )

        # ── Update State ──────────────────────────────────
        # We spread the existing state and update only
        # the fields this node is responsible for.
        return {
            **state,
            "vendor_name": result.get("vendor_name"),
            "invoice_number": result.get("invoice_number"),
            "invoice_date": result.get("invoice_date"),
            "line_items": line_items,
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
