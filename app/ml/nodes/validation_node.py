from app.ml.state import InvoiceState, PipelineStatus
import logging

logger = logging.getLogger(__name__)


def validation_node(state: InvoiceState) -> InvoiceState:

    if state["status"] == PipelineStatus.FAILED:
        logger.warning("Skipping validation — pipeline already failed")
        return state

    logger.info("Starting validation")
    errors: list[str] = []

    # Rule 1: Required fields
    if not state.get("vendor_name"):
        errors.append("Missing vendor name")
    if not state.get("invoice_number"):
        errors.append("Missing invoice number")
    if not state.get("total_amount"):
        errors.append("Missing total amount")
    if not state.get("invoice_date"):
        errors.append("Missing invoice date")

    # Rule 2: Math consistency
    if (
        state.get("subtotal") is not None
        and state.get("tax_amount") is not None
        and state.get("total_amount") is not None
    ):
        expected_total = round(
            state["subtotal"] + state["tax_amount"], 2
        )
        actual_total = round(state["total_amount"], 2)
        if abs(expected_total - actual_total) > 0.01:
            errors.append(
                f"Total mismatch: "
                f"subtotal({state['subtotal']}) + "
                f"tax({state['tax_amount']}) = {expected_total} "
                f"but total is {actual_total}"
            )

    # Rule 3: Missing tax
    # WHY WE CHECK is_tax_exempt:
    # Missing tax is only suspicious for non-exempt invoices.
    # For tax-exempt vendors this is completely normal.
    if (
        state.get("tax_amount") is None
        and not state.get("is_tax_exempt", False)
    ):
        errors.append(
            "Missing tax amount — if tax exempt please "
            "mark invoice as tax exempt"
        )

    # Rule 4: Negative amounts
    for field in ["subtotal", "tax_amount", "total_amount"]:
        value = state.get(field)
        if value is not None and value < 0:
            errors.append(
                f"Negative amount detected in {field}: {value}"
            )

    # Rule 5: Confidence score (guard against None from LLM)
    confidence = state.get("confidence_score")
    if confidence is None:
        errors.append("Missing confidence score (minimum: 0.60)")
    elif confidence < 0.6:
        errors.append(
            f"Low confidence score: {confidence:.2f} (minimum: 0.60)"
        )

    # Rule 6: Line items vs subtotal
    if state.get("line_items") and state.get("subtotal"):
        line_items_total = round(
            sum(item.get("total", 0) for item in state["line_items"]), 2
        )
        subtotal = round(state["subtotal"], 2)
        if abs(line_items_total - subtotal) > 0.01:
            errors.append(
                f"Line items total ({line_items_total}) "
                f"does not match subtotal ({subtotal})"
            )

    if errors:
        logger.warning(
            f"Validation failed with {len(errors)} errors: {errors}"
        )
        return {**state, "validation_errors": errors}

    logger.info("Validation passed")
    return {
        **state,
        "validation_errors": [],
        "status": PipelineStatus.VALIDATED,
    }

def should_retry(state: InvoiceState) -> str:
    """
    WHY THIS FUNCTION EXISTS:
    This is a LangGraph CONDITIONAL EDGE — it decides
    which node to go to next based on the current state.

    Think of it as a traffic controller at an intersection:
    - No errors?        → proceed to anomaly detection
    - Errors + retries left? → go back and try extraction again
    - Errors + no retries?   → mark as failed and stop

    WHY MAX 2 RETRIES:
    We don't want infinite loops. If the LLM fails 3 times
    on the same invoice, the invoice is likely too corrupted
    or unclear to process automatically. We save it as
    failed for manual review.

    RETURN VALUES must match the keys in add_conditional_edges()
    in pipeline.py — we will wire this up next.
    """
    if state["status"] == PipelineStatus.FAILED:
        logger.warning("Pipeline already failed — routing to failed node")
        return "failed"

    has_errors = bool(state["validation_errors"])
    retry_count = state["retry_count"]

    if not has_errors:
        logger.info("Validation passed — proceeding to anomaly detection")
        return "proceed"

    if retry_count < 2:
        logger.info(
            f"Validation failed — retrying "
            f"(attempt {retry_count + 1} of 2)"
        )
        return "retry"

    logger.error(
        f"Validation failed after {retry_count} retries — marking as failed"
    )
    return "failed"