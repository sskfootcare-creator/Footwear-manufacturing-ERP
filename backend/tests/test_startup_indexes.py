import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import server

@pytest.mark.anyio
async def test_startup_creates_all_target_indexes():
    """Verify that startup event creates all query optimization indexes cleanly without error."""
    mock_db = MagicMock()
    collections = [
        "users", "materials", "styles", "pos", "production_jobs", "vendors",
        "workers", "notifications", "sku_map", "style_lifecycle", "password_resets",
        "component_master", "component_stock_movements", "style_component_mapping",
        "fg_inventory", "fg_stock_movements", "inventory_reservations",
        "warehouse_locations", "fg_location_inventory", "picklists",
        "invoices", "dispatch_records"
    ]
    created_indexes = {c: [] for c in collections}

    for c in collections:
        col_mock = MagicMock()
        async def make_create_index(col_name):
            async def _create_index(keys, **kwargs):
                created_indexes[col_name].append((keys, kwargs))
                return f"{col_name}_idx_{len(created_indexes[col_name])}"
            return _create_index

        col_mock.create_index = AsyncMock(side_effect=await make_create_index(c))
        setattr(mock_db, c, col_mock)

    with patch.object(server, "db", mock_db), \
         patch("server.get_current_user_factory", AsyncMock(return_value=AsyncMock())), \
         patch("server.seed_admin", AsyncMock()):
        
        # Execute startup handler
        await server.on_startup()

    # Verify production_jobs indexes
    pj_indexes = [idx[0] for idx in created_indexes["production_jobs"]]
    assert "po_id" in pj_indexes
    assert "style_id" in pj_indexes
    assert "style_code" in pj_indexes
    assert "po_number" in pj_indexes

    # Verify invoices indexes
    inv_indexes = [idx[0] for idx in created_indexes["invoices"]]
    assert "po_id" in inv_indexes
    assert "po_ids" in inv_indexes
    assert "po_number" in inv_indexes
    assert "po_numbers" in inv_indexes

    # Verify dispatch_records indexes
    disp_indexes = [idx[0] for idx in created_indexes["dispatch_records"]]
    assert "po_id" in disp_indexes
    assert "po_ids" in disp_indexes
    assert "po_number" in disp_indexes
    assert "po_numbers" in disp_indexes
