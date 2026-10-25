"""Gmail Extractor and Parsing Engine for SSK Footcare ERP.

Classifies incoming emails into:
- GRN (Goods Receipt Notes / Delivery Receipts / Acceptance)
- PAYMENT (Client remittance / Bank credit alerts: NEFT/RTGS/IMPS/UTR/Cheque)
- OTHER (Irrelevant)

Extracts structured metadata (amounts, dates, references, line items, POs, invoices)
and matches them against MongoDB open invoices, POs, clients, and bank accounts.
"""

import io
import re
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

log = logging.getLogger("gmail_extractor_service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("₹", "").replace("Rs.", "").replace("INR", "").strip()
    try:
        return float(s)
    except Exception:
        return default


def extract_text_from_attachments(attachments: List[Dict[str, Any]]) -> str:
    """Extract plain text from PDF, CSV, Excel, or text attachments."""
    extracted_chunks = []

    for att in attachments:
        fname = (att.get("filename") or "").lower()
        data = att.get("data_bytes")
        if not data:
            continue

        # 1. PDF Attachment
        if fname.endswith(".pdf") or "pdf" in (att.get("mime_type") or "").lower():
            try:
                import pypdf
                pdf_reader = pypdf.PdfReader(io.BytesIO(data))
                pdf_pages = []
                for page in pdf_reader.pages:
                    txt = page.extract_text() or ""
                    if txt.strip():
                        pdf_pages.append(txt.strip())
                if pdf_pages:
                    extracted_chunks.append(f"--- ATTACHMENT PDF: {att.get('filename')} ---\n" + "\n".join(pdf_pages))
            except Exception as pe:
                log.warning("Could not extract text from PDF attachment %s: %s", fname, pe)

        # 2. Excel Attachment
        elif fname.endswith(".xlsx") or fname.endswith(".xls"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
                wb_lines = []
                for sheet in wb.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        row_vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if row_vals:
                            wb_lines.append(" | ".join(row_vals))
                if wb_lines:
                    extracted_chunks.append(f"--- ATTACHMENT EXCEL: {att.get('filename')} ---\n" + "\n".join(wb_lines[:200]))
            except Exception as ee:
                log.warning("Could not extract text from Excel attachment %s: %s", fname, ee)

        # 3. CSV / Plain Text
        elif fname.endswith(".csv") or fname.endswith(".txt"):
            try:
                text_content = data.decode("utf-8", errors="replace")
                extracted_chunks.append(f"--- ATTACHMENT TEXT: {att.get('filename')} ---\n" + text_content[:5000])
            except Exception as te:
                log.warning("Could not extract plain text attachment %s: %s", fname, te)

    return "\n\n".join(extracted_chunks).strip()


def classify_email(subject: str, body_text: str, sender: str, attachment_text: str = "") -> Dict[str, Any]:
    """Classify the incoming email into GRN, PAYMENT, or OTHER with a confidence score."""
    combined = f"{subject}\n{body_text}\n{attachment_text}".lower()

    # GRN Signals
    grn_score = 0
    grn_cues = []
    if re.search(r"\b(grn|goods receipt|delivery receipt|receiving voucher|goods acceptance|delivery acceptance|material receipt|goods received)\b", subject, re.I):
        grn_score += 55
        grn_cues.append("Subject contains explicit GRN/Goods Receipt keyword")
    elif re.search(r"\b(grn|goods receipt|delivery receipt|receiving voucher|goods acceptance|delivery acceptance|material receipt|goods received)\b", combined, re.I):
        grn_score += 40
        grn_cues.append("Body or attachment contains GRN terms")

    if re.search(r"\b(accepted\s+\d+|rejected\s+\d+|\d+\s+pairs\s+(?:accepted|rejected)|accepted\s*qty|received\s*qty|accepted\s*pairs|dispatched\s*qty|rejected\s*qty|inspection\s*report|goods\s*receipt\s*confirmation|pairs\s*dispatched)\b", combined, re.I):
        grn_score += 30
        grn_cues.append("Found line-level receiving/acceptance breakdown")

    if re.search(r"\b(po\s*#?|purchase order|challan\s*#?|invoice\s*#?)\b", combined, re.I):
        grn_score += 15

    # Payment Signals
    pay_score = 0
    pay_cues = []
    is_credit = False
    is_debit = False

    if re.search(r"\b(credited to|has been credited|received payment|payment received|remittance advice|credit alert)\b", combined, re.I):
        pay_score += 45
        is_credit = True
        pay_cues.append("Found credit alert / payment received phrasing")
    elif re.search(r"\b(debited from|payment sent|vendor payment|debit alert)\b", combined, re.I):
        pay_score += 40
        is_debit = True
        pay_cues.append("Found debit alert / payment sent phrasing")

    if re.search(r"\b(neft|rtgs|imps|utr\s*#?|utr\s*no|transaction id|cheque\s*#?|chq\s*no)\b", combined, re.I):
        pay_score += 30
        pay_cues.append("Found banking transfer reference keywords (NEFT/RTGS/IMPS/UTR)")

    if re.search(r"\b(inr|rs\.?|₹)\s*[\d,]+(\.\d{1,2})?\b", combined, re.I) or re.search(r"\bamt\b|\bamount\b", combined, re.I):
        pay_score += 20
        pay_cues.append("Found monetary amount")

    # Decision
    if grn_score >= 35 and grn_score > pay_score:
        confidence = min(0.98, max(0.40, grn_score / 100.0))
        return {
            "category": "GRN",
            "sub_type": "GOODS_RECEIPT",
            "confidence": round(confidence, 2),
            "reasons": grn_cues,
        }
    elif pay_score >= 35:
        sub_type = "CLIENT_PAYMENT" if (is_credit or not is_debit) else "VENDOR_PAYMENT"
        confidence = min(0.98, max(0.40, pay_score / 100.0))
        return {
            "category": "PAYMENT",
            "sub_type": sub_type,
            "confidence": round(confidence, 2),
            "reasons": pay_cues,
        }

    else:
        return {
            "category": "OTHER",
            "sub_type": "UNKNOWN",
            "confidence": 0.20,
            "reasons": ["Insufficient matching keywords for automated GRN or payment processing"],
        }


def extract_grn_data(subject: str, body_text: str, sender: str, attachment_text: str = "") -> Dict[str, Any]:
    """Extract GRN fields: invoice reference, PO number, client, line items, and quantities."""
    full_text = f"{subject}\n{body_text}\n{attachment_text}"
    data: Dict[str, Any] = {
        "invoice_no": "",
        "po_number": "",
        "client_reference": "",
        "grn_no": "",
        "grn_date": "",
        "received_date": "",
        "client_name": "",
        "total_dispatched": 0,
        "total_received": 0,
        "total_accepted": 0,
        "total_rejected": 0,
        "line_items": [],
        "notes": "",
    }

    # 1. Invoice Number Extraction
    inv_match = re.search(r"\b(?:invoice\s*(?:no\.?|#|num)?\s*[:\-]?\s*)([A-Z0-9\-_/]+)\b", full_text, re.I)
    if inv_match:
        data["invoice_no"] = inv_match.group(1).strip()
    else:
        # Fallback check standard SSK invoice patterns: INV-YYYY-XXX or similar
        inv_cand = re.search(r"\b(INV[A-Z0-9\-_/]{4,20})\b", full_text, re.I)
        if inv_cand:
            data["invoice_no"] = inv_cand.group(1).strip()

    # 2. PO Number Extraction
    po_match = re.search(r"\b(?:po\s*(?:no\.?|#|num)?\s*[:\-]?\s*|purchase\s*order\s*[:\-]?\s*)([A-Z0-9\-_/]+)\b", full_text, re.I)
    if po_match:
        data["po_number"] = po_match.group(1).strip()
    else:
        # Match Reliance / Bata / Metro style 10-digit PO numbers (e.g. 2220012750 or 4500012345)
        po_cand = re.search(r"\b(222\d{7}|450\d{7}|PO\d{4,8})\b", full_text)
        if po_cand:
            data["po_number"] = po_cand.group(1).strip()

    # 3. GRN / Challan Reference
    grn_m = re.search(r"\b(?:grn\s*(?:no\.?|#|num)?\s*[:\-]?\s*|receipt\s*(?:no\.?|#)?\s*[:\-]?\s*)([A-Z0-9\-_/]+)\b", full_text, re.I)
    if grn_m:
        data["client_reference"] = grn_m.group(1).strip()
    else:
        dc_m = re.search(r"\b(?:challan\s*(?:no\.?|#)?\s*[:\-]?\s*)([A-Z0-9\-_/]+)\b", full_text, re.I)
        if dc_m:
            data["client_reference"] = dc_m.group(1).strip()

    # 4. Date Extraction (YYYY-MM-DD or DD/MM/YYYY)
    date_m = re.search(r"\b(?:date|grn\s*date|received\s*on)\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})\b", full_text, re.I)
    if date_m:
        raw_d = date_m.group(1).strip().replace("/", "-")
        # Normalize to YYYY-MM-DD
        parts = raw_d.split("-")
        if len(parts) == 3:
            if len(parts[0]) == 4:
                data["received_date"] = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            elif len(parts[2]) == 4:
                data["received_date"] = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
    if not data["received_date"]:
        data["received_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data["grn_date"] = data["received_date"]

    # 5. Total Quantities
    recv_m = re.search(r"\b(?:received|total\s*received|recv)\s*[:\-]?\s*(\d+)\s*(?:prs|pairs|pcs)?\b", full_text, re.I)
    acc_m = re.search(r"\b(?:accepted|total\s*accepted|acc)\s*[:\-]?\s*(\d+)\s*(?:prs|pairs|pcs)?\b", full_text, re.I)
    rej_m = re.search(r"\b(?:rejected|total\s*rejected|rej|shortage)\s*[:\-]?\s*(\d+)\s*(?:prs|pairs|pcs)?\b", full_text, re.I)
    disp_m = re.search(r"\b(?:dispatched|total\s*dispatched|dispatch\s*qty)\s*[:\-]?\s*(\d+)\s*(?:prs|pairs|pcs)?\b", full_text, re.I)

    if recv_m:
        data["total_received"] = int(recv_m.group(1))
    if acc_m:
        data["total_accepted"] = int(acc_m.group(1))
    if rej_m:
        data["total_rejected"] = int(rej_m.group(1))
    if disp_m:
        data["total_dispatched"] = int(disp_m.group(1))

    # Auto-balance quantities if one is missing
    if data["total_received"] > 0 and data["total_accepted"] == 0 and data["total_rejected"] == 0:
        data["total_accepted"] = data["total_received"]
    elif data["total_accepted"] > 0 and data["total_received"] == 0:
        data["total_received"] = data["total_accepted"] + data["total_rejected"]

    # 6. Detailed Table Line Extraction (size/color/pairs)
    # Match patterns like: "ART-101 | Black | 8 | 120 | 118 | 2"
    line_pattern = re.compile(
        r"(?:([A-Z0-9\-_]+)\s*[\/\|,]\s*)?"
        r"(?:([A-Za-z]+)\s*[\/\|,]\s*)?"
        r"(?:(?:size\s*[:\-]?\s*)?(\d{1,2}|UK\d+|EU\d+)\s*[\/\|,]\s*)?"
        r"(\d+)\s*[\/\|,]\s*(\d+)"
        r"(?:\s*[\/\|,]\s*(\d+))?",
        re.I
    )
    for m in line_pattern.finditer(attachment_text or body_text):
        sc, col, sz, q1, q2, q3 = m.groups()
        if int(q1 or 0) > 0:
            disp_qty = int(q1)
            recv_qty = int(q2 or q1)
            rej_qty = int(q3 or 0)
            data["line_items"].append({
                "style_code": sc or "",
                "color": col or "",
                "size": sz or "",
                "dispatched_qty": disp_qty,
                "received_qty": recv_qty,
                "accepted_qty": max(0, recv_qty - rej_qty),
                "rejected_qty": rej_qty,
                "rejection_reason": "Damaged/Defective" if rej_qty > 0 else None,
            })

    data["notes"] = f"Auto-extracted from email: {subject[:100]}"
    return data


def extract_payment_data(subject: str, body_text: str, sender: str, attachment_text: str = "") -> Dict[str, Any]:
    """Extract payment fields: amount, UTR/reference, mode, payment date, payer/client name, invoices."""
    full_text = f"{subject}\n{body_text}\n{attachment_text}"
    data: Dict[str, Any] = {
        "amount": 0.0,
        "payment_date": "",
        "mode": "Bank Transfer",
        "reference": "",
        "bank": "",
        "bank_account_last4": "",
        "client_name": "",
        "invoice_numbers": [],
        "notes": "",
    }

    # 1. Amount Extraction
    # Match formats like: "INR 1,50,000.00", "₹ 75000", "Rs. 25,400.50", "Amount: 18000.00", "Credited with INR 4,20,000"
    amt_matches = re.findall(
        r"(?:(?:INR|Rs\.?|₹|amt|amount|credited\s*with)\s*[:\-]?\s*)([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\b",
        full_text,
        re.I,
    )
    if amt_matches:
        # Pick the largest reasonable non-zero amount
        parsed_amounts = [_safe_float(a) for a in amt_matches if _safe_float(a) > 0]
        if parsed_amounts:
            data["amount"] = parsed_amounts[0]

    # Fallback amount regex: Any currency symbol followed by numbers
    if data["amount"] <= 0:
        fallback_amt = re.search(r"[₹Rs\.INR]+\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)", full_text)
        if fallback_amt:
            data["amount"] = _safe_float(fallback_amt.group(1))

    # 2. UTR / Transaction Reference Extraction
    utr_m = re.search(
        r"\b(?:utr\s*(?:no\.?|#|num)?\s*[:\-]?\s*|ref\s*(?:no\.?|#)?\s*[:\-]?\s*|txn\s*(?:id|no)?\s*[:\-]?\s*|transaction\s*id\s*[:\-]?\s*)([A-Z0-9\-_/]{8,35})\b",
        full_text,
        re.I,
    )
    if utr_m:
        data["reference"] = utr_m.group(1).strip()
    else:
        # Check standard Indian bank UTR patterns (e.g. HDFCR520261025..., ICIC000..., SBIN..., CMS...)
        bank_utr = re.search(r"\b([A-Z]{4}[RCNP0-9][0-9]{10,25}|CMS[0-9]{8,15})\b", full_text)
        if bank_utr:
            data["reference"] = bank_utr.group(1).strip()

    # Cheque number check
    chq_m = re.search(r"\b(?:cheque|chq)\s*(?:no\.?|#)?\s*[:\-]?\s*(\d{6})\b", full_text, re.I)
    if chq_m:
        data["reference"] = f"CHQ-{chq_m.group(1)}"
        data["mode"] = "Cheque"

    # 3. Mode Extraction
    if "neft" in full_text.lower():
        data["mode"] = "NEFT"
    elif "rtgs" in full_text.lower():
        data["mode"] = "RTGS"
    elif "imps" in full_text.lower():
        data["mode"] = "IMPS"
    elif "upi" in full_text.lower():
        data["mode"] = "UPI"
    elif "cheque" in full_text.lower() or "chq" in full_text.lower():
        data["mode"] = "Cheque"
    else:
        data["mode"] = "Bank Transfer"

    # 4. Bank and Account Identification
    bank_m = re.search(r"\b(hdfc\s*bank|icici\s*bank|state\s*bank\s*of\s*india|sbi|axis\s*bank|kotak\s*bank|yes\s*bank|punjab\s*national\s*bank|pnb)\b", full_text, re.I)
    if bank_m:
        data["bank"] = bank_m.group(1).strip().upper()

    ac_m = re.search(r"\b(?:a\/c|account)\s*(?:no\.?|#)?\s*(?:ending\s*(?:with|in)?\s*)?[xX*]*([0-9]{4})\b", full_text, re.I)
    if ac_m:
        data["bank_account_last4"] = ac_m.group(1)

    # 5. Date Extraction
    date_m = re.search(r"\b(?:on\s*date|dated|value\s*date|payment\s*date|txn\s*date)\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})\b", full_text, re.I)
    if date_m:
        raw_d = date_m.group(1).strip().replace("/", "-")
        parts = raw_d.split("-")
        if len(parts) == 3:
            if len(parts[0]) == 4:
                data["payment_date"] = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            elif len(parts[2]) == 4:
                data["payment_date"] = f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
    if not data["payment_date"]:
        data["payment_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 6. Referenced Invoices
    inv_list = re.findall(r"\b(INV[-_/]?[A-Z0-9\-_/]{3,20})\b", full_text, re.I)
    for raw_inv in inv_list:
        raw_inv = raw_inv.strip().strip(",").strip(".").strip(";")
        if raw_inv and raw_inv.upper() not in [x.upper() for x in data["invoice_numbers"]]:
            data["invoice_numbers"].append(raw_inv)


    data["notes"] = f"Auto-extracted payment alert from: {subject[:100]}"
    return data


async def match_with_erp(item_category: str, extracted: Dict[str, Any], db) -> Dict[str, Any]:
    """Cross-reference extracted entities with ERP collections (invoices, POs, clients, bank_accounts)."""
    match_result = {
        "is_matched": False,
        "match_confidence": 0.0,
        "matched_invoice": None,
        "matched_client": None,
        "matched_bank_account": None,
        "suggested_action": "",
        "suggested_allocations": {},
        "notes": "",
    }

    if db is None:
        return match_result

    # ─────────────────────────────────────────────────────────────
    # GRN MATCHING LOGIC
    # ─────────────────────────────────────────────────────────────
    if item_category == "GRN":
        inv_no = extracted.get("invoice_no")
        po_no = extracted.get("po_number")
        client_ref = extracted.get("client_reference")

        query_or = []
        if inv_no:
            query_or.append({"invoice_no": {"$regex": f"^{re.escape(inv_no)}$", "$options": "i"}})
            query_or.append({"invoice_no": {"$regex": re.escape(inv_no), "$options": "i"}})
        if po_no:
            query_or.append({"po_number": {"$regex": f"^{re.escape(po_no)}$", "$options": "i"}})
        if client_ref:
            query_or.append({"invoice_no": {"$regex": re.escape(client_ref), "$options": "i"}})

        inv = None
        if query_or:
            inv = await db.invoices.find_one({"$or": query_or})

        if inv:
            match_result["is_matched"] = True
            match_result["matched_invoice"] = {
                "id": str(inv["_id"]),
                "invoice_no": inv.get("invoice_no"),
                "po_number": inv.get("po_number"),
                "client_name": inv.get("client_name"),
                "grand_total": inv.get("grand_total"),
                "total_pairs": inv.get("total_pairs") or inv.get("total_quantity"),
                "invoice_date": inv.get("invoice_date"),
                "status": inv.get("status"),
            }
            # High confidence if invoice number matched exactly
            if inv_no and inv.get("invoice_no", "").lower() == inv_no.lower():
                match_result["match_confidence"] = 0.95
            elif po_no and inv.get("po_number", "").lower() == po_no.lower():
                match_result["match_confidence"] = 0.85
            else:
                match_result["match_confidence"] = 0.70

            match_result["suggested_action"] = "create_grn"
            match_result["notes"] = f"Matched to Invoice {inv.get('invoice_no')} ({inv.get('client_name')})"

            # If line items weren't parsed from email, pre-fill them from invoice dispatch lines!
            if not extracted.get("line_items") and inv.get("line_items"):
                total_recv = extracted.get("total_received") or 0
                total_disp_inv = sum(int(li.get("quantity") or li.get("dispatched_qty") or 0) for li in inv.get("line_items", []))

                populated_lines = []
                for li in inv.get("line_items", []):
                    d_qty = int(li.get("quantity") or li.get("dispatched_qty") or 0)
                    r_qty = d_qty if (total_recv == 0 or total_recv >= total_disp_inv) else int(round(d_qty * (total_recv / max(1, total_disp_inv))))
                    populated_lines.append({
                        "style_code": li.get("style_code") or "",
                        "color": li.get("color") or "",
                        "size": str(li.get("size") or ""),
                        "dispatched_qty": d_qty,
                        "received_qty": r_qty,
                        "accepted_qty": r_qty,
                        "rejected_qty": 0,
                        "rejection_reason": None,
                    })
                extracted["line_items"] = populated_lines
                if extracted.get("total_dispatched", 0) == 0:
                    extracted["total_dispatched"] = total_disp_inv
                if extracted.get("total_received", 0) == 0:
                    extracted["total_received"] = sum(l["received_qty"] for l in populated_lines)
                    extracted["total_accepted"] = extracted["total_received"]

    # ─────────────────────────────────────────────────────────────
    # PAYMENT MATCHING LOGIC
    # ─────────────────────────────────────────────────────────────
    elif item_category == "PAYMENT":
        amount = extracted.get("amount") or 0.0
        inv_numbers = extracted.get("invoice_numbers") or []
        client_name = extracted.get("client_name") or ""
        bank_last4 = extracted.get("bank_account_last4") or ""

        # 1. Match company receiving bank account
        if bank_last4:
            ba = await db.bank_accounts.find_one({"account_number": {"$regex": f"{re.escape(bank_last4)}$"}})
            if ba:
                match_result["matched_bank_account"] = {
                    "id": str(ba["_id"]),
                    "bank_name": ba.get("bank_name") or ba.get("name"),
                    "account_number": ba.get("account_number"),
                    "current_balance": ba.get("current_balance"),
                }

        # 2. Match Invoices
        matched_invs = []
        if inv_numbers:
            for num in inv_numbers:
                inv = await db.invoices.find_one({"invoice_no": {"$regex": re.escape(num), "$options": "i"}})
                if inv and str(inv["_id"]) not in [m["id"] for m in matched_invs]:
                    matched_invs.append({
                        "id": str(inv["_id"]),
                        "invoice_no": inv.get("invoice_no"),
                        "client_name": inv.get("client_name"),
                        "grand_total": inv.get("grand_total"),
                        "net_amount": inv.get("net_amount") or inv.get("grand_total"),
                        "due_date": inv.get("due_date"),
                    })

        # 3. If no direct invoice match, match by client name and find open invoices
        if not matched_invs and client_name:
            client_doc = await db.clients.find_one({"name": {"$regex": re.escape(client_name), "$options": "i"}})
            if client_doc:
                match_result["matched_client"] = {"id": str(client_doc["_id"]), "name": client_doc.get("name")}
                # Find unpaid invoices for this client
                unpaid = await db.invoices.find({
                    "client_name": {"$regex": f"^{re.escape(client_doc.get('name'))}$", "$options": "i"},
                    "status": {"$in": ["PENDING", "PARTIALLY_PAID", "OVERDUE", "SUBMITTED", "APPROVED"]}
                }).to_list(10)
                for inv in unpaid:
                    matched_invs.append({
                        "id": str(inv["_id"]),
                        "invoice_no": inv.get("invoice_no"),
                        "client_name": inv.get("client_name"),
                        "grand_total": inv.get("grand_total"),
                        "net_amount": inv.get("net_amount") or inv.get("grand_total"),
                        "due_date": inv.get("due_date"),
                    })

        # Compute allocations if we have matched invoices and positive amount
        if matched_invs and amount > 0:
            match_result["is_matched"] = True
            match_result["suggested_action"] = "record_client_payment"
            rem = amount
            allocations = {}
            for inv in matched_invs:
                inv_total = float(inv.get("net_amount") or inv.get("grand_total") or 0.0)
                take = round(min(rem, inv_total), 2)
                if take > 0:
                    allocations[inv["id"]] = take
                    rem = round(rem - take, 2)
                if rem <= 0:
                    break

            match_result["suggested_allocations"] = allocations
            match_result["matched_invoice"] = matched_invs[0]

            # High confidence if amount matches invoice amount exactly
            if any(abs(float(inv.get("net_amount") or inv.get("grand_total") or 0.0) - amount) < 1.0 for inv in matched_invs):
                match_result["match_confidence"] = 0.95
            elif len(inv_numbers) > 0:
                match_result["match_confidence"] = 0.90
            else:
                match_result["match_confidence"] = 0.75

            inv_tags = ", ".join(inv["invoice_no"] for inv in matched_invs[:3])
            match_result["notes"] = f"Suggested payment allocation of ₹{amount:,.2f} against {inv_tags}"

    return match_result


async def parse_and_match_email(email_dict: Dict[str, Any], db=None) -> Dict[str, Any]:
    """Top-level pipeline: processes an email dictionary into a fully parsed and ERP-matched item."""
    subject = email_dict.get("subject", "")
    body_text = email_dict.get("body_text", "")
    sender = email_dict.get("from_header", "")
    attachments = email_dict.get("attachments", [])

    # 1. Attachment Text Extraction
    attachment_text = extract_text_from_attachments(attachments)

    # 2. Classification
    classification = classify_email(subject, body_text, sender, attachment_text)
    cat = classification["category"]

    extracted_data: Dict[str, Any] = {}
    if cat == "GRN":
        extracted_data = extract_grn_data(subject, body_text, sender, attachment_text)
    elif cat == "PAYMENT":
        extracted_data = extract_payment_data(subject, body_text, sender, attachment_text)

    # 3. Match against ERP Database
    erp_match = await match_with_erp(cat, extracted_data, db=db)

    # 4. Overall Confidence
    base_conf = classification.get("confidence", 0.5)
    match_conf = erp_match.get("match_confidence", 0.0)
    overall_confidence = round(base_conf * 0.4 + match_conf * 0.6 if erp_match.get("is_matched") else base_conf, 2)

    return {
        "message_id": email_dict.get("message_id"),
        "thread_id": email_dict.get("thread_id"),
        "subject": subject,
        "from_header": sender,
        "from_email": email_dict.get("from_email", ""),
        "sender_name": email_dict.get("sender_name", ""),
        "received_iso": email_dict.get("received_iso") or now_iso(),
        "snippet": email_dict.get("snippet", ""),
        "category": cat,
        "sub_type": classification.get("sub_type", "UNKNOWN"),
        "confidence": overall_confidence,
        "reasons": classification.get("reasons", []),
        "extracted_data": extracted_data,
        "erp_match": erp_match,
        "status": "pending_review",  # "pending_review" | "auto_recorded" | "processed" | "dismissed"
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
