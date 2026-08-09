"""Test unit functions for carton labels with mapped PO / external style code."""
import io
import os
import sys
import pypdf

# Ensure backend directory is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pdf_carton_label import build_carton_labels
from packing_list import build_carton_list_xlsx

def test_build_carton_labels_with_mapped_sku():
    cartons = [
        {
            "box_number": 1,
            "total_cartons": 2,
            "style_code": "SSK_00008",
            "mapped_from_sku": "5ZEZP125WWFLT11719888",
            "color": "CREAM",
            "size": "8",
            "qty": 72,
            "ean_code": "8536450598023"
        },
        {
            "box_number": 2,
            "total_cartons": 2,
            "style_code": "SSK_00008",
            "mapped_from_sku": None,
            "color": "CREAM",
            "size": "9",
            "qty": 48,
            "ean_code": "8536450598024"
        }
    ]

    pdf_bytes = build_carton_labels(cartons, "2220008833", "SSK26-27-007")
    assert len(pdf_bytes) > 500, "PDF bytes should not be empty"

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text()

    assert "5ZEZP125WWFLT11719888" in text, "Mapped external style code 5ZEZP125WWFLT11719888 should be printed in PDF"
    assert "SSK_00008" in text, "Fallback internal style code SSK_00008 should be printed for unmapped carton"
    print("SUCCESS: PDF text extraction verified! Mapped PO style code '5ZEZP125WWFLT11719888' is printed on label.")

if __name__ == "__main__":
    test_build_carton_labels_with_mapped_sku()
