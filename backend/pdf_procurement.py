"""PDF: Material Requirement Sheet (procurement)."""
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


BLACK = colors.black
HEAD_BG = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#C27842")
LIGHT = colors.HexColor("#F1F5F9")
LINE = colors.HexColor("#94A3B8")


def _fmt(n, d=2):
    try:
        v = float(n or 0)
    except Exception:
        return str(n or "")
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.{d}f}"


SWATCH_CATEGORIES = {"upper", "lining", "sole", "insole", "bottom"}


def _make_swatch_box(color_text: str = ""):
    box = Table([[""]], colWidths=[14 * mm], rowHeights=[9 * mm])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BLACK),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    clean_color = (color_text or "").strip()
    if clean_color:
        color_p = Paragraph(
            clean_color,
            ParagraphStyle(
                "swatch_color",
                fontName="Helvetica-Bold",
                fontSize=6.5,
                leading=7.5,
                alignment=1,
                textColor=colors.HexColor("#0F172A"),
            )
        )
        cell_table = Table([[box], [color_p]], colWidths=[18 * mm])
        cell_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return cell_table
    return box


def build_material_requirement(scope_label: str, jobs_summary: list[dict],
                               material_lines: list[dict], notes: str = "") -> bytes:
    """
    jobs_summary: [{po_number, style_code, color, total_pairs, sizes_text}]
    material_lines: [{code, name, category, unit, rate, total_qty_required, total_cost, color}]
    """
    S = getSampleStyleSheet()
    title_style = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, textColor=BLACK, leading=18)
    sub_style = ParagraphStyle("s", fontName="Helvetica", fontSize=9, textColor=BLACK, leading=11)
    label = ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT, leading=10)
    para = ParagraphStyle("p", fontName="Helvetica", fontSize=9, textColor=BLACK, leading=11)
    small = ParagraphStyle("sm", fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#475569"), leading=8)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="Material Requirement Sheet",
    )

    # Header
    header_cell = [
        Paragraph("SSK FOOTCARE MANUFACTURING LLP", title_style),
        Paragraph('REHAB BLDG "F" WING JAY AMBE SRA, NEAR SHELL COLONY, OFF EASTERN EXPRESS, CHEMBUR, MUMBAI-400071', sub_style),
        Paragraph("<b>GSTIN:</b> 27AFKFS4410F1Z2", sub_style),
    ]
    header_t = Table([[header_cell]], colWidths=[180 * mm])
    header_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))

    title_t = Table([[Paragraph("<b>MATERIAL REQUIREMENT SHEET</b>",
                                ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=13, alignment=1, leading=15))]],
                    colWidths=[180 * mm])
    title_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    meta_data = [
        [Paragraph("<b>Scope :</b>", label), Paragraph(scope_label, para),
         Paragraph("<b>Date :</b>", label), Paragraph(datetime.now().strftime("%d/%m/%Y"), para)],
        [Paragraph("<b>Total Pairs :</b>", label),
         Paragraph(f"{sum(j['total_pairs'] for j in jobs_summary):,}", para),
         Paragraph("<b>Materials :</b>", label), Paragraph(str(len(material_lines)), para)],
    ]
    meta_t = Table(meta_data, colWidths=[22 * mm, 68 * mm, 22 * mm, 68 * mm])
    meta_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
    ]))

    # Jobs included
    jobs_rows = [["#", "PO Number", "Style", "Color", "Pairs", "Sizes"]]
    for i, j in enumerate(jobs_summary, 1):
        jobs_rows.append([
            str(i), j.get("po_number", ""), j.get("style_code", ""), j.get("color", ""),
            str(j.get("total_pairs", 0)), j.get("sizes_text", "")
        ])
    jobs_t = Table(jobs_rows, colWidths=[10 * mm, 30 * mm, 35 * mm, 30 * mm, 20 * mm, 55 * mm])
    jobs_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (4, 1), (4, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # Material requirement table
    mat_rows = [["#", "Code", "Material", "Category", "Unit", "Qty Required", "Rate", "Total Cost", "Swatch"]]
    row_heights = [None]
    total_cost = 0.0
    for i, m in enumerate(material_lines, 1):
        cat = (m.get("category") or "").strip().lower()
        color_val = (m.get("color") or "").strip()
        if cat in SWATCH_CATEGORIES:
            swatch_cell = _make_swatch_box(color_val)
            row_heights.append(15 * mm if color_val else 13 * mm)
        else:
            swatch_cell = "—"
            row_heights.append(None)

        mat_rows.append([
            str(i),
            m.get("code", ""),
            m.get("name", ""),
            m.get("category", ""),
            m.get("unit", ""),
            _fmt(m.get("total_qty_required", 0), 2),
            f"Rs.{_fmt(m.get('rate', 0), 2)}",
            f"Rs.{_fmt(m.get('total_cost', 0), 2)}",
            swatch_cell,
        ])
        total_cost += m.get("total_cost", 0)

    row_heights.append(None)
    mat_rows.append([
        "", "", "", "", "", Paragraph("<b>TOTAL</b>", ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=9, alignment=2)),
        "", Paragraph(f"<b>Rs.{_fmt(total_cost, 2)}</b>", ParagraphStyle("b2", fontName="Helvetica-Bold", fontSize=10, alignment=2)),
        ""
    ])

    mat_t = Table(mat_rows, colWidths=[8 * mm, 20 * mm, 50 * mm, 18 * mm, 10 * mm, 18 * mm, 16 * mm, 20 * mm, 20 * mm], rowHeights=row_heights)
    mat_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -2), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -2), "Helvetica", 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (4, 0), (-2, -1), "RIGHT"),
        ("ALIGN", (4, 1), (4, -2), "CENTER"),
        ("ALIGN", (8, 0), (8, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BLACK),
    ]))

    elements = [
        header_t,
        title_t,
        Spacer(1, 6),
        meta_t,
        Spacer(1, 10),
        Paragraph("<b>Jobs included</b>", label),
        Spacer(1, 4),
        jobs_t,
        Spacer(1, 12),
        Paragraph("<b>Materials required</b>", label),
        Spacer(1, 4),
        mat_t,
        Spacer(1, 14),
        Paragraph("Notes:", label),
        Paragraph(notes or "Quantities include waste % as defined in the style BOM. Yield-per-unit factored in. "
                          "Verify with supplier before placing order.", small),
        Spacer(1, 30),
        Paragraph("_______________________________<br/>Procurement Officer",
                  ParagraphStyle("sig", fontName="Helvetica", fontSize=9, alignment=2, leading=11)),
    ]
    doc.build(elements)
    return buf.getvalue()
