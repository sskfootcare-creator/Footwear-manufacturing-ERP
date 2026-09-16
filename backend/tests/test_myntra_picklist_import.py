import asyncio
import io
from bson import ObjectId
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import UploadFile

from routes.online_orders import import_configured_online_orders

MYNTRA_PICKLIST_CSV = b"""binBarcode,myntraSkuCode,sellerSkuCode,productDescription,quantity,expiryDates
N/A,DSBYFlats123467666,CC-058-BR-38,DressBerry Women Open Toe Flats with Buckles,2,N/A
N/A,ANUKFlats103652039,2412-FAKC-006-TN-39,Anouk Women Embellished Fashion Flats,1,N/A
N/A,CRCAFlats120195804,CCE-047-TN-38,CORSICA Women Open Toe Flats with Buckles,1,N/A"""

def test_myntra_picklist_import_all_mapped_scenarios():
    async def run():
        mock_db = MagicMock()
        mock_user = {"email": "admin@example.com", "role": "admin"}

        cfg_doc = {
            "platform": "myntra",
            "role": "order",
            "sheet_locator": {"type": "first_sheet"},
            "header_locator": {"type": "fixed_row", "row": 0},
            "skip_rows_after_header": 0,
            "column_map": {
                "order_id": None,
                "myntra_sku_code": "myntraSkuCode",
                "leaf_sku": "sellerSkuCode",
                "product_title": "productDescription",
                "qty": "quantity",
                "bin_barcode": "binBarcode",
            },
            "known_sku_prefixes_to_strip": [],
            "known_sku_prefix_replacements": {},
            "is_picklist": True,
            "active": True,
        }

        style_doc = {
            "_id": ObjectId(),
            "code": "SSK_00034",
            "name": "Flat Sandal",
        }

        mappings = {
            "cc-058-br": {
                "_id": ObjectId(),
                "style_id": str(style_doc["_id"]),
                "style_code": "SSK_00034",
                "source_type": "online_channel",
                "source_name": "myntra",
                "source_name_key": "myntra",
                "external_sku": "CC-058-BR",
                "external_sku_key": "cc-058-br",
                "color": "Brown",
                "color_map": {"BR": "Brown"},
                "size_map": {"38": "38"},
            },
            "2412-fakc-006-tn-39": {
                "_id": ObjectId(),
                "style_id": str(style_doc["_id"]),
                "style_code": "SSK_00034",
                "source_type": "online_channel",
                "source_name": "myntra",
                "source_name_key": "myntra",
                "external_sku": "2412-FAKC-006-TN-39",
                "external_sku_key": "2412-fakc-006-tn-39",
                "color": "Tan",
                "color_map": {"TN": "Tan"},
                "size_map": {"39": "39"},
            },
            "crcaflats120195804": {
                "_id": ObjectId(),
                "style_id": str(style_doc["_id"]),
                "style_code": "SSK_00034",
                "source_type": "online_channel",
                "source_name": "myntra",
                "source_name_key": "myntra",
                "external_sku": "CRCAFlats120195804",
                "external_sku_key": "crcaflats120195804",
                "color": "Tan",
                "color_map": {},
                "size_map": {"38": "38"},
            }
        }

        async def mock_find_one(query, *args, **kwargs):
            if "platform" in query:
                return cfg_doc
            if "_id" in query and isinstance(query["_id"], ObjectId):
                return style_doc
            ext_key = query.get("external_sku_key")
            if ext_key in mappings:
                return mappings[ext_key]
            return None

        mock_db.order_import_format_configs.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.sku_map.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.styles.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.production_jobs.insert_many = AsyncMock()
        mock_db.online_order_exceptions.insert_many = AsyncMock()

        class FakeRequest:
            app = type("App", (), {"mongodb": mock_db})()
            headers = {}

        with patch("routes.online_orders.get_db", return_value=mock_db), \
             patch("routes.online_orders._get_user", AsyncMock(return_value=mock_user)), \
             patch("routes.sku_map.ObjectId", ObjectId):

            file_obj = UploadFile(filename="OP20625445.csv", file=io.BytesIO(MYNTRA_PICKLIST_CSV))
            res_preview = await import_configured_online_orders(
                file=file_obj,
                platform="myntra",
                dry_run=True,
                request=FakeRequest()
            )

            assert res_preview["stats"]["total_rows_read"] == 3
            assert res_preview["stats"]["matched"] == 3
            assert res_preview["stats"]["unmatched"] == 0
            assert len(res_preview["matched"]) == 3

            # Row 1 matched via group_id CC-058-BR
            r1 = res_preview["matched"][0]
            assert r1["style_code"] == "SSK_00034"
            assert r1["color"] == "Brown"
            assert r1["size"] == "38"
            assert r1["quantity"] == 2

            # Row 2 matched via exact leaf SKU 2412-FAKC-006-TN-39
            r2 = res_preview["matched"][1]
            assert r2["style_code"] == "SSK_00034"
            assert r2["color"] == "Tan"
            assert r2["size"] == "39"
            assert r2["quantity"] == 1

            # Row 3 matched via secondary SKU CRCAFlats120195804
            r3 = res_preview["matched"][2]
            assert r3["style_code"] == "SSK_00034"
            assert r3["color"] == "Tan"
            assert r3["size"] == "38"
            assert r3["quantity"] == 1

            # Now test commit mode (dry_run=False)
            file_commit = UploadFile(filename="OP20625445.csv", file=io.BytesIO(MYNTRA_PICKLIST_CSV))
            res_commit = await import_configured_online_orders(
                file=file_commit,
                platform="myntra",
                dry_run=False,
                request=FakeRequest()
            )

            assert res_commit["committed"]["jobs_created"] == 3
            assert res_commit["committed"]["exceptions_queued"] == 0
            mock_db.production_jobs.insert_many.assert_called_once()

    asyncio.run(run())
