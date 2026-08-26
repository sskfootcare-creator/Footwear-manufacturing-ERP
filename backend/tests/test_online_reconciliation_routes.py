"""Unit and integration tests for Online Reconciliation and Profitability Routes."""

import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId
import openpyxl

import server
from routes.online_reconciliation import (
    online_reconciliation_router,
    _compute_online_profitability,
)


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, count):
        return self

    async def to_list(self, limit=10000):
        return self.docs[:limit]


class MockOnlineReconciliationDB:
    def __init__(self):
        self.daily_payments_store = []
        self.settlements_store = []
        self.non_order_deductions_store = []
        self.monthly_reports_store = []
        self.cost_snapshots_store = {}
        self.profitability_daily_store = {}
        self.order_items_store = []
        self.styles_store = {}
        self.sku_maps_store = []
        self.marketplace_mappings_store = []
        self.audit_logs_store = []

        self.online_daily_payments = MagicMock()
        self.online_daily_payments.find = MagicMock(return_value=MockCursor(self.daily_payments_store))
        self.online_daily_payments.insert_many = AsyncMock(side_effect=self._insert_many_daily_payments)
        self.online_daily_payments.delete_many = AsyncMock(side_effect=self._clear_daily_payments)

        self.online_settlements_detailed = MagicMock()
        self.online_settlements_detailed.find = MagicMock(return_value=MockCursor(self.settlements_store))
        self.online_settlements_detailed.insert_one = AsyncMock(side_effect=self._insert_settlement)
        self.online_settlements_detailed.delete_many = AsyncMock(side_effect=self._clear_settlements)

        self.online_non_order_deductions = MagicMock()
        self.online_non_order_deductions.find = MagicMock(return_value=MockCursor(self.non_order_deductions_store))
        self.online_non_order_deductions.insert_one = AsyncMock(side_effect=self._insert_non_order_deduction)
        self.online_non_order_deductions.delete_many = AsyncMock(side_effect=self._clear_non_order_deductions)

        self.online_monthly_order_reports = MagicMock()
        self.online_monthly_order_reports.find = MagicMock(return_value=MockCursor(self.monthly_reports_store))
        self.online_monthly_order_reports.insert_many = AsyncMock(side_effect=self._insert_many_monthly_reports)
        self.online_monthly_order_reports.delete_many = AsyncMock(side_effect=self._clear_monthly_reports)

        self.style_cost_snapshots = MagicMock()
        self.style_cost_snapshots.find = MagicMock(side_effect=self._find_cost_snapshots)
        self.style_cost_snapshots.insert_one = AsyncMock(side_effect=self._insert_cost_snapshot)
        self.style_cost_snapshots.delete_many = AsyncMock(side_effect=self._clear_cost_snapshots)

        self.online_profitability_daily = MagicMock()
        self.online_profitability_daily.find = MagicMock(side_effect=self._find_profitability_daily)
        self.online_profitability_daily.update_one = AsyncMock(side_effect=self._update_profitability_daily)

        self.online_order_items = MagicMock()
        self.online_order_items.aggregate = MagicMock(side_effect=self._aggregate_order_items)

        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=self._find_styles)
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        self.sku_map = MagicMock()
        self.sku_map.find = MagicMock(return_value=MockCursor(self.sku_maps_store))

        self.marketplace_style_color_mapping = MagicMock()
        self.marketplace_style_color_mapping.find = MagicMock(return_value=MockCursor(self.marketplace_mappings_store))

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    async def list_collection_names(self):
        return [
            "online_daily_payments",
            "online_settlements_detailed",
            "online_non_order_deductions",
            "online_monthly_order_reports",
            "style_cost_snapshots",
            "online_profitability_daily",
            "online_order_items",
            "styles",
        ]

    async def _insert_many_daily_payments(self, docs):
        self.daily_payments_store.extend(docs)
        self.online_daily_payments.find = MagicMock(return_value=MockCursor(self.daily_payments_store))
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])

    async def _clear_daily_payments(self, q=None):
        self.daily_payments_store.clear()
        self.online_daily_payments.find = MagicMock(return_value=MockCursor(self.daily_payments_store))
        return MagicMock(deleted_count=1)

    async def _insert_settlement(self, doc):
        self.settlements_store.append(doc)
        self.online_settlements_detailed.find = MagicMock(return_value=MockCursor(self.settlements_store))
        return MagicMock(inserted_id=ObjectId())

    async def _clear_settlements(self, q=None):
        self.settlements_store.clear()
        self.online_settlements_detailed.find = MagicMock(return_value=MockCursor(self.settlements_store))
        return MagicMock(deleted_count=1)

    async def _insert_non_order_deduction(self, doc):
        self.non_order_deductions_store.append(doc)
        self.online_non_order_deductions.find = MagicMock(return_value=MockCursor(self.non_order_deductions_store))
        return MagicMock(inserted_id=ObjectId())

    async def _clear_non_order_deductions(self, q=None):
        self.non_order_deductions_store.clear()
        self.online_non_order_deductions.find = MagicMock(return_value=MockCursor(self.non_order_deductions_store))
        return MagicMock(deleted_count=1)

    async def _insert_many_monthly_reports(self, docs):
        self.monthly_reports_store.extend(docs)
        self.online_monthly_order_reports.find = MagicMock(return_value=MockCursor(self.monthly_reports_store))
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])

    async def _clear_monthly_reports(self, q=None):
        self.monthly_reports_store.clear()
        self.online_monthly_order_reports.find = MagicMock(return_value=MockCursor(self.monthly_reports_store))
        return MagicMock(deleted_count=1)

    def _find_cost_snapshots(self, q=None):
        docs = list(self.cost_snapshots_store.values())
        if q and "style_code" in q:
            docs = [d for d in docs if d.get("style_code") == q["style_code"]]
        return MockCursor(docs)

    async def _insert_cost_snapshot(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.cost_snapshots_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _clear_cost_snapshots(self, q=None):
        self.cost_snapshots_store.clear()
        return MagicMock(deleted_count=1)

    def _find_profitability_daily(self, q=None):
        return MockCursor(list(self.profitability_daily_store.values()))

    async def _update_profitability_daily(self, query, update, upsert=False):
        k = tuple(sorted((k, str(v)) for k, v in query.items()))
        if k in self.profitability_daily_store:
            self.profitability_daily_store[k].update(update.get("$set", {}))
        elif upsert:
            doc = {**query, **update.get("$set", {})}
            self.profitability_daily_store[k] = doc
        return MagicMock(matched_count=1)

    def _aggregate_order_items(self, pipeline):
        # Determine aggregate type based on pipeline
        if len(pipeline) >= 2 and "$match" in pipeline[0] and "$group" in pipeline[1]:
            match_clause = pipeline[0]["$match"]
            if match_clause.get("is_net_sold") is True:
                # Sold pipeline
                groups = {}
                for item in self.order_items_store:
                    if item.get("is_net_sold"):
                        sid = item.get("style_id")
                        if sid not in groups:
                            groups[sid] = {
                                "_id": sid,
                                "style_code": item.get("style_code"),
                                "color": item.get("color"),
                                "units_sold": 0,
                                "item_final_amount": 0.0,
                                "order_release_ids": set(),
                            }
                        groups[sid]["units_sold"] += item.get("qty", 1)
                        groups[sid]["item_final_amount"] += item.get("final_amount", 0.0)
                        if item.get("order_release_id"):
                            groups[sid]["order_release_ids"].add(item.get("order_release_id"))
                res = []
                for v in groups.values():
                    v["order_release_ids"] = list(v["order_release_ids"])
                    res.append(v)
                return MockCursor(res)

            elif match_clause.get("was_returned_to_stock") is True:
                # Returned pipeline
                groups = {}
                for item in self.order_items_store:
                    if item.get("was_returned_to_stock"):
                        sid = item.get("style_id")
                        groups[sid] = groups.get(sid, 0) + item.get("qty", 1)
                return MockCursor([{"_id": k, "returned_units": v} for k, v in groups.items()])

            elif match_clause.get("was_packed") is True:
                total = sum(item.get("qty", 1) for item in self.order_items_store if item.get("was_packed"))
                return MockCursor([{"_id": None, "n": total}])

        return MockCursor([])

    def _find_styles(self, q=None, projection=None):
        docs = list(self.styles_store.values())
        if q and "_id" in q and isinstance(q["_id"], dict) and "$in" in q["_id"]:
            in_ids = [str(x) for x in q["_id"]["$in"]]
            docs = [d for d in docs if str(d.get("_id")) in in_ids]
        return MockCursor(docs)

    async def _find_one_style(self, q):
        if "_id" in q:
            return self.styles_store.get(str(q["_id"]))
        if "code" in q:
            for s in self.styles_store.values():
                if s.get("code") == q["code"]:
                    return s
        return None


@pytest.fixture
def mock_recon_env(monkeypatch):
    mock_db = MockOnlineReconciliationDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    async def mock_compute_style_costing_async(style, db=None):
        return {
            "total_cost": 450.0,
            "materials_cost": 300.0,
            "labor_cost": 100.0,
            "labor_source": "actual",
            "cost_is_estimated": False,
            "is_assigned": True,
            "actual_labor_cost": 100.0,
            "planned_labor_cost": 90.0,
            "overhead_cost": 30.0,
            "packing_cost": 20.0,
        }

    monkeypatch.setattr(server, "compute_style_costing_async", mock_compute_style_costing_async)

    def mock_compute_style_costing(style):
        return {"total_cost": 450.0, "materials_cost": 300.0, "labor_cost": 100.0}

    monkeypatch.setattr(server, "compute_style_costing", mock_compute_style_costing)
    return mock_db


@pytest.fixture
def client(mock_recon_env):
    test_app = FastAPI()
    test_app.include_router(online_reconciliation_router)
    test_app.mongodb = mock_recon_env
    return TestClient(test_app)


def test_cost_snapshots_crud(client, mock_recon_env):
    # 1. Create cost snapshot
    res = client.post("/api/online-reconciliation/cost-snapshots", json={
        "style_code": "SSK-RUN-01",
        "effective_date": "2026-08-01",
        "total_cost": 480.0,
        "material_cost": 320.0,
        "labor_cost": 120.0,
        "notes": "Q3 Baseline Costing"
    })
    assert res.status_code == 200, res.text
    snap = res.json()
    assert snap["style_code"] == "SSK-RUN-01"
    assert snap["total_cost"] == 480.0

    # 2. List cost snapshots
    res = client.get("/api/online-reconciliation/cost-snapshots?style_code=SSK-RUN-01")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["total_cost"] == 480.0

    # 3. Clear test data
    res = client.post("/api/online-reconciliation/clear-test-data")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_import_and_reconciliation_flow(client, mock_recon_env):
    # 1. Import Daily Payments CSV
    daily_csv = (
        "neft_ref,settled_amount,commission,shipping_fee,tds,payment_type,order_type,order_release_id,seller_order_id,payment_date\n"
        "NEFT12345,1500.0,150.0,100.0,15.0,prepaid,Forward,REL_001,ORD_001,2026-08-10\n"
    )
    res = client.post(
        "/api/online-reconciliation/import-daily-payments",
        files={"file": ("daily_payments.csv", io.BytesIO(daily_csv.encode("utf-8")), "text/csv")}
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1

    # 2. Import Settlements XLSX
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Forward_Settled"
    # Row 1 and 2 are title/dummy, Row 3 is header
    ws.append(["Title", ""])
    ws.append(["Subtitle", ""])
    ws.append(["seller_order_id", "order_release_id", "settled_amount_prepaid", "commission_amount_incl_gst", "logistics_cost_forward_incl_tax", "seller_sku_code", "neft_ref"])
    ws.append(["ORD_001", "REL_001", 1500.0, 150.0, 100.0, "SSK-RUN-BLK-8", "NEFT12345"])
    buf = io.BytesIO()
    wb.save(buf)

    res = client.post(
        "/api/online-reconciliation/import-settlements",
        files={"file": ("settlements.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res.status_code == 200
    assert res.json()["settlements_count"] == 1

    # 3. Import Monthly Order Report CSV
    monthly_csv = (
        "seller_order_id,order_release_id,seller_sku_code,order_status,packed_on,final_amount\n"
        "ORD_001,REL_001,SSK-RUN-BLK-8,Delivered,2026-08-05,1800.0\n"
    )
    res = client.post(
        "/api/online-reconciliation/import-monthly-report",
        files={"file": ("monthly_report.csv", io.BytesIO(monthly_csv.encode("utf-8")), "text/csv")}
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1

    # 4. Run Online Reconciliation
    res = client.get("/api/online-reconciliation/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_monthly_report_units"] == 1
    assert summary["settled_count"] == 1
    assert summary["join_rate_pct"] == 100.0

    # 5. List unreconciled orders
    res = client.get("/api/online-reconciliation/unreconciled-orders")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_online_profitability_endpoints(client, mock_recon_env):
    # Seed a style in mock DB
    s_oid = ObjectId()
    mock_recon_env.styles_store[str(s_oid)] = {
        "_id": s_oid,
        "code": "SSK-RUN-01",
        "name": "Runner Shoe",
    }
    # Seed an order item
    mock_recon_env.order_items_store.append({
        "style_id": s_oid,
        "style_code": "SSK-RUN-01",
        "color": "Black",
        "qty": 2,
        "final_amount": 3600.0,
        "is_net_sold": True,
        "was_packed": True,
        "was_returned_to_stock": False,
        "packed_on": "2026-08-15",
    })

    # 1. Live Profitability GET
    res = client.get("/api/reports/online-profitability?platform=myntra")
    assert res.status_code == 200
    prof = res.json()
    assert prof["net_units_sold"] == 2
    assert prof["total_net_cogs"] == 900.0  # 450 * 2
    assert prof["gross_profit"] == 2700.0  # 3600 - 900

    # 2. Materialised Rebuild POST
    res = client.post("/api/reports/online-profitability/rebuild?date_from=2026-08-01&date_to=2026-08-31")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # 3. List Materialised Snapshots
    res = client.get("/api/reports/online-profitability-materialised")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 4. Trend GET
    res = client.get("/api/reports/online-profitability/trend?date_from=2026-08-01&date_to=2026-08-05&bucket=day")
    assert res.status_code == 200
    trend = res.json()
    assert "rows" in trend
    assert len(trend["rows"]) == 5

    # 5. Export GET (.xlsx)
    res = client.get("/api/reports/online-profitability/export")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(res.content) > 0
