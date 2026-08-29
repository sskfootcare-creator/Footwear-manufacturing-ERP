import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from fastapi import Request
from routes.pos import update_job, update_job_quantity, update_job_assignment, bulk_assign, report_payroll
from routes.workers import ready_for_pickup, worker_ledger, my_payroll
from models.orders import ProductionStageUpdate
from models.materials import QuantityUpdate
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
                    if op == "$gte" and not (val is not None and val >= op_val):
                        return False
                    if op == "$lte" and not (val is not None and val <= op_val):
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
        self.advances = GenericMockCollection()
        self.audit_logs = GenericMockCollection()
        self.system_settings = GenericMockCollection([{"_id": "stage_durations", "durations": {}}])


def make_request(db, user_payload):
    req = MagicMock(spec=Request)
    req.state = MagicMock()
    req.state.user = user_payload
    req.app = MagicMock()
    req.app.mongodb = db
    return req


@pytest.mark.anyio
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
    payload = ProductionStageUpdate(stage="stitching", completed_qty=100)
    res = await update_job(str(job_id), payload, req)

    updated_job = await db.production_jobs.find_one({"_id": job_id})
    assert updated_job["completed_qty"] == 100
    assert updated_job["completed_by"] is not None
    assert updated_job["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["completed_by"]["worker_name"] == "Ramesh Kumar"
    assert updated_job["completed_by"]["rate_per_pair"] == 12.0

    assert updated_job["assignments"]["stitching"]["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["assignments"]["stitching"]["completed_qty"] == 100


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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
    res = await ready_for_pickup(str(job_id), rfp_payload, req)
    assert res["ok"] is True

    updated_job = await db.production_jobs.find_one({"_id": job_id})
    assert updated_job["completed_qty"] == 50
    assert updated_job["completed_by"] is not None
    assert updated_job["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["completed_by"]["rate_per_pair"] == 15.0
    assert updated_job["assignments"]["cutting"]["completed_by"]["worker_id"] == str(w1_id)


@pytest.mark.anyio
async def test_update_job_quantity_snapshots_completed_by(monkeypatch):
    db = MockDB()
    w1_id = ObjectId()
    db.workers.docs.append({
        "_id": w1_id,
        "name": "Ramesh Kumar",
        "rate_per_pair": 14.0,
    })

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-TEST-003",
        "style_code": "LOAFER",
        "size": "9",
        "quantity": 80,
        "stage": "stitching",
        "assignments": {
            "stitching": {
                "worker_id": str(w1_id),
                "worker_name": "Ramesh Kumar",
                "rate_per_pair": 14.0,
            }
        },
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "manager@ssk.com", "role": "manager", "roles": ["manager"]})

    payload = QuantityUpdate(quantity=80, completed_qty=75, reason="Batch complete")
    res = await update_job_quantity(str(job_id), payload, req)

    updated_job = await db.production_jobs.find_one({"_id": job_id})
    assert updated_job["completed_qty"] == 75
    assert updated_job["completed_by"] is not None
    assert updated_job["completed_by"]["worker_id"] == str(w1_id)
    assert updated_job["completed_by"]["rate_per_pair"] == 14.0
    assert updated_job["assignments"]["stitching"]["completed_qty"] == 75
    assert updated_job["assignments"]["stitching"]["completed_by"]["worker_id"] == str(w1_id)


@pytest.mark.anyio
async def test_worker_ledger_credits_completed_by_worker(monkeypatch):
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
        "po_number": "PO-TEST-004",
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
                    "worker_id": str(w1_id),  # Completed by w1
                    "worker_name": "Ramesh Kumar",
                    "rate_per_pair": 12.0,
                    "at": "2026-03-01T10:00:00Z",
                },
            }
        },
    })

    req = make_request(db, {"id": str(w1_id), "role": "admin", "roles": ["admin"]})

    ledger_res_w1 = await worker_ledger(str(w1_id), req)
    assert len(ledger_res_w1["entries"]) == 1
    assert ledger_res_w1["entries"][0]["amount"] == 1200.0
    assert ledger_res_w1["total_earned"] == 1200.0

    ledger_res_w2 = await worker_ledger(str(w2_id), req)
    assert len(ledger_res_w2["entries"]) == 0
    assert ledger_res_w2["total_earned"] == 0.0


@pytest.mark.anyio
async def test_multiple_reassignments_interspersed_completions(monkeypatch):
    """
    Test a job with multiple interspersed reassignments and completions:
    1. Worker A completes 30 pairs @ ₹10 = ₹300
    2. Reassigned to Worker B
    3. Worker B completes up to 70 pairs (+40 pairs @ ₹12 = ₹480)
    4. Reassigned to Worker C
    5. Worker C completes up to 100 pairs (+30 pairs @ ₹15 = ₹450)
    Confirm report_payroll and worker_ledger split earnings accurately without gaps or double-counting.
    """
    db = MockDB()
    wA_id = ObjectId()
    wB_id = ObjectId()
    wC_id = ObjectId()
    db.workers.docs.extend([
        {"_id": wA_id, "name": "Worker A", "skill": "stitching", "rate_per_pair": 10.0},
        {"_id": wB_id, "name": "Worker B", "skill": "stitching", "rate_per_pair": 12.0},
        {"_id": wC_id, "name": "Worker C", "skill": "stitching", "rate_per_pair": 15.0},
    ])

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-MULTI-001",
        "style_code": "SNEAKER",
        "size": "8",
        "quantity": 100,
        "completed_qty": 100,
        "stage": "stitching",
        "assignments": {
            "stitching": {
                "worker_id": str(wC_id),
                "worker_name": "Worker C",
                "rate_per_pair": 15.0,
                "completed_qty": 100,
                "completed_by": {
                    "worker_id": str(wC_id),
                    "worker_name": "Worker C",
                    "rate_per_pair": 15.0,
                    "at": "2026-03-03T10:00:00Z",
                },
            }
        },
        "history": [
            {
                "event": "assignment_update",
                "role": "stitching",
                "worker_id": str(wA_id),
                "worker_name": "Worker A",
                "rate_per_pair": 10.0,
                "at": "2026-03-01T08:00:00Z",
            },
            {
                "event": "quantity_update",
                "role": "stitching",
                "completed_qty": 30,
                "completed_by": {
                    "worker_id": str(wA_id),
                    "worker_name": "Worker A",
                    "rate_per_pair": 10.0,
                    "at": "2026-03-01T12:00:00Z",
                },
                "at": "2026-03-01T12:00:00Z",
            },
            {
                "event": "assignment_update",
                "role": "stitching",
                "worker_id": str(wB_id),
                "worker_name": "Worker B",
                "rate_per_pair": 12.0,
                "at": "2026-03-02T08:00:00Z",
            },
            {
                "event": "quantity_update",
                "role": "stitching",
                "completed_qty": 70,
                "completed_by": {
                    "worker_id": str(wB_id),
                    "worker_name": "Worker B",
                    "rate_per_pair": 12.0,
                    "at": "2026-03-02T16:00:00Z",
                },
                "at": "2026-03-02T16:00:00Z",
            },
            {
                "event": "assignment_update",
                "role": "stitching",
                "worker_id": str(wC_id),
                "worker_name": "Worker C",
                "rate_per_pair": 15.0,
                "at": "2026-03-03T08:00:00Z",
            },
            {
                "event": "quantity_update",
                "role": "stitching",
                "completed_qty": 100,
                "completed_by": {
                    "worker_id": str(wC_id),
                    "worker_name": "Worker C",
                    "rate_per_pair": 15.0,
                    "at": "2026-03-03T10:00:00Z",
                },
                "at": "2026-03-03T10:00:00Z",
            },
        ],
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})

    payroll_res = await report_payroll(req)
    rows = payroll_res.get("rows", [])

    # Check Worker A: 30 pairs * ₹10 = ₹300
    row_A = next((r for r in rows if r["worker_id"] == str(wA_id)), None)
    assert row_A is not None
    assert row_A["total_pairs"] == 30
    assert row_A["total_earning"] == 300.0

    # Check Worker B: 40 pairs * ₹12 = ₹480
    row_B = next((r for r in rows if r["worker_id"] == str(wB_id)), None)
    assert row_B is not None
    assert row_B["total_pairs"] == 40
    assert row_B["total_earning"] == 480.0

    # Check Worker C: 30 pairs * ₹15 = ₹450
    row_C = next((r for r in rows if r["worker_id"] == str(wC_id)), None)
    assert row_C is not None
    assert row_C["total_pairs"] == 30
    assert row_C["total_earning"] == 450.0

    # Verify grand totals
    assert payroll_res["grand_total"] == 300.0 + 480.0 + 450.0  # 1230.0

    # Verify worker ledgers
    ledger_A = await worker_ledger(str(wA_id), req)
    assert ledger_A["total_earned"] == 300.0
    assert len(ledger_A["entries"]) == 1

    ledger_B = await worker_ledger(str(wB_id), req)
    assert ledger_B["total_earned"] == 480.0
    assert len(ledger_B["entries"]) == 1

    ledger_C = await worker_ledger(str(wC_id), req)
    assert ledger_C["total_earned"] == 450.0
    assert len(ledger_C["entries"]) == 1


@pytest.mark.anyio
async def test_reassignment_with_zero_work_after_reassignment(monkeypatch):
    """
    Worker A completes 50 pairs @ ₹10.
    Job is reassigned to Worker B, but Worker B completes 0 work.
    Confirm Worker A gets credited for 50 pairs, Worker B gets 0.
    """
    db = MockDB()
    wA_id = ObjectId()
    wB_id = ObjectId()
    db.workers.docs.extend([
        {"_id": wA_id, "name": "Worker A", "skill": "stitching", "rate_per_pair": 10.0},
        {"_id": wB_id, "name": "Worker B", "skill": "stitching", "rate_per_pair": 12.0},
    ])

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-REASGN-001",
        "style_code": "BOOT",
        "size": "9",
        "quantity": 100,
        "completed_qty": 50,
        "stage": "stitching",
        "assignments": {
            "stitching": {
                "worker_id": str(wB_id),  # Reassigned to B
                "worker_name": "Worker B",
                "rate_per_pair": 12.0,
                "completed_qty": 50,
                "completed_by": {
                    "worker_id": str(wA_id),  # Completed by A
                    "worker_name": "Worker A",
                    "rate_per_pair": 10.0,
                    "at": "2026-03-01T12:00:00Z",
                },
            }
        },
        "history": [
            {
                "event": "quantity_update",
                "role": "stitching",
                "completed_qty": 50,
                "completed_by": {
                    "worker_id": str(wA_id),
                    "worker_name": "Worker A",
                    "rate_per_pair": 10.0,
                    "at": "2026-03-01T12:00:00Z",
                },
                "at": "2026-03-01T12:00:00Z",
            },
            {
                "event": "assignment_update",
                "role": "stitching",
                "worker_id": str(wB_id),
                "worker_name": "Worker B",
                "rate_per_pair": 12.0,
                "at": "2026-03-02T08:00:00Z",
            },
        ],
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})

    payroll_res = await report_payroll(req)
    rows = payroll_res.get("rows", [])

    row_A = next((r for r in rows if r["worker_id"] == str(wA_id)), None)
    assert row_A is not None
    assert row_A["total_pairs"] == 50
    assert row_A["total_earning"] == 500.0

    row_B = next((r for r in rows if r["worker_id"] == str(wB_id)), None)
    assert row_B is None


@pytest.mark.anyio
async def test_legacy_job_fallback_to_current_assignment(monkeypatch):
    """
    For historical jobs with no completed_by snapshots or milestone logs,
    report_payroll falls back to the current assignments field.
    """
    db = MockDB()
    w1_id = ObjectId()
    db.workers.docs.append({
        "_id": w1_id,
        "name": "Legacy Worker",
        "skill": "cutting",
        "rate_per_pair": 8.0,
    })

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-LEGACY-001",
        "style_code": "SLIPPER",
        "size": "7",
        "quantity": 60,
        "completed_qty": 60,
        "stage": "cutting",
        "assignments": {
            "cutting": {
                "worker_id": str(w1_id),
                "worker_name": "Legacy Worker",
                "rate_per_pair": 8.0,
                "completed_qty": 60,
                # No completed_by snapshot!
            }
        },
        # No completed_by in history!
        "history": [
            {"event": "stage_update", "stage": "cutting", "completed_qty": 60, "at": "2025-01-01T10:00:00Z"}
        ]
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})

    payroll_res = await report_payroll(req)
    rows = payroll_res.get("rows", [])

    row = next((r for r in rows if r["worker_id"] == str(w1_id)), None)
    assert row is not None
    assert row["total_pairs"] == 60
    assert row["total_earning"] == 480.0


@pytest.mark.anyio
async def test_my_payroll_reflects_same_corrected_earnings_as_admin_report(monkeypatch):
    """
    Verify: as Karigar A (via karigar login/session), check "My Payroll" reflects the
    same corrected earnings as the admin-side payroll report for the same period.
    Also verify Karigar B (reassigned, 0 work done) receives 0 in both views.
    """
    db = MockDB()
    wA_id = ObjectId()
    wB_id = ObjectId()
    db.workers.docs.extend([
        {"_id": wA_id, "name": "Karigar A", "skill": "stitching", "rate_per_pair": 10.0},
        {"_id": wB_id, "name": "Karigar B", "skill": "stitching", "rate_per_pair": 12.0},
    ])

    job_id = ObjectId()
    db.production_jobs.docs.append({
        "_id": job_id,
        "po_number": "PO-REASGN-002",
        "style_code": "BOOT",
        "size": "9",
        "quantity": 100,
        "completed_qty": 50,
        "stage": "stitching",
        "updated_at": "2026-08-15T12:00:00Z",
        "assignments": {
            "stitching": {
                "worker_id": str(wB_id),  # Active assignee is Karigar B
                "worker_name": "Karigar B",
                "rate_per_pair": 12.0,
                "completed_qty": 50,
                "completed_by": {
                    "worker_id": str(wA_id),  # But work was completed by Karigar A!
                    "worker_name": "Karigar A",
                    "rate_per_pair": 10.0,
                    "at": "2026-03-01T12:00:00Z",
                },
            }
        },
        "history": [
            {
                "event": "quantity_update",
                "role": "stitching",
                "completed_qty": 50,
                "completed_by": {
                    "worker_id": str(wA_id),
                    "worker_name": "Karigar A",
                    "rate_per_pair": 10.0,
                    "at": "2026-03-01T12:00:00Z",
                },
                "at": "2026-03-01T12:00:00Z",
            },
            {
                "event": "assignment_update",
                "role": "stitching",
                "worker_id": str(wB_id),
                "worker_name": "Karigar B",
                "rate_per_pair": 12.0,
                "at": "2026-03-02T08:00:00Z",
            },
        ],
    })

    monkeypatch.setattr("routes.pos.get_db", lambda: db)

    # 1. Admin checks report_payroll
    admin_req = make_request(db, {"email": "admin@ssk.com", "role": "admin", "roles": ["admin"]})
    admin_payroll = await report_payroll(admin_req)
    admin_rows = admin_payroll.get("rows", [])
    admin_row_A = next((r for r in admin_rows if r["worker_id"] == str(wA_id)), None)
    admin_row_B = next((r for r in admin_rows if r["worker_id"] == str(wB_id)), None)

    assert admin_row_A is not None
    assert admin_row_A["total_pairs"] == 50
    assert admin_row_A["total_earning"] == 500.0
    assert admin_row_B is None

    # 2. Karigar A logs in and accesses /api/my/payroll
    karigarA_req = make_request(db, {
        "id": str(wA_id),
        "worker_id": str(wA_id),
        "name": "Karigar A",
        "role": "worker",
    })
    karigarA_payroll_res = await my_payroll(karigarA_req)
    karigarA_payroll = karigarA_payroll_res.get("payroll", {})

    # Ensure Karigar A view matches the Admin view identically
    assert karigarA_payroll["worker_id"] == str(wA_id)
    assert karigarA_payroll["total_pairs"] == admin_row_A["total_pairs"] == 50
    assert karigarA_payroll["total_earning"] == admin_row_A["total_earning"] == 500.0
    assert karigarA_payroll["net_payable"] == admin_row_A["net_payable"] == 500.0

    # 3. Karigar B logs in and accesses /api/my/payroll
    karigarB_req = make_request(db, {
        "id": str(wB_id),
        "worker_id": str(wB_id),
        "name": "Karigar B",
        "role": "worker",
    })
    karigarB_payroll_res = await my_payroll(karigarB_req)
    karigarB_payroll = karigarB_payroll_res.get("payroll", {})

    # Ensure Karigar B gets 0 earnings (no double-credit)
    assert karigarB_payroll["worker_id"] == str(wB_id)
    assert karigarB_payroll["total_pairs"] == 0
    assert karigarB_payroll["total_earning"] == 0.0
    assert karigarB_payroll["net_payable"] == 0.0



