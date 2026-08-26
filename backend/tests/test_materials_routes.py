"""Unit tests for Raw Materials, BOM items & Inventory Movement Routes."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.materials import (
    materials_router,
    _calculate_material_weighted_avg,
    _auto_consume_inventory,
    _get_material_balance,
)


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def skip(self, count):
        return self

    async def to_list(self, limit=10000):
        return self.docs[:limit]


class MockMaterialsDB:
    def __init__(self):
        self.materials_store = {}
        self.movements_store = {}
        self.component_master_store = {}
        self.styles_store = {}
        self.vendors_store = {}
        self.production_jobs_store = {}
        self.audit_logs_store = []

        self.materials = MagicMock()
        self.materials.find = MagicMock(side_effect=self._find_materials)
        self.materials.find_one = AsyncMock(side_effect=self._find_one_material)
        self.materials.insert_one = AsyncMock(side_effect=self._insert_material)
        self.materials.update_one = AsyncMock(side_effect=self._update_material)
        self.materials.delete_one = AsyncMock(side_effect=self._delete_material)

        self.inventory_movements = MagicMock()
        self.inventory_movements.find = MagicMock(side_effect=self._find_movements)
        self.inventory_movements.find_one = AsyncMock(side_effect=self._find_one_movement)
        self.inventory_movements.insert_one = AsyncMock(side_effect=self._insert_movement)
        self.inventory_movements.insert_many = AsyncMock(side_effect=self._insert_many_movements)
        self.inventory_movements.delete_one = AsyncMock(side_effect=self._delete_movement)

        self.component_master = MagicMock()
        self.component_master.find = MagicMock(side_effect=self._find_components)
        self.component_master.insert_one = AsyncMock(side_effect=self._insert_component)
        self.component_master.update_many = AsyncMock(side_effect=self._update_components)

        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=self._find_styles)
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        self.vendors = MagicMock()
        self.vendors.find = MagicMock(return_value=MockCursor(list(self.vendors_store.values())))

        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=self._find_jobs)
        self.production_jobs.update_one = AsyncMock(side_effect=self._update_job)

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    def _find_materials(self, q=None):
        docs = list(self.materials_store.values())
        if q and "code" in q and isinstance(q["code"], dict) and "$in" in q["code"]:
            codes = q["code"]["$in"]
            docs = [d for d in docs if d.get("code") in codes]
        return MockCursor(docs)

    async def _find_one_material(self, q):
        if "_id" in q:
            return self.materials_store.get(str(q["_id"]))
        if "code" in q:
            val = q["code"]
            if isinstance(val, dict) and "$regex" in val:
                for m in self.materials_store.values():
                    if m.get("code", "").lower() == val["$regex"].strip("^$").lower():
                        return m
            else:
                for m in self.materials_store.values():
                    if m.get("code") == val:
                        return m
        return None

    async def _insert_material(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.materials_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_material(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.materials_store:
            if "balance" in query and isinstance(query["balance"], dict) and "$gte" in query["balance"]:
                if self.materials_store[oid_str].get("balance", 0.0) < query["balance"]["$gte"]:
                    return MagicMock(matched_count=0)
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    self.materials_store[oid_str][k] = self.materials_store[oid_str].get(k, 0.0) + v
            if "$set" in update:
                self.materials_store[oid_str].update(update["$set"])
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def _delete_material(self, query):
        oid_str = str(query.get("_id"))
        self.materials_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_movements(self, q=None):
        docs = list(self.movements_store.values())
        if q and "material_id" in q:
            docs = [d for d in docs if d.get("material_id") == q["material_id"]]
        return MockCursor(docs)

    async def _find_one_movement(self, q):
        if "_id" in q:
            return self.movements_store.get(str(q["_id"]))
        return None

    async def _insert_movement(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.movements_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _insert_many_movements(self, docs):
        for doc in docs:
            oid = ObjectId()
            doc["_id"] = oid
            self.movements_store[str(oid)] = doc
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])

    async def _delete_movement(self, q):
        oid_str = str(q.get("_id"))
        self.movements_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_components(self, q=None):
        return MockCursor(list(self.component_master_store.values()))

    async def _insert_component(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.component_master_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_components(self, query, update):
        return MagicMock(matched_count=1)

    def _find_styles(self, q=None):
        return MockCursor(list(self.styles_store.values()))

    async def _find_one_style(self, q):
        if "_id" in q:
            return self.styles_store.get(str(q["_id"]))
        if "code" in q:
            for s in self.styles_store.values():
                if s.get("code") == q["code"]:
                    return s
        return None

    def _find_jobs(self, q=None):
        return MockCursor(list(self.production_jobs_store.values()))

    async def _update_job(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.production_jobs_store:
            if "$set" in update:
                self.production_jobs_store[oid_str].update(update["$set"])
        return MagicMock(matched_count=1)


@pytest.fixture
def mock_materials_env(monkeypatch):
    mock_db = MockMaterialsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_materials_env):
    test_app = FastAPI()
    test_app.include_router(materials_router)
    test_app.mongodb = mock_materials_env
    return TestClient(test_app)


def test_materials_crud(client, mock_materials_env):
    # 1. Create material
    res = client.post("/api/materials", json={
        "code": "LEATH-TAN-01",
        "name": "Tan Synthetic Leather",
        "category": "upper",
        "unit": "meter",
        "rate": 250.0,
        "reorder_level": 50.0,
        "color": "Tan",
        "is_component": True,
        "component_category": "Upper",
        "default_yield_per_unit": 3.5,
    })
    assert res.status_code == 200, res.text
    mat = res.json()
    mid = mat["id"]
    assert mat["code"] == "LEATH-TAN-01"
    assert mat["default_yield_per_unit"] == 3.5

    # 2. List materials
    res = client.get("/api/materials")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # 3. Patch material
    res = client.patch(f"/api/materials/{mid}", json={
        "code": "LEATH-TAN-01",
        "name": "Tan Synthetic Leather Premium",
        "category": "upper",
        "unit": "meter",
        "rate": 260.0,
        "reorder_level": 40.0,
    })
    assert res.status_code == 200
    assert res.json()["name"] == "Tan Synthetic Leather Premium"

    # 4. Delete material
    res = client.delete(f"/api/materials/{mid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert len(mock_materials_env.materials_store) == 0


def test_inventory_movements_and_valuation(client, mock_materials_env):
    # Seed material
    m_oid = ObjectId()
    mid = str(m_oid)
    mock_materials_env.materials_store[mid] = {
        "_id": m_oid,
        "code": "SOLE-EVA-01",
        "name": "EVA Sheet Sole",
        "category": "sole",
        "unit": "pair",
        "rate": 100.0,
        "balance": 0.0,
        "reorder_level": 20.0,
    }

    # 1. Stock In movement
    res = client.post("/api/inventory/movements", json={
        "material_id": mid,
        "type": "in",
        "quantity": 100.0,
        "rate": 110.0,
        "party": "Vendor Alpha",
        "notes": "PO-101 delivery"
    })
    assert res.status_code == 200, res.text
    mov1 = res.json()
    mov_id = mov1["id"]

    # 2. Check balance via /api/inventory
    res = client.get("/api/inventory")
    assert res.status_code == 200
    inv = res.json()
    assert len(inv) == 1
    assert inv[0]["balance"] == 100.0
    assert inv[0]["weighted_avg_rate"] == 110.0
    assert inv[0]["value"] == 11000.0

    # 3. Stock Out movement
    res = client.post("/api/inventory/movements", json={
        "material_id": mid,
        "type": "out",
        "quantity": 30.0,
        "notes": "Issued to Cutting"
    })
    assert res.status_code == 200
    res = client.get("/api/inventory")
    assert res.json()[0]["balance"] == 70.0

    # 4. Stock Out exceeding balance should fail
    res = client.post("/api/inventory/movements", json={
        "material_id": mid,
        "type": "out",
        "quantity": 500.0,
    })
    assert res.status_code == 400

    # 5. List movements
    res = client.get(f"/api/inventory/movements?material_id={mid}")
    assert res.status_code == 200
    assert len(res.json()) >= 2

    # 6. Delete movement
    res = client.delete(f"/api/inventory/movements/{mov_id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_procurement_requirements_and_shortage(client, mock_materials_env):
    # Seed material
    m_oid = ObjectId()
    mid = str(m_oid)
    mock_materials_env.materials_store[mid] = {
        "_id": m_oid,
        "code": "FOAM-01",
        "name": "Memory Foam Insole",
        "category": "accessory",
        "unit": "pair",
        "rate": 30.0,
        "balance": 10.0,
        "reorder_level": 50.0,
    }

    # Seed style with BOM
    s_oid = ObjectId()
    mock_materials_env.styles_store[str(s_oid)] = {
        "_id": s_oid,
        "code": "SSK-RUN-01",
        "name": "Runner",
        "bom": [
            {
                "material_id": mid,
                "material_code": "FOAM-01",
                "material_name": "Memory Foam Insole",
                "unit": "pair",
                "rate": 30.0,
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "waste_pct": 0.0,
                "color": "Black"
            }
        ]
    }

    # Seed production job
    j_oid = ObjectId()
    jid = str(j_oid)
    mock_materials_env.production_jobs_store[jid] = {
        "_id": j_oid,
        "po_number": "PO-99",
        "style_code": "SSK-RUN-01",
        "color": "Black",
        "size": "8",
        "quantity": 50,
    }

    # 1. Procurement requirement API
    res = client.post("/api/procurement/requirement", json={"job_ids": [jid]})
    assert res.status_code == 200
    data = res.json()
    assert len(data["materials"]) == 1
    assert data["materials"][0]["total_qty_required"] == 50.0

    # 2. Inventory shortage API
    res = client.post("/api/inventory/shortage", json={"job_ids": [jid]})
    assert res.status_code == 200
    shortage_data = res.json()
    assert len(shortage_data["shortage"]) == 1
    # 50 required - 0 in stock mock list = 50 shortage (or 50 - balance)
    assert shortage_data["shortage"][0]["required"] == 50.0

    # 3. Inventory alerts API
    res = client.get("/api/inventory/alerts")
    assert res.status_code == 200
    alerts = res.json()
    assert len(alerts) >= 1


@pytest.mark.anyio
async def test_auto_consume_inventory(mock_materials_env):
    # Seed material
    m_oid = ObjectId()
    mid = str(m_oid)
    mock_materials_env.materials_store[mid] = {
        "_id": m_oid,
        "code": "SOLE-RUB-01",
        "name": "Rubber Sole",
        "category": "sole",
        "unit": "pair",
        "rate": 150.0,
        "balance": 100.0,
    }
    # Seed movements so balance = 100
    await mock_materials_env._insert_movement({
        "material_id": mid,
        "type": "in",
        "quantity": 100.0,
        "rate": 150.0,
    })

    # Seed style
    s_oid = ObjectId()
    mock_materials_env.styles_store[str(s_oid)] = {
        "_id": s_oid,
        "code": "SSK-BOOT-01",
        "bom": [
            {
                "material_code": "SOLE-RUB-01",
                "quantity": 1.0,
                "yield_per_unit": 1.0,
                "rate": 150.0,
            }
        ]
    }

    # Job
    j_oid = ObjectId()
    job = {
        "_id": j_oid,
        "style_code": "SSK-BOOT-01",
        "quantity": 20,
        "po_number": "PO-100",
        "color": "Black",
        "size": "9",
    }
    mock_materials_env.production_jobs_store[str(j_oid)] = job

    # Run auto consume
    consumed = await _auto_consume_inventory(job, "admin@sskfootcare.com", db=mock_materials_env)
    assert consumed is True
    assert job.get("inventory_consumed") is True
    assert len(mock_materials_env.movements_store) == 2  # 1 initial 'in', 1 auto 'out'
