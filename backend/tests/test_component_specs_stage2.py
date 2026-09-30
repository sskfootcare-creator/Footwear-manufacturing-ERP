import pytest
from services.component_spec_service import (
    derive_component_specs,
    init_component_tracks,
    check_merge_gates,
)


def test_derive_component_specs_flat_style_pvc_sole():
    """Flat style with PVC sole (ready to use). Heel component should be absent."""
    materials = {
        "m_leather": {"category": "upper", "stage_requirements": ["cutting", "stitching"]},
        "m_texon": {"category": "insole", "stage_requirements": ["cutting"]},
        "m_pvc_sole": {"category": "sole", "stage_requirements": []},
    }
    style = {
        "code": "FLAT-001",
        "name": "Flat Casual Loafer",
        "footwear_type": "flat",
        "bom": [
            {"material_id": "m_leather", "section": "upper", "quantity": 1.0},
            {"material_id": "m_texon", "section": "insole", "quantity": 1.0},
            {"material_id": "m_pvc_sole", "section": "sole", "quantity": 1.0},
        ],
    }

    specs = derive_component_specs(style, materials_by_id=materials)
    assert specs["footwear_type"] == "flat"
    assert "heel_gola" not in specs["components"]
    assert "upper" in specs["components"]
    assert "bottom" in specs["components"]
    assert "sole" in specs["components"]

    assert specs["components"]["sole"]["stages"] == []
    tracks = init_component_tracks(specs)
    assert tracks["sole"]["status"] == "ready"
    assert tracks["upper"]["status"] == "in_progress"
    assert tracks["upper"]["current_stage"] == "cutting"


def test_derive_component_specs_heel_style_with_cover():
    """Heel style with cover-cutting/folding heel and rubbersheet sole."""
    materials = {
        "m_leather": {"category": "upper", "stage_requirements": ["cutting", "stitching"]},
        "m_board": {"category": "insole", "stage_requirements": ["cutting"]},
        "m_rubber": {"category": "sole", "stage_requirements": ["cutting", "finishing"]},
        "m_heel_cover": {"category": "heel", "stage_requirements": ["cover_cutting", "folding"]},
    }
    style = {
        "code": "HEEL-001",
        "name": "Covered Block Heel",
        "footwear_type": "heel",
        "bom": [
            {"material_id": "m_leather", "section": "upper"},
            {"material_id": "m_board", "section": "bottom"},
            {"material_id": "m_rubber", "section": "sole"},
            {"material_id": "m_heel_cover", "section": "cover", "component": "heel"},
        ],
    }

    specs = derive_component_specs(style, materials_by_id=materials)
    assert specs["footwear_type"] == "heel"
    assert "heel_gola" in specs["components"]
    assert specs["components"]["heel_gola"]["stages"] == ["cover_cutting", "folding"]
    assert specs["components"]["sole"]["stages"] == ["cutting", "finishing"]

    tracks = init_component_tracks(specs)
    assert tracks["heel_gola"]["status"] == "in_progress"
    assert tracks["heel_gola"]["current_stage"] == "cover_cutting"
    assert tracks["sole"]["status"] == "in_progress"
    assert tracks["sole"]["current_stage"] == "cutting"


def test_derive_component_specs_heel_vendor_colored():
    """Heel style with pre-finished / vendor-colored heel (stage_requirements = [])."""
    materials = {
        "m_leather": {"category": "upper"},
        "m_board": {"category": "insole"},
        "m_pvc_sole": {"category": "sole", "stage_requirements": []},
        "m_finished_heel": {"category": "heel", "stage_requirements": []},
    }
    style = {
        "code": "HEEL-002",
        "name": "Stiletto Vendor Colored",
        "footwear_type": "heel",
        "bom": [
            {"material_id": "m_leather", "section": "upper"},
            {"material_id": "m_board", "section": "bottom"},
            {"material_id": "m_pvc_sole", "section": "sole"},
            {"material_id": "m_finished_heel", "section": "heel"},
        ],
    }

    specs = derive_component_specs(style, materials_by_id=materials)
    assert specs["components"]["heel_gola"]["stages"] == []
    tracks = init_component_tracks(specs)
    assert tracks["heel_gola"]["status"] == "ready"
    assert tracks["sole"]["status"] == "ready"


def test_check_merge_gates_logic():
    """Verify merge gate validation for lasting and sole_pasting."""
    specs = {
        "footwear_type": "heel",
        "components": {
            "upper": {"stages": ["cutting", "stitching"]},
            "bottom": {"stages": ["cutting"]},
            "sole": {"stages": ["finishing"]},
            "heel_gola": {"stages": ["folding"]},
        },
    }
    tracks = {
        "upper": {"status": "in_progress", "current_stage": "cutting"},
        "bottom": {"status": "ready", "current_stage": "ready"},
        "sole": {"status": "in_progress", "current_stage": "finishing"},
        "heel_gola": {"status": "ready", "current_stage": "ready"},
    }

    # 1. Lasting gate blocked because upper is in_progress
    allowed, msg = check_merge_gates("lasting", tracks, specs)
    assert allowed is False
    assert "upper" in msg

    # Mark upper ready
    tracks["upper"]["status"] = "ready"
    allowed, msg = check_merge_gates("lasting", tracks, specs)
    assert allowed is True
    assert msg is None

    # 2. Sole pasting gate blocked because sole is in_progress
    allowed, msg = check_merge_gates("sole_pasting", tracks, specs)
    assert allowed is False
    assert "sole" in msg

    # Mark sole ready
    tracks["sole"]["status"] = "ready"
    allowed, msg = check_merge_gates("sole_pasting", tracks, specs)
    assert allowed is True
    assert msg is None
