"""Component Spec & Production Track Service.

Derives component_specs from style BOM (with ColorBomOverride applied) and material stage_requirements.
Manages component_tracks initialization, stage progression, and merge gate checks.
"""

from typing import Dict, List, Optional, Any, Tuple

MERGE_GATES = {
    "lasting": ["upper", "bottom"],
    "sole_pasting": ["sole"],  # plus heel_gola if heel
}

DEFAULT_UPPER_STAGES = ["cutting", "stitching"]
DEFAULT_BOTTOM_STAGES = ["cutting", "stitching", "stamping"]


def classify_bom_line_component(
    line: Any,
    material: Optional[dict] = None
) -> str:
    """Classify a BOM item into 'upper', 'bottom', 'sole', or 'heel_gola'."""
    line_dict = line if isinstance(line, dict) else (line.model_dump() if hasattr(line, "model_dump") else {})
    comp = str(line_dict.get("component") or "").strip().lower()
    section = str(line_dict.get("section") or "").strip().lower()
    mat_cat = str(material.get("category") or "").strip().lower() if material else ""
    mat_comp_cat = str(material.get("component_category") or "").strip().lower() if material else ""
    mat_name = str(material.get("name") or line_dict.get("material_name") or "").strip().lower()

    # 1. Heel / Gola / Platform keywords
    for val in (comp, section, mat_cat, mat_comp_cat, mat_name):
        if any(kw in val for kw in ("heel", "gola", "platform", "cover")):
            return "heel_gola"

    # 2. Sole keywords
    for val in (comp, section, mat_cat, mat_comp_cat, mat_name):
        if any(kw in val for kw in ("sole", "outsole", "tpr", "sheet")):
            if "insole" not in val:
                return "sole"

    # 3. Bottom / Insole / Sockliner keywords
    for val in (comp, section, mat_cat, mat_comp_cat, mat_name):
        if any(kw in val for kw in ("bottom", "insole", "sockliner", "texon", "board", "shank")):
            return "bottom"

    # 4. Upper / Lining / Vamp / Collar / Trim keywords
    for val in (comp, section, mat_cat, mat_comp_cat, mat_name):
        if any(kw in val for kw in ("upper", "lining", "vamp", "quarter", "collar", "strap", "leather", "rexine", "fabric", "foam")):
            return "upper"

    return "upper"


def derive_component_specs(
    style: dict,
    color: Optional[str] = None,
    materials_by_id: Optional[Dict[str, dict]] = None,
) -> Dict[str, Any]:
    """
    Given a style dict and optional color, resolve effective BOM lines with overrides,
    group by active component (based on footwear_type), union stage_requirements of linked materials,
    and return the derived component_specs dictionary.
    """
    from routes.styles import get_effective_bom

    if isinstance(color, dict) and materials_by_id is None:
        materials_by_id = color
        color = None

    style = style or {}
    footwear_type = style.get("footwear_type") or "flat"
    active_components = ["upper", "bottom", "sole"]
    if footwear_type == "heel":
        active_components.append("heel_gola")

    effective_bom = get_effective_bom(style, color)
    materials_map = materials_by_id or {}

    # Accumulate stage requirements per component
    comp_extra_stages: Dict[str, List[str]] = {c: [] for c in active_components}
    comp_has_material: Dict[str, bool] = {c: False for c in active_components}

    for line in effective_bom:
        line_dict = line if isinstance(line, dict) else (line.model_dump() if hasattr(line, "model_dump") else {})
        mat_id = str(line_dict.get("material_id") or "")
        mat = materials_map.get(mat_id) or {}

        target_comp = classify_bom_line_component(line_dict, mat)
        if target_comp not in comp_extra_stages:
            if target_comp == "heel_gola" and "heel_gola" not in active_components:
                continue
            target_comp = "upper"

        comp_has_material[target_comp] = True
        stage_reqs = mat.get("stage_requirements")
        if stage_reqs and isinstance(stage_reqs, list):
            for st in stage_reqs:
                st_clean = str(st).strip()
                if st_clean and st_clean not in comp_extra_stages[target_comp]:
                    comp_extra_stages[target_comp].append(st_clean)

    # Build final component specs
    components_spec = {}
    for c in active_components:
        extra = comp_extra_stages[c]
        if c == "upper":
            stages = extra if len(extra) > 0 else list(DEFAULT_UPPER_STAGES)
            ready_if_empty = False
        elif c == "bottom":
            base_stages = list(DEFAULT_BOTTOM_STAGES)
            stages = base_stages + [s for s in extra if s not in base_stages]
            ready_if_empty = False
        elif c == "sole":
            sole_mat_ready = any(
                bool(line.get("ready_to_use") or line.get("is_ready_to_use"))
                for line in (effective_bom if isinstance(effective_bom, list) else [])
                if isinstance(line, dict) and classify_bom_line_component(line, materials_map.get(str(line.get("material_id") or "")) or {}) == "sole"
            )
            is_ready_to_use = bool(
                style.get("sole_ready_to_use")
                or style.get("ready_to_use_sole")
                or style.get("sole_type") == "ready_to_use"
                or sole_mat_ready
            )
            stages = [] if is_ready_to_use else list(extra)
            ready_if_empty = True
        elif c == "heel_gola":
            stages = list(extra)
            ready_if_empty = True
        else:
            stages = list(extra)
            ready_if_empty = True

        comp_dict = {
            "stages": stages,
            "extra_stages": extra,
            "ready_if_empty": ready_if_empty,
        }
        if c == "sole":
            comp_dict["is_ready_to_use"] = is_ready_to_use
        components_spec[c] = comp_dict

    return {
        "footwear_type": footwear_type,
        "components": components_spec,
    }


def init_component_tracks(component_specs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize component_tracks from derived component_specs.
    Each active component starts at its first stage, or immediately at 'ready' if stages is empty or marked ready_to_use.
    """
    tracks = {}
    comps = component_specs.get("components") or {}
    for comp_name, spec in comps.items():
        stages = spec.get("stages") or []
        if not stages or (comp_name == "sole" and spec.get("is_ready_to_use")):
            tracks[comp_name] = {
                "current_stage": "ready",
                "status": "ready",
                "stages_completed": [],
            }
        else:
            tracks[comp_name] = {
                "current_stage": stages[0],
                "status": "in_progress",
                "stages_completed": [],
            }
    return tracks


def check_merge_gates(
    target_stage: str,
    component_tracks: Optional[Dict[str, Any]],
    component_specs: Optional[Dict[str, Any]],
    fallback_components: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Check whether a job can enter target_stage (e.g. 'lasting' or 'sole_pasting').
    Returns (allowed, error_message).
    """
    if target_stage not in MERGE_GATES:
        return True, None

    footwear_type = (component_specs or {}).get("footwear_type", "flat")
    specs_comps = (component_specs or {}).get("components") or {}

    # Special-case lasting gate for exact legacy error message compatibility
    if target_stage == "lasting":
        upper_ready = True
        bottom_ready = True
        if fallback_components:
            if not fallback_components.get("upper_done"):
                upper_ready = False
            if not fallback_components.get("bottom_done"):
                bottom_ready = False
        if component_tracks:
            if "upper" in specs_comps and component_tracks.get("upper", {}).get("status") != "ready":
                upper_ready = False
            if "bottom" in specs_comps and component_tracks.get("bottom", {}).get("status") != "ready":
                bottom_ready = False

        if not upper_ready and not bottom_ready:
            return False, "Cannot move to lasting: upper and bottom/insole not completed"
        elif not upper_ready:
            return False, "Cannot move to lasting: upper not completed"
        elif not bottom_ready:
            return False, "Cannot move to lasting: bottom/insole not completed"
        return True, None

    # Special-case sole_pasting gate
    if target_stage == "sole_pasting":
        sole_ready = True
        heel_ready = True
        if fallback_components and "sole_done" in fallback_components:
            if not fallback_components.get("sole_done"):
                sole_ready = False
        if component_tracks:
            if "sole" in specs_comps and component_tracks.get("sole", {}).get("status") != "ready":
                sole_ready = False
            if footwear_type == "heel" and "heel_gola" in specs_comps:
                if component_tracks.get("heel_gola", {}).get("status") != "ready":
                    heel_ready = False

        if not sole_ready and not heel_ready:
            return False, "Cannot move to sole_pasting: sole and heel/gola not completed"
        elif not sole_ready:
            return False, "Cannot move to sole_pasting: sole not completed"
        elif not heel_ready:
            return False, "Cannot move to sole_pasting: heel/gola not completed"
        return True, None

    # Generic gate fallback if other target stages configured in MERGE_GATES
    required = list(MERGE_GATES[target_stage])
    if component_tracks:
        blocking = []
        for req in required:
            if req not in specs_comps:
                continue
            track = component_tracks.get(req) or {}
            if track.get("status") != "ready":
                current = track.get("current_stage") or "pending"
                blocking.append(f"{req} (currently at '{current}')")
        if blocking:
            return False, f"Cannot move to {target_stage}: required components not ready: {', '.join(blocking)}"

    return True, None
