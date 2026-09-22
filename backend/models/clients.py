"""Pydantic models for Client Master and Direct Invoice creation with Indian GST state logic."""

import re
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field, model_validator


class ClientAddress(BaseModel):
    address_line: str = ""
    city: str = ""
    state: str = "Uttar Pradesh"
    state_code: str = "09"
    pincode: str = ""


class ClientIn(BaseModel):
    company_name: str = Field(..., description="Client company / trade name")
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    gstin: Optional[str] = ""
    pan: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    state: Optional[str] = "Uttar Pradesh"
    state_code: Optional[str] = "09"
    payment_terms_days: Optional[int] = 30
    notes: Optional[str] = ""
    is_active: Optional[bool] = True


class DirectInvoiceLineItem(BaseModel):
    style_code: str = Field(..., description="Style code or product name")
    color: Optional[str] = ""
    size: Optional[str] = ""
    description: Optional[str] = ""
    hsn_code: Optional[str] = "6403"
    qty: Optional[int] = Field(None, gt=0, description="Quantity in pairs")
    quantity: Optional[int] = Field(None, gt=0, description="Quantity in pairs")
    unit_price: float = Field(..., ge=0, description="Rate per pair")

    @model_validator(mode="before")
    @classmethod
    def resolve_quantity(cls, data: Any):
        if isinstance(data, dict):
            q = data.get("quantity") if data.get("quantity") is not None else data.get("qty")
            if q is not None:
                try:
                    val = int(q)
                    data["quantity"] = val
                    data["qty"] = val
                except (ValueError, TypeError):
                    pass
        return data

    @model_validator(mode="after")
    def validate_quantity_present(self):
        if self.qty is None and self.quantity is None:
            raise ValueError("Quantity is required and must be greater than 0")
        if self.qty is not None and self.quantity is None:
            self.quantity = self.qty
        elif self.quantity is not None and self.qty is None:
            self.qty = self.quantity
        return self


class DirectInvoiceIn(BaseModel):
    # Client info
    client_id: Optional[str] = None
    client_name: str = Field(..., description="Client company / business name")
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    client_gstin: Optional[str] = ""
    pan: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    place_of_supply: Optional[str] = None
    client_state_code: Optional[str] = None

    # Invoice parameters
    invoice_date: Optional[str] = None  # DD/MM/YYYY or YYYY-MM-DD
    payment_terms_days: Optional[int] = 30
    due_date: Optional[str] = None      # Optional override; auto-computed if omitted

    # Dispatch / Logistics details (optional)
    transport_mode: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    supply_date: Optional[str] = ""
    notes: Optional[str] = ""

    # Tax configuration (Footwear 5% default: 2.5% CGST + 2.5% SGST or 5% IGST)
    supplier_state_code: Optional[str] = None  # Seller state code (e.g. 27 for Maharashtra, 09 for UP)
    tax_mode: Optional[str] = "auto"          # 'auto' | 'intra' | 'inter'
    gst_rate: Optional[float] = 5.0
    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    igst_rate: Optional[float] = None

    # Line Items
    line_items: List[DirectInvoiceLineItem] = Field(..., min_length=1)

    # Master saving option
    save_client_to_master: Optional[bool] = True


INDIAN_STATES_MAP: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}

# Name aliases to state codes
REVERSE_STATES_MAP: Dict[str, str] = {
    v.lower(): k for k, v in INDIAN_STATES_MAP.items()
}
REVERSE_STATES_MAP.update({
    "up": "09",
    "uttar pradesh": "09",
    "mh": "27",
    "maharashtra": "27",
    "dl": "07",
    "delhi": "07",
    "nct of delhi": "07",
    "orissa": "21",
    "pondicherry": "34",
    "uttaranchal": "05",
})


def extract_state_code(
    state_code: Optional[str] = None,
    gstin: Optional[str] = None,
    place_of_supply: Optional[str] = None,
    address: Optional[str] = None,
    fallback: str = "09",
) -> str:
    """
    Robustly extract a valid 2-digit Indian GST state code from:
    1. GSTIN (first 2 digits are the authoritative state code under GST Act)
    2. Explicit state_code string (e.g. '09', '27', '9')
    3. Place of supply string (e.g. '09-Uttar Pradesh', '27-Maharashtra', 'Delhi')
    4. Address text containing a state name
    5. Fallback state code
    """
    # 1. Authoritative check: GSTIN
    if gstin:
        clean_gst = re.sub(r"[^A-Z0-9]", "", str(gstin).strip().upper())
        if len(clean_gst) >= 2 and clean_gst[:2].isdigit():
            c = clean_gst[:2]
            if c in INDIAN_STATES_MAP:
                return c

    # 2. Explicit state_code
    if state_code:
        clean_code = re.sub(r"[^0-9]", "", str(state_code).strip())
        if clean_code:
            clean_code = clean_code.zfill(2)
            if clean_code in INDIAN_STATES_MAP:
                return clean_code

    # 3. Place of supply
    if place_of_supply:
        pos_str = str(place_of_supply).strip()
        m = re.match(r"^(\d{1,2})", pos_str)
        if m:
            c = m.group(1).zfill(2)
            if c in INDIAN_STATES_MAP:
                return c
        pos_lower = pos_str.lower()
        for name_lower, code in REVERSE_STATES_MAP.items():
            if name_lower in pos_lower:
                return code

    # 4. Address scan
    if address:
        addr_lower = str(address).lower()
        for name_lower, code in REVERSE_STATES_MAP.items():
            if name_lower in addr_lower:
                return code

    return fallback.zfill(2) if fallback else "09"


def determine_tax_mode(
    supplier_state_code: Optional[str],
    client_state_code: Optional[str],
    tax_mode: Optional[str] = "auto",
) -> Tuple[bool, str]:
    """
    Determine whether billing is intra-state (CGST+SGST) or inter-state (IGST).
    Returns: (is_intra_state: bool, resolved_tax_mode: 'intra' | 'inter')
    """
    mode = (tax_mode or "auto").strip().lower()
    if mode == "intra":
        return True, "intra"
    if mode == "inter":
        return False, "inter"

    # 'auto': Compare supplier state vs client state
    s_code = str(supplier_state_code or "").strip().zfill(2)
    c_code = str(client_state_code or "").strip().zfill(2)

    if s_code and c_code and s_code == c_code:
        return True, "intra"
    return False, "inter"
