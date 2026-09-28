import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from server import app


@pytest.fixture
def client_app():
    return TestClient(app)


def test_channel_allocation_explanation(client_app):
    """DB-009 Acceptance Criteria:
    The system can explain available, reserved, allocated, safety,
    and sellable quantities by channel and SKU.
    """
    mock_db = MagicMock()

    sample_fg_items = [
        {
            "_id": "64a000000000000000000001",
            "style_id": "64a000000000000000000010",
            "style_code": "SSK-DERBY-01",
            "color": "BLACK",
            "size": "8",
            "ready_for_dispatch": 50,
            "reserved": 10,
            "safety_stock": 5,
        }
    ]

    def mock_find(query):
        class AsyncCursor:
            async def to_list(self, limit):
                return sample_fg_items
        return AsyncCursor()

    mock_db.fg_inventory.find = mock_find

    headers = {"Authorization": "Bearer test-token"}

    with patch("routes.inventory._get_user", AsyncMock(return_value={"email": "alloc_mgr@ssk.com", "role": "manager"})), \
         patch.object(app, "mongodb", mock_db, create=True):

        # 1. Query for online channel
        res_online = client_app.get("/api/inventory/channel-allocation?channel=online", headers=headers)
        assert res_online.status_code == 200
        data_online = res_online.json()
        assert data_online["channel"] == "online"
        assert len(data_online["items"]) == 1
        item = data_online["items"][0]

        # Verify key quantities
        assert item["physical_on_hand"] == 60
        assert item["available"] == 50
        assert item["reserved"] == 10
        assert item["safety"] == 5
        # online sellable = ready (50) - safety (5) = 45
        assert item["sellable"] == 45
        assert item["channels"]["online"] == 45
        # b2b sellable = total physical (60) - reserved (10) = 50
        assert item["channels"]["b2b"] == 50
