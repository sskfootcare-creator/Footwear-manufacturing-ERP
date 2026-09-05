import io
import pytest
import pypdf
from bson import ObjectId
from unittest.mock import MagicMock

from models.materials import BomItem, ColorBomOverride
from routes.styles import get_effective_bom
from routes.materials import _compute_material_requirement
from pdf_procurement import (
    build_material_requirement,
    generate_material_requirement_sheet,
    _make_swatch_box,
    _is_swatch_item,
)


def test_is_swatch_item_helper():
    """Verify that Upper Top, Lining, and Insole Cover are recognized as swatch categories."""
    assert _is_swatch_item("Upper Top") is True
    assert _is_swatch_item("Upper Lining") is True
    assert _is_swatch_item("Insole Cover") is True
    assert _is_swatch_item("Insole Cover (PU/Leather)") is True
    assert _is_swatch_item("Sole") is True
    assert _is_swatch_item("Bottom Layer") is True
    # Any item with an explicit color specified gets swatch enabled
    assert _is_swatch_item("Other Section", "Midnight Blue") is True
    # Non-swatch category without color is False
    assert _is_swatch_item("Packaging", "") is False


@pytest.mark.anyio
async def test_material_requirement_sheet_style_with_no_overrides():
    """
    Scenario 1:
    Create a style with NO color overrides, set colors on Upper Top / Lining / Insole Cover lines in the base BOM.
    Generate a Material Requirement Sheet — confirm colors print correctly next to swatch boxes
    (this is the exact reported bug, confirm it's fixed).
    """
    line_upper = BomItem(
        line_id="line-up-1",
        material_id="mat-upper-1",
        material_name="Full Grain Leather",
        material_code="MAT-UPP-01",
        section="Upper Top",
        unit="sqft",
        rate=120.0,
        quantity=1.2,
        yield_per_unit=1.0,
        waste_pct=5.0,
        color="Burgundy Leather",
    )
    line_lining = BomItem(
        line_id="line-lin-1",
        material_id="mat-lin-1",
        material_name="Breathable Mesh",
        material_code="MAT-LIN-01",
        section="Lining",
        unit="meter",
        rate=45.0,
        quantity=0.5,
        yield_per_unit=1.0,
        waste_pct=2.0,
        color="Beige Fabric",
    )
    line_insole = BomItem(
        line_id="line-ins-1",
        material_id="mat-ins-1",
        material_name="Comfort Insole Cover",
        material_code="MAT-INS-01",
        section="Insole Cover",
        unit="pair",
        rate=35.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        color="Tan Cushion",
    )

    style_doc = {
        "_id": ObjectId(),
        "code": "STY-NO-OVR-01",
        "name": "Classic Derby",
        "base_size": "8",
        "bom": [line_upper.model_dump(), line_lining.model_dump(), line_insole.model_dump()],
        "color_bom_overrides": {},
    }

    job_id = ObjectId()
    job_doc = {
        "_id": job_id,
        "po_number": "PO-NO-OVR-100",
        "style_code": "STY-NO-OVR-01",
        "color": "Standard",
        "quantity": 50,
        "size": "8",
    }

    class MockCursor:
        def __init__(self, items):
            self.items = items
        async def to_list(self, limit=1000):
            return self.items[:limit]

    materials_db = [
        {"_id": "mat-upper-1", "code": "MAT-UPP-01", "name": "Full Grain Leather", "category": "Upper Top", "rate": 120.0},
        {"_id": "mat-lin-1", "code": "MAT-LIN-01", "name": "Breathable Mesh", "category": "Lining", "rate": 45.0},
        {"_id": "mat-ins-1", "code": "MAT-INS-01", "name": "Comfort Insole Cover", "category": "Insole Cover", "rate": 35.0},
    ]

    mock_db = MagicMock()
    mock_db.production_jobs.find = MagicMock(return_value=MockCursor([job_doc]))
    mock_db.styles.find = MagicMock(return_value=MockCursor([style_doc]))
    mock_db.materials.find = MagicMock(return_value=MockCursor(materials_db))

    # Compute requirements
    req = await _compute_material_requirement([str(job_id)], db=mock_db)
    materials = req["materials"]
    assert len(materials) == 3

    colors_by_code = {m["code"]: m.get("color") for m in materials}
    assert colors_by_code["MAT-UPP-01"] == "Burgundy Leather"
    assert colors_by_code["MAT-LIN-01"] == "Beige Fabric"
    assert colors_by_code["MAT-INS-01"] == "Tan Cushion"

    # Generate PDF through build_material_requirement
    pdf_bytes = build_material_requirement("PO-NO-OVR-100 (Standard)", req["jobs"], req["materials"])
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    # Read PDF text using pypdf to confirm exact printed colors
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_pdf_text = " ".join("".join(page.extract_text() for page in reader.pages).split())

    assert "Burgundy Leather" in full_pdf_text
    assert "Beige Fabric" in full_pdf_text
    assert "Tan Cushion" in full_pdf_text

    # Also verify direct generator call generate_material_requirement_sheet
    pdf_direct = generate_material_requirement_sheet(style_doc, color="Standard", pairs=50)
    reader_direct = pypdf.PdfReader(io.BytesIO(pdf_direct))
    direct_text = " ".join("".join(page.extract_text() for page in reader_direct.pages).split())
    assert "Burgundy Leather" in direct_text
    assert "Beige Fabric" in direct_text
    assert "Tan Cushion" in direct_text


@pytest.mark.anyio
async def test_material_requirement_sheet_style_with_color_override():
    """
    Scenario 2:
    Create a style WITH a color override on one line that also specifies a different color for that override.
    Generate a requirement sheet for that specific variant:
    - confirm the overridden line shows ITS color, not the base line's color
    - non-overridden lines still show base colors correctly.
    """
    line_upper = BomItem(
        line_id="line-up-base",
        material_id="mat-upper-base",
        material_name="Base Black Box Leather",
        material_code="MAT-UPP-BLK",
        section="Upper Top",
        unit="sqft",
        rate=100.0,
        quantity=1.2,
        yield_per_unit=1.0,
        waste_pct=5.0,
        color="Base Black",
    )
    line_lining = BomItem(
        line_id="line-lin-base",
        material_id="mat-lin-base",
        material_name="Base Grey Cambrelle",
        material_code="MAT-LIN-GRY",
        section="Lining",
        unit="meter",
        rate=40.0,
        quantity=0.5,
        yield_per_unit=1.0,
        waste_pct=2.0,
        color="Base Grey",
    )
    line_insole = BomItem(
        line_id="line-ins-base",
        material_id="mat-ins-base",
        material_name="Base Insole Cover",
        material_code="MAT-INS-BRN",
        section="Insole Cover",
        unit="pair",
        rate=30.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        color="Base Brown",
    )

    style_doc = {
        "_id": ObjectId(),
        "code": "STY-OVR-99",
        "name": "Oxford Variant Test",
        "base_size": "8",
        "bom": [line_upper.model_dump(), line_lining.model_dump(), line_insole.model_dump()],
        "color_bom_overrides": {
            "Cognac": [
                # Overrides the Upper Top line with Cognac Suede and specifies color "Cognac Brown"
                ColorBomOverride(
                    line_id="line-up-base",
                    material_id="mat-upper-cognac",
                    material_name="Cognac Suede Leather",
                    material_code="MAT-UPP-COG",
                    rate=160.0,
                    quantity=1.3,
                    color="Cognac Brown",
                ).model_dump()
            ]
        },
    }

    job_cognac_id = ObjectId()
    job_cognac = {
        "_id": job_cognac_id,
        "po_number": "PO-COG-501",
        "style_code": "STY-OVR-99",
        "color": "Cognac",
        "quantity": 30,
        "size": "8",
    }

    job_black_id = ObjectId()
    job_black = {
        "_id": job_black_id,
        "po_number": "PO-BLK-502",
        "style_code": "STY-OVR-99",
        "color": "Black",
        "quantity": 30,
        "size": "8",
    }

    class MockCursor:
        def __init__(self, items):
            self.items = items
        async def to_list(self, limit=1000):
            return self.items[:limit]

    materials_db = [
        {"_id": "mat-upper-base", "code": "MAT-UPP-BLK", "name": "Base Black Box Leather", "category": "Upper Top", "rate": 100.0},
        {"_id": "mat-upper-cognac", "code": "MAT-UPP-COG", "name": "Cognac Suede Leather", "category": "Upper Top", "rate": 160.0},
        {"_id": "mat-lin-base", "code": "MAT-LIN-GRY", "name": "Base Grey Cambrelle", "category": "Lining", "rate": 40.0},
        {"_id": "mat-ins-base", "code": "MAT-INS-BRN", "name": "Base Insole Cover", "category": "Insole Cover", "rate": 30.0},
    ]

    def mock_jobs_find(q):
        ids = [str(x) for x in q.get("_id", {}).get("$in", [])]
        matched = []
        if str(job_cognac_id) in ids:
            matched.append(job_cognac)
        if str(job_black_id) in ids:
            matched.append(job_black)
        return MockCursor(matched)

    mock_db = MagicMock()
    mock_db.production_jobs.find = MagicMock(side_effect=mock_jobs_find)
    mock_db.styles.find = MagicMock(return_value=MockCursor([style_doc]))
    mock_db.materials.find = MagicMock(return_value=MockCursor(materials_db))

    # 1. Verification for Cognac variant (overridden line + base lines)
    req_cognac = await _compute_material_requirement([str(job_cognac_id)], db=mock_db)
    cognac_mats = req_cognac["materials"]

    cognac_colors = {m["code"]: m.get("color") for m in cognac_mats}
    # Overridden line shows ITS color, NOT the base line's color
    assert "MAT-UPP-COG" in cognac_colors
    assert cognac_colors["MAT-UPP-COG"] == "Cognac Brown"
    assert "MAT-UPP-BLK" not in cognac_colors

    # Non-overridden lines still show base colors correctly
    assert cognac_colors["MAT-LIN-GRY"] == "Base Grey"
    assert cognac_colors["MAT-INS-BRN"] == "Base Brown"

    # Generate PDF and check extracted text
    pdf_cognac_bytes = build_material_requirement("PO-COG-501 (Cognac)", req_cognac["jobs"], req_cognac["materials"])
    reader_cognac = pypdf.PdfReader(io.BytesIO(pdf_cognac_bytes))
    cognac_pdf_text = " ".join("".join(page.extract_text() for page in reader_cognac.pages).split())

    assert "Cognac Brown" in cognac_pdf_text
    assert "Base Grey" in cognac_pdf_text
    assert "Base Brown" in cognac_pdf_text
    assert "Base Black" not in cognac_pdf_text

    # 2. Verification for Black variant (no overrides, base colors throughout)
    req_black = await _compute_material_requirement([str(job_black_id)], db=mock_db)
    black_mats = req_black["materials"]
    black_colors = {m["code"]: m.get("color") for m in black_mats}

    assert "MAT-UPP-BLK" in black_colors
    assert black_colors["MAT-UPP-BLK"] == "Base Black"
    assert black_colors["MAT-LIN-GRY"] == "Base Grey"
    assert black_colors["MAT-INS-BRN"] == "Base Brown"
    assert "MAT-UPP-COG" not in black_colors

    pdf_black_bytes = build_material_requirement("PO-BLK-502 (Black)", req_black["jobs"], req_black["materials"])
    reader_black = pypdf.PdfReader(io.BytesIO(pdf_black_bytes))
    black_pdf_text = " ".join("".join(page.extract_text() for page in reader_black.pages).split())

    assert "Base Black" in black_pdf_text
    assert "Base Grey" in black_pdf_text
    assert "Base Brown" in black_pdf_text
    assert "Cognac Brown" not in black_pdf_text
