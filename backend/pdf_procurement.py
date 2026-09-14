"""PDF: Material Requirement Sheet (procurement)."""
import re
from io import BytesIO
from datetime import datetime
from typing import Optional, Any
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


SWATCH_CATEGORIES = {
    "upper", "lining", "sole", "insole", "bottom",
    "upper top", "upper lining", "insole cover", "insole board", "bottom layer", "sockliner"
}


def _is_swatch_item(category: str = "", color: str = "") -> bool:
    if (color or "").strip():
        return True
    c = (category or "").strip().lower()
    if not c:
        return False
    if c in SWATCH_CATEGORIES:
        return True
    return any(kw in c for kw in ("upper", "lining", "sole", "insole", "bottom", "cover", "sock"))


def _make_swatch_box(color_text: str = ""):
    box = Table([[""]], colWidths=[10 * mm], rowHeights=[6 * mm])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, BLACK),
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
                fontSize=6,
                leading=7,
                alignment=1,
                textColor=colors.HexColor("#0F172A"),
            )
        )
        cell_table = Table([[box], [color_p]], colWidths=[12 * mm])
        cell_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return cell_table
    return box


def generate_material_requirement_sheet(
    style: dict,
    color: Optional[str] = None,
    pairs: int = 1,
    po_number: str = "",
    scope_label: Optional[str] = None,
    notes: str = "",
) -> bytes:
    """Generate a Material Requirement Sheet PDF for a given style and color (e.g. the PO's actual color).

    Sources each line's printed color from get_effective_bom(style, color)'s result, ensuring
    both base colors (when no override exists) and variant-specific overridden colors are correctly printed.
    """
    from routes.styles import get_effective_bom

    effective_bom = get_effective_bom(style, color)
    material_lines = []
    for b_item in effective_bom:
        b = b_item.model_dump() if hasattr(b_item, "model_dump") else (b_item if isinstance(b_item, dict) else dict(b_item))
        code = b.get("material_code") or ""
        name = b.get("material_name") or ""
        cat = b.get("section") or "other"
        unit = b.get("unit") or ""
        rate = float(b.get("rate") or 0.0)
        color_val = (b.get("color") or "").strip()
        qty = float(b.get("quantity") or 1.0)
        yld = float(b.get("yield_per_unit") or 1.0)
        if yld <= 0:
            yld = 1.0
        waste = float(b.get("waste_pct") or 0.0)
        per_pair = (qty / yld) * (1 + waste / 100)
        tot_qty = round(per_pair * pairs, 2)
        vendor_name = (b.get("preferred_vendor_name") or b.get("vendor_name") or b.get("vendor") or b.get("supplier") or "").strip()
        material_lines.append({
            "code": code,
            "name": name,
            "category": cat,
            "unit": unit,
            "rate": rate,
            "total_qty_required": tot_qty,
            "total_cost": round(tot_qty * rate, 2),
            "color": color_val,
            "preferred_vendor_name": vendor_name,
        })

    po_num = po_number or f"PO-{style.get('code', 'STYLE')}"
    jobs_summary = [{
        "po_number": po_num,
        "style_code": style.get("code", ""),
        "color": color or "",
        "total_pairs": pairs,
        "sizes_text": str(style.get("base_size", "")),
    }]
    label = scope_label or f"{style.get('code', 'Style')} ({color or 'Base'})"
    return build_material_requirement(label, jobs_summary, material_lines, notes)


def _build_materials_table_flowable(material_lines_sorted, header_bg=HEAD_BG, total_title="TOTAL"):
    mat_rows = [["#", "Code", "Material", "Category", "Vendor", "Unit", "Qty Required", "Rate", "Total Cost", "Swatch"]]
    total_cost = 0.0
    for i, m in enumerate(material_lines_sorted, 1):
        cat = (m.get("category") or "").strip().lower()
        color_val = (m.get("color") or "").strip()
        if _is_swatch_item(cat, color_val):
            swatch_cell = _make_swatch_box(color_val)
        else:
            swatch_cell = Paragraph("—", ParagraphStyle("no_sw", fontName="Helvetica", fontSize=8, alignment=1, textColor=colors.HexColor("#94A3B8")))

        mat_name = m.get("name", "") or m.get("code", "")
        size_bd = m.get("size_breakdown")
        if cat == "sole" and size_bd:
            bd_parts = [f"{sz}:{_fmt(qty)}" for sz, qty in size_bd.items()]
            bd_text = "  ".join(bd_parts)
            mat_cell = [
                Paragraph(mat_name, ParagraphStyle("mat_n", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=BLACK)),
                Paragraph(f"<font color='#C27842'><b>Sizes:</b></font> <font color='#334155'>{bd_text}</font>",
                          ParagraphStyle("mat_s", fontName="Helvetica", fontSize=6.5, leading=8))
            ]
        elif color_val:
            mat_cell = [
                Paragraph(mat_name, ParagraphStyle("mat_n", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=BLACK)),
                Paragraph(f"<font color='#64748B'>Variant Color: </font><font color='#0F172A'><b>{color_val}</b></font>",
                          ParagraphStyle("mat_col", fontName="Helvetica", fontSize=6.5, leading=8))
            ]
        else:
            mat_cell = Paragraph(mat_name, ParagraphStyle("mat_n", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=BLACK))

        vendor_val = (m.get("preferred_vendor_name") or m.get("vendor_name") or m.get("vendor") or m.get("supplier") or "").strip()

        mat_rows.append([
            Paragraph(str(i), ParagraphStyle("mat_idx", fontName="Helvetica", fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor("#475569"))),
            Paragraph(m.get("code", ""), ParagraphStyle("mat_c", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.HexColor("#0F172A"))),
            mat_cell,
            Paragraph(cat.capitalize(), ParagraphStyle("mat_cat", fontName="Helvetica", fontSize=7.5, leading=9, textColor=colors.HexColor("#334155"))),
            Paragraph(vendor_val or "—", ParagraphStyle("mat_vnd", fontName="Helvetica-Bold" if vendor_val else "Helvetica", fontSize=7.5, leading=9, textColor=colors.HexColor("#0F172A") if vendor_val else colors.HexColor("#94A3B8"))),
            Paragraph(m.get("unit", ""), ParagraphStyle("mat_u", fontName="Helvetica", fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor("#475569"))),
            Paragraph(_fmt(m.get("total_qty_required", 0), 2), ParagraphStyle("mat_q", fontName="Helvetica-Bold", fontSize=8, leading=9.5, alignment=2, textColor=colors.HexColor("#0F172A"))),
            Paragraph(f"Rs.{_fmt(m.get('rate', 0), 2)}", ParagraphStyle("mat_r", fontName="Helvetica", fontSize=7.5, leading=9, alignment=2, textColor=colors.HexColor("#475569"))),
            Paragraph(f"Rs.{_fmt(m.get('total_cost', 0), 2)}", ParagraphStyle("mat_tc", fontName="Helvetica-Bold", fontSize=8, leading=9.5, alignment=2, textColor=colors.HexColor("#0F172A"))),
            swatch_cell,
        ])
        total_cost += m.get("total_cost", 0)

    # Bottom TOTAL row (spans cols 0 to 7)
    mat_rows.append([
        Paragraph(f"<b>{total_title}</b>", ParagraphStyle("b", fontName="Helvetica-Bold", fontSize=9, alignment=2, textColor=colors.HexColor("#0F172A"))),
        "", "", "", "", "", "", "",
        Paragraph(f"<b>Rs.{_fmt(total_cost, 2)}</b>", ParagraphStyle("b2", fontName="Helvetica-Bold", fontSize=9.5, alignment=2, textColor=colors.HexColor("#0F172A"))),
        ""
    ])

    mat_t = Table(mat_rows, colWidths=[7 * mm, 22 * mm, 37 * mm, 17 * mm, 26 * mm, 11 * mm, 17 * mm, 16 * mm, 23 * mm, 14 * mm], repeatRows=1)
    
    table_styles = [
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -2), 0.4, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (5, 0), (5, -2), "CENTER"),
        ("ALIGN", (6, 0), (8, -2), "RIGHT"),
        ("ALIGN", (9, 0), (9, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
    ]
    for r in range(1, len(mat_rows) - 1):
        bg = colors.white if r % 2 == 1 else colors.HexColor("#F8FAFC")
        table_styles.append(("BACKGROUND", (0, r), (-1, r), bg))

    table_styles.extend([
        ("SPAN", (0, -1), (7, -1)),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, BLACK),
        ("TOPPADDING", (0, -1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
    ])
    mat_t.setStyle(TableStyle(table_styles))
    return mat_t


def build_material_requirement(
    scope_label: Any,
    jobs_summary: Any = None,
    material_lines: Any = None,
    notes: str = "",
    *,
    style: Optional[dict] = None,
    color: Optional[str] = None,
    pairs: int = 1,
    split_by_color: bool = False,
    by_color: Optional[dict] = None,
    is_merged: bool = False,
) -> bytes:
    """
    jobs_summary: [{po_number, style_code, color, total_pairs, sizes_text}]
    material_lines: [{code, name, category, unit, rate, total_qty_required, total_cost, color, preferred_vendor_name}]
    split_by_color: whether to render distinct per-color tables
    by_color: {color_name: {color, total_pairs, materials}}
    """
    # If style is passed directly (first arg or kwarg), delegate to generate_material_requirement_sheet
    if style is not None or (isinstance(scope_label, dict) and ("bom" in scope_label or "color_bom_overrides" in scope_label or "code" in scope_label)):
        actual_style = style if style is not None else scope_label
        actual_color = color if color is not None else (jobs_summary if isinstance(jobs_summary, str) else None)
        actual_pairs = pairs if pairs != 1 else (material_lines if isinstance(material_lines, (int, float)) else 1)
        actual_notes = notes if notes else (material_lines if isinstance(material_lines, str) else "")
        return generate_material_requirement_sheet(
            style=actual_style,
            color=actual_color,
            pairs=int(actual_pairs),
            notes=str(actual_notes),
        )

    if jobs_summary is None:
        jobs_summary = []
    if material_lines is None:
        material_lines = []
    S = getSampleStyleSheet()
    title_style = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15, textColor=BLACK, leading=17)
    sub_style = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, textColor=BLACK, leading=10.5)
    label = ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT, leading=10)
    para = ParagraphStyle("p", fontName="Helvetica", fontSize=8.5, textColor=BLACK, leading=10.5)
    small = ParagraphStyle("sm", fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#475569"), leading=8.5)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title="Material Requirement Sheet",
    )

    # Header
    header_cell = [
        Paragraph("SSK FOOTCARE MANUFACTURING LLP", title_style),
        Paragraph('REHAB BLDG "F" WING JAY AMBE SRA, NEAR SHELL COLONY, OFF EASTERN EXPRESS, CHEMBUR, MUMBAI-400071', sub_style),
        Paragraph("<b>GSTIN:</b> 27AFKFS4410F1Z2", sub_style),
    ]
    header_t = Table([[header_cell]], colWidths=[190 * mm])
    header_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))

    merged_sheet = bool(
        is_merged
        or (isinstance(scope_label, str) and (
            "merged" in scope_label.lower()
            or "consolidated" in scope_label.lower()
            or bool(re.search(r'\b\d+\s+(?:procurement\s+)?cards?\b', scope_label.lower()))
        ))
        or (isinstance(jobs_summary, list) and len({j.get("po_number") for j in jobs_summary if isinstance(j, dict) and j.get("po_number")}) > 1)
    )
    if merged_sheet:
        split_by_color = False

    sheet_title = "CONSOLIDATED MATERIAL REQUIREMENT SHEET" if merged_sheet else "MATERIAL REQUIREMENT SHEET"
    title_t = Table([[Paragraph(f"<b>{sheet_title}</b>",
                                ParagraphStyle("ti", fontName="Helvetica-Bold", fontSize=12, alignment=1, leading=14, textColor=colors.white))]],
                    colWidths=[190 * mm])
    title_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEAD_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    unique_vendors = sorted(list({
        (m.get("preferred_vendor_name") or m.get("vendor_name") or m.get("vendor") or "").strip()
        for m in material_lines
        if (m.get("preferred_vendor_name") or m.get("vendor_name") or m.get("vendor") or "").strip()
    }))
    v_count_txt = f" ({len(unique_vendors)} vendor{'s' if len(unique_vendors) != 1 else ''})" if unique_vendors else ""

    meta_data = [
        [Paragraph("<b>Scope :</b>", label), Paragraph(str(scope_label), para),
         Paragraph("<b>Date :</b>", label), Paragraph(datetime.now().strftime("%d/%m/%Y"), para)],
        [Paragraph("<b>Total Pairs :</b>", label),
         Paragraph(f"{sum(j.get('total_pairs', 0) for j in jobs_summary):,}", para),
         Paragraph("<b>Materials :</b>", label), Paragraph(f"{len(material_lines)} items{v_count_txt}", para)],
    ]
    meta_t = Table(meta_data, colWidths=[24 * mm, 71 * mm, 24 * mm, 71 * mm])
    meta_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
    ]))

    # Jobs included
    jobs_rows = [["#", "PO Number", "Style", "Color", "Pairs", "Sizes"]]
    for i, j in enumerate(jobs_summary, 1):
        jobs_rows.append([
            Paragraph(str(i), ParagraphStyle("j_i", fontName="Helvetica", fontSize=8, alignment=1, textColor=colors.HexColor("#475569"))),
            Paragraph(str(j.get("po_number", "")), ParagraphStyle("j_po", fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#0F172A"))),
            Paragraph(str(j.get("style_code", "")), ParagraphStyle("j_st", fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT)),
            Paragraph(str(j.get("color", "")), ParagraphStyle("j_col", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#0F172A"))),
            Paragraph(f"{j.get('total_pairs', 0):,}", ParagraphStyle("j_p", fontName="Helvetica-Bold", fontSize=8, alignment=2, textColor=colors.HexColor("#0F172A"))),
            Paragraph(str(j.get("sizes_text", "")), ParagraphStyle("j_sz", fontName="Helvetica", fontSize=7.5, leading=9, textColor=colors.HexColor("#334155"))),
        ])
    jobs_t = Table(jobs_rows, colWidths=[8 * mm, 32 * mm, 35 * mm, 28 * mm, 22 * mm, 65 * mm])
    jobs_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))

    # Material requirement table
    material_lines_sorted = sorted(
        material_lines,
        key=lambda m: (
            str(m.get("category") or "").strip().lower(),
            str(m.get("code") or "").strip(),
            str(m.get("color") or "").strip()
        )
    )

    elements = [
        header_t,
        title_t,
        Spacer(1, 4),
        meta_t,
        Spacer(1, 7),
        Paragraph("<b>Jobs included</b>", label),
        Spacer(1, 3),
        jobs_t,
    ]

    has_multi_colors = by_color and len(by_color) > 1
    if split_by_color and has_multi_colors:
        # Render each color variant section
        for col_name, col_data in by_color.items():
            col_pairs = col_data.get("total_pairs", 0)
            col_materials = sorted(
                col_data.get("materials", []),
                key=lambda m: (
                    str(m.get("category") or "").strip().lower(),
                    str(m.get("code") or "").strip(),
                    str(m.get("color") or "").strip()
                )
            )
            col_banner = Table(
                [[Paragraph(f"<b>COLOR VARIANT: {col_name.upper()} &nbsp;·&nbsp; {col_pairs} PAIRS</b>",
                            ParagraphStyle("col_h", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white))]],
                colWidths=[190 * mm]
            )
            col_banner.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#7C3AED")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(Spacer(1, 8))
            elements.append(col_banner)
            elements.append(Spacer(1, 3))
            elements.append(_build_materials_table_flowable(
                col_materials,
                header_bg=colors.HexColor("#5B21B6"),
                total_title=f"SUBTOTAL ({col_name.upper()})"
            ))

        # Followed by consolidated all-colors table
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("<b>CONSOLIDATED TOTAL REQUIREMENT (ALL COLORS)</b>", label))
        elements.append(Spacer(1, 3))
        elements.append(_build_materials_table_flowable(
            material_lines_sorted,
            header_bg=HEAD_BG,
            total_title="GRAND TOTAL"
        ))
    else:
        # Standard consolidated table
        elements.append(Spacer(1, 8))
        req_heading = "<b>CONSOLIDATED MATERIALS REQUIRED</b>" if merged_sheet else "<b>Materials required</b>"
        total_txt = "CONSOLIDATED TOTAL" if merged_sheet else "TOTAL"
        elements.append(Paragraph(req_heading, label))
        elements.append(Spacer(1, 3))
        elements.append(_build_materials_table_flowable(
            material_lines_sorted,
            header_bg=HEAD_BG,
            total_title=total_txt
        ))

    elements.extend([
        Spacer(1, 8),
        Paragraph("Notes:", label),
        Paragraph(notes or "Quantities include waste % as defined in the style BOM. Yield-per-unit factored in. "
                           "Verify with supplier before placing order.", small),
        Spacer(1, 14),
        Paragraph("_______________________________<br/>Procurement Officer",
                  ParagraphStyle("sig", fontName="Helvetica", fontSize=8.5, alignment=2, leading=11)),
    ])
    doc.build(elements)
    return buf.getvalue()
