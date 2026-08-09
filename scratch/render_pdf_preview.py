import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pdf_carton_label import build_carton_labels

cartons = [
    {
        "box_number": 1,
        "total_cartons": 10,
        "style_code": "SSK_00008",
        "mapped_from_sku": "8536450598023",
        "color": "CREAM",
        "size": "8",
        "qty": 72,
        "ean_code": "8536450598023"
    }
]

pdf_bytes = build_carton_labels(cartons, "2220008833", "SSK26-27-007")

try:
    import fitz # PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=150)
    out_path = os.path.join(os.path.dirname(__file__), "monochrome_carton_label_preview.png")
    pix.save(out_path)
    print("SAVED PREVIEW TO:", out_path)
except Exception as e:
    print("Could not render image with PyMuPDF:", e)
