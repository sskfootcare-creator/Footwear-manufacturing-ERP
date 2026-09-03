"""
Test Suite for Stage 1: Flexible Per-Color BOM Line Overrides
Verifies:
1. BomItem generates a short 8-character unique line_id automatically if none provided.
2. ColorBomOverride model supports line_id and optional fields:
   (material_id, material_name, material_code, rate, quantity, yield_per_unit, waste_pct).
3. StyleIn model includes color_bom_overrides: Optional[Dict[str, List[ColorBomOverride]]].
4. Color with no entries uses base BOM as the zero-extra-work default.
5. End-to-end API persistence: save a style with a base BOM (several lines, mixed sections)
   and one color overriding two different lines (rate on one line, quantity on another).
"""

import pytest
import os
import requests
from models.materials import BomItem, ColorBomOverride
from models.styles import StyleIn


def test_bom_item_auto_generates_line_id():
    """Verify: BomItem auto-generates a short unique line_id (8-char hex) if none is provided,
    and preserves it if already provided."""
    # Line without line_id
    item1 = BomItem(material_name="Black Leather", rate=100.0, section="upper")
    assert item1.line_id is not None
    assert isinstance(item1.line_id, str)
    assert len(item1.line_id) == 8

    # Line with line_id=None explicitly passed
    item2 = BomItem(line_id=None, material_name="Sole", rate=150.0, section="sole")
    assert item2.line_id is not None
    assert len(item2.line_id) == 8
    assert item1.line_id != item2.line_id

    # Line with empty string passed
    item3 = BomItem(line_id="   ", material_name="Insole", rate=30.0, section="insole")
    assert item3.line_id is not None
    assert len(item3.line_id) == 8

    # Line with existing custom line_id preserves it
    item4 = BomItem(line_id="custom-line-99", material_name="Lining", rate=20.0, section="lining")
    assert item4.line_id == "custom-line-99"


def test_color_bom_override_model():
    """Verify: ColorBomOverride model requires line_id and all other fields are optional."""
    ov1 = ColorBomOverride(line_id="line-abc", rate=125.5)
    assert ov1.line_id == "line-abc"
    assert ov1.rate == 125.5
    assert ov1.quantity is None
    assert ov1.material_name is None
    assert ov1.material_id is None

    ov2 = ColorBomOverride(line_id="line-xyz", quantity=2.5, waste_pct=4.0)
    assert ov2.line_id == "line-xyz"
    assert ov2.quantity == 2.5
    assert ov2.waste_pct == 4.0
    assert ov2.rate is None

    # Dict-like access support
    assert ov1["rate"] == 125.5
    assert ov1.get("rate") == 125.5
    assert "rate" in ov1
    assert ov1.get("non_existent") is None


def test_style_in_model_with_color_bom_overrides():
    """Verify: StyleIn accepts color_bom_overrides dict with ColorBomOverride lists."""
    line1 = BomItem(material_name="Black Box Leather", rate=100.0, section="upper")
    line2 = BomItem(material_name="Insole Board", rate=30.0, section="insole")

    style = StyleIn(
        name="Oxford Classic",
        bom=[line1, line2],
        color_bom_overrides={
            "Tan": [
                ColorBomOverride(line_id=line1.line_id, rate=145.0),
                ColorBomOverride(line_id=line2.line_id, quantity=1.5),
            ]
        },
    )

    assert "Tan" in style.color_bom_overrides
    assert len(style.color_bom_overrides["Tan"]) == 2
    assert style.color_bom_overrides["Tan"][0].rate == 145.0
    assert style.color_bom_overrides["Tan"][1].quantity == 1.5

    # Zero-extra-work default: color not in overrides has no entry
    assert "Black" not in style.color_bom_overrides


@pytest.fixture
def test_api():
    """Provides an authenticated client and base API URL."""
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


def test_persist_style_with_color_bom_overrides_via_api(test_api):
    """End-to-End API Persistence Verification:
    Save a style with a base BOM (several lines, mixed sections) and one color
    overriding two different lines (rate on one line, quantity on another).
    Confirm it persists correctly via the API."""
    client, api_url = test_api

    # Pre-generate 3 base lines across mixed sections
    item_upper = BomItem(
        material_id="mat-blk-box",
        material_name="Black Box Leather",
        material_code="MAT-BLK-01",
        rate=110.0,
        quantity=1.2,
        section="upper",
        component="Vamp",
    ).model_dump()

    item_insole = BomItem(
        material_id="mat-board",
        material_name="Standard Shank Board",
        material_code="MAT-INS-01",
        rate=35.0,
        quantity=1.0,
        section="insole",
    ).model_dump()

    item_sole = BomItem(
        material_id="mat-sole-tpr",
        material_name="TPR Lug Sole",
        material_code="MAT-SOL-01",
        rate=180.0,
        quantity=1.0,
        section="sole",
    ).model_dump()

    line_id_upper = item_upper["line_id"]
    line_id_insole = item_insole["line_id"]
    line_id_sole = item_sole["line_id"]

    import time
    style_payload = {
        "code": f"STY-BOM-OV-{int(time.time())}",
        "name": "Flexible Override Boot",
        "category": "Footwear",
        "base_size": "8",
        "bom": [item_upper, item_insole, item_sole],
        "color_bom_overrides": {
            "Mahogany": [
                # Override 1: Rate on upper line
                {
                    "line_id": line_id_upper,
                    "material_name": "Mahogany Pull-Up Leather",
                    "material_code": "MAT-MAH-01",
                    "rate": 165.0,
                },
                # Override 2: Quantity on insole line
                {
                    "line_id": line_id_insole,
                    "quantity": 1.75,
                },
            ]
        },
    }

    prefix = f"{api_url}" if api_url else ""
    res = client.post(f"{prefix}/styles", json=style_payload)
    assert res.status_code in [200, 201], f"Style creation failed: {res.text}"
    data = res.json()
    style_id = data.get("id")
    assert style_id, "Response must include style id"

    try:
        # Fetch persisted style from API
        get_res = client.get(f"{prefix}/styles/{style_id}")
        assert get_res.status_code == 200, f"Get style failed: {get_res.text}"
        persisted = get_res.json()

        # Check BOM lines have generated line_ids
        persisted_bom = persisted.get("bom") or []
        assert len(persisted_bom) == 3
        for b in persisted_bom:
            assert b.get("line_id"), "Each BOM line must have a line_id"

        # Check color_bom_overrides persistence
        assert "color_bom_overrides" in persisted
        ov_dict = persisted["color_bom_overrides"]
        assert "Mahogany" in ov_dict
        mahogany_ovs = ov_dict["Mahogany"]
        assert len(mahogany_ovs) == 2

        # Verify Line 1 override (rate changed to 165.0)
        up_ov = next((o for o in mahogany_ovs if o["line_id"] == line_id_upper), None)
        assert up_ov is not None
        assert up_ov["rate"] == 165.0
        assert up_ov["material_name"] == "Mahogany Pull-Up Leather"

        # Verify Line 2 override (quantity changed to 1.75)
        ins_ov = next((o for o in mahogany_ovs if o["line_id"] == line_id_insole), None)
        assert ins_ov is not None
        assert ins_ov["quantity"] == 1.75
        assert ins_ov.get("rate") is None  # Inherits base rate

        # Unspecified lines (sole) and colors (e.g. Black) have no override entries
        sole_ov = next((o for o in mahogany_ovs if o["line_id"] == line_id_sole), None)
        assert sole_ov is None, "Sole was not overridden and must have no entry"
        assert "Black" not in ov_dict, "Color without overrides must have no entry"

    finally:
        client.delete(f"{prefix}/styles/{style_id}")
