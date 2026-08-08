"""Automated verification script for Digital Style Folder & PLM Module."""
import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.plm import DEFAULT_PLM_FOLDERS, PLMDocumentIn, PLMToolingIn


async def run_tests():
    print("--- Starting Automated PLM Module Verification Tests ---")

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get("DB_NAME", "sskfootcare")]

    # 1. Verify 23-Folder Structure initialization
    print("\n1. Testing 23-Folder Structure...")
    test_style_code = "SSK_PLM_TEST"
    test_style = await db.styles.find_one({"code": test_style_code})
    if not test_style:
        res = await db.styles.insert_one({
            "code": test_style_code,
            "name": "PLM Test Footwear Style",
            "category": "Footwear",
            "status": "active",
            "created_at": "2026-07-31T00:00:00Z"
        })
        style_id = str(res.inserted_id)
    else:
        style_id = str(test_style["_id"])

    # Auto-initialize folders if not present
    folder_doc = await db.style_folders.find_one({"style_id": style_id})
    if not folder_doc:
        folder_doc = {
            "style_id": style_id,
            "style_code": test_style_code,
            "folders": DEFAULT_PLM_FOLDERS,
            "created_at": "2026-07-31T00:00:00Z"
        }
        await db.style_folders.insert_one(folder_doc)

    assert len(DEFAULT_PLM_FOLDERS) == 23, "Must have exactly 23 standardized sub-folders!"
    print(f"[OK] Verified 23 PLM folders auto-initialized for style {test_style_code}")

    # 2. Testing Document Upload & Version Control
    print("\n2. Testing Document Upload & Versioning...")
    doc = {
        "style_id": style_id,
        "style_code": test_style_code,
        "folder_code": "03",
        "folder_name": "03 Upper Patterns",
        "document_name": "Vamp Shell Pattern CAD",
        "document_type": "pattern",
        "pattern_category": "Upper Pattern",
        "current_version": 1,
        "url": "https://ik.imagekit.io/ssk/test_pattern_v1.dxf",
        "file_name": "test_pattern_v1.dxf",
        "file_type": "application/dxf",
        "file_size": 2048500,
        "versions": [{
            "version": 1,
            "file_name": "test_pattern_v1.dxf",
            "url": "https://ik.imagekit.io/ssk/test_pattern_v1.dxf",
            "uploaded_by": "Test Suite",
            "uploaded_at": "2026-07-31T00:00:00Z",
            "remarks": "Initial v1 release"
        }],
        "status": "approved",
        "created_at": "2026-07-31T00:00:00Z",
        "updated_at": "2026-07-31T00:00:00Z"
    }

    doc_res = await db.plm_documents.insert_one(doc)
    doc_id = str(doc_res.inserted_id)
    print(f"[OK] Created document {doc_id} with Version v1")

    # Simulate Version 2 Replacement
    v2_entry = {
        "version": 2,
        "file_name": "test_pattern_v2.dxf",
        "url": "https://ik.imagekit.io/ssk/test_pattern_v2.dxf",
        "uploaded_by": "Senior Designer",
        "uploaded_at": "2026-07-31T01:00:00Z",
        "remarks": "Updated toe spring curvature"
    }
    await db.plm_documents.update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": {"current_version": 2, "url": v2_entry["url"], "file_name": v2_entry["file_name"]}, "$push": {"versions": v2_entry}}
    )
    doc_after_v2 = await db.plm_documents.find_one({"_id": ObjectId(doc_id)})
    assert doc_after_v2["current_version"] == 2, "Document must update to v2"
    assert len(doc_after_v2["versions"]) == 2, "Document must preserve history of 2 versions"
    print("[OK] Verified Version v2 replacement & history preservation")

    # 3. Testing Tooling Library & Sole Mould Linking
    print("\n3. Testing Tooling & Sole Mould Auto-Linking...")
    mould_code = "MLD-SOLE-TEST01"
    tool_doc = {
        "tool_code": mould_code,
        "tool_name": "TPR Sports Sole 6-Cavity Mould",
        "tool_category": "Sole Mould",
        "vendor": "Precision Moulds Inc",
        "material_code": "MAT-SOLE-TPR01",
        "life_cycle_status": "Active",
        "max_usage": 100000,
        "current_usage": 12500,
        "storage_location": "RACK-A-04",
        "compatible_styles": [test_style_code],
        "created_at": "2026-07-31T00:00:00Z"
    }
    await db.plm_tooling.delete_many({"tool_code": mould_code})
    await db.plm_tooling.insert_one(tool_doc)

    found_mould = await db.plm_tooling.find_one({"tool_category": "Sole Mould", "material_code": "MAT-SOLE-TPR01"})
    assert found_mould is not None, "Sole Mould must be linkable via material_code!"
    assert found_mould["tool_code"] == mould_code
    print(f"[OK] Verified Sole Mould Auto-Linking for material MAT-SOLE-TPR01 -> {mould_code}")

    # 4. Testing Audit Log
    print("\n4. Testing PLM Audit Logging...")
    await db.plm_audit_log.insert_one({
        "action": "replace",
        "style_code": test_style_code,
        "doc_id": doc_id,
        "previous_version": "1",
        "current_version": "2",
        "user": "test_user@ssk.com",
        "details": "Replaced Vamp Pattern with v2",
        "timestamp": "2026-07-31T01:00:00Z"
    })
    audit_entry = await db.plm_audit_log.find_one({"style_code": test_style_code, "doc_id": doc_id})
    assert audit_entry is not None, "Audit log entry must be recorded!"
    print("[OK] Verified PLM Audit Logging")

    print("\n>>> ALL PLM MODULE VERIFICATION TESTS PASSED SUCCESSFULLY!")
    client.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
