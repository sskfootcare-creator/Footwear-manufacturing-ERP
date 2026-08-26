import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.components import components_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    async def to_list(self, limit):
        return self.docs


class MockComponentsDB:
    def __init__(self):
        self.component_master_store = {}
        self.component_movements_store = []
        self.style_mappings_store = {}
        self.styles_store = {}
        self.materials_store = {}
        self.audit_logs_store = []

        self.component_master = MagicMock()
        self.component_master.find = MagicMock(side_effect=self._find_components)
        self.component_master.find_one = AsyncMock(side_effect=self._find_one_component)
        self.component_master.insert_one = AsyncMock(side_effect=self._insert_component)
        self.component_master.update_one = AsyncMock(side_effect=self._update_component)
        self.component_master.update_many = AsyncMock(return_value=MagicMock(modified_count=1))

        self.component_stock_movements = MagicMock()
        self.component_stock_movements.find = MagicMock(side_effect=self._find_movements)
        self.component_stock_movements.insert_one = AsyncMock(side_effect=self._insert_movement)

        self.style_component_mapping = MagicMock()
        self.style_component_mapping.find = MagicMock(side_effect=self._find_mappings)
        self.style_component_mapping.find_one = AsyncMock(side_effect=self._find_one_mapping)
        self.style_component_mapping.insert_one = AsyncMock(side_effect=self._insert_mapping)
        self.style_component_mapping.update_one = AsyncMock(side_effect=self._update_mapping)
        self.style_component_mapping.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
        self.style_component_mapping.delete_one = AsyncMock(side_effect=self._delete_mapping)

        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=self._find_styles)
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        self.materials = MagicMock()
        self.materials.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    def _find_components(self, query=None):
        docs = list(self.component_master_store.values())
        if query and "component_code" in query and isinstance(query["component_code"], str):
            docs = [d for d in docs if d.get("component_code") == query["component_code"]]
        return MockCursor(docs)

    async def _find_one_component(self, query):
        if "_id" in query:
            oid_str = str(query["_id"])
            return self.component_master_store.get(oid_str)
        if "component_code" in query:
            for c in self.component_master_store.values():
                if (c.get("component_code") == query["component_code"]
                        and c.get("color") == query.get("color")
                        and c.get("size") == query.get("size")):
                    return c
        return None

    async def _insert_component(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.component_master_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_component(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.component_master_store:
            comp = self.component_master_store[oid_str]
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    comp[k] = comp.get(k, 0) + v
            if "$set" in update:
                comp.update(update["$set"])
            return MagicMock(modified_count=1, matched_count=1)
        return MagicMock(modified_count=0, matched_count=0)

    def _find_movements(self, query=None):
        return MockCursor(self.component_movements_store)

    async def _insert_movement(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.component_movements_store.append(doc)
        return MagicMock(inserted_id=oid)

    def _find_mappings(self, query=None):
        return MockCursor(list(self.style_mappings_store.values()))

    async def _find_one_mapping(self, query):
        oid_str = str(query.get("_id"))
        return self.style_mappings_store.get(oid_str)

    async def _insert_mapping(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.style_mappings_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_mapping(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.style_mappings_store:
            self.style_mappings_store[oid_str].update(update.get("$set", {}))
            return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def _delete_mapping(self, query):
        oid_str = str(query.get("_id"))
        self.style_mappings_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_styles(self, query=None):
        return MockCursor(list(self.styles_store.values()))

    async def _find_one_style(self, query):
        oid_str = str(query.get("_id"))
        return self.styles_store.get(oid_str)


@pytest.fixture
def mock_comps_env(monkeypatch):
    mock_db = MockComponentsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User"
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_comps_env):
    test_app = FastAPI()
    test_app.include_router(components_router)
    test_app.mongodb = mock_comps_env
    return TestClient(test_app)


def test_component_crud_and_matrix(client, mock_comps_env):
    # 1. Create component row
    res = client.post("/api/components", json={
        "component_code": "CMP-UPP-01",
        "component_name": "Leather Upper Derby",
        "component_category": "Upper",
        "color": "Black",
        "size": "40",
        "current_stock": 50,
        "reorder_level": 10,
        "minimum_stock": 5,
        "lead_time_days": 2,
        "active": True
    })
    assert res.status_code == 200
    comp = res.json()
    assert comp["component_code"] == "CMP-UPP-01"
    assert comp["current_stock"] == 50
    assert comp["available_stock"] == 50
    cid = comp["id"]

    # 2. List components
    res = client.get("/api/components")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. Get Size Matrix
    res = client.get("/api/components/size-matrix/CMP-UPP-01")
    assert res.status_code == 200
    matrix_data = res.json()
    assert matrix_data["component_code"] == "CMP-UPP-01"
    assert "Black" in matrix_data["matrix"]
    assert matrix_data["matrix"]["Black"]["40"]["qty"] == 50

    # 4. Update component metadata
    res = client.put(f"/api/components/{cid}", json={
        "component_name": "Leather Upper Derby Oxford",
        "reorder_level": 15
    })
    assert res.status_code == 200
    assert res.json()["component_name"] == "Leather Upper Derby Oxford"

    # 5. Post Component Movement (Adjustment to zero so we can delete)
    res = client.post("/api/components/movements", json={
        "component_id": cid,
        "movement_type": "adjustment",
        "adjustment_dir": "decrease",
        "quantity": 50,
        "notes": "Adjustment to zero"
    })
    assert res.status_code == 200
    assert res.json()["component"]["current_stock"] == 0

    # 6. List movements
    res = client.get("/api/components/movements")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 7. Delete component
    res = client.delete(f"/api/components/{cid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_style_component_mapping(client, mock_comps_env):
    sid = str(ObjectId())
    cid = str(ObjectId())

    mock_comps_env.styles_store[sid] = {
        "_id": ObjectId(sid),
        "code": "SSK-M-01",
        "name": "Classic Derby Shoes",
    }
    mock_comps_env.component_master_store[cid] = {
        "_id": ObjectId(cid),
        "component_code": "SOLE-TPR-01",
        "component_name": "TPR Sole",
        "component_category": "Sole",
        "color": "Black",
        "size": "40",
        "current_stock": 100,
        "reserved_stock": 0,
        "active": True
    }

    # 1. Create mapping
    res = client.post("/api/style-component-mapping", json={
        "style_id": sid,
        "component_id": cid,
        "quantity_per_pair": 1.0,
        "wastage_percent": 2.0,
        "active": True
    })
    assert res.status_code == 200
    mapping = res.json()
    mid = mapping["id"]
    assert mapping["style_id"] == sid
    assert mapping["component_id"] == cid

    # 2. List mappings
    res = client.get(f"/api/style-component-mapping?style_id={sid}")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["style_code"] == "SSK-M-01"

    # 3. Update mapping
    res = client.put(f"/api/style-component-mapping/{mid}", json={
        "quantity_per_pair": 1.05
    })
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # 4. Delete mapping
    res = client.delete(f"/api/style-component-mapping/{mid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True
