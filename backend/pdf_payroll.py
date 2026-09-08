"""PDF: Payroll Summary + Per-karigar Wage Slip."""
from io import BytesIO
from datetime import datetime
from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

BLACK = colors.black
HEAD = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#C27842")
LINE = colors.HexColor("#94A3B8")
LIGHT = colors.HexColor("#F1F5F9")
GREEN = colors.HexColor("#16A34A")
RED = colors.HexColor("#DC2626")


def _inr(n):
    try:
        return f"Rs. {float(n or 0):,.2f}"
    except Exception:
        return f"Rs. {n}"


def _amount_words(amount):
    try:
        rupees = int(amount)
        words = "Rupees " + num2words(rupees, lang="en_IN").title()
        return words + " Only"
    except Exception:
        return f"Rs. {amount}"


def _company_header():
    p = lambda t, s=10, b=False, c=BLACK, align=1: Paragraph(
        t, ParagraphStyle("h", fontName="Helvetica-Bold" if b else "Helvetica",
                          fontSize=s, textColor=c, alignment=align, leading=s + 2)
    )
    inner = [
        p("SSK FOOTCARE MANUFACTURING LLP", 14, True),
        p('REHAB BLDG "F" WING JAY AMBE SRA, NEAR SHELL COLONY, CHEMBUR, MUMBAI-400071', 8),
        p("GSTIN: 27AFKFS4410F1Z2", 8, True),
    ]
    t = Table([[inner]], colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _title_bar(title):
    t = Table([[Paragraph(title, ParagraphStyle("t", fontName="Helvetica-Bold",
                                                fontSize=13, alignment=1, textColor=colors.white))]],
              colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEAD),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build_payroll_summary(data: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title="Payroll Summary")
    rows = data.get("rows", [])
    period = f"{data.get('from_date') or 'All time'} → {data.get('to_date') or 'Today'}"

    meta = Table([
        ["Period", period, "Karigars", str(data.get("worker_count", 0))],
        ["Opening Balance", _inr(data.get("grand_opening_balance", 0)),
         "Period Earnings", _inr(data.get("grand_total", 0))],
        ["Paid / Advances", _inr((data.get("grand_advances_open", 0) or 0) + (data.get("grand_payments", 0) or 0)),
         "Net Payable", _inr(data.get("grand_net_payable", 0))],
    ], colWidths=[32 * mm, 58 * mm, 32 * mm, 58 * mm])
    meta.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # Karigar table
    header = ["#", "Karigar", "Skill", "Opening Bal", "Pairs", "Earnings", "Paid / Adv", "Net Payable"]
    table_rows = [header]
    for i, r in enumerate(rows, 1):
        debit = (r.get("advances_open", 0) or 0) + (r.get("payments_paid", 0) or 0)
        table_rows.append([
            str(i), r["name"], r["skill"], _inr(r.get("opening_balance", 0)), str(r["total_pairs"]),
            _inr(r["total_earning"]), _inr(debit), _inr(r["net_payable"]),
        ])
    table_rows.append(["", Paragraph("<b>TOTAL</b>", ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=9, alignment=2)),
                       "", _inr(data.get("grand_opening_balance", 0)), str(sum(r["total_pairs"] for r in rows)),
                       _inr(data.get("grand_total", 0)), _inr((data.get("grand_advances_open", 0) or 0) + (data.get("grand_payments", 0) or 0)),
                       _inr(data.get("grand_net_payable", 0))])

    t = Table(table_rows, colWidths=[8 * mm, 38 * mm, 22 * mm, 24 * mm, 16 * mm, 24 * mm, 24 * mm, 24 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -2), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -2), "Helvetica", 8),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BLACK),
        ("TEXTCOLOR", (6, 1), (6, -2), RED),
        ("TEXTCOLOR", (7, 1), (7, -2), GREEN),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))


    elements = [
        _company_header(),
        _title_bar("PAYROLL SUMMARY"),
        Spacer(1, 8),
        meta,
        Spacer(1, 12),
        t,
        Spacer(1, 20),
        Paragraph(f"Total Net Payable in Words: <b>{_amount_words(data.get('grand_net_payable', 0))}</b>",
                  ParagraphStyle("aw", fontName="Helvetica", fontSize=9, leading=11)),
        Spacer(1, 30),
        Paragraph("Prepared by ______________________ &nbsp;&nbsp;&nbsp;&nbsp; Authorised Signatory ______________________",
                  ParagraphStyle("s", fontName="Helvetica", fontSize=9, alignment=1)),
    ]
    doc.build(elements)
    return buf.getvalue()


def build_wage_slip(row: dict, advances: list, from_date: str, to_date: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"Wage Slip - {row['name']}")
    period = f"{from_date or 'All time'} → {to_date or 'Today'}"

    # Karigar info
    info = Table([
        ["Karigar Name", row["name"], "Skill", (row.get("skill") or "—").upper()],
        ["Phone", row.get("phone") or "—", "Default Rate", _inr(row.get("default_rate", 0)) + "/pair"],
        ["Period", period, "Total Pairs Done", str(row.get("total_pairs", 0))],
    ], colWidths=[30 * mm, 60 * mm, 30 * mm, 60 * mm])
    info.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # Jobs table
    jobs_data = [["#", "PO", "Style", "Color", "Size", "Role", "Pairs", "Rate", "Earning"]]
    for i, j in enumerate(row.get("jobs", []), 1):
        jobs_data.append([
            str(i), j.get("po_number", ""), j.get("style_code", ""),
            j.get("color", ""), str(j.get("size", "")), j.get("role", "").upper(),
            str(j.get("pairs", 0)), _inr(j.get("rate", 0)), _inr(j.get("earning", 0)),
        ])
    if len(jobs_data) == 1:
        jobs_data.append(["", "—", "no jobs in this period", "", "", "", "", "", ""])
    jobs_data.append(["", "", "", "", "", Paragraph("<b>Subtotal</b>", ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=9, alignment=2)),
                      str(row.get("total_pairs", 0)), "", _inr(row.get("total_earning", 0))])

    jobs_t = Table(jobs_data, colWidths=[8 * mm, 24 * mm, 28 * mm, 20 * mm, 12 * mm, 22 * mm, 16 * mm, 22 * mm, 28 * mm])
    jobs_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -2), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -2), "Helvetica", 8),
        ("ALIGN", (6, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # Advances table
    adv_data = [["#", "Date", "Amount", "Status", "Notes"]]
    for i, a in enumerate(advances, 1):
        adv_data.append([
            str(i), a.get("date", "")[:10] if a.get("date") else "—",
            _inr(a.get("amount", 0)),
            "Settled" if a.get("settled") else "Open",
            a.get("notes", "")
        ])
    if len(adv_data) == 1:
        adv_data.append(["", "—", "No advances taken", "", ""])

    adv_t = Table(adv_data, colWidths=[8 * mm, 24 * mm, 30 * mm, 24 * mm, 94 * mm])
    adv_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # Final settlement block
    debit_amt = (row.get("advances_open", 0) or 0) + (row.get("payments_paid", 0) or 0)
    settle_data = [
        ["Opening Balance (b/f)", _inr(row.get("opening_balance", 0))],
        ["Current Period Earnings", _inr(row.get("total_earning", 0))],
        ["Productivity Bonus", _inr(row.get("total_bonus", 0))],
        ["Less: Period Advances / Paid", "(-) " + _inr(debit_amt)],
        ["Net Payable Due", _inr(row.get("net_payable", 0))],
    ]
    settle = Table(settle_data, colWidths=[80 * mm, 70 * mm])
    settle.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, -1), (-1, -1), HEAD),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
        ("TEXTCOLOR", (1, 3), (1, 3), RED),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    elements = [
        _company_header(),
        _title_bar("KARIGAR WAGE SLIP"),
        Spacer(1, 8),
        info,
        Spacer(1, 12),
        Paragraph("<b>Jobs Completed</b>",
                  ParagraphStyle("lh", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)),
        Spacer(1, 4),
        jobs_t,
        Spacer(1, 12),
        Paragraph("<b>Advances Taken</b>",
                  ParagraphStyle("lh2", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT)),
        Spacer(1, 4),
        adv_t,
        Spacer(1, 14),
        settle,
        Spacer(1, 8),
        Paragraph(f"Net Payable in Words: <b>{_amount_words(row.get('net_payable', 0))}</b>",
                  ParagraphStyle("aw", fontName="Helvetica", fontSize=9, leading=11)),
        Spacer(1, 24),
        Paragraph("Received by ______________________ (Karigar) &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
                  "Authorised Signatory ______________________",
                  ParagraphStyle("s", fontName="Helvetica", fontSize=9, alignment=1)),
    ]
    doc.build(elements)
    return buf.getvalue()
