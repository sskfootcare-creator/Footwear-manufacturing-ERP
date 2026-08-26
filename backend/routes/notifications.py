"""In-app pickup-ready notifications for production/admin/manager."""

from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from models.notifications import NotificationIn
from auth import require_roles

notifications_router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(400, "Invalid object ID format")


async def _get_user(request: Request):
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    db = getattr(request.app, "mongodb", None) or server.db
    fn = await get_current_user_factory(db)
    return await fn(request)


@notifications_router.get("")
@notifications_router.get("/")
async def list_notifications(request: Request, unread_only: bool = True):
    """List pickup-ready notifications (admin/manager/production only), newest first."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {"type": "pickup_ready"}
    if unread_only:
        q["read"] = False
    notifs = await db.notifications.find(q).sort("at", -1).to_list(200)
    return [stringify(n) for n in notifs]


@notifications_router.patch("/{nid}/read")
async def mark_notification_read(nid: str, request: Request):
    """Mark a pickup-ready notification as read (admin/manager/production only)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    now = now_iso()
    result = await db.notifications.update_one(
        {"_id": oid(nid)},
        {"$set": {"read": True, "read_by": u.get("email") or u.get("name", ""), "read_at": now}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}
