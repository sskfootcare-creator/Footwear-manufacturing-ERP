import pytest
from pydantic import ValidationError
from models.materials import MaterialIn
from models.styles import StyleIn


def test_material_stage_requirements_model():
    # 1. Defaults to None
    m = MaterialIn(code="MAT-001", name="PVC Sole", category="sole", rate=100.0, unit="pcs")
    assert m.stage_requirements is None

    # 2. Empty list (e.g. ready-to-use PVC/PU)
    m_pvc = MaterialIn(
        code="MAT-002",
        name="PVC Sole Black",
        category="sole",
        rate=120.0,
        unit="pcs",
        stage_requirements=[],
    )
    assert m_pvc.stage_requirements == []

    # 3. Non-empty list (e.g. rubbersheet needing cutting and finishing)
    m_rubber = MaterialIn(
        code="MAT-003",
        name="Rubber Sheet",
        category="sole",
        rate=250.0,
        unit="sqft",
        stage_requirements=["cutting", " finishing "],
    )
    assert m_rubber.stage_requirements == ["cutting", "finishing"]


def test_style_footwear_type_model():
    # 1. Defaults to "flat"
    s = StyleIn(name="Classic Oxford")
    assert s.footwear_type == "flat"

    # 2. Can be explicitly set to "flat"
    s_flat = StyleIn(name="Casual Flat", footwear_type="flat")
    assert s_flat.footwear_type == "flat"

    # 3. Can be explicitly set to "heel"
    s_heel = StyleIn(name="Block Heel Sandal", footwear_type="heel")
    assert s_heel.footwear_type == "heel"

    # 4. Invalid value raises ValidationError
    with pytest.raises(ValidationError):
        StyleIn(name="Invalid Footwear", footwear_type="boot")
