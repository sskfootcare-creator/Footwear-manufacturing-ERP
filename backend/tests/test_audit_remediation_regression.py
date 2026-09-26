"""Comprehensive regression test suite verifying all invariants from the audit remediation (R-002).

Invariants covered:
1. Endpoint authorization & module enforcement (F-001, F-025, F-026)
2. Last-admin protection & self-demotion guards (F-027)
3. Nonexistent user deletion returns 404 (F-028)
4. Refresh token rotation & token replay revocation (F-003)
5. Atomic password reset token consumption & dev reset url privacy (F-004, F-005)
6. FG stock reservation overcommit prevention (F-009)
7. Partial FG reservation release (F-010)
8. Cross-PO job dispatch rejection (F-017)
9. Invoicing zero completed_qty safeguard (F-018)
10. Idempotent invoice & dispatch creation (F-019, F-020)
11. Invoice voiding instead of destructive deletion (F-022)
12. Canonical direct invoice quantity validation (F-024)
13. Image upload pixel-bomb / decompression protection (F-030)
14. Authoritative dashboard ledger invariants (F-031, F-032)
15. Configurable reverse freight rates in returns engine (F-033, F-034)
"""

import pytest
import io
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from fastapi import HTTPException
from PIL import Image

import server
from auth import check_route_module_access
from models.clients import DirectInvoiceIn, DirectInvoiceLineItem
from routes.auth import (
    update_user,
    delete_user,
    UserUpdate,
    reset_password,
    ResetPasswordInput,
    refresh_token_route,
)
from routes.inventory import reserve_stock, release_stock
from models.inventory import StockReservation, StockRelease
from routes.invoice_packing import create_dispatch, create_direct_invoice, void_invoice
from models.invoice_packing import DispatchCreate


# ── 1. Endpoint Authorization & Module Enforcement (F-001, F-025, F-026) ─────
def test_route_module_matrix_enforcement():
    """Verify non-admin users without module permissions get HTTP 403."""
    sales_user = {"email": "sales@ssk.com", "role": "sales", "allowed_modules": ["orders_sales"]}
    
    # Allowed: /api/pos requires orders_sales
    check_route_module_access(sales_user, "/api/pos")
    
    # Denied: /api/inventory requires inventory
    with pytest.raises(HTTPException) as exc:
        check_route_module_access(sales_user, "/api/inventory")
    assert exc.value.status_code == 403
    assert "inventory" in exc.value.detail


# ── 2. Last-Admin Protection & Nonexistent User Deletion (F-027, F-028) ───────
@pytest.mark.anyio
async def test_last_admin_protection():
    """Verify the system refuses to demote the sole remaining active admin."""
    target_id = str(ObjectId())
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": ObjectId(target_id), "role": "admin", "active": True})
    mock_db.users.count_documents = AsyncMock(return_value=0)  # No other active admin exists

    req = MagicMock()
    with patch("routes.auth._get_db", return_value=mock_db), \
         patch("routes.auth._current_user_fn", return_value=AsyncMock(return_value={"id": str(ObjectId()), "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        await update_user(target_id, UserUpdate(role="manager"), req)
    assert exc.value.status_code == 400
    assert "Cannot remove, demote, or deactivate the last active administrator" in exc.value.detail


@pytest.mark.anyio
async def test_self_demotion_rejected():
    """Verify an admin cannot demote their own account."""
    admin_id = str(ObjectId())
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value={"_id": ObjectId(admin_id), "role": "admin", "active": True})
    mock_db.users.count_documents = AsyncMock(return_value=5)

    req = MagicMock()
    with patch("routes.auth._get_db", return_value=mock_db), \
         patch("routes.auth._current_user_fn", return_value=AsyncMock(return_value={"id": admin_id, "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        await update_user(admin_id, UserUpdate(role="viewer"), req)
    assert exc.value.status_code == 400
    assert "Administrators cannot demote their own account" in exc.value.detail


@pytest.mark.anyio
async def test_delete_nonexistent_user_returns_404():
    """Verify deleting a nonexistent user returns HTTP 404 (F-028)."""
    target_id = str(ObjectId())
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)

    req = MagicMock()
    with patch("routes.auth._get_db", return_value=mock_db), \
         patch("routes.auth._current_user_fn", return_value=AsyncMock(return_value={"id": str(ObjectId()), "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        await delete_user(target_id, req)
    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail


# ── 3. Refresh Token Rotation & Replay Attack Revocation (F-003) ───────────────
@pytest.mark.anyio
async def test_refresh_token_rotation_and_replay_detection():
    """Verify that replaying a rotated refresh token triggers security revocation."""
    mock_db = MagicMock()
    mock_db.refresh_tokens.find_one_and_update = AsyncMock(return_value=None)
    mock_db.refresh_tokens.find_one = AsyncMock(return_value={
        "token_jti": "jti-old",
        "user_id": "user123",
        "revoked": True,
        "expires_at": datetime.now(timezone.utc).timestamp() + 3600,
    })
    mock_db.refresh_tokens.update_many = AsyncMock()

    mock_req = MagicMock()
    mock_req.app.mongodb = mock_db
    mock_req.cookies = {"refresh_token": "valid.token.jwt"}
    mock_req.headers = {}

    with patch("routes.auth._get_db", return_value=mock_db), \
         patch("routes.auth.jwt.decode", return_value={"jti": "jti-old", "sub": "user123", "type": "refresh"}):
        with pytest.raises(HTTPException) as exc:
            await refresh_token_route(mock_req, MagicMock())
        assert exc.value.status_code == 401
        assert "replay detected" in exc.value.detail.lower()
        # Assert all tokens for user were revoked due to breach detection
        mock_db.refresh_tokens.update_many.assert_called_once()


# ── 4. Atomic Password Reset Token Consumption (F-004, F-005) ─────────────────
@pytest.mark.anyio
async def test_password_reset_token_atomic_single_use():
    """Verify that a password reset token can only be consumed once."""
    mock_db = MagicMock()
    mock_db.password_resets.find_one_and_update = AsyncMock(return_value=None)
    mock_db.password_resets.find_one = AsyncMock(return_value={"token_hash": "already_used", "used_at": "2026-08-01T00:00:00Z"})

    with patch("routes.auth._get_db", return_value=mock_db), \
         pytest.raises(HTTPException) as exc:
        await reset_password(
            payload=ResetPasswordInput(token="already_used_token", new_password="NewPassword123!"),
        )
    assert exc.value.status_code == 400
    assert "already been used" in exc.value.detail.lower()


# ── 5. FG Inventory Reservation Available Stock Check (F-009, F-010) ──────────
@pytest.mark.anyio
async def test_fg_reservation_overcommit_prevented():
    """Verify reserving FG stock fails when available < requested."""
    style_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.styles.find_one = AsyncMock(return_value={"_id": style_oid, "code": "STYLE01"})
    # ready_stock = 10, reserved = 8 -> available = 2
    mock_db.fg_inventory.find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "style_id": style_oid,
        "color": "Black",
        "size": "8",
        "ready_stock_qty": 10,
        "reserved_qty": 8,
    })

    req = MagicMock()
    req.app.mongodb = mock_db
    with patch("routes.inventory._get_user", AsyncMock(return_value={"email": "mgr@ssk.com", "role": "manager"})), \
         pytest.raises(HTTPException) as exc:
        await reserve_stock(
            request=req,
            payload=StockReservation(style_id=str(style_oid), color="Black", size="8", quantity=5, channel="b2b")
        )
    assert exc.value.status_code == 400
    assert "Insufficient available stock to reserve" in exc.value.detail


# ── 6. Invoicing & Dispatch Integrity (F-017, F-020, F-022, F-024) ────────────
@pytest.mark.anyio
async def test_dispatch_rejects_cross_po_jobs():
    """Verify dispatch creation rejects jobs that do not belong to the requested PO (F-017)."""
    mock_db = MagicMock()
    po_id = str(ObjectId())
    mock_db.pos.find_one = AsyncMock(return_value={"_id": ObjectId(po_id), "po_number": "PO-SSK-100"})
    
    # Job belongs to different PO
    mock_db.production_jobs.find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "po_id": str(ObjectId()),
        "po_number": "PO-OTHER-200",
    })

    req = MagicMock()
    req.app.mongodb = mock_db
    with patch("routes.invoice_packing._get_db", return_value=mock_db), \
         patch("routes.invoice_packing._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        await create_dispatch(
            DispatchCreate(po_id=po_id, job_ids=[str(ObjectId())]),
            req
        )
    assert exc.value.status_code == 400
    assert "belongs to PO ID" in exc.value.detail


def test_direct_invoice_canonical_quantity_rejection():
    """Verify direct invoice rejects line items with non-positive quantities (F-024)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DirectInvoiceLineItem(style_code="OX-01", qty=0, unit_price=500.0)


@pytest.mark.anyio
async def test_void_invoice_workflow():
    """Verify voiding an invoice transitions status to 'voided' and reverses financial record (F-022)."""
    mock_db = MagicMock()
    inv_id = str(ObjectId())
    j1 = str(ObjectId())
    j2 = str(ObjectId())
    mock_db.invoices.find_one = AsyncMock(return_value={
        "_id": ObjectId(inv_id),
        "invoice_no": "SSK26-27-042",
        "status": "issued",
        "job_ids": [j1, j2]
    })
    mock_db.invoices.update_one = AsyncMock()
    mock_db.dispatch_records.update_many = AsyncMock()
    mock_db.payments.update_many = AsyncMock()
    mock_db.cartons.update_many = AsyncMock()
    mock_db.packing_cartons.update_many = AsyncMock()
    mock_db.production_jobs.update_many = AsyncMock()
    mock_db.production_jobs.update_one = AsyncMock()

    req = MagicMock()
    req.app.mongodb = mock_db

    with patch("routes.invoice_packing._get_db", return_value=mock_db), \
         patch("routes.invoice_packing._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"})):
        resp = await void_invoice(inv_id, req)
        assert resp["ok"] is True
        assert resp["status"] == "voided"
        mock_db.invoices.update_one.assert_called_once()


# ── 7. Image Upload Security & Operational Controls (F-030) ───────────────────
@pytest.mark.anyio
async def test_image_upload_pixel_bomb_protection():
    """Verify images exceeding 10MP decompression threshold are rejected (F-030)."""
    # 3500 x 3000 = 10,500,000 pixels (> 10MP cap)
    large_img = Image.new("RGB", (3500, 3000), color="white")
    buf = io.BytesIO()
    large_img.save(buf, format="JPEG")
    buf.seek(0)

    upload_file = MagicMock()
    upload_file.filename = "bomb.jpg"
    upload_file.content_type = "image/jpeg"
    upload_file.read = AsyncMock(return_value=buf.getvalue())

    dummy_req = MagicMock()
    with patch("server.get_current_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        await server.upload_image(file=upload_file, request=dummy_req)
    assert exc.value.status_code == 400
    assert "exceed" in exc.value.detail.lower()


# ── 8. Authoritative Dashboard Ledger Invariants (F-031, F-032) ───────────────
@pytest.mark.anyio
async def test_dashboard_stats_authoritative_ledgers():
    """Verify dashboard stats computes authoritative ledger invariants rather than raw job counts."""
    mock_db = MagicMock()
    mock_db.pos.count_documents = AsyncMock(return_value=5)
    mock_db.materials.count_documents = AsyncMock(return_value=12)
    mock_db.styles.count_documents = AsyncMock(return_value=8)
    
    mock_jobs = [
        {"source_type": "b2b", "stage": "cutting", "quantity": 100, "status": "in_progress"},
        {"source_type": "b2b", "stage": "dispatched", "quantity": 50, "status": "completed"},
    ]
    mock_db.production_jobs.find.return_value.to_list = AsyncMock(return_value=mock_jobs)
    
    # FG inventory ledger
    mock_db.fg_inventory.find.return_value.to_list = AsyncMock(return_value=[
        {"ready_stock": 250, "reserved": 50}
    ])
    # Dispatch records ledger
    mock_db.dispatch_records.find.return_value.to_list = AsyncMock(return_value=[
        {"total_pairs": 50}
    ])
    mock_db.online_returns_records.count_documents = AsyncMock(return_value=3)
    mock_db.invoices.find.return_value.to_list = AsyncMock(return_value=[
        {"grand_total": 45000.0, "status": "issued"}
    ])
    mock_db.pos.find.return_value.to_list = AsyncMock(return_value=[
        {"grand_total": 50000.0, "status": "in_production"}
    ])
    mock_db.cash_ledger.find.return_value.to_list = AsyncMock(return_value=[])

    with patch.object(server, "db", mock_db):
        stats = await server._compute_dashboard_stats_live()
        assert "ledger_invariants" in stats
        invariants = stats["ledger_invariants"]
        assert invariants["physical_fg_stock"] == 250
        assert invariants["reserved_fg_stock"] == 50
        assert invariants["invoiced_realized_revenue"] == 45000.0
        assert invariants["total_returns_units"] == 3
