"""2D Interlocking Nesting & Multi-Component Yield Calculation Engine.

Calculates exact raw material consumption (meters/pair, sheets/pair),
yield per unit (pairs/meter, pairs/sheet), cutting efficiency %, waste %,
and generates 2D vector layout coordinates for visual preview across:
- Continuous rolls (e.g. 54", 58", 60" Synthetic Rexine / PVC / Fabric)
- Standard sheets (e.g. 40"x60" EVA Cushioning Foam, Shank Board)
- Standard Linear Components (Folded Laces/Straps: Cut Width = 2 * Folded Width)
- Standard Die-Cut Insole & Bottom Covering (Preset fixed factory yields)
"""

import math
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("yield_nesting")

INCH_TO_MM = 25.4

# Distinct color palette for visual nesting pieces
PIECE_COLORS = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#8b5cf6",  # purple
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#f97316",  # orange
]

# Standard Footwear Preset Components (Fixed factory yields, no scanning required)
STANDARD_FACTORY_PRESETS = [
    {
        "component_key": "insole_board_diecut",
        "name": "Standard Die-Cut Cellulose Insole Board",
        "material_type": "sheet",
        "is_standard_preset": True,
        "consumption_per_pair": 0.0385,  # 26 pairs per 40"x60" sheet
        "consumption_unit": "sheet",
        "yield_per_unit": 26.0,
        "yield_unit_label": "pairs / sheet",
        "waste_pct": 5.0,
        "notes": "Standard die-cut insole board yield preset (not recalculated from scan)",
    },
    {
        "component_key": "cushioning_eva_diecut",
        "name": "Standard Die-Cut EVA Cushioning Foam (3mm/4mm)",
        "material_type": "sheet",
        "is_standard_preset": True,
        "consumption_per_pair": 0.040,   # 25 pairs per 40"x60" sheet
        "consumption_unit": "sheet",
        "yield_per_unit": 25.0,
        "yield_unit_label": "pairs / sheet",
        "waste_pct": 4.0,
        "notes": "Standard EVA foam cushioning sheet yield preset",
    },
    {
        "component_key": "socks_bottom_covering",
        "name": "Standard Insole Socks / Bottom Covering Material",
        "material_type": "roll",
        "is_standard_preset": True,
        "consumption_per_pair": 0.125,  # 8 pairs per running meter of 54" roll
        "consumption_unit": "meter",
        "yield_per_unit": 8.0,
        "yield_unit_label": "pairs / meter",
        "waste_pct": 5.0,
        "notes": "Standard bottom/socks covering yield preset",
    },
    {
        "component_key": "outsole_ready",
        "name": "Standard Ready Made Outsole & Heel",
        "material_type": "pair",
        "is_standard_preset": True,
        "consumption_per_pair": 1.0,
        "consumption_unit": "pair",
        "yield_per_unit": 1.0,
        "yield_unit_label": "pairs / pair",
        "waste_pct": 0.0,
        "notes": "Ready-made sole mould (1 pair per pair)",
    },
]


def calculate_standard_strip(
    strip: Optional[Dict[str, Any]] = None,
    roll_width_inches: float = 54.0,
    roll_width_mm: Optional[float] = None,
    selvage_margin_mm: float = 20.0,
    kerf_mm: float = 1.0,
    waste_pct: float = 5.0,
    roll_length_meters: float = 1.0,
    **kwargs,
) -> Dict[str, Any]:
    """Calculate yield for folded laces/straps using the 2x folded width formula.
    
    Formula:
        Raw Cut Width = 2 * Folded Width (e.g. 8mm folded lace -> 16mm cut strip).
    
    Yield Calculations:
        1. Slitting Lanes = Usable Roll Width // (Cut Width + Kerf)
        2. Lace Ribbon Length per 1 Meter of Roll = Lanes * 1.0 meter
        3. Total Laces Yielded in 1 Meter of Roll = (Lanes * 1000mm) / Length per Lace (mm)
        4. Pairs Yielded per 1 Meter of Roll = Laces Yielded / Pieces per Pair
    """
    strip_dict = dict(strip or {})
    strip_dict.update(kwargs)

    strip_type = str(strip_dict.get("strip_type") or "folded").lower()
    cut_orientation = str(strip_dict.get("cut_orientation") or "along_length").lower()

    if strip_type == "unfolded":
        cut_w = float(strip_dict.get("strip_width_mm") or strip_dict.get("cut_width_mm") or 15.0)
        folded_w = cut_w
    else:
        folded_w = float(strip_dict.get("folded_width_mm") or 8.0)
        # User's formula: 2 times the folded width
        cut_w = float(strip_dict.get("cut_width_mm") or (folded_w * 2.0))

    # Material specific width overrides (Lace material length/width definition)
    mat_w_val = strip_dict.get("material_width")
    mat_w_unit = str(strip_dict.get("material_width_unit") or "inch").lower()
    mat_w_mm = strip_dict.get("material_width_mm")

    if mat_w_mm is not None and float(mat_w_mm) > 0:
        actual_roll_width_mm = float(mat_w_mm)
    elif mat_w_val is not None and float(mat_w_val) > 0:
        scale = 25.4 if ("in" in mat_w_unit or "inch" in mat_w_unit) else (10.0 if "cm" in mat_w_unit else 1.0)
        actual_roll_width_mm = float(mat_w_val) * scale
    elif roll_width_mm is not None:
        actual_roll_width_mm = float(roll_width_mm)
    else:
        actual_roll_width_mm = float(roll_width_inches or 50.0) * INCH_TO_MM

    usable_width_mm = max(50.0, actual_roll_width_mm - (2 * selvage_margin_mm))

    # Defined length: if cut across width of material, default length is the width of selected material
    raw_len = strip_dict.get("length_mm")
    if cut_orientation == "across_width":
        if not raw_len or float(raw_len) <= 0 or float(raw_len) == 650.0:
            length_mm = float(actual_roll_width_mm)
        else:
            length_mm = float(raw_len)
    else:
        length_mm = float(raw_len or 650.0)

    pieces_per_pair = max(1, int(strip_dict.get("pieces_per_pair") or 2))
    total_length_pair_mm = length_mm * pieces_per_pair
    net_area_sqcm = round((cut_w * total_length_pair_mm) / 100.0, 2)

    # Material specific length overrides (Lace material length definition)
    mat_len_val = strip_dict.get("material_length")
    mat_len_unit = str(strip_dict.get("material_length_unit") or "meter").lower()
    mat_len_m = strip_dict.get("material_length_meters")

    if mat_len_m is not None and float(mat_len_m) > 0:
        roll_len = float(mat_len_m)
    elif mat_len_val is not None and float(mat_len_val) > 0:
        scale_m = 0.0254 if ("in" in mat_len_unit or "inch" in mat_len_unit) else (0.9144 if "yd" in mat_len_unit or "yard" in mat_len_unit else 1.0)
        roll_len = float(mat_len_val) * scale_m
    else:
        roll_len = max(0.1, float(roll_length_meters or 1.0))

    # Yield calculation based on cutting orientation
    if cut_orientation == "across_width":
        # Strips cut crosswise across material roll width (guillotine / cross-cut)
        cuts_per_meter = max(1, int(1000.0 // (cut_w + kerf_mm)))
        strips_per_cut = 1 if length_mm >= (usable_width_mm * 0.95) else max(1, int(usable_width_mm // length_mm))
        laces_yield_per_meter = round(float(cuts_per_meter * strips_per_cut), 2)
        lanes = cuts_per_meter
        total_lace_meters_per_roll_meter = round((laces_yield_per_meter * length_mm) / 1000.0, 2)
    else:
        # Continuous slitting lanes across roll usable width
        lanes = max(1, int((usable_width_mm + kerf_mm) // (cut_w + kerf_mm)))
        total_mm_lace_per_meter_roll = lanes * 1000.0
        total_lace_meters_per_roll_meter = round(lanes * 1.0, 2)
        laces_yield_per_meter = round(total_mm_lace_per_meter_roll / length_mm, 2) if length_mm > 0 else 0.0

    # Pairs yield from 1 linear meter of roll (before waste):
    raw_pairs_per_meter = laces_yield_per_meter / pieces_per_pair if pieces_per_pair > 0 else 0.0

    # Roll consumption per pair with waste buffer:
    waste_mult = 1.0 + (waste_pct / 100.0)
    consumption_per_pair = round((1.0 / raw_pairs_per_meter) * waste_mult, 5) if raw_pairs_per_meter > 0 else 0.0
    final_yield_per_meter = round(1.0 / consumption_per_pair, 2) if consumption_per_pair > 0 else 0.0

    # Total laces & pairs produced from the specified roll length:
    total_laces_full_roll = round(laces_yield_per_meter * roll_len)
    total_pairs_full_roll = round(final_yield_per_meter * roll_len)

    # Unit conversions for display
    length_inches = round(length_mm / INCH_TO_MM, 2)
    length_cm = round(length_mm / 10.0, 2)
    folded_width_inches = round(folded_w / INCH_TO_MM, 3)
    cut_width_inches = round(cut_w / INCH_TO_MM, 3)

    # Material info and cost calculation
    mat_id = strip_dict.get("material_id")
    mat_name = strip_dict.get("material_name")
    mat_code = strip_dict.get("material_code")
    mat_rate = float(strip_dict.get("material_rate") or 0.0)
    cost_per_pair = round(consumption_per_pair * mat_rate, 2) if mat_rate > 0 else 0.0

    mat_label = f" ({mat_name})" if mat_name else ""
    dim_desc = f" [{round(actual_roll_width_mm / INCH_TO_MM, 1)}\"W × {roll_len}mL]"
    orient_label = "Cross-cut across roll width" if cut_orientation == "across_width" else f"{lanes} continuous slitting lanes"

    if strip_type == "unfolded":
        formula_note = (
            f"Unfolded Strip (Width {cut_w}mm) · {orient_label} · Default length {round(length_mm, 1)}mm{mat_label}{dim_desc} · "
            f"Yields {laces_yield_per_meter} strips/m · Full Roll ({roll_len}m): {total_laces_full_roll} strips"
        )
    else:
        formula_note = (
            f"Raw cut width ({cut_w}mm) = 2 × folded width ({folded_w}mm){mat_label}{dim_desc} · "
            f"Yields {laces_yield_per_meter} laces/m ({orient_label}) · Full Roll ({roll_len}m): {total_laces_full_roll} laces"
        )

    return {
        "strip_id": strip_dict.get("strip_id") or f"strip_{folded_w}mm",
        "name": strip_dict.get("name") or (f"Unfolded Strip {cut_w}mm" if strip_type == "unfolded" else f"Folded Lace {folded_w}mm"),
        "strip_type": strip_type,
        "cut_orientation": cut_orientation,
        "strip_width_mm": cut_w if strip_type == "unfolded" else None,
        "strip_width_label": f"{cut_w}mm" if strip_type == "unfolded" else None,
        "folded_width_mm": folded_w,
        "folded_width_inches": folded_width_inches,
        "cut_width_mm": cut_w,
        "cut_width_inches": cut_width_inches,
        "length_mm": length_mm,
        "length_cm": length_cm,
        "length_inches": length_inches,
        "pieces_per_pair": pieces_per_pair,
        "total_length_pair_mm": total_length_pair_mm,
        "net_area_sqcm": net_area_sqcm,
        "lanes_across_roll": lanes,
        "total_lace_meters_per_roll_meter": total_lace_meters_per_roll_meter,
        "laces_yield_per_meter": laces_yield_per_meter,
        "pairs_per_meter": round(raw_pairs_per_meter, 2),
        "consumption_per_pair": consumption_per_pair,
        "yield_per_unit": final_yield_per_meter,
        "consumption_unit": "meter",
        "yield_unit_label": "strips / meter" if strip_type == "unfolded" else "pairs / meter",
        "roll_length_meters": roll_len,
        "total_laces_full_roll": total_laces_full_roll,
        "total_pairs_full_roll": total_pairs_full_roll,
        "cutting_direction": "width_up" if cut_orientation == "across_width" else (strip_dict.get("cutting_direction") or "length_up"),
        "formula_note": formula_note,
        "component": "unfolded_strip" if strip_type == "unfolded" else (strip_dict.get("component") or "upper"),
        "material_id": mat_id,
        "material_name": mat_name,
        "material_code": mat_code,
        "material_rate": mat_rate,
        "material_form": strip_dict.get("material_form") or "roll",
        "material_width": strip_dict.get("material_width") or round(actual_roll_width_mm / INCH_TO_MM, 2),
        "material_width_unit": strip_dict.get("material_width_unit") or "inch",
        "material_width_mm": round(actual_roll_width_mm, 2),
        "material_length": strip_dict.get("material_length") or roll_len,
        "material_length_unit": strip_dict.get("material_length_unit") or "meter",
        "material_length_meters": roll_len,
        "cost_per_pair": cost_per_pair,
    }


def _build_strip_preview(st: Dict[str, Any], roll_width_mm: float, selvage_margin_mm: float, visual_sample_length_mm: float = 1000.0) -> Dict[str, Any]:
    st_cut_w = float(st.get("cut_width_mm") or 16.0)
    usable_w = max(100.0, roll_width_mm - 2 * selvage_margin_mm)
    placed_items = []
    cut_orientation = str(st.get("cut_orientation") or "along_length").lower()
    is_unfolded = str(st.get("strip_type") or "folded").lower() == "unfolded"
    color = "#06b6d4" if is_unfolded else "#f97316"

    if cut_orientation == "across_width":
        # Crosswise horizontal strips cut across the material roll width
        cur_y = selvage_margin_mm
        max_y = visual_sample_length_mm - selvage_margin_mm
        count = 0
        while cur_y + st_cut_w <= max_y and count < 40:
            placed_items.append({
                "piece_id": st.get("strip_id") or f"st_cross_{count}",
                "piece_name": f"{st.get('name', 'Unfolded Strip')} ({round(usable_w, 1)}×{round(st_cut_w, 1)}mm)",
                "color": color,
                "x_mm": round(selvage_margin_mm, 1),
                "y_mm": round(cur_y, 1),
                "w_mm": round(usable_w, 1),
                "h_mm": round(st_cut_w, 1),
                "rotation": 0,
                "is_strip": True,
            })
            cur_y += st_cut_w + 2.0
            count += 1
    else:
        # Vertical continuous slitting lanes running down the roll length
        lanes = max(1, int(usable_w // (st_cut_w + 1.0)))
        lane_h = visual_sample_length_mm - 40.0
        for lane_i in range(min(50, lanes)):
            lane_x = selvage_margin_mm + lane_i * (st_cut_w + 1.0)
            placed_items.append({
                "piece_id": st.get("strip_id") or f"st_{lane_i}",
                "piece_name": f"{st.get('name', 'Folded Lace')} ({round(st_cut_w, 1)}mm)",
                "color": color,
                "x_mm": round(lane_x, 1),
                "y_mm": 20.0,
                "w_mm": round(st_cut_w, 1),
                "h_mm": round(lane_h, 1),
                "rotation": 0,
                "is_strip": True,
            })

    return {
        "canvas_width_mm": round(roll_width_mm, 1),
        "canvas_height_mm": round(visual_sample_length_mm, 1),
        "selvage_left_x": 0.0,
        "selvage_left_w": selvage_margin_mm,
        "selvage_right_x": round(roll_width_mm - selvage_margin_mm, 1),
        "selvage_right_w": selvage_margin_mm,
        "placed_items": placed_items,
        "shelves_count": 1,
        "width_utilization_pct": 98.0,
    }


def simulate_nesting(
    pieces: Optional[List[Dict[str, Any]]] = None,
    material_type: str = "roll",
    roll_width_inches: float = 54.0,
    custom_roll_width_mm: Optional[float] = None,
    sheet_length_mm: Optional[float] = None,
    sheet_width_mm: Optional[float] = None,
    selvage_margin_mm: float = 20.0,
    kerf_spacing_mm: float = 3.0,
    waste_allowance_pct: float = 5.0,
    visual_sample_length_mm: float = 1000.0,
    standard_strips: Optional[List[Dict[str, Any]]] = None,
    standard_presets: Optional[List[Dict[str, Any]]] = None,
    cutting_direction: str = "length_up",
    roll_length_meters: float = 1.0,
    expected_pieces_count: Optional[int] = None,
    measurement_unit: str = "mm",
    upper_spec: Optional[Dict[str, Any]] = None,
    lining_material_id: Optional[str] = None,
    lining_material_name: Optional[str] = None,
    lining_material_code: Optional[str] = None,
    canvas_backing: Optional[str] = None,
    materials_info: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Calculate nesting metrics and generate 2D layout coordinates across all components.
    
    Supports:
    - Scanned irregular pattern pieces (Vamps, Quarters, Straps)
    - Cutting Direction / Stretch control (length_up [default / no stretch], width_up, both)
    - Formula-based standard folded laces / linear strips (Cut Width = 2 * Folded Width)
    - Full roll length calculation (e.g. 50m factory roll yield)
    - Custom roll width and flexible measurement units (mm, cm, inches)
    - Standard die-cut insole board and bottom covering presets
    - Tech Pack Lining & Canvas Reinforcement Backing calculation
    """
    pieces = pieces or []
    standard_strips = standard_strips or []
    standard_presets = standard_presets or []
    upper_spec_dict = dict(upper_spec or {})

    actual_roll_width_mm = custom_roll_width_mm if custom_roll_width_mm is not None else (roll_width_inches * INCH_TO_MM)
    actual_roll_width_inches = round(actual_roll_width_mm / INCH_TO_MM, 2)

    # Calculate standard linear strips (formula-based)
    calculated_strips = [
        calculate_standard_strip(
            strip=st,
            roll_width_inches=actual_roll_width_inches,
            roll_width_mm=actual_roll_width_mm,
            selvage_margin_mm=selvage_margin_mm,
            kerf_mm=1.0,
            waste_pct=waste_allowance_pct,
            roll_length_meters=roll_length_meters,
        )
        for st in standard_strips
    ]

    # If no irregular pieces and no strips, return empty result
    if not pieces and not calculated_strips:
        res = _empty_yield_result(material_type)
        res["cutting_direction"] = cutting_direction
        res["measurement_unit"] = measurement_unit
        res["expected_pieces_count"] = expected_pieces_count
        return res

    if material_type == "sheet":
        base_res = _simulate_sheet_nesting(
            pieces=pieces,
            sheet_length_mm=sheet_length_mm or 1524.0,  # 60 inches
            sheet_width_mm=sheet_width_mm or 1016.0,   # 40 inches
            margin_mm=selvage_margin_mm,
            kerf_mm=kerf_spacing_mm,
            waste_pct=waste_allowance_pct,
        )
    else:
        # Default: Roll Nesting
        base_res = _simulate_roll_nesting(
            pieces=pieces,
            roll_width_inches=actual_roll_width_inches,
            roll_width_mm=actual_roll_width_mm,
            selvage_margin_mm=selvage_margin_mm,
            kerf_mm=kerf_spacing_mm,
            waste_pct=waste_allowance_pct,
            visual_sample_length_mm=visual_sample_length_mm,
            calculated_strips=calculated_strips,
            cutting_direction=cutting_direction,
            roll_length_meters=roll_length_meters,
        )

    # Attach standard strips and standard presets
    base_res["standard_strips"] = calculated_strips
    base_res["standard_presets"] = standard_presets or STANDARD_FACTORY_PRESETS
    base_res["cutting_direction"] = cutting_direction
    base_res["roll_length_meters"] = roll_length_meters
    base_res["measurement_unit"] = measurement_unit
    base_res["expected_pieces_count"] = expected_pieces_count

    # Build Multi-Component Breakdown
    # 1. Upper Irregular Nested Pieces
    upper_pieces = [p for p in pieces if p.get("component", "upper") == "upper"]
    lining_pieces = [p for p in pieces if p.get("component") == "lining"]
    canvas_pieces = [p for p in pieces if p.get("component") in ("canvas", "canvas_backing")]

    upper_net_area = sum((p.get("area_sqcm") or 0.0) * (p.get("pieces_per_pair") or 2) for p in upper_pieces)
    strip_net_area = sum(st["net_area_sqcm"] for st in calculated_strips if st.get("component") == "upper")
    total_upper_net_area = round(upper_net_area + strip_net_area, 2)

    # Upper total consumption (nested pieces + laces/strips)
    strip_consumption = sum(st["consumption_per_pair"] for st in calculated_strips if st.get("component") == "upper")
    total_upper_consumption = round(base_res["consumption_per_pair"] + strip_consumption, 4)
    total_upper_yield = round(1.0 / total_upper_consumption, 2) if total_upper_consumption > 0 else 0.0

    # Total pairs from specified roll length
    if material_type == "roll" and total_upper_consumption > 0:
        base_res["total_pairs_per_roll"] = round(roll_length_meters / total_upper_consumption)
    else:
        base_res["total_pairs_per_roll"] = round(base_res.get("yield_per_unit", 0.0) * roll_length_meters)

    component_breakdown = {
        "upper": {
            "name": "Upper Component (Nested Patterns + Folded Laces)",
            "consumption_per_pair": total_upper_consumption,
            "consumption_unit": "meter" if material_type == "roll" else "sheet",
            "yield_per_unit": total_upper_yield,
            "yield_unit_label": "pairs / meter" if material_type == "roll" else "pairs / sheet",
            "net_area_sqcm_per_pair": total_upper_net_area,
            "scanned_pieces_count": len(upper_pieces),
            "standard_strips_count": len(calculated_strips),
            "cutting_direction": cutting_direction,
        },
        "lining": {
            "name": "Upper Lining Component",
            "pieces_count": len(lining_pieces),
            "net_area_sqcm_per_pair": round(sum((p.get("area_sqcm") or 0.0) * (p.get("pieces_per_pair") or 2) for p in lining_pieces), 2),
        },
        "standard_insole": next((p for p in (standard_presets or STANDARD_FACTORY_PRESETS) if "insole" in p.get("component_key", "")), None),
        "standard_bottom_covering": next((p for p in (standard_presets or STANDARD_FACTORY_PRESETS) if "socks" in p.get("component_key", "")), None),
    }

    # Tech Pack Multi-Material Breakdown (Upper Top materials only — Lining & Canvas are calculated separately):
    material_breakdowns = []
    distinct_materials: Dict[str, Dict[str, Any]] = {}
    for p in (upper_pieces if upper_pieces else pieces):
        if p.get("component") in ("lining", "canvas", "canvas_backing"):
            continue
        mid = p.get("material_id") or p.get("material_name") or "primary_upper"
        if mid not in distinct_materials:
            distinct_materials[mid] = {
                "material_id": p.get("material_id"),
                "material_name": p.get("material_name") or "Primary Upper Material",
                "material_code": p.get("material_code") or "",
                "placement": p.get("placement") or p.get("component", "Upper"),
                "pieces": [],
            }
        distinct_materials[mid]["pieces"].append(p)

    mat_lookup = materials_info or {}

    def _resolve_mat_dims(mat_id: Optional[str], fallback_roll_in: float, fallback_roll_mm: float):
        mdoc = mat_lookup.get(mat_id) if mat_id else None
        if not mdoc:
            return "roll", fallback_roll_in, fallback_roll_mm, sheet_length_mm or 1524.0, sheet_width_mm or 1016.0
        mform = mdoc.get("material_form") or "roll"
        dim_unit = (mdoc.get("dimension_unit") or "inch").lower()
        mult = INCH_TO_MM if "in" in dim_unit else (10.0 if "cm" in dim_unit else (1000.0 if dim_unit == "m" else 1.0))
        if mform == "sheet":
            sw_mm = float(mdoc.get("width_mm") or (float(mdoc.get("sheet_width") or 40.0) * mult))
            sh_mm = float(mdoc.get("height_mm") or (float(mdoc.get("sheet_height") or 60.0) * mult))
            return "sheet", fallback_roll_in, fallback_roll_mm, max(sw_mm, sh_mm), min(sw_mm, sh_mm)
        rw_mm = float(mdoc.get("width_mm") or (float(mdoc.get("roll_width") or fallback_roll_in) * mult))
        rw_in = round(rw_mm / INCH_TO_MM, 2)
        return "roll", rw_in, rw_mm, sheet_length_mm or 1524.0, sheet_width_mm or 1016.0

    for mid, minfo in distinct_materials.items():
        mat_pieces = minfo["pieces"]
        mat_strips = [st for st in calculated_strips if st.get("material_id") == minfo["material_id"]] if minfo["material_id"] else []
        mform, m_roll_in, m_roll_mm, m_sheet_l, m_sheet_w = _resolve_mat_dims(
            minfo.get("material_id"), actual_roll_width_inches, actual_roll_width_mm
        )
        if mform == "sheet":
            mat_res = _simulate_sheet_nesting(
                pieces=mat_pieces,
                sheet_length_mm=m_sheet_l,
                sheet_width_mm=m_sheet_w,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=waste_allowance_pct,
                cutting_direction=cutting_direction,
            )
        else:
            mat_res = _simulate_roll_nesting(
                pieces=mat_pieces,
                roll_width_inches=m_roll_in,
                roll_width_mm=m_roll_mm,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=waste_allowance_pct,
                visual_sample_length_mm=visual_sample_length_mm,
                calculated_strips=mat_strips,
                cutting_direction=cutting_direction,
                roll_length_meters=roll_length_meters,
            )
        material_breakdowns.append({
            "material_id": minfo["material_id"],
            "material_name": minfo["material_name"],
            "material_code": minfo["material_code"],
            "placement": minfo["placement"],
            "pieces_count": len(mat_pieces),
            "pieces": [
                {
                    "piece_id": p.get("piece_id"),
                    "piece_name": p.get("piece_name"),
                    "area_sqcm": p.get("area_sqcm"),
                    "pieces_per_pair": p.get("pieces_per_pair", 2),
                    "length_mm": p.get("length_mm"),
                    "width_mm": p.get("width_mm"),
                    "color": p.get("color"),
                    "svg_polygon": p.get("svg_polygon") or p.get("svg_path"),
                    "svg_path": p.get("svg_path") or p.get("svg_polygon"),
                }
                for p in mat_pieces
            ],
            "consumption_per_pair": mat_res["consumption_per_pair"],
            "consumption_unit": mat_res["consumption_unit"],
            "yield_per_unit": mat_res["yield_per_unit"],
            "yield_unit_label": mat_res["yield_unit_label"],
            "net_area_sqcm_per_pair": mat_res["net_area_sqcm_per_pair"],
            "utilization_pct": mat_res["utilization_pct"],
            "waste_pct": mat_res["waste_pct"],
            "visual_nesting_preview": mat_res["visual_nesting_preview"],
        })

    # Tech Pack Lining Component Calculation
    eff_lining_id = lining_material_id or upper_spec_dict.get("lining_material_id")
    eff_lining_name = lining_material_name or upper_spec_dict.get("lining_material_name")
    eff_lining_code = lining_material_code or upper_spec_dict.get("lining_material_code") or ""
    has_lining = bool(eff_lining_id or eff_lining_name)

    lining_target_pieces = lining_pieces if lining_pieces else upper_pieces
    if lining_target_pieces:
        lining_pieces_nest = [dict(p) for p in lining_target_pieces]
        for lp in lining_pieces_nest:
            lp["color"] = "#10b981"  # emerald green
        l_form, l_roll_in, l_roll_mm, l_sheet_l, l_sheet_w = _resolve_mat_dims(
            eff_lining_id, 54.0, 54.0 * INCH_TO_MM
        )
        if l_form == "sheet":
            lining_res = _simulate_sheet_nesting(
                pieces=lining_pieces_nest,
                sheet_length_mm=l_sheet_l,
                sheet_width_mm=l_sheet_w,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=4.0,
                cutting_direction="length_up",
            )
        else:
            lining_res = _simulate_roll_nesting(
                pieces=lining_pieces_nest,
                roll_width_inches=l_roll_in,
                roll_width_mm=l_roll_mm,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=4.0,
                visual_sample_length_mm=visual_sample_length_mm,
                cutting_direction="length_up",
                roll_length_meters=roll_length_meters,
            )
        lining_entry = {
            "material_id": eff_lining_id or "lining_default",
            "material_name": eff_lining_name or "Upper Footwear Lining (54\" Roll)",
            "material_code": eff_lining_code or "LINING-54",
            "placement": "Upper Lining",
            "is_lining": True,
            "pieces_count": len(lining_target_pieces),
            "pieces": [
                {
                    "piece_id": f"lin_{p.get('piece_id')}",
                    "piece_name": f"{p.get('piece_name')} (Lining)",
                    "area_sqcm": p.get("area_sqcm"),
                    "pieces_per_pair": p.get("pieces_per_pair", 2),
                    "length_mm": p.get("length_mm"),
                    "width_mm": p.get("width_mm"),
                    "color": "#10b981",
                    "svg_polygon": p.get("svg_polygon") or p.get("svg_path"),
                    "svg_path": p.get("svg_path") or p.get("svg_polygon"),
                }
                for p in lining_target_pieces
            ],
            "consumption_per_pair": lining_res["consumption_per_pair"],
            "consumption_unit": "meter",
            "yield_per_unit": lining_res["yield_per_unit"],
            "yield_unit_label": "pairs / meter",
            "net_area_sqcm_per_pair": lining_res["net_area_sqcm_per_pair"],
            "utilization_pct": lining_res["utilization_pct"],
            "waste_pct": lining_res["waste_pct"],
            "visual_nesting_preview": lining_res["visual_nesting_preview"],
        }
        component_breakdown["lining"] = lining_entry
        if has_lining:
            material_breakdowns.append(lining_entry)

    # Tech Pack Canvas Backing / Reinforcement Calculation
    eff_canvas_id = upper_spec_dict.get("canvas_material_id")
    eff_canvas = canvas_backing or upper_spec_dict.get("canvas_material_name") or upper_spec_dict.get("canvas_backing") or ""
    eff_canvas_code = upper_spec_dict.get("canvas_material_code") or "CANVAS-48"
    has_canvas = bool(eff_canvas_id or (eff_canvas and eff_canvas.strip()))
    canvas_target_pieces = canvas_pieces if canvas_pieces else upper_pieces
    if canvas_target_pieces:
        canvas_pieces_nest = [dict(p) for p in canvas_target_pieces]
        for cp in canvas_pieces_nest:
            cp["color"] = "#f59e0b"  # amber
        c_form, c_roll_in, c_roll_mm, c_sheet_l, c_sheet_w = _resolve_mat_dims(
            eff_canvas_id, 48.0, 48.0 * INCH_TO_MM
        )
        if c_form == "sheet":
            canvas_res = _simulate_sheet_nesting(
                pieces=canvas_pieces_nest,
                sheet_length_mm=c_sheet_l,
                sheet_width_mm=c_sheet_w,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=3.0,
                cutting_direction="length_up",
            )
        else:
            canvas_res = _simulate_roll_nesting(
                pieces=canvas_pieces_nest,
                roll_width_inches=c_roll_in,
                roll_width_mm=c_roll_mm,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=3.0,
                visual_sample_length_mm=visual_sample_length_mm,
                cutting_direction="length_up",
                roll_length_meters=roll_length_meters,
            )
        canvas_entry = {
            "material_id": eff_canvas_id or (f"canvas_{eff_canvas.lower().replace(' ', '_')}" if eff_canvas else "canvas_backing_default"),
            "material_name": f"Canvas / Interlining: {eff_canvas}" if eff_canvas else "Upper Canvas Reinforcement Backing (48\" Roll)",
            "material_code": eff_canvas_code,
            "placement": "Upper Reinforcement Backing",
            "specification": eff_canvas or "Cotton / Drill Canvas",
            "is_canvas": True,
            "pieces_count": len(upper_pieces),
            "pieces": [
                {
                    "piece_id": f"cv_{p.get('piece_id')}",
                    "piece_name": f"{p.get('piece_name')} (Canvas Backing)",
                    "area_sqcm": p.get("area_sqcm"),
                    "pieces_per_pair": p.get("pieces_per_pair", 2),
                    "length_mm": p.get("length_mm"),
                    "width_mm": p.get("width_mm"),
                    "color": "#f59e0b",
                    "svg_polygon": p.get("svg_polygon") or p.get("svg_path"),
                    "svg_path": p.get("svg_path") or p.get("svg_polygon"),
                }
                for p in upper_pieces
            ],
            "consumption_per_pair": canvas_res["consumption_per_pair"],
            "consumption_unit": "meter",
            "yield_per_unit": canvas_res["yield_per_unit"],
            "yield_unit_label": "pairs / meter",
            "net_area_sqcm_per_pair": canvas_res["net_area_sqcm_per_pair"],
            "utilization_pct": canvas_res["utilization_pct"],
            "waste_pct": canvas_res["waste_pct"],
            "visual_nesting_preview": canvas_res["visual_nesting_preview"],
        }
        component_breakdown["canvas_reinforcement"] = canvas_entry
        if has_canvas:
            material_breakdowns.append(canvas_entry)

    # Style BOM Summary: Total & Average Material Consumption for all pieces, laces, lining & canvas
    upper_top_mats = [mb for mb in material_breakdowns if not mb.get("is_lining") and not mb.get("is_canvas")]
    tot_upper_top_cons = round(sum(mb["consumption_per_pair"] for mb in upper_top_mats), 4)
    avg_upper_top_cons = round(tot_upper_top_cons / max(1, len(upper_top_mats)), 4) if upper_top_mats else round(base_res["consumption_per_pair"], 4)

    lining_cons = component_breakdown.get("lining", {}).get("consumption_per_pair", 0.0) if (has_lining or component_breakdown.get("lining")) else 0.0
    canvas_cons = component_breakdown.get("canvas_reinforcement", {}).get("consumption_per_pair", 0.0) if has_canvas else 0.0
    strip_cons = round(sum(st["consumption_per_pair"] for st in calculated_strips), 4)

    std_insole = next((p for p in (standard_presets or STANDARD_FACTORY_PRESETS) if "insole" in p.get("component_key", "")), None)
    std_socks = next((p for p in (standard_presets or STANDARD_FACTORY_PRESETS) if "socks" in p.get("component_key", "")), None)
    insole_cons = std_insole.get("consumption_per_pair", 0.0385) if std_insole else 0.0385
    socks_cons = std_socks.get("consumption_per_pair", 0.125) if std_socks else 0.125

    base_res["bom_summary"] = {
        "total_upper_top_consumption": tot_upper_top_cons,
        "avg_upper_top_consumption": avg_upper_top_cons,
        "laces_consumption": strip_cons,
        "lining_consumption": lining_cons,
        "canvas_consumption": canvas_cons,
        "insole_board_consumption": insole_cons,
        "socks_covering_consumption": socks_cons,
        "total_upper_consumption_per_pair": round(tot_upper_top_cons + strip_cons, 4),
        "total_shoe_roll_consumption": round(tot_upper_top_cons + strip_cons + lining_cons + canvas_cons + socks_cons, 4),
        "overall_avg_efficiency_pct": round(
            sum(mb["utilization_pct"] for mb in material_breakdowns) / max(1, len(material_breakdowns)), 1
        ) if material_breakdowns else 85.0,
    }

    # Build Isolated Component Nestings: ONLY the selected component is mapped on its roll, zero mixing
    component_nestings = []
    for p_idx, p in enumerate(pieces):
        p_dir = p.get("cutting_direction") if (p.get("cutting_direction") and p.get("cutting_direction") != "inherit") else cutting_direction
        p_res = _simulate_roll_nesting(
            pieces=[p],
            roll_width_inches=actual_roll_width_inches,
            roll_width_mm=actual_roll_width_mm,
            selvage_margin_mm=selvage_margin_mm,
            kerf_mm=kerf_spacing_mm,
            waste_pct=waste_allowance_pct,
            visual_sample_length_mm=visual_sample_length_mm,
            calculated_strips=[],
            cutting_direction=p_dir,
            roll_length_meters=roll_length_meters,
        )
        component_nestings.append({
            "key": f"piece_{p.get('piece_id') or p_idx}",
            "type": "pattern_piece",
            "piece_id": p.get("piece_id") or f"piece_{p_idx}",
            "name": p.get("piece_name") or f"Component Piece {p_idx + 1}",
            "component_type": p.get("component_type") or p.get("component", "upper"),
            "material_id": p.get("material_id"),
            "material_name": p.get("material_name") or "Upper Material",
            "material_code": p.get("material_code") or "",
            "placement": p.get("placement") or "Upper",
            "pieces_per_pair": p.get("pieces_per_pair", 2),
            "area_sqcm": p.get("area_sqcm"),
            "length_mm": p.get("length_mm"),
            "width_mm": p.get("width_mm"),
            "color": p.get("color") or PIECE_COLORS[p_idx % len(PIECE_COLORS)],
            "consumption_per_pair": p_res["consumption_per_pair"],
            "consumption_unit": p_res["consumption_unit"],
            "yield_per_unit": p_res["yield_per_unit"],
            "yield_unit_label": p_res["yield_unit_label"],
            "net_area_sqcm_per_pair": p_res["net_area_sqcm_per_pair"],
            "utilization_pct": p_res["utilization_pct"],
            "waste_pct": p_res["waste_pct"],
            "visual_nesting_preview": p_res["visual_nesting_preview"],
        })

    # Add folded laces and unfolded strips as individual components
    for s_idx, st in enumerate(calculated_strips):
        st_prev = _build_strip_preview(st, actual_roll_width_mm, selvage_margin_mm, visual_sample_length_mm)
        is_unfolded = str(st.get("strip_type") or "folded").lower() == "unfolded"
        type_label = "Unfolded Strip" if is_unfolded else "Folded Lace"
        dim_label = f"{st.get('cut_width_mm')}mm wide" if is_unfolded else f"{st.get('folded_width_mm', 8)}mm folded"
        orient_label = "Across Width" if st.get("cut_orientation") == "across_width" else "Along Length"
        component_nestings.append({
            "key": f"strip_{st.get('strip_id') or s_idx}",
            "type": "unfolded_strip" if is_unfolded else "folded_lace",
            "strip_id": st.get("strip_id"),
            "name": f"{type_label}: {st.get('name', 'Strip')} ({dim_label} · {orient_label})",
            "component_type": "strip",
            "strip_type": st.get("strip_type", "folded"),
            "cut_orientation": st.get("cut_orientation", "along_length"),
            "material_id": st.get("material_id"),
            "material_name": st.get("material_name") or "Lace / Strip Material",
            "material_code": st.get("material_code") or "",
            "placement": "Upper Laces & Strips",
            "folded_width_mm": st.get("folded_width_mm"),
            "cut_width_mm": st.get("cut_width_mm"),
            "length_mm": st.get("length_mm"),
            "consumption_per_pair": st.get("consumption_per_pair"),
            "consumption_unit": "meter",
            "yield_per_unit": st.get("laces_yield_per_meter"),
            "yield_unit_label": "strips / meter" if is_unfolded else "laces / meter",
            "color": "#06b6d4" if is_unfolded else "#f97316",
            "visual_nesting_preview": st_prev,
        })

    # Add Upper Lining as isolated component & individual lining piece nestings (54" Roll)
    if has_lining and lining_target_pieces:
        for lp_idx, lp in enumerate(lining_target_pieces):
            lp_res = _simulate_roll_nesting(
                pieces=[{**lp, "color": "#10b981"}],
                roll_width_inches=54.0,
                roll_width_mm=54.0 * INCH_TO_MM,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=4.0,
                visual_sample_length_mm=visual_sample_length_mm,
                cutting_direction="length_up",
                roll_length_meters=roll_length_meters,
            )
            component_nestings.append({
                "key": f"piece_lining_{lp.get('piece_id') or lp_idx}",
                "type": "pattern_piece",
                "piece_id": f"lin_{lp.get('piece_id') or lp_idx}",
                "name": f"{lp.get('piece_name') or f'Piece {lp_idx + 1}'} (Lining)",
                "component_type": "lining",
                "material_id": eff_lining_id or "lining_default",
                "material_name": eff_lining_name or "Upper Lining Material",
                "material_code": eff_lining_code or "",
                "placement": "Upper Lining",
                "pieces_per_pair": lp.get("pieces_per_pair", 2),
                "area_sqcm": lp.get("area_sqcm"),
                "length_mm": lp.get("length_mm"),
                "width_mm": lp.get("width_mm"),
                "color": "#10b981",
                "consumption_per_pair": lp_res["consumption_per_pair"],
                "consumption_unit": "meter",
                "yield_per_unit": lp_res["yield_per_unit"],
                "yield_unit_label": "pairs / meter",
                "net_area_sqcm_per_pair": lp_res["net_area_sqcm_per_pair"],
                "utilization_pct": lp_res["utilization_pct"],
                "waste_pct": lp_res["waste_pct"],
                "visual_nesting_preview": lp_res["visual_nesting_preview"],
            })

        component_nestings.append({
            "key": "component_lining",
            "type": "lining",
            "name": f"Upper Lining ({eff_lining_name or 'Tech Pack Lining'})",
            "component_type": "lining",
            "material_id": eff_lining_id,
            "material_name": eff_lining_name or "Upper Lining Material",
            "material_code": eff_lining_code,
            "placement": "Upper Lining",
            "pieces_count": len(lining_target_pieces),
            "color": "#10b981",
            "consumption_per_pair": lining_res["consumption_per_pair"],
            "consumption_unit": "meter",
            "yield_per_unit": lining_res["yield_per_unit"],
            "yield_unit_label": "pairs / meter",
            "net_area_sqcm_per_pair": lining_res["net_area_sqcm_per_pair"],
            "utilization_pct": lining_res["utilization_pct"],
            "waste_pct": lining_res["waste_pct"],
            "visual_nesting_preview": (
                component_nestings[-1]["visual_nesting_preview"]
                if component_nestings and component_nestings[-1]["type"] == "pattern_piece"
                else lining_res["visual_nesting_preview"]
            ),
        })

    # Add Canvas Reinforcement as isolated component & individual canvas piece nestings (48" Roll)
    if has_canvas and upper_pieces:
        for cp_idx, cp in enumerate(upper_pieces):
            cp_res = _simulate_roll_nesting(
                pieces=[{**cp, "color": "#f59e0b"}],
                roll_width_inches=48.0,
                roll_width_mm=48.0 * INCH_TO_MM,
                selvage_margin_mm=selvage_margin_mm,
                kerf_mm=kerf_spacing_mm,
                waste_pct=3.0,
                visual_sample_length_mm=visual_sample_length_mm,
                cutting_direction="length_up",
                roll_length_meters=roll_length_meters,
            )
            component_nestings.append({
                "key": f"piece_canvas_{cp.get('piece_id') or cp_idx}",
                "type": "pattern_piece",
                "piece_id": f"cv_{cp.get('piece_id') or cp_idx}",
                "name": f"{cp.get('piece_name') or f'Piece {cp_idx + 1}'} (Canvas)",
                "component_type": "canvas_backing",
                "material_name": eff_canvas or "Sada Kada Canvas",
                "material_code": "CANVAS-48",
                "placement": "Reinforcement Backing",
                "pieces_per_pair": cp.get("pieces_per_pair", 2),
                "area_sqcm": cp.get("area_sqcm"),
                "length_mm": cp.get("length_mm"),
                "width_mm": cp.get("width_mm"),
                "color": "#f59e0b",
                "consumption_per_pair": cp_res["consumption_per_pair"],
                "consumption_unit": "meter",
                "yield_per_unit": cp_res["yield_per_unit"],
                "yield_unit_label": "pairs / meter",
                "net_area_sqcm_per_pair": cp_res["net_area_sqcm_per_pair"],
                "utilization_pct": cp_res["utilization_pct"],
                "waste_pct": cp_res["waste_pct"],
                "visual_nesting_preview": cp_res["visual_nesting_preview"],
            })

        component_nestings.append({
            "key": "component_canvas",
            "type": "canvas_backing",
            "name": f"Canvas / Reinforcement Backing ({eff_canvas or 'Sada Kada'})",
            "component_type": "canvas_backing",
            "material_name": eff_canvas or "Sada Kada",
            "placement": "Reinforcement Backing",
            "pieces_count": len(upper_pieces),
            "color": "#f59e0b",
            "consumption_per_pair": canvas_res["consumption_per_pair"],
            "consumption_unit": "meter",
            "yield_per_unit": canvas_res["yield_per_unit"],
            "yield_unit_label": "pairs / meter",
            "net_area_sqcm_per_pair": canvas_res["net_area_sqcm_per_pair"],
            "utilization_pct": canvas_res["utilization_pct"],
            "waste_pct": canvas_res["waste_pct"],
            "visual_nesting_preview": (
                component_nestings[-1]["visual_nesting_preview"]
                if component_nestings and component_nestings[-1]["type"] == "pattern_piece"
                else canvas_res["visual_nesting_preview"]
            ),
        })

    base_res["component_nestings"] = component_nestings
    if component_nestings:
        base_res["visual_nesting_preview"] = component_nestings[0]["visual_nesting_preview"]

    base_res["component_breakdown"] = component_breakdown
    base_res["material_breakdown"] = material_breakdowns
    return base_res


def _normalize_polygon_to_box(
    raw_pts: Optional[List[List[float]]],
    target_w: float,
    target_h: float,
) -> tuple[str, str]:
    """Normalizes polygon coordinates strictly inside [0, target_w] x [0, target_h].
    If raw points aspect ratio is opposite to target bounding box (e.g. piece was scanned
    horizontally but placed vertically for length-up cutting), rotates points 90 degrees clockwise
    so the piece's geometry is preserved without any stretching or deformation.
    Returns (normal_svg_path, inverted_180_svg_path).
    Mathematically guarantees that points strictly lie in [0, target_w] x [0, target_h]."""
    target_w = max(1.0, float(target_w))
    target_h = max(1.0, float(target_h))

    if not raw_pts or len(raw_pts) < 3:
        pts = [
            [round(target_w * 0.05, 1), round(target_h * 0.15, 1)],
            [round(target_w * 0.50, 1), 0.0],
            [round(target_w * 0.95, 1), round(target_h * 0.15, 1)],
            [round(target_w, 1), round(target_h * 0.50, 1)],
            [round(target_w * 0.90, 1), round(target_h, 1)],
            [round(target_w * 0.10, 1), round(target_h, 1)],
            [0.0, round(target_h * 0.50, 1)],
        ]
    else:
        min_x = min(p[0] for p in raw_pts)
        max_x = max(p[0] for p in raw_pts)
        min_y = min(p[1] for p in raw_pts)
        max_y = max(p[1] for p in raw_pts)
        ow = max(0.1, max_x - min_x)
        oh = max(0.1, max_y - min_y)

        # Check if orientation needs 90 degree rotation to match target box aspect ratio
        raw_is_horizontal = ow > oh
        target_is_horizontal = target_w > target_h

        if raw_is_horizontal != target_is_horizontal:
            # Rotate 90 degrees clockwise:
            # new_x = y - min_y
            # new_y = ow - (x - min_x)
            pts_work = [[p[1] - min_y, ow - (p[0] - min_x)] for p in raw_pts]
            ow, oh = oh, ow
        else:
            pts_work = [[p[0] - min_x, p[1] - min_y] for p in raw_pts]

        sx = target_w / ow
        sy = target_h / oh
        # Clamp points strictly to [0, target_w] and [0, target_h]
        pts = [
            [
                round(max(0.0, min(target_w, p[0] * sx)), 1),
                round(max(0.0, min(target_h, p[1] * sy)), 1),
            ]
            for p in pts_work
        ]

    inv_pts = [
        [
            round(max(0.0, min(target_w, target_w - p[0])), 1),
            round(max(0.0, min(target_h, target_h - p[1])), 1),
        ]
        for p in pts
    ]
    norm_path = f"M {pts[0][0]} {pts[0][1]} " + " ".join(f"L {p[0]} {p[1]}" for p in pts[1:]) + " Z"
    inv_path = f"M {inv_pts[0][0]} {inv_pts[0][1]} " + " ".join(f"L {p[0]} {p[1]}" for p in inv_pts[1:]) + " Z"
    return norm_path, inv_path


def _compute_interlocking_offsets(
    raw_pts: Optional[List[List[float]]],
    w: float,
    h: float,
    kerf_mm: float = 3.0,
) -> tuple[float, float, float]:
    """
    Computes exact contour-aware pairwise interlocking shifts for footwear patterns.
    Returns:
      dx_AB: horizontal shift from normal Piece A to inverted Piece B (nested pair)
      dx_BC: horizontal shift from Pair 1 to Pair 2 (from Piece A to next Piece A)
      dy: vertical row step (interlocking row pitch)
    """
    w = max(10.0, float(w))
    h = max(10.0, float(h))
    kerf_mm = max(1.5, float(kerf_mm or 2.5))

    default_AB = max(kerf_mm, round(w * 0.45, 1))
    default_BA = max(kerf_mm, round(w * 0.45, 1))
    default_dy = max(10.0, round(h * 0.88 + kerf_mm, 1))

    if not raw_pts or len(raw_pts) < 3:
        return default_AB, default_BA, default_dy

    try:
        import cv2
        import numpy as np

        ow = max(p[0] for p in raw_pts) - min(p[0] for p in raw_pts)
        oh = max(p[1] for p in raw_pts) - min(p[1] for p in raw_pts)
        if (ow > oh) != (w > h):
            pts_work = [[p[1], ow - p[0]] for p in raw_pts]
        else:
            pts_work = [[p[0], p[1]] for p in raw_pts]
        min_x = min(p[0] for p in pts_work)
        min_y = min(p[1] for p in pts_work)
        pts_work = [[p[0] - min_x, p[1] - min_y] for p in pts_work]
        max_pw = max(p[0] for p in pts_work) or 1.0
        max_ph = max(p[1] for p in pts_work) or 1.0
        sx = w / max_pw
        sy = h / max_ph
        pts = [[p[0] * sx, p[1] * sy] for p in pts_work]

        scale = 1.0  # 1px per mm
        img_w = int(w * 3 * scale)
        img_h = max(10, int(h * scale))

        poly_A = np.array([[int(p[0] * scale), int(p[1] * scale)] for p in pts], dtype=np.int32)
        poly_B = np.array([[int((w - p[0]) * scale), int((h - p[1]) * scale)] for p in pts], dtype=np.int32)

        kerf_px = max(1, int(kerf_mm * scale))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kerf_px * 2 + 1, kerf_px * 2 + 1))

        # 1. Calculate safe_AB: Shift from A (normal) to B (inverted)
        img_A = np.zeros((img_h + 1, img_w + 1), dtype=np.uint8)
        cv2.fillPoly(img_A, [poly_A], 255)
        img_A_dilated = cv2.dilate(img_A, kernel)

        safe_AB = w + kerf_mm
        for dx in range(max(1, int(kerf_mm)), int(w + kerf_mm) + 2):
            shifted_B = poly_B.copy()
            shifted_B[:, 0] += dx
            img_B = np.zeros((img_h + 1, img_w + 1), dtype=np.uint8)
            cv2.fillPoly(img_B, [shifted_B], 255)
            if np.sum(cv2.bitwise_and(img_A_dilated, img_B)) == 0:
                safe_AB = float(dx)
                break

        # 2. Calculate safe_BA: Shift from B (inverted) to next A (normal)
        img_B = np.zeros((img_h + 1, img_w + 1), dtype=np.uint8)
        cv2.fillPoly(img_B, [poly_B], 255)
        img_B_dilated = cv2.dilate(img_B, kernel)

        safe_BA = w + kerf_mm
        for dx in range(max(1, int(kerf_mm)), int(w + kerf_mm) + 2):
            shifted_A = poly_A.copy()
            shifted_A[:, 0] += dx
            img_A_test = np.zeros((img_h + 1, img_w + 1), dtype=np.uint8)
            cv2.fillPoly(img_A_test, [shifted_A], 255)
            if np.sum(cv2.bitwise_and(img_B_dilated, img_A_test)) == 0:
                safe_BA = float(dx)
                break

        # Safe vertical step: strictly enforce non-overlapping clearance
        safe_dy = max(10.0, round(h + kerf_mm, 1))
        return round(safe_AB, 1), round(safe_BA, 1), round(safe_dy, 1)
    except Exception:
        return default_AB, default_BA, default_dy


def _simulate_roll_nesting(
    pieces: List[Dict[str, Any]],
    roll_width_inches: float,
    selvage_margin_mm: float,
    kerf_mm: float,
    waste_pct: float,
    visual_sample_length_mm: float,
    calculated_strips: Optional[List[Dict[str, Any]]] = None,
    roll_width_mm: Optional[float] = None,
    cutting_direction: str = "length_up",
    roll_length_meters: float = 1.0,
) -> Dict[str, Any]:
    actual_roll_width_mm = roll_width_mm if roll_width_mm is not None else (roll_width_inches * INCH_TO_MM)
    usable_width_mm = max(100.0, actual_roll_width_mm - (2 * selvage_margin_mm))

    total_net_pair_area_sqcm = 0.0
    piece_results: List[Dict[str, Any]] = []
    total_consumption_meters = 0.0

    piece_specs: List[Dict[str, Any]] = []

    for p_idx, p in enumerate(pieces):
        p_name = p.get("piece_name") or f"Piece {p_idx + 1}"
        p_id = p.get("piece_id") or f"p_{p_idx + 1}"
        p_len = max(10.0, float(p.get("length_mm") or p.get("raw_bbox_h_mm") or 100.0))
        p_wid = max(10.0, float(p.get("width_mm") or p.get("raw_bbox_w_mm") or 50.0))
        p_area = float(p.get("area_sqcm") or (p_len * p_wid / 100.0 * 0.75))
        qty_per_pair = max(1, int(p.get("pieces_per_pair") or 2))
        color = p.get("color") or PIECE_COLORS[p_idx % len(PIECE_COLORS)]

        total_net_pair_area_sqcm += p_area * qty_per_pair

        # Footwear Cutting Direction & Stretch Control:
        # Synthetic roll does NOT stretch in Length (Warp/Machine direction), but STRETCHES in Width (Weft).
        # By default ("length_up"), piece length is placed along roll length so shoe doesn't stretch when worn.
        piece_cut_dir = p.get("cutting_direction")
        if not piece_cut_dir or piece_cut_dir == "inherit":
            piece_cut_dir = cutting_direction

        # Orientation 1: Piece Length aligned with Roll Length (Y-axis / Warp / Length-Up)
        # Width is across the roll (X-axis) -> NO LENGTH STRETCH WHEN PRODUCT IS WORN
        cols_1 = max(1, int((usable_width_mm + kerf_mm) // (p_wid + kerf_mm)))
        row_height_1 = p_len
        # Curved footwear pieces interlock when placed in alternating pairs:
        interlock_factor_1 = 0.85 if (p_len / p_wid) < 3.0 else 0.92
        pitch_1 = (row_height_1 * interlock_factor_1) + kerf_mm
        pieces_per_meter_1 = (cols_1 * (1000.0 / pitch_1))

        # Orientation 2: Piece Length aligned with Roll Width (X-axis / Weft / Crosswise)
        # Width is along roll length (Y-axis)
        cols_2 = max(1, int((usable_width_mm + kerf_mm) // (p_len + kerf_mm)))
        row_height_2 = p_wid
        interlock_factor_2 = 0.88
        pitch_2 = (row_height_2 * interlock_factor_2) + kerf_mm
        pieces_per_meter_2 = (cols_2 * (1000.0 / pitch_2))

        # Contour-Aware Interlocking Enhancement: Count actual interlocking twin pairs
        raw_pts_p = p.get("local_points_mm") or []
        if raw_pts_p and len(raw_pts_p) >= 3:
            dx_ab1, dx_ba1, dy1 = _compute_interlocking_offsets(raw_pts_p, p_wid, p_len, kerf_mm)
            fitted_1 = 0
            cur_test_x = 0.0
            while True:
                if fitted_1 == 0:
                    test_x = 0.0
                elif fitted_1 % 2 == 1:
                    test_x = cur_test_x + dx_ab1
                else:
                    test_x = cur_test_x + dx_ba1
                if test_x + p_wid > usable_width_mm:
                    break
                cur_test_x = test_x
                fitted_1 += 1
            if fitted_1 > cols_1:
                cols_1 = fitted_1
                pitch_1 = dy1
                pieces_per_meter_1 = cols_1 * (1000.0 / pitch_1)

            dx_ab2, dx_ba2, dy2 = _compute_interlocking_offsets(raw_pts_p, p_len, p_wid, kerf_mm)
            fitted_2 = 0
            cur_test_x = 0.0
            while True:
                if fitted_2 == 0:
                    test_x = 0.0
                elif fitted_2 % 2 == 1:
                    test_x = cur_test_x + dx_ab2
                else:
                    test_x = cur_test_x + dx_ba2
                if test_x + p_len > usable_width_mm:
                    break
                cur_test_x = test_x
                fitted_2 += 1
            if fitted_2 > cols_2:
                cols_2 = fitted_2
                pitch_2 = dy2
                pieces_per_meter_2 = cols_2 * (1000.0 / pitch_2)

        if piece_cut_dir == "length_up":
            # Strictly length side up (default factory footwear standard)
            best_cols = cols_1
            best_w = p_wid
            best_l = p_len
            best_pitch = pitch_1
            best_ppm = pieces_per_meter_1
            is_rotated = False
            chosen_dir_label = "Length-Up (No Length Stretch)"
        elif piece_cut_dir == "width_up":
            # Strictly crosswise / width side up
            best_cols = cols_2
            best_w = p_len
            best_l = p_wid
            best_pitch = pitch_2
            best_ppm = pieces_per_meter_2
            is_rotated = True
            chosen_dir_label = "Crosswise / Width (Stretch along piece)"
        else:
            # "both" / "best_yield": pick whichever gives higher pieces per meter
            if pieces_per_meter_1 >= pieces_per_meter_2:
                best_cols = cols_1
                best_w = p_wid
                best_l = p_len
                best_pitch = pitch_1
                best_ppm = pieces_per_meter_1
                is_rotated = False
                chosen_dir_label = "Length-Up (Optimal)"
            else:
                best_cols = cols_2
                best_w = p_len
                best_l = p_wid
                best_pitch = pitch_2
                best_ppm = pieces_per_meter_2
                is_rotated = True
                chosen_dir_label = "Crosswise (Optimal)"

        pairs_per_meter = best_ppm / qty_per_pair
        meters_per_pair = (1.0 / pairs_per_meter) if pairs_per_meter > 0 else 0.0

        total_consumption_meters += meters_per_pair

        piece_results.append({
            "piece_id": p_id,
            "piece_name": p_name,
            "component": p.get("component", "upper"),
            "component_type": p.get("component_type", "vamp"),
            "color": color,
            "area_sqcm": p_area,
            "area_sqin": round(p_area / 6.4516, 2),
            "area_sqft": round(p_area / 929.0304, 3),
            "length_mm": p_len,
            "length_inches": round(p_len / INCH_TO_MM, 2),
            "length_cm": round(p_len / 10.0, 2),
            "width_mm": p_wid,
            "width_inches": round(p_wid / INCH_TO_MM, 2),
            "width_cm": round(p_wid / 10.0, 2),
            "pieces_per_pair": qty_per_pair,
            "columns_across_roll": best_cols,
            "is_rotated": is_rotated,
            "cutting_direction": piece_cut_dir,
            "cutting_direction_label": chosen_dir_label,
            "pitch_mm": round(best_pitch, 1),
            "pieces_per_meter": round(best_ppm, 2),
            "pairs_per_meter": round(pairs_per_meter, 2),
            "meters_per_pair": round(meters_per_pair, 4),
        })

        # Extract points for normalization
        pts = p.get("local_points_mm") or []
        norm_path, inv_path = _normalize_polygon_to_box(pts, best_w, best_l)

        piece_specs.append({
            "piece_id": p_id,
            "piece_name": p_name,
            "material_id": p.get("material_id"),
            "material_name": p.get("material_name"),
            "color": color,
            "w": best_w,
            "h": best_l,
            "qty_per_pair": qty_per_pair,
            "norm_path": norm_path,
            "inv_path": inv_path,
            "raw_pts": pts,
        })

    # ═════════════════════════════════════════════════════════════════════════
    # MULTI-COMPONENT BEST-FIT DECREASING SHELF (BFDS) 2D NESTING LAYOUT
    # Edge-to-edge roll packing (selvage to selvage) with GUARANTEED ZERO OVERLAP
    # & Full Roll Length Utilization (Top Margin down to Bottom Margin)
    # ═════════════════════════════════════════════════════════════════════════
    layout_placed_items: List[Dict[str, Any]] = []
    current_visual_y = selvage_margin_mm
    shelf_utilizations: List[float] = []

    target_canvas_length_mm = max(
        600.0,
        min(
            3000.0,
            (roll_length_meters * 1000.0) if (roll_length_meters and roll_length_meters > 0) else visual_sample_length_mm,
        ),
    )
    max_usable_y = target_canvas_length_mm - selvage_margin_mm

    if piece_specs:
        sorted_specs = sorted(piece_specs, key=lambda s: s["h"], reverse=True)
        effective_gap = max(1.5, float(kerf_mm or 2.5))

        # ── ISOLATED SINGLE-COMPONENT PAIRWISE INTERLOCKING NESTING ──
        # Eliminates empty space between pieces and right-side selvage waste
        if len(sorted_specs) == 1:
            leader = sorted_specs[0]
            dx_AB, dx_BA, dy = _compute_interlocking_offsets(leader.get("raw_pts"), leader["w"], leader["h"], effective_gap)

            shelf_idx = 0
            while current_visual_y + leader["h"] <= max_usable_y:
                is_odd_row = (shelf_idx % 2 == 1)
                shelf_items = []
                piece_idx_in_row = 0

                while True:
                    # Smart Alternating Row Inversion (Checkerboard Pattern):
                    # Even rows: Normal -> Inverted -> Normal -> Inverted...
                    # Odd rows (line below): Inverted -> Normal -> Inverted -> Normal...
                    is_inv = (piece_idx_in_row % 2 == 1) if not is_odd_row else (piece_idx_in_row % 2 == 0)

                    if piece_idx_in_row == 0:
                        cur_x = selvage_margin_mm
                    elif not is_odd_row:
                        # Even row: Normal -> Inverted (dx_AB), then Inverted -> Normal (dx_BA)
                        cur_x = shelf_items[-1]["x_mm"] + (dx_AB if piece_idx_in_row % 2 == 1 else dx_BA)
                    else:
                        # Odd row: Inverted -> Normal (dx_BA), then Normal -> Inverted (dx_AB)
                        cur_x = shelf_items[-1]["x_mm"] + (dx_BA if piece_idx_in_row % 2 == 1 else dx_AB)

                    if cur_x + leader["w"] > selvage_margin_mm + usable_width_mm:
                        break

                    shelf_items.append({
                        "piece_id": leader["piece_id"],
                        "piece_name": leader["piece_name"],
                        "material_id": leader.get("material_id"),
                        "material_name": leader.get("material_name"),
                        "color": leader["color"],
                        "x_mm": round(cur_x, 1),
                        "y_mm": round(current_visual_y, 1),
                        "w_mm": round(leader["w"], 1),
                        "h_mm": round(leader["h"], 1),
                        "rotation": 0,
                        "is_inverted": is_inv,
                        "svg_path": leader["inv_path"] if is_inv else leader["norm_path"],
                        "svg_polygon": leader["inv_path"] if is_inv else leader["norm_path"],
                    })
                    piece_idx_in_row += 1

                if not shelf_items:
                    break

                layout_placed_items.extend(shelf_items)
                last_piece_end = shelf_items[-1]["x_mm"] + leader["w"] - selvage_margin_mm
                shelf_util = min(100.0, round((last_piece_end / usable_width_mm) * 100.0, 1))
                shelf_utilizations.append(shelf_util)

                current_visual_y += max(leader["h"] + effective_gap, dy)
                shelf_idx += 1
        else:
            # ── MULTI-COMPONENT BEST-FIT DECREASING SHELF (BFDS) FALLBACK ──
            min_piece_h = min(s["h"] for s in sorted_specs)
            spec_cycle_idx = 0
            pair_cycle = 0

            while current_visual_y + min_piece_h <= max_usable_y:
                candidates = [s for s in sorted_specs if current_visual_y + s["h"] <= max_usable_y]
                if not candidates:
                    break

                leader = candidates[spec_cycle_idx % len(candidates)]
                spec_cycle_idx += 1
                shelf_h = leader["h"]
                shelf_items = []
                cur_shelf_w = 0.0

                while cur_shelf_w + leader["w"] + (kerf_mm if shelf_items else 0.0) <= usable_width_mm:
                    shelf_items.append(dict(leader))
                    cur_shelf_w += leader["w"] + (kerf_mm if len(shelf_items) > 1 else 0.0)

                while True:
                    rem_w = usable_width_mm - cur_shelf_w - kerf_mm
                    if rem_w < 5.0:
                        break
                    fit_smaller = [s for s in sorted_specs if s["piece_id"] != leader["piece_id"] and s["w"] <= rem_w and s["h"] <= shelf_h]
                    if not fit_smaller:
                        break
                    chosen = max(fit_smaller, key=lambda s: s["w"])
                    shelf_items.append(dict(chosen))
                    cur_shelf_w += kerf_mm + chosen["w"]

                if not shelf_items:
                    break

                cur_x = selvage_margin_mm
                for it_i, it in enumerate(shelf_items):
                    is_inv = (pair_cycle + it_i) % 2 == 1
                    layout_placed_items.append({
                        "piece_id": it["piece_id"],
                        "piece_name": it["piece_name"],
                        "material_id": it.get("material_id"),
                        "material_name": it.get("material_name"),
                        "color": it["color"],
                        "x_mm": round(cur_x, 1),
                        "y_mm": round(current_visual_y, 1),
                        "w_mm": round(it["w"], 1),
                        "h_mm": round(it["h"], 1),
                        "rotation": 0,
                        "is_inverted": is_inv,
                        "svg_path": it["inv_path"] if is_inv else it["norm_path"],
                        "svg_polygon": it["inv_path"] if is_inv else it["norm_path"],
                    })
                    cur_x += it["w"] + effective_gap

                total_items_w = sum(it["w"] for it in shelf_items)
                shelf_util = min(100.0, round((total_items_w / usable_width_mm) * 100.0, 1))
                shelf_utilizations.append(shelf_util)

                current_visual_y += shelf_h + effective_gap
                pair_cycle += 1

    # Render Visual Preview for Standard Strips / Laces if present
    if calculated_strips and (max_usable_y - current_visual_y) >= 20.0:
        for st_idx, st in enumerate(calculated_strips):
            is_unf = str(st.get("strip_type") or "folded").lower() == "unfolded"
            st_color = "#06b6d4" if is_unf else "#f97316"
            st_cut_w = float(st.get("cut_width_mm") or 16.0)
            cut_orient = str(st.get("cut_orientation") or "along_length").lower()

            if cut_orient == "across_width":
                # Crosswise horizontal strip across usable roll width
                st_w = max(50.0, actual_roll_width_mm - (2 * selvage_margin_mm))
                while current_visual_y + st_cut_w <= max_usable_y:
                    layout_placed_items.append({
                        "piece_id": st.get("strip_id") or f"st_cr_{len(layout_placed_items)}",
                        "piece_name": f"{st.get('name', 'Strip')} ({round(st_w, 1)}×{round(st_cut_w, 1)}mm)",
                        "color": st_color,
                        "x_mm": round(selvage_margin_mm, 1),
                        "y_mm": round(current_visual_y, 1),
                        "w_mm": round(st_w, 1),
                        "h_mm": round(st_cut_w, 1),
                        "rotation": 0,
                        "is_strip": True,
                    })
                    current_visual_y += st_cut_w + 2.0
            else:
                # Vertical continuous slitting lanes
                st_lanes = min(25, st.get("lanes_across_roll", 10))
                st_h = min(80.0, max_usable_y - current_visual_y - kerf_mm)
                if st_h <= 10.0:
                    break
                for lane_i in range(st_lanes):
                    lane_x = selvage_margin_mm + lane_i * (st_cut_w + 1.0)
                    if lane_x + st_cut_w > actual_roll_width_mm - selvage_margin_mm:
                        break
                    layout_placed_items.append({
                        "piece_id": st.get("strip_id") or f"st_{lane_i}",
                        "piece_name": f"{st.get('name', 'Lace')} ({round(st_cut_w, 1)}mm)",
                        "color": st_color,
                        "x_mm": round(lane_x, 1),
                        "y_mm": round(current_visual_y, 1),
                        "w_mm": round(st_cut_w, 1),
                        "h_mm": round(st_h, 1),
                        "rotation": 0,
                        "is_strip": True,
                    })
                current_visual_y += st_h + kerf_mm

    # Apply waste allowance buffer
    waste_multiplier = 1.0 + (waste_pct / 100.0)
    final_consumption_per_pair = round(total_consumption_meters * waste_multiplier, 4)
    final_yield_per_meter = round(1.0 / final_consumption_per_pair, 2) if final_consumption_per_pair > 0 else 0.0

    gross_area_sqcm_per_pair = round((actual_roll_width_mm / 10.0) * (final_consumption_per_pair * 100.0), 2)

    if gross_area_sqcm_per_pair > 0:
        utilization_pct = min(98.0, round((total_net_pair_area_sqcm / gross_area_sqcm_per_pair) * 100.0, 1))
    else:
        utilization_pct = 75.0
    actual_waste_pct = round(100.0 - utilization_pct, 1)

    width_utilization_pct = (
        round(sum(shelf_utilizations) / len(shelf_utilizations), 1)
        if shelf_utilizations
        else 85.0
    )

    return {
        "ok": True,
        "material_type": "roll",
        "material_spec": {
            "roll_width_inches": roll_width_inches,
            "roll_width_mm": round(actual_roll_width_mm, 1),
            "usable_width_mm": round(usable_width_mm, 1),
            "selvage_margin_mm": selvage_margin_mm,
            "kerf_spacing_mm": kerf_mm,
            "waste_allowance_pct": waste_pct,
            "cutting_direction": cutting_direction,
            "roll_length_meters": roll_length_meters,
        },
        "consumption_per_pair": final_consumption_per_pair,
        "consumption_unit": "meter",
        "yield_per_unit": final_yield_per_meter,
        "yield_unit_label": "pairs / meter",
        "total_pairs_per_roll": round(roll_length_meters / final_consumption_per_pair) if final_consumption_per_pair > 0 else 0,
        "utilization_pct": utilization_pct,
        "waste_pct": actual_waste_pct,
        "net_area_sqcm_per_pair": round(total_net_pair_area_sqcm, 2),
        "gross_area_sqcm_per_pair": gross_area_sqcm_per_pair,
        "pieces_analysis": piece_results,
        "visual_nesting_preview": {
            "canvas_width_mm": round(actual_roll_width_mm, 1),
            "canvas_height_mm": round(target_canvas_length_mm, 1),
            "selvage_left_x": 0.0,
            "selvage_left_w": selvage_margin_mm,
            "selvage_right_x": round(actual_roll_width_mm - selvage_margin_mm, 1),
            "selvage_right_w": selvage_margin_mm,
            "placed_items": layout_placed_items,
            "width_utilization_pct": width_utilization_pct,
        },
    }


def _simulate_sheet_nesting(
    pieces: List[Dict[str, Any]],
    sheet_length_mm: float,
    sheet_width_mm: float,
    margin_mm: float,
    kerf_mm: float,
    waste_pct: float,
) -> Dict[str, Any]:
    usable_l = max(100.0, sheet_length_mm - (2 * margin_mm))
    usable_w = max(100.0, sheet_width_mm - (2 * margin_mm))
    sheet_area_sqcm = round((sheet_length_mm / 10.0) * (sheet_width_mm / 10.0), 2)

    total_net_pair_area_sqcm = 0.0
    piece_results: List[Dict[str, Any]] = []
    total_sheets_per_pair = 0.0
    layout_placed_items: List[Dict[str, Any]] = []

    current_sheet_y = margin_mm

    for p_idx, p in enumerate(pieces):
        p_name = p.get("piece_name") or f"Piece {p_idx + 1}"
        p_id = p.get("piece_id") or f"p_{p_idx + 1}"
        p_len = max(10.0, float(p.get("length_mm") or 100.0))
        p_wid = max(10.0, float(p.get("width_mm") or 50.0))
        p_area = float(p.get("area_sqcm") or (p_len * p_wid / 100.0 * 0.75))
        qty_per_pair = max(1, int(p.get("pieces_per_pair") or 2))
        color = p.get("color") or PIECE_COLORS[p_idx % len(PIECE_COLORS)]

        total_net_pair_area_sqcm += p_area * qty_per_pair

        cols_1 = max(1, int((usable_w + kerf_mm) // (p_wid + kerf_mm)))
        rows_1 = max(1, int((usable_l + kerf_mm) // (p_len + kerf_mm)))
        pieces_1 = cols_1 * rows_1

        cols_2 = max(1, int((usable_w + kerf_mm) // (p_len + kerf_mm)))
        rows_2 = max(1, int((usable_l + kerf_mm) // (p_wid + kerf_mm)))
        pieces_2 = cols_2 * rows_2

        best_pieces = max(pieces_1, pieces_2)
        best_cols = cols_1 if pieces_1 >= pieces_2 else cols_2
        best_rows = rows_1 if pieces_1 >= pieces_2 else rows_2
        best_w = p_wid if pieces_1 >= pieces_2 else p_len
        best_l = p_len if pieces_1 >= pieces_2 else p_wid

        pairs_per_sheet = best_pieces / qty_per_pair
        sheets_per_pair = (1.0 / pairs_per_sheet) if pairs_per_sheet > 0 else 0.0
        total_sheets_per_pair += sheets_per_pair

        piece_results.append({
            "piece_id": p_id,
            "piece_name": p_name,
            "component": p.get("component", "upper"),
            "color": color,
            "area_sqcm": p_area,
            "pieces_per_pair": qty_per_pair,
            "pieces_per_sheet": best_pieces,
            "pairs_per_sheet": round(pairs_per_sheet, 2),
            "sheets_per_pair": round(sheets_per_pair, 4),
        })

        pts = p.get("local_points_mm") or []
        norm_path, inv_path = _normalize_polygon_to_box(pts, best_w, best_l)

        rendered_count = 0
        rows_to_render = min(best_rows, 6)
        for r in range(rows_to_render):
            row_y = current_sheet_y + r * (best_l + kerf_mm)
            if row_y + best_l > sheet_length_mm - margin_mm or rendered_count >= 40:
                break
            for c in range(best_cols):
                if rendered_count >= 40:
                    break
                col_x = margin_mm + c * (best_w + kerf_mm)
                is_inverted = (r + c) % 2 == 1
                layout_placed_items.append({
                    "piece_id": p_id,
                    "piece_name": p_name,
                    "color": color,
                    "x_mm": round(col_x, 1),
                    "y_mm": round(row_y, 1),
                    "w_mm": round(best_w, 1),
                    "h_mm": round(best_l, 1),
                    "rotation": 0,
                    "is_inverted": is_inverted,
                    "svg_path": inv_path if is_inverted else norm_path,
                    "svg_polygon": inv_path if is_inverted else norm_path,
                })
                rendered_count += 1

        current_sheet_y += rows_to_render * (best_l + kerf_mm)

    waste_multiplier = 1.0 + (waste_pct / 100.0)
    final_consumption_per_pair = round(total_sheets_per_pair * waste_multiplier, 4)
    final_yield_per_sheet = round(1.0 / final_consumption_per_pair, 2) if final_consumption_per_pair > 0 else 0.0
    gross_area_sqcm_per_pair = round(sheet_area_sqcm * final_consumption_per_pair, 2)

    if gross_area_sqcm_per_pair > 0:
        utilization_pct = min(98.0, round((total_net_pair_area_sqcm / gross_area_sqcm_per_pair) * 100.0, 1))
    else:
        utilization_pct = 75.0
    actual_waste_pct = round(100.0 - utilization_pct, 1)

    return {
        "ok": True,
        "material_type": "sheet",
        "material_spec": {
            "sheet_length_mm": sheet_length_mm,
            "sheet_width_mm": sheet_width_mm,
            "usable_length_mm": round(usable_l, 1),
            "usable_width_mm": round(usable_w, 1),
            "margin_mm": margin_mm,
            "kerf_spacing_mm": kerf_mm,
            "waste_allowance_pct": waste_pct,
        },
        "consumption_per_pair": final_consumption_per_pair,
        "consumption_unit": "sheet",
        "yield_per_unit": final_yield_per_sheet,
        "yield_unit_label": "pairs / sheet",
        "utilization_pct": utilization_pct,
        "waste_pct": actual_waste_pct,
        "net_area_sqcm_per_pair": round(total_net_pair_area_sqcm, 2),
        "gross_area_sqcm_per_pair": gross_area_sqcm_per_pair,
        "pieces_analysis": piece_results,
        "visual_nesting_preview": {
            "canvas_width_mm": sheet_width_mm,
            "canvas_height_mm": sheet_length_mm,
            "placed_items": layout_placed_items,
        },
    }


def _empty_yield_result(material_type: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "material_type": material_type,
        "consumption_per_pair": 0.0,
        "consumption_unit": "meter" if material_type == "roll" else "sheet",
        "yield_per_unit": 0.0,
        "yield_unit_label": "pairs / meter" if material_type == "roll" else "pairs / sheet",
        "utilization_pct": 0.0,
        "waste_pct": 0.0,
        "net_area_sqcm_per_pair": 0.0,
        "gross_area_sqcm_per_pair": 0.0,
        "pieces_analysis": [],
        "standard_strips": [],
        "standard_presets": STANDARD_FACTORY_PRESETS,
        "component_breakdown": {},
        "visual_nesting_preview": None,
    }
