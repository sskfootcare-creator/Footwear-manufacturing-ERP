"""
Test Suite for Stage 3: Flexible Per-Color Costing & Material Requirement Sheet
Verifies:
1. compute_style_costing(style, color=None) uses get_effective_bom(style, color)
   instead of style["bom"] directly when color is provided.
2. Rate override on one line for one color produces exact matching cost difference
   between overridden color and base.
3. Material Requirement Sheet for a PO in the overridden color shows the
   overridden material and quantity, not the base one.
4. compute_po_profitability passes color through so profitability reflects the real
   materials for that specific color.
"""

import pytest
from bson import ObjectId
from unittest.mock import MagicMock
from models.materials import BomItem, ColorBomOverride
from routes.styles import compute_style_costing, compute_po_profitability
from routes.materials import _compute_material_requirement
from pdf_procurement import build_material_requirement


def test_costing_difference_with_color_bom_override():
    """Verify: create a style with a rate override on one line for one color,
    compute costing for that color vs the base — confirm the cost difference matches exactly.
    """
    line1 = BomItem(
        line_id="line-vamp",
        material_id="mat-blk-01",
        material_name="Black Box Leather",
        material_code="MAT-BLK-01",
        rate=110.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="upper",
    )
    line2 = BomItem(
        line_id="line-sole",
        material_id="mat-sole-01",
        material_name="TPR Sole",
        material_code="MAT-SOL-01",
        rate=150.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="sole",
    )

    # Style with 0 overhead and margin so total_cost == materials_cost directly
    style = {
        "code": "STY-COST-01",
        "name": "Derby Cost Test",
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
        "labor": [],
        "bom": [line1, line2],
        "color_bom_overrides": {
            "Burgundy": [
                # Rate overridden: 110.0 -> 175.0 (+65.0 diff)
                ColorBomOverride(
                    line_id="line-vamp",
                    rate=175.0,
                )
            ]
        },
    }

    cost_base = compute_style_costing(style)
    cost_burgundy = compute_style_costing(style, color="Burgundy")
    cost_black = compute_style_costing(style, color="Black")

    # Base BOM cost = 110 + 150 = 260.0
    assert cost_base["materials_cost"] == 260.0
    # Black has no override -> returns base costing
    assert cost_black["materials_cost"] == 260.0

    # Burgundy has line-vamp at 175.0 -> 175 + 150 = 325.0
    assert cost_burgundy["materials_cost"] == 325.0

    # Exact difference matches rate difference (+65.0)
    rate_diff = 175.0 - 110.0
    cost_diff = cost_burgundy["materials_cost"] - cost_base["materials_cost"]
    assert cost_diff == rate_diff == 65.0


@pytest.mark.anyio
async def test_material_requirement_sheet_with_color_bom_override():
    """Verify: Generate a Material Requirement Sheet for a PO in the overridden color,
    confirm it shows the overridden material/quantity, not the base one.
    """
    line1 = BomItem(
        line_id="line-upper",
        material_id="mat-blk-01",
        material_name="Black Standard Leather",
        material_code="MAT-BLK-01",
        rate=100.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="upper",
    )
    line2 = BomItem(
        line_id="line-lining",
        material_id="mat-lin-01",
        material_name="Standard Lining",
        material_code="MAT-LIN-01",
        rate=40.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="lining",
    )

    style = {
        "code": "STY-REQ-02",
        "name": "Requirement Test Shoe",
        "bom": [line1, line2],
        "color_bom_overrides": {
            "Burgundy": [
                # Overriding upper with different material AND quantity (1.0 -> 1.5)
                ColorBomOverride(
                    line_id="line-upper",
                    material_id="mat-burg-01",
                    material_name="Burgundy Pull-Up Calfskin",
                    material_code="MAT-BURG-01",
                    quantity=1.5,
                    rate=180.0,
                )
            ]
        },
    }

    job_burgundy_id = ObjectId()
    job_black_id = ObjectId()

    job_burgundy = {
        "_id": job_burgundy_id,
        "po_number": "PO-BUR-101",
        "style_code": "STY-REQ-02",
        "color": "Burgundy",
        "quantity": 10,
        "size": "8",
    }
    job_black = {
        "_id": job_black_id,
        "po_number": "PO-BLK-102",
        "style_code": "STY-REQ-02",
        "color": "Black",
        "quantity": 10,
        "size": "8",
    }

    materials_db = [
        {"_id": "mat-blk-01", "code": "MAT-BLK-01", "name": "Black Standard Leather", "category": "upper", "rate": 100.0},
        {"_id": "mat-burg-01", "code": "MAT-BURG-01", "name": "Burgundy Pull-Up Calfskin", "category": "upper", "rate": 180.0},
        {"_id": "mat-lin-01", "code": "MAT-LIN-01", "name": "Standard Lining", "category": "lining", "rate": 40.0},
    ]

    class MockCursor:
        def __init__(self, items):
            self.items = items
        async def to_list(self, limit=1000):
            return self.items[:limit]

    def mock_jobs_find(q):
        ids = [str(x) for x in q.get("_id", {}).get("$in", [])]
        matched = []
        if str(job_burgundy_id) in ids:
            matched.append(job_burgundy)
        if str(job_black_id) in ids:
            matched.append(job_black)
        return MockCursor(matched)

    mock_db = MagicMock()
    mock_db.production_jobs.find = MagicMock(side_effect=mock_jobs_find)
    mock_db.styles.find = MagicMock(return_value=MockCursor([style]))
    mock_db.materials.find = MagicMock(return_value=MockCursor(materials_db))

    # 1. Compute Material Requirement for Burgundy PO
    req_burgundy = await _compute_material_requirement([str(job_burgundy_id)], db=mock_db)
    burgundy_mat_names = [m["name"] for m in req_burgundy["materials"]]

    # Confirm it shows the overridden material, NOT the base one
    assert "Burgundy Pull-Up Calfskin" in burgundy_mat_names
    assert "Black Standard Leather" not in burgundy_mat_names

    # Check total quantity required: 10 pairs * 1.5 qty/pair = 15.0
    burg_item = next(m for m in req_burgundy["materials"] if m["name"] == "Burgundy Pull-Up Calfskin")
    assert burg_item["total_qty_required"] == 15.0
    assert burg_item["rate"] == 180.0
    assert burg_item["total_cost"] == 2700.0  # 15.0 * 180.0

    # 2. Generate PDF for Burgundy Requirement Sheet
    pdf_bytes = build_material_requirement("PO-BUR-101 (Burgundy)", req_burgundy["jobs"], req_burgundy["materials"])
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")

    # 3. Compute Material Requirement for Black PO (Base color)
    req_black = await _compute_material_requirement([str(job_black_id)], db=mock_db)
    black_mat_names = [m["name"] for m in req_black["materials"]]

    # Confirm base shows base material and base quantity (10 pairs * 1.0 = 10.0)
    assert "Black Standard Leather" in black_mat_names
    assert "Burgundy Pull-Up Calfskin" not in black_mat_names
    blk_item = next(m for m in req_black["materials"] if m["name"] == "Black Standard Leather")
    assert blk_item["total_qty_required"] == 10.0


@pytest.mark.anyio
async def test_compute_po_profitability_with_color_bom_override():
    """Verify: compute_po_profitability reflects overridden material costs
    when PO line specifies the overridden color.
    """
    line1 = BomItem(
        line_id="line-vamp",
        material_name="Base Vamp Leather",
        rate=100.0,
        quantity=1.0,
    )
    style = {
        "code": "STY-PROF-01",
        "bom": [line1],
        "overhead_pct": 0,
        "packing_cost": 0,
        "labor": [],
        "color_bom_overrides": {
            "Burgundy": [
                ColorBomOverride(line_id="line-vamp", rate=160.0)
            ]
        },
    }

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = MagicMock(return_value=[])
    mock_db.production_jobs.find = MagicMock(return_value=mock_cursor)

    po_line_burgundy = {
        "style_code": "STY-PROF-01",
        "color": "Burgundy",
        "unit_price": 250.0,
    }
    po_line_black = {
        "style_code": "STY-PROF-01",
        "color": "Black",
        "unit_price": 250.0,
    }

    prof_burgundy = await compute_po_profitability(po_line_burgundy, style, db=mock_db)
    prof_black = await compute_po_profitability(po_line_black, style, db=mock_db)

    # Burgundy BOM cost is 160.0 -> Profit = 250 - 160 = 90.0
    assert prof_burgundy["bom_cost"] == 160.0
    assert prof_burgundy["total_cost"] == 160.0
    assert prof_burgundy["profit"] == 90.0

    # Black BOM cost is 100.0 -> Profit = 250 - 100 = 150.0
    assert prof_black["bom_cost"] == 100.0
    assert prof_black["total_cost"] == 100.0
    assert prof_black["profit"] == 150.0
