import pytest
import io
import pypdf
from pdf_procurement import build_material_requirement, generate_material_requirement_sheet
from routes.styles import get_effective_bom
from models.materials import BomItem, ColorBomOverride

def test_color_bom_override_new_line():
    """Verify that ColorBomOverride with line_id=None adds a new line to effective BOM for that color."""
    style = {
        "code": "TEST_STYLE_01",
        "name": "Test Style 01",
        "bom": [
            {
                "line_id": "line-1",
                "material_id": "mat-base",
                "material_code": "MAT-BASE",
                "material_name": "Base Upper",
                "unit": "mtr",
                "rate": 100.0,
                "quantity": 1.0,
                "yield_per_unit": 10.0,
                "waste_pct": 5.0,
                "section": "upper",
                "color": "Black",
            }
        ],
        "color_bom_overrides": {
            "Gold": [
                # Added new line with no line_id
                {
                    "material_id": "mat-gold-buckle",
                    "material_code": "MAT-GB",
                    "material_name": "Gold Buckle",
                    "unit": "pcs",
                    "rate": 15.0,
                    "quantity": 2.0,
                    "yield_per_unit": 1.0,
                    "waste_pct": 0.0,
                    "section": "accessory",
                    "color": "Gold",
                }
            ]
        }
    }

    # Effective BOM for base / Black: only 1 line
    bom_black = get_effective_bom(style, "Black")
    assert len(bom_black) == 1
    assert bom_black[0].material_code == "MAT-BASE"

    # Effective BOM for Gold: 2 lines (base line + newly added Gold Buckle line)
    bom_gold = get_effective_bom(style, "Gold")
    assert len(bom_gold) == 2
    codes = [b.material_code for b in bom_gold]
    assert "MAT-BASE" in codes
    assert "MAT-GB" in codes


def test_procurement_pdf_with_vendors():
    """Verify build_material_requirement produces valid PDF containing Vendor column, vendor names, and swatch boxes."""
    jobs_summary = [
        {
            "po_number": "PO-TEST-999",
            "style_code": "SSK_TEST",
            "color": "TAN",
            "total_pairs": 200,
            "sizes_text": "6, 7, 8, 9",
        }
    ]

    material_lines = [
        {
            "code": "UPPER-LEATHER",
            "name": "Premium Tan Leather",
            "category": "upper",
            "unit": "mtr",
            "rate": 250.0,
            "total_qty_required": 25.5,
            "total_cost": 6375.0,
            "color": "TAN",
            "preferred_vendor_name": "Apex Tannery Ltd",
        },
        {
            "code": "TPR-SOLE",
            "name": "TPR Sole Unit",
            "category": "sole",
            "unit": "prs",
            "rate": 45.0,
            "total_qty_required": 200.0,
            "total_cost": 9000.0,
            "color": "BROWN",
            "size_breakdown": {"6": 50, "7": 50, "8": 50, "9": 50},
            "preferred_vendor_name": "SoleCraft India",
        },
        {
            "code": "BUCKLE-BRASS",
            "name": "Brass Roller Buckle",
            "category": "accessory",
            "unit": "pcs",
            "rate": 5.0,
            "total_qty_required": 400.0,
            "total_cost": 2000.0,
            "color": "",
            "preferred_vendor_name": "MetalTrims Co",
        },
    ]

    pdf_bytes = build_material_requirement(
        scope_label="PO-TEST-999 (TAN)",
        jobs_summary=jobs_summary,
        material_lines=material_lines,
        notes="Urgent vendor dispatch requirement.",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000

    # Parse and inspect PDF text
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    all_text = " ".join(page.extract_text() for page in reader.pages)

    assert "SSK FOOTCARE MANUFACTURING LLP" in all_text
    assert "MATERIAL REQUIREMENT SHEET" in all_text
    assert "PO-TEST-999" in all_text
    assert "SSK_TEST" in all_text
    assert "Apex Tannery Ltd" in all_text
    assert "SoleCraft India" in all_text
    assert "MetalTrims Co" in all_text
    assert "TOTAL" in all_text
    assert "Vendor" in all_text or "vendors" in all_text.lower()


def test_procurement_merged_sheet():
    """Verify consolidated / merged requirement sheet formatting."""
    jobs_summary = [
        {"po_number": "PO-1", "style_code": "S1", "color": "RED", "total_pairs": 100, "sizes_text": "7, 8"},
        {"po_number": "PO-2", "style_code": "S2", "color": "BLUE", "total_pairs": 150, "sizes_text": "8, 9"},
    ]
    material_lines = [
        {"code": "THREAD", "name": "Nylon Thread", "category": "consumable", "unit": "cone", "rate": 80.0, "total_qty_required": 5.0, "total_cost": 400.0, "preferred_vendor_name": "ThreadCorp"}
    ]
    pdf_bytes = build_material_requirement(
        scope_label="Merged Batch (PO-1 + PO-2)",
        jobs_summary=jobs_summary,
        material_lines=material_lines,
        is_merged=True,
    )
    assert isinstance(pdf_bytes, bytes)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    all_text = " ".join(page.extract_text() for page in reader.pages)
    assert "CONSOLIDATED MATERIAL REQUIREMENT SHEET" in all_text
    assert "CONSOLIDATED TOTAL" in all_text


def test_merging_two_or_more_production_cards_gives_only_consolidated_requirement():
    """Verify that merging two or more production cards gives ONLY consolidated total requirement."""
    jobs_summary = [
        {"po_number": "PO-2026-092", "style_code": "SSK_00059", "color": "Mahogany", "total_pairs": 260, "sizes_text": "6, 7, 8, 9, 10"},
        {"po_number": "PO-2026-095", "style_code": "SSK_00034", "color": "Tan", "total_pairs": 200, "sizes_text": "6, 7, 8, 9"},
    ]
    materials = [
        {"code": "MAT-INS-01", "name": "Standard Shank Board", "category": "Insole", "unit": "prs", "rate": 35.0, "total_qty_required": 455, "total_cost": 15925.0, "color": "Mahogany", "preferred_vendor_name": ""},
        {"code": "MAT-LED-14B18C", "name": "Sole Leather Grade A", "category": "Sole", "unit": "pair", "rate": 23.0, "total_qty_required": 210, "total_cost": 4830.0, "color": "Tan", "preferred_vendor_name": "Ledger Test Vendor", "size_breakdown": {"6": 42, "7": 63, "8": 63, "9": 42}},
        {"code": "MAT-SOL-01", "name": "TPR Lug Sole", "category": "Sole", "unit": "prs", "rate": 180.0, "total_qty_required": 260, "total_cost": 46800.0, "color": "Mahogany", "preferred_vendor_name": "", "size_breakdown": {"6": 30, "7": 60, "8": 80, "9": 60, "10": 30}},
        {"code": "MAT-1788115306", "name": "Synthetic Upper Leather", "category": "Upper", "unit": "sqft", "rate": 150.0, "total_qty_required": 14, "total_cost": 2100.0, "color": "Cream", "preferred_vendor_name": ""},
        {"code": "MAT-MAH-01", "name": "Mahogany Pull-Up Leather", "category": "Upper", "unit": "sqft", "rate": 165.0, "total_qty_required": 312, "total_cost": 51480.0, "color": "Mahogany", "preferred_vendor_name": ""},
        {"code": "patent", "name": "patentbrown", "category": "Upper", "unit": "mtr", "rate": 110.0, "total_qty_required": 14, "total_cost": 1540.0, "color": "Tan", "preferred_vendor_name": ""},
    ]
    by_color = {
        "Mahogany": {"color": "Mahogany", "total_pairs": 260, "materials": materials[:3]},
        "Tan": {"color": "Tan", "total_pairs": 200, "materials": materials[3:]},
    }

    # Even if split_by_color is passed as True with by_color populated,
    # merging 2 production cards must suppress color breakdown and only give consolidated total requirement
    pdf_bytes = build_material_requirement(
        scope_label="2 procurement cards",
        jobs_summary=jobs_summary,
        material_lines=materials,
        split_by_color=True,
        by_color=by_color,
    )

    assert isinstance(pdf_bytes, bytes)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    all_text = " ".join(page.extract_text() for page in reader.pages)

    # Must contain consolidated header and total
    assert "CONSOLIDATED MATERIAL REQUIREMENT SHEET" in all_text
    assert "CONSOLIDATED MATERIALS REQUIRED" in all_text
    assert "CONSOLIDATED TOTAL" in all_text

    # Must NOT contain individual color breakdown banners
    assert "COLOR VARIANT:" not in all_text
    assert "SUBTOTAL (MAHOGANY)" not in all_text
    assert "SUBTOTAL (TAN)" not in all_text

    # Must fit on 1 page cleanly without orphan signature page
    assert len(reader.pages) == 1

