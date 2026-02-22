from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy import true
from app.ml.state import InvoiceState, PipelineStatus
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

llm = ChatOllama(
    model=settings.OLLAMA_MODEL,
    temperature=0,
    format="json",
    base_url=settings.OLLAMA_BASE_URL,
)

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
- Tax Exempt: {is_tax_exempt}
- Tax Exempt Reason: {tax_exempt_reason}

Check specifically for:
1. Suspiciously round numbers (e.g. exactly $10,000.00)
2. Truly vague line item descriptions only (e.g. "Miscellaneous", "Other", "Item 1", "Supplies") — NOT normal product names like "Floral Cotton Dress" or "Cuban Collar Shirt"
3. Invoice dates on weekends or public holidays
4. Vendor names that look misspelled or suspicious
5. Amounts just below common approval thresholds
6. Missing or duplicate invoice numbers
7. Line items with unusually high unit prices (e.g. one item 10x higher than others, or unit price over $5000) — do NOT flag normal retail prices like $100–200
8. Missing tax ONLY if Tax Exempt is False

IMPORTANT: If Tax Exempt is True, do NOT flag
missing tax amount as an anomaly.

Only flag clear anomalies. Normal product names and moderate
prices ($50–500) are not anomalies.

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


def _is_vendor_whitelisted(
    vendor_name: str,
    whitelisted_vendors: list[str],
) -> bool:
    """
    WHY A PRIVATE HELPER FUNCTION:
    This logic is used only inside this node.
    Keeping it as a private function (underscore prefix)
    makes it clear it's not meant to be imported elsewhere.
    It also makes the main function easier to read.
    """
    if not vendor_name or not whitelisted_vendors:
        return False

    vendor_lower = vendor_name.lower().strip()

    for whitelisted in whitelisted_vendors:
        # Exact match
        if vendor_lower == whitelisted:
            logger.info(f"Vendor exact match: {vendor_name}")
            return True

        # Partial match
        if whitelisted in vendor_lower or vendor_lower in whitelisted:
            logger.info(f"Vendor partial match: {vendor_name}")
            return True

    return False


def _filter_vendor_anomalies(
    anomalies: list[str],
    vendor_name: str | None,
    whitelisted_vendors: list[str],
) -> list[str]:
    """
    WHY WE FILTER NOT SKIP:
    Even for whitelisted vendors we still check for
    math errors, duplicate invoices etc.
    We only remove vendor name related flags.
    """
    if not vendor_name:
        return anomalies

    if not _is_vendor_whitelisted(vendor_name, whitelisted_vendors):
        return anomalies

    filtered = [
        anomaly for anomaly in anomalies
        if not any(
            keyword in anomaly.lower()
            for keyword in [
                "vendor",
                "vendor name",
                "company name",
                "generic name",
                "suspicious name",
            ]
        )
    ]

    removed = len(anomalies) - len(filtered)
    if removed > 0:
        logger.info(
            f"Filtered {removed} vendor anomalies "
            f"for whitelisted vendor: {vendor_name}"
        )

    return filtered


def anomaly_node(state: InvoiceState) -> InvoiceState:

    if state["status"] == PipelineStatus.FAILED:
        logger.warning("Skipping anomaly detection — pipeline failed")
        return state

    if state["status"] != PipelineStatus.VALIDATED:
        logger.warning("Skipping anomaly detection — not yet validated")
        return state

    logger.info("Starting anomaly detection")

    try:
        result: dict = chain.invoke({
            "vendor_name": state.get("vendor_name", "Unknown"),
            "invoice_number": state.get("invoice_number", "Unknown"),
            "invoice_date": state.get("invoice_date", "Unknown"),
            "subtotal": state.get("subtotal", 0),
            "tax_amount": state.get("tax_amount", "Not provided"),
            "total_amount": state.get("total_amount", 0),
            "line_items": state.get("line_items", []),
            "is_tax_exempt": state.get("is_tax_exempt", False),
            "tax_exempt_reason": state.get("tax_exempt_reason", "N/A"),
        })

        anomalies: list[str] = result.get("anomalies", [])
        risk_score: float = result.get("risk_score", 0.0)
        risk_level: str = result.get("risk_level", "low")

        # ── Apply Whitelist Filter ─────────────────────
        # WHY FROM STATE NOT DB:
        # Whitelist was loaded from DB before pipeline started
        # and passed in via initial state. No DB call needed here.
        anomalies = _filter_vendor_anomalies(
            anomalies=anomalies,
            vendor_name=state.get("vendor_name"),
            whitelisted_vendors=state["whitelisted_vendors"],
        )

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
        logger.error(f"Anomaly detection failed: {e}")
        return {
            **state,
            "anomaly_flags": [],
            "status": PipelineStatus.COMPLETED,
        }