from unittest.mock import AsyncMock, MagicMock
from server import _ensure_startup_indexes


class AsyncIter:
    def __init__(self, items):
        self.items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


def test_ensure_startup_indexes_heals_sku_map():
    """Verify that _ensure_startup_indexes heals legacy sku_map documents and creates index."""
    import asyncio

    async def _run():
        mock_db = MagicMock()
        
        # Configure all other collections to avoid AttributeError
        mock_coll = MagicMock()
        mock_coll.create_index = AsyncMock(return_value="index_name")
        mock_coll.drop_index = AsyncMock(return_value=None)
        mock_coll.update_one = AsyncMock(return_value=None)
        mock_coll.delete_one = AsyncMock(return_value=None)
        mock_coll.delete_many = AsyncMock(return_value=None)
        
        for coll_name in [
            "users", "materials", "styles", "pos", "outbox_events", "production_jobs",
            "invoices", "dispatch_records", "expenses", "fg_inventory", "vendors",
            "workers", "notifications", "style_lifecycle", "password_resets",
            "component_master", "component_stock_movements", "style_component_mapping"
        ]:
            setattr(mock_db, coll_name, mock_coll)

        # Setup sku_map with legacy unindexed docs
        legacy_doc = {
            "_id": "doc1",
            "source_type": "b2b_client",
            "client_name": "Test Client",
            "external_sku": "SKU-100",
        }
        
        mock_sku_map = MagicMock()
        mock_sku_map.find.return_value = AsyncIter([legacy_doc])
        mock_sku_map.aggregate.return_value = AsyncIter([])
        mock_sku_map.update_one = AsyncMock(return_value=None)
        mock_sku_map.delete_many = AsyncMock(return_value=None)
        mock_sku_map.delete_one = AsyncMock(return_value=None)
        mock_sku_map.create_index = AsyncMock(return_value="sku_map_unique_normalized")
        mock_sku_map.drop_index = AsyncMock(return_value=None)
        
        mock_db.sku_map = mock_sku_map

        await _ensure_startup_indexes(mock_db)

        # Verify backfill occurred
        mock_sku_map.update_one.assert_called_once()
        call_args = mock_sku_map.update_one.call_args[0]
        assert call_args[0] == {"_id": "doc1"}
        assert call_args[1]["$set"]["source_name_key"] == "test client"
        assert call_args[1]["$set"]["external_sku_key"] == "sku-100"

        # Verify partialFilterExpression is passed to create_index
        create_index_calls = mock_sku_map.create_index.call_args_list
        compound_index_call = [c for c in create_index_calls if c.kwargs.get("name") == "sku_map_unique_normalized"]
        assert len(compound_index_call) == 1
        assert compound_index_call[0].kwargs.get("partialFilterExpression") == {
            "source_name_key": {"$type": "string"},
            "external_sku_key": {"$type": "string"},
        }

    asyncio.run(_run())
