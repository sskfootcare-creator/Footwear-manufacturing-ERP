"""Unit tests verifying resolution and upsert mapping for distinct styles FLL_AK_005_GO and FL_AK_005_GO.

Covers:
1. FLL and FL are distinct style families: FLL_AK_005_GO (SSK_00121) and FL_AK_005_GO (SSK_00098).
2. Direct resolution in wms and sku_map does not mangle FLL into FL.
3. strip_known_prefixes and apply_prefix_replacements preserve FLL prefix.
4. create_sku_map supports upsert=True without 409 Conflict error.
"""
import pytest
import asyncio
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request

import server
from models.sku_map import SkuMapIn
from routes.sku_map import create_sku_map, resolve_style, _norm_key
from routes.online_orders import strip_known_prefixes, apply_prefix_replacements


@pytest.mark.anyio
async def test_strip_known_prefixes_preserves_fll():
    # If prefixes contains "FL", it must not strip "FL" from "FLL_AK_005_GO-6"
    res = strip_known_prefixes("FLL_AK_005_GO-6", ["FL", "TH"])
    assert res == "FLL_AK_005_GO-6", f"Expected FLL_AK_005_GO-6 to remain intact, got {res}"

    # But it should strip true prefixes from other SKUs
    res_fl = strip_known_prefixes("FL_AK_005_GO-5", ["TH"])
    assert res_fl == "FL_AK_005_GO-5"

    res_th = strip_known_prefixes("THFL_AK_048_BG_37", ["TH"])
    assert res_th == "FL_AK_048_BG_37"


@pytest.mark.anyio
async def test_apply_prefix_replacements_preserves_fll():
    # Even if replacements map has "FLL": "FL", it must NOT replace FLL
    replacements = {"FLL": "FL", "OLD": "NEW"}
    res, replaced = apply_prefix_replacements("FLL_AK_005_GO-6", replacements)
    assert res == "FLL_AK_005_GO-6"
    assert replaced is None

    # Other replacements still work
    res_other, replaced_other = apply_prefix_replacements("OLD_STYLE_123", replacements)
    assert res_other == "NEW_STYLE_123"
    assert replaced_other == "OLD"


@pytest.mark.anyio
async def test_resolve_style_distinguishes_fll_and_fl():
    s121_id = ObjectId()
    s98_id = ObjectId()

    style_121 = {"_id": s121_id, "code": "SSK_00121", "name": "X GOLD"}
    style_98 = {"_id": s98_id, "code": "SSK_00098", "name": "FL GOLD"}

    mapping_fll = {
        "_id": ObjectId(),
        "source_type": "online_channel",
        "source_name": "myntra",
        "source_name_key": "myntra",
        "external_sku": "FLL_AK_005_GO",
        "external_sku_key": _norm_key("FLL_AK_005_GO"),
        "style_id": str(s121_id),
        "style_code": "SSK_00121",
        "size_map": {"6": "FLL_AK_005_GO-6"},
    }

    mapping_fl = {
        "_id": ObjectId(),
        "source_type": "online_channel",
        "source_name": "myntra",
        "source_name_key": "myntra",
        "external_sku": "FL_AK_005_GO",
        "external_sku_key": _norm_key("FL_AK_005_GO"),
        "style_id": str(s98_id),
        "style_code": "SSK_00098",
        "size_map": {"5": "FL_AK_005_GO-5"},
    }

    mock_db = MagicMock()
    async def find_one_sku_map(query):
        ext_key = query.get("external_sku_key")
        if ext_key == _norm_key("FLL_AK_005_GO"):
            return mapping_fll
        if ext_key == _norm_key("FL_AK_005_GO"):
            return mapping_fl
        return None

    async def find_one_styles(query):
        sid = query.get("_id")
        if sid == s121_id:
            return style_121
        if sid == s98_id:
            return style_98
        return None

    mock_db.sku_map.find_one = AsyncMock(side_effect=find_one_sku_map)
    mock_db.styles.find_one = AsyncMock(side_effect=find_one_styles)

    with patch.object(server, "db", mock_db):
        # Resolve FLL_AK_005_GO-6
        res_fll = await resolve_style("online_channel", "myntra", "FLL_AK_005_GO-6", external_size="6", db=mock_db)
        assert res_fll["matched"] is True
        assert res_fll["style_code"] == "SSK_00121"
        assert res_fll["size"] == "6"

        # Resolve FL_AK_005_GO-5
        res_fl = await resolve_style("online_channel", "myntra", "FL_AK_005_GO-5", external_size="5", db=mock_db)
        assert res_fl["matched"] is True
        assert res_fl["style_code"] == "SSK_00098"
        assert res_fl["size"] == "5"


@pytest.mark.anyio
async def test_create_sku_map_upsert():
    from fastapi import HTTPException

    s121_id = ObjectId()
    style_121 = {"_id": s121_id, "code": "SSK_00121", "name": "X GOLD"}

    existing_map_id = ObjectId()
    existing_mapping = {
        "_id": existing_map_id,
        "source_type": "online_channel",
        "source_name": "myntra",
        "source_name_key": "myntra",
        "external_sku": "FLL_AK_005_GO",
        "external_sku_key": _norm_key("FLL_AK_005_GO"),
        "style_id": str(ObjectId()), # previously mapped to old style
        "style_code": "OLD_CODE",
        "size_map": {"5": "FLL_AK_005_GO-5"},
    }

    mock_db = MagicMock()
    mock_db.styles.find_one = AsyncMock(return_value=style_121)
    mock_db.sku_map.find_one = AsyncMock(return_value=existing_mapping)
    mock_db.sku_map.update_one = AsyncMock()
    mock_db.activity_logs.insert_one = AsyncMock()
    mock_db.production_jobs.find.return_value.to_list = AsyncMock(return_value=[])

    mock_request = MagicMock(spec=Request)
    mock_request.app = MagicMock()
    mock_request.app.mongodb = mock_db
    mock_request.state = MagicMock()
    mock_request.state.user = {"email": "admin@example.com", "role": "admin"}

    payload = SkuMapIn(
        style_id=str(s121_id),
        source_type="online_channel",
        source_name="myntra",
        external_sku="FLL_AK_005_GO",
        size_map={"6": "FLL_AK_005_GO-6"},
    )

    with patch("routes.sku_map._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin"})):
        # 1. Without upsert, must raise 409
        with pytest.raises(HTTPException) as exc_info:
            await create_sku_map(payload, mock_request, upsert=False)
        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

        # 2. With upsert=True, must successfully update
        res = await create_sku_map(payload, mock_request, upsert=True)
        assert res["id"] == str(existing_map_id)
        mock_db.sku_map.update_one.assert_called_once()
        call_args = mock_db.sku_map.update_one.call_args[0]
        assert call_args[0] == {"_id": existing_map_id}
        update_set = call_args[1]["$set"]
        assert update_set["style_id"] == str(s121_id)
        assert update_set["style_code"] == "SSK_00121"
        # Verify sizes merged
        assert update_set["size_map"]["5"] == "FLL_AK_005_GO-5"
        assert update_set["size_map"]["6"] == "FLL_AK_005_GO-6"
