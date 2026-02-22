from typing import TYPE_CHECKING

import logging
from langgraph.graph import StateGraph, END

from app.ml.state import InvoiceState, PipelineStatus
from app.ml.nodes.ocr_node import make_ocr_node
from app.ml.nodes.extraction_node import extraction_node
from app.ml.nodes.validation_node import validation_node, should_retry
from app.ml.nodes.anomaly_node import anomaly_node

if TYPE_CHECKING:
    from app.services.docling_service import DoclingService

logger = logging.getLogger(__name__)


def retry_node(state: InvoiceState) -> InvoiceState:
    """
    WHY THIS NODE EXISTS:
    Before we retry extraction we need to:
    1. Increment the retry counter so we don't loop forever
    2. Clear the previous validation errors so the
       validation node starts fresh next time

    WHY NOT PUT THIS LOGIC IN VALIDATION NODE:
    Single Responsibility — validation finds errors,
    retry node prepares for another attempt.
    Mixing them would make both harder to understand.
    """
    logger.info(
        f"Preparing retry attempt {state['retry_count'] + 1}"
    )
    return {
        **state,
        "retry_count": state["retry_count"] + 1,
        "validation_errors": [],
    }


def failed_node(state: InvoiceState) -> InvoiceState:
    """
    WHY THIS NODE EXISTS:
    When all retries are exhausted we need a clean
    terminal node that marks the invoice as failed.

    WHY NOT JUST USE END:
    We need to update the status to FAILED before
    ending. LangGraph needs a node to do this —
    END just terminates, it doesn't update state.
    """
    logger.error(
        f"Invoice processing failed after "
        f"{state['retry_count']} retries. "
        f"Errors: {state['validation_errors']}"
    )
    return {
        **state,
        "status": PipelineStatus.FAILED,
    }


def build_pipeline(
    docling_service: "DoclingService | None" = None,
) -> StateGraph:
    """
    WHY WE USE A FUNCTION TO BUILD THE PIPELINE:
    Instead of building the graph at module level
    we wrap it in a function. This means:
    - Easier to test (call build_pipeline() in tests)
    - Easier to create multiple instances if needed
    - Clearer separation between definition and execution

    DoclingService is injected so the OCR node can use Docling
    for document parsing when OCR_USE_DOCLING is True.

    HOW LANGGRAPH WORKS:
    Think of it like drawing a flowchart in code:
    1. Add nodes  — the boxes in the flowchart
    2. Add edges  — the arrows between boxes
    3. Compile    — LangGraph validates and optimizes the graph
    4. Invoke     — run the graph with an initial state
    """

    # ── Create Graph ──────────────────────────────────────
    # StateGraph takes our TypedDict as the state type.
    # This tells LangGraph what shape the state object is.
    graph = StateGraph(InvoiceState)

    # ── Add Nodes ─────────────────────────────────────────
    # WHY STRING NAMES:
    # We reference nodes by string name when adding edges.
    # This decouples the node functions from the graph
    # structure — we could swap ocr_node for a different
    # implementation without changing the edge definitions.
    # OCR node receives docling_service via closure (dependency injection).
    graph.add_node("ocr", make_ocr_node(docling_service))
    graph.add_node("extract", extraction_node)
    graph.add_node("validate", validation_node)
    graph.add_node("retry", retry_node)
    graph.add_node("anomaly", anomaly_node)
    graph.add_node("failed", failed_node)

    # ── Entry Point ───────────────────────────────────────
    # WHY SET ENTRY POINT:
    # LangGraph needs to know which node to start from.
    # Without this it wouldn't know where to begin.
    graph.set_entry_point("ocr")

    # ── Static Edges ──────────────────────────────────────
    # WHY STATIC EDGES:
    # These nodes always go to the same next node —
    # no decision making needed. Simple and predictable.
    graph.add_edge("ocr", "extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("retry", "extract")   # retry loops back to extract
    graph.add_edge("anomaly", END)       # anomaly is the last real node
    graph.add_edge("failed", END)        # failed is a terminal node

    # ── Conditional Edge ──────────────────────────────────
    # WHY CONDITIONAL EDGES:
    # After validation we have THREE possible paths.
    # A static edge can only go to one place so we need
    # a conditional edge that calls should_retry() to
    # decide which path to take.
    #
    # The dict maps return values of should_retry()
    # to node names:
    # "proceed" → go to anomaly detection
    # "retry"   → go to retry node (then back to extract)
    # "failed"  → go to failed node (then END)
    graph.add_conditional_edges(
        "validate",       # from this node
        should_retry,     # call this function to decide
        {
            "proceed": "anomaly",
            "retry": "retry",
            "failed": "failed",
        }
    )

    # ── Compile ───────────────────────────────────────────
    # WHY COMPILE:
    # Compilation validates the graph structure —
    # checks for disconnected nodes, missing edges etc.
    # It also optimizes the graph for execution.
    # If there is a mistake in our graph definition
    # we find out here not at runtime.
    return graph.compile()


def process_invoice(
    file_path: str,
    whitelisted_vendors: list[str] | None = None,
    is_tax_exempt: bool = False,
    tax_exempt_reason: str | None = None,
    docling_service: "DoclingService | None" = None,
) -> InvoiceState:
    """
    WHY THIS WRAPPER FUNCTION:
    It hides the complexity of building the initial state
    from the callers. The service layer just calls
    process_invoice(file_path) and gets back a result.
    It doesn't need to know about InvoiceState structure.
    """
    logger.info(f"Starting pipeline for: {file_path}")

    # ── Initial State ─────────────────────────────────────
    # WHY WE SET ALL FIELDS:
    # TypedDict requires all fields to be present.
    # We set sensible defaults for all fields so
    # each node can safely read any field without
    # checking if it exists first.
    initial_state: InvoiceState = {
        "file_path": file_path,
        "raw_text": "",
        "vendor_name": None,
        "invoice_number": None,
        "invoice_date": None,
        "line_items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None,
        "confidence_score": 0.0,
        "retry_count": 0,
        "validation_errors": [],
        "anomaly_flags": [],
        "status": PipelineStatus.PENDING,
        "is_tax_exempt": is_tax_exempt,
        "tax_exempt_reason": tax_exempt_reason,
        "whitelisted_vendors": [
            v.lower().strip()
            for v in (whitelisted_vendors or [])
        ],
    }

    # Build pipeline with injected DoclingService (built per request when DI is used)
    pipeline = build_pipeline(docling_service=docling_service)
    result: InvoiceState = pipeline.invoke(initial_state)
    logger.info(
        f"Pipeline completed. "
        f"Status: {result['status']} "
        f"Vendor: {result.get('vendor_name')} "
        f"Total: {result.get('total_amount')}"
    )

    return result
