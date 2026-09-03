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


def test_get_effective_bom_upper_and_insole_verification():
    """Verify: unit-test with a base BOM containing one 'upper' line and one 'insole'
    line, plus a color overriding only 'upper' — confirm the result has the override
    applied to the upper line and the insole line unchanged. Test a color with no
    overrides — confirm the base BOM returns completely unchanged."""
    base_style = {
        "bom": [
            {
                "material_id": "mat-up-base",
                "material_name": "Base Black Leather",
                "material_code": "MAT-BASE-UP",
                "rate": 100.0,
                "quantity": 1.5,
                "yield_per_unit": 1.0,
                "waste_pct": 2.0,
                "section": "upper",
                "component": "Upper Vamp",
            },
            {
                "material_id": "mat-ins-base",
                "material_name": "Base Insole Board",
                "material_code": "MAT-BASE-INS",
                "rate": 40.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "insole",
                "component": "Insole",
            },
        ],
        "color_material_overrides": {
            "Tan": {
                "upper": {
                    "material_id": "mat-up-tan",
                    "material_name": "Tan Suede Leather",
                    "material_code": "MAT-TAN-UP",
                    "rate": 160.0,
                    # quantity not specified: inherits base BOM line quantity (1.5)
                }
            }
        },
    }

    # 1. Color overriding only "upper" -> upper line has override applied, insole line unchanged
    res_tan = get_effective_bom(base_style, "Tan")
    assert len(res_tan) == 2

    # Upper line has override values
    tan_up = res_tan[0]
    assert tan_up.material_id == "mat-up-tan"
    assert tan_up.material_name == "Tan Suede Leather"
    assert tan_up.material_code == "MAT-TAN-UP"
    assert tan_up.rate == 160.0
    # Unspecified fields in override inherit base BOM line
    assert tan_up.quantity == 1.5
    assert tan_up.yield_per_unit == 1.0
    assert tan_up.waste_pct == 2.0
    assert tan_up.section == "upper"
    assert tan_up.component == "Upper Vamp"

    # Insole line remains unchanged
    tan_ins = res_tan[1]
    assert tan_ins.material_id == "mat-ins-base"
    assert tan_ins.material_name == "Base Insole Board"
    assert tan_ins.material_code == "MAT-BASE-INS"
    assert tan_ins.rate == 40.0
    assert tan_ins.quantity == 1.0
    assert tan_ins.section == "insole"

    # Also verify dict access works seamlessly on lines
    assert tan_up["material_name"] == "Tan Suede Leather"
    assert tan_up["rate"] == 160.0
    assert tan_ins["rate"] == 40.0

    # 2. Test a color with no overrides (e.g. "Black") -> base BOM returns completely unchanged
    res_black = get_effective_bom(base_style, "Black")
    assert len(res_black) == 2
    assert res_black[0].material_id == "mat-up-base"
    assert res_black[0].material_name == "Base Black Leather"
    assert res_black[0].material_code == "MAT-BASE-UP"
    assert res_black[0].rate == 100.0
    assert res_black[0].quantity == 1.5
    assert res_black[1].material_id == "mat-ins-base"
    assert res_black[1].material_name == "Base Insole Board"
    assert res_black[1].rate == 40.0

    # 3. Test color=None -> base BOM returns completely unchanged
    res_none = get_effective_bom(base_style, None)
    assert len(res_none) == 2
    assert res_none[0].material_id == "mat-up-base"
    assert res_none[0].rate == 100.0
    assert res_none[1].material_id == "mat-ins-base"
    assert res_none[1].rate == 40.0


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


@pytest.mark.anyio
async def test_costing_difference_and_material_requirement_sheet_with_override():
    """Verify: create a style with an upper-material override for one color at a
    different rate, compute costing for that color vs the base — confirm the cost
    difference matches the rate difference correctly. Generate a Material Requirement
    Sheet for a PO in the overridden color, confirm it shows the overridden material,
    not the base one."""
    from bson import ObjectId
    from unittest.mock import MagicMock
    from routes.materials import _compute_material_requirement
    from pdf_procurement import build_material_requirement

    style = {
        "code": "STY-REQ-01",
        "name": "Derby Classic",
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
        "labor": [],
        "bom": [
            {
                "material_id": "mat-base-up",
                "material_name": "Base Black Leather",
                "material_code": "MAT-BASE-UP",
                "rate": 100.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "upper",
            },
            {
                "material_id": "mat-base-ins",
                "material_name": "Standard Insole Board",
                "material_code": "MAT-BASE-INS",
                "rate": 30.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "insole",
            },
        ],
        "color_material_overrides": {
            "Tan": {
                "upper": {
                    "material_id": "mat-tan-up",
                    "material_name": "Tan Suede Leather",
                    "material_code": "MAT-TAN-UP",
                    "rate": 160.0,  # rate difference = +60.0
                }
            }
        },
    }

    # 1. Compute costing for Tan vs base and confirm cost diff matches rate diff
    cost_base = compute_style_costing(style)
    cost_tan = compute_style_costing(style, color="Tan")

    rate_diff = 160.0 - 100.0
    cost_diff = cost_tan["materials_cost"] - cost_base["materials_cost"]
    assert cost_base["materials_cost"] == 130.0
    assert cost_tan["materials_cost"] == 190.0
    assert cost_diff == rate_diff == 60.0

    # 2. Material Requirement Sheet generation for PO in overridden color ("Tan")
    class MockCursor:
        def __init__(self, items):
            self.items = items
        async def to_list(self, limit=1000):
            return self.items[:limit]

    job_tan_id = ObjectId()
    job_black_id = ObjectId()

    job_tan = {
        "_id": job_tan_id,
        "po_number": "PO-TAN-901",
        "style_code": "STY-REQ-01",
        "color": "Tan",
        "quantity": 20,
        "size": "8",
    }
    job_black = {
        "_id": job_black_id,
        "po_number": "PO-BLK-902",
        "style_code": "STY-REQ-01",
        "color": "Black",
        "quantity": 20,
        "size": "8",
    }

    materials_db = [
        {"_id": "mat-base-up", "code": "MAT-BASE-UP", "name": "Base Black Leather", "category": "upper", "rate": 100.0},
        {"_id": "mat-tan-up", "code": "MAT-TAN-UP", "name": "Tan Suede Leather", "category": "upper", "rate": 160.0},
        {"_id": "mat-base-ins", "code": "MAT-BASE-INS", "name": "Standard Insole Board", "category": "insole", "rate": 30.0},
    ]

    def mock_jobs_find(q):
        ids = [str(x) for x in q.get("_id", {}).get("$in", [])]
        matched = []
        if str(job_tan_id) in ids:
            matched.append(job_tan)
        if str(job_black_id) in ids:
            matched.append(job_black)
        return MockCursor(matched)

    mock_db = MagicMock()
    mock_db.production_jobs.find = MagicMock(side_effect=mock_jobs_find)
    mock_db.styles.find = MagicMock(return_value=MockCursor([style]))
    mock_db.materials.find = MagicMock(return_value=MockCursor(materials_db))

    req_tan = await _compute_material_requirement([str(job_tan_id)], db=mock_db)
    tan_mat_names = [m["name"] for m in req_tan["materials"]]

    # Confirm it shows the overridden material, not the base one
    assert "Tan Suede Leather" in tan_mat_names
    assert "Base Black Leather" not in tan_mat_names

    tan_mat = next(m for m in req_tan["materials"] if m["name"] == "Tan Suede Leather")
    assert tan_mat["total_qty_required"] == 20.0
    assert tan_mat["rate"] == 160.0
    assert tan_mat["total_cost"] == 3200.0

    # Generate Material Requirement Sheet PDF
    pdf_bytes = build_material_requirement("PO-TAN-901 (Tan)", req_tan["jobs"], req_tan["materials"])
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")

    # Confirm base color ("Black") reflects the base material, not the overridden one
    req_black = await _compute_material_requirement([str(job_black_id)], db=mock_db)
    black_mat_names = [m["name"] for m in req_black["materials"]]
    assert "Base Black Leather" in black_mat_names
    assert "Tan Suede Leather" not in black_mat_names


@pytest.fixture
def test_api():
    """Provides an authenticated client (requests.Session against live server or TestClient)
    and base API URL."""
    import os
    import requests
    try:
        s = requests.Session()
        r = s.post("http://localhost:8000/api/auth/login", json={"email": "admin@sskfootcare.com", "password": "Admin@123"}, timeout=2)
        if r.status_code == 200:
            yield s, "http://localhost:8000/api"
            return
    except Exception:
        pass

    import server
    from motor.motor_asyncio import AsyncIOMotorClient
    server.client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    server.db = server.client[os.environ.get("DB_NAME", "test_ssk_footcare")]

    from fastapi.testclient import TestClient
    with TestClient(server.app, base_url="http://testserver/api") as tc:
        r = tc.post("/auth/login", json={"email": "admin@sskfootcare.com", "password": "Admin@123"})
        assert r.status_code == 200, f"TestClient login failed: {r.text}"
        yield tc, ""


def test_persist_style_with_upper_override_via_api(test_api):
    """Verify: save a style with a base BOM and one color specifying an override for just
    the 'upper' section, confirm it persists correctly via the API."""
    client, api_url = test_api
    import time
    style_payload = {
        "name": f"Test Simple Override Oxford {int(time.time())}",
        "category": "Footwear",
        "base_size": "7",
        "overhead_pct": 5.0,
        "packing_cost": 10.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
        "bom": [
            {
                "material_id": "mat-base-up",
                "material_name": "Base Black Leather",
                "material_code": "MAT-BASE-BLK",
                "rate": 100.0,
                "quantity": 1.5,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "upper",
            },
            {
                "material_id": "mat-base-insole",
                "material_name": "Standard Insole Board",
                "material_code": "MAT-BASE-INS",
                "rate": 35.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "section": "insole",
            },
        ],
        "color_material_overrides": {
            "Tan": {
                "upper": {
                    "material_id": "mat-tan-up",
                    "material_name": "Tan Suede Leather",
                    "material_code": "MAT-TAN-UP",
                    "rate": 160.0,
                    # quantity omitted to test inheriting base BOM line's quantity (1.5)
                }
            }
        },
    }

    # 1. Save style via API
    res = client.post(f"{api_url}/styles", json=style_payload)
    assert res.status_code in [200, 201], f"Style creation failed: {res.text}"
    created_data = res.json()
    style_id = created_data.get("id")
    assert style_id, "Response should include style ID"

    try:
        # 2. Confirm persistence in GET /styles/{id}
        get_res = client.get(f"{api_url}/styles/{style_id}")
        assert get_res.status_code == 200, f"Get style failed: {get_res.text}"
        persisted_style = get_res.json()

        # Check color_material_overrides is persisted accurately
        assert "color_material_overrides" in persisted_style
        overrides = persisted_style["color_material_overrides"]
        assert "Tan" in overrides, "Color 'Tan' must be in color_material_overrides"
        assert "upper" in overrides["Tan"], "Section 'upper' must be overridden for 'Tan'"

        tan_upper = overrides["Tan"]["upper"]
        assert tan_upper["material_id"] == "mat-tan-up"
        assert tan_upper["material_name"] == "Tan Suede Leather"
        assert tan_upper["material_code"] == "MAT-TAN-UP"
        assert tan_upper["rate"] == 160.0

        # Colors without overrides must NOT be in color_material_overrides
        assert "Black" not in overrides

        # 3. Confirm GET /styles/{id}/effective-bom for Tan has the override
        eff_tan_res = client.get(f"{api_url}/styles/{style_id}/effective-bom?color=Tan")
        assert eff_tan_res.status_code == 200
        eff_tan_bom = eff_tan_res.json()
        assert len(eff_tan_bom) == 2

        tan_up_line = next(b for b in eff_tan_bom if b.get("section") == "upper")
        assert tan_up_line["material_code"] == "MAT-TAN-UP"
        assert tan_up_line["material_name"] == "Tan Suede Leather"
        assert tan_up_line["rate"] == 160.0
        assert tan_up_line["quantity"] == 1.5  # inherited from base BOM

        # Insole line remains base BOM
        insole_line = next(b for b in eff_tan_bom if b.get("section") == "insole")
        assert insole_line["material_code"] == "MAT-BASE-INS"
        assert insole_line["rate"] == 35.0

        # 4. Confirm GET /styles/{id}/effective-bom for Black uses base BOM completely
        eff_blk_res = client.get(f"{api_url}/styles/{style_id}/effective-bom?color=Black")
        assert eff_blk_res.status_code == 200
        eff_blk_bom = eff_blk_res.json()
        blk_up_line = next(b for b in eff_blk_bom if b.get("section") == "upper")
        assert blk_up_line["material_code"] == "MAT-BASE-BLK"
        assert blk_up_line["rate"] == 100.0

    finally:
        # Clean up created style
        client.delete(f"{api_url}/styles/{style_id}")


def test_get_effective_bom_override_more_than_one_material():
    """Verify: A color can override MORE THAN ONE material in the same section or across
    different sections independently (e.g. Vamp and Collar both in 'upper' overridden with
    different materials, plus insole overridden)."""
    base_style = {
        "bom": [
            {
                "line_id": "line-vamp",
                "material_id": "m-blk-vamp",
                "material_name": "Black Box Leather",
                "material_code": "MAT-BLK-VAMP",
                "rate": 120.0,
                "quantity": 1.2,
                "yield_per_unit": 1.0,
                "section": "upper",
                "component": "Vamp",
            },
            {
                "line_id": "line-collar",
                "material_id": "m-blk-collar",
                "material_name": "Black Suede Trim",
                "material_code": "MAT-BLK-COLLAR",
                "rate": 80.0,
                "quantity": 0.4,
                "yield_per_unit": 1.0,
                "section": "upper",
                "component": "Collar",
            },
            {
                "line_id": "line-insole",
                "material_id": "m-ins",
                "material_name": "Texon Board",
                "material_code": "MAT-TEX",
                "rate": 30.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "section": "insole",
            },
        ],
        "color_material_overrides": {
            "Tan/Brown": {
                # Override 1: Vamp material
                "line-vamp": {
                    "material_id": "m-tan-vamp",
                    "material_name": "Tan Full Grain Leather",
                    "material_code": "MAT-TAN-VAMP",
                    "rate": 170.0,
                },
                # Override 2: Collar material (second material in the SAME 'upper' section)
                "line-collar": {
                    "material_id": "m-brn-collar",
                    "material_name": "Brown Suede Trim",
                    "material_code": "MAT-BRN-COLLAR",
                    "rate": 95.0,
                },
                # Override 3: Insole material
                "insole": {
                    "material_id": "m-cushion",
                    "material_name": "EVA Molded Insole",
                    "material_code": "MAT-EVA-INS",
                    "rate": 55.0,
                },
            }
        },
    }

    eff_bom = get_effective_bom(base_style, "Tan/Brown")
    assert len(eff_bom) == 3

    # Confirm Material 1 was overridden
    vamp = next(b for b in eff_bom if b.line_id == "line-vamp")
    assert vamp.material_name == "Tan Full Grain Leather"
    assert vamp.rate == 170.0
    assert vamp.quantity == 1.2

    # Confirm Material 2 was overridden with its own different material
    collar = next(b for b in eff_bom if b.line_id == "line-collar")
    assert collar.material_name == "Brown Suede Trim"
    assert collar.rate == 95.0
    assert collar.quantity == 0.4

    # Confirm Material 3 was overridden
    insole = next(b for b in eff_bom if b.line_id == "line-insole")
    assert insole.material_name == "EVA Molded Insole"
    assert insole.rate == 55.0


