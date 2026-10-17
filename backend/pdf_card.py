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
LIGHT = colors.HexColor("#F8FAFC")
ZEBRA = colors.HexColor("#F1F5F9")
WHITE = colors.white

USABLE_MM = 180


def _img_from_dataurl(image_url: str, max_h_mm: float = 50, max_w_mm: float = 50):
    """Backward-compatible thin wrapper — kept for any external caller that
    still references this symbol."""
    return load_image_for_pdf(image_url, max_h_mm=max_h_mm, max_w_mm=max_w_mm)


def _make_mini_swatch_box(size_mm=8):
    """Deprecated: Component swatches removed from production card."""
    t = Table([[""]], colWidths=[size_mm * mm], rowHeights=[size_mm * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
    ]))
    return t


def _build_comp_cell(title, done, layers, compact=False):
    """Deprecated: Component swatches removed from production card."""
    return Table([[Paragraph(f"<b>{title}</b>", ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=8))]], colWidths=[60 * mm])


def _build_card_elements(job_group: dict, style: dict | None, with_rates: bool = True, compact: bool = False) -> list:
    if compact:
        S = {
            "h_co": ParagraphStyle("h_co", fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=WHITE),
            "co_sub": ParagraphStyle("cs", fontName="Helvetica", fontSize=5.5, leading=7.5, alignment=2, textColor=colors.HexColor("#CBD5E1")),
            "h_style": ParagraphStyle("hst", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=BLACK),
            "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=ACCENT),
            "lab": ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=5, textColor=ACCENT, leading=6),
            "val": ParagraphStyle("v", fontName="Helvetica", fontSize=5.5, textColor=BLACK, leading=7),
            "valb": ParagraphStyle("vb", fontName="Helvetica-Bold", fontSize=6, textColor=BLACK, leading=7.5),
            "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=5, textColor=colors.HexColor("#475569"), leading=6.5),
            "huge_color": ParagraphStyle("hc", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT, leading=10.5, alignment=1),
            "huge_qty": ParagraphStyle("hq", fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=HEAD, alignment=1),
        }
        sp_xs, sp_sm = Spacer(1, 0.8), Spacer(1, 1.2)
    else:
        S = {
            "h_co": ParagraphStyle("h_co", fontName="Helvetica-Bold", fontSize=13, leading=15, textColor=WHITE),
            "co_sub": ParagraphStyle("cs", fontName="Helvetica", fontSize=7.5, leading=9.5, alignment=2, textColor=colors.HexColor("#CBD5E1")),
            "h_style": ParagraphStyle("hst", fontName="Helvetica-Bold", fontSize=16, leading=18, textColor=BLACK),
            "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=ACCENT),
            "lab": ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=6.5, textColor=ACCENT, leading=8),
            "val": ParagraphStyle("v", fontName="Helvetica", fontSize=7.5, textColor=BLACK, leading=9.5),
            "valb": ParagraphStyle("vb", fontName="Helvetica-Bold", fontSize=8.5, textColor=BLACK, leading=10.5),
            "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=6, textColor=colors.HexColor("#475569"), leading=8),
            "huge_color": ParagraphStyle("hc", fontName="Helvetica-Bold", fontSize=14, textColor=ACCENT, leading=16, alignment=1),
            "huge_qty": ParagraphStyle("hq", fontName="Helvetica-Bold", fontSize=20, leading=22, textColor=HEAD, alignment=1),
        }
        sp_xs, sp_sm = Spacer(1, 2), Spacer(1, 3.5)

    # 1. Company Header Strip
    card_type_text = "SHOP FLOOR CIRCULATION" if not with_rates else "ADMIN / OFFICE RECORD"
    company = Table(
        [[
            Paragraph("SSK FOOTCARE MANUFACTURING LLP", S["h_co"]),
            Paragraph(f"PRODUCTION JOB CARD ({card_type_text}) · {datetime.now().strftime('%d %b %Y')}", S["co_sub"]),
        ]],
        colWidths=[105 * mm, 75 * mm],
    )
    company.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), HEAD),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))

    # 2. Header Card (Image + Details + Qty Box)
    img_max_h = 20 if compact else 38
    img_max_w = 20 if compact else 38
    raw_img = load_image_for_pdf(style or {}, max_h_mm=img_max_h, max_w_mm=img_max_w)
    if raw_img is not None:
        img_cell = Table([[raw_img]], colWidths=[img_max_w * mm], rowHeights=[img_max_h * mm])
        img_cell.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), WHITE),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
    else:
        img_cell = Table([[Paragraph("No Image", ParagraphStyle("ni", fontName="Helvetica", fontSize=5.5 if compact else 7.5, alignment=1))]],
                         colWidths=[img_max_w * mm], rowHeights=[img_max_h * mm])
        img_cell.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

    style_code = job_group.get("style_code", "—")
    po_style_code = job_group.get("po_style_code")
    has_mapped = (
        po_style_code and
        str(po_style_code).strip() and
        str(po_style_code).strip().upper() != str(style_code).strip().upper()
    )
    style_display = f"{style_code}/{po_style_code}" if has_mapped else style_code

    created_raw = job_group.get("created_at") or ""
    try:
        if created_raw:
            created_dt = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            card_created_date = created_dt.strftime("%d %b %Y")
        else:
            card_created_date = "—"
    except Exception:
        card_created_date = str(created_raw)[:10] or "—"

    h_style_fs = (8 if compact else 12) if len(style_display) > 16 else (10 if compact else 15)
    h_style_lead = h_style_fs + 2
    h_style_p = Paragraph(f"<b>{style_display}</b>", ParagraphStyle("hst_dyn", fontName="Helvetica-Bold", fontSize=h_style_fs, leading=h_style_lead, textColor=BLACK))

    info_rows = [
        [Paragraph("PO NUMBER", S["lab"]), Paragraph(job_group.get("po_number", "—") or "—", S["valb"])],
        [Paragraph("CLIENT", S["lab"]), Paragraph(job_group.get("client_name", "—") or "—", S["val"])],
        [Paragraph("STYLE", S["lab"]), h_style_p],
        [Paragraph("ARTICLE", S["lab"]), Paragraph((style or {}).get("name", "") or job_group.get("description", "—") or "—", S["val"])],
        [Paragraph("CREATED", S["lab"]), Paragraph(card_created_date, S["val"])],
        [Paragraph("DELIVERY", S["lab"]), Paragraph(job_group.get("delivery_date", "—") or "—", S["valb"])],
    ]
    info_col1 = 17 if compact else 20
    info_col2 = 104 if compact else 74
    info_t = Table(info_rows, colWidths=[info_col1 * mm, info_col2 * mm])
    info_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0 if compact else 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 0 if compact else 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    sizes = job_group.get("sizes") or job_group.get("rows") or []
    total_qty = job_group.get("total_qty")
    if total_qty is None:
        total_qty = job_group.get("quantity")
    if total_qty is None:
        total_qty = sum(s.get("quantity", 0) for s in sizes)

    color_qty = Table([
        [Paragraph("COLOR", S["lab"])],
        [Paragraph(job_group.get("color", "—") or "—", S["huge_color"])],
        [Spacer(1, 0.5 if compact else 3)],
        [Paragraph("TOTAL PAIRS", S["lab"])],
        [Paragraph(str(total_qty), S["huge_qty"])],
    ], colWidths=[34 * mm if compact else 40 * mm])
    color_qty.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, ACCENT),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 2.5),
    ]))

    img_col_w = (img_max_w + 2) * mm
    right_col_w = (34 if compact else 40) * mm
    mid_col_w = (USABLE_MM - (img_max_w + 2) - (34 if compact else 40)) * mm
    header_card = Table([[img_cell, info_t, color_qty]], colWidths=[img_col_w, mid_col_w, right_col_w])
    header_card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1 if compact else 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 2.5),
    ]))

    # 3. Size Breakdown Matrix
    n = max(len(sizes), 1)
    lbl_w = 24 if compact else 32
    tot_w = 14 if compact else 20
    remaining = USABLE_MM - lbl_w - tot_w
    size_col_w = max(4.5, remaining / n)

    size_data = [["SIZE"] + [str(s.get("size", "")) for s in sizes] + ["TOTAL"]]
    qty_row = ["PAIRS"] + [str(s.get("quantity", 0)) for s in sizes] + [str(total_qty)]
    size_data.append(qty_row)

    size_t = Table(size_data, colWidths=[lbl_w * mm] + [size_col_w * mm] * n + [tot_w * mm])
    size_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 6.5 if compact else 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica-Bold", 7.5 if compact else 10.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (-1, 1), (-1, 1), LIGHT),
        ("TEXTCOLOR", (-1, 1), (-1, 1), ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 0.8 if compact else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8 if compact else 3),
    ]))

    # 4. Manufacturing Process Tally
    proc_rows = [
        "1. UPPER CUTTING",
        "2. UPPER STITCHING",
        "3. BOTTOM PREP / STAMP",
        "4. TOE & HEEL LASTING",
        "5. SOLE PASTING & PRESS",
        "6. FINISHING & PACKING",
    ]
    tally_header = ["MANUFACTURING PROCESS"] + [str(s.get("size", "")) for s in sizes] + ["DONE", "REJ", "SIGN"]
    tally_data = [tally_header]
    tally_data.append(["PLANNED TARGET"] + [str(s.get("quantity", 0)) for s in sizes] + [str(total_qty), "—", "—"])
    for label in proc_rows:
        tally_data.append([label] + ["" for _ in sizes] + ["", "", ""])

    p_lbl_w = 34 if compact else 44
    p_done_w = 9 if compact else 13
    p_rej_w = 8 if compact else 11
    p_sign_w = 19 if compact else 26
    tally_size_w = max(4.5, (USABLE_MM - p_lbl_w - p_done_w - p_rej_w - p_sign_w) / n)

    tally_t = Table(
        tally_data,
        colWidths=[p_lbl_w * mm] + [tally_size_w * mm] * n + [p_done_w * mm, p_rej_w * mm, p_sign_w * mm],
    )
    tally_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 5.5 if compact else 7.5),
        ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 5.2 if compact else 7.2),
        ("FONT", (1, 1), (-1, -1), "Helvetica", 6 if compact else 8),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
        ("TEXTCOLOR", (0, 1), (-1, 1), ACCENT),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 6 if compact else 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.4 if compact else 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.4 if compact else 3),
        ("LINEBELOW", (0, 1), (-1, 1), 0.8, BLACK),
    ]))

    # 5. Process Sub-tasks & Karigar Assignments (NO COMPONENT SWATCHES)
    assigns = job_group.get("assignments", {}) or {}
    outside_list = job_group.get("outside_labour", []) or []
    if not outside_list and style and style.get("outside_labour"):
        outside_list = style.get("outside_labour") or []

    specs = job_group.get("component_specs", {}) or (style.get("component_specs") if style else {}) or {}
    is_heel = (job_group.get("footwear_type") == "heel") or (specs.get("footwear_type") == "heel") or (style and style.get("footwear_type") == "heel") or bool(assigns.get("heel_gola"))
    is_ready_sole = job_group.get("sole_ready_to_use") or (style and (style.get("sole_ready_to_use") or style.get("ready_to_use_sole")))

    # Left: Upper Track + Sole Track (+ Heel if heel)
    left_items = [
        ("upper", "Upper: Lead", "upper", None),
        ("upper.cutting", "Upper: Cutting", "cutting", "upper"),
        ("upper.stitching", "Upper: Stitching", "stitching", "upper"),
        ("upper.folding", "Upper: Folding", None, "upper"),
        ("upper.attachment", "Upper: Attachment", None, "upper"),
    ]
    if is_ready_sole:
        left_items.append(("sole_ready", "Sole: Ready-to-Use", None, None))
    else:
        left_items.append(("sole", "Sole: Lead", "sole", None))
        left_items.append(("sole.prep", "Sole: Prep / Buffing", None, "sole"))

    if is_heel:
        left_items.append(("heel_gola", "Heel/Gola: Lead", "heel_gola", None))
        left_items.append(("heel_gola.cutting", "Heel: Cover Cut / Prep", None, "heel_gola"))

    # Right: Bottom Track + Assembly Pipeline + Outside Work
    right_items = [
        ("bottom", "Bottom: Lead", "bottom", None),
        ("bottom.cutting", "Bottom: Cutting", None, "bottom"),
        ("bottom.stitching", "Bottom: Stitching", None, "bottom"),
        ("bottom.stamping", "Bottom: Stamping", None, "bottom"),
        ("bottom.assembly", "Bottom: Insole Prep", None, "bottom"),
        ("lasting", "Lasting Master", "lasting", None),
        ("sole_pasting", "Sole Pasting", "sole_pasting", None),
        ("finishing", "Finishing Tech", "finishing", None),
        ("qc_pack", "QC & Packing", "qc_pack", None),
    ]
    for o in outside_list:
        oname = o.get("name") or "Job Work"
        right_items.append(("outside", f"Out: {oname[:13]}", o, None))

    max_len = max(len(left_items), len(right_items))
    while len(left_items) < max_len:
        left_items.append(("blank", "Other / Special", None, None))
    while len(right_items) < max_len:
        right_items.append(("blank", "Other / Special", None, None))

    fs_h = 5.5 if compact else 7.5
    fs_r = 5.0 if compact else 7.0
    pad = 0.5 if compact else 2.0

    def format_row(item):
        k, label, extra, parent = item
        if k == "sole_ready":
            w_disp = "Vendor Supplied"
            r_disp = "—"
        elif k == "outside":
            v_name = (extra.get("vendor") or extra.get("vendor_name") or "Outside")[:14]
            w_disp = v_name
            rate_val = extra.get("rate")
            r_disp = f"Rs.{rate_val}" if rate_val is not None else ("___" if compact else "_____")
        elif k == "blank":
            w_disp = "____" if compact else "________"
            r_disp = "___" if compact else "____"
        else:
            asgn = assigns.get(k) or (assigns.get(extra) if extra else None) or (assigns.get(parent) if parent else None)
            w = asgn.get("worker_name") if asgn else ""
            r = asgn.get("rate_per_pair") if asgn else None
            if not w:
                w_disp = "____" if compact else "________"
            else:
                w_disp = f"{w[:12]} (L)" if (not assigns.get(k) and parent and assigns.get(parent) and compact) else w[:14]
            r_disp = f"Rs.{r}" if r is not None else ("___" if compact else "____")

        if with_rates:
            return [label, w_disp, r_disp, "___"]
        else:
            return [label, w_disp, "___"]

    left_rows = [["UPPER & SOLE SUB-TASKS", "KARIGAR", "RATE", "SIGN"] if with_rates else ["UPPER & SOLE SUB-TASKS", "KARIGAR", "SIGN"]]
    for it in left_items:
        left_rows.append(format_row(it))

    right_rows = [["BOTTOM & ASSEMBLY", "KARIGAR / VENDOR", "RATE", "SIGN"] if with_rates else ["BOTTOM & ASSEMBLY", "KARIGAR / VENDOR", "SIGN"]]
    for it in right_items:
        right_rows.append(format_row(it))

    col_w = [26 * mm, 32 * mm, 14 * mm, 18 * mm] if with_rates else [29 * mm, 35 * mm, 26 * mm]
    t_left = Table(left_rows, colWidths=col_w)
    t_right = Table(right_rows, colWidths=col_w)

    st_base = [
        ("BOX", (0, 0), (-1, -1), 0.8, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", fs_h),
        ("FONT", (0, 1), (-1, -1), "Helvetica", fs_r),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]
    for r_idx in range(1, len(left_rows)):
        if r_idx % 2 == 0:
            st_base.append(("BACKGROUND", (0, r_idx), (-1, r_idx), ZEBRA))
    if with_rates:
        st_base.append(("ALIGN", (2, 1), (2, -1), "RIGHT"))

    t_left.setStyle(TableStyle(st_base))
    t_right.setStyle(TableStyle(st_base))

    kar_t = Table([[t_left, t_right]], colWidths=[90 * mm, 90 * mm])
    kar_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # 6. Footer (Special Instructions & Quality Control)
    if compact:
        footer_t = Table([[
            Paragraph("<b>SPECIAL INSTRUCTIONS:</b> ____________________________________________________", ParagraphStyle("n", fontName="Helvetica", fontSize=5.5, leading=7)),
            Paragraph("<b>QC PASS:</b> [ ]   <b>SIGN:</b> ____________", ParagraphStyle("qc", fontName="Helvetica", fontSize=5.5, leading=7, alignment=1)),
        ]], colWidths=[120 * mm, 60 * mm])
        footer_t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, BLACK),
            ("LINEAFTER", (0, 0), (0, 0), 0.8, BLACK),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
    else:
        footer_t = Table([[
            Paragraph(
                "<b>SPECIAL INSTRUCTIONS / SHOP FLOOR NOTES:</b><br/><br/>"
                "________________________________________________________________<br/><br/>"
                "________________________________________________________________",
                ParagraphStyle("n", fontName="Helvetica", fontSize=7.5, leading=11)),
            Paragraph(
                "<b>QUALITY CONTROL:</b><br/>"
                "[ ] PASSED   [ ] REWORK<br/><br/>"
                "<b>SUPERVISOR SIGN:</b><br/>"
                "____________________",
                ParagraphStyle("qc", fontName="Helvetica", fontSize=7.5, leading=11, alignment=1)),
        ]], colWidths=[120 * mm, 60 * mm])
        footer_t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, BLACK),
            ("LINEAFTER", (0, 0), (0, 0), 1, BLACK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

    return [
        company,
        sp_xs,
        header_card,
        sp_xs,
        Paragraph("SIZE BREAKDOWN", S["h2"]),
        Spacer(1, 0.4 if compact else 1),
        size_t,
        sp_sm,
        Paragraph("MANUFACTURING PROCESS TALLY", S["h2"]),
        Spacer(1, 0.4 if compact else 1),
        tally_t,
        sp_sm,
        Paragraph("PROCESS SUB-TASKS & KARIGAR ASSIGNMENTS", S["h2"]),
        Spacer(1, 0.4 if compact else 1),
        kar_t,
        sp_sm,
        footer_t,
    ]


def build_production_card(job_group: dict, style: dict | None, with_rates: bool = True) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=8 * mm, bottomMargin=8 * mm,
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
        topMargin=4 * mm, bottomMargin=4 * mm,
        title=f"Dual Production Card {job_group.get('style_code','')}-{job_group.get('color','')}",
    )

    # Top half: Shop Floor Circulation (with_rates=False, compact=True)
    top_elements = _build_card_elements(job_group, style, with_rates=False, compact=True)

    # Dashed Cut Line
    cut_d = Drawing(180 * mm, 4 * mm)
    cut_d.add(Line(0, 2 * mm, 180 * mm, 2 * mm, strokeWidth=1, strokeColor=BLACK, strokeDashArray=[4, 4]))
    cut_d.add(String(90 * mm, 0.5 * mm, "✂  CUT HERE  (Top: Shop Floor Circulation  |  Bottom: Admin Retention)  ✂", fontName="Helvetica-Bold", fontSize=6, textAnchor="middle"))

    # Bottom half: Admin Retention (with_rates=True, compact=True)
    bottom_elements = _build_card_elements(job_group, style, with_rates=True, compact=True)

    elements = top_elements + [cut_d] + bottom_elements
    doc.build(elements)
    return buf.getvalue()
