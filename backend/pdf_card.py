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

    h_style_fs = (8.5 if compact else 13) if len(style_display) > 16 else (11 if compact else 18)
    h_style_lead = h_style_fs + 2
    h_style_p = Paragraph(f"<b>{style_display}</b>", ParagraphStyle("hst_dyn", fontName="Helvetica-Bold", fontSize=h_style_fs, leading=h_style_lead, textColor=BLACK))

    info_rows = [
        [Paragraph("PO NUMBER", S["lab"]), Paragraph(job_group.get("po_number", "—"), S["valb"])],
        [Paragraph("CLIENT", S["lab"]), Paragraph(job_group.get("client_name", "—"), S["val"])],
        [Paragraph("STYLE", S["lab"]), h_style_p],
        [Paragraph("ARTICLE", S["lab"]), Paragraph((style or {}).get("name", "") or job_group.get("description", "—"), S["val"])],
        [Paragraph("CREATED", S["lab"]), Paragraph(card_created_date, S["val"])],
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
    tracks = job_group.get("component_tracks", {}) or {}
    specs = job_group.get("component_specs", {}) or {}
    is_heel = specs.get("footwear_type") == "heel"

    upper_done = (tracks.get("upper", {}).get("status") == "ready") if "upper" in tracks else comp.get("upper_done")
    bottom_done = (tracks.get("bottom", {}).get("status") == "ready") if "bottom" in tracks else comp.get("bottom_done")
    sole_done = (tracks.get("sole", {}).get("status") == "ready") if "sole" in tracks else comp.get("sole_done")

    c1 = _build_comp_cell("UPPER", upper_done, ["Upper Top", "Mid Layer / Reinforce", "Lining"], compact=compact)
    c2 = _build_comp_cell("BOTTOM / INSOLE", bottom_done, ["Bottom Layer", "Insole Board+Cushion", "Insole Cover"], compact=compact)
    c3 = _build_comp_cell("SOLE", sole_done, ["Outsole"], compact=compact)

    if is_heel:
        heel_done = (tracks.get("heel_gola", {}).get("status") == "ready") if "heel_gola" in tracks else False
        c4 = _build_comp_cell("HEEL / GOLA", heel_done, ["Heel / Platform", "Cover / Gola"], compact=compact)
        comp_t = Table([[c1, c2, c3, c4]], colWidths=[45 * mm, 45 * mm, 45 * mm, 45 * mm])
    else:
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

    # --- Process Sub-tasks & Karigar Assignments ---
    assigns = job_group.get("assignments", {}) or {}
    outside_list = job_group.get("outside_labour", []) or []
    if not outside_list and style and style.get("outside_labour"):
        outside_list = style.get("outside_labour") or []

    specs = job_group.get("component_specs", {}) or (style.get("component_specs") if style else {}) or {}
    is_heel = (job_group.get("footwear_type") == "heel") or (specs.get("footwear_type") == "heel") or (style and style.get("footwear_type") == "heel") or bool(assigns.get("heel_gola"))
    is_ready_sole = job_group.get("sole_ready_to_use") or (style and (style.get("sole_ready_to_use") or style.get("ready_to_use_sole")))

    # Left Column: Upper Track & Sole Track (+ Heel if heel style)
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

    # Right Column: Bottom / Insole Track + Assembly Pipeline + Outside Work
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

    col_w = [25.5 * mm, 31 * mm, 15 * mm, 18 * mm] if with_rates else [28.5 * mm, 34 * mm, 27 * mm]
    t_left = Table(left_rows, colWidths=col_w)
    t_right = Table(right_rows, colWidths=col_w)

    st = [
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
    if with_rates:
        st.append(("ALIGN", (2, 1), (2, -1), "RIGHT"))
    t_left.setStyle(TableStyle(st))
    t_right.setStyle(TableStyle(st))

    kar_t = Table([[t_left, t_right]], colWidths=[89.5 * mm, 89.5 * mm])
    kar_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

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
        Paragraph("PROCESS SUB-TASKS & KARIGAR ASSIGNMENTS", S["h2"]),
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
