"""Monthly Salaried Staff Payroll, Attendance & Holiday Management Routes."""

import calendar
import logging
from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from bson import ObjectId

from auth import get_current_user_factory, require_roles

log = logging.getLogger("staff_payroll")
staff_payroll_router = APIRouter(prefix="/api/staff-payroll", tags=["Monthly Staff Payroll"])

def _get_db(request: Request):
    return getattr(request.app, "mongodb", None) or __import__("server").db


async def _get_user(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    fn = await get_current_user_factory(_get_db(request))
    return await fn(request)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(val: str) -> ObjectId:
    try:
        return ObjectId(val)
    except Exception:
        raise HTTPException(400, f"Invalid ID format: '{val}'")


def stringify(doc: dict) -> dict:
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d


class StaffEmployeeIn(BaseModel):
    name: str
    role: str = "Staff"
    department: Optional[str] = "Operations"
    monthly_salary: float = Field(..., ge=0)
    phone: Optional[str] = ""
    joining_date: Optional[str] = ""
    relieving_date: Optional[str] = ""
    bank_account: Optional[str] = ""
    upi_id: Optional[str] = ""
    is_active: bool = True
    notes: Optional[str] = ""


class HolidayIn(BaseModel):
    holiday_date: str  # YYYY-MM-DD
    name: str
    holiday_type: Optional[str] = "Public Holiday"


class AttendanceMarkIn(BaseModel):
    staff_id: str
    date: str  # YYYY-MM-DD
    status: str = "present"  # present | absent | half_day | paid_leave | holiday | week_off
    overtime_hours: Optional[float] = 0.0
    notes: Optional[str] = ""


class BulkAttendanceIn(BaseModel):
    date: str  # YYYY-MM-DD
    status: str = "present"
    staff_ids: Optional[List[str]] = None


class SalaryPaymentIn(BaseModel):
    staff_id: str
    month: str  # YYYY-MM
    amount: float = Field(..., gt=0)
    bonus: Optional[float] = 0.0
    advance_deduction: Optional[float] = 0.0
    payment_mode: Optional[str] = "bank"  # bank | cash | upi
    reference_no: Optional[str] = ""
    notes: Optional[str] = ""


# ── 1. STAFF MASTER ──────────────────────────────────────────────────────────

@staff_payroll_router.get("/employees")
async def list_staff_employees(request: Request, active_only: bool = False):
    await _get_user(request)
    db = _get_db(request)
    q = {"is_active": True} if active_only else {}
    docs = await db.staff_employees.find(q).sort("name", 1).to_list(500)
    return [stringify(d) for d in docs]


@staff_payroll_router.post("/employees")
async def create_staff_employee(payload: StaffEmployeeIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    doc = payload.model_dump()
    doc["name"] = doc["name"].strip()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    doc["created_by"] = u.get("email", "")
    res = await db.staff_employees.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@staff_payroll_router.put("/employees/{eid}")
async def update_staff_employee(eid: str, payload: StaffEmployeeIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    updates = payload.model_dump()
    updates["name"] = updates["name"].strip()
    updates["updated_at"] = now_iso()
    res = await db.staff_employees.update_one({"_id": oid(eid)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Staff employee not found")
    return stringify(await db.staff_employees.find_one({"_id": oid(eid)}))


@staff_payroll_router.delete("/employees/{eid}")
async def delete_staff_employee(eid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    res = await db.staff_employees.delete_one({"_id": oid(eid)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Staff employee not found")
    return {"ok": True}


# ── 2. HOLIDAY LIST ──────────────────────────────────────────────────────────

@staff_payroll_router.get("/holidays")
async def list_holidays(request: Request, year: Optional[str] = None):
    await _get_user(request)
    db = _get_db(request)
    q = {}
    if year:
        q["holiday_date"] = {"$regex": f"^{year.strip()}"}
    docs = await db.staff_holidays.find(q).sort("holiday_date", 1).to_list(500)
    return [stringify(d) for d in docs]


@staff_payroll_router.post("/holidays")
async def create_holiday(payload: HolidayIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    hdate = payload.holiday_date.strip()[:10]
    existing = await db.staff_holidays.find_one({"holiday_date": hdate})
    if existing:
        await db.staff_holidays.update_one(
            {"_id": existing["_id"]},
            {"$set": {"name": payload.name.strip(), "holiday_type": payload.holiday_type or "Public Holiday", "updated_at": now_iso()}},
        )
        return stringify(await db.staff_holidays.find_one({"_id": existing["_id"]}))
    doc = {
        "holiday_date": hdate,
        "name": payload.name.strip(),
        "holiday_type": payload.holiday_type or "Public Holiday",
        "created_at": now_iso(),
        "created_by": u.get("email", ""),
    }
    res = await db.staff_holidays.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@staff_payroll_router.delete("/holidays/{hid}")
async def delete_holiday(hid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    res = await db.staff_holidays.delete_one({"_id": oid(hid)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Holiday not found")
    return {"ok": True}


# ── 3. ATTENDANCE REGISTER ───────────────────────────────────────────────────

@staff_payroll_router.get("/attendance")
async def get_monthly_attendance(request: Request, month: str = Query(..., description="YYYY-MM")):
    await _get_user(request)
    db = _get_db(request)
    docs = await db.staff_attendance.find({"date": {"$regex": f"^{month.strip()}"}}).to_list(10000)
    return [stringify(d) for d in docs]


@staff_payroll_router.post("/attendance")
async def mark_attendance(payload: AttendanceMarkIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    att_date = payload.date.strip()[:10]
    valid_statuses = {"present", "absent", "half_day", "paid_leave", "holiday", "week_off"}
    st = payload.status.strip().lower()
    if st not in valid_statuses:
        raise HTTPException(400, f"Invalid attendance status '{st}'. Must be one of {sorted(valid_statuses)}")

    await db.staff_attendance.update_one(
        {"staff_id": payload.staff_id, "date": att_date},
        {
            "$set": {
                "staff_id": payload.staff_id,
                "date": att_date,
                "status": st,
                "overtime_hours": float(payload.overtime_hours or 0.0),
                "notes": payload.notes or "",
                "updated_at": now_iso(),
                "marked_by": u.get("email", ""),
            }
        },
        upsert=True,
    )
    doc = await db.staff_attendance.find_one({"staff_id": payload.staff_id, "date": att_date})
    return stringify(doc)


@staff_payroll_router.post("/attendance/bulk")
async def mark_bulk_attendance(payload: BulkAttendanceIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    att_date = payload.date.strip()[:10]
    st = payload.status.strip().lower()

    if payload.staff_ids:
        target_ids = payload.staff_ids
    else:
        emps = await db.staff_employees.find({"is_active": True}, {"_id": 1}).to_list(500)
        target_ids = [str(e["_id"]) for e in emps]

    for sid in target_ids:
        await db.staff_attendance.update_one(
            {"staff_id": sid, "date": att_date},
            {
                "$set": {
                    "staff_id": sid,
                    "date": att_date,
                    "status": st,
                    "updated_at": now_iso(),
                    "marked_by": u.get("email", ""),
                }
            },
            upsert=True,
        )
    return {"ok": True, "updated_count": len(target_ids), "date": att_date, "status": st}


# ── 4. MONTHLY SALARY CALCULATION & LEDGER ───────────────────────────────────

@staff_payroll_router.get("/monthly-summary")
async def get_monthly_salary_summary(request: Request, month: str = Query(..., description="YYYY-MM")):
    """Calculate attendance, LOP deductions, holidays, overtime & net salary for all salaried staff."""
    await _get_user(request)
    db = _get_db(request)

    try:
        yr, mo = map(int, month.strip().split("-"))
        days_in_month = calendar.monthrange(yr, mo)[1]
    except Exception:
        raise HTTPException(400, "Invalid month format. Expected YYYY-MM.")

    month_start = date(yr, mo, 1)
    month_end = date(yr, mo, days_in_month)
    month_start_str = month_start.isoformat()

    employees = await db.staff_employees.find({
        "$or": [
            {"is_active": True},
            {"relieving_date": {"$gte": month_start_str}},
        ]
    }).sort("name", 1).to_list(500)
    holidays = await db.staff_holidays.find({"holiday_date": {"$regex": f"^{month.strip()}"}}).to_list(100)
    holiday_dates = {h["holiday_date"] for h in holidays}

    # Count Sundays in month as default week-offs
    sundays = {
        f"{yr:04d}-{mo:02d}-{d:02d}"
        for d in range(1, days_in_month + 1)
        if date(yr, mo, d).weekday() == 6
    }

    att_docs = await db.staff_attendance.find({"date": {"$regex": f"^{month.strip()}"}}).to_list(10000)
    att_by_staff: Dict[str, Dict[str, dict]] = {}
    for a in att_docs:
        att_by_staff.setdefault(a["staff_id"], {})[a["date"]] = a

    pay_docs = await db.staff_salary_payments.find({"month": month.strip()}).to_list(2000)
    payments_by_staff: Dict[str, List[dict]] = {}
    for p in pay_docs:
        payments_by_staff.setdefault(p["staff_id"], []).append(p)

    rows = []
    for emp in employees:
        eid = str(emp["_id"])
        base_salary = float(emp.get("monthly_salary") or 0.0)
        emp_att = att_by_staff.get(eid, {})

        doj_str = (emp.get("joining_date") or "").strip()[:10]
        dor_str = (emp.get("relieving_date") or "").strip()[:10]
        eff_start = month_start
        eff_end = month_end
        if doj_str:
            try:
                doj_dt = date.fromisoformat(doj_str)
                if doj_dt > eff_start:
                    eff_start = doj_dt
            except ValueError:
                pass
        if dor_str:
            try:
                dor_dt = date.fromisoformat(dor_str)
                if dor_dt < eff_end:
                    eff_end = dor_dt
            except ValueError:
                pass

        if eff_end < eff_start:
            employed_days = 0
            pro_rata_salary = 0.0
        else:
            employed_days = (eff_end - eff_start).days + 1
            pro_rata_salary = base_salary if employed_days >= days_in_month else round((base_salary / days_in_month) * employed_days, 2)

        present_days = 0
        half_days = 0
        absent_days = 0
        paid_leave_days = 0
        holiday_days = 0
        week_off_days = 0
        overtime_hours = 0.0

        for d in range(1, days_in_month + 1):
            cur_dt = date(yr, mo, d)
            if cur_dt < eff_start or cur_dt > eff_end:
                continue
            d_str = f"{yr:04d}-{mo:02d}-{d:02d}"
            rec = emp_att.get(d_str)
            if rec:
                st = rec.get("status", "present")
                overtime_hours += float(rec.get("overtime_hours") or 0.0)
            elif d_str in holiday_dates:
                st = "holiday"
            elif d_str in sundays:
                st = "week_off"
            else:
                st = "unmarked"

            if st == "present":
                present_days += 1
            elif st == "half_day":
                half_days += 1
            elif st == "absent":
                absent_days += 1
            elif st == "paid_leave":
                paid_leave_days += 1
            elif st == "holiday":
                holiday_days += 1
            elif st == "week_off":
                week_off_days += 1

        lop_days = absent_days + (half_days * 0.5)
        per_day_rate = base_salary / days_in_month if days_in_month > 0 else 0.0
        lop_deduction = round(per_day_rate * lop_days, 2)
        hourly_rate = per_day_rate / 8.0
        overtime_pay = round(overtime_hours * hourly_rate, 2)

        emp_payments = payments_by_staff.get(eid, [])
        bonus_total = round(sum(float(p.get("bonus") or 0.0) for p in emp_payments), 2)
        adv_deduction = round(sum(float(p.get("advance_deduction") or 0.0) for p in emp_payments), 2)
        paid_amount = round(sum(float(p.get("amount") or 0.0) for p in emp_payments), 2)

        net_payable = max(0.0, round(pro_rata_salary - lop_deduction + overtime_pay + bonus_total - adv_deduction, 2))
        balance_due = max(0.0, round(net_payable - paid_amount, 2))

        rows.append({
            "staff_id": eid,
            "name": emp.get("name"),
            "role": emp.get("role"),
            "department": emp.get("department", "Operations"),
            "phone": emp.get("phone", ""),
            "joining_date": doj_str,
            "relieving_date": dor_str,
            "employed_days": employed_days,
            "monthly_salary": base_salary,
            "pro_rata_salary": pro_rata_salary,
            "days_in_month": days_in_month,
            "present_days": present_days,
            "half_days": half_days,
            "paid_leave_days": paid_leave_days,
            "holiday_days": holiday_days,
            "week_off_days": week_off_days,
            "absent_days": absent_days,
            "lop_days": lop_days,
            "lop_deduction": lop_deduction,
            "overtime_hours": overtime_hours,
            "overtime_pay": overtime_pay,
            "bonus": bonus_total,
            "advance_deduction": adv_deduction,
            "net_payable": net_payable,
            "paid_amount": paid_amount,
            "balance_due": balance_due,
            "status": "paid" if balance_due <= 0.01 and net_payable > 0 else ("partial" if paid_amount > 0 else "unpaid"),
        })

    return {
        "month": month.strip(),
        "days_in_month": days_in_month,
        "holidays_count": len(holidays),
        "sundays_count": len(sundays),
        "rows": rows,
        "totals": {
            "total_gross": round(sum(r["monthly_salary"] for r in rows), 2),
            "total_deductions": round(sum(r["lop_deduction"] + r["advance_deduction"] for r in rows), 2),
            "total_net_payable": round(sum(r["net_payable"] for r in rows), 2),
            "total_paid": round(sum(r["paid_amount"] for r in rows), 2),
            "total_balance_due": round(sum(r["balance_due"] for r in rows), 2),
        },
    }


@staff_payroll_router.post("/pay")
async def record_staff_salary_payment(payload: SalaryPaymentIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    emp = await db.staff_employees.find_one({"_id": oid(payload.staff_id)})
    if not emp:
        raise HTTPException(404, "Staff employee not found")

    now = now_iso()
    pay_doc = {
        "staff_id": payload.staff_id,
        "staff_name": emp.get("name"),
        "month": payload.month.strip(),
        "amount": round(float(payload.amount), 2),
        "bonus": round(float(payload.bonus or 0.0), 2),
        "advance_deduction": round(float(payload.advance_deduction or 0.0), 2),
        "payment_mode": payload.payment_mode or "bank",
        "reference_no": payload.reference_no or "",
        "notes": payload.notes or "",
        "paid_at": now,
        "paid_by": u.get("email", ""),
    }
    res = await db.staff_salary_payments.insert_one(pay_doc)
    pay_doc["id"] = str(res.inserted_id)
    pay_doc.pop("_id", None)

    # Also record in expenses ledger
    try:
        await db.expenses.insert_one({
            "date": now[:10],
            "category": "Monthly Staff Salary",
            "amount": pay_doc["amount"],
            "description": f"Salary ({payload.month}) - {emp.get('name')} ({emp.get('role')})",
            "payment_mode": pay_doc["payment_mode"],
            "reference": pay_doc["reference_no"],
            "staff_id": payload.staff_id,
            "created_at": now,
            "created_by": u.get("email", ""),
        })
    except Exception:
        pass

    return {"ok": True, "payment": pay_doc}


@staff_payroll_router.get("/employees/{eid}/ledger")
async def get_staff_ledger(eid: str, request: Request):
    """Chronological salary & payment ledger for a monthly salaried staff member."""
    await _get_user(request)
    db = _get_db(request)
    emp = await db.staff_employees.find_one({"_id": oid(eid)})
    if not emp:
        raise HTTPException(404, "Staff employee not found")

    payments = await db.staff_salary_payments.find({"staff_id": eid}).sort("paid_at", -1).to_list(200)
    return {
        "employee": stringify(emp),
        "payments": [stringify(p) for p in payments],
        "total_paid": round(sum(float(p.get("amount") or 0.0) for p in payments), 2),
    }
