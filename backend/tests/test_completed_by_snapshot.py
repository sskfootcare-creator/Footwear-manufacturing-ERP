import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from fastapi import Request
from routes.pos import update_job, update_job_quantity, update_job_assignment, bulk_assign, report_payroll
from routes.workers import mark_job_ready_for_pickup
from models.pos import JobUpdate, QuantityUpdate
from models.workers import AssignmentUpdate, BulkAssign, ReadyForPickupIn


class GenericMockCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def _matches(self, doc, query):
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                return any(self._matches(doc, cond) for cond in v)
            if k == "$and":
                return all(self._matches(doc, cond) for cond in v)
            val = doc.get(k)
            if isinstance(v, dict):
                for op, op_val in v.items():
                    if op == "$gte" and not (val >= op_val):
                        return False
                    if op == "$lte" and not (val <= op_val):
                        return False
                    if op == "$in" and val not in op_val:
                        return False
            elif isinstance(val, list):
                if v not in val:
                    return False
            elif val != v:
                return False
        return True

    async def find_one(self, query=None, projection=None):
        for d in self.docs:
            if self._matches(d, query):
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        matched = [dict(d) for d in self.docs if self._matches(d, query)]
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=matched)
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        return mock_cursor

    async def update_one(self, query, update):
        for d in self.docs:
            if self._matches(d, query):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        if "." in k:
                            parts = k.split(".")
                            curr = d
                            for p in parts[:-1]:
                                if p not in curr:
                                    curr[p] = {}
                                curr = curr[p]
                            curr[parts[-1]] = v
                        else:
                            d[k] = v
                if "$push" in update:
                    for k, v in update["$push"].items():
                        d.setdefault(k, []).append(v)
                if "$unset" in update:
                    for k in update["$unset"]:
                        d.pop(k, None)
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        mock_res = MagicMock()
        mock_res.inserted_id = d["_id"]
        return mock_res


class MockDB:
    def __init__(self):
        self.production_jobs = GenericMockCollection()
        self.workers = GenericMockCollection()
        self.styles = GenericMockCollection()
        self.notifications = GenericMockCollection()
        self.system_settings = GenericMockCollection([{"_id": "stage_durations", "durations": {}}])


def make_request(db, user_payload):
    req = MagicMock(spec=Request)
    req.state = MagicMock()
    req.state.user = user_payload
    req.app = MagicMock()
    req.app.mongodb = db
    return req


@pytest.mark.asyncio
async def test_update_job_snapshots_completed_by(monkeypatch):
    db = MockDB()
    w1_id = ObjectId()
    db.workers.docs.append({
        "_id": w1_id,
        "name": "Ramesh Kumar",
        "rate_per_pair": 12.0,
    })

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-TEST-001",
        "style_code": "OXFORD",
        "size": "8",
        "quantity": 100,
        "stage": "stitching",
        "assignments": {
            "stitching": {
                "worker_id": str(w1_id),
                "worker_name": "Ramesh Kumar",
                "rate_per_pair": 12.0,
            }
        },
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})

    # Update job with completed_qty
    payload = JobUpdate(stage="stitching", completed_qty=100)
    res = await update_job(str(job_id), payload, req)

    updated_job = await db.production_jobs.find_one({"_id": job_id})
    assert updated_job["completed_qty"] == 100
    assert updated_job["completed_by"] is not None
    assert updated_job["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["completed_by"]["worker_name"] == "Ramesh Kumar"
    assert updated_job["completed_by"]["rate_per_pair"] == 12.0

    assert updated_job["assignments"]["stitching"]["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["assignments"]["stitching"]["completed_qty"] == 100


@pytest.mark.asyncio
async def test_reassignment_preserves_completed_by_snapshot(monkeypatch):
    db = MockDB()
    w1_id = ObjectId()
    w2_id = ObjectId()
    db.workers.docs.extend([
        {"_id": w1_id, "name": "Ramesh Kumar", "rate_per_pair": 12.0},
        {"_id": w2_id, "name": "Suresh Patel", "rate_per_pair": 18.0},
    ])

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-TEST-001",
        "style_code": "OXFORD",
        "size": "8",
        "quantity": 100,
        "completed_qty": 100,
        "stage": "stitching",
        "completed_by": {
            "worker_id": str(w1_id),
            "worker_name": "Ramesh Kumar",
            "rate_per_pair": 12.0,
            "at": "2026-03-01T10:00:00Z",
        },
        "assignments": {
            "stitching": {
                "worker_id": str(w1_id),
                "worker_name": "Ramesh Kumar",
                "rate_per_pair": 12.0,
                "completed_qty": 100,
                "completed_by": {
                    "worker_id": str(w1_id),
                    "worker_name": "Ramesh Kumar",
                    "rate_per_pair": 12.0,
                    "at": "2026-03-01T10:00:00Z",
                },
            }
        },
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})

    # Reassign stitching role to Worker 2
    asgn_payload = AssignmentUpdate(role="stitching", worker_id=str(w2_id), rate_per_pair=18.0)
    await update_job_assignment(str(job_id), asgn_payload, req)

    updated_job = await db.production_jobs.find_one({"_id": job_id})
    # Active assignee is now w2
    assert updated_job["assignments"]["stitching"]["worker_id"] == str(w2_id)
    assert updated_job["assignments"]["stitching"]["worker_name"] == "Suresh Patel"
    # But completed_by remains Worker 1!
    assert updated_job["assignments"]["stitching"]["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["assignments"]["stitching"]["completed_by"]["rate_per_pair"] == 12.0


@pytest.mark.asyncio
async def test_report_payroll_credits_completed_by_worker_not_reassigned_worker(monkeypatch):
    db = MockDB()
    w1_id = ObjectId()
    w2_id = ObjectId()
    db.workers.docs.extend([
        {"_id": w1_id, "name": "Ramesh Kumar", "skill": "stitching", "rate_per_pair": 12.0},
        {"_id": w2_id, "name": "Suresh Patel", "skill": "stitching", "rate_per_pair": 18.0},
    ])

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-TEST-001",
        "style_code": "OXFORD",
        "size": "8",
        "quantity": 100,
        "completed_qty": 100,
        "stage": "stitching",
        "assignments": {
            "stitching": {
                "worker_id": str(w2_id),  # Reassigned to w2
                "worker_name": "Suresh Patel",
                "rate_per_pair": 18.0,
                "completed_qty": 100,
                "completed_by": {
                    "worker_id": str(w1_id),  # But completed by w1!
                    "worker_name": "Ramesh Kumar",
                    "rate_per_pair": 12.0,
                    "at": "2026-03-01T10:00:00Z",
                },
            }
        },
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})

    payroll_res = await report_payroll(req)
    rows = payroll_res.get("rows", [])
    
    # Worker 1 should have earned 100 pairs * ₹12 = ₹1200
    w1_row = next((r for r in rows if r["worker_id"] == str(w1_id)), None)
    assert w1_row is not None
    assert w1_row["total_pairs"] == 100
    assert w1_row["total_earning"] == 1200.0

    # Worker 2 should have 0 earnings
    w2_row = next((r for r in rows if r["worker_id"] == str(w2_id)), None)
    assert w2_row is None


@pytest.mark.asyncio
async def test_ready_for_pickup_snapshots_completed_by(monkeypatch):
    db = MockDB()
    w1_id = ObjectId()
    db.workers.docs.append({
        "_id": w1_id,
        "name": "Ramesh Kumar",
        "rate_per_pair": 15.0,
    })

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-TEST-002",
        "style_code": "DERBY",
        "size": "7",
        "quantity": 50,
        "stage": "cutting",
        "assignments": {
            "cutting": {
                "worker_id": str(w1_id),
                "worker_name": "Ramesh Kumar",
                "rate_per_pair": 15.0,
            }
        },
    })

    req = make_request(db, {"id": str(w1_id), "worker_id": str(w1_id), "name": "Ramesh Kumar", "role": "worker"})

    rfp_payload = ReadyForPickupIn(completed_qty=50, notes="Cutting finished")
    res = await mark_job_ready_for_pickup(str(job_id), rfp_payload, req)
    assert res["ok"] is True

    updated_job = await db.production_jobs.find_one({"_id": job_id})
    assert updated_job["completed_qty"] == 50
    assert updated_job["completed_by"] is not None
    assert updated_job["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["completed_by"]["rate_per_pair"] == 15.0
    assert updated_job["assignments"]["cutting"]["completed_by"]["worker_id"] == str(w1_id)
