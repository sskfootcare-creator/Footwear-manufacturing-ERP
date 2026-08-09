"""PDF: Carton Labels — A4, 2 labels per page (Monochrome / High Contrast for Laser Printers).

Each label corresponds to one packing_cartons row (one box).
Layout (per label, top to bottom):
  [VENDOR STRIP]  SSK FOOTCARE MANUFACTURING LLP
  [ROW]  PO No.  |  Box No. (big)  |  Invoice No.
  [EAN]  EAN code large
  [GOODS] Style  |  Color  |  Size (large)  |  Qty (big)
"""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4          # 595.28 x 841.89 pts
MARGIN = 10 * mm
LABEL_W = PAGE_W - 2 * MARGIN
LABEL_H = (PAGE_H - 3 * MARGIN) / 2   # 2 labels per page with gap

VENDOR_NAME = "SSK FOOTCARE MANUFACTURING LLP"
BLACK = colors.black


def _draw_label(c: canvas.Canvas, x: float, y: float, carton: dict,
                po_number: str, invoice_no: str) -> None:
    """Draw a single label inside the bounding box (x, y) bottom-left corner."""
    w, h = LABEL_W, LABEL_H

    # Outer border (solid 1pt black line for laser printing)
    c.setStrokeColor(BLACK)
    c.setLineWidth(1.0)
    c.rect(x, y, w, h)

    # ── VENDOR STRIP (top 12mm) — Clean text, no background fill ─────────────
    strip_h = 12 * mm
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.8)
    c.line(x, y + h - strip_h, x + w, y + h - strip_h)

    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(x + w / 2, y + h - strip_h + 3.5 * mm, VENDOR_NAME)

    # ── PO / BOX / INVOICE ROW (next 18mm) ──────────────────────────────────
    row1_y = y + h - strip_h - 18 * mm
    row1_h = 18 * mm
    col = w / 3

    # Dividers
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.6)
    c.line(x + col, row1_y, x + col, row1_y + row1_h)
    c.line(x + 2 * col, row1_y, x + 2 * col, row1_y + row1_h)
    c.line(x, row1_y, x + w, row1_y)

    def _cell(cx, val_text, label_text, big=False):
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(cx, row1_y + row1_h - 4.5 * mm, label_text)
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 14 if big else 10)
        c.drawCentredString(cx, row1_y + 3.5 * mm, val_text)

    _cell(x + col / 2,       po_number or "—",             "PO NUMBER")
    box_num = carton.get("box_number") or "—"
    total = carton.get("total_cartons")
    box_label = f"{box_num}/{total}" if total else str(box_num)
    _cell(x + col + col / 2, box_label, "CARTON No.", big=True)
    _cell(x + 2 * col + col / 2, invoice_no or "—",        "INVOICE No.")

    # ── EAN ROW (next 16mm) — Clean white background, black text ─────────────
    ean_y = row1_y - 16 * mm
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.6)
    c.line(x, ean_y, x + w, ean_y)

    ean_val = carton.get("ean_code") or "—"
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x + 4 * mm, ean_y + 16 * mm - 4.5 * mm, "EAN / BARCODE")
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(x + w / 2, ean_y + 3 * mm, ean_val)

    # ── GOODS ROW (bottom) ───────────────────────────────────────────────────
    goods_y = y
    goods_h = ean_y - y
    # Four quadrants: Style | Color | Size | Qty
    qcol = w / 4

    def _goods(gx, lab, val, font_sz=9):
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(gx, goods_y + goods_h - 5 * mm, lab)
        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", font_sz)
        c.drawCentredString(gx, goods_y + 3 * mm, str(val) if val else "—")

    # vertical separators inside goods row
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.6)
    for i in (1, 2, 3):
        c.line(x + i * qcol, goods_y, x + i * qcol, ean_y)

    style_val = (
        carton.get("mapped_from_sku") or
        carton.get("external_sku") or
        carton.get("po_style_code") or
        carton.get("customer_style_code") or
        carton.get("buyer_style_code") or
        carton.get("style_code") or
        "—"
    )
    style_str = str(style_val)
    if len(style_str) > 18:
        style_font_sz = 6
    elif len(style_str) > 13:
        style_font_sz = 7
    else:
        style_font_sz = 8

    _goods(x + qcol * 0.5, "STYLE CODE",  style_val,             style_font_sz)
    _goods(x + qcol * 1.5, "COLOR",        carton.get("color", "—"),       9)
    _goods(x + qcol * 2.5, "SIZE",         carton.get("size", "—"),        20)
    _goods(x + qcol * 3.5, "QTY (PAIRS)",  carton.get("qty", "—"),         20)



def build_carton_labels(cartons: list[dict], po_number: str, invoice_no: str) -> bytes:
    """
    Build A4 PDF with 2 carton labels per page.
    cartons: list of packing_cartons dicts, should already have box_number set.
    """
    # Sort by box_number
    cartons = sorted(cartons, key=lambda c: c.get("box_number") or 0)
    total_cartons = len(cartons)
    for c in cartons:
        if c.get("total_cartons") is None:
            c["total_cartons"] = total_cartons

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Carton Labels — {po_number} — {invoice_no}")
    c.setAuthor("SSK Footcare ERP")

    positions = [
        (MARGIN, MARGIN + LABEL_H + MARGIN),   # top label
        (MARGIN, MARGIN),                        # bottom label
    ]

    for i, carton in enumerate(cartons):
        slot = i % 2
        bx, by = positions[slot]
        _draw_label(c, bx, by, carton, po_number, invoice_no)

        # After filling both slots on a page, start a new page
        if slot == 1 and i < len(cartons) - 1:
            c.showPage()

    c.save()
    return buf.getvalue()
