"""PDF: SSK Footcare Tax Invoice (replicates SSK26-27-XXX format) + Dispatch Challan."""
from io import BytesIO
from datetime import datetime
from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


COMPANY = {
    "name": "SSK FOOTCARE MANUFACTURING LLP",
    "address1": 'REHAB BLDG "F" WING JAY AMBE SRA',
    "address2": "NEAR SHELL COLONY, OFF EASTERN EXPRESS,",
    "address3": "CHEMBUR, MUMBAI-400071",
    "gstin": "27AFKFS4410F1Z2",
    "state": "Maharashtra",
    "state_code": "27",
    "bank_acc": "50200105184765",
    "bank_ifsc": "HDFC0001452",
    "bank_name": "HDFC BANK",
    "phone": "",
    "email": "",
}

def update_company_profile(profile: dict):
    global COMPANY
    COMPANY.update({k: v for k, v in profile.items() if k != "_id"})

BLACK = colors.black
BRAND = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#C27842")
MUTED = colors.HexColor("#475569")
LINE = colors.HexColor("#94A3B8")
LIGHT = colors.HexColor("#F1F5F9")
HEAD_BG = colors.HexColor("#E2E8F0")


def amount_in_words(amount: float) -> str:
    try:
        rupees = int(amount)
        paise = int(round((amount - rupees) * 100))
        words = "Rupees " + num2words(rupees, lang="en_IN").title()
        if paise:
            words += f" and {num2words(paise, lang='en_IN').title()} Paise"
        return words + " Only"
    except Exception:
        return f"Rupees {amount}"


def _fmt(n) -> str:
    try:
        n = float(n or 0)
    except Exception:
        return str(n or "")
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}"


def _styles():
    s = getSampleStyleSheet()
    return {
        "company": ParagraphStyle("co", fontName="Helvetica-Bold", fontSize=14, textColor=BLACK,
                                  alignment=1, leading=16),
        "addr": ParagraphStyle("ad", fontName="Helvetica", fontSize=8, textColor=BLACK,
                               alignment=1, leading=10),
        "title": ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=13, textColor=BLACK,
                                alignment=1, leading=15),
        "label": ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=8, textColor=BLACK, leading=10),
        "val": ParagraphStyle("v", fontName="Helvetica", fontSize=8, textColor=BLACK, leading=10),
        "valb": ParagraphStyle("vb", fontName="Helvetica-Bold", fontSize=9, textColor=BLACK, leading=11),
        "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=7, textColor=BLACK, leading=8),
        "decl": ParagraphStyle("dec", fontName="Helvetica", fontSize=7, textColor=BLACK, leading=9, alignment=4),
    }


def _company_header(invoice_no: str, invoice_date: str, po_number: str, po_date: str = ""):
    S = _styles()
    header_cell = [
        Paragraph(COMPANY["name"], S["company"]),
        Paragraph(COMPANY["address1"], S["addr"]),
        Paragraph(COMPANY["address2"], S["addr"]),
        Paragraph(COMPANY["address3"], S["addr"]),
        Spacer(1, 2),
        Paragraph(f'<b>GSTIN:</b> {COMPANY["gstin"]}', S["val"]),
    ]
    t = Table([[header_cell]], colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ]))
    return t


def _invoice_title():
    S = _styles()
    t = Table([[Paragraph("TAX INVOICE", S["title"])]], colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), HEAD_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _meta_block(invoice_no, invoice_date, po_number, po_date, transport_mode, vehicle_no, supply_date):
    """Two-column meta: invoice info left, transport info right."""
    S = _styles()

    def kv(label, value):
        return Table(
            [[Paragraph(label, S["label"]), Paragraph(value or "", S["val"])]],
            colWidths=[28 * mm, 60 * mm],
        )

    left_rows = [
        [Paragraph("PO Number :", S["label"]), Paragraph(po_number or "", S["val"])],
        [Paragraph("Invoice No. :", S["label"]), Paragraph(invoice_no, S["val"])],
        [Paragraph("Invoice Date :", S["label"]), Paragraph(invoice_date, S["val"])],
        [Paragraph("State :", S["label"]), Paragraph(f"{COMPANY['state']}  &nbsp;&nbsp;State Code : {COMPANY['state_code']}", S["val"])],
    ]
    right_rows = [
        [Paragraph("Transportation Mode :", S["label"]), Paragraph(transport_mode or "", S["val"])],
        [Paragraph("Vehicle Number :", S["label"]), Paragraph(vehicle_no or "", S["val"])],
        [Paragraph("Date of Supply :", S["label"]), Paragraph(supply_date or "", S["val"])],
        [Paragraph("Place of Supply :", S["label"]), Paragraph(COMPANY["state"], S["val"])],
    ]
    left = Table(left_rows, colWidths=[28 * mm, 62 * mm])
    right = Table(right_rows, colWidths=[36 * mm, 54 * mm])
    for sub in (left, right):
        sub.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
    outer = Table([[left, right]], colWidths=[90 * mm, 90 * mm])
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return outer


def _party_block(po: dict):
    """Buyer (Billed To) | Consignee (Shipped To)."""
    S = _styles()

    def party(header, name, address, gstin, state, state_code):
        rows = [
            [Paragraph(f"<b>{header}</b>", S["valb"]), ""],
            [Paragraph("Name :", S["label"]), Paragraph(name or "", S["val"])],
            [Paragraph("Address :", S["label"]), Paragraph(address or "", S["val"])],
            [Paragraph("GSTIN :", S["label"]), Paragraph(gstin or "", S["val"])],
            [Paragraph("State :", S["label"]),
             Paragraph(f"{state or ''}  &nbsp;&nbsp;State Code : {state_code or ''}", S["val"])],
        ]
        t = Table(rows, colWidths=[22 * mm, 68 * mm])
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    billed = party(
        "Detail of Receiver | Billed To :",
        po.get("client_name", ""),
        po.get("billing_address") or po.get("client_address") or "",
        po.get("client_gstin", ""),
        po.get("client_state", ""),
        po.get("client_state_code", ""),
    )
    shipped = party(
        "Detail of Consignee | Shipped To :",
        po.get("client_name", ""),
        po.get("shipping_address") or po.get("billing_address") or po.get("client_address") or "",
        po.get("client_gstin", ""),
        po.get("client_state", ""),
        po.get("client_state_code", ""),
    )
    t = Table([[billed, shipped]], colWidths=[90 * mm, 90 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _items_table(items: list, cgst_rate: float, sgst_rate: float, igst_rate: float):
    """SSK invoice item table with CGST/SGST/IGST sub-columns."""
    # Two-row header
    h1 = [
        "SR.", "Name of Product & Detail", "HSN/SAC", "Quantity", "Rate", "Amount", "MRP",
        "Taxable Value", "CGST", "", "SGST", "", "IGST", "", "TOTAL"
    ]
    h2 = ["", "", "", "", "", "", "", "", "Rate", "Amount", "Rate", "Amount", "Rate", "Amount", ""]
    data = [h1, h2]

    total_qty = 0
    total_amount = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    total_total = 0.0

    for i, li in enumerate(items, 1):
        qty = int(li.get("quantity", 0) or 0)
        rate = float(li.get("unit_price", 0) or 0)
        amount = float(li.get("amount", qty * rate))
        mrp = li.get("mrp", "")
        tax_value = amount
        cgst_amt = round(tax_value * cgst_rate / 100, 2)
        sgst_amt = round(tax_value * sgst_rate / 100, 2)
        igst_amt = round(tax_value * igst_rate / 100, 2)
        row_total = round(tax_value + cgst_amt + sgst_amt + igst_amt, 2)

        name = li.get("style_code", "")
        if li.get("color"):
            name += f"-{li.get('color', '')[:2].upper()}"
        desc = li.get("description", "")
        if li.get("size"):
            desc += f" / Sz {li.get('size')}"

        row = [
            str(i),
            Paragraph(f"<b>{name}</b><br/><font size=7>{desc}</font>",
                      ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10)),
            li.get("hsn_code", ""),
            str(qty),
            _fmt(rate),
            _fmt(amount),
            _fmt(mrp) if mrp else "",
            _fmt(tax_value),
            f"{cgst_rate}%" if cgst_rate else "",
            _fmt(cgst_amt) if cgst_amt else "",
            f"{sgst_rate}%" if sgst_rate else "",
            _fmt(sgst_amt) if sgst_amt else "",
            f"{igst_rate}%" if igst_rate else "",
            _fmt(igst_amt) if igst_amt else "",
            _fmt(row_total),
        ]
        data.append(row)
        total_qty += qty
        total_amount += amount
        total_cgst += cgst_amt
        total_sgst += sgst_amt
        total_igst += igst_amt
        total_total += row_total

    # Pad to at least 6 rows for a fuller look
    while len(data) - 2 < 6:
        data.append([""] * 15)

    # Total row
    data.append([
        "", "Total :", "", str(total_qty), "", _fmt(total_amount), "",
        _fmt(total_amount),
        "", _fmt(total_cgst),
        "", _fmt(total_sgst),
        "", _fmt(total_igst),
        _fmt(total_total),
    ])

    col_widths_mm = [7, 36, 14, 13, 12, 14, 10, 14, 7, 11, 7, 11, 7, 11, 16]
    t = Table(data, colWidths=[w * mm for w in col_widths_mm], repeatRows=2)
    style = [
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 1), HEAD_BG),
        ("FONT", (0, 0), (-1, 1), "Helvetica-Bold", 7),
        ("FONT", (0, 2), (-1, -1), "Helvetica", 8),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("ALIGN", (3, 2), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 2), (0, -1), "CENTER"),
        ("ALIGN", (2, 2), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Spans for grouped header cells: SR, Name, HSN, Qty, Rate, Amount, MRP, Taxable single column header spans 2 rows
        ("SPAN", (0, 0), (0, 1)),  # SR
        ("SPAN", (1, 0), (1, 1)),  # Name
        ("SPAN", (2, 0), (2, 1)),  # HSN
        ("SPAN", (3, 0), (3, 1)),  # Qty
        ("SPAN", (4, 0), (4, 1)),  # Rate
        ("SPAN", (5, 0), (5, 1)),  # Amount
        ("SPAN", (6, 0), (6, 1)),  # MRP
        ("SPAN", (7, 0), (7, 1)),  # Taxable Value
        ("SPAN", (8, 0), (9, 0)),  # CGST group
        ("SPAN", (10, 0), (11, 0)),  # SGST group
        ("SPAN", (12, 0), (13, 0)),  # IGST group
        ("SPAN", (14, 0), (14, 1)),  # TOTAL
        # Total row bold + background
        ("BACKGROUND", (0, -1), (-1, -1), HEAD_BG),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    t.setStyle(TableStyle(style))
    return t, total_amount, total_cgst, total_sgst, total_igst, total_total


def _totals_section(amount_words: str, taxable: float, cgst: float, sgst: float, igst: float, grand_total: float,
                    cgst_rate: float, sgst_rate: float, igst_rate: float):
    S = _styles()

    left_cells = [
        [Paragraph("<b>Total Invoice Amount in Word :</b>", S["label"])],
        [Paragraph(amount_words, S["valb"])],
        [Spacer(1, 4)],
        [Paragraph("<b>Bank Account Number :</b> " + COMPANY["bank_acc"], S["val"])],
        [Paragraph("<b>Bank Branch IFSC Code :</b> " + COMPANY["bank_ifsc"], S["val"])],
        [Paragraph("<b>Bank Name :</b> " + COMPANY["bank_name"], S["val"])],
    ]
    left = Table([[c] for c in left_cells], colWidths=[110 * mm])
    left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    right_rows = [
        ["Total Amount Before Tax", _fmt(taxable)],
        [f"Add: CGST {cgst_rate}%", _fmt(cgst)],
        [f"Add: SGST {sgst_rate}%", _fmt(sgst)],
        [f"Add: IGST {igst_rate}%", _fmt(igst)],
        ["Total Amount : GST", _fmt(cgst + sgst + igst)],
        ["Total Amount After Tax", _fmt(grand_total)],
    ]
    right = Table(right_rows, colWidths=[45 * mm, 25 * mm])
    right.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, -1), (-1, -1), HEAD_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    outer = Table([[left, right]], colWidths=[110 * mm, 70 * mm])
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return outer


def _footer_block():
    S = _styles()
    decl_text = (
        "I/We hereby certify that my/our registration certificate under the Central and State Goods "
        "and Service Tax Act, 2017 is in force on the date on which the sale of the goods specified "
        "in this tax invoice is made by me/us and that the transaction of the sale covered by this "
        "invoice has been effected by me/us and it shall be accounted for in the turnover of sales "
        "while filing my return and the due tax if any payable on the sales has been paid or shall be paid."
    )
    left_cell = [
        Paragraph("<b>GST Payable on Reverse Charges :</b> N.A.", S["val"]),
        Spacer(1, 4),
        Paragraph("<b>Declaration :</b>", S["label"]),
        Paragraph(decl_text, S["decl"]),
        Spacer(1, 4),
        Paragraph("<b>Terms and Conditions & Common Seal</b>", S["label"]),
    ]
    right_cell = [
        Paragraph("Certified that the particulars given above are true and correct", S["val"]),
        Spacer(1, 24),
        Paragraph(f"<b>For, {COMPANY['name']}</b>", S["valb"]),
        Spacer(1, 18),
        Paragraph("<b>Authorised Signatory</b>", S["label"]),
    ]
    t = Table([[left_cell, right_cell]], colWidths=[110 * mm, 70 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
        ("VALIGN", (0, 0), (0, 0), "TOP"),
        ("VALIGN", (1, 0), (1, 0), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def build_invoice(po: dict, invoice_no: str, invoice_date: str = "",
                  transport_mode: str = "", vehicle_no: str = "",
                  supply_date: str = "", line_items: list = None) -> bytes:
    """Build a SSK-style tax invoice PDF. If `line_items` is given, use those; else use po['line_items']."""
    if not invoice_date:
        invoice_date = datetime.now().strftime("%d/%m/%Y")
    items = line_items if line_items is not None else po.get("line_items", [])

    cgst_rate = float(po.get("cgst_rate", 0) or 0)
    sgst_rate = float(po.get("sgst_rate", 0) or 0)
    igst_rate = float(po.get("igst_rate", 0) or 0)

    item_table, total_amount, total_cgst, total_sgst, total_igst, grand_total = _items_table(
        items, cgst_rate, sgst_rate, igst_rate
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Tax Invoice {invoice_no}",
    )
    elements = [
        _company_header(invoice_no, invoice_date, po.get("po_number", "")),
        _invoice_title(),
        _meta_block(invoice_no, invoice_date, po.get("po_number", ""), po.get("po_date", ""),
                    transport_mode, vehicle_no, supply_date),
        _party_block(po),
        item_table,
        _totals_section(amount_in_words(grand_total), total_amount, total_cgst, total_sgst, total_igst,
                        grand_total, cgst_rate, sgst_rate, igst_rate),
        _footer_block(),
    ]
    doc.build(elements)
    return buf.getvalue()


# Backward-compatible names
def generate_tax_invoice_pdf(po: dict) -> bytes:
    inv_no = po.get("invoice_no") or f"SSK-{po.get('po_number', 'TMP')}"
    inv_date = po.get("invoice_date") or datetime.now().strftime("%d/%m/%Y")
    return build_invoice(po, inv_no, inv_date)


def generate_dispatch_challan_pdf(po: dict, dispatch_qty: int = None,
                                  transporter: str = "", vehicle: str = "") -> bytes:
    """Dispatch challan: same layout but titled 'Dispatch Challan' and without prices."""
    # Reuse invoice layout but title differently and zero out the price columns visually
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Dispatch Challan {po.get('po_number')}",
    )
    S = _styles()
    items = po.get("line_items", [])

    # Build a simple challan items table (no price columns)
    h = ["SR.", "Name of Product & Detail", "HSN/SAC", "Color", "Size", "Quantity"]
    rows = [h]
    total_qty = 0
    for i, li in enumerate(items, 1):
        qty = int(li.get("quantity", 0) or 0)
        rows.append([
            str(i),
            Paragraph(f"<b>{li.get('style_code', '')}</b><br/><font size=7>{li.get('description', '')}</font>",
                      ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10)),
            li.get("hsn_code", ""),
            li.get("color", ""),
            str(li.get("size", "")),
            str(qty),
        ])
        total_qty += qty
    while len(rows) - 1 < 6:
        rows.append([""] * 6)
    rows.append(["", "Total :", "", "", "", str(total_qty)])

    items_table = Table(rows, colWidths=[12 * mm, 80 * mm, 24 * mm, 24 * mm, 16 * mm, 24 * mm])
    items_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), HEAD_BG),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    title_table = Table([[Paragraph("DISPATCH CHALLAN", S["title"])]], colWidths=[180 * mm])
    title_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), HEAD_BG),
    ]))

    elements = [
        _company_header("", "", po.get("po_number", "")),
        title_table,
        _meta_block(po.get("po_number", "") + "-CHN", datetime.now().strftime("%d/%m/%Y"),
                    po.get("po_number", ""), po.get("po_date", ""),
                    transporter, vehicle, po.get("delivery_date", "")),
        _party_block(po),
        items_table,
        _footer_block(),
    ]
    doc.build(elements)
    return buf.getvalue()
