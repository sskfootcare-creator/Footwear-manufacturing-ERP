"""PDF: Printable Production Card (A4 — fits inside 180mm usable width)."""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.graphics.shapes import Drawing, Line, String

from pdf_image import load_image_for_pdf

BLACK = colors.black
HEAD = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#C27842")
LINE = colors.HexColor("#94A3B8")
LIGHT = colors.HexColor("#F1F5F9")
WHITE = colors.white

USABLE_MM = 180


def _img_from_dataurl(image_url: str, max_h_mm: float = 50, max_w_mm: float = 50):
    """Backward-compatible thin wrapper — kept for any external caller that
    still references this symbol."""
    return load_image_for_pdf(image_url, max_h_mm=max_h_mm, max_w_mm=max_w_mm)


def _make_mini_swatch_box(size_mm=8):
    t = Table([[""]], colWidths=[size_mm * mm], rowHeights=[size_mm * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _build_comp_cell(title, done, layers, compact=False):
    check = "[X]" if done else "[ ]"
    header_fs = 8.5 if compact else 11
    header_lead = 10 if compact else 13
    header_p = Paragraph(f"<b>{check} {title}</b>",
                         ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=header_fs, leading=header_lead, textColor=BLACK))

    box_sz = 5.5 if compact else 8
    font_sz = 6 if compact else 7.5
    lead_sz = 7 if compact else 9.0

    rows = [[header_p, ""]]
    for l in layers:
        sb = _make_mini_swatch_box(size_mm=box_sz)
        p = Paragraph(l, ParagraphStyle("cl", fontName="Helvetica", fontSize=font_sz, leading=lead_sz, textColor=colors.HexColor("#334155")))
        rows.append([sb, p])

    t = Table(rows, colWidths=[(box_sz + 2) * mm, (58 - box_sz - 2) * mm])
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5 if compact else 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5 if compact else 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def _build_card_elements(job_group: dict, style: dict | None, with_rates: bool = True, compact: bool = False) -> list:
    if compact:
        S = {
            "h_co": ParagraphStyle("h_co", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=WHITE),
            "co_sub": ParagraphStyle("cs", fontName="Helvetica", fontSize=6, leading=8, alignment=2, textColor=colors.HexColor("#CBD5E1")),
            "h_style": ParagraphStyle("hst", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=BLACK),
            "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=7, leading=8.5, textColor=ACCENT),
            "lab": ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=5, textColor=ACCENT, leading=6),
            "val": ParagraphStyle("v", fontName="Helvetica", fontSize=6, textColor=BLACK, leading=7.5),
            "valb": ParagraphStyle("vb", fontName="Helvetica-Bold", fontSize=6.5, textColor=BLACK, leading=8),
            "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=5, textColor=colors.HexColor("#475569"), leading=6.5),
            "huge_color": ParagraphStyle("hc", fontName="Helvetica-Bold", fontSize=9.5, textColor=ACCENT, leading=11, alignment=1),
            "huge_qty": ParagraphStyle("hq", fontName="Helvetica-Bold", fontSize=13, leading=15, textColor=HEAD, alignment=1),
        }
        sp_xs, sp_sm = Spacer(1, 1), Spacer(1, 1.5)
    else:
        S = {
            "h_co": ParagraphStyle("h_co", fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=WHITE),
            "co_sub": ParagraphStyle("cs", fontName="Helvetica", fontSize=8, leading=10, alignment=2, textColor=colors.HexColor("#CBD5E1")),
            "h_style": ParagraphStyle("hst", fontName="Helvetica-Bold", fontSize=18, leading=20, textColor=BLACK),
            "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=ACCENT),
            "lab": ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=7, textColor=ACCENT, leading=9),
            "val": ParagraphStyle("v", fontName="Helvetica", fontSize=8, textColor=BLACK, leading=10),
            "valb": ParagraphStyle("vb", fontName="Helvetica-Bold", fontSize=9, textColor=BLACK, leading=11),
            "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=6.5, textColor=colors.HexColor("#475569"), leading=8.5),
            "huge_color": ParagraphStyle("hc", fontName="Helvetica-Bold", fontSize=16, textColor=ACCENT, leading=18, alignment=1),
            "huge_qty": ParagraphStyle("hq", fontName="Helvetica-Bold", fontSize=22, leading=24, textColor=HEAD, alignment=1),
        }
        sp_xs, sp_sm = Spacer(1, 2), Spacer(1, 4)

    # --- Company strip ---
    card_type_text = "SHOP FLOOR CIRCULATION" if not with_rates else "ADMIN / OFFICE RECORD"
    company = Table(
        [[
            Paragraph("SSK FOOTCARE MANUFACTURING LLP", S["h_co"]),
            Paragraph(f"Production Card ({card_type_text}) · {datetime.now().strftime('%d %b %Y')}", S["co_sub"]),
        ]],
        colWidths=[105 * mm, 75 * mm],
    )
    company.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), HEAD),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    # --- Header Card ---
    img_max_h = 22 if compact else 46
    img_max_w = 22 if compact else 46
    img_cell = load_image_for_pdf(style or {}, max_h_mm=img_max_h, max_w_mm=img_max_w)
    if img_cell is None:
        img_cell = Table([[Paragraph("No Image", ParagraphStyle("ni", fontName="Helvetica", fontSize=6 if compact else 8, alignment=1))]],
                         colWidths=[img_max_w * mm], rowHeights=[img_max_h * mm])
        img_cell.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

    info_rows = [
        [Paragraph("PO NUMBER", S["lab"]), Paragraph(job_group.get("po_number", "—"), S["valb"])],
        [Paragraph("CLIENT", S["lab"]), Paragraph(job_group.get("client_name", "—"), S["val"])],
        [Paragraph("STYLE", S["lab"]), Paragraph(f"<b>{job_group.get('style_code','—')}</b>", S["h_style"])],
        [Paragraph("ARTICLE", S["lab"]), Paragraph((style or {}).get("name", "") or job_group.get("description", "—"), S["val"])],
        [Paragraph("DELIVERY", S["lab"]), Paragraph(job_group.get("delivery_date", "—"), S["valb"])],
    ]
    info_col1 = 18 if compact else 20
    info_col2 = 89 if compact else 90
    info_t = Table(info_rows, colWidths=[info_col1 * mm, info_col2 * mm])
    info_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0 if compact else 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0 if compact else 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    color_qty = Table([
        [Paragraph("COLOR", S["lab"])],
        [Paragraph(job_group.get("color", "—"), S["huge_color"])],
        [Spacer(1, 0.5 if compact else 4)],
        [Paragraph("TOTAL PAIRS", S["lab"])],
        [Paragraph(str(job_group.get("total_qty", 0)), S["huge_qty"])],
    ], colWidths=[33 * mm if compact else 40 * mm])
    color_qty.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, ACCENT),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 3),
    ]))

    img_col_w = (img_max_w + 2) * mm
    header_card = Table([[img_cell, info_t, color_qty]],
                        colWidths=[img_col_w, (USABLE_MM - img_max_w - 2 - (33 if compact else 40)) * mm, (33 if compact else 40) * mm])
    header_card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 3),
    ]))

    # --- Size Breakdown ---
    sizes = job_group.get("sizes", [])
    n = max(len(sizes), 1)
    lbl_w = 26 if compact else 36
    tot_w = 15 if compact else 22
    remaining = USABLE_MM - lbl_w - tot_w
    size_col_w = max(5, remaining / n)

    size_data = [["SIZE"] + [str(s["size"]) for s in sizes] + ["TOTAL"]]
    qty_row = [job_group.get("color", "")] + [str(s["quantity"]) for s in sizes] + [str(job_group.get("total_qty", 0))]
    size_data.append(qty_row)

    size_t = Table(size_data, colWidths=[lbl_w * mm] + [size_col_w * mm] * n + [tot_w * mm])
    size_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5 if compact else 10),
        ("FONT", (0, 1), (-1, -1), "Helvetica-Bold", 8.5 if compact else 12),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (-1, 1), (-1, 1), LIGHT),
        ("TEXTCOLOR", (-1, 1), (-1, 1), ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 4),
    ]))

    # --- Process Tally ---
    proc_rows = ["CUTTING", "UPPER", "BOTTOM", "STITCHING", "LASTING", "SOLE PASTING", "FINISH / QC"]
    tally_header = ["PROCESS"] + [str(s["size"]) for s in sizes] + ["DONE", "REJ", "SIGN"]
    tally_data = [tally_header]
    tally_data.append(["PLANNED"] + [str(s["quantity"]) for s in sizes] + [str(job_group.get("total_qty", 0)), "—", "—"])
    for label in proc_rows:
        tally_data.append([label] + ["" for _ in sizes] + ["", "", ""])

    p_lbl_w = 24 if compact else 30
    p_done_w = 8 if compact else 12
    p_rej_w = 7 if compact else 10
    p_sign_w = 18 if compact else 28
    tally_size_w = max(4.5, (USABLE_MM - p_lbl_w - p_done_w - p_rej_w - p_sign_w) / n)

    tally_t = Table(
        tally_data,
        colWidths=[p_lbl_w * mm] + [tally_size_w * mm] * n + [p_done_w * mm, p_rej_w * mm, p_sign_w * mm],
    )
    tally_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 5.5 if compact else 7.5),
        ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 5.5 if compact else 7.5),
        ("FONT", (1, 1), (-1, -1), "Helvetica", 6.5 if compact else 8.5),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
        ("TEXTCOLOR", (0, 1), (-1, 1), ACCENT),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 6.5 if compact else 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5 if compact else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5 if compact else 6),
        ("LINEBELOW", (0, 1), (-1, 1), 1, BLACK),
    ]))

    # --- Components with Swatches ---
    comp = job_group.get("components", {}) or {}
    c1 = _build_comp_cell("UPPER", comp.get("upper_done"), ["Upper Top", "Mid Layer / Reinforce", "Lining"], compact=compact)
    c2 = _build_comp_cell("BOTTOM / INSOLE", comp.get("bottom_done"), ["Bottom Layer", "Insole Board+Cushion", "Insole Cover"], compact=compact)
    c3 = _build_comp_cell("SOLE", comp.get("sole_done"), ["Outsole"], compact=compact)

    comp_t = Table([[c1, c2, c3]], colWidths=[60 * mm, 60 * mm, 60 * mm])
    comp_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("LINEAFTER", (0, 0), (-2, -1), 1, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1 if compact else 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1 if compact else 5),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 7),
    ]))

    # --- Karigar Assignments ---
    assigns = job_group.get("assignments", {}) or {}
    role_labels = [
        ("cutting", "CUTTING"), ("upper", "UPPER"), ("bottom", "BOTTOM"),
        ("stitching", "STITCHING"), ("lasting", "LASTING"),
        ("sole_pasting", "SOLE PASTING"), ("finishing", "FINISHING"),
    ]

    if with_rates:
        kar_rows = [["ROLE", "KARIGAR", "RATE / PAIR", "SIGN"]]
        for rk, rl in role_labels:
            a = assigns.get(rk) or {}
            kar_rows.append([
                rl,
                a.get("worker_name", "_______________"),
                f"Rs.{a.get('rate_per_pair', '')}" if a.get("rate_per_pair") is not None else "_______",
                "________________",
            ])
        kar_col_widths = [35 * mm, 60 * mm, 25 * mm, 60 * mm]
        rate_align = [("ALIGN", (2, 1), (2, -1), "RIGHT")]
    else:
        kar_rows = [["ROLE", "KARIGAR", "SIGN"]]
        for rk, rl in role_labels:
            a = assigns.get(rk) or {}
            kar_rows.append([
                rl,
                a.get("worker_name", "________________________"),
                "________________________",
            ])
        kar_col_widths = [40 * mm, 70 * mm, 70 * mm]
        rate_align = []

    kar_t = Table(kar_rows, colWidths=kar_col_widths)
    kar_style = [
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 6 if compact else 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 6.5 if compact else 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5 if compact else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5 if compact else 4),
    ] + rate_align
    kar_t.setStyle(TableStyle(kar_style))

    # --- Footer ---
    if compact:
        footer_t = Table([[
            Paragraph("<b>NOTES:</b> ____________________________________________________________________", ParagraphStyle("n", fontName="Helvetica", fontSize=6, leading=7)),
            Paragraph("<b>QC PASS:</b> [ ]   <b>SIGN:</b> ____________", ParagraphStyle("qc", fontName="Helvetica", fontSize=6, leading=7, alignment=1)),
        ]], colWidths=[120 * mm, 60 * mm])
        footer_t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, BLACK),
            ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
    else:
        footer_t = Table([[
            Paragraph(
                "<b>NOTES / INSTRUCTIONS:</b><br/><br/>"
                "________________________________________________________________<br/><br/>"
                "________________________________________________________________<br/><br/>"
                "________________________________________________________________",
                ParagraphStyle("n", fontName="Helvetica", fontSize=8, leading=12)),
            Paragraph(
                "<b>QC PASS:</b> [ ]<br/><br/><b>SIGN:</b><br/><br/>____________________<br/>Supervisor",
                ParagraphStyle("qc", fontName="Helvetica", fontSize=8, leading=12, alignment=1)),
        ]], colWidths=[120 * mm, 60 * mm])
        footer_t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, BLACK),
            ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))

    return [
        company,
        sp_xs,
        header_card,
        sp_xs,
        Paragraph("SIZE BREAKDOWN", S["h2"]),
        Spacer(1, 0.5 if compact else 1),
        size_t,
        sp_sm,
        Paragraph("PROCESS TALLY · Fill in qty processed per size at each stage", S["h2"]),
        Spacer(1, 0.5 if compact else 1),
        tally_t,
        sp_sm,
        Paragraph("COMPONENTS & SWATCHES", S["h2"]),
        Spacer(1, 0.5 if compact else 1),
        comp_t,
        sp_sm,
        Paragraph("KARIGAR ASSIGNMENTS", S["h2"]),
        Spacer(1, 0.5 if compact else 1),
        kar_t,
        sp_sm,
        footer_t,
    ]


def build_production_card(job_group: dict, style: dict | None, with_rates: bool = True) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f"Production Card {job_group.get('style_code','')}-{job_group.get('color','')}",
    )
    elements = _build_card_elements(job_group, style, with_rates=with_rates, compact=False)
    doc.build(elements)
    return buf.getvalue()


def build_production_card_dual_a4(job_group: dict, style: dict | None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=5 * mm, bottomMargin=5 * mm,
        title=f"Dual Production Card {job_group.get('style_code','')}-{job_group.get('color','')}",
    )

    # Top half: Shop Floor Circulation (with_rates=False, compact=True)
    top_elements = _build_card_elements(job_group, style, with_rates=False, compact=True)

    # Dashed Cut Line
    cut_d = Drawing(180 * mm, 6 * mm)
    cut_d.add(Line(0, 3 * mm, 180 * mm, 3 * mm, strokeWidth=1, strokeColor=BLACK, strokeDashArray=[4, 4]))
    cut_d.add(String(90 * mm, 1 * mm, "✂  CUT HERE  (Top: Shop Floor Circulation  |  Bottom: Admin Retention)  ✂", fontName="Helvetica-Bold", fontSize=6.5, textAnchor="middle"))

    # Bottom half: Admin Retention (with_rates=True, compact=True)
    bottom_elements = _build_card_elements(job_group, style, with_rates=True, compact=True)

    elements = top_elements + [Spacer(1, 1), cut_d, Spacer(1, 1)] + bottom_elements
    doc.build(elements)
    return buf.getvalue()
