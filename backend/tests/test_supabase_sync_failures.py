"""Tests for Supabase Sync Failures Tracking."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from services.supabase_sync_failure_service import (
    build_sync_failure_doc,
    record_supabase_sync_failure,
    get_supabase_sync_failures,
)


@pytest.mark.anyio
async def test_build_sync_failure_doc():
    doc = build_sync_failure_doc(
        collection="invoices",
        doc_id="inv_123",
        error="Connection refused on port 54321",
    )
    assert doc["collection"] == "invoices"
    assert doc["doc_id"] == "inv_123"
    assert "Connection refused" in doc["error"]
    assert "timestamp" in doc
    assert "id" in doc


@pytest.mark.anyio
async def test_record_supabase_sync_failure():
    mock_db = MagicMock()
    mock_db.supabase_sync_failures = MagicMock()
    mock_db.supabase_sync_failures.insert_one = AsyncMock(return_value=MagicMock(inserted_id="f_1"))

    res = await record_supabase_sync_failure(
        db=mock_db,
        collection="payments",
        doc_id="pay_999",
        error="PostgREST 500 internal error",
    )
    assert res is not None
    assert res["collection"] == "payments"
    assert res["doc_id"] == "pay_999"
    assert mock_db.supabase_sync_failures.insert_one.called
    inserted = mock_db.supabase_sync_failures.insert_one.call_args[0][0]
    assert inserted["doc_id"] == "pay_999"
    assert inserted["error"] == "PostgREST 500 internal error"


@pytest.mark.anyio
async def test_get_supabase_sync_failures():
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "oid1",
                "id": "uuid1",
                "collection": "vendor_purchase_orders",
                "doc_id": "vpo_55",
                "error": "Timeout",
                "timestamp": "2026-09-23T10:00:00Z",
            }
        ]
    )

    mock_db = MagicMock()
    mock_db.supabase_sync_failures = MagicMock()
    mock_db.supabase_sync_failures.find.return_value = mock_cursor

    failures = await get_supabase_sync_failures(mock_db, collection="vendor_purchase_orders")
    assert len(failures) == 1
    assert failures[0]["collection"] == "vendor_purchase_orders"
    assert failures[0]["doc_id"] == "vpo_55"
    assert "_id" not in failures[0]
