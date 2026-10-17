import sys, io
sys.path.insert(0, 'backend')
from pypdf import PdfReader
from pdf_card import build_production_card, build_production_card_dual_a4

def test_production_card_pdf_with_all_subtasks():
    job_group = {
        "po_number": "PO-SUBTASK-2026",
        "client_name": "METRO BRANDS LTD",
        "style_code": "SSK_CLASSIC_01",
        "po_style_code": "MB-CLS-01",
        "created_at": "2026-10-15T10:00:00Z",
        "color": "CHERRY RED",
        "description": "Premium Leather Oxford",
        "delivery_date": "2026-11-05",
        "sizes": [{"size": "7", "quantity": 120}, {"size": "8", "quantity": 180}],
        "total_qty": 300,
        "components": {"upper_done": True, "bottom_done": False, "sole_done": True},
        "component_specs": {
            "footwear_type": "flat",
            "components": {
                "upper": {"stages": ["cutting", "stitching", "folding", "attachment"]},
                "bottom": {"stages": ["cutting", "stitching", "stamping", "assembly"]},
                "sole": {"stages": ["prep"]},
            }
        },
        "assignments": {
            "upper": {"worker_name": "Ramesh Lead", "rate_per_pair": 22.0},
            "upper.cutting": {"worker_name": "Dev Cutting", "rate_per_pair": 8.0},
            "upper.stitching": {"worker_name": "Pooja Stitcher", "rate_per_pair": 14.0},
            "upper.folding": {"worker_name": "Ramesh Lead", "rate_per_pair": 5.0},
            "upper.attachment": {"worker_name": "Ramesh Lead", "rate_per_pair": 4.0},
            "bottom": {"worker_name": "Suresh Bottom Lead", "rate_per_pair": 18.0},
            "bottom.stamping": {"worker_name": "Mahesh Stamp", "rate_per_pair": 3.5},
            "sole": {"worker_name": "Karan Sole", "rate_per_pair": 12.0},
            "lasting": {"worker_name": "Mohan Master", "rate_per_pair": 20.0},
            "sole_pasting": {"worker_name": "Vinod Pasting", "rate_per_pair": 10.0},
            "finishing": {"worker_name": "Raj Finish", "rate_per_pair": 7.0},
            "qc_pack": {"worker_name": "Anil QC", "rate_per_pair": 5.0},
        },
        "outside_labour": [
            {
                "name": "Gold Foil Embossing",
                "vendor": "Royal Prints",
                "rate": 6.5,
            }
        ],
    }

    style = {
        "code": "SSK_CLASSIC_01",
        "name": "Classic Oxford",
        "footwear_type": "flat",
        "sole_ready_to_use": False,
    }

    # 1. Standard A4 PDF
    single_pdf = build_production_card(job_group, style, with_rates=True)
    assert len(single_pdf) > 1000, "Single A4 PDF too small"
    assert single_pdf.startswith(b"%PDF"), "Must be a valid PDF"

    reader_single = PdfReader(io.BytesIO(single_pdf))
    text_single = ""
    for page in reader_single.pages:
        text_single += page.extract_text() or ""

    # Verify all sub-tasks and assignments are present in single PDF
    assert len(reader_single.pages) == 1, f"Single A4 must fit on exactly 1 page, got {len(reader_single.pages)}"
    assert "Upper: Cutting" in text_single or "Upper: Lead" in text_single
    assert "Pooja Stitcher" in text_single
    assert "Mohan Master" in text_single
    assert "Gold Foil Emb" in text_single
    assert "Royal Prints" in text_single
    assert "COMPONENTS & SWATCHES" not in text_single
    assert "MANUFACTURING PROCESS TALLY" in text_single

    # 2. Dual A4 PDF (fits on 1 single page)
    dual_pdf = build_production_card_dual_a4(job_group, style)
    assert len(dual_pdf) > 1000, "Dual A4 PDF too small"
    assert dual_pdf.startswith(b"%PDF"), "Must be a valid PDF"

    reader_dual = PdfReader(io.BytesIO(dual_pdf))
    assert len(reader_dual.pages) == 1, f"Dual A4 must fit on exactly 1 page, got {len(reader_dual.pages)}"

    text_dual = reader_dual.pages[0].extract_text() or ""
    assert "Pooja Stitcher" in text_dual
    assert "Mohan Master" in text_dual
    assert "Gold Foil Emb" in text_dual
    assert "COMPONENTS & SWATCHES" not in text_dual
    assert "MANUFACTURING PROCESS TALLY" in text_dual


def test_production_card_pdf_ready_to_use_sole():
    ready_sole_job = {
        "po_number": "PO-READY-SOLE",
        "style_code": "SSK_READY_01",
        "color": "TAN",
        "sizes": [{"size": "8", "quantity": 100}],
        "total_qty": 100,
        "sole_ready_to_use": True,
        "assignments": {
            "upper": {"worker_name": "Ramesh", "rate_per_pair": 20},
            "lasting": {"worker_name": "Mohan", "rate_per_pair": 18},
        },
    }

    dual_pdf = build_production_card_dual_a4(ready_sole_job, {"sole_ready_to_use": True})
    reader = PdfReader(io.BytesIO(dual_pdf))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text() or ""
    assert "Sole: Ready-to-Use" in text or "Vendor Supplied" in text
