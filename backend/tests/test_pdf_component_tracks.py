import sys, os
sys.path.insert(0, 'backend')
from pdf_card import build_production_card, build_production_card_dual_a4

def test_pdf_rendering():
    # 1. Flat job
    flat_job = {
        "po_number": "PO-TEST-FLAT",
        "style_code": "FLAT_STYLE_01",
        "style_name": "Comfort Loafer",
        "color": "Tan",
        "quantity": 100,
        "rows": [{"size": "7", "quantity": 50}, {"size": "8", "quantity": 50}],
        "component_specs": {
            "footwear_type": "flat",
            "components": {
                "upper": {"stages": ["cutting", "stitching"]},
                "bottom": {"stages": ["cutting"]},
                "sole": {"stages": []}
            }
        },
        "component_tracks": {
            "upper": {"status": "ready"},
            "bottom": {"status": "ready"},
            "sole": {"status": "ready"}
        }
    }
    pdf_bytes_flat = build_production_card(flat_job, None)
    assert len(pdf_bytes_flat) > 1000, "Flat PDF too small"
    print(f"Flat job card PDF generated successfully ({len(pdf_bytes_flat)} bytes)")

    # 2. Heel job
    heel_job = {
        "po_number": "PO-TEST-HEEL",
        "style_code": "HEEL_STYLE_02",
        "style_name": "Party Stiletto",
        "color": "Gold",
        "quantity": 60,
        "rows": [{"size": "6", "quantity": 30}, {"size": "7", "quantity": 30}],
        "component_specs": {
            "footwear_type": "heel",
            "components": {
                "upper": {"stages": ["cutting", "stitching"]},
                "bottom": {"stages": ["cutting"]},
                "sole": {"stages": ["cutting", "finishing"]},
                "heel_gola": {"stages": ["cover_cutting", "folding"]}
            }
        },
        "component_tracks": {
            "upper": {"status": "ready"},
            "bottom": {"status": "ready"},
            "sole": {"status": "in_progress"},
            "heel_gola": {"status": "ready"}
        }
    }
    pdf_bytes_heel = build_production_card_dual_a4(heel_job, None)
    assert len(pdf_bytes_heel) > 1000, "Heel PDF too small"
    print(f"Heel dual A4 job card PDF generated successfully ({len(pdf_bytes_heel)} bytes)")

if __name__ == "__main__":
    test_pdf_rendering()
