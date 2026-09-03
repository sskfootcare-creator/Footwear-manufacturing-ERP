import pytest
from models.styles import StyleIn
from models.materials import BomItem, ColorMaterialOverride
from routes.styles import get_effective_bom, compute_style_costing
from routes.pos import compute_po_profitability


def test_style_in_model_validation():
    payload = {
        "name": "Derby Classic",
        "category": "Footwear",
        "bom": [
            {
                "material_id": "mat-up-1",
                "material_name": "Base Black Leather",
                "material_code": "MAT-UP-01",
                "rate": 100.0,
                "quantity": 1.5,
                "yield_per_unit": 1.0,
                "section": "upper",
            },
            {
                "material_id": "mat-ins-1",
                "material_name": "Standard Insole Board",
                "material_code": "MAT-INS-01",
                "rate": 40.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "section": "insole",
            },
        ],
        "color_material_overrides": {
            "Tan": {
                "upper": {
                    "material_id": "mat-up-tan",
                    "material_name": "Tan Suede Leather",
                    "material_code": "MAT-UP-TAN",
                    "rate": 150.0,
                }
            }
        },
    }
    style = StyleIn(**payload)
    assert "Tan" in style.color_material_overrides
    assert "upper" in style.color_material_overrides["Tan"]
    ov = style.color_material_overrides["Tan"]["upper"]
    assert ov.material_name == "Tan Suede Leather"
    assert ov.rate == 150.0
    assert ov.quantity is None


def test_get_effective_bom_simple_overrides():
    base_style = {
        "bom": [
            {
                "material_id": "m1",
                "material_name": "Standard Black Leather",
                "material_code": "MAT-BLK",
                "rate": 100.0,
                "quantity": 2.0,
                "yield_per_unit": 1.2,
                "waste_pct": 5.0,
                "section": "upper",
                "component": "Upper Vamp",
            },
            {
                "material_id": "m2",
                "material_name": "Standard Black Collar",
                "material_code": "MAT-COL-BLK",
                "rate": 80.0,
                "quantity": 0.5,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "upper",
                "component": "Upper Collar",
            },
            {
                "material_id": "m3",
                "material_name": "Texon Board",
                "material_code": "MAT-TEX",
                "rate": 35.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "insole",
            },
            {
                "material_id": "m4",
                "material_name": "Standard Insole Cover",
                "material_code": "MAT-COV",
                "rate": 20.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "cover",
            },
        ],
        "color_material_overrides": {
            "Cherry": {
                "upper": {
                    "material_id": "m-cherry",
                    "material_name": "Cherry Patent Leather",
                    "material_code": "MAT-CHR",
                    "rate": 160.0,
                }
            }
        },
    }

    # 1. No color provided -> returns base BOM untouched
    bom_none = get_effective_bom(base_style, None)
    assert len(bom_none) == 4
    assert bom_none[0].material_name == "Standard Black Leather"
    assert bom_none[0].rate == 100.0

    # 2. Color with no overrides -> returns base BOM untouched
    bom_black = get_effective_bom(base_style, "Black")
    assert len(bom_black) == 4
    assert bom_black[0].material_name == "Standard Black Leather"
    assert bom_black[0].rate == 100.0

    # 3. Color with upper override -> BOTH upper lines get overridden, insole & cover untouched
    bom_cherry = get_effective_bom(base_style, "Cherry")
    assert len(bom_cherry) == 4

    # Both upper lines have Cherry material and rate, but keep their original quantity and yield
    up1 = bom_cherry[0]
    assert up1.material_name == "Cherry Patent Leather"
    assert up1.material_code == "MAT-CHR"
    assert up1.rate == 160.0
    assert up1.quantity == 2.0
    assert up1.yield_per_unit == 1.2
    assert up1.waste_pct == 5.0
    assert up1.component == "Upper Vamp"

    up2 = bom_cherry[1]
    assert up2.material_name == "Cherry Patent Leather"
    assert up2.rate == 160.0
    assert up2.quantity == 0.5
    assert up2.component == "Upper Collar"

    # Insole and cover are untouched
    assert bom_cherry[2].material_name == "Texon Board"
    assert bom_cherry[2].rate == 35.0
    assert bom_cherry[3].material_name == "Standard Insole Cover"
    assert bom_cherry[3].rate == 20.0

    # 4. Case-insensitivity check ("cherry" matches "Cherry")
    bom_lower = get_effective_bom(base_style, "cherry")
    assert bom_lower[0].material_name == "Cherry Patent Leather"


def test_costing_with_simple_override():
    base_style = {
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
        "labor": [],
        "bom": [
            {
                "material_id": "m1",
                "material_name": "Base Leather",
                "material_code": "M1",
                "rate": 100.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "upper",
            },
            {
                "material_id": "m2",
                "material_name": "Insole Sheet",
                "material_code": "M2",
                "rate": 50.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "insole",
            },
        ],
        "color_material_overrides": {
            "Gold": {
                "upper": {
                    "material_id": "m-gold",
                    "material_name": "Metallic Gold Foil",
                    "material_code": "M-GOLD",
                    "rate": 180.0,  # +80 difference
                }
            }
        },
    }

    cost_base = compute_style_costing(base_style)
    assert cost_base["materials_cost"] == 150.0

    cost_gold = compute_style_costing(base_style, color="Gold")
    assert cost_gold["materials_cost"] == 230.0  # 180 + 50 = 230


@pytest.mark.anyio
async def test_compute_po_profitability_with_simple_override():
    base_style = {
        "code": "STY-800",
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
        "labor": [],
        "bom": [
            {
                "material_id": "m1",
                "material_name": "Base Leather",
                "material_code": "M1",
                "rate": 100.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "upper",
            },
        ],
        "color_material_overrides": {
            "Premium": {
                "upper": {
                    "material_id": "m-prem",
                    "material_name": "Italian Calfskin",
                    "material_code": "M-PREM",
                    "rate": 250.0,
                }
            }
        },
    }

    # PO line with base color
    po_line_base = {"style_code": "STY-800", "unit_price": 300.0, "color": "Regular"}
    prof_base = await compute_po_profitability(po_line_base, base_style)
    assert prof_base["bom_cost"] == 100.0
    assert prof_base["profit"] == 200.0

    # PO line with Premium color override
    po_line_prem = {"style_code": "STY-800", "unit_price": 300.0, "color": "Premium"}
    prof_prem = await compute_po_profitability(po_line_prem, base_style)
    assert prof_prem["bom_cost"] == 250.0
    assert prof_prem["profit"] == 50.0
