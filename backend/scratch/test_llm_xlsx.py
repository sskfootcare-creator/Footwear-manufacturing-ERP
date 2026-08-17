import asyncio
import io
import json
import os
import sys
from unittest.mock import MagicMock, patch
import openpyxl

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from po_extractor import _llm_extract_xlsx

os.environ["GEMINI_API_KEY"] = "test_key_dummy"

# 1. Create a sample in-memory Excel PO file using openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "PurchaseOrder"

ws.append(["PURCHASE ORDER", "", "", "", "", ""])
ws.append(["PO Number:", "PO-2026-XLSX-001", "PO Date:", "2026-03-01", "", ""])
ws.append(["Vendor:", "SSK Footcare", "Buyer:", "Metro Brands Retail Ltd", "", ""])
ws.append(["Buyer GSTIN:", "27AABCM1234F1Z8", "Delivery Date:", "2026-04-15", "", ""])
ws.append([])
ws.append(["Item Code", "Style Code", "Description", "Color", "Size", "Qty", "Rate", "Amount"])
ws.append(["MB-DER-07", "DERBY-01", "Men Classic Derby", "Tan", "7", 50, 1200.0, 60000.0])
ws.append(["MB-DER-08", "DERBY-01", "Men Classic Derby", "Tan", "8", 75, 1200.0, 90000.0])
ws.append(["MB-DER-09", "DERBY-01", "Men Classic Derby", "Black", "9", 40, 1200.0, 48000.0])
ws.append([])
ws.append(["Subtotal", "", "", "", "", "", "", 198000.0])
ws.append(["IGST 18%", "", "", "", "", "", "", 35640.0])
ws.append(["Grand Total", "", "", "", "", "", "", 233640.0])

buf = io.BytesIO()
wb.save(buf)
xlsx_bytes = buf.getvalue()

sample_llm_output = json.dumps({
    "po_number": "PO-2026-XLSX-001",
    "po_date": "2026-03-01",
    "client_name": "Metro Brands Retail Ltd",
    "client_gstin": "27AABCM1234F1Z8",
    "client_state": "",
    "client_state_code": "",
    "vendor_name": "SSK Footcare",
    "delivery_date": "2026-04-15",
    "currency": "INR",
    "line_items": [
        {
            "item_code": "MB-DER-07",
            "style_code": "DERBY-01",
            "description": "Men Classic Derby",
            "color": "Tan",
            "size": "7",
            "quantity": 50,
            "unit_price": 1200.0,
            "amount": 60000.0
        },
        {
            "item_code": "MB-DER-08",
            "style_code": "DERBY-01",
            "description": "Men Classic Derby",
            "color": "Tan",
            "size": "8",
            "quantity": 75,
            "unit_price": 1200.0,
            "amount": 90000.0
        },
        {
            "item_code": "MB-DER-09",
            "style_code": "DERBY-01",
            "description": "Men Classic Derby",
            "color": "Black",
            "size": "9",
            "quantity": 40,
            "unit_price": 1200.0,
            "amount": 48000.0
        }
    ],
    "subtotal": 198000.0,
    "igst_rate": 18.0,
    "igst_amount": 35640.0,
    "grand_total": 233640.0,
    "total_quantity": 165
})

mock_client = MagicMock()
mock_response = MagicMock()
mock_response.text = f"```json\n{sample_llm_output}\n```"
mock_client.models.generate_content.return_value = mock_response

with patch("google.genai.Client", return_value=mock_client):
    result = asyncio.run(_llm_extract_xlsx(xlsx_bytes))
    print("SUCCESS: _llm_extract_xlsx executed successfully.")
    print(f"PO Number: {result.get('po_number')}")
    print(f"Client GSTIN: {result.get('client_gstin')}")
    print(f"Client State: {result.get('client_state')} (Code: {result.get('client_state_code')})")
    print(f"Line items count: {len(result.get('line_items', []))}")
    for li in result.get("line_items", []):
        print(f"  - Item: {li.get('item_code')} | Style: {li.get('style_code')} | Color: {li.get('color')} | Size: {li.get('size')} | Qty: {li.get('quantity')} | Rate: {li.get('unit_price')}")

    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert "--- Document Content ---" in call_kwargs["contents"]
    assert "PO-2026-XLSX-001" in call_kwargs["contents"]
    print("All SDK payload contents and text extraction assertions passed!")

# Test missing / unset GEMINI_API_KEY
for key_val in [None, ""]:
    if key_val is None:
        os.environ.pop("GEMINI_API_KEY", None)
        desc = "unset"
    else:
        os.environ["GEMINI_API_KEY"] = key_val
        desc = "empty"
    try:
        asyncio.run(_llm_extract_xlsx(xlsx_bytes))
        raise AssertionError(f"Expected error when GEMINI_API_KEY is {desc}")
    except (ValueError, RuntimeError) as e:
        assert "GEMINI_API_KEY" in str(e), f"Error message should mention GEMINI_API_KEY: {e}"
        print(f"Verified error when GEMINI_API_KEY is {desc}: {e}")
