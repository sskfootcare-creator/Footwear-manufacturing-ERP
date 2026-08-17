"""End-to-end tests for the real PO extraction upload flow (/api/pos/extract).

Tests:
1. Siyaram-format PO (PDF): Local parser only, high confidence, zero LLM calls, zero regressions.
2. SHEIN-comma-format PO (PDF): Local parser only, high confidence, zero LLM calls, zero regressions.
3. Unrecognized-format PO (neither Siyaram nor SHEIN): Local parser low confidence -> routes to Gemini fallback, returns populated color/size and confidence metadata.
"""
import io
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import server
from po_extractor import extract_po_from_pdf, extract_po_from_xlsx


# Helper: Generate a real SHEIN-style comma-separated PDF
def _generate_shein_pdf() -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("<b>PURCHASE ORDER</b>", styles["Title"]),
        Paragraph("Purchase Order No: 5155396467 | Date: 24.03.2026", styles["Normal"]),
        Paragraph("Buyer: NEXTGEN RETAIL INDIA PVT LTD | GSTIN: 27AABCN1234F1Z1", styles["Normal"]),
        Paragraph("Vendor Name: SSK FOOTCARE MANUFACTURING LLP", styles["Normal"]),
        Spacer(1, 10),
    ]
    table_data = [
        ["Article / Description", "HSN", "Quantity", "Unit Rate", "Total Amount"],
        ["SHEIN WOMEN FOOTWEAR,BLACK,3", "64039990", "10", "235.00", "2350.00"],
        ["SHEIN WOMEN FOOTWEAR,TAN,4", "64039990", "20", "235.00", "4700.00"],
        ["SHEIN WOMEN FOOTWEAR,WHITE,5", "64039990", "15", "235.00", "3525.00"],
    ]
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(t)
    doc.build(story)
    return buf.getvalue()


# Helper: Generate an unrecognized PDF format (plain descriptions without comma/trailing Siyaram syntax)
def _generate_unrecognized_pdf() -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("<b>PURCHASE ORDER</b>", styles["Title"]),
        Paragraph("PO Number: PO-REGAL-9988 | Date: 15/04/2026", styles["Normal"]),
        Paragraph("Buyer: Regal Shoes International Ltd | GSTIN: 27AABCR9988G1Z3", styles["Normal"]),
        Spacer(1, 10),
    ]
    table_data = [
        ["Item", "Description", "HSN Code", "Qty", "Price", "Amount"],
        ["1", "Handcrafted Mens Formal Derby", "6403", "40", "1400.00", "56000.00"],
        ["2", "Casual Leather Loafers", "6403", "60", "1250.00", "75000.00"],
    ]
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(t)
    doc.build(story)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def mock_auth_user(monkeypatch):
    """Bypass auth checks for direct endpoint testing."""
    mock_user = {"id": "admin_test", "role": "admin", "roles": ["admin"]}
    monkeypatch.setattr(server, "get_current_user", AsyncMock(return_value=mock_user))
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_api_key_12345")


# -------------------------------------------------------------------
# Test 1: Siyaram Format (Real PDF Fixture) -> Local parser only
# -------------------------------------------------------------------
@pytest.mark.anyio
async def test_upload_flow_siyaram_pdf_local_only():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "siyaram_2220008835.pdf")
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()

    upload_file = UploadFile(filename="siyaram_2220008835.pdf", file=io.BytesIO(pdf_bytes))

    mock_client = MagicMock()
    with patch("google.genai.Client", return_value=mock_client):
        result = await server.extract_po(file=upload_file, request=None)

        # 1. LLM must NOT be called
        mock_client.models.generate_content.assert_not_called()

        # 2. Local parser results are high confidence
        assert result.get("extraction_method") == "local"
        assert result.get("confidence") == "high"
        assert result.get("po_number") == "2220008835"
        assert "SIYARAM" in (result.get("client_name") or "").upper()
        assert len(result.get("line_items", [])) == 32

        # 3. Check color/size preservation on line items
        first_item = result["line_items"][0]
        assert first_item["color"] == "BROWN"
        assert first_item["size"] == "4"
        assert first_item["quantity"] == 72
        assert first_item["unit_price"] == 160.0


# -------------------------------------------------------------------
# Test 2: SHEIN-comma Format (PDF) -> Local parser only
# -------------------------------------------------------------------
@pytest.mark.anyio
async def test_upload_flow_shein_comma_pdf_local_only():
    shein_bytes = _generate_shein_pdf()
    upload_file = UploadFile(filename="shein_order_5155396467.pdf", file=io.BytesIO(shein_bytes))

    mock_client = MagicMock()
    with patch("google.genai.Client", return_value=mock_client):
        result = await server.extract_po(file=upload_file, request=None)

        # 1. LLM must NOT be called
        mock_client.models.generate_content.assert_not_called()

        # 2. Local parser extracted successfully
        assert result.get("extraction_method") == "local"
        assert result.get("confidence") == "high"
        assert result.get("po_number") == "5155396467"
        assert len(result.get("line_items", [])) == 3

        # 3. Comma-separated color and size extracted correctly
        items = result["line_items"]
        assert items[0]["color"] == "BLACK"
        assert items[0]["size"] == "3"
        assert items[1]["color"] == "TAN"
        assert items[1]["size"] == "4"
        assert items[2]["color"] == "WHITE"
        assert items[2]["size"] == "5"


# -------------------------------------------------------------------
# Test 3: Unrecognized Format (PDF) -> Routes to Gemini Fallback
# -------------------------------------------------------------------
@pytest.mark.anyio
async def test_upload_flow_unrecognized_pdf_triggers_gemini_fallback():
    unrec_bytes = _generate_unrecognized_pdf()
    upload_file = UploadFile(filename="regal_order_9988.pdf", file=io.BytesIO(unrec_bytes))

    # Mock Gemini response containing properly structured color and size
    gemini_output = json.dumps({
        "po_number": "PO-REGAL-9988",
        "po_date": "2026-04-15",
        "client_name": "Regal Shoes International Ltd",
        "client_gstin": "27AABCR9988G1Z3",
        "client_state": "Maharashtra",
        "client_state_code": "27",
        "vendor_name": "SSK Footcare",
        "currency": "INR",
        "line_items": [
            {
                "item_code": "RG-DERBY-01",
                "style_code": "DERBY-01",
                "description": "Handcrafted Mens Formal Derby",
                "color": "Dark Brown",
                "size": "8",
                "hsn_code": "6403",
                "quantity": 40,
                "unit_price": 1400.0,
                "amount": 56000.0
            },
            {
                "item_code": "RG-LOAF-02",
                "style_code": "LOAFER-02",
                "description": "Casual Leather Loafers",
                "color": "Cherry",
                "size": "9",
                "hsn_code": "6403",
                "quantity": 60,
                "unit_price": 1250.0,
                "amount": 75000.0
            }
        ],
        "subtotal": 131000.0,
        "grand_total": 154580.0,
        "total_quantity": 100
    })

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = f"```json\n{gemini_output}\n```"
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        result = await server.extract_po(file=upload_file, request=None)

        # 1. Gemini fallback WAS invoked
        mock_client.models.generate_content.assert_called_once()

        # 2. Metadata reflects Gemini fallback
        assert result.get("extraction_method") == "gemini_fallback"
        assert result.get("confidence") == "high"
        assert "confidence_warning" in result
        assert "Gemini AI fallback" in result["confidence_warning"]

        # 3. Line items have correct color and size
        items = result.get("line_items", [])
        assert len(items) == 2
        assert items[0]["color"] == "Dark Brown"
        assert items[0]["size"] == "8"
        assert items[1]["color"] == "Cherry"
        assert items[1]["size"] == "9"
