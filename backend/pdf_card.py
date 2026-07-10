"""PDF: Printable Production Card (A4 — fits inside 180mm usable width)."""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from pdf_image import load_image_for_pdf

BLACK = colors.black
HEAD = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#C27842")
LINE = colors.HexColor("#94A3B8")
LIGHT = colors.HexColor("#F1F5F9")
WHITE = colors.white

# A4 usable width = 210 - 12 - 12 = 186mm; we pick 180mm with a 3mm safety on each side.
USABLE_MM = 180


def _img_from_dataurl(image_url: str, max_h_mm: float = 50, max_w_mm: float = 50):
    """Backward-compatible thin wrapper — kept for any external caller that
    still references this symbol.  All real work happens in
    pdf_image.load_image_for_pdf() so every PDF generator shares one
    implementation of URL → sized reportlab Image."""
    return load_image_for_pdf(image_url, max_h_mm=max_h_mm, max_w_mm=max_w_mm)


def build_production_card(job_group: dict, style: dict | None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f"Production Card {job_group.get('style_code','')}-{job_group.get('color','')}",
    )
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

    # --- Company strip (180mm) — company name now WHITE so it's visible on dark bg ---
    company = Table(
        [[
            Paragraph("SSK FOOTCARE MANUFACTURING LLP", S["h_co"]),
            Paragraph(f"Production Card · {datetime.now().strftime('%d %b %Y %H:%M')}", S["co_sub"]),
        ]],
        colWidths=[120 * mm, 60 * mm],
    )
    company.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), HEAD),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    # --- Header card (image | info | color/qty) — total 180mm = 50+90+40 ---
    img_cell = load_image_for_pdf(
        style or {},   # full dict — helper picks the display variant, not the 1600px original
        max_h_mm=46, max_w_mm=46,
    )
    if img_cell is None:
        img_cell = Table([[Paragraph("No Image", ParagraphStyle("ni", fontName="Helvetica", fontSize=8, alignment=1))]],
                         colWidths=[46 * mm], rowHeights=[46 * mm])
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
    info_t = Table(info_rows, colWidths=[20 * mm, 70 * mm])
    info_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))

    color_qty = Table([
        [Paragraph("COLOR", S["lab"])],
        [Paragraph(job_group.get("color", "—"), S["huge_color"])],
        [Spacer(1, 4)],
        [Paragraph("TOTAL PAIRS", S["lab"])],
        [Paragraph(str(job_group.get("total_qty", 0)), S["huge_qty"])],
    ], colWidths=[40 * mm])
    color_qty.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, ACCENT),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    header_card = Table([[img_cell, info_t, color_qty]],
                        colWidths=[50 * mm, 90 * mm, 40 * mm])
    header_card.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    # --- SIZE BREAKDOWN: fits exactly 180mm ---
    sizes = job_group.get("sizes", [])
    n = max(len(sizes), 1)
    # Reserve 36mm for label + 22mm for TOTAL col → split the rest
    remaining = USABLE_MM - 36 - 22
    size_col_w = max(8, remaining / n)
    size_data = [["SIZE"] + [str(s["size"]) for s in sizes] + ["TOTAL"]]
    qty_row = [job_group.get("color", "")] + [str(s["quantity"]) for s in sizes] + [str(job_group.get("total_qty", 0))]
    size_data.append(qty_row)
    size_t = Table(size_data, colWidths=[36 * mm] + [size_col_w * mm] * n + [22 * mm])
    size_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("FONT", (0, 1), (-1, -1), "Helvetica-Bold", 12),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (-1, 1), (-1, 1), LIGHT),
        ("TEXTCOLOR", (-1, 1), (-1, 1), ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # --- PROCESS TALLY: fits exactly 180mm ---
    proc_rows = ["CUTTING", "UPPER", "BOTTOM", "STITCHING", "LASTING", "SOLE PASTING", "FINISH / QC"]
    tally_header = ["PROCESS"] + [str(s["size"]) for s in sizes] + ["DONE", "REJ", "SIGN"]
    tally_data = [tally_header]
    tally_data.append(["PLANNED"] + [str(s["quantity"]) for s in sizes] + [str(job_group.get("total_qty", 0)), "—", "—"])
    for label in proc_rows:
        tally_data.append([label] + ["" for _ in sizes] + ["", "", ""])
    # 30 + n*x + 12 + 10 + 28 = 180  =>  x = (180-80)/n
    tally_size_w = max(7, (USABLE_MM - 30 - 12 - 10 - 28) / n)
    tally_t = Table(
        tally_data,
        colWidths=[30 * mm] + [tally_size_w * mm] * n + [12 * mm, 10 * mm, 28 * mm],
    )
    tally_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
        ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 7.5),
        ("FONT", (1, 1), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
        ("TEXTCOLOR", (0, 1), (-1, 1), ACCENT),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, 1), 1, BLACK),
    ]))

    # --- Components (Upper / Bottom / Sole) — 180mm = 60+60+60 ---
    comp = job_group.get("components", {}) or {}

    def comp_cell(title, done, layers):
        check = "[X]" if done else "[ ]"
        layer_lines = "<br/>".join([f"   - {l}" for l in layers])
        return Paragraph(
            f"<font size=11><b>{check} {title}</b></font><br/><font size=7 color='#475569'>{layer_lines}</font>",
            ParagraphStyle("c", fontName="Helvetica", fontSize=9, leading=11),
        )

    comp_t = Table([[
        comp_cell("UPPER", comp.get("upper_done"),
                  ["Upper Top", "Mid Layer / Reinforcement", "Lining"]),
        comp_cell("BOTTOM / INSOLE", comp.get("bottom_done"),
                  ["Bottom Layer", "Insole Board + Cushion", "Insole Cover"]),
        comp_cell("SOLE", comp.get("sole_done"), ["Outsole"]),
    ]], colWidths=[60 * mm, 60 * mm, 60 * mm])
    comp_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("LINEAFTER", (0, 0), (-2, -1), 1, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))

    # --- Karigar assignments — 180mm = 35+60+25+60 ---
    assigns = job_group.get("assignments", {}) or {}
    role_labels = [
        ("cutting", "CUTTING"), ("upper", "UPPER"), ("bottom", "BOTTOM"),
        ("stitching", "STITCHING"), ("lasting", "LASTING"),
        ("sole_pasting", "SOLE PASTING"), ("finishing", "FINISHING"),
    ]
    kar_rows = [["ROLE", "KARIGAR", "RATE / PAIR", "SIGN"]]
    for rk, rl in role_labels:
        a = assigns.get(rk) or {}
        kar_rows.append([
            rl,
            a.get("worker_name", "_______________"),
            f"Rs.{a.get('rate_per_pair', '')}" if a.get("rate_per_pair") is not None else "_______",
            "________________",
        ])
    kar_t = Table(kar_rows, colWidths=[35 * mm, 60 * mm, 25 * mm, 60 * mm])
    kar_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # --- Footer — 180mm = 120+60 ---
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

    elements = [
        company,
        Spacer(1, 4),
        header_card,
        Spacer(1, 5),
        Paragraph("SIZE BREAKDOWN", S["h2"]),
        Spacer(1, 1),
        size_t,
        Spacer(1, 6),
        Paragraph("PROCESS TALLY · Fill in qty processed per size at each stage", S["h2"]),
        Spacer(1, 1),
        tally_t,
        Spacer(1, 6),
        Paragraph("COMPONENTS", S["h2"]),
        Spacer(1, 1),
        comp_t,
        Spacer(1, 6),
        Paragraph("KARIGAR ASSIGNMENTS", S["h2"]),
        Spacer(1, 1),
        kar_t,
        Spacer(1, 6),
        footer_t,
    ]
    doc.build(elements)
    return buf.getvalue()
