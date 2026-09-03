"""
Test Suite for Stage 2: Merge function: effective BOM per color (get_effective_bom)
Verifies:
1. 5-line base BOM and a color overriding 2 specific lines on different fields:
   - One line overridden on rate-only (inheriting material, quantity, yield, waste)
   - One line overridden on material + quantity (inheriting base rate, yield, waste)
   - Confirm exactly those 2 lines reflect the override; the other 3 remain completely untouched.
2. Color with no overrides (or color=None) returns the base BOM completely unchanged.
3. Stale line_id reference (e.g. line removed from base BOM) is skipped with a warning,
   NOT a hard failure, preserving the rest of the style's valid BOM.
"""

import pytest
import logging
from models.materials import BomItem, ColorBomOverride
from routes.styles import get_effective_bom


def test_get_effective_bom_5_lines_override_2_lines():
    """Unit Test:
    5-line base BOM across mixed sections.
    Color 'Burgundy' overrides:
      - Line 1 (Upper): rate only (100 -> 145)
      - Line 2 (Lining): material and quantity (Lining A, qty 1.0 -> Lining Burgundy Satin, qty 1.4)
    Confirm exactly those 2 lines reflect the override, other 3 lines remain untouched.
    """
    line1 = BomItem(
        line_id="line-01",
        material_id="mat-blk-box",
        material_name="Black Box Leather",
        material_code="MAT-BLK-01",
        rate=100.0,
        quantity=1.2,
        yield_per_unit=1.0,
        waste_pct=5.0,
        section="upper",
        component="Vamp",
    )
    line2 = BomItem(
        line_id="line-02",
        material_id="mat-lin-std",
        material_name="Standard Fabric Lining",
        material_code="MAT-LIN-01",
        rate=40.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=2.0,
        section="lining",
        component="Quarter Lining",
    )
    line3 = BomItem(
        line_id="line-03",
        material_id="mat-ins-board",
        material_name="Texon Insole Board",
        material_code="MAT-INS-01",
        rate=30.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="insole",
    )
    line4 = BomItem(
        line_id="line-04",
        material_id="mat-sole-tpr",
        material_name="TPR Lug Sole",
        material_code="MAT-SOL-01",
        rate=150.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="sole",
    )
    line5 = BomItem(
        line_id="line-05",
        material_id="mat-lace-blk",
        material_name="Black Waxed Cotton Laces",
        material_code="MAT-LAC-01",
        rate=12.0,
        quantity=1.0,
        yield_per_unit=1.0,
        waste_pct=0.0,
        section="accessories",
    )

    style = {
        "code": "STY-5LINE-TEST",
        "name": "5-Line Test Derby",
        "bom": [line1, line2, line3, line4, line5],
        "color_bom_overrides": {
            "Burgundy": [
                # Line 1 override: rate-only
                ColorBomOverride(
                    line_id="line-01",
                    rate=145.0,
                ),
                # Line 2 override: material + quantity
                ColorBomOverride(
                    line_id="line-02",
                    material_id="mat-lin-burg",
                    material_name="Burgundy Satin Lining",
                    material_code="MAT-LIN-BUR",
                    quantity=1.4,
                ),
            ]
        },
    }

    effective = get_effective_bom(style, color="Burgundy")
    assert len(effective) == 5

    # 1. Line 1 checks (Rate overridden, everything else untouched)
    eff_1 = effective[0]
    assert eff_1.line_id == "line-01"
    assert eff_1.rate == 145.0  # Overridden
    assert eff_1.material_name == "Black Box Leather"  # Untouched
    assert eff_1.material_code == "MAT-BLK-01"  # Untouched
    assert eff_1.quantity == 1.2  # Untouched
    assert eff_1.waste_pct == 5.0  # Untouched
    assert eff_1.component == "Vamp"  # Untouched

    # 2. Line 2 checks (Material + Quantity overridden, rate untouched)
    eff_2 = effective[1]
    assert eff_2.line_id == "line-02"
    assert eff_2.material_name == "Burgundy Satin Lining"  # Overridden
    assert eff_2.material_code == "MAT-LIN-BUR"  # Overridden
    assert eff_2.material_id == "mat-lin-burg"  # Overridden
    assert eff_2.quantity == 1.4  # Overridden
    assert eff_2.rate == 40.0  # Untouched base rate
    assert eff_2.waste_pct == 2.0  # Untouched
    assert eff_2.component == "Quarter Lining"  # Untouched

    # 3. Lines 3, 4, 5 checks (Completely untouched)
    eff_3 = effective[2]
    assert eff_3.line_id == "line-03"
    assert eff_3.material_name == "Texon Insole Board"
    assert eff_3.rate == 30.0
    assert eff_3.quantity == 1.0

    eff_4 = effective[3]
    assert eff_4.line_id == "line-04"
    assert eff_4.material_name == "TPR Lug Sole"
    assert eff_4.rate == 150.0

    eff_5 = effective[4]
    assert eff_5.line_id == "line-05"
    assert eff_5.material_name == "Black Waxed Cotton Laces"
    assert eff_5.rate == 12.0


def test_get_effective_bom_color_with_no_overrides():
    """Unit Test:
    Test a color with no overrides (e.g. 'Black' when only 'Burgundy' has overrides,
    or color=None). Confirm the base BOM returns completely unchanged.
    """
    line1 = BomItem(line_id="l1", material_name="Upper Leather", rate=100.0)
    line2 = BomItem(line_id="l2", material_name="Sole", rate=150.0)

    style = {
        "name": "Classic Loafer",
        "bom": [line1, line2],
        "color_bom_overrides": {
            "Burgundy": [ColorBomOverride(line_id="l1", rate=130.0)]
        },
    }

    # Test with color having no override entry
    eff_black = get_effective_bom(style, color="Black")
    assert len(eff_black) == 2
    assert eff_black[0].rate == 100.0
    assert eff_black[1].rate == 150.0

    # Test with color=None
    eff_none = get_effective_bom(style, color=None)
    assert len(eff_none) == 2
    assert eff_none[0].rate == 100.0

    # Test with color="" (empty string)
    eff_empty = get_effective_bom(style, color="")
    assert len(eff_empty) == 2
    assert eff_empty[0].rate == 100.0


def test_get_effective_bom_stale_line_id_skipped_with_warning(caplog):
    """Unit Test:
    Test a stale line_id reference (e.g. base BOM was edited and line was removed).
    Confirm it's skipped with a warning, NOT a hard failure, and the remaining
    valid lines are processed properly.
    """
    line_valid = BomItem(
        line_id="line-valid-1",
        material_name="Valid Upper",
        rate=110.0,
        quantity=1.0,
    )

    style = {
        "code": "STY-STALE-TEST",
        "name": "Stale Override Test Style",
        "bom": [line_valid],
        "color_bom_overrides": {
            "Navy": [
                # Stale override for a line that no longer exists in base BOM
                ColorBomOverride(
                    line_id="line-stale-999",
                    rate=250.0,
                    material_name="Ghost Material",
                ),
                # Valid override for the existing line
                ColorBomOverride(
                    line_id="line-valid-1",
                    rate=135.0,
                ),
            ]
        },
    }

    with caplog.at_level(logging.WARNING):
        effective = get_effective_bom(style, color="Navy")

    # Only the 1 valid line exists in the result
    assert len(effective) == 1
    assert effective[0].line_id == "line-valid-1"
    assert effective[0].rate == 135.0  # Valid override was applied

    # Check that a warning was emitted for line-stale-999
    warning_records = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any(
        "line-stale-999" in rec.message and "stale override" in rec.message
        for rec in warning_records
    ), "A warning must be logged for the stale line_id"
