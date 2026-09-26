import pytest
from fastapi.testclient import TestClient
from bson import ObjectId
from unittest.mock import MagicMock, patch, AsyncMock
import server
from server import app


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, limit=None):
        return self.docs


class MockCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, *args, **kwargs):
        return MockCursor(self.docs)

    async def find_one(self, q=None, *args, **kwargs):
        if not q:
            return self.docs[0] if self.docs else None
        for d in self.docs:
            match = True
            for k, v in q.items():
                if k == "_id" and str(d.get("_id")) != str(v):
                    match = False
                elif k != "_id" and d.get(k) != v:
                    match = False
            if match:
                return d
        return self.docs[0] if self.docs else None

    async def insert_one(self, doc, *args, **kwargs):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def update_one(self, q, u, *args, **kwargs):
        doc = await self.find_one(q)
        if doc and "$set" in u:
            doc.update(u["$set"])
        res = MagicMock()
        res.modified_count = 1
        return res

    async def update_many(self, q, u, *args, **kwargs):
        res = MagicMock()
        res.modified_count = 1
        return res


class MockDB:
    def __init__(self):
        self.jobs = MockCollection([{"_id": ObjectId(), "stage": "cutting", "order_qty": 100, "completed_qty": 20}])
        self.production_cards = MockCollection()
        self.fg_inventory = MockCollection([{"_id": ObjectId(), "style_code": "BOOT-01", "ready_stock_qty": 50, "unit_cost": 400.0, "updated_at": "2025-01-01T00:00:00Z"}])
        self.materials = MockCollection([{"_id": ObjectId(), "material_code": "LTH-01", "current_stock": 200, "unit_cost": 50.0}])
        self.invoices = MockCollection([{"_id": ObjectId(), "invoice_no": "SSK26-27-001", "grand_total": 50000.0, "paid_amount": 50000.0, "items": [{"style_code": "BOOT-01", "qty": 50}]}])
        self.dispatch_records = MockCollection([{"_id": ObjectId(), "items": [{"style_code": "BOOT-01", "qty": 50}]}])
        self.vendors = MockCollection([{"_id": ObjectId(), "name": "Apex Soles", "vendor_name": "Apex Soles"}])
        self.vendor_pos = MockCollection([{"_id": ObjectId(), "vendor_id": "Apex Soles", "status": "completed", "quantity": 100, "received_qty": 100, "defect_qty": 0, "total_amount": 25000.0}])
        self.purchase_orders = MockCollection()
        self.clients = MockCollection([{"_id": ObjectId(), "name": "Global Footwear", "client_name": "Global Footwear"}])
        self.styles = MockCollection([{"_id": ObjectId(), "code": "BOOT-01", "standard_cost": 380.0}])
        self.warehouse_locations = MockCollection([{"_id": ObjectId(), "location_code": "R01-RK1-C01", "row": 1, "rack": 1, "cell": 1, "capacity_pairs": 40, "occupied_pairs": 20, "zone": "main"}])
        self.picklists = MockCollection([{"_id": ObjectId(), "status": "completed", "picker": "John", "items": [{"qty": 10}]}])
        self.task_progress = MockCollection()
        self.quality_defect_reports = MockCollection()
        self.invoice_variances = MockCollection()
        self.entity_revisions = MockCollection()
        self.barcode_scan_logs = MockCollection()
        self.stock_audit_counts = MockCollection()
        self.offline_sync_events = MockCollection()
        self.audit_logs = MockCollection()

    def __getitem__(self, item):
        if not hasattr(self, item):
            setattr(self, item, MockCollection())
        return getattr(self, item)

    def __getattr__(self, item):
        col = MockCollection()
        setattr(self, item, col)
        return col



@pytest.fixture
def mock_env(monkeypatch):
    mock_db = MockDB()
    auth_user = {
        "id": "admin_user_id",
        "email": "admin@sskfootcare.com",
        "role": "admin",
        "roles": ["admin"],
        "modules": ["*"],
    }

    async def mock_get_user(request=None):
        return auth_user

    monkeypatch.setattr(server, "get_current_user", mock_get_user)
    monkeypatch.setattr(server, "_get_auth_user", mock_get_user)
    monkeypatch.setattr(server, "db", mock_db)
    monkeypatch.setattr("routes.reports._get_user", mock_get_user)
    monkeypatch.setattr("routes.reports._get_db", lambda r: mock_db)
    monkeypatch.setattr("routes.wms._get_user", mock_get_user)
    monkeypatch.setattr("routes.inventory._get_user", mock_get_user)
    monkeypatch.setattr("routes.invoice_packing._get_user", mock_get_user)
    monkeypatch.setattr("routes.invoice_packing._get_db", lambda r: mock_db)

    app.mongodb = mock_db
    client = TestClient(app)
    return client, mock_db


# ── A-001: Production Velocity & Stage Bottleneck Dashboard ───────────────────
def test_a001_production_velocity_report(mock_env):
    client, _ = mock_env
    res = client.get("/api/reports/production-velocity")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "summary" in data
    assert "stage_cycle_hours" in data
    assert "bottlenecks" in data
    assert isinstance(data["bottlenecks"], list)
    assert len(data["bottlenecks"]) > 0
    assert "load_index" in data["bottlenecks"][0]
    assert "severity" in data["bottlenecks"][0]


# ── A-002: Inventory Turnover & Dead Stock Detection ──────────────────────────
def test_a002_inventory_turnover_and_dead_stock(mock_env):
    client, _ = mock_env
    res_turn = client.get("/api/reports/inventory-turnover?days=365")
    assert res_turn.status_code == 200, res_turn.text
    data_turn = res_turn.json()
    assert "inventory_turnover_ratio" in data_turn
    assert "days_sales_of_inventory" in data_turn

    res_dead = client.get("/api/reports/dead-stock?idle_days_threshold=90")
    assert res_dead.status_code == 200, res_dead.text
    data_dead = res_dead.json()
    assert "total_dead_stock_count" in data_dead
    assert "total_locked_capital" in data_dead


# ── A-003: Supplier & Customer Scorecards ─────────────────────────────────────
def test_a003_supplier_and_customer_scorecards(mock_env):
    client, _ = mock_env
    res_sup = client.get("/api/reports/supplier-scorecards")
    assert res_sup.status_code == 200, res_sup.text
    data_sup = res_sup.json()
    assert "suppliers" in data_sup
    assert len(data_sup["suppliers"]) >= 1

    res_cust = client.get("/api/reports/customer-scorecards")
    assert res_cust.status_code == 200, res_cust.text
    data_cust = res_cust.json()
    assert "clients" in data_cust


# ── A-004: Cost Variance Report (Estimated vs Actual) ─────────────────────────
def test_a004_cost_variance_report(mock_env):
    client, _ = mock_env
    res = client.get("/api/reports/cost-variance")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "summary" in data
    assert "net_variance_amount" in data["summary"]
    assert "jobs" in data


# ── A-005: Warehouse Cell Heatmap & Picker Efficiency ─────────────────────────
def test_a005_warehouse_analytics(mock_env):
    client, _ = mock_env
    res_heat = client.get("/api/wms/analytics/utilization-heatmap")
    assert res_heat.status_code == 200, res_heat.text
    data_heat = res_heat.json()
    assert "summary" in data_heat
    assert "overall_utilization_pct" in data_heat["summary"]
    assert "heatmap" in data_heat

    res_pick = client.get("/api/wms/analytics/picker-efficiency")
    assert res_pick.status_code == 200, res_pick.text
    data_pick = res_pick.json()
    assert "pickers" in data_pick


# ── A-006: Demand Forecasting & Safety Stock ──────────────────────────────────
def test_a006_demand_forecasting_and_safety_stock(mock_env):
    client, _ = mock_env
    res_fore = client.get("/api/reports/demand-forecasting?horizon_months=3")
    assert res_fore.status_code == 200, res_fore.text
    data_fore = res_fore.json()
    assert "forecasts" in data_fore

    res_safe = client.get("/api/reports/safety-stock?service_level_z=1.65")
    assert res_safe.status_code == 200, res_safe.text
    data_safe = res_safe.json()
    assert "service_level" in data_safe
    assert "recommendations" in data_safe


# ── U-004: Task Progress & Real-Time ETA ──────────────────────────────────────
def test_u004_task_progress_tracking(mock_env):
    client, _ = mock_env
    up_res = client.post("/api/tasks/task_abc_01/progress", json={
        "total": 100,
        "processed": 50,
        "elapsed_seconds": 10.0,
        "current_item": "SKU-990",
    })
    assert up_res.status_code == 200, up_res.text
    up_data = up_res.json()
    assert up_data["percent"] == 50.0
    assert up_data["eta_seconds"] > 0

    get_res = client.get("/api/tasks/task_abc_01/progress")
    assert get_res.status_code == 200, get_res.text
    get_data = get_res.json()
    assert get_data["task_id"] == "task_abc_01"
    assert get_data["percent"] == 50.0


# ── U-005: Defect Reporting with Photo Evidence ───────────────────────────────
def test_u005_defect_reporting_with_photo(mock_env):
    client, _ = mock_env
    payload = {
        "style_id": str(ObjectId()),
        "color": "Tan",
        "size": "8",
        "quantity": 3,
        "defect_reason": "Adhesive bond failure along welt line",
        "defect_category": "sole_separation",
        "photo_urls": ["https://assets.sskfootcare.com/defects/photo_01.jpg"],
        "notes": "Spotted during final inspection",
    }
    with patch("routes.inventory._apply_movement", new_callable=AsyncMock) as mock_mv:
        mock_mv.return_value = {"ok": True, "style_code": "OXFORD-01"}
        res = client.post("/api/inventory/defect-report", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["ok"] is True
        assert "report_id" in data
        assert len(data["report"]["photo_urls"]) == 1

    list_res = client.get("/api/inventory/defect-reports")
    assert list_res.status_code == 200, list_res.text
    assert "reports" in list_res.json()


# ── U-006: Invoice Variance Explanation & Approval ────────────────────────────
def test_u006_invoice_variance_workflow(mock_env):
    client, mock_db = mock_env
    inv_id = str(ObjectId())
    mock_db.invoices.docs.append({
        "_id": ObjectId(inv_id),
        "invoice_no": "SSK26-27-055",
        "grand_total": 60000.0,
        "status": "pending",
    })

    sub_res = client.post(f"/api/invoices/{inv_id}/variance", json={
        "variance_reason": "Additional palletization packing charge",
        "variance_category": "off_standard_freight",
        "variance_amount": 2500.0,
        "notes": "Client requested waterproof stretch wrap",
    })
    assert sub_res.status_code == 200, sub_res.text
    sub_data = sub_res.json()
    assert sub_data["ok"] is True
    assert sub_data["variance"]["status"] == "pending_approval"

    get_res = client.get(f"/api/invoices/{inv_id}/variance")
    assert get_res.status_code == 200, get_res.text
    assert len(get_res.json()["variances"]) >= 1

    app_res = client.post(f"/api/invoices/{inv_id}/variance/approve", json={
        "approved": True,
        "approval_notes": "Charge approved per contract clause 4.2",
    })
    assert app_res.status_code == 200, app_res.text
    assert app_res.json()["variance_status"] == "approved"


# ── U-008: Revision History & Revert Controls ─────────────────────────────────
def test_u008_revision_history_and_revert(mock_env):
    client, mock_db = mock_env
    ent_id = str(ObjectId())
    rev_id = str(ObjectId())
    mock_db.entity_revisions.docs.append({
        "_id": ObjectId(rev_id),
        "entity_type": "invoice",
        "entity_id": ent_id,
        "snapshot": {"invoice_no": "SSK26-27-088", "grand_total": 45000.0, "status": "draft"},
        "reason": "Baseline draft invoice",
        "created_by": "finance@ssk.com",
        "created_at": "2026-09-01T00:00:00Z",
    })
    mock_db.invoices.docs.append({
        "_id": ObjectId(ent_id),
        "invoice_no": "SSK26-27-088",
        "grand_total": 52000.0,
        "status": "modified",
    })

    get_res = client.get(f"/api/revisions/invoice/{ent_id}")
    assert get_res.status_code == 200, get_res.text
    assert len(get_res.json()["revisions"]) >= 1

    rev_post = client.post(f"/api/revisions/invoice/{ent_id}/revert", json={
        "revision_id": rev_id,
    })
    assert rev_post.status_code == 200, rev_post.text
    assert rev_post.json()["ok"] is True


# ── U-010: Offline Mode & Batch Sync-on-Reconnect ─────────────────────────────
def test_u010_offline_batch_sync(mock_env):
    client, _ = mock_env
    batch_payload = {
        "client_sync_id": "tablet_floor_scan_04",
        "operations": [
            {
                "id": "op_01",
                "type": "barcode_scan",
                "payload": {"barcode": "8901234567890", "location_code": "R01-RK1-C01"},
            },
            {
                "id": "op_02",
                "type": "stock_count",
                "payload": {"location_code": "R01-RK1-C01", "counted_pairs": 20},
            },
        ]
    }
    res = client.post("/api/sync/offline-batch", json=batch_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_operations"] == 2
    assert data["synced"] == 2
    assert data["failed"] == 0
