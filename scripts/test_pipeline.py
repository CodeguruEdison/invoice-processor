from app.ml.pipeline import process_invoice
from app.ml.state import PipelineStatus
import json


def test_pipeline() -> None:
    print("\n" + "="*50)
    print("🚀 Testing Invoice Processing Pipeline")
    print("="*50)

    file_path = "data/sample_invoices/test.pdf"

    print(f"\n📄 Processing: {file_path}")
    print("-"*50)

    whitelisted_vendors = [
        "TestTalent",
        "TestCreative Solutions Services",
        "TestAcme Corporation",
    ]
    is_tax_exempt = True
    tax_exempt_reason = "C2C services"
    # ── Run Pipeline ──────────────────────────────────
    result = process_invoice(file_path, whitelisted_vendors, is_tax_exempt, tax_exempt_reason)

    # ── Print Results ─────────────────────────────────
    print(f"\n✅ Status:         {result['status']}")
    print(f"🏢 Vendor:         {result['vendor_name']}")
    print(f"🔢 Invoice Number: {result['invoice_number']}")
    print(f"📅 Date:           {result['invoice_date']}")
    print(f"💰 Subtotal:       {result['subtotal']}")
    print(f"💰 Tax:            {result['tax_amount']}")
    print(f"💰 Total:          {result['total_amount']}")
    print(f"🎯 Confidence:     {result['confidence_score']:.2f}")
    print(f"🔄 Retries:        {result['retry_count']}")

    # ── Line Items ────────────────────────────────────
    if result.get("line_items"):
        print(f"\n📋 Line Items ({len(result['line_items'])}):")
        for item in result["line_items"]:
            print(
                f"   - {item.get('description')} | "
                f"qty: {item.get('quantity')} | "
                f"price: {item.get('unit_price')} | "
                f"total: {item.get('total')}"
            )

    # ── Validation Errors ─────────────────────────────
    if result.get("validation_errors"):
        print(f"\n⚠️  Validation Errors:")
        for error in result["validation_errors"]:
            print(f"   - {error}")

    # ── Anomalies ─────────────────────────────────────
    if result.get("anomaly_flags"):
        print(f"\n🚨 Anomalies Detected:")
        for anomaly in result["anomaly_flags"]:
            print(f"   - {anomaly}")
    else:
        print(f"\n✅ No anomalies detected")

    print("\n" + "="*50)

    # ── Final Verdict ─────────────────────────────────
    if result["status"] == PipelineStatus.COMPLETED:
        print("✅ Invoice processed successfully!")
    elif result["status"] == PipelineStatus.ANOMALY_FLAGGED:
        print("⚠️  Invoice flagged for review!")
    elif result["status"] == PipelineStatus.FAILED:
        print("❌ Invoice processing failed!")

    print("="*50 + "\n")


if __name__ == "__main__":
    test_pipeline()