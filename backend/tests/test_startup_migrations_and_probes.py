import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from server import app
from db.migrations.runner import run_mongo_migrations, acquire_migration_lock, release_migration_lock


@pytest.fixture
def client_app():
    return TestClient(app)


def test_healthz_liveness_probe(client_app):
    """OPS-023 / DB-004: Liveness probe verification."""
    res = client_app.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_readyz_readiness_probe_success(client_app):
    """OPS-023 / DB-004: Readiness probe returns ready when MongoDB is connected."""
    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": 1})

    with patch("server.db", mock_db), \
         patch("db.supabase_client.get_supabase_admin_client", return_value=None):
        res = client_app.get("/readyz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["checks"]["mongodb"] == "connected"


def test_readyz_readiness_probe_failure(client_app):
    """OPS-023 / DB-004: Readiness probe returns 503 when MongoDB is unavailable."""
    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("server.db", mock_db), \
         patch("db.supabase_client.get_supabase_admin_client", return_value=None):
        res = client_app.get("/readyz")
        assert res.status_code == 503
        data = res.json()
        assert data["detail"]["status"] == "not_ready"


def test_mongo_migration_runner_idempotency_and_locking():
    """DB-002 Acceptance Criteria:
    Repeatable forward-only migrations without application startup performing destructive work.
    """
    import asyncio

    async def _run_test():
        mock_db = MagicMock()
        mock_db.schema_migrations = MagicMock()
        mock_db.migration_locks = MagicMock()

        applied_versions = set()

        def mock_find(query):
            class AsyncCursor:
                async def to_list(self, limit):
                    return [{"version": v} for v in applied_versions]
            return AsyncCursor()

        async def mock_update_one(filter_dict, update_dict, upsert=False):
            ver = filter_dict.get("version")
            if ver:
                applied_versions.add(ver)
            return MagicMock(modified_count=1)

        mock_db.schema_migrations.create_index = AsyncMock()
        mock_db.schema_migrations.find = mock_find
        mock_db.schema_migrations.update_one = AsyncMock(side_effect=mock_update_one)

        mock_registry = [
            ("001", "core_indexes", AsyncMock()),
            ("002", "wms_locations", AsyncMock()),
            ("003", "marketplace_configs", AsyncMock()),
            ("004", "offline_and_recon_indexes", AsyncMock()),
            ("005", "legacy_url_rewrites", AsyncMock()),
        ]

        # First run acquires lock and applies all migrations
        with patch("db.migrations.runner.acquire_migration_lock", AsyncMock(return_value=True)), \
             patch("db.migrations.runner.release_migration_lock", AsyncMock()), \
             patch("db.migrations.runner.MIGRATIONS_REGISTRY", mock_registry):

            res1 = await run_mongo_migrations(mock_db)
            assert res1["status"] == "success"
            assert res1["applied_count"] == 5

            # Second run: schema is up to date, 0 pending, 0 re-applied
            res2 = await run_mongo_migrations(mock_db)
            assert res2["status"] == "up_to_date"
            assert res2["applied_count"] == 0

    asyncio.run(_run_test())
