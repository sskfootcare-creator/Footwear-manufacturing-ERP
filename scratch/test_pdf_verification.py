import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import io
from pypdf import PdfReader
from pdf_procurement import build_material_requirement
from pdf_card import build_production_card, build_production_card_dual_a4

def test_procurement():
    jobs_summary = [
        {"po_number": "PO-101", "style_code": "ST-01", "color": "BLACK", "total_pairs": 500, "sizes_text": "6:100, 7:200, 8:200"}
    ]
    material_lines = [
        {"code": "MAT-01", "name": "Synthetic Leather", "category": "upper", "unit": "mtr", "rate": 150.0, "total_qty_required": 120, "total_cost": 18000.0},
        {"code": "MAT-02", "name": "Lining Fabric", "category": "lining", "unit": "mtr", "rate": 80.0, "total_qty_required": 100, "total_cost": 8000.0},
        {"code": "MAT-03", "name": "Rubber Sole", "category": "sole", "unit": "prs", "rate": 120.0, "total_qty_required": 500, "total_cost": 60000.0},
        {"code": "MAT-04", "name": "Adhesive Glue", "category": "consumable", "unit": "kg", "rate": 250.0, "total_qty_required": 10, "total_cost": 2500.0},
    ]
    pdf_bytes = build_material_requirement("PO Batch PO-101", jobs_summary, material_lines, "Test notes")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    print(f"Material Requirement Sheet Page Count: {len(reader.pages)}")
    assert len(reader.pages) == 1

def test_card_dual():
    job_group_5 = {
        "po_number": "PO-202",
        "client_name": "Acme Shoes",
        "style_code": "S-555",
        "color": "TAN",
        "description": "Men Formal Shoe",
        "delivery_date": "15/08/2026",
        "total_qty": 300,
        "sizes": [
            {"size": "6", "quantity": 50},
            {"size": "7", "quantity": 100},
            {"size": "8", "quantity": 100},
            {"size": "9", "quantity": 50},
            {"size": "10", "quantity": 0},
        ],
        "components": {"upper_done": True, "bottom_done": False, "sole_done": True},
        "assignments": {
            "cutting": {"worker_name": "Ramesh", "rate_per_pair": 12},
            "upper": {"worker_name": "Suresh", "rate_per_pair": 25},
            "lasting": {"worker_name": "Mahesh", "rate_per_pair": 30},
        }
    }
    
    # Test 5 sizes
    pdf_5 = build_production_card_dual_a4(job_group_5, None)
    reader_5 = PdfReader(io.BytesIO(pdf_5))
    print(f"Dual Card (5 sizes) Page Count: {len(reader_5.pages)}")
    
    # Test 8 sizes
    job_group_8 = dict(job_group_5)
    job_group_8["sizes"] = [
        {"size": str(i), "quantity": 40} for i in range(5, 13)
    ]
    pdf_8 = build_production_card_dual_a4(job_group_8, None)
    reader_8 = PdfReader(io.BytesIO(pdf_8))
    print(f"Dual Card (8 sizes) Page Count: {len(reader_8.pages)}")
    
    assert len(reader_5.pages) == 1
    assert len(reader_8.pages) == 1

if __name__ == "__main__":
    test_procurement()
    test_card_dual()
    print("ALL TESTS PASSED!")
