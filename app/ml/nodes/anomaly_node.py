from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.ml.state import InvoiceState, PipelineStatus
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


"""
WHY THIS NODE EXISTS:
Validation checks math and required fields — things a
simple rule can verify. But some fraud patterns are
more subtle:

- A vendor name that looks slightly off ('Micros0ft' vs 'Microsoft')
- An invoice date on a weekend or holiday
- Round numbers that are suspiciously convenient ($10,000.00 exactly)
- Line item descriptions that are vague or nonsensical
- Amounts that are just below approval thresholds

These patterns require REASONING not just rules.
That is why we use the LLM here instead of Python code.

WHY THIS IS A SEPARATE NODE FROM EXTRACTION:
Single Responsibility Principle — extraction finds data,
anomaly detection judges it. Mixing them would make
both harder to test and maintain.
"""

# ── LLM Setup ─────────────────────────────────────────────
# Same LLM as extraction node.
# WHY MODULE LEVEL AGAIN:
# Each node file is independent. We don't share the LLM
# instance between files because it would create tight
# coupling between nodes. The small overhead of two
# instances is worth the cleaner architecture.
llm = ChatOllama(
    model=settings.OLLAMA_MODEL,
    temperature=0,
    format="json",
    base_url=settings.OLLAMA_BASE_URL,
)

# ── Prompt Template ───────────────────────────────────────
# WHY SO SPECIFIC IN THE PROMPT:
# The more specific we are about what to look for,
# the better the LLM performs. Vague prompts give
# vague results. We give it a checklist to work through.
prompt = ChatPromptTemplate.from_template("""
You are a senior financial fraud analyst with 20 years
of experience detecting invoice fraud and anomalies.

Carefully analyze this invoice data and identify ANY
suspicious patterns or anomalies.

Invoice Data:
- Vendor Name: {vendor_name}
- Invoice Number: {invoice_number}
- Invoice Date: {invoice_date}
- Subtotal: {subtotal}
- Tax Amount: {tax_amount}
- Total Amount: {total_amount}
- Line Items: {line_items}

Check specifically for:
1. Suspiciously round numbers (e.g. exactly $10,000.00)
2. Vague or generic line item descriptions
3. Invoice dates on weekends or public holidays
4. Vendor names that look misspelled or suspicious
5. Amounts just below common approval thresholds
   (e.g. $9,999 when threshold is $10,000)
6. Missing or duplicate invoice numbers
7. Tax amounts that seem incorrect for the region
8. Line items with unusually high unit prices

Return ONLY valid JSON:
{{
    "anomalies": [
        "clear description of each anomaly found"
    ],
    "risk_score": number between 0.0 and 1.0,
    "risk_level": "low" or "medium" or "high"
}}

If no anomalies found return empty list for anomalies,
0.0 for risk_score and "low" for risk_level.
""")

parser = JsonOutputParser()
chain = prompt | llm | parser


def anomaly_node(state: InvoiceState) -> InvoiceState:
    """
    WHY WE CHECK STATUS FIRST:
    We only run anomaly detection on successfully
    validated invoices. Running it on failed invoices
    would waste LLM resources and give meaningless results
    since the data itself is unreliable.
    """

    # ── Early Exit ────────────────────────────────────────
    if state["status"] == PipelineStatus.FAILED:
        logger.warning("Skipping anomaly detection — pipeline failed")
        return state

    if state["status"] != PipelineStatus.VALIDATED:
        logger.warning("Skipping anomaly detection — not yet validated")
        return state

    logger.info("Starting anomaly detection")

    try:
        # ── LLM Call ──────────────────────────────────────
        # We pass all the structured fields individually
        # rather than the raw text.
        # WHY: The LLM performs better when analyzing
        # clean structured data vs messy raw text.
        result: dict = chain.invoke({
            "vendor_name": state.get("vendor_name", "Unknown"),
            "invoice_number": state.get("invoice_number", "Unknown"),
            "invoice_date": state.get("invoice_date", "Unknown"),
            "subtotal": state.get("subtotal", 0),
            "tax_amount": state.get("tax_amount", 0),
            "total_amount": state.get("total_amount", 0),
            "line_items": state.get("line_items", []),
        })

        anomalies: list[str] = result.get("anomalies", [])
        risk_score: float = result.get("risk_score", 0.0)
        risk_level: str = result.get("risk_level", "low")

        # ── Determine Final Status ────────────────────────
        # WHY TWO DIFFERENT STATUSES:
        # ANOMALY_FLAGGED means the invoice needs human review
        # COMPLETED means it passed all checks automatically
        # This lets the business decide what to do with each.
        if anomalies:
            final_status = PipelineStatus.ANOMALY_FLAGGED
            logger.warning(
                f"Anomalies detected: {len(anomalies)} "
                f"risk_level={risk_level} "
                f"risk_score={risk_score}"
            )
        else:
            final_status = PipelineStatus.COMPLETED
            logger.info("No anomalies detected — invoice completed")

        return {
            **state,
            "anomaly_flags": anomalies,
            "status": final_status,
        }

    except Exception as e:
        # ── Graceful Degradation ──────────────────────────
        # WHY WE DON'T FAIL HERE:
        # Anomaly detection is a bonus check — if it fails
        # we don't want to fail the entire invoice.
        # We mark it as completed and log the error.
        # The invoice data itself is still valid.
        logger.error(f"Anomaly detection failed: {e}")
        return {
            **state,
            "anomaly_flags": [],
            "status": PipelineStatus.COMPLETED,
        }
