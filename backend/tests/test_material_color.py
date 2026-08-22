import os
import sys
import pytest
from pydantic import ValidationError

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.materials import MaterialIn, BomItem


def test_material_in_color_default():
    """Verify MaterialIn color defaults to empty string when not specified."""
    mat = MaterialIn(
        code="MAT-001",
        name="Synthetic Leather",
        category="upper",
        unit="sqft",
        rate=145.5,
        reorder_level=10.0,
    )
    assert mat.color == ""
    dumped = mat.model_dump()
    assert "color" in dumped
    assert dumped["color"] == ""


def test_material_in_color_custom():
    """Verify MaterialIn color preserves custom plain-text string."""
    mat = MaterialIn(
        code="MAT-002",
        name="Lining Fabric",
        category="lining",
        unit="mtr",
        rate=85.0,
        color="Tan Brown",
    )
    assert mat.color == "Tan Brown"
    dumped = mat.model_dump()
    assert dumped["color"] == "Tan Brown"


def test_material_in_optional_none():
    """Verify MaterialIn accepts None or empty string gracefully."""
    mat_none = MaterialIn(
        code="MAT-003",
        name="Rubber Sole Unit",
        category="sole",
        unit="pair",
        rate=120.0,
        color=None,
    )
    assert mat_none.color is None or mat_none.color == ""

    mat_empty = MaterialIn(
        code="MAT-004",
        name="Eyelets Brass",
        category="accessory",
        unit="pcs",
        rate=0.75,
        color="",
    )
    assert mat_empty.color == ""


def test_material_in_backward_compatibility():
    """Verify legacy payloads without color parse cleanly without validation errors."""
    legacy_payload = {
        "code": "LEGACY-001",
        "name": "Classic Thread",
        "category": "consumable",
        "unit": "pcs",
        "rate": 45.0,
        "reorder_level": 5,
        "notes": "Legacy batch",
    }
    mat = MaterialIn(**legacy_payload)
    assert mat.code == "LEGACY-001"
    assert mat.color == ""
    assert mat.rate == 45.0
