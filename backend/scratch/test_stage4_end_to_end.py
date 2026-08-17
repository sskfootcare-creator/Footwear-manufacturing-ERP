import asyncio
import io
import json
import os
import sys
from unittest.mock import MagicMock, patch
import openpyxl
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from po_extractor import extract_po_from_pdf, extract_po_from_xlsx, _is_low_confidence
from po_extractor_free import extract_po_from_pdf_local, extract_po_from_xlsx_local

os.environ["GEMINI_API_KEY"] = "test_key_dummy"

# -------------------------------------------------------------
# 1. TEST RECOGNIZED LOCAL FORMAT (Siyaram) -> NO LLM CALL
# -------------------------------------------------------------
print("\n--- TEST 1: Siyaram Recognized Format (Local Offline Path) ---")
siyaram_fixture = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "siyaram_2220008835.pdf")
with open(siyaram_fixture, "rb") as f:
    siyaram_bytes = f.read()

local_siyaram = extract_po_from_pdf_local(siyaram_bytes)
is_siyaram_low_conf = _is_low_confidence(local_siyaram)
print(f"Siyaram parsed locally: {len(local_siyaram['line_items'])} items. is_low_confidence = {is_siyaram_low_conf}")
assert not is_siyaram_low_conf, "Siyaram format should have high confidence (color and size populated)"

mock_client = MagicMock()
with patch("google.genai.Client", return_value=mock_client):
    result_siyaram = asyncio.run(extract_po_from_pdf(siyaram_bytes))
    # LLM should NOT have been called because local confidence was high
    mock_client.models.generate_content.assert_not_called()
    print("SUCCESS: Local parser used directly, zero LLM calls needed.")
    assert len(result_siyaram["line_items"]) == 32
    assert result_siyaram["line_items"][0]["color"] == "BROWN"
    assert result_siyaram["line_items"][0]["size"] == "4"


# -------------------------------------------------------------
# 2. TEST UNRECOGNIZED PDF FORMAT -> ROUTES TO GEMINI FALLBACK
# -------------------------------------------------------------
print("\n--- TEST 2: Unrecognized PDF Format -> Gemini Fallback ---")
# Create a PDF PO with standard table headers but descriptions like "Men Casual Loafers"
# (Neither Siyaram 'CODE COLOR SIZE' nor SHEIN 'CODE,COLOR,SIZE')
pdf_buf = io.BytesIO()
doc = SimpleDocTemplate(pdf_buf, pagesize=letter)
styles = getSampleStyleSheet()
story = [
    Paragraph("<b>PURCHASE ORDER</b>", styles["Title"]),
    Paragraph("PO Number: PO-METRO-2026-99 | Date: 2026-06-10", styles["Normal"]),
    Paragraph("Buyer: Metro Brands Ltd | GSTIN: 27AABCM5678F1Z2", styles["Normal"]),
    Spacer(1, 12),
]
table_data = [
    ["Item", "Description", "HSN", "Qty", "Rate", "Amount"],
    ["1", "Premium Casual Loafer Shoe", "6403", "50", "1500.00", "75000.00"],
    ["2", "Classic Leather Oxford", "6403", "30", "1800.00", "54000.00"],
]
t = Table(table_data)
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.grey),
    ('GRID', (0,0), (-1,-1), 1, colors.black),
]))
story.append(t)
doc.build(story)
unrecognized_pdf_bytes = pdf_buf.getvalue()

# Check what local parser produces
local_parsed = extract_po_from_pdf_local(unrecognized_pdf_bytes)
print(f"Local parser extracted {len(local_parsed['line_items'])} items:")
for li in local_parsed["line_items"]:
    print(f"  - Desc: '{li.get('description')}' | Color: '{li.get('color')}' | Size: '{li.get('size')}' | Qty: {li.get('quantity')}")

is_low_conf = _is_low_confidence(local_parsed)
print(f"is_low_confidence check: {is_low_conf}")
assert is_low_conf, "Unrecognized format must be flagged as low confidence because color/size are missing"

# Now run through extract_po_from_pdf with mock Gemini response providing actual color/size
mock_llm_pdf_response = json.dumps({
    "po_number": "PO-METRO-2026-99",
    "po_date": "2026-06-10",
    "client_name": "Metro Brands Ltd",
    "client_gstin": "27AABCM5678F1Z2",
    "line_items": [
        {
            "item_code": "MB-LOAF-01",
            "style_code": "LOAFER-01",
            "description": "Premium Casual Loafer Shoe",
            "color": "Navy Blue",
            "size": "8",
            "quantity": 50,
            "unit_price": 1500.0,
            "amount": 75000.0
        },
        {
            "item_code": "MB-OXF-02",
            "style_code": "OXFORD-02",
            "description": "Classic Leather Oxford",
            "color": "Tan",
            "size": "9",
            "quantity": 30,
            "unit_price": 1800.0,
            "amount": 54000.0
        }
    ],
    "grand_total": 129000.0
})

mock_client = MagicMock()
mock_resp = MagicMock()
mock_resp.text = f"```json\n{mock_llm_pdf_response}\n```"
mock_client.models.generate_content.return_value = mock_resp

with patch("google.genai.Client", return_value=mock_client):
    result = asyncio.run(extract_po_from_pdf(unrecognized_pdf_bytes))
    mock_client.models.generate_content.assert_called_once()
    print("SUCCESS: Gemini fallback was invoked due to low_confidence flag!")
    print(f"Extracted PO: {result.get('po_number')}")
    print(f"Extracted Line Items ({len(result.get('line_items', []))} items):")
    for li in result.get("line_items", []):
        print(f"  - Item: {li.get('item_code')} | Style: {li.get('style_code')} | Color: {li.get('color')} | Size: {li.get('size')} | Qty: {li.get('quantity')}")
        assert li["color"] in ["Navy Blue", "Tan"], f"Expected populated color, got '{li['color']}'"
        assert li["size"] in ["8", "9"], f"Expected populated size, got '{li['size']}'"


# -------------------------------------------------------------
# 3. TEST UNRECOGNIZED XLSX FORMAT -> ROUTES TO GEMINI FALLBACK
# -------------------------------------------------------------
print("\n--- TEST 3: Unrecognized XLSX Format -> Gemini Fallback ---")
wb = openpyxl.Workbook()
ws = wb.active
ws.append(["PURCHASE ORDER - BATA INDIA"])
ws.append(["PO Number:", "PO-BATA-2026-441", "Date:", "2026-05-18"])
ws.append([])
ws.append(["Item No", "Product Description", "HSN", "Quantity", "Unit Rate", "Total Amount"])
ws.append(["1", "Mens Sports Sneaker", "6404", 100, 950.0, 95000.0])
ws.append(["2", "Womens Walking Sneaker", "6404", 150, 850.0, 127500.0])
buf = io.BytesIO()
wb.save(buf)
unrec_xlsx_bytes = buf.getvalue()

local_xlsx_parsed = extract_po_from_xlsx_local(unrec_xlsx_bytes)
is_xlsx_low_conf = _is_low_confidence(local_xlsx_parsed)
print(f"Local XLSX parse: is_low_confidence = {is_xlsx_low_conf}")
assert is_xlsx_low_conf, "Unrecognized XLSX format must be flagged as low confidence"

mock_llm_xlsx_response = json.dumps({
    "po_number": "PO-BATA-2026-441",
    "po_date": "2026-05-18",
    "client_name": "Bata India Ltd",
    "client_gstin": "19AABCB1234E1Z1",
    "line_items": [
        {
            "item_code": "BT-SP-01",
            "style_code": "SPORTS-01",
            "description": "Mens Sports Sneaker",
            "color": "White/Navy",
            "size": "10",
            "quantity": 100,
            "unit_price": 950.0,
            "amount": 95000.0
        },
        {
            "item_code": "BT-WLK-02",
            "style_code": "WALK-02",
            "description": "Womens Walking Sneaker",
            "color": "Pink",
            "size": "6",
            "quantity": 150,
            "unit_price": 850.0,
            "amount": 127500.0
        }
    ],
    "grand_total": 222500.0
})

mock_client = MagicMock()
mock_resp = MagicMock()
mock_resp.text = f"```json\n{mock_llm_xlsx_response}\n```"
mock_client.models.generate_content.return_value = mock_resp

with patch("google.genai.Client", return_value=mock_client):
    result_xlsx = asyncio.run(extract_po_from_xlsx(unrec_xlsx_bytes))
    mock_client.models.generate_content.assert_called_once()
    print("SUCCESS: Gemini fallback was invoked for XLSX due to low_confidence flag!")
    for li in result_xlsx.get("line_items", []):
        print(f"  - Item: {li.get('item_code')} | Style: {li.get('style_code')} | Color: {li.get('color')} | Size: {li.get('size')} | Qty: {li.get('quantity')}")
        assert li["color"] in ["White/Navy", "Pink"]
        assert li["size"] in ["10", "6"]

print("\n========================================================")
print("ALL END-TO-END STAGE 4 CONFIDENCE & ROUTING TESTS PASSED!")
print("========================================================\n")
