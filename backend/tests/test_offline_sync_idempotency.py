import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from server import app


@pytest.fixture
def client_app():
    return TestClient(app)


def test_offline_sync_five_times_idempotency(client_app):
    """DB-007 Acceptance Criteria:
    Submitting the same offline batch five times produces exactly one business effect
    per operation and reports all repeats as already processed.
    """
    mock_db = MagicMock()
    mock_db.offline_operation_registry = MagicMock()
    mock_db.barcode_scan_logs = MagicMock()

    # Track in-memory store for registry
    stored_registry = {}
    scan_logs = []

    async def mock_find_one(query):
        key = (query.get("client_sync_id"), query.get("op_id"))
        return stored_registry.get(key)

    async def mock_insert_reg(doc):
        key = (doc.get("client_sync_id"), doc.get("op_id"))
        stored_registry[key] = doc
        return MagicMock(inserted_id="reg_123")

    async def mock_insert_scan(doc):
        scan_logs.append(doc)
        return MagicMock(inserted_id="scan_123")

    mock_db.offline_operation_registry.find_one = AsyncMock(side_effect=mock_find_one)
    mock_db.offline_operation_registry.insert_one = AsyncMock(side_effect=mock_insert_reg)
    mock_db.barcode_scan_logs.insert_one = AsyncMock(side_effect=mock_insert_scan)

    batch_payload = {
        "client_sync_id": "device_handheld_01_batch_999",
        "operations": [
            {
                "id": "op_barcode_scan_001",
                "type": "barcode_scan",
                "payload": {"barcode": "8901234567890", "location_code": "R01-S01-B01"},
                "timestamp": "2026-09-28T10:00:00Z",
            },
            {
                "id": "op_barcode_scan_002",
                "type": "barcode_scan",
                "payload": {"barcode": "8901234567891", "location_code": "R01-S01-B02"},
                "timestamp": "2026-09-28T10:00:01Z",
            }
        ]
    }

    headers = {"Authorization": "Bearer test-token"}

    with patch("server.db", mock_db), \
         patch("server._get_auth_user", AsyncMock(return_value={"email": "wh_scanner@ssk.com", "role": "wms_operator"})):

        responses = []
        for i in range(5):
            res = client_app.post("/api/sync/offline-batch", json=batch_payload, headers=headers)
            assert res.status_code == 200
            responses.append(res.json())

        # First run: both synced
        first = responses[0]
        assert first["synced"] == 2
        assert first["already_processed"] == 0
        assert first["results"][0]["status"] == "synced"
        assert first["results"][1]["status"] == "synced"

        # Subsequent 4 runs: 0 synced, 2 already_processed
        for rep_idx, rep in enumerate(responses[1:], start=2):
            assert rep["synced"] == 0, f"Run {rep_idx} should have 0 synced"
            assert rep["already_processed"] == 2, f"Run {rep_idx} should report 2 already_processed"
            assert rep["results"][0]["status"] == "already_processed"
            assert rep["results"][1]["status"] == "already_processed"

        # Exactly 2 scan logs written across all 5 runs
        assert len(scan_logs) == 2
