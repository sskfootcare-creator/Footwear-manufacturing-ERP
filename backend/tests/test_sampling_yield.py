"""Unit & Integration Tests for Pattern Scanner Service & 2D Yield Engine.

Includes coverage for:
1. Dark Background Scanner Mode (Contrast Pattern on Dark Bed).
2. Standard Linear Components & Folded Laces (Formula: Raw Cut Width = 2 * Folded Width).
3. Standard Factory Presets Retention (Die-cut Insole Board 26 prs/sheet & Bottom Covering 8 prs/m).
4. Reusable PLM Pattern Library (Listing, Import/Re-use across styles, Save to Library).
5. BOM Injection & Digital Style Folder PLM Archival (Folder 03 Upper Patterns).
"""

import io
import pytest
import numpy as np
from PIL import Image, ImageDraw
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch

from services.pattern_scanner_service import (
    extract_patterns_from_image_bytes,
    A4_WIDTH_MM,
    A4_HEIGHT_MM,
)
from services.yield_nesting_service import (
    simulate_nesting,
    calculate_standard_strip,
    STANDARD_FACTORY_PRESETS,
)
from routes.sampling import (
    scan_sample_pattern,
    calculate_sample_yield,
    get_sample_yield_spec,
    transfer_sample_to_style,
    list_pattern_library,
    import_pattern_to_sample,
    save_sample_pattern_to_library,
)
from models.sampling import (
    CalculateYieldIn,
    TransferToStyleIn,
    StandardStripItem,
    ImportPatternIn,
    SaveToLibraryIn,
)


@pytest.fixture
def synthetic_a4_scan():
    """Create a synthetic A4 image (2100 x 2970 px, 10 px/mm) with 2 distinct shapes:
    1. A large vamp-like rectangle (100mm x 60mm -> 1000 x 600 px).
    2. A thin strap-like rectangle (150mm x 20mm -> 1500 x 200 px).
    Background: White (scanner bed). Shapes: Dark Gray/Black (cardstock).
    """
    img_w, img_h = 2100, 2970
    img = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Vamp piece: top-left (300, 400), size (1000, 600) -> 100mm x 60mm = 60 cm²
    draw.rectangle([300, 400, 1300, 1000], fill=(30, 30, 30))

    # Strap piece: top-left (300, 1200), size (1500, 200) -> 150mm x 20mm = 30 cm²
    draw.rectangle([300, 1200, 1800, 1400], fill=(30, 30, 30))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def synthetic_dark_a4_scan():
    """Create a synthetic A4 image with DARK background (black scanner bed)
    and CONTRAST bright paper/cardstock patterns (light cream / white).
    Matches user's exact physical setup: Dark background + Contrast pattern.
    """
    img_w, img_h = 2100, 2970
    img = Image.new("RGB", (img_w, img_h), color=(15, 15, 18))  # Dark scanner bed
    draw = ImageDraw.Draw(img)

    # Contrast Vamp piece (White/Cream cardstock)
    draw.rectangle([300, 400, 1300, 1000], fill=(240, 240, 235))

    # Contrast Strap piece
    draw.rectangle([300, 1200, 1800, 1400], fill=(240, 240, 235))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.samples = MagicMock()
    db.styles = MagicMock()
    db.materials = MagicMock()
    db.counters = MagicMock()
    db.image_uploads = MagicMock()
    db.style_folders = MagicMock()
    db.plm_documents = MagicMock()
    db.plm_patterns = MagicMock()
    return db


@pytest.fixture
def mock_admin_user():
    return {
        "email": "admin@example.com",
        "role": "admin",
        "username": "Admin",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pattern Scanner & Computer Vision Calibration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_pattern_scanner_extracts_calibrated_geometry(synthetic_a4_scan):
    """Verify that an A4 scanned image on light bed is calibrated accurately to physical mm and cm²."""
    res = extract_patterns_from_image_bytes(synthetic_a4_scan, min_area_sqcm=2.0, background_mode="light")

    assert res["ok"] is True
    assert res["calibration"]["orientation"] == "portrait"
    assert res["calibration"]["page_width_mm"] == A4_WIDTH_MM
    assert res["calibration"]["page_height_mm"] == A4_HEIGHT_MM
    # Scale: 2100px / 210mm = 10 px/mm
    assert abs(res["calibration"]["scale_px_per_mm"] - 10.0) < 0.1
    assert abs(res["calibration"]["dpi"] - 254.0) < 2.0

    # Must detect both pattern pieces
    pieces = res["pattern_pieces"]
    assert len(pieces) == 2

    # Check piece 1 (Vamp: 1000px x 600px -> 100mm x 60mm = 60 cm²)
    p1 = pieces[0]
    assert abs(p1["area_sqcm"] - 60.0) < 3.0
    assert abs(p1["length_mm"] - 100.0) < 3.0
    assert abs(p1["width_mm"] - 60.0) < 3.0
    assert p1["svg_polygon"].startswith("M ")
    assert p1["pieces_per_pair"] == 2

    # Check piece 2 (Strap: 1500px x 200px -> 150mm x 20mm = 30 cm²)
    p2 = pieces[1]
    assert abs(p2["area_sqcm"] - 30.0) < 2.0
    assert abs(p2["length_mm"] - 150.0) < 3.0
    assert abs(p2["width_mm"] - 20.0) < 3.0
    assert "Strap" in p2["piece_name"]


def test_pattern_scanner_dark_background_mode(synthetic_dark_a4_scan):
    """Verify that Dark Background mode accurately segments bright contrast patterns on dark scanner beds."""
    res = extract_patterns_from_image_bytes(synthetic_dark_a4_scan, min_area_sqcm=2.0, background_mode="dark")

    assert res["ok"] is True
    assert res["calibration"]["background_mode"] == "dark"
    assert len(res["pattern_pieces"]) == 2

    # Both pieces must be cleanly detected with accurate area
    p1 = res["pattern_pieces"][0]
    assert abs(p1["area_sqcm"] - 60.0) < 3.0
    assert abs(p1["length_mm"] - 100.0) < 3.0


def test_pattern_scanner_rejects_empty_or_corrupt_data():
    """Verify error handling on invalid image bytes."""
    with pytest.raises(ValueError):
        extract_patterns_from_image_bytes(b"not an image", min_area_sqcm=2.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Standard Folded Laces Formula & 2D Nesting Engine Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_standard_folded_lace_formula():
    """Verify factory formula: Raw Cut Width = 2 * Folded Width.
    E.g. 8mm folded lace -> 16mm raw cut width.
    0.5 inch (12.7mm) folded lace -> 25.4mm raw cut width.
    And verify laces yielded per 1 meter of roll calculation.
    """
    # 8mm folded lace, 650mm long (2 per pair) across 54" roll (1371.6mm)
    res_8mm = calculate_standard_strip(
        folded_width_mm=8.0,
        length_mm=650.0,
        pieces_per_pair=2,
        roll_width_inches=54.0,
        selvage_margin_mm=20.0,
        roll_length_meters=50.0,
    )
    assert res_8mm["cut_width_mm"] == 16.0  # Exactly 2 * 8mm
    assert res_8mm["lanes_across_roll"] > 0
    assert res_8mm["total_lace_meters_per_roll_meter"] == res_8mm["lanes_across_roll"] * 1.0
    # Expected laces per meter: (lanes * 1000mm) / 650mm
    expected_laces_per_m = round((res_8mm["lanes_across_roll"] * 1000.0) / 650.0, 2)
    assert res_8mm["laces_yield_per_meter"] == expected_laces_per_m
    assert res_8mm["pairs_per_meter"] == round(expected_laces_per_m / 2.0, 2)
    assert res_8mm["total_laces_full_roll"] > 0
    assert res_8mm["total_pairs_full_roll"] > 0
    assert res_8mm["consumption_per_pair"] > 0.0

    # 0.5 inch (12.7mm) folded lace
    res_half_inch = calculate_standard_strip(
        folded_width_mm=12.7,
        length_mm=800.0,
        pieces_per_pair=4,
    )
    assert res_half_inch["cut_width_mm"] == pytest.approx(25.4, 0.01)  # Exactly 2 * 12.7mm = 1 inch
    assert res_half_inch["pieces_per_pair"] == 4
    assert res_half_inch["cut_width_inches"] == pytest.approx(1.0, 0.01)
    assert res_half_inch["length_inches"] == pytest.approx(31.5, 0.1)


def test_cutting_direction_stretch_control():
    """Verify footwear cutting direction controls:
    - 'length_up' (default/warp): No length stretch when shoe is worn; piece length along roll length.
    - 'width_up' (weft): Piece length placed along roll width.
    - 'both': Evaluates both and chooses max yield.
    """
    # Create an elongated piece (180mm length, 50mm width)
    sample_pieces = [
        {
            "piece_id": "vamp_long",
            "piece_name": "Long Vamp",
            "area_sqcm": 75.0,
            "length_mm": 180.0,
            "width_mm": 50.0,
            "pieces_per_pair": 2,
        }
    ]

    # 1. Length-Up (Default - strictly no length stretch)
    res_len_up = simulate_nesting(
        pieces=sample_pieces,
        material_type="roll",
        roll_width_inches=54.0,
        cutting_direction="length_up",
    )
    p_len_up = res_len_up["pieces_analysis"][0]
    assert p_len_up["is_rotated"] is False
    assert "Length-Up" in p_len_up["cutting_direction_label"]

    # 2. Width-Up (strictly crosswise)
    res_wid_up = simulate_nesting(
        pieces=sample_pieces,
        material_type="roll",
        roll_width_inches=54.0,
        cutting_direction="width_up",
    )
    p_wid_up = res_wid_up["pieces_analysis"][0]
    assert p_wid_up["is_rotated"] is True
    assert "Crosswise" in p_wid_up["cutting_direction_label"]

    # 3. Custom roll width (1400mm) and 50-meter roll length calculation
    res_custom = simulate_nesting(
        pieces=sample_pieces,
        material_type="roll",
        custom_roll_width_mm=1400.0,
        roll_length_meters=50.0,
        cutting_direction="length_up",
        measurement_unit="inch",
    )
    assert res_custom["material_spec"]["roll_width_mm"] == 1400.0
    assert res_custom["total_pairs_per_roll"] > 0
    assert res_custom["cutting_direction"] == "length_up"
    assert res_custom["measurement_unit"] == "inch"


def test_roll_nesting_with_standard_strips_and_presets():
    """Verify continuous roll nesting metrics including both 2D contours,
    folded laces, and factory locked standard presets."""
    sample_pieces = [
        {
            "piece_id": "vamp_1",
            "piece_name": "Main Vamp",
            "area_sqcm": 85.0,
            "length_mm": 160.0,
            "width_mm": 90.0,
            "pieces_per_pair": 2,
        },
    ]

    standard_strips = [
        {
            "strip_id": "lace_1",
            "name": "Main 8mm Folded Lace",
            "folded_width_mm": 8.0,
            "length_mm": 650.0,
            "pieces_per_pair": 2,
        }
    ]

    res = simulate_nesting(
        pieces=sample_pieces,
        material_type="roll",
        roll_width_inches=54.0,
        selvage_margin_mm=20.0,
        kerf_spacing_mm=3.0,
        waste_allowance_pct=5.0,
        standard_strips=standard_strips,
    )

    assert res["ok"] is True
    assert res["material_type"] == "roll"
    assert res["material_spec"]["roll_width_mm"] == pytest.approx(1371.6, 0.1)

    # Core BOM KPIs
    assert res["consumption_per_pair"] > 0.0
    assert res["consumption_unit"] == "meter"
    assert res["yield_per_unit"] > 0.0

    # Standard strips must be calculated with cut_width = 2 * folded_width
    assert len(res["standard_strips"]) == 1
    assert res["standard_strips"][0]["cut_width_mm"] == 16.0

    # Component breakdown must include upper, lining, and standard presets
    bd = res["component_breakdown"]
    assert "upper" in bd
    assert "standard_insole" in bd
    assert bd["standard_insole"]["yield_per_unit"] == 26.0
    assert "standard_bottom_covering" in bd
    assert bd["standard_bottom_covering"]["yield_per_unit"] == 8.0


def test_sheet_nesting_calculation():
    """Verify sheet nesting metrics across 40'' x 60'' EVA foam sheet."""
    sample_pieces = [
        {
            "piece_id": "cushion_1",
            "piece_name": "Insole Cushioning",
            "area_sqcm": 110.0,
            "length_mm": 230.0,
            "width_mm": 75.0,
            "pieces_per_pair": 2,
        }
    ]

    res = simulate_nesting(
        pieces=sample_pieces,
        material_type="sheet",
        sheet_length_mm=1524.0,  # 60"
        sheet_width_mm=1016.0,   # 40"
        selvage_margin_mm=15.0,
        kerf_spacing_mm=3.0,
        waste_allowance_pct=5.0,
    )

    assert res["ok"] is True
    assert res["material_type"] == "sheet"
    assert res["consumption_unit"] == "sheet"
    assert res["yield_per_unit"] > 0.0
    assert "pairs / sheet" in res["yield_unit_label"]
    assert res["consumption_per_pair"] > 0.0


def test_nesting_with_tech_pack_lining_and_canvas():
    """Verify that simulate_nesting calculates lining and canvas reinforcement from Tech Pack."""
    sample_pieces = [
        {
            "piece_id": "vamp_1",
            "piece_name": "Main Vamp",
            "material_id": "mat_synth_1",
            "material_name": "Synthetic ParisNapa",
            "placement": "Primary",
            "area_sqcm": 95.0,
            "length_mm": 170.0,
            "width_mm": 85.0,
            "pieces_per_pair": 2,
        },
        {
            "piece_id": "quarter_1",
            "piece_name": "Side Quarter",
            "material_id": "mat_leath_2",
            "material_name": "Karigar Leather",
            "placement": "Secondary",
            "area_sqcm": 70.0,
            "length_mm": 190.0,
            "width_mm": 60.0,
            "pieces_per_pair": 2,
        },
    ]

    upper_spec = {
        "lining_material_name": "Fixture Style Lining",
        "canvas_backing": "Sada Kada",
    }

    res = simulate_nesting(
        pieces=sample_pieces,
        material_type="roll",
        roll_width_inches=54.0,
        upper_spec=upper_spec,
    )

    assert res["ok"] is True
    # Material breakdown should contain Primary, Secondary, Lining, and Canvas
    mb_names = [mb["material_name"] for mb in res["material_breakdown"]]
    assert any("ParisNapa" in n for n in mb_names)
    assert any("Karigar Leather" in n for n in mb_names)
    assert any("Lining" in n for n in mb_names)
    assert any("Canvas" in n for n in mb_names)

    # Component breakdown must include lining and canvas_reinforcement
    assert "lining" in res["component_breakdown"]
    assert res["component_breakdown"]["lining"]["consumption_per_pair"] > 0.0
    assert "canvas_reinforcement" in res["component_breakdown"]
    assert res["component_breakdown"]["canvas_reinforcement"]["consumption_per_pair"] > 0.0

    # BOM summary must exist and report average and total metrics
    assert "bom_summary" in res
    assert res["bom_summary"]["total_upper_top_consumption"] > 0.0
    assert res["bom_summary"]["avg_upper_top_consumption"] > 0.0
    assert res["bom_summary"]["lining_consumption"] > 0.0
    assert res["bom_summary"]["canvas_consumption"] > 0.0



# ─────────────────────────────────────────────────────────────────────────────
# 3. Route & BOM Injection Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_calculate_sample_yield_endpoint(mock_db, mock_admin_user):
    """Verify POST /api/samples/{sid}/calculate-yield saves yield_spec with standard strips."""
    sid = str(ObjectId())
    mock_sample = {
        "_id": ObjectId(sid),
        "sample_name": "Lacebuckle",
        "status": "sample_ready",
        "pattern_pieces": [
            {
                "piece_id": "p1",
                "piece_name": "Vamp",
                "area_sqcm": 80.0,
                "length_mm": 150.0,
                "width_mm": 80.0,
                "pieces_per_pair": 2,
            }
        ],
    }
    mock_db.samples.find_one = AsyncMock(return_value=mock_sample)
    mock_db.samples.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_db.plm_patterns.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    req = MagicMock()
    req.state.user = mock_admin_user
    req.app.mongodb = mock_db

    payload = CalculateYieldIn(
        material_type="roll",
        material_name="Synthetic Rexine Beige",
        roll_width_inches=54.0,
        standard_strips=[
            StandardStripItem(
                name="Front Lace",
                folded_width_mm=8.0,
                length_mm=650.0,
                pieces_per_pair=2,
            )
        ],
    )

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await calculate_sample_yield(sid=sid, payload=payload, request=req)

    assert res["ok"] is True
    assert "yield_spec" in res
    assert res["yield_spec"]["consumption_per_pair"] > 0.0
    mock_db.samples.update_one.assert_called_once()


@pytest.mark.anyio
async def test_yield_calculation_locked_until_sample_ready(mock_db, mock_admin_user):
    """Verify business rule: Yield calculation & pattern scan are locked during 'draft' and 'in_sampling'."""
    from fastapi import HTTPException
    sid = str(ObjectId())
    draft_sample = {
        "_id": ObjectId(sid),
        "sample_name": "Unapproved Sandal",
        "status": "in_sampling",  # On workshop floor, not marked ready yet
        "pattern_pieces": [{"piece_id": "p1", "area_sqcm": 50.0, "pieces_per_pair": 2}],
    }
    mock_db.samples.find_one = AsyncMock(return_value=draft_sample)

    req = MagicMock()
    req.state.user = mock_admin_user
    req.app.mongodb = mock_db
    payload = CalculateYieldIn(material_type="roll")

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        with pytest.raises(HTTPException) as exc_info:
            await calculate_sample_yield(sid=sid, payload=payload, request=req)
        assert exc_info.value.status_code == 400
        assert "Yield calculation is locked" in exc_info.value.detail


@pytest.mark.anyio
async def test_pattern_library_and_re_use(mock_db, mock_admin_user):
    """Verify pattern library listing, saving to library, and re-using in a new sample."""
    sid = str(ObjectId())
    mock_sample = {
        "_id": ObjectId(sid),
        "temp_code": "SMP-2026-0009",
        "sample_name": "Derby Oxford",
        "pattern_pieces": [
            {"piece_id": "vamp_1", "piece_name": "Vamp", "area_sqcm": 95.0, "pieces_per_pair": 2}
        ],
        "standard_strips": [
            {"strip_id": "s1", "name": "Folded Lace", "folded_width_mm": 8.0, "cut_width_mm": 16.0}
        ],
        "yield_spec": {"consumption_per_pair": 0.15, "yield_per_unit": 6.67},
    }

    mock_db.samples.find_one = AsyncMock(return_value=mock_sample)
    mock_db.samples.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_db.plm_patterns.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    # Mock cursor for library listing
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[
        {
            "_id": ObjectId(),
            "pattern_code": "PAT-DERBY",
            "pattern_name": "Derby Master Pattern",
            "pattern_pieces": mock_sample["pattern_pieces"],
            "standard_strips": mock_sample["standard_strips"],
            "yield_spec": mock_sample["yield_spec"],
        }
    ])
    mock_db.plm_patterns.find.return_value = mock_cursor

    req = MagicMock()
    req.state.user = mock_admin_user
    req.app.mongodb = mock_db

    # 1. Test List Pattern Library
    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        lib_res = await list_pattern_library(request=req)
        assert len(lib_res) == 1
        assert lib_res[0]["pattern_code"] == "PAT-DERBY"

    # 2. Test Save to Library
    save_payload = SaveToLibraryIn(pattern_name="Derby Master Pattern", category="Upper Pattern")
    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        save_res = await save_sample_pattern_to_library(sid=sid, payload=save_payload, request=req)
        assert save_res["ok"] is True
        assert "Pattern successfully saved" in save_res["message"]

    # 3. Test Import / Re-use Pattern in another sample
    target_pat = {
        "_id": ObjectId(),
        "pattern_code": "PAT-DERBY",
        "pattern_name": "Derby Master Pattern",
        "pattern_pieces": mock_sample["pattern_pieces"],
        "standard_strips": mock_sample["standard_strips"],
        "yield_spec": mock_sample["yield_spec"],
        "scan_url": "https://img.io/pattern_derby.png",
    }
    mock_db.plm_patterns.find_one = AsyncMock(return_value=target_pat)

    import_payload = ImportPatternIn(pattern_code="PAT-DERBY")
    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        import_res = await import_pattern_to_sample(sid=sid, payload=import_payload, request=req)
        assert import_res["ok"] is True
        assert "Successfully imported pattern PAT-DERBY" in import_res["message"]


@pytest.mark.anyio
async def test_transfer_to_style_injects_folded_laces_and_saves_to_digital_folder(mock_db, mock_admin_user):
    """Verify that when a sample is transferred to Style Master:
    1. Upper BOM receives calibrated yield + folded laces with raw cut width (2 * folded width).
    2. Locked standard presets are injected for Insole Board (26 prs/sheet) and Socks Covering (8 prs/m).
    3. Document is automatically saved to the Style's Digital Folder 03 (Upper Patterns).
    """
    sid = str(ObjectId())
    mock_sample = {
        "_id": ObjectId(sid),
        "temp_code": "SMP-2026-0008",
        "sample_name": "Lacebuckle",
        "profile": "flat",
        "status": "approved",
        "pattern_scan_url": "https://img.io/pattern_lacebuckle.png",
        "pattern_pieces": [
            {"piece_id": "vamp_1", "piece_name": "Vamp", "area_sqcm": 85.0, "pieces_per_pair": 2}
        ],
        "standard_strips": [
            {
                "name": "Main Ankle Lace",
                "folded_width_mm": 8.0,
                "cut_width_mm": 16.0,
                "length_mm": 650.0,
                "pieces_per_pair": 2,
                "consumption_per_pair": 0.016,
                "yield_per_meter": 62.5,
            }
        ],
        "upper_spec": {
            "materials": [
                {
                    "material_id": "mat_123",
                    "material_name": "Parisnapa Brown",
                    "material_code": "MAT-001",
                    "placement": "Primary",
                    "color_to_develop": "Brown",
                }
            ],
            "cutting_operation": "die_cut",
            "stitching_operation": "stitching",
            "edge_treatment": "none",
        },
        "insole_spec": {"profile_type": "flat", "base_board": "cellulose_board"},
        "sole_spec": {"sole_material": "PVC", "mould_name": "Ginger"},
        "inspiration_photos": [],
        "yield_spec": {
            "material_type": "roll",
            "consumption_per_pair": 0.1425,
            "consumption_unit": "meter",
            "yield_per_unit": 7.02,
            "waste_pct": 14.8,
            "utilization_pct": 85.2,
        },
    }

    mock_db.samples.find_one = AsyncMock(return_value=mock_sample)
    mock_db.styles.find_one = AsyncMock(return_value=None)
    mock_db.styles.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.samples.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_db.materials.find_one = AsyncMock(return_value={"_id": ObjectId(), "rate": 250.0, "unit": "meter"})
    mock_db.plm_documents.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.plm_patterns.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_db.style_folders.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

    req = MagicMock()
    req.state.user = mock_admin_user
    req.app.mongodb = mock_db

    payload = TransferToStyleIn(
        style_code="SS-2026-0042",
        name="Lacebuckle Production",
    )

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await transfer_sample_to_style(sid, payload, req)

    assert res["ok"] is True
    # Verify the inserted style's BOM items
    inserted_style = mock_db.styles.insert_one.call_args[0][0]
    bom_items = inserted_style["bom"]

    # 1. Main Upper Item
    upper_item = next(item for item in bom_items if item["section"] == "Upper")
    assert upper_item["quantity"] == pytest.approx(1.0, 0.0001)
    assert upper_item["yield_per_unit"] == pytest.approx(7.02, 0.01)

    # 2. Folded Lace Item in BOM with 2x folded width
    lace_item = next(item for item in bom_items if "Main Ankle Lace" in item["material_name"])
    assert lace_item["section"] == "Upper"
    assert "Raw Cut 16.0mm" in lace_item["material_name"]

    # 3. Standard Insole Board Preset (26 prs/sheet)
    insole_item = next(item for item in bom_items if item["section"] == "Insole" and "Insole Base" in item["material_name"])
    assert insole_item["quantity"] == pytest.approx(1.0, 0.001)
    assert insole_item["yield_per_unit"] == pytest.approx(26.0, 0.1)

    # 4. Standard Socks / Bottom Covering Preset (8 prs/meter)
    socks_item = next(item for item in bom_items if item["section"] == "Insole" and "Socks" in item["material_name"])
    assert socks_item["quantity"] == pytest.approx(1.0, 0.001)
    assert socks_item["yield_per_unit"] == pytest.approx(8.0, 0.1)

    # 5. Digital Style Folder PLM Archival
    mock_db.plm_documents.insert_one.assert_called_once()
    plm_doc = mock_db.plm_documents.insert_one.call_args[0][0]
    assert plm_doc["folder_code"] == "03"
    assert plm_doc["folder_name"] == "03 Upper Patterns"
    assert plm_doc["style_code"] == "SS-2026-0042"
    assert plm_doc["pattern_category"] == "Upper Pattern"


def test_material_form_dimensions_and_lace_material_definition():
    """Verify:
    1. Material dimension normalization: Roll default 50" -> 1270mm; Sheet default 40"x60" -> 1016mm x 1524mm.
    2. Lace calculation with defined material link (from material master) and material length/width definition.
    """
    from routes.materials import _normalize_material_dimensions
    from services.yield_nesting_service import calculate_standard_strip

    # 1. Roll material with default 50" width
    roll_doc = {"material_form": "roll", "dimension_unit": "inch", "roll_width": 50.0}
    norm_roll = _normalize_material_dimensions(roll_doc)
    assert norm_roll["width_mm"] == 1270.0
    assert norm_roll["height_mm"] is None

    # 2. Sheet material with default 40" x 60"
    sheet_doc = {"material_form": "sheet", "dimension_unit": "inch", "sheet_width": 40.0, "sheet_height": 60.0}
    norm_sheet = _normalize_material_dimensions(sheet_doc)
    assert norm_sheet["width_mm"] == 1016.0
    assert norm_sheet["height_mm"] == 1524.0

    # 3. Sheet material in cm (e.g. 100cm x 150cm)
    sheet_cm_doc = {"material_form": "sheet", "dimension_unit": "cm", "sheet_width": 100.0, "sheet_height": 150.0}
    norm_cm_sheet = _normalize_material_dimensions(sheet_cm_doc)
    assert norm_cm_sheet["width_mm"] == 1000.0
    assert norm_cm_sheet["height_mm"] == 1500.0

    # 4. Lace calculation with linked material and custom material width (50" roll, 25m length)
    lace_strip = {
        "strip_id": "lace_paris_brown",
        "name": "Paris Brown 8mm Folded Lace",
        "folded_width_mm": 8.0,
        "cut_width_mm": 16.0,
        "length_mm": 650.0,
        "pieces_per_pair": 2,
        # Linked material from materials master:
        "material_id": "mat_paris_99",
        "material_name": "Parisnapa Synthetic Brown",
        "material_code": "MAT-SYN-001",
        "material_rate": 220.0,
        # Defined material dimensions:
        "material_width": 50.0,
        "material_width_unit": "inch",
        "material_length": 25.0,
        "material_length_unit": "meter",
    }
    calc = calculate_standard_strip(lace_strip)

    # 50" = 1270mm. Usable width with 20mm selvage each side = 1230mm.
    # cut_w = 16mm, kerf = 1mm -> 17mm/lane. lanes = 1230 // 17 = 72 lanes.
    assert calc["material_id"] == "mat_paris_99"
    assert calc["material_name"] == "Parisnapa Synthetic Brown"
    assert calc["material_code"] == "MAT-SYN-001"
    assert calc["material_width"] == 50.0
    assert calc["material_width_mm"] == 1270.0
    assert calc["roll_length_meters"] == 25.0
    assert calc["lanes_across_roll"] == 72
    # In 1 meter: 72 lanes * 1000mm / 650mm = 110.77 laces/m
    assert calc["laces_yield_per_meter"] == pytest.approx(110.77, 0.1)
    # Pairs per meter before waste: 110.77 / 2 = 55.38 prs/m
    assert calc["pairs_per_meter"] == pytest.approx(55.38, 0.1)
    # Total laces on 25m roll: 111 * 25 = 2769 laces
    assert calc["total_laces_full_roll"] == round(110.77 * 25.0)
    # Cost per pair = consumption_per_pair * 220.0
    assert calc["cost_per_pair"] > 0

