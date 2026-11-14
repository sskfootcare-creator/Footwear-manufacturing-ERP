"""Unit & Integration Tests for Footwear Sample Development & Tracking System."""

import pytest
import asyncio
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch

from models.sampling import (
    SampleCreateIn,
    SampleUpdateIn,
    TransferToStyleIn,
    UpperSpec,
    InsoleSpec,
    SoleSpec,
)
from routes.sampling import (
    _next_sample_code,
    create_sample,
    get_sample,
    list_samples,
    update_sample,
    update_sample_status,
    transfer_sample_to_style,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Mock collections
    db.samples = MagicMock()
    db.styles = MagicMock()
    db.materials = MagicMock()
    db.workers = MagicMock()
    db.counters = MagicMock()
    db.image_uploads = MagicMock()
    db.style_folders = MagicMock()
    return db


@pytest.fixture
def mock_admin_user():
    return {
        "email": "admin@example.com",
        "role": "admin",
        "username": "Admin",
    }


@pytest.mark.anyio
async def test_next_sample_code_increments_atomically(mock_db):
    """Verify sample code follows SMP-YYYY-XXXX sequential atomic generation."""
    mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 42})
    code = await _next_sample_code(mock_db)
    assert code.startswith("SMP-")
    assert code.endswith("-0042")


@pytest.mark.anyio
async def test_create_sample_with_specs(mock_db, mock_admin_user):
    """Verify creating a sample assigns temporary code, draft status, and stores specs."""
    mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
    inserted_id = ObjectId()
    mock_db.samples.insert_one = AsyncMock(return_value=MagicMock(inserted_id=inserted_id))

    request = MagicMock()
    request.state.user = mock_admin_user

    payload = SampleCreateIn(
        sample_name="Strappy Block Heel Sandal",
        profile="heeled",
        category="Women Footwear",
        season="SS26",
        upper_spec=UpperSpec(
            upper_top_material_name="Metallic Rose Synthetic",
            upper_color_to_develop="Rose Gold",
            canvas_backing="10oz Micro Canvas",
            lining_material_name="Breathable PU Lining",
            cutting_operation="die_cut",
            stitching_operation="stitching",
            edge_treatment="edge_coloring",
            has_buckle=True,
            buckle_spec="15mm Oval Gold Buckle",
        ),
        insole_spec=InsoleSpec(
            profile_type="heeled",
            heeled_category="block_heel",
            insole_style_code_shape="HEEL-BLOCK-45-SQ",
            base_board="cellulose_board",
            shank_reinforced=True,
            cushioning_type="both",
            cushioning_thickness_mm="3mm EVA + 2mm PU Foam",
            socks_covering_type="matching",
            embossing="gold_foil",
            embossing_details="SSK Brand Logo Stamp",
        ),
        sole_spec=SoleSpec(
            sole_material="TPR",
            sole_type="ready_made",
            mould_name="TPR-HEEL-M03",
            sole_shape="Square",
            velting=True,
            attaching_top_piece=True,
            heel_type="block_heel",
            heel_mould_name="M-BLK-55MM",
            heel_height="55mm / 2.2 inch",
            heel_finish="covered",
            heel_covering_type="matching",
        ),
    )

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await create_sample(payload, request)

    assert res["sample_name"] == "Strappy Block Heel Sandal"
    assert res["profile"] == "heeled"
    assert res["temp_code"].startswith("SMP-")
    assert res["status"] == "draft"
    assert res["upper_spec"]["has_buckle"] is True
    assert res["insole_spec"]["base_board"] == "cellulose_board"
    assert res["sole_spec"]["heel_finish"] == "covered"


@pytest.mark.anyio
async def test_sample_status_lifecycle_and_rejection(mock_db, mock_admin_user):
    """Verify status advancement and rejection handling."""
    sample_id = ObjectId()
    sample_doc = {
        "_id": sample_id,
        "temp_code": "SMP-2026-0005",
        "sample_name": "Casual Loafer",
        "status": "draft",
    }
    mock_db.samples.find_one = AsyncMock(return_value=sample_doc)
    mock_db.samples.update_one = AsyncMock()

    request = MagicMock()
    request.state.user = mock_admin_user

    # Advance to in_sampling
    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await update_sample_status(str(sample_id), "in_sampling", request)
        assert mock_db.samples.update_one.called
        call_args = mock_db.samples.update_one.call_args[0][1]["$set"]
        assert call_args["status"] == "in_sampling"

    # Reject sample with reason
    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res_rej = await update_sample_status(
            str(sample_id),
            "rejected",
            request,
            rejection_reason="Sole fitting mould too loose at toe area",
        )
        call_args_rej = mock_db.samples.update_one.call_args[0][1]["$set"]
        assert call_args_rej["status"] == "rejected"
        assert call_args_rej["rejection_reason"] == "Sole fitting mould too loose at toe area"


@pytest.mark.anyio
async def test_transfer_to_style_master_creates_full_bom_and_labor(mock_db, mock_admin_user):
    """Verify transferring an approved sample into Style Master:
    - Sets unique ERP Style Code
    - Pre-populates BOM with material yields
    - Pre-populates Labor operations with cutting, stitching, lasting, pasting
    - Updates sample state to transferred_to_style
    """
    sample_id = ObjectId()
    sample_doc = {
        "_id": sample_id,
        "temp_code": "SMP-2026-0010",
        "sample_name": "Party Platform Pump",
        "profile": "heeled",
        "category": "Women Footwear",
        "status": "approved",
        "inspiration_photos": [
            {"url": "/api/uploads/samples_inspiration/sample1.jpg", "is_primary": True}
        ],
        "upper_spec": {
            "upper_top_material_name": "Velvet Suede Synthetic",
            "upper_color_to_develop": "Wine Red",
            "canvas_backing": "Twill Cotton Canvas",
            "lining_material_name": "Microfiber Suede Lining",
            "cutting_operation": "folding",
            "stitching_operation": "stitching",
            "edge_treatment": "edge_coloring",
            "has_buckle": True,
            "buckle_spec": "Square Rhinestone Buckle 20mm",
        },
        "insole_spec": {
            "profile_type": "heeled",
            "heeled_category": "platforms",
            "insole_style_code_shape": "PLAT-SHAPE-37-ALMOND",
            "base_board": "paper_board",
            "cushioning_type": "both",
            "cushioning_thickness_mm": "5mm EVA + PU",
            "socks_covering_type": "matching",
            "embossing": "gold_foil",
            "embossing_details": "Gold Leaf Signature",
            "printing": "none",
        },
        "sole_spec": {
            "sole_material": "Neolite",
            "sole_type": "die_cut",
            "mould_name": "NEOLITE-PUMP-01",
            "sole_shape": "Almond",
            "velting": True,
            "grinding": True,
            "attaching_top_piece": True,
            "heel_type": "platform_gola",
            "heel_mould_name": "GOLA-PLAT-70MM",
            "heel_height": "70mm / 2.75 inch",
            "heel_finish": "covered",
            "heel_covering_type": "matching",
        },
    }

    mock_db.samples.find_one = AsyncMock(return_value=sample_doc)
    mock_db.styles.find_one = AsyncMock(return_value=None)  # Style code is unique
    new_style_oid = ObjectId()
    mock_db.styles.insert_one = AsyncMock(return_value=MagicMock(inserted_id=new_style_oid))
    mock_db.samples.update_one = AsyncMock()
    mock_db.style_folders.insert_one = AsyncMock()

    request = MagicMock()
    request.state.user = mock_admin_user

    transfer_payload = TransferToStyleIn(
        style_code="SSK-PLAT-001",
        name="Wine Red Platform Pump",
        base_size="7",
        material_yields={
            "upper_top": 1.4,
            "canvas": 0.2,
            "lining": 1.1,
            "base_board": 1.0,
            "cushioning": 1.0,
            "socks_covering": 0.9,
            "sole": 1.0,
            "heel": 1.0,
            "buckle": 1.0,
        },
        labor_rates={
            "cutting": 15.0,
            "stitching": 30.0,
            "edge_coloring": 10.0,
            "insole_making": 12.0,
            "embossing": 6.0,
            "sole_prep": 18.0,
            "heel_work": 14.0,
            "lasting": 25.0,
            "pasting": 22.0,
            "finishing": 12.0,
        },
        use_sample_photo_as_primary=True,
    )

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await transfer_sample_to_style(str(sample_id), transfer_payload, request)

    assert res["ok"] is True
    style_inserted = mock_db.styles.insert_one.call_args[0][0]
    assert style_inserted["code"] == "SSK-PLAT-001"
    assert style_inserted["name"] == "Wine Red Platform Pump"
    assert style_inserted["footwear_type"] == "heel"
    assert style_inserted["image_url"] == "/api/uploads/samples_inspiration/sample1.jpg"

    # Verify BOM lines
    bom = style_inserted["bom"]
    sections = [b["section"] for b in bom]
    assert "Upper" in sections
    assert "Lining" in sections
    assert "Insole" in sections
    assert "Sole" in sections
    assert "Accessories" in sections

    # Check upper yield
    upper_line = next(b for b in bom if "Velvet Suede" in b["material_name"])
    assert upper_line["quantity"] == 1.4
    assert upper_line["color"] == "Wine Red"

    # Verify Labor operations
    labor = style_inserted["labor"]
    labor_names = [l["name"] for l in labor]
    assert any("Cutting" in n for n in labor_names)
    assert any("Stitching" in n for n in labor_names)
    assert any("Edge Coloring" in n for n in labor_names)
    assert any("Insole Board" in n for n in labor_names)
    assert any("Sole Processing" in n for n in labor_names)
    assert any("Lasting" in n for n in labor_names)
    assert any("Pasting" in n for n in labor_names)
    assert any("Finishing" in n for n in labor_names)

    # Verify sample updated to transferred_to_style
    sample_update = mock_db.samples.update_one.call_args[0][1]["$set"]
    assert sample_update["status"] == "transferred_to_style"
    assert sample_update["transferred_style_code"] == "SSK-PLAT-001"


@pytest.mark.anyio
async def test_inspiration_photo_isolation(mock_db, mock_admin_user):
    """Verify that uploaded sample photos are isolated:
    - Path resides in uploads/samples_inspiration/
    - Tagged category='sample_inspiration'
    - Marked is_sample_inspiration=True
    """
    from routes.sampling import upload_sample_photo
    import io
    from fastapi import UploadFile

    sample_id = ObjectId()
    sample_doc = {
        "_id": sample_id,
        "temp_code": "SMP-2026-0099",
        "inspiration_photos": [],
    }
    mock_db.samples.find_one = AsyncMock(return_value=sample_doc)
    mock_db.samples.update_one = AsyncMock()
    mock_db.image_uploads.insert_one = AsyncMock()

    request = MagicMock()
    request.state.user = mock_admin_user

    # Create dummy JPEG bytes
    dummy_jpg = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 50
    file_obj = UploadFile(filename="sample_inspiration_shoe.jpg", file=io.BytesIO(dummy_jpg))

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)), \
         patch("routes.sampling.validate_uploaded_file", AsyncMock(return_value=(dummy_jpg, "sample_inspiration_shoe.jpg"))), \
         patch("builtins.open", MagicMock()):
        res = await upload_sample_photo(
            str(sample_id),
            request,
            file=file_obj,
            caption="Runway inspiration mood board",
            is_primary=True,
        )

    assert res["ok"] is True
    photo = res["photo"]
    assert "/api/uploads/samples_inspiration/" in photo["url"]
    assert photo["category"] == "sample_inspiration"
    assert photo["is_primary"] is True

    # Verify db.image_uploads was called with isolation tags
    img_record = mock_db.image_uploads.insert_one.call_args[0][0]
    assert img_record["category"] == "sample_inspiration"
    assert img_record["is_sample_inspiration"] is True
    assert img_record["sample_id"] == str(sample_id)


@pytest.mark.anyio
async def test_multiple_upper_materials_and_transfer_bom(mock_db, mock_admin_user):
    """Verify multiple upper materials and buckle photos are preserved and transferred to Style BOM."""
    from models.sampling import UpperMaterialItem
    sample_id = ObjectId()
    sample_doc = {
        "_id": sample_id,
        "sample_name": "Multi-Strap Wedge",
        "profile": "flat",
        "temp_code": "SMP-2026-0005",
        "status": "approved",
        "inspiration_photos": [],
        "upper_spec": {
            "materials": [
                {
                    "material_id": "mat-leather-01",
                    "material_name": "Tan Nappa Leather",
                    "material_code": "MAT-LEA-01",
                    "color_to_develop": "Cognac",
                    "placement": "Primary",
                    "photo_url": "/api/uploads/swatch1.jpg"
                },
                {
                    "material_id": "mat-suede-02",
                    "material_name": "Dark Brown Suede",
                    "material_code": "MAT-SUE-02",
                    "color_to_develop": "Espresso",
                    "placement": "Accent Strap",
                    "photo_url": "/api/uploads/swatch2.jpg"
                }
            ],
            "upper_top_material_id": "mat-leather-01",
            "upper_top_material_name": "Tan Nappa Leather",
            "has_buckle": True,
            "buckle_spec": "15mm Brass Buckle",
            "buckle_photo_url": "/api/uploads/buckle1.jpg",
        },
        "insole_spec": {"base_board": "paper_board"},
        "sole_spec": {"sole_material": "TPR", "sole_type": "ready_made"},
    }
    mock_db.samples.find_one = AsyncMock(return_value=sample_doc)
    mock_db.styles.find_one = AsyncMock(return_value=None)
    mock_db.styles.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.samples.update_one = AsyncMock()

    request = MagicMock()
    request.state.user = mock_admin_user

    transfer_payload = TransferToStyleIn(
        style_code="ST-MULTI-01",
        name="Multi-Strap Wedge",
        margin_pct=25.0,
        gst_pct=5.0,
        material_yields={"upper_top": 1.2},
    )

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await transfer_sample_to_style(str(sample_id), transfer_payload, request)

    assert res["ok"] is True

    style_doc = mock_db.styles.insert_one.call_args[0][0]
    assert style_doc["code"] == "ST-MULTI-01"
    bom_items = style_doc["bom"]
    # Check that both upper materials were transferred into BOM
    upper_bom = [b for b in bom_items if b.get("section") == "Upper" and "Tan Nappa" in b.get("material_name", "")]
    strap_bom = [b for b in bom_items if b.get("section") == "Upper" and "Dark Brown Suede" in b.get("material_name", "")]
    assert len(upper_bom) == 1
    assert upper_bom[0]["color"] == "Cognac"
    assert len(strap_bom) == 1
    assert strap_bom[0]["color"] == "Espresso"


@pytest.mark.anyio
async def test_insole_socks_color_transfer(mock_db, mock_admin_user):
    """Verify custom insole socks color is preserved and passed to insole BOM line."""
    sample_id = ObjectId()
    sample_doc = {
        "_id": sample_id,
        "sample_name": "Two-Tone Sandal",
        "profile": "flat",
        "temp_code": "SMP-2026-0009",
        "status": "approved",
        "inspiration_photos": [],
        "upper_spec": {
            "materials": [
                {
                    "material_id": "mat-blk-01",
                    "material_name": "Black Nappa",
                    "color_to_develop": "Jet Black",
                    "placement": "Primary",
                }
            ],
            "upper_top_material_id": "mat-blk-01",
            "upper_top_material_name": "Black Nappa",
            "upper_color_to_develop": "Jet Black",
        },
        "insole_spec": {
            "base_board": "paper_board",
            "socks_covering_type": "custom",
            "socks_material_name": "Beige Synthetic",
            "socks_color": "Tan Nude",
        },
        "sole_spec": {"sole_material": "TPR", "sole_type": "ready_made"},
    }
    mock_db.samples.find_one = AsyncMock(return_value=sample_doc)
    mock_db.styles.find_one = AsyncMock(return_value=None)
    mock_db.styles.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.samples.update_one = AsyncMock()

    request = MagicMock()
    request.state.user = mock_admin_user

    transfer_payload = TransferToStyleIn(
        style_code="ST-TWOTONE-01",
        name="Two-Tone Sandal",
        margin_pct=25.0,
        gst_pct=5.0,
    )

    with patch("routes.sampling.get_db", return_value=mock_db), \
         patch("routes.sampling._get_user", AsyncMock(return_value=mock_admin_user)):
        res = await transfer_sample_to_style(str(sample_id), transfer_payload, request)

    assert res["ok"] is True
    style_doc = mock_db.styles.insert_one.call_args[0][0]
    bom_items = style_doc["bom"]
    socks_bom = [b for b in bom_items if b.get("material_name") == "Beige Synthetic"]
    assert len(socks_bom) == 1
    assert socks_bom[0]["color"] == "Tan Nude"


