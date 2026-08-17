import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from po_extractor import _llm_extract_pdf, _get_gemini_model

async def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY is missing or empty in backend/.env")
        return 1
    
    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
    model_name = _get_gemini_model()
    print(f"Testing Gemini API with key: {masked}")
    print(f"Target model: {model_name}")

    fixture_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "siyaram_2220008835.pdf"
    if not fixture_path.exists():
        print(f"ERROR: Fixture not found at {fixture_path}")
        return 1
    
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()

    print(f"Sending PO document ({len(pdf_bytes)} bytes) to Gemini API...")
    try:
        data = await _llm_extract_pdf(pdf_bytes)
        print("\n=== SUCCESS: Gemini API Response Received ===")
        print(f"PO Number:       {data.get('po_number')}")
        print(f"PO Date:         {data.get('po_date')}")
        print(f"Client Name:     {data.get('client_name')}")
        print(f"Client GSTIN:    {data.get('client_gstin')}")
        print(f"Client State:    {data.get('client_state')} (Code: {data.get('client_state_code')})")
        print(f"Subtotal:        Rs. {data.get('subtotal', 0):,.2f}")
        print(f"Total Tax:       Rs. {data.get('total_tax', 0):,.2f}")
        print(f"Grand Total:     Rs. {data.get('grand_total', 0):,.2f}")
        
        items = data.get("line_items", [])
        print(f"\nExtracted Line Items: {len(items)} items")
        for i, it in enumerate(items[:10], 1):
            print(f"  [{i:02d}] Style: {it.get('style_code')} | Color: {it.get('color')} | Size: {it.get('size')} | Qty: {it.get('quantity')} | Rate: Rs. {it.get('unit_price')}")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more items.")
        print("\nGemini API integration is fully operational and working!")
        return 0
    except Exception as e:
        print(f"\nERROR: Gemini API call failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
