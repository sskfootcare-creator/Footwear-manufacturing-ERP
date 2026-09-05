import io
import pytest
import pypdf
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock

from models.materials import BomItem
from models.orders import PRODUCTION_STAGES, ProductionJobDoc
from routes.materials import _compute_material_requirement
from pdf_procurement import build_material_requirement


def test_planning_stage_configuration():
    """Verify 'planning' is the initial stage in PRODUCTION_STAGES and ProductionJobDoc."""
    assert "planning" in PRODUCTION_STAGES
    assert PRODUCTION_STAGES[0] == "planning"
    job = ProductionJobDoc(style_code="SSK008", quantity=100)
    assert job.stage == "planning"


@pytest.mark.anyio
async def test_compute_material_requirement_by_color_split():
    """
    Test user scenario:
    Style SSK008 with Black (100 pairs) and Cream (100 pairs).
    Yield is 10 pairs/meter.
    Black needs 10m of black material, Cream needs 10m of cream material.
    _compute_material_requirement should separate them in by_color and aggregate correctly.
    """
    job_black_id = ObjectId()
    job_cream_id = ObjectId()

    style_id = ObjectId()
    style_doc = {
        "_id": style_id,
        "code": "SSK008",
        "name": "SSK Oxford 008",
        "bom": [
            {
                "line_id": "line-upper",
                "material_id": "mat-rexine",
                "material_code": "MAT-REX",
                "material_name": "Rexine Upper",
                "section": "Upper Top",
                "unit": "MTR",
                "rate": 200.0,
                "quantity": 1.0,
                "yield_per_unit": 10.0,  # 10 pairs per meter
                "waste_pct": 0.0,
                "color": "",
            },
            {
                "line_id": "line-lining",
                "material_id": "mat-lining",
                "material_code": "MAT-LIN",
                "material_name": "Lining Fabric",
                "section": "Lining",
                "unit": "MTR",
                "rate": 100.0,
                "quantity": 1.0,
                "yield_per_unit": 10.0,  # 10 pairs per meter
                "waste_pct": 0.0,
                "color": "",
            }
        ],
        "color_bom_overrides": {
            "Black": [
                {
                    "line_id": "line-upper",
                    "color": "Black",
                },
                {
                    "line_id": "line-lining",
                    "color": "Gun Metal",
                }
            ],
            "Cream": [
                {
                    "line_id": "line-upper",
                    "color": "Cream",
                },
                {
                    "line_id": "line-lining",
                    "color": "Silver",
                }
            ]
        }
    }

    job_black = {
        "_id": job_black_id,
        "po_number": "PO-101",
        "style_code": "SSK008",
        "color": "Black",
        "quantity": 100,
        "size": "8",
    }
    job_cream = {
        "_id": job_cream_id,
        "po_number": "PO-101",
        "style_code": "SSK008",
        "color": "Cream",
        "quantity": 100,
        "size": "9",
    }

    mock_db = MagicMock()

    # mock production_jobs query
    mock_jobs_cursor = MagicMock()
    mock_jobs_cursor.to_list = AsyncMock(return_value=[job_black, job_cream])
    mock_db.production_jobs.find.return_value = mock_jobs_cursor

    # mock styles query
    mock_styles_cursor = MagicMock()
    mock_styles_cursor.to_list = AsyncMock(return_value=[style_doc])
    mock_db.styles.find.return_value = mock_styles_cursor

    # mock materials query
    mock_materials_cursor = MagicMock()
    mock_materials_cursor.to_list = AsyncMock(return_value=[
        {"_id": ObjectId(), "code": "MAT-REX", "name": "Rexine Upper", "unit": "MTR", "category": "Upper Top", "rate": 200.0},
        {"_id": ObjectId(), "code": "MAT-LIN", "name": "Lining Fabric", "unit": "MTR", "category": "Lining", "rate": 100.0},
    ])
    mock_db.materials.find.return_value = mock_materials_cursor

    result = await _compute_material_requirement([str(job_black_id), str(job_cream_id)], db=mock_db)

    assert "by_color" in result
    by_color = result["by_color"]

    # Verify Black breakdown
    assert "Black" in by_color
    black_info = by_color["Black"]
    assert black_info["total_pairs"] == 100
    black_mats = { (m["code"], m["color"]): m for m in black_info["materials"] }
    # 100 pairs / 10 pairs/meter = 10.0 meters
    assert ("MAT-REX", "Black") in black_mats
    assert black_mats[("MAT-REX", "Black")]["total_qty_required"] == 10.0
    assert ("MAT-LIN", "Gun Metal") in black_mats
    assert black_mats[("MAT-LIN", "Gun Metal")]["total_qty_required"] == 10.0

    # Verify Cream breakdown
    assert "Cream" in by_color
    cream_info = by_color["Cream"]
    assert cream_info["total_pairs"] == 100
    cream_mats = { (m["code"], m["color"]): m for m in cream_info["materials"] }
    # 100 pairs / 10 pairs/meter = 10.0 meters
    assert ("MAT-REX", "Cream") in cream_mats
    assert cream_mats[("MAT-REX", "Cream")]["total_qty_required"] == 10.0
    assert ("MAT-LIN", "Silver") in cream_mats
    assert cream_mats[("MAT-LIN", "Silver")]["total_qty_required"] == 10.0

    # Test PDF generation with split_by_color=True
    pdf_bytes = build_material_requirement(
        scope_label="PO-101 SSK008 Black & Cream",
        jobs_summary=result["jobs"],
        material_lines=result["materials"],
        notes="Urgent production",
        split_by_color=True,
        by_color=result["by_color"],
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000

    # Verify PDF content with pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    all_text = " ".join(page.extract_text() for page in reader.pages)
    assert "PO-101" in all_text
    assert "COLOR VARIANT: BLACK" in all_text
    assert "COLOR VARIANT: CREAM" in all_text
    assert "CONSOLIDATED TOTAL REQUIREMENT" in all_text
    assert "Gun Metal" in all_text
    assert "Silver" in all_text
