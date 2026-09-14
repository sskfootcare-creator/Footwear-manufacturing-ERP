import pytest
from unittest.mock import MagicMock, AsyncMock
from bson import ObjectId
from datetime import datetime, timezone

from pdf_card import build_production_card, build_production_card_dual_a4, _build_card_elements
from routes.pos import _enrich_jobs


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, limit=None):
        return self.docs


@pytest.mark.anyio
async def test_enrich_jobs_populates_po_style_code_and_created_at():
    mock_db = MagicMock()
    mock_po = {
        "po_number": "PO-TEST-100",
        "line_items": [
            {
                "style_code": "SSK_00034",
                "color": "CREAM",
                "external_sku": "EXT-SKU-100",
            },
            {
                "style_code": "SSK_00034",
                "color": "BLACK",
                "external_sku": "EXT-SKU-200",
            },
        ],
    }
    mock_db.pos.find.return_value = MockCursor([mock_po])

    gen_oid = ObjectId()
    jobs = [
        {
            "_id": gen_oid,
            "po_number": "PO-TEST-100",
            "style_code": "SSK_00034",
            "color": "CREAM",
        },
        {
            "_id": ObjectId(),
            "po_number": "PO-TEST-100",
            "style_code": "SSK_00034",
            "color": "BLACK",
            "created_at": "2026-09-01T12:00:00Z",
        },
    ]

    enriched = await _enrich_jobs(jobs, mock_db)
    assert len(enriched) == 2
    assert enriched[0]["po_style_code"] == "EXT-SKU-100"
    assert enriched[0]["created_at"] == gen_oid.generation_time.isoformat()
    assert enriched[1]["po_style_code"] == "EXT-SKU-200"
    assert enriched[1]["created_at"] == "2026-09-01T12:00:00Z"


def test_build_card_elements_mapped_style_and_created_date():
    job_group_mapped = {
        "po_number": "2220011455",
        "client_name": "SIYARAM SILK MILLS LTD.",
        "style_code": "SSK_00034",
        "po_style_code": "5ZE1026WFFLT-0-0602",
        "created_at": "2026-09-05T10:38:44.624735+00:00",
        "color": "CREAM",
        "description": "SAMPLE ARTICLE",
        "delivery_date": "2026-09-25",
        "sizes": [{"size": "6", "quantity": 100}],
        "total_qty": 100,
        "components": {},
        "assignments": {},
    }

    elements = _build_card_elements(job_group_mapped, None, compact=False)
    assert elements, "Card elements should not be empty"

    # Verify standard A4 PDF generation
    pdf_bytes = build_production_card(job_group_mapped, None)
    assert len(pdf_bytes) > 500
    assert b"%PDF" in pdf_bytes[:10]

    # Verify Dual A4 PDF generation
    pdf_dual_bytes = build_production_card_dual_a4(job_group_mapped, None)
    assert len(pdf_dual_bytes) > 500
    assert b"%PDF" in pdf_dual_bytes[:10]


def test_build_card_elements_unmapped_style():
    job_group_unmapped = {
        "po_number": "2220010098",
        "client_name": "SIYARAM SILK MILLS LTD.",
        "style_code": "SSK_00010",
        "po_style_code": None,
        "created_at": "",
        "color": "TAUPE",
        "description": "SANDAL",
        "delivery_date": "2026-09-20",
        "sizes": [{"size": "7", "quantity": 50}],
        "total_qty": 50,
        "components": {},
        "assignments": {},
    }

    elements = _build_card_elements(job_group_unmapped, None, compact=False)
    assert elements, "Card elements should not be empty"

    pdf_bytes = build_production_card(job_group_unmapped, None)
    assert len(pdf_bytes) > 500
    assert b"%PDF" in pdf_bytes[:10]
