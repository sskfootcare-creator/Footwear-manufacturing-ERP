import os
import sys
import time
import pytest
import httpx

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "Admin@123")


def test_bom_item_model_color_field():
    """Unit test for BomItem model color field default and custom values."""
    from models.materials import BomItem
    from models.styles import StyleIn

    # Default color should be empty string
    item_default = BomItem(
        material_id="mat123",
        material_name="Synthetic Leather",
        material_code="SL-01",
        unit="sqft",
        rate=120.0,
        quantity=1.2
    )
    assert item_default.color == ""
    dumped = item_default.model_dump()
    assert "color" in dumped
    assert dumped["color"] == ""

    # Specified color value
    item_with_color = BomItem(
        material_id="mat123",
        material_name="Synthetic Leather",
        material_code="SL-01",
        unit="sqft",
        rate=120.0,
        quantity=1.2,
        color="Tan Brown"
    )
    assert item_with_color.color == "Tan Brown"
    dumped_color = item_with_color.model_dump()
    assert dumped_color["color"] == "Tan Brown"

    # Tested in StyleIn payload
    style = StyleIn(
        name="Derby Classic",
        category="Footwear",
        bom=[item_with_color]
    )
    assert len(style.bom) == 1
    assert style.bom[0].color == "Tan Brown"


def test_style_in_mould_fields():
    """Unit test for insole_mould_name and sole_mould_name fields on core StyleIn model."""
    from models.styles import StyleIn, StyleLifecycleUpsert

    # 1. Defaults are None (optional, no validation error when omitted)
    style_default = StyleIn(
        name="Slipper Basic",
        category="Footwear"
    )
    assert style_default.insole_mould_name is None
    assert style_default.sole_mould_name is None
    dumped = style_default.model_dump()
    assert dumped["insole_mould_name"] is None
    assert dumped["sole_mould_name"] is None

    # 2. Populated fields are preserved and serialized correctly
    style_with_moulds = StyleIn(
        name="Sport Runner Pro",
        category="Footwear",
        insole_mould_name="DIE-INS-402",
        sole_mould_name="MOULD-EVA-99"
    )
    assert style_with_moulds.insole_mould_name == "DIE-INS-402"
    assert style_with_moulds.sole_mould_name == "MOULD-EVA-99"
    dumped_moulds = style_with_moulds.model_dump()
    assert dumped_moulds["insole_mould_name"] == "DIE-INS-402"
    assert dumped_moulds["sole_mould_name"] == "MOULD-EVA-99"

    # 3. Backward compatibility: StyleLifecycleUpsert still retains sole_mould_name
    lifecycle = StyleLifecycleUpsert(
        sole_mould_name="MOULD-LIFECYCLE-01"
    )
    assert lifecycle.sole_mould_name == "MOULD-LIFECYCLE-01"



def test_pdf_procurement_swatch_color_rendering():
    """Unit test to verify swatch box rendering with specified colors, blank colors, and non-swatch items."""
    from pdf_procurement import build_material_requirement, _make_swatch_box
    from reportlab.platypus import Table

    # 1. Test _make_swatch_box helper
    # With color: returns Table with swatch box and color text
    cell_with_color = _make_swatch_box("Midnight Blue")
    assert isinstance(cell_with_color, Table)
    # Check that the table has 2 rows (box + text)
    assert len(cell_with_color._cellvalues) == 2

    # Without color: returns single box table (1 row)
    cell_no_color = _make_swatch_box("")
    assert isinstance(cell_no_color, Table)
    assert len(cell_no_color._cellvalues) == 1

    # Whitespace only: returns single box table (1 row)
    cell_whitespace = _make_swatch_box("   ")
    assert len(cell_whitespace._cellvalues) == 1

    # 2. Test full PDF generation
    jobs_summary = [
        {"po_number": "PO-999", "style_code": "SSK-001", "color": "Navy Blue", "total_pairs": 100, "sizes_text": "7, 8, 9"}
    ]
    material_lines = [
        # Swatch category WITH color
        {"code": "MAT-UPPER-01", "name": "Grain Leather", "category": "upper", "unit": "sqft", "rate": 150.0, "total_qty_required": 120.0, "total_cost": 18000.0, "color": "Royal Sapphire Blue"},
        # Swatch category WITHOUT color (legacy/agnostic)
        {"code": "MAT-SOLE-01", "name": "TPR Sole", "category": "sole", "unit": "pair", "rate": 80.0, "total_qty_required": 100.0, "total_cost": 8000.0, "color": ""},
        # Non-swatch category (consumable)
        {"code": "MAT-ADH-01", "name": "PU Adhesive", "category": "consumable", "unit": "kg", "rate": 250.0, "total_qty_required": 5.0, "total_cost": 1250.0, "color": "Transparent"}
    ]

    pdf_bytes = build_material_requirement("Test Scope", jobs_summary, material_lines, notes="Test notes")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF-")

    # 3. Test PDF generation with sole size_breakdown
    material_lines_with_breakdown = [
        {"code": "MAT-UPPER-01", "name": "Grain Leather", "category": "upper", "unit": "sqft", "rate": 150.0, "total_qty_required": 120.0, "total_cost": 18000.0, "color": "Royal Sapphire Blue"},
        {"code": "MAT-SOLE-01", "name": "TPR Sole", "category": "sole", "unit": "pair", "rate": 80.0, "total_qty_required": 273.0, "total_cost": 21840.0, "color": "Black", "size_breakdown": {"6": 90, "7": 95, "8": 88}},
        {"code": "MAT-ADH-01", "name": "PU Adhesive", "category": "consumable", "unit": "kg", "rate": 250.0, "total_qty_required": 5.0, "total_cost": 1250.0, "color": "Transparent"}
    ]
    pdf_bytes_bd = build_material_requirement("PO Batch PO-101", jobs_summary, material_lines_with_breakdown, notes="Test notes")
    assert isinstance(pdf_bytes_bd, bytes)
    assert len(pdf_bytes_bd) > 0
    assert pdf_bytes_bd.startswith(b"%PDF-")


@pytest.mark.anyio
async def test_compute_material_requirement_sole_size_breakdown():
    """Unit test to verify _compute_material_requirement computes size_breakdown for soles while keeping bulk materials aggregated."""
    from routes.materials import _compute_material_requirement
    from bson import ObjectId

    job1_id = ObjectId()
    job2_id = ObjectId()
    job3_id = ObjectId()
    mat_leather_id = ObjectId()
    mat_sole_id = ObjectId()

    mock_materials = [
        {"_id": mat_leather_id, "code": "MAT-UPP-1", "name": "Leather", "category": "upper", "unit": "sqft", "rate": 100.0},
        {"_id": mat_sole_id, "code": "MAT-SOL-1", "name": "Rubber Sole", "category": "sole", "unit": "pair", "rate": 50.0},
    ]

    mock_styles = [
        {
            "_id": ObjectId(),
            "code": "STY-001",
            "name": "Classic Derby",
            "bom": [
                {
                    "material_id": str(mat_leather_id),
                    "material_code": "MAT-UPP-1",
                    "material_name": "Leather",
                    "unit": "sqft",
                    "quantity": 1.5,
                    "yield_per_unit": 1.0,
                    "waste_pct": 0.0,
                    "color": "Brown",
                    "section": "upper"
                },
                {
                    "material_id": str(mat_sole_id),
                    "material_code": "MAT-SOL-1",
                    "material_name": "Rubber Sole",
                    "unit": "pair",
                    "quantity": 1.0,
                    "yield_per_unit": 1.0,
                    "waste_pct": 0.0,
                    "color": "Black",
                    "section": "sole"
                }
            ]
        }
    ]

    mock_jobs = [
        {"_id": job1_id, "po_number": "PO-100", "style_code": "STY-001", "color": "Brown", "size": "6", "quantity": 90},
        {"_id": job2_id, "po_number": "PO-100", "style_code": "STY-001", "color": "Brown", "size": "7", "quantity": 95},
        {"_id": job3_id, "po_number": "PO-100", "style_code": "STY-001", "color": "Brown", "size": "8", "quantity": 88},
    ]

    class AsyncMockCursor:
        def __init__(self, data):
            self.data = data
        async def to_list(self, length=None):
            return self.data

    class MockCollection:
        def __init__(self, data):
            self.data = data
        def find(self, query=None):
            if not query:
                return AsyncMockCursor(self.data)
            if "_id" in query and "$in" in query["_id"]:
                filtered = [d for d in self.data if d["_id"] in query["_id"]["$in"]]
                return AsyncMockCursor(filtered)
            if "code" in query and "$in" in query["code"]:
                filtered = [d for d in self.data if d["code"] in query["code"]["$in"]]
                return AsyncMockCursor(filtered)
            return AsyncMockCursor(self.data)

    class MockDB:
        def __init__(self):
            self.production_jobs = MockCollection(mock_jobs)
            self.styles = MockCollection(mock_styles)
            self.materials = MockCollection(mock_materials)

    db = MockDB()
    res = await _compute_material_requirement([str(job1_id), str(job2_id), str(job3_id)], db=db)

    assert "materials" in res
    assert len(res["materials"]) == 2

    # Find sole and upper
    sole_line = next(m for m in res["materials"] if m["code"] == "MAT-SOL-1")
    upper_line = next(m for m in res["materials"] if m["code"] == "MAT-UPP-1")

    # Sole must have size_breakdown matching per-size quantities
    assert sole_line["size_breakdown"] == {"6": 90, "7": 95, "8": 88}
    assert sole_line["total_qty_required"] == 273.0
    assert sum(sole_line["size_breakdown"].values()) == sole_line["total_qty_required"]

    # Non-sole material must NOT have size_breakdown or size splitting
    assert "size_breakdown" not in upper_line or upper_line.get("size_breakdown") is None
    assert upper_line["total_qty_required"] == round(1.5 * (90 + 95 + 88), 2)


@pytest.fixture(scope="module")
def client():
    # Try connecting to live server first
    try:
        c = httpx.Client(base_url="http://localhost:8000/api", timeout=3)
        r = c.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        if r.status_code == 200:
            yield c
            return
    except Exception:
        pass

    # Fallback: FastAPI TestClient as context manager (triggers on_event("startup"))
    try:
        from fastapi.testclient import TestClient
        from server import app
        with TestClient(app, base_url="http://testserver/api") as tc:
            r = tc.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
            if r.status_code == 200:
                yield tc
                return
            else:
                pytest.skip(f"Login failed on testserver: {r.text}")
    except Exception as exc:
        pytest.skip(f"Database / test server not reachable: {exc}")




def test_bom_item_color_crud(client):
    # Fetch materials to use a valid material_id if available, or create dummy material
    mat_res = client.get("/materials")
    assert mat_res.status_code == 200
    materials = mat_res.json()
    if materials:
        mat = materials[0]
        mat_id = mat.get("id") or mat.get("_id")
        mat_name = mat.get("name", "Test Leather")
        mat_code = mat.get("code", "RM001")
        mat_unit = mat.get("unit", "sqft")
        mat_rate = float(mat.get("rate", 100))
    else:
        # Create a material
        new_mat = {
            "code": f"MAT-{int(time.time())}",
            "name": "Synthetic Upper Leather",
            "category": "upper",
            "unit": "sqft",
            "rate": 150.0,
            "reorder_level": 10
        }
        create_mat_res = client.post("/materials", json=new_mat)
        assert create_mat_res.status_code in [200, 201]
        mat = create_mat_res.json()
        mat_id = mat.get("id") or mat.get("_id")
        mat_name = mat.get("name")
        mat_code = mat.get("code")
        mat_unit = mat.get("unit")
        mat_rate = float(mat.get("rate"))

    test_color_1 = "Royal Sapphire Blue"
    bom_item_1 = {
        "material_id": str(mat_id),
        "material_name": mat_name,
        "material_code": mat_code,
        "unit": mat_unit,
        "rate": mat_rate,
        "quantity": 1.5,
        "yield_per_unit": 1.0,
        "waste_pct": 5.0,
        "section": "Upper",
        "color": test_color_1
    }

    style_payload = {
        "name": f"Test Color BOM Style {int(time.time())}",
        "category": "Footwear",
        "base_size": "8",
        "bom": [bom_item_1],
        "labor": [{"name": "Cutting", "rate": 20.0}]
    }

    # 1. Create Style with BOM item containing color
    create_style_res = client.post("/styles", json=style_payload)
    assert create_style_res.status_code in [200, 201], f"Create style failed: {create_style_res.text}"
    style_created = create_style_res.json()
    style_id = style_created["id"]

    try:
        # Verify created response contains color in BOM item
        assert len(style_created.get("bom", [])) == 1
        assert style_created["bom"][0].get("color") == test_color_1

        # 2. Retrieve style via GET /styles/{id}
        get_style_res = client.get(f"/styles/{style_id}")
        assert get_style_res.status_code == 200, f"Get style failed: {get_style_res.text}"
        style_retrieved = get_style_res.json()

        assert len(style_retrieved.get("bom", [])) == 1
        assert style_retrieved["bom"][0].get("color") == test_color_1

        # 3. Update style with modified BOM item color via PATCH /styles/{id}
        test_color_2 = "Crimson Red Velvet"
        bom_item_2 = dict(bom_item_1)
        bom_item_2["color"] = test_color_2

        patch_payload = {
            "name": style_retrieved["name"],
            "category": style_retrieved["category"],
            "base_size": style_retrieved["base_size"],
            "bom": [bom_item_2],
            "labor": style_retrieved.get("labor", [])
        }

        patch_res = client.patch(f"/styles/{style_id}", json=patch_payload)
        assert patch_res.status_code == 200, f"Patch style failed: {patch_res.text}"
        style_patched = patch_res.json()
        assert style_patched["bom"][0].get("color") == test_color_2

        # 4. Verify again via fresh GET /styles/{id}
        get_style_res_2 = client.get(f"/styles/{style_id}")
        assert get_style_res_2.status_code == 200
        style_retrieved_2 = get_style_res_2.json()
        assert style_retrieved_2["bom"][0].get("color") == test_color_2

    finally:
        # Cleanup
        client.delete(f"/styles/{style_id}")
