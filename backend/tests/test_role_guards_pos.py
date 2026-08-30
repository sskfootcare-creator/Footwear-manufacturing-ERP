import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.pos import pos_router
from routes.workers import workers_router
from tests.test_pos_routes import MockPosDB


@pytest.fixture
def test_setup(monkeypatch):
    mock_db = MockPosDB()
    monkeypatch.setattr(server, "db", mock_db)
    
    current_user_holder = {"user": None}

    async def mock_get_current_user(request=None):
        if current_user_holder["user"] is not None:
            return current_user_holder["user"]
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    monkeypatch.setattr(server, "log_activity", AsyncMock())

    app = FastAPI()
    app.include_router(pos_router)
    app.include_router(workers_router)
    client = TestClient(app)

    return mock_db, current_user_holder, client


def test_worker_cannot_access_production_jobs(test_setup):
    mock_db, current_user_holder, client = test_setup
    
    # 1. Seed worker & job
    wid = str(ObjectId())
    job_id = str(ObjectId())
    asyncio.run(mock_db.workers.insert_one({
        "_id": ObjectId(wid),
        "name": "Karigar 1",
        "phone": "9876543210",
        "role": "worker",
        "rate_per_pair": 25.0,
        "active": True
    }))
    asyncio.run(mock_db.production_jobs.insert_one({
        "_id": ObjectId(job_id),
        "po_number": "PO-101",
        "style_code": "ART-01",
        "stage": "cutting",
        "quantity": 100,
        "assignments": {
            "cutting": {
                "worker_id": wid,
                "worker_name": "Karigar 1",
                "rate_per_pair": 25.0,
            },
            "stitching": {
                "worker_id": str(ObjectId()),
                "worker_name": "Other Karigar",
                "rate_per_pair": 40.0,
            }
        }
    }))

    # Set user context to worker
    current_user_holder["user"] = {
        "id": wid,
        "worker_id": wid,
        "email": "9876543210",
        "role": "worker",
        "name": "Karigar 1"
    }

    # Calling /api/production/jobs MUST BE 403 Forbidden
    r_jobs = client.get("/api/production/jobs")
    assert r_jobs.status_code == 403, f"Expected 403 for worker on /production/jobs, got {r_jobs.status_code}: {r_jobs.text}"

    # Calling /api/pos MUST BE 403 Forbidden
    r_pos = client.get("/api/pos")
    assert r_pos.status_code == 403, f"Expected 403 for worker on /pos, got {r_pos.status_code}: {r_pos.text}"

    # Calling /api/clients MUST BE 403 Forbidden
    r_clients = client.get("/api/clients")
    assert r_clients.status_code == 403, f"Expected 403 for worker on /clients, got {r_clients.status_code}: {r_clients.text}"

    # Calling /api/reports/payroll MUST BE 403 Forbidden
    r_payroll = client.get("/api/reports/payroll")
    assert r_payroll.status_code == 403

    # Calling /api/defects MUST BE 403 Forbidden
    r_defects = client.get("/api/defects")
    assert r_defects.status_code == 403

    # BUT /api/my/tasks MUST STILL WORK and return 200
    r_mytasks = client.get("/api/my/tasks?scope=active")
    assert r_mytasks.status_code == 200, f"Expected 200 for worker on /my/tasks, got {r_mytasks.status_code}: {r_mytasks.text}"
    tasks = r_mytasks.json()
    assert len(tasks) > 0


def test_admin_manager_production_sales_access(test_setup):
    mock_db, current_user_holder, client = test_setup

    asyncio.run(mock_db.production_jobs.insert_one({
        "po_number": "PO-TEST",
        "style_code": "ART-01",
        "stage": "cutting",
        "quantity": 10,
    }))
    asyncio.run(mock_db.pos.insert_one({
        "po_number": "PO-TEST",
        "client_name": "Client A",
        "line_items": [{"style_code": "ART-01", "quantity": 10, "unit_price": 500.0, "amount": 5000.0}],
    }))

    roles_for_jobs = {
        "admin": 200,
        "manager": 200,
        "production": 200,
        "sales": 403,
        "worker": 403,
    }
    for role, expected_code in roles_for_jobs.items():
        current_user_holder["user"] = {"id": f"u_{role}", "email": f"{role}@ssk.com", "role": role, "name": f"{role} User"}
        r = client.get("/api/production/jobs")
        assert r.status_code == expected_code, f"Role {role} on /production/jobs got {r.status_code}, expected {expected_code}"

    roles_for_pos = {
        "admin": 200,
        "manager": 200,
        "sales": 200,
        "production": 200,
        "worker": 403,
    }
    for role, expected_code in roles_for_pos.items():
        current_user_holder["user"] = {"id": f"u_{role}", "email": f"{role}@ssk.com", "role": role, "name": f"{role} User"}
        r = client.get("/api/pos")
        assert r.status_code == expected_code, f"Role {role} on /pos got {r.status_code}, expected {expected_code}"

    roles_for_clients = {
        "admin": 200,
        "manager": 200,
        "sales": 200,
        "production": 403,
        "worker": 403,
    }
    for role, expected_code in roles_for_clients.items():
        current_user_holder["user"] = {"id": f"u_{role}", "email": f"{role}@ssk.com", "role": role, "name": f"{role} User"}
        r = client.get("/api/clients")
        assert r.status_code == expected_code, f"Role {role} on /clients got {r.status_code}, expected {expected_code}"


def test_manager_cannot_access_my_tasks(test_setup):
    mock_db, current_user_holder, client = test_setup

    current_user_holder["user"] = {
        "id": "mgr_1",
        "email": "manager@sskfootcare.com",
        "role": "manager",
        "name": "Manager"
    }
    # /my/tasks is strictly worker only
    r = client.get("/api/my/tasks")
    assert r.status_code == 403
