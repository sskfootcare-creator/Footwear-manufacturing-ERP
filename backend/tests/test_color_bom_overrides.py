import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

import server
from models.materials import BomItem, BomLineOverride
from models.styles import StyleIn
from routes.styles import create_style, update_style, get_style, get_effective_bom
from server import get_effective_bom as server_get_effective_bom


class MockCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, limit=1000):
        return self.items[:limit]

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class DummyRequest:
    def __init__(self, user=None):
        self.state = type("State", (), {"user": user or {"email": "admin@sskfootcare.com", "role": "admin"}})()
        self.headers = {}
        self.cookies = {}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._styles = []
    db._counters = {"style_code": {"_id": "style_code", "seq": 100}}

    def find_styles(q=None, *args, **kwargs):
        return MockCursor(list(db._styles))

    async def find_one_style(q, *args, **kwargs):
        for s in db._styles:
            if "_id" in q and str(s.get("_id")) == str(q["_id"]):
                return dict(s)
            if "code" in q and s.get("code") == q["code"]:
                return dict(s)
        return None

    async def insert_one_style(doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        db._styles.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def update_one_style(filter_q, update_doc, *args, **kwargs):
        sid = filter_q.get("_id")
        for s in db._styles:
            if str(s.get("_id")) == str(sid):
                if "$set" in update_doc:
                    s.update(update_doc["$set"])
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def find_one_and_update(filter_q, update_op, *args, **kwargs):
        seq = db._counters["style_code"]["seq"] + 1
        db._counters["style_code"]["seq"] = seq
        return {"_id": "style_code", "seq": seq}

    db.styles.find = MagicMock(side_effect=find_styles)
    db.styles.find_one = AsyncMock(side_effect=find_one_style)
    db.styles.insert_one = AsyncMock(side_effect=insert_one_style)
    db.styles.update_one = AsyncMock(side_effect=update_one_style)
    db.counters.find_one_and_update = AsyncMock(side_effect=find_one_and_update)
    db.style_folders = MagicMock()
    db.style_folders.insert_one = AsyncMock(return_value=MagicMock())
    return db


def test_bom_item_line_id_auto_generation():
    """Verify line_id is auto-generated if missing/None/empty, and preserved when set."""
    # 1. Default instantiation without line_id
    item1 = BomItem(
        material_id="mat1",
        material_name="Leather",
        material_code="LTH-01",
        unit="sqft",
        rate=120.0,
        quantity=1.5,
    )
    assert item1.line_id is not None
    assert len(item1.line_id) == 8
    # Should be valid hex
    int(item1.line_id, 16)

    # 2. Instantiation with line_id=None or line_id=""
    item2 = BomItem(
        line_id=None,
        material_id="mat2",
        material_name="Sole EVA",
        material_code="SOL-02",
        unit="pair",
        rate=80.0,
        quantity=1.0,
    )
    assert item2.line_id is not None
    assert len(item2.line_id) == 8
    assert item1.line_id != item2.line_id

    item3 = BomItem(
        line_id="",
        material_id="mat3",
        material_name="Lining",
        material_code="LIN-03",
        unit="meter",
        rate=40.0,
        quantity=0.5,
    )
    assert item3.line_id is not None
    assert len(item3.line_id) == 8

    # 3. Explicit line_id is preserved
    item_custom = BomItem(
        line_id="custom99",
        material_id="mat4",
        material_name="Thread",
        material_code="THR-04",
        unit="reel",
        rate=15.0,
        quantity=0.1,
    )
    assert item_custom.line_id == "custom99"
    dumped = item_custom.model_dump()
    assert dumped["line_id"] == "custom99"


def test_bom_line_override_model():
    """Verify BomLineOverride defaults and custom field values."""
    # 1. Default BomLineOverride
    override_default = BomLineOverride()
    assert override_default.line_id is None
    assert override_default.removed is False
    assert override_default.material_id is None
    assert override_default.material_name is None
    assert override_default.material_code is None
    assert override_default.unit is None
    assert override_default.rate is None
    assert override_default.quantity is None
    assert override_default.yield_per_unit is None
    assert override_default.waste_pct is None
    assert override_default.section is None
    assert override_default.component is None
    assert override_default.with_eva is None
    assert override_default.color is None

    # 2. Overridden line
    override_line = BomLineOverride(
        line_id="line_001",
        rate=145.0,
        material_name="Tan Rexine Upper",
        color="Tan",
    )
    assert override_line.line_id == "line_001"
    assert override_line.removed is False
    assert override_line.rate == 145.0
    assert override_line.material_name == "Tan Rexine Upper"
    assert override_line.color == "Tan"

    # 3. Removed line
    removed_line = BomLineOverride(
        line_id="line_002",
        removed=True,
    )
    assert removed_line.line_id == "line_002"
    assert removed_line.removed is True


def test_style_in_color_bom_overrides():
    """Verify StyleIn handles color_bom_overrides correctly."""
    # 1. Default is empty dict
    style_default = StyleIn(name="Classic Oxford")
    assert style_default.color_bom_overrides == {}

    # 2. Populated color_bom_overrides
    style_with_overrides = StyleIn(
        name="Classic Oxford",
        bom=[
            BomItem(
                line_id="base_1",
                material_id="mat1",
                material_name="Upper Leather",
                material_code="UL-01",
                unit="sqft",
                rate=100.0,
                quantity=1.0,
            ),
            BomItem(
                line_id="base_2",
                material_id="mat2",
                material_name="Foam Padding",
                material_code="FP-01",
                unit="sheet",
                rate=50.0,
                quantity=0.5,
            ),
        ],
        color_bom_overrides={
            "Tan": [
                BomLineOverride(line_id="base_1", rate=110.0, color="Tan"),
                BomLineOverride(line_id="base_2", removed=True),
            ],
            "Black": [
                BomLineOverride(line_id="base_1", rate=95.0, color="Black"),
            ],
        },
    )
    assert len(style_with_overrides.color_bom_overrides) == 2
    assert "Tan" in style_with_overrides.color_bom_overrides
    assert len(style_with_overrides.color_bom_overrides["Tan"]) == 2
    assert style_with_overrides.color_bom_overrides["Tan"][0].rate == 110.0
    assert style_with_overrides.color_bom_overrides["Tan"][1].removed is True

    # 3. Validation: whitespace stripped in color key
    style_trimmed = StyleIn(
        name="Derby",
        color_bom_overrides={
            "  Burgundy  ": [BomLineOverride(line_id="base_1", rate=120.0)],
        },
    )
    assert "Burgundy" in style_trimmed.color_bom_overrides

    # 4. Validation: empty key rejected
    with pytest.raises(Exception):
        StyleIn(
            name="Derby",
            color_bom_overrides={
                "": [BomLineOverride(line_id="base_1")],
            },
        )


@pytest.mark.anyio
async def test_style_bom_and_color_overrides_api_persistence(monkeypatch, mock_db):
    """Save style with base BOM and color overrides (one override + one remove), confirm API persistence."""
    monkeypatch.setattr(server, "db", mock_db)
    async def mock_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}
    monkeypatch.setattr(server, "get_current_user", mock_user)

    req = DummyRequest()

    # 1. Create a style with legacy/unassigned line_id BOM items
    create_payload = StyleIn(
        name="Derby Color Edition",
        category="Footwear",
        bom=[
            {
                "material_id": "mat_upper",
                "material_name": "Base Upper Leather",
                "material_code": "MAT-UPPER",
                "unit": "sqft",
                "quantity": 1.2,
                "rate": 150.0,
            },
            {
                "material_id": "mat_accent",
                "material_name": "Accent Strip",
                "material_code": "MAT-ACCENT",
                "unit": "meter",
                "quantity": 0.4,
                "rate": 30.0,
            },
        ],
    )

    created = await create_style(create_payload, req)
    assert created["id"] is not None
    assert len(created["bom"]) == 2
    # Verify line_ids are generated server-side
    line_id_1 = created["bom"][0]["line_id"]
    line_id_2 = created["bom"][1]["line_id"]
    assert line_id_1 is not None and len(line_id_1) == 8
    assert line_id_2 is not None and len(line_id_2) == 8
    assert line_id_1 != line_id_2

    sid = created["id"]

    # 2. Update the style with color_bom_overrides (one overridden line + one removed line)
    update_payload = StyleIn(
        name="Derby Color Edition",
        category="Footwear",
        bom=created["bom"],
        color_bom_overrides={
            "Navy": [
                {
                    "line_id": line_id_1,
                    "rate": 165.0,
                    "material_name": "Navy Nubuck Leather",
                    "color": "Navy",
                },
                {
                    "line_id": line_id_2,
                    "removed": True,
                },
            ],
        },
    )

    updated = await update_style(sid, update_payload, req)
    assert updated["id"] == sid
    assert "color_bom_overrides" in updated
    assert "Navy" in updated["color_bom_overrides"]
    navy_overrides = updated["color_bom_overrides"]["Navy"]
    assert len(navy_overrides) == 2

    assert navy_overrides[0]["line_id"] == line_id_1
    assert navy_overrides[0]["rate"] == 165.0
    assert navy_overrides[0]["material_name"] == "Navy Nubuck Leather"
    assert navy_overrides[0]["color"] == "Navy"
    assert navy_overrides[0]["removed"] is False

    assert navy_overrides[1]["line_id"] == line_id_2
    assert navy_overrides[1]["removed"] is True

    # 3. Retrieve via GET /styles/{sid} to confirm full persistence
    fetched = await get_style(sid, req)
    assert fetched["id"] == sid
    assert fetched["bom"][0]["line_id"] == line_id_1
    assert fetched["bom"][1]["line_id"] == line_id_2
    assert fetched["color_bom_overrides"]["Navy"][0]["line_id"] == line_id_1
    assert fetched["color_bom_overrides"]["Navy"][0]["rate"] == 165.0
    assert fetched["color_bom_overrides"]["Navy"][1]["line_id"] == line_id_2
    assert fetched["color_bom_overrides"]["Navy"][1]["removed"] is True


def test_get_effective_bom_5_lines_override_fixture():
    """
    Verify get_effective_bom with a base BOM of 5 lines + a color override that:
      - changes 1 line's material & rate (modifies in place, keeping non-overridden fields)
      - removes 1 line (drops matching line_id)
      - adds 1 new line (color-specific addition)
    Confirm result has exactly 5 lines (5 base - 1 removed - 1 changed-in-place + 1 added = 5 lines:
    i.e. 4 remaining base lines with 1 modified + 1 new = 5 total).
    Also verify color=None and color without overrides return base BOM unchanged.
    """
    base_line_1 = BomItem(
        line_id="base_upper",
        material_id="mat_upper_01",
        material_name="Black Calfskin Leather",
        material_code="MAT-UPPER-BLK",
        unit="sqft",
        rate=120.0,
        quantity=1.2,
        yield_per_unit=1.0,
        waste_pct=5.0,
        section="Upper",
        component="upper",
        with_eva=False,
        color="Black",
    )
    base_line_2 = BomItem(
        line_id="base_lining",
        material_id="mat_lining_01",
        material_name="Sheepskin Lining",
        material_code="MAT-LIN-01",
        unit="sqft",
        rate=45.0,
        quantity=0.8,
        yield_per_unit=1.0,
        waste_pct=2.0,
        section="Lining",
        component="lining",
    )
    base_line_3 = BomItem(
        line_id="base_insole",
        material_id="mat_insole_01",
        material_name="Texon Insole Board",
        material_code="MAT-INS-01",
        unit="sheet",
        rate=35.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="Bottom",
        component="insole",
    )
    base_line_4 = BomItem(
        line_id="base_sole",
        material_id="mat_sole_01",
        material_name="Rubber Unit Sole",
        material_code="MAT-SOL-01",
        unit="pair",
        rate=90.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="Bottom",
        component="sole",
    )
    base_line_5 = BomItem(
        line_id="base_lace",
        material_id="mat_lace_01",
        material_name="Waxed Cotton Laces",
        material_code="MAT-LAC-01",
        unit="pair",
        rate=12.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="Packing",
        component="lace",
    )

    base_bom = [base_line_1, base_line_2, base_line_3, base_line_4, base_line_5]
    assert len(base_bom) == 5

    style_dict = {
        "id": "style_123",
        "name": "Oxford Brogue",
        "bom": [b.model_dump() for b in base_bom],
        "color_bom_overrides": {
            "Tan": [
                # 1. Change 1 line's material (base_upper)
                BomLineOverride(
                    line_id="base_upper",
                    material_id="mat_upper_tan",
                    material_name="Tan Veg-Tan Leather",
                    material_code="MAT-UPPER-TAN",
                    rate=140.0,
                    color="Tan",
                ).model_dump(),
                # 2. Remove 1 line (base_lace)
                BomLineOverride(
                    line_id="base_lace",
                    removed=True,
                ).model_dump(),
                # 3. Add 1 new line (Brass Buckle)
                BomLineOverride(
                    line_id=None,
                    material_id="mat_buckle_01",
                    material_name="Brass Buckle",
                    material_code="MAT-BCK-01",
                    unit="pcs",
                    rate=25.0,
                    quantity=2.0,
                    yield_per_unit=1.0,
                    waste_pct=0.0,
                    section="Accessory",
                    component=None,
                    color="Brass",
                ).model_dump(),
            ]
        },
    }

    # --- Case 1: Effective BOM for "Tan" ---
    effective_tan = get_effective_bom(style_dict, "Tan")

    # Math check: 5 base - 1 removed (lace) - 1 changed-in-place (upper) + 1 added (buckle) = 5 total
    # (i.e. 4 remaining base lines with 1 modified + 1 new = 5 total)
    assert len(effective_tan) == 5

    # Check modified Line 1:
    line1 = effective_tan[0]
    assert line1.line_id == "base_upper"
    assert line1.material_id == "mat_upper_tan"
    assert line1.material_name == "Tan Veg-Tan Leather"
    assert line1.material_code == "MAT-UPPER-TAN"
    assert line1.rate == 140.0
    assert line1.color == "Tan"
    # Verify unspecified fields are untouched and inherited from base line
    assert line1.unit == "sqft"
    assert line1.quantity == 1.2
    assert line1.yield_per_unit == 1.0
    assert line1.waste_pct == 5.0
    assert line1.section == "Upper"
    assert line1.component == "upper"
    assert line1.with_eva is False

    # Check untouched Line 2 (Lining):
    line2 = effective_tan[1]
    assert line2.line_id == "base_lining"
    assert line2.material_name == "Sheepskin Lining"
    assert line2.rate == 45.0
    assert line2.quantity == 0.8

    # Check untouched Line 3 (Insole):
    line3 = effective_tan[2]
    assert line3.line_id == "base_insole"
    assert line3.material_name == "Texon Insole Board"
    assert line3.rate == 35.0

    # Check untouched Line 4 (Sole):
    line4 = effective_tan[3]
    assert line4.line_id == "base_sole"
    assert line4.material_name == "Rubber Unit Sole"
    assert line4.rate == 90.0

    # Check that removed Line 5 (base_lace) is NOT present:
    assert all(b.line_id != "base_lace" for b in effective_tan)

    # Check added Line 5 (Brass Buckle):
    line5 = effective_tan[4]
    assert line5.material_id == "mat_buckle_01"
    assert line5.material_name == "Brass Buckle"
    assert line5.material_code == "MAT-BCK-01"
    assert line5.unit == "pcs"
    assert line5.rate == 25.0
    assert line5.quantity == 2.0
    assert line5.section == "Accessory"
    assert line5.color == "Brass"
    assert line5.line_id is not None
    assert len(line5.line_id) == 8

    # --- Case 2: color is None ---
    effective_none = get_effective_bom(style_dict, None)
    assert len(effective_none) == 5
    assert [b.line_id for b in effective_none] == ["base_upper", "base_lining", "base_insole", "base_sole", "base_lace"]
    assert effective_none[0].material_name == "Black Calfskin Leather"
    assert effective_none[4].material_name == "Waxed Cotton Laces"

    # --- Case 3: color with no override entry (e.g. "Burgundy") ---
    effective_unconfigured = get_effective_bom(style_dict, "Burgundy")
    assert len(effective_unconfigured) == 5
    assert [b.line_id for b in effective_unconfigured] == ["base_upper", "base_lining", "base_insole", "base_sole", "base_lace"]
    assert effective_unconfigured[0].material_name == "Black Calfskin Leather"
    assert effective_unconfigured[4].material_name == "Waxed Cotton Laces"

    # --- Case 4: Verify server.py re-export works identically ---
    effective_server = server_get_effective_bom(style_dict, "Tan")
    assert len(effective_server) == 5
    assert effective_server[0].material_name == "Tan Veg-Tan Leather"


@pytest.mark.anyio
async def test_costing_and_material_requirement_with_color_overrides():
    """
    Verify:
      1. compute_style_costing with color parameter computes materials_cost based on effective BOM.
      2. compute_po_profitability passes through po_line's color to calculate per-color profitability.
      3. _compute_material_requirement and Material Requirement Sheet generation (pdf_procurement)
         for a PO in the overridden color reflects the overridden material & quantity.
      4. Material Requirement Sheet for a PO with no override reflects the base BOM.
    """
    from routes.styles import compute_style_costing, compute_po_profitability
    from routes.materials import _compute_material_requirement
    from pdf_procurement import build_material_requirement

    # Setup Style with base BOM and Cream color override
    base_upper = BomItem(
        line_id="line_upper_base",
        material_id="mat_upper_black",
        material_name="Black Leather Upper",
        material_code="MAT-UPPER-BLK",
        unit="sqft",
        rate=100.0,
        quantity=1.2,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="Upper",
        component="upper",
    )
    base_sole = BomItem(
        line_id="line_sole_base",
        material_id="mat_sole_std",
        material_name="Standard Sole",
        material_code="MAT-SOL-01",
        unit="pair",
        rate=50.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="Bottom",
        component="sole",
    )

    style_doc = {
        "_id": ObjectId(),
        "code": "SSK_99001",
        "name": "Loafer Deluxe",
        "overhead_pct": 10.0,
        "packing_cost": 20.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
        "bom": [base_upper.model_dump(), base_sole.model_dump()],
        "labor": [{"name": "Stitching", "rate": 40.0}],
        "color_bom_overrides": {
            "Cream": [
                # Overrides material and quantity for upper line
                BomLineOverride(
                    line_id="line_upper_base",
                    material_id="mat_upper_cream_velvet",
                    material_name="Cream Velvet Fabric",
                    material_code="MAT-UPPER-CRM",
                    rate=150.0,
                    quantity=1.5,
                    color="Cream",
                ).model_dump(),
            ],
        },
    }

    # 1. Costing Verification
    # Base BOM materials cost: (100 * 1.2) + (50 * 1.0) = 120 + 50 = 170.0
    cost_base = compute_style_costing(style_doc)
    assert cost_base["materials_cost"] == 170.0

    cost_black = compute_style_costing(style_doc, color="Black")
    assert cost_black["materials_cost"] == 170.0

    # Cream overridden materials cost: (150 * 1.5) + (50 * 1.0) = 225 + 50 = 275.0
    cost_cream = compute_style_costing(style_doc, color="Cream")
    assert cost_cream["materials_cost"] == 275.0
    assert cost_cream["total_cost"] > cost_base["total_cost"]

    # 2. PO Profitability Verification
    mock_db = MagicMock()
    mock_db.production_jobs = MagicMock()
    mock_db.production_jobs.find = MagicMock(return_value=MockCursor([]))

    po_line_cream = {
        "style_code": "SSK_99001",
        "color": "Cream",
        "unit_price": 500.0,
        "quantity": 20,
    }
    prof_cream = await compute_po_profitability(po_line_cream, style_doc, db=mock_db)
    assert prof_cream["bom_cost"] == 275.0

    po_line_black = {
        "style_code": "SSK_99001",
        "color": "Black",
        "unit_price": 500.0,
        "quantity": 20,
    }
    prof_black = await compute_po_profitability(po_line_black, style_doc, db=mock_db)
    assert prof_black["bom_cost"] == 170.0

    # 3. Material Requirement Sheet Verification
    job_cream_id = ObjectId()
    job_black_id = ObjectId()

    job_cream = {
        "_id": job_cream_id,
        "po_number": "PO-CRM-001",
        "style_code": "SSK_99001",
        "color": "Cream",
        "quantity": 10,
        "size": "8",
    }
    job_black = {
        "_id": job_black_id,
        "po_number": "PO-BLK-002",
        "style_code": "SSK_99001",
        "color": "Black",
        "quantity": 10,
        "size": "8",
    }

    materials_db = [
        {"_id": ObjectId(), "code": "MAT-UPPER-BLK", "name": "Black Leather Upper", "category": "upper", "rate": 100.0},
        {"_id": ObjectId(), "code": "MAT-UPPER-CRM", "name": "Cream Velvet Fabric", "category": "upper", "rate": 150.0},
        {"_id": ObjectId(), "code": "MAT-SOL-01", "name": "Standard Sole", "category": "sole", "rate": 50.0},
    ]

    def mock_jobs_find(q):
        ids = [str(x) for x in q.get("_id", {}).get("$in", [])]
        matched = []
        if str(job_cream_id) in ids:
            matched.append(job_cream)
        if str(job_black_id) in ids:
            matched.append(job_black)
        return MockCursor(matched)

    def mock_styles_find(q):
        return MockCursor([style_doc])

    def mock_materials_find(q):
        return MockCursor(materials_db)

    req_db = MagicMock()
    req_db.production_jobs.find = MagicMock(side_effect=mock_jobs_find)
    req_db.styles.find = MagicMock(side_effect=mock_styles_find)
    req_db.materials.find = MagicMock(side_effect=mock_materials_find)

    # 3a. Material requirement for Cream PO (overridden variant)
    req_cream = await _compute_material_requirement([str(job_cream_id)], db=req_db)
    cream_materials = req_cream["materials"]
    cream_mat_names = [m["name"] for m in cream_materials]

    assert "Cream Velvet Fabric" in cream_mat_names
    assert "Black Leather Upper" not in cream_mat_names

    cream_velvet_entry = next(m for m in cream_materials if m["name"] == "Cream Velvet Fabric")
    # 1.5 sqft per pair * 10 pairs = 15.0 sqft
    assert cream_velvet_entry["total_qty_required"] == 15.0
    assert cream_velvet_entry["rate"] == 150.0
    assert cream_velvet_entry["total_cost"] == 2250.0

    sole_cream_entry = next(m for m in cream_materials if m["name"] == "Standard Sole")
    assert sole_cream_entry["total_qty_required"] == 10.0

    # PDF generation for Cream PO
    pdf_cream_bytes = build_material_requirement("PO-CRM-001 (Cream)", req_cream["jobs"], cream_materials)
    assert isinstance(pdf_cream_bytes, bytes)
    assert pdf_cream_bytes.startswith(b"%PDF")

    # 3b. Material requirement for Black PO (base recipe, no override)
    req_black = await _compute_material_requirement([str(job_black_id)], db=req_db)
    black_materials = req_black["materials"]
    black_mat_names = [m["name"] for m in black_materials]

    assert "Black Leather Upper" in black_mat_names
    assert "Cream Velvet Fabric" not in black_mat_names

    black_leather_entry = next(m for m in black_materials if m["name"] == "Black Leather Upper")
    # 1.2 sqft per pair * 10 pairs = 12.0 sqft
    assert black_leather_entry["total_qty_required"] == 12.0
    assert black_leather_entry["rate"] == 100.0
    assert black_leather_entry["total_cost"] == 1200.0

    # PDF generation for Black PO
    pdf_black_bytes = build_material_requirement("PO-BLK-002 (Black)", req_black["jobs"], black_materials)
    assert isinstance(pdf_black_bytes, bytes)
    assert pdf_black_bytes.startswith(b"%PDF")


