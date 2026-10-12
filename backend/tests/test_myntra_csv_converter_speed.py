import asyncio
import io
import time
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile

from routes.wms import preview_myntra_picklist, process_myntra_picklist


CSV_CONTENT = b"""binBarcode,myntraSkuCode,sellerSkuCode,productDescription,quantity,expiryDates
N/A,DSBYFlats123467666,CC-058-BR-38,DressBerry Women Open Toe Flats with Buckles,2,N/A
N/A,DSBYFlats123467666,CC-058-BR-38,DressBerry Women Open Toe Flats with Buckles,1,N/A
N/A,ANUKFlats103652039,2412-FAKC-006-TN-39,Anouk Women Embellished Fashion Flats,1,N/A
N/A,ANUKFlats103652039,2412-FAKC-006-TN-39,Anouk Women Embellished Fashion Flats,3,N/A
N/A,CRCAFlats120195804,CCE-047-TN-38,CORSICA Women Open Toe Flats with Buckles,1,N/A
"""


def test_myntra_picklist_preview_and_process_speed():
    async def run():
        mock_db = MagicMock()
        style_doc = {
            "_id": ObjectId("6a990d24e35335076c235327"),
            "code": "SSK_00034",
            "name": "Flat Sandal",
            "image_url": "/company/laser_cut_flat.jpg",
        }
        mapping_doc = {
            "_id": ObjectId("6a99129ae35335076c23534e"),
            "style_id": str(style_doc["_id"]),
            "style_code": "SSK_00034",
            "source_type": "online_channel",
            "source_name": "myntra",
            "source_name_key": "myntra",
            "external_sku": "CC-058-BR",
            "external_sku_key": "cc-058-br",
            "color": "Brown",
            "size_map": {"38": "38", "39": "39"},
        }

        async def mock_find_one(query, *args, **kwargs):
            if "platform" in query:
                return {"known_sku_prefixes_to_strip": [], "known_sku_prefix_replacements": {}}
            if "_id" in query and query["_id"] == "myntra_sealtag":
                return {"_id": "myntra_sealtag", "seq": 259240000}
            if "_id" in query and query["_id"] == "myntra_bagid":
                return {"_id": "myntra_bagid", "seq": 883599}
            if "_id" in query and isinstance(query["_id"], ObjectId):
                return style_doc
            ext_key = query.get("external_sku_key")
            if ext_key in ("cc-058-br", "2412-fakc-006-tn-39", "cce-047-tn-38"):
                return mapping_doc
            return None

        mock_db.order_import_format_configs.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.sku_map.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.styles.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.online_style_photos.find_one = AsyncMock(return_value=None)
        mock_db.counters.find_one = AsyncMock(side_effect=mock_find_one)
        mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 259240010})

        mock_request = MagicMock()
        mock_request.app.mongodb = mock_db

        # Test 1: Preview caching
        file_preview = UploadFile(filename="test_picklist.csv", file=io.BytesIO(CSV_CONTENT))
        t0 = time.perf_counter()
        preview_res = await preview_myntra_picklist(mock_request, file_preview)
        t_preview = time.perf_counter() - t0

        assert preview_res["stats"]["total"] == 5
        assert preview_res["stats"]["matched"] == 5
        assert len(preview_res["rows"]) == 5
        # Verify resolution
        for r in preview_res["rows"]:
            assert r["mapped"] is True
            assert r["erp_style_name"] == "Flat Sandal"

        # Test 2: Process using preview_rows (instant pass-through)
        import json
        preview_json = json.dumps(preview_res["rows"])
        file_process = UploadFile(filename="test_picklist.csv", file=io.BytesIO(CSV_CONTENT))

        t0 = time.perf_counter()
        resp = await process_myntra_picklist(mock_request, file_process, preview_rows=preview_json)
        t_process = time.perf_counter() - t0

        assert resp.status_code == 200
        # Check output content
        chunks = [chunk async for chunk in resp.body_iterator]
        output_csv = (b"".join(chunks)).decode("utf-8")
        assert "SkuName" in output_csv
        assert "Flat Sandal" in output_csv
        assert "SealTag" in output_csv
        assert "BagId" in output_csv

    asyncio.run(run())
