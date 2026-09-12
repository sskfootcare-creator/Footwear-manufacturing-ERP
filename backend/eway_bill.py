"""E-Way Bill JSON generation for NIC Bulk Upload (ewaybillgst.gov.in).

Generates a JSON file conforming to the official Government E-Way Bill
Bulk Generation schema (version 1.0.0621).
"""
import json
import re
from typing import Optional

from pdf_docs import COMPANY


# ── Helpers ──────────────────────────────────────────────────────────────

_PIN_RE = re.compile(r"\b([1-9]\d{5})\b")

TRANS_MODE_MAP = {
    "road": 1, "1": 1,
    "rail": 2, "2": 2,
    "air":  3, "3": 3,
    "ship": 4, "4": 4,
}


def extract_pincode(text: str) -> Optional[str]:
    """Extract a 6-digit Indian pincode from free-text address."""
    if not text:
        return None
    m = _PIN_RE.search(text)
    return m.group(1) if m else None


def extract_city(text: str) -> str:
    """Best-effort city extraction from a free-text address blob."""
    if not text:
        return ""
    t = " ".join(text.split())
    parts = [p.strip() for p in t.split(",") if p.strip()]
    if len(parts) >= 2:
        for p in reversed(parts):
            cleaned = re.sub(r"\d{6}", "", p).strip()
            cleaned = re.sub(r"\b(MAHARASHTRA|KARNATAKA|GUJARAT|TAMIL NADU|TELANGANA|ANDHRA PRADESH|"
                             r"RAJASTHAN|UTTAR PRADESH|MADHYA PRADESH|WEST BENGAL|BIHAR|ODISHA|"
                             r"HARYANA|PUNJAB|JHARKHAND|CHHATTISGARH|UTTARAKHAND|GOA|TRIPURA|"
                             r"MEGHALAYA|MANIPUR|NAGALAND|MIZORAM|ARUNACHAL PRADESH|SIKKIM|"
                             r"HIMACHAL PRADESH|ASSAM|KERALA|DELHI|CHANDIGARH|PUDUCHERRY|"
                             r"JAMMU AND KASHMIR|LADAKH|LAKSHADWEEP|ANDAMAN AND NICOBAR|"
                             r"DADRA AND NAGAR HAVELI|DAMAN AND DIU)\b",
                             "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"^[-\s]+|[-\s]+$", "", cleaned)
            if cleaned and len(cleaned) > 1 and not cleaned.isdigit():
                return cleaned.upper()
    fallback = re.sub(r"\d+", "", t).strip()
    first_word = fallback.split()[0] if fallback.split() else ""
    return first_word.upper()


def normalize_vehicle_no(v: str) -> str:
    """Normalise vehicle number: uppercase, remove spaces/dashes."""
    if not v:
        return ""
    return re.sub(r"[\s\-]", "", v).upper()


def map_transport_mode(mode) -> int:
    """Convert free-text or numeric transport mode to NIC numeric code (integer)."""
    if mode is None:
        return 1
    key = str(mode).strip().lower()
    return TRANS_MODE_MAP.get(key, 1)


def _split_address(addr: str, max_len: int = 120) -> tuple:
    """Split address into addr1 (up to max_len) and addr2 (remainder)."""
    if not addr:
        return ("", "")
    addr = " ".join(addr.replace('"', ' ').replace('\n', ' ').split())
    if len(addr) <= max_len:
        return (addr, "")
    split_point = addr.rfind(" ", 0, max_len)
    if split_point == -1:
        split_point = max_len
    return (addr[:split_point].strip(), addr[split_point:].strip()[:max_len])


def normalize_date(d: str) -> str:
    """Normalize date string to DD/MM/YYYY."""
    if not d:
        return ""
    d = str(d).strip()
    if "T" in d:
        d = d.split("T")[0].strip()
    elif " " in d:
        d = d.split(" ")[0].strip()
    if "-" in d:
        parts = d.split("-")
        if len(parts) == 3:
            if len(parts[0]) == 4:  # YYYY-MM-DD
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            elif len(parts[2]) == 4:  # DD-MM-YYYY
                return f"{parts[0]}/{parts[1]}/{parts[2]}"
    elif "/" in d:
        parts = d.split("/")
        if len(parts) == 3:
            if len(parts[0]) == 4:  # YYYY/MM/DD
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            return d  # Already DD/MM/YYYY
    return d


def _num(val):
    try:
        f = float(val)
        if f.is_integer():
            return int(f)
        return round(f, 2)
    except (ValueError, TypeError):
        return 0


# ── Main Generator ────────────────────────────────────────────────────────

def generate_eway_bill_data(
    po: dict,
    line_items: list[dict],
    totals: dict,
    invoice_no: str,
    invoice_date: str,
    transport_mode: str = "",
    vehicle_no: str = "",
    transporter: str = "",
    transporter_id: str = "",
    trans_distance: float = 0,
    vehicle_type: str = "R",
    to_pincode: str = "",
    to_place: str = "",
    supply_date: str = "",
) -> dict:
    """Build the NIC-compliant E-Way Bill Bulk Generation JSON structure.

    Conforms to the Government E-Way Bill Bulk Generation schema (version 1.0.0621).
    """
    # ── From (Supplier / SSK) ────────────────────────────────────────
    from_gstin = (COMPANY.get("gstin") or "27AFKFS4410F1Z2").strip()
    from_trd_name = (COMPANY.get("trade_name") or "").strip()

    raw_addr1 = COMPANY.get("address1", 'REHAB BLDG "F" WING JAY AMBE SRA').replace('"', ' ').strip()
    raw_addr2 = COMPANY.get("address2", 'NEAR SHELL COLONY, OFF EASTERN EXPRESS,').strip()
    raw_addr3 = COMPANY.get("address3", 'CHEMBUR, MUMBAI-400071').strip()

    if "REHAB BLDG" in raw_addr1:
        from_addr1 = "REHAB BLDG  F WING JAY AMBE SRA,NEAR SHELL COLONY"
        from_addr2 = "CHEMBUR"
    else:
        from_addr_full = ", ".join(filter(None, [raw_addr1, raw_addr2, raw_addr3]))
        from_addr1, from_addr2 = _split_address(from_addr_full)

    from_place = (COMPANY.get("city") or "MUMBAI").strip().upper()
    from_pincode = int(COMPANY.get("pincode") or 400071)
    from_state_code = int(COMPANY.get("state_code", 27))
    actual_from_state_code = from_state_code
    if not from_state_code and from_gstin and len(from_gstin) >= 2 and from_gstin[:2].isdigit():
        from_state_code = int(from_gstin[:2])
        actual_from_state_code = from_state_code

    # ── To (Buyer / Client) ──────────────────────────────────────────
    to_gstin = (po.get("client_gstin") or "").strip()
    to_name = (po.get("client_name") or "").strip()
    to_addr_full = (
        po.get("shipping_address") or po.get("billing_address") or
        po.get("client_address") or po.get("delivery_address") or ""
    ).strip()
    to_addr1, to_addr2 = _split_address(to_addr_full)

    # Resolve to_pincode: explicit > extracted from address
    if not to_pincode:
        to_pincode = extract_pincode(to_addr_full) or ""
    to_pin_int = int(to_pincode) if to_pincode and str(to_pincode).isdigit() and len(str(to_pincode)) == 6 else 0

    # Resolve to_place: explicit > po.destination > extracted from address
    if not to_place:
        to_place = (po.get("destination") or "").strip()
    if not to_place:
        to_place = extract_city(to_addr_full)
    if not to_place or len(to_place.strip()) < 2:
        to_place = (po.get("client_city") or po.get("client_state") or "DESTINATION").strip()
    to_place = to_place.upper()

    to_state_code = int(po.get("client_state_code") or 0)
    if not to_state_code and to_gstin and len(to_gstin) >= 2 and to_gstin[:2].isdigit():
        to_state_code = int(to_gstin[:2])
    actual_to_state_code = to_state_code

    # ── Document Details ─────────────────────────────────────────────
    doc_date = normalize_date(invoice_date or supply_date)
    trans_doc_date = normalize_date(supply_date or invoice_date) or doc_date

    # ── Tax Values ───────────────────────────────────────────────────
    subtotal = float(totals.get("subtotal", 0))
    cgst_val = float(totals.get("cgst_amount") if totals.get("cgst_amount") is not None else totals.get("cgst", 0))
    sgst_val = float(totals.get("sgst_amount") if totals.get("sgst_amount") is not None else totals.get("sgst", 0))
    igst_val = float(totals.get("igst_amount") if totals.get("igst_amount") is not None else totals.get("igst", 0))
    grand_total = float(totals.get("grand_total", 0))

    # ── Transport ────────────────────────────────────────────────────
    trans_mode_code = map_transport_mode(transport_mode)
    vehicle = normalize_vehicle_no(vehicle_no)
    transporter_id_clean = (transporter_id or "").strip().upper()
    transporter_name = (transporter or "").strip()
    distance = int(float(trans_distance)) if trans_distance else 0
    v_type = (vehicle_type or "R").strip().upper()
    if v_type not in ("R", "O"):
        v_type = "R"

    # ── Item List ────────────────────────────────────────────────────
    item_list = []
    main_hsn = 64029990
    for idx, li in enumerate(line_items, start=1):
        raw_hsn = str(li.get("hsn_code") or "64029990").strip()
        hsn_str = raw_hsn if raw_hsn else "64029990"
        if idx == 1 and hsn_str.isdigit():
            main_hsn = int(hsn_str)
        qty = int(li.get("quantity") or 0)
        taxable = _num(li.get("amount") or 0)
        desc_parts = [
            li.get("po_style_code") or li.get("style_code") or "",
            li.get("color") or "",
        ]
        product_name = " ".join(filter(None, desc_parts)).strip() or li.get("product_name") or "FOOTWEAR"
        product_desc = (li.get("description") or product_name or "FOOTWEAR")[:100]

        item_list.append({
            "itemNo": idx,
            "productName": product_name[:100],
            "productDesc": product_desc,
            "hsnCode": hsn_str,
            "quantity": qty,
            "qtyUnit": "PRS",
            "taxableAmount": taxable,
            "sgstRate": -1,
            "cgstRate": -1,
            "igstRate": -1,
            "cessRate": -1,
            "cessNonAdvol": -1,
        })

    if not item_list:
        item_list.append({
            "itemNo": 1,
            "productName": "FOOTWEAR",
            "productDesc": "FOOTWEAR",
            "hsnCode": str(main_hsn),
            "quantity": int(totals.get("total_quantity") or 0),
            "qtyUnit": "PRS",
            "taxableAmount": _num(subtotal),
            "sgstRate": -1,
            "cgstRate": -1,
            "igstRate": -1,
            "cessRate": -1,
            "cessNonAdvol": -1,
        })

    # ── Assemble billLists entry ─────────────────────────────────────
    bill = {
        "userGstin": from_gstin,
        "supplyType": "O",
        "subSupplyType": 1,
        "subSupplyDesc": "",
        "docType": "INV",
        "docNo": invoice_no,
        "docDate": doc_date,
        "transType": 1,
        "fromGstin": from_gstin,
        "fromTrdName": from_trd_name,
        "fromAddr1": from_addr1[:120],
        "fromAddr2": from_addr2[:120],
        "fromPlace": from_place[:50],
        "fromPincode": from_pincode,
        "fromStateCode": from_state_code,
        "actualFromStateCode": actual_from_state_code,
        "toGstin": to_gstin,
        "toTrdName": to_name[:100],
        "toAddr1": to_addr1[:120],
        "toAddr2": to_addr2[:120],
        "toPlace": to_place[:50],
        "toPincode": to_pin_int,
        "toStateCode": to_state_code,
        "actualToStateCode": actual_to_state_code,
        "totalValue": _num(subtotal),
        "cgstValue": _num(cgst_val),
        "sgstValue": _num(sgst_val),
        "igstValue": _num(igst_val),
        "cessValue": 0,
        "TotNonAdvolVal": 0,
        "OthValue": 0,
        "totInvValue": _num(grand_total),
        "transMode": trans_mode_code,
        "transDistance": distance,
        "transporterName": transporter_name[:100],
        "transporterId": transporter_id_clean[:15] if transporter_id_clean else "",
        "transDocNo": "",
        "transDocDate": trans_doc_date,
        "vehicleNo": vehicle[:20],
        "vehicleType": v_type,
        "mainHsnCode": main_hsn,
        "itemList": item_list,
    }

    return {
        "version": "1.0.0621",
        "billLists": [bill],
    }


def generate_eway_bill_bytes(
    po: dict,
    line_items: list[dict],
    totals: dict,
    invoice_no: str,
    invoice_date: str,
    **kwargs,
) -> bytes:
    """Generate E-Way Bill JSON and return as UTF-8 bytes."""
    data = generate_eway_bill_data(
        po=po,
        line_items=line_items,
        totals=totals,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        **kwargs,
    )
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
