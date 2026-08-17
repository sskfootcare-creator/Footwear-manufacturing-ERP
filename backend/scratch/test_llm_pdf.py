import asyncio
import os
import json
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from po_extractor import _llm_extract_pdf

os.environ["GEMINI_API_KEY"] = "test_key_dummy"

sample_llm_output = json.dumps({
    "po_number": "2220008835",
    "po_date": "2025-01-15",
    "client_name": "SIYARAM SILK MILLS LTD",
    "client_gstin": "27AAACS1234A1Z5",
    "client_state": "",
    "client_state_code": "",
    "vendor_name": "SSK Footcare",
    "vendor_address": "Agra, UP",
    "billing_address": "Mumbai, MH",
    "shipping_address": "Mumbai, MH",
    "delivery_date": "2025-02-15",
    "payment_terms": "30 days",
    "currency": "INR",
    "line_items": [
        {
            "item_code": "SY-OXF-08",
            "style_code": "OXFORD-01",
            "description": "Men Formal Leather Oxford",
            "color": "Black",
            "size": "8",
            "hsn_code": "6403",
            "quantity": 120,
            "unit_price": 850.0,
            "amount": 102000.0
        },
        {
            "item_code": "SY-OXF-09",
            "style_code": "OXFORD-01",
            "description": "Men Formal Leather Oxford",
            "color": "Brown",
            "size": "9",
            "hsn_code": "6403",
            "quantity": 80,
            "unit_price": 850.0,
            "amount": 68000.0
        }
    ],
    "subtotal": 170000.0,
    "cgst_rate": 0.0,
    "cgst_amount": 0.0,
    "sgst_rate": 0.0,
    "sgst_amount": 0.0,
    "igst_rate": 18.0,
    "igst_amount": 30600.0,
    "total_tax": 30600.0,
    "grand_total": 200600.0,
    "total_quantity": 200,
    "notes": "Urgent delivery"
})

mock_client = MagicMock()
mock_response = MagicMock()
mock_response.text = f"```json\n{sample_llm_output}\n```"
mock_client.models.generate_content.return_value = mock_response

fixture_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "siyaram_2220008835.pdf")
with open(fixture_path, "rb") as f:
    pdf_bytes = f.read()

with patch("google.genai.Client", return_value=mock_client):
    result = asyncio.run(_llm_extract_pdf(pdf_bytes))
    print("SUCCESS: _llm_extract_pdf executed successfully.")
    print(f"PO Number: {result.get('po_number')}")
    print(f"Client GSTIN: {result.get('client_gstin')}")
    print(f"Client State: {result.get('client_state')} (Code: {result.get('client_state_code')})")
    print(f"Line items parsed ({len(result.get('line_items', []))} items):")
    for item in result.get("line_items", []):
        print(f"  - Item: {item.get('item_code')} | Style: {item.get('style_code')} | Color: {item.get('color')} | Size: {item.get('size')} | Qty: {item.get('quantity')} | Price: {item.get('unit_price')}")

    # Verify generate_content was called with correct structure
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert len(call_kwargs["contents"]) == 2
    part = call_kwargs["contents"][0]
    assert part.inline_data.mime_type == "application/pdf"
    assert len(part.inline_data.data) == len(pdf_bytes)
    print("All SDK payload and validation assertions passed!")

# Test missing / unset GEMINI_API_KEY
for key_val in [None, ""]:
    if key_val is None:
        os.environ.pop("GEMINI_API_KEY", None)
        desc = "unset"
    else:
        os.environ["GEMINI_API_KEY"] = key_val
        desc = "empty"
    try:
        asyncio.run(_llm_extract_pdf(pdf_bytes))
        raise AssertionError(f"Expected error when GEMINI_API_KEY is {desc}")
    except (ValueError, RuntimeError) as e:
        assert "GEMINI_API_KEY" in str(e), f"Error message should mention GEMINI_API_KEY: {e}"
        print(f"Verified error when GEMINI_API_KEY is {desc}: {e}")

