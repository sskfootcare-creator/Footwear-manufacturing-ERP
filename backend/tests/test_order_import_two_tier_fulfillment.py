import asyncio
import io
from bson import ObjectId
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import UploadFile

from routes.online_orders import import_configured_online_orders

CSV_TEST_ORDER = b"""order_no,item_sku,qty,color,size
ORD-1001,SKU-SSK-001,10,Tan,8"""

def _build_base_env():
    mock_db = MagicMock()
    mock_user = {"email": "admin@example.com", "role": "admin"}

    cfg_doc = {
        "platform": "generic",
        "role": "order",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id": "order_no",
            "leaf_sku": "item_sku",
            "qty": "qty",
            "color": "color",
            "size": "size",
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {},
        "is_picklist": False,
        "active": True,
    }

    style_id = ObjectId()
    style_doc = {
        "_id": style_id,
        "code": "SSK_00034",
        "name": "Flat Sandal",
    }

    sku_mapping = {
        "_id": ObjectId(),
        "style_id": str(style_id),
        "style_code": "SSK_00034",
        "source_type": "online_channel",
        "source_name": "generic",
        "source_name_key": "generic",
        "external_sku": "SKU-SSK-001",
        "external_sku_key": "sku-ssk-001",
        "color": "Tan",
        "color_map": {},
        "size_map": {"8": "8"},
    }

    return mock_db, mock_user, cfg_doc, style_doc, sku_mapping


def test_two_tier_full_finished_goods_stock():
    async def run():
        mock_db, mock_user, cfg_doc, style_doc, sku_mapping = _build_base_env()

        # In-stock finished goods: 15 pairs available (order needs 10)
        fg_loc_id = ObjectId()
        fg_record = {
            "_id": fg_loc_id,
            "style_id": style_doc["_id"],
            "location_code": "R01-RK1-C01",
            "color": "Tan",
            "size": "8",
            "qty": 15,
            "reserved_qty": 0,
        }

        async def mock_find_one(query, *args, **kwargs):
            if "platform" in query:
                return cfg_doc
            if query.get("location_code") == "R01-RK1-C01":
                return {"location_code": "R01-RK1-C01", "status": "active", "rack": "R01", "row": "RK1", "cell": "C01"}
            if "_id" in query and isinstance(query["_id"], ObjectId):
                return style_doc
            if query.get("external_sku_key") == "sku-ssk-001":
                return sku_mapping
            return None

        mock_db.order_import_format_configs.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.sku_map.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.styles.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.warehouse_locations.find_one = AsyncMock(side_effect=mock_find_one)

        # Mock fg_location_inventory cursor
        cursor_mock = MagicMock()
        cursor_mock.sort.return_value = cursor_mock
        cursor_mock.to_list = AsyncMock(return_value=[fg_record])

        # For _generate_picklist_for_order which does `async for loc in cur:`
        async def mock_async_iter():
            yield fg_record
        cursor_mock.__aiter__ = lambda self: mock_async_iter()

        mock_db.fg_location_inventory.find = MagicMock(return_value=cursor_mock)
        mock_db.fg_location_inventory.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.picklists.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        mock_db.production_jobs.insert_many = AsyncMock()

        mock_picklist_doc = {
            "_id": ObjectId(),
            "picklist_no": "PL-20260916-001",
            "order_id": "ORD-1001",
            "channel": "generic",
            "status": "pending",
            "total_qty": 10,
            "items": [{"location_code": "R01-RK1-C01", "qty": 10}],
        }

        file_obj = UploadFile(filename="orders.csv", file=io.BytesIO(CSV_TEST_ORDER))
        with patch("routes.online_orders._get_user", AsyncMock(return_value=mock_user)), \
             patch("routes.online_orders.get_db", return_value=mock_db), \
             patch("routes.wms._generate_picklist_for_order", AsyncMock(return_value=(mock_picklist_doc, {}, {}))) as mock_gen_pl:

            # 1. Preview mode (dry_run=True)
            res_preview = await import_configured_online_orders(
                file=file_obj, platform="generic", dry_run=True, request=MagicMock()
            )

            assert res_preview["stats"]["matched"] == 1
            assert res_preview["stats"]["pairs_fulfilled_from_stock"] == 10
            assert res_preview["stats"]["pairs_to_manufacture"] == 0
            assert res_preview["rows"][0]["fulfillment_status"] == "in_stock_picklist"
            assert res_preview["rows"][0]["covered_qty"] == 10
            assert res_preview["rows"][0]["remaining_qty"] == 0

            # 2. Commit mode (dry_run=False)
            file_obj2 = UploadFile(filename="orders.csv", file=io.BytesIO(CSV_TEST_ORDER))
            res_commit = await import_configured_online_orders(
                file=file_obj2, platform="generic", dry_run=False, request=MagicMock()
            )

            assert res_commit["committed"]["picklists_created"] == 1
            assert res_commit["committed"]["jobs_created"] == 0
            assert res_commit["committed"]["pairs_fulfilled_from_stock"] == 10
            assert res_commit["committed"]["pairs_to_manufacture"] == 0
            mock_gen_pl.assert_awaited_once()

    asyncio.run(run())


def test_two_tier_partial_fg_stock_and_cutting_for_remainder():
    async def run():
        mock_db, mock_user, cfg_doc, style_doc, sku_mapping = _build_base_env()

        # Only 4 pairs available in FG stock (order needs 10, so 6 remainder)
        fg_loc_id = ObjectId()
        fg_record = {
            "_id": fg_loc_id,
            "style_id": style_doc["_id"],
            "location_code": "R01-RK1-C01",
            "color": "Tan",
            "size": "8",
            "qty": 4,
            "reserved_qty": 0,
        }

        # BOM exists with 1 component: Sole
        comp_id = ObjectId()
        bom_item = {
            "style_id": style_doc["_id"],
            "component_id": comp_id,
            "component_code": "SOL-001",
            "quantity_per_pair": 1,
            "active": True,
        }
        # Component has plenty of stock (100 free)
        comp_doc = {
            "_id": comp_id,
            "component_code": "SOL-001",
            "component_name": "Rubber Sole",
            "current_stock": 100,
            "reserved_stock": 0,
        }

        async def mock_find_one(query, *args, **kwargs):
            if "platform" in query:
                return cfg_doc
            if query.get("location_code") == "R01-RK1-C01":
                return {"location_code": "R01-RK1-C01", "status": "active", "rack": "R01", "row": "RK1", "cell": "C01"}
            if "_id" in query and isinstance(query["_id"], ObjectId):
                if query["_id"] == style_doc["_id"]:
                    return style_doc
                if query["_id"] == comp_id:
                    return comp_doc
            if query.get("component_code") == "SOL-001":
                return comp_doc
            if query.get("external_sku_key") == "sku-ssk-001":
                return sku_mapping
            return None

        mock_db.order_import_format_configs.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.sku_map.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.styles.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.warehouse_locations.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.component_master.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.component_master.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        # Mock fg_location_inventory cursor
        fg_cursor = MagicMock()
        fg_cursor.sort.return_value = fg_cursor
        fg_cursor.to_list = AsyncMock(return_value=[fg_record])
        mock_db.fg_location_inventory.find = MagicMock(return_value=fg_cursor)

        # Mock style_component_mapping cursor
        bom_cursor = MagicMock()
        bom_cursor.to_list = AsyncMock(return_value=[bom_item])
        mock_db.style_component_mapping.find = MagicMock(return_value=bom_cursor)

        mock_db.production_jobs.insert_many = AsyncMock()

        mock_picklist_doc = {
            "_id": ObjectId(),
            "picklist_no": "PL-20260916-002",
            "order_id": "ORD-1001",
            "channel": "generic",
            "status": "pending",
            "total_qty": 4,
            "items": [{"location_code": "R01-RK1-C01", "qty": 4}],
        }

        file_obj = UploadFile(filename="orders.csv", file=io.BytesIO(CSV_TEST_ORDER))
        with patch("routes.online_orders._get_user", AsyncMock(return_value=mock_user)), \
             patch("routes.online_orders.get_db", return_value=mock_db), \
             patch("routes.wms._generate_picklist_for_order", AsyncMock(return_value=(mock_picklist_doc, {}, {}))) as mock_gen_pl:
            res = await import_configured_online_orders(
                file=file_obj, platform="generic", dry_run=False, request=MagicMock()
            )

        # 4 pairs covered by picklist, 6 pairs remaining for production
        assert res["committed"]["picklists_created"] == 1
        assert res["committed"]["jobs_created"] == 1
        assert res["committed"]["pairs_fulfilled_from_stock"] == 4
        assert res["committed"]["pairs_to_manufacture"] == 6

        # Check job stage is 'cutting' because components were available
        inserted_jobs = mock_db.production_jobs.insert_many.call_args[0][0]
        assert len(inserted_jobs) == 1
        job = inserted_jobs[0]
        assert job["quantity"] == 6
        assert job["covered_from_stock_qty"] == 4
        assert job["stage"] == "cutting"
        assert job["components_available"] is True
        mock_gen_pl.assert_awaited_once()

    asyncio.run(run())


def test_two_tier_shortage_no_bom():
    async def run():
        mock_db, mock_user, cfg_doc, style_doc, sku_mapping = _build_base_env()

        # 0 FG stock
        fg_cursor = MagicMock()
        fg_cursor.sort.return_value = fg_cursor
        fg_cursor.to_list = AsyncMock(return_value=[])
        mock_db.fg_location_inventory.find = MagicMock(return_value=fg_cursor)

        # No BOM mapped
        bom_cursor = MagicMock()
        bom_cursor.to_list = AsyncMock(return_value=[])
        mock_db.style_component_mapping.find = MagicMock(return_value=bom_cursor)

        async def mock_find_one(query, *args, **kwargs):
            if "platform" in query:
                return cfg_doc
            if "_id" in query and isinstance(query["_id"], ObjectId):
                return style_doc
            if query.get("external_sku_key") == "sku-ssk-001":
                return sku_mapping
            return None

        mock_db.order_import_format_configs.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.sku_map.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.styles.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.production_jobs.insert_many = AsyncMock()

        file_obj = UploadFile(filename="orders.csv", file=io.BytesIO(CSV_TEST_ORDER))
        with patch("routes.online_orders._get_user", AsyncMock(return_value=mock_user)), \
             patch("routes.online_orders.get_db", return_value=mock_db):
            res = await import_configured_online_orders(
                file=file_obj, platform="generic", dry_run=False, request=MagicMock()
            )

        # 0 picklists, 1 job created
        assert res["committed"]["picklists_created"] == 0
        assert res["committed"]["jobs_created"] == 1
        assert res["committed"]["pairs_to_manufacture"] == 10

        # Check job routed to 'procurement' due to NO_BOM
        inserted_jobs = mock_db.production_jobs.insert_many.call_args[0][0]
        job = inserted_jobs[0]
        assert job["quantity"] == 10
        assert job["stage"] == "procurement"
        assert job["components_available"] is False
        assert job["has_bom"] is False
        assert any(s.get("component_code") == "NO_BOM" for s in job["component_shortages"])

    asyncio.run(run())


def test_two_tier_component_stock_insufficient():
    async def run():
        mock_db, mock_user, cfg_doc, style_doc, sku_mapping = _build_base_env()

        # 0 FG stock
        fg_cursor = MagicMock()
        fg_cursor.sort.return_value = fg_cursor
        fg_cursor.to_list = AsyncMock(return_value=[])
        mock_db.fg_location_inventory.find = MagicMock(return_value=fg_cursor)

        # BOM exists with 1 component: Sole (needs 1 per pair -> 10 pairs needed)
        comp_id = ObjectId()
        bom_item = {
            "style_id": style_doc["_id"],
            "component_id": comp_id,
            "component_code": "SOL-001",
            "quantity_per_pair": 1,
            "active": True,
        }
        # Component has only 2 units in stock (need 10, shortage of 8)
        comp_doc = {
            "_id": comp_id,
            "component_code": "SOL-001",
            "component_name": "Rubber Sole",
            "current_stock": 2,
            "reserved_stock": 0,
        }

        bom_cursor = MagicMock()
        bom_cursor.to_list = AsyncMock(return_value=[bom_item])
        mock_db.style_component_mapping.find = MagicMock(return_value=bom_cursor)

        async def mock_find_one(query, *args, **kwargs):
            if "platform" in query:
                return cfg_doc
            if "_id" in query and isinstance(query["_id"], ObjectId):
                if query["_id"] == style_doc["_id"]:
                    return style_doc
                if query["_id"] == comp_id:
                    return comp_doc
            if query.get("component_code") == "SOL-001":
                return comp_doc
            if query.get("external_sku_key") == "sku-ssk-001":
                return sku_mapping
            return None

        mock_db.order_import_format_configs.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.sku_map.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.styles.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.component_master.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.production_jobs.insert_many = AsyncMock()

        file_obj = UploadFile(filename="orders.csv", file=io.BytesIO(CSV_TEST_ORDER))
        with patch("routes.online_orders._get_user", AsyncMock(return_value=mock_user)), \
             patch("routes.online_orders.get_db", return_value=mock_db):
            res = await import_configured_online_orders(
                file=file_obj, platform="generic", dry_run=False, request=MagicMock()
            )

        assert res["committed"]["picklists_created"] == 0
        assert res["committed"]["jobs_created"] == 1
        assert res["committed"]["pairs_to_manufacture"] == 10

        # Check job routed to 'procurement' due to insufficient components
        inserted_jobs = mock_db.production_jobs.insert_many.call_args[0][0]
        job = inserted_jobs[0]
        assert job["quantity"] == 10
        assert job["stage"] == "procurement"
        assert job["components_available"] is False
        assert job["has_bom"] is True
        assert len(job["component_shortages"]) == 1
        shortage = job["component_shortages"][0]
        assert shortage["component_code"] == "SOL-001"
        assert shortage["required"] == 10
        assert shortage["available"] == 2
        assert shortage["shortage"] == 8

    asyncio.run(run())
