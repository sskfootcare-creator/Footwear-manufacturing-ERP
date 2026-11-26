import { useState, useEffect, useRef, useMemo } from "react";
import { http, formatApiError, friendlyAxiosError } from "../lib/api";
import { SafeImage } from "./ImageUploader";
import {
  X, Upload, Scan, Grid, CheckCircle2, AlertCircle, ArrowRight,
  RefreshCw, Ruler, Layers, Scissors, SlidersHorizontal, ZoomIn,
  ZoomOut, Maximize2, ShieldAlert, Cpu, Sparkles, FileText,
  Bookmark, FolderOpen, Plus, Trash2, Sun, Moon, Info, HelpCircle,
  ArrowUpDown, ArrowLeftRight, RotateCw, Gauge, Calculator, Save, Camera
} from "lucide-react";

const getSafePhotoUrl = (url) => {
  if (!url) return "";
  if (typeof url !== "string") return "";
  if (url.includes("ik.imagekit.io") && !url.includes("?tr=") && !url.includes("tr:")) {
    return `${url}?tr=w-800,q-85`;
  }
  return url;
};

const getErrorMessage = (err, fallback = "An error occurred") => {
  if (err?.response?.data?.detail) {
    return formatApiError(err.response.data.detail);
  }
  return friendlyAxiosError(err) || fallback;
};

const INCH_TO_MM = 25.4;
const SQINCH_TO_SQCM = 6.4516;
const SQFT_TO_SQCM = 929.0304;

// Distinct color palette for visual nesting pieces
const PIECE_COLORS = [
  "#3b82f6",  // blue
  "#10b981",  // emerald
  "#f59e0b",  // amber
  "#8b5cf6",  // purple
  "#ec4899",  // pink
  "#06b6d4",  // cyan
  "#f97316",  // orange
  "#6366f1",  // indigo
];

// Standard Folded Lace Presets for Footwear
const LACE_PRESETS = [
  { label: "4 mm (Folded)", folded_mm: 4.0, folded_inch: 0.157 },
  { label: "6 mm (Folded)", folded_mm: 6.0, folded_inch: 0.236 },
  { label: "8 mm (Folded)", folded_mm: 8.0, folded_inch: 0.315 },
  { label: "10 mm (Folded)", folded_mm: 10.0, folded_inch: 0.394 },
  { label: "12 mm (Folded)", folded_mm: 12.0, folded_inch: 0.472 },
  { label: "0.5 inch (12.7 mm Folded)", folded_mm: 12.7, folded_inch: 0.5 },
  { label: "0.75 inch (19.05 mm Folded)", folded_mm: 19.05, folded_inch: 0.75 },
  { label: "1.0 inch (25.4 mm Folded)", folded_mm: 25.4, folded_inch: 1.0 },
  { label: "Custom Size...", folded_mm: 0, folded_inch: 0 },
];

// Roll Width Presets
const ROLL_WIDTH_PRESETS = [
  { label: "54″ (137.2 cm) — Standard Footwear Rexine", inches: 54.0, mm: 1371.6 },
  { label: "58″ (147.3 cm) — Wide Roll Synthetic", inches: 58.0, mm: 1473.2 },
  { label: "60″ (152.4 cm) — Extra Wide Roll", inches: 60.0, mm: 1524.0 },
  { label: "48″ (121.9 cm) — Medium Roll", inches: 48.0, mm: 1219.2 },
  { label: "44″ (111.8 cm) — Narrow Roll", inches: 44.0, mm: 1117.6 },
  { label: "36″ (91.4 cm) — Compact Roll", inches: 36.0, mm: 914.4 },
  { label: "Custom Width...", inches: 0, mm: 0 },
];

// Roll Length Presets
const ROLL_LENGTH_PRESETS = [
  { label: "1 Meter (Unit Yield / Pair Calculation)", meters: 1.0 },
  { label: "25 Meters (Small Roll)", meters: 25.0 },
  { label: "50 Meters (Standard Factory Roll)", meters: 50.0 },
  { label: "100 Meters (Bulk Master Roll)", meters: 100.0 },
  { label: "Custom Roll Length...", meters: 0 },
];

// Footwear Component Types
const COMPONENT_TYPES = [
  { value: "vamp", label: "Main Vamp" },
  { value: "quarter", label: "Quarter (Lateral/Medial)" },
  { value: "strap", label: "Strap / Cross Band" },
  { value: "counter", label: "Back Counter" },
  { value: "tongue", label: "Shoe Tongue" },
  { value: "collar", label: "Collar / Cuff" },
  { value: "toe_cap", label: "Toe Cap" },
  { value: "backstay", label: "Backstay" },
  { value: "lining_piece", label: "Lining Piece" },
  { value: "canvas_reinforcement", label: "Canvas Reinforcement" },
  { value: "folded_lace", label: "Folded Lace / Binding" },
  { value: "custom", label: "Custom Shape" },
];

// Standard Factory Component Presets (Locked)
const FACTORY_PRESETS_DEFAULT = [
  {
    component: "standard_insole",
    name: "Cellulose Insole Board",
    material_type: "sheet",
    sheet_spec: "40'' x 60'' (1016 x 1524 mm)",
    standard_yield: 26.0,
    yield_unit: "pairs / sheet",
    standard_consumption: 0.0385,
    consumption_unit: "sheet",
    note: "Factory Die-Cut Standard (26 prs/sheet) — locked",
    active: true,
  },
  {
    component: "standard_bottom_covering",
    name: "Socks / Bottom Covering Material",
    material_type: "roll",
    sheet_spec: "54'' Continuous Roll",
    standard_yield: 8.0,
    yield_unit: "pairs / meter",
    standard_consumption: 0.125,
    consumption_unit: "meter",
    note: "Factory Standard (8 prs/meter) — locked",
    active: true,
  },
  {
    component: "standard_eva_cushion",
    name: "EVA Insole Cushioning Foam",
    material_type: "sheet",
    sheet_spec: "40'' x 60'' (1016 x 1524 mm)",
    standard_yield: 25.0,
    yield_unit: "pairs / sheet",
    standard_consumption: 0.04,
    consumption_unit: "sheet",
    note: "Factory Die-Cut Standard (25 prs/sheet) — locked",
    active: false,
  },
];

export default function PatternYieldModal({
  sample,
  materials = [],
  onClose,
  onSaved,
  onOpenTransfer,
}) {
  const sid = sample?.id || sample?._id;
  const [activeTab, setActiveTab] = useState("scan"); // "scan" | "nesting" | "bom"

  // ═════════════════════════════════════════════════════════════════════════
  // REQUIREMENT 4: MEASUREMENT SYSTEM UNITS (MM, CM, INCH, CM², SQ IN, SQ FT)
  // ═════════════════════════════════════════════════════════════════════════
  const [measurementUnit, setMeasurementUnit] = useState("mm"); // "mm" | "cm" | "inch"
  const [areaUnit, setAreaUnit] = useState("cm²"); // "cm²" | "sq in" | "sq ft"

  // Unit conversion helpers
  const toDisplayLength = (mm) => {
    if (mm == null || isNaN(mm)) return "-";
    const val = parseFloat(mm);
    if (measurementUnit === "inch") return (val / INCH_TO_MM).toFixed(2);
    if (measurementUnit === "cm") return (val / 10.0).toFixed(1);
    return val.toFixed(1);
  };

  const toDisplayArea = (sqcm) => {
    if (sqcm == null || isNaN(sqcm)) return "-";
    const val = parseFloat(sqcm);
    if (areaUnit === "sq in") return (val / SQINCH_TO_SQCM).toFixed(2);
    if (areaUnit === "sq ft") return (val / SQFT_TO_SQCM).toFixed(3);
    return val.toFixed(1);
  };

  const parseInputToMm = (inputVal) => {
    const v = parseFloat(inputVal) || 0;
    if (measurementUnit === "inch") return v * INCH_TO_MM;
    if (measurementUnit === "cm") return v * 10.0;
    return v;
  };

  // ═════════════════════════════════════════════════════════════════════════
  // REQUIREMENT 1: EXPECTED PIECES DEFINITION & CONTINUOUS ROLL SIZING CONTROL
  // ═════════════════════════════════════════════════════════════════════════
  const [expectedPiecesCount, setExpectedPiecesCount] = useState(
    sample?.yield_spec?.expected_pieces_count || 4
  );
  const [patternPieces, setPatternPieces] = useState(sample?.pattern_pieces || []);
  const [scanUrl, setScanUrl] = useState(sample?.pattern_scan_url || "");
  const [calibration, setCalibration] = useState(null);
  const [yieldSpec, setYieldSpec] = useState(sample?.yield_spec || null);

  // Manual component addition state
  const [showAddPieceModal, setShowAddPieceModal] = useState(false);
  const [newPieceName, setNewPieceName] = useState("Quarter Lateral");
  const [newPieceType, setNewPieceType] = useState("quarter");
  const [newPieceLength, setNewPieceLength] = useState("140");
  const [newPieceWidth, setNewPieceWidth] = useState("75");
  const [newPiecePcsPerPair, setNewPiecePcsPerPair] = useState(2);
  const [newPieceCutDir, setNewPieceCutDir] = useState("inherit");

  // Roll Width Controls (Presets + Custom Size)
  const [rollWidthPreset, setRollWidthPreset] = useState("54.0");
  const [customRollWidthMm, setCustomRollWidthMm] = useState(1371.6);
  const [customRollWidthUnit, setCustomRollWidthUnit] = useState("inches");

  // Roll Length Controls (Presets + Custom Size)
  const [rollLengthPreset, setRollLengthPreset] = useState("1.0");
  const [customRollLengthMeters, setCustomRollLengthMeters] = useState(50.0);

  // ═════════════════════════════════════════════════════════════════════════
  // REQUIREMENT 2: DIRECTION OF CUTTING (STRETCH PHYSICS CONTROL)
  // Synthetic material: Length-up does not stretch (Warp/Machine direction).
  // Width stretches. Default to "length_up" so shoes don't stretch when worn!
  // ═════════════════════════════════════════════════════════════════════════
  const [cuttingDirection, setCuttingDirection] = useState(
    sample?.yield_spec?.cutting_direction || "length_up"
  ); // "length_up" (default/no stretch) | "width_up" | "both" (best yield)

  // ═════════════════════════════════════════════════════════════════════════
  // REQUIREMENT 3: LACES YIELD CALCULATOR (LACES PER 1 METER + LENGTH DEFINED)
  // + Material definition & link from Material Master
  // ═════════════════════════════════════════════════════════════════════════
  const [standardStrips, setStandardStrips] = useState(
    sample?.standard_strips || sample?.yield_spec?.standard_strips || []
  );
  // Unfolded Strips vs Folded Laces + Cutting Orientation
  const [stripType, setStripType] = useState("folded"); // "folded" | "unfolded"
  const [unfoldedStripWidthMm, setUnfoldedStripWidthMm] = useState(15.0); // user defined measurement of width
  const [stripCutOrientation, setStripCutOrientation] = useState("along_length"); // "along_length" | "across_width"
  const [newStripName, setNewStripName] = useState("Main Folded Lace");
  const [selectedLacePreset, setSelectedLacePreset] = useState("8.0");
  const [newStripFoldedWidthMm, setNewStripFoldedWidthMm] = useState(8.0);
  const [newStripLengthMm, setNewStripLengthMm] = useState(650.0);
  const [newStripLengthUnit, setNewStripLengthUnit] = useState("mm");
  const [newStripPcsPerPair, setNewStripPcsPerPair] = useState(2);

  // Lace Source Material from Material Master & Material Dimensions
  const [laceMaterialId, setLaceMaterialId] = useState("");
  const [laceMaterialName, setLaceMaterialName] = useState("");
  const [laceMaterialCode, setLaceMaterialCode] = useState("");
  const [laceMaterialRate, setLaceMaterialRate] = useState(0.0);
  const [laceMaterialWidth, setLaceMaterialWidth] = useState(50.0); // default 50 inch width
  const [laceMaterialWidthUnit, setLaceMaterialWidthUnit] = useState("inch");
  const [laceMaterialLength, setLaceMaterialLength] = useState(1.0); // default 1 meter
  const [laceMaterialLengthUnit, setLaceMaterialLengthUnit] = useState("meter");

  // Helper to convert selected material width into active length unit
  const getSelectedMaterialWidthInLengthUnits = (targetUnit = newStripLengthUnit) => {
    let matWMm = parseFloat(laceMaterialWidth) || 50.0;
    if (laceMaterialWidthUnit === "inch") matWMm *= INCH_TO_MM;
    else if (laceMaterialWidthUnit === "cm") matWMm *= 10.0;

    if (targetUnit === "inch") return Math.round((matWMm / INCH_TO_MM) * 100) / 100;
    if (targetUnit === "cm") return Math.round((matWMm / 10.0) * 10) / 10;
    return Math.round(matWMm);
  };

  const handleOrientationChange = (orient) => {
    setStripCutOrientation(orient);
    if (orient === "across_width") {
      setNewStripLengthMm(getSelectedMaterialWidthInLengthUnits());
    } else {
      if (newStripLengthUnit === "mm") setNewStripLengthMm(650.0);
      else if (newStripLengthUnit === "cm") setNewStripLengthMm(65.0);
      else if (newStripLengthUnit === "inch") setNewStripLengthMm(25.6);
    }
  };

  // Materials master list loaded from props or fetched from /materials
  const [materialsList, setMaterialsList] = useState(materials || []);
  useEffect(() => {
    if (!materialsList || materialsList.length === 0) {
      http.get("/materials")
        .then((res) => {
          if (Array.isArray(res.data) && res.data.length > 0) {
            setMaterialsList(res.data);
          }
        })
        .catch((e) => console.error("Failed to load materials in PatternYieldModal:", e));
    }
  }, [materialsList]);

  const handleSelectLaceMaterial = (matId) => {
    setLaceMaterialId(matId);
    if (!matId) {
      setLaceMaterialName("");
      setLaceMaterialCode("");
      setLaceMaterialRate(0.0);
      return;
    }
    const found = materialsList.find((m) => (m.id || m._id) === matId);
    if (found) {
      setLaceMaterialName(found.name || "");
      setLaceMaterialCode(found.code || "");
      setLaceMaterialRate(found.rate || 0.0);
      if (found.material_form === "roll" && found.roll_width) {
        setLaceMaterialWidth(found.roll_width);
        setLaceMaterialWidthUnit(found.dimension_unit || "inch");
      } else if (found.width_mm) {
        setLaceMaterialWidth(Math.round(found.width_mm / INCH_TO_MM * 10) / 10);
        setLaceMaterialWidthUnit("inch");
      }
      if (found.roll_length) {
        setLaceMaterialLength(found.roll_length);
        setLaceMaterialLengthUnit("meter");
      }
    }
  };

  // Background scanner mode (Dark bed with contrast pattern vs Light bed)
  const [backgroundMode, setBackgroundMode] = useState("dark");

  // Standard factory presets (Insole, Socks covering)
  const [factoryPresets, setFactoryPresets] = useState(
    sample?.yield_spec?.standard_presets?.length > 0
      ? sample.yield_spec.standard_presets
      : FACTORY_PRESETS_DEFAULT
  );

  // Pattern library re-use & save states
  const [showLibraryModal, setShowLibraryModal] = useState(false);
  const [libraryPatterns, setLibraryPatterns] = useState([]);
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [libraryQuery, setLibraryQuery] = useState("");
  const [importingPattern, setImportingPattern] = useState(false);

  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveLibraryName, setSaveLibraryName] = useState(
    sample?.sample_name ? `${sample.sample_name} Pattern Master` : "Upper Pattern Master"
  );
  const [savingToLibrary, setSavingToLibrary] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState("");

  // Sheet / Nesting Parameters
  const [materialType, setMaterialType] = useState(sample?.yield_spec?.material_type || "roll");
  const [selectedMaterialId, setSelectedMaterialId] = useState(sample?.yield_spec?.material_id || "");
  const [selectedMaterialName, setSelectedMaterialName] = useState(sample?.yield_spec?.material_name || "");
  const [selectedComponentKey, setSelectedComponentKey] = useState(
    sample?.yield_spec?.component_nestings?.[0]?.key ||
    (sample?.pattern_pieces?.[0] ? `piece_${sample.pattern_pieces[0].piece_id || 0}` : "")
  );

  // Extract Tech Pack materials from sample specification
  const techPackMaterials = (() => {
    const list = [];
    const seen = new Set();

    if (Array.isArray(sample?.upper_spec?.materials)) {
      sample.upper_spec.materials.forEach((m, idx) => {
        if (m && (m.material_id || m.material_name)) {
          const key = m.material_id || `up_${idx}`;
          if (!seen.has(key)) {
            seen.add(key);
            list.push({
              material_id: m.material_id || null,
              material_name: m.material_name || "Upper Material",
              material_code: m.material_code || "",
              placement: m.placement || "Upper Specification",
              color: m.color_to_develop || "",
              component: "upper",
            });
          }
        }
      });
    }

    if (sample?.upper_spec?.upper_top_material_id || sample?.upper_spec?.upper_top_material_name) {
      const key = sample.upper_spec.upper_top_material_id || "primary_top";
      if (!seen.has(key)) {
        seen.add(key);
        list.push({
          material_id: sample.upper_spec.upper_top_material_id || null,
          material_name: sample.upper_spec.upper_top_material_name || "Primary Upper Top",
          material_code: sample.upper_spec.upper_top_material_code || "",
          placement: "Primary Upper Top",
          color: sample.upper_spec.upper_color_to_develop || "",
          component: "upper",
        });
      }
    }

    const effLiningName = sample?.upper_spec?.lining_material_name || sample?.upper_spec?.lining;
    if (effLiningName || sample?.upper_spec?.lining_material_id) {
      const key = sample?.upper_spec?.lining_material_id || "lining_mat";
      if (!seen.has(key)) {
        seen.add(key);
        list.push({
          material_id: sample?.upper_spec?.lining_material_id || null,
          material_name: effLiningName || "Lining Material",
          material_code: sample?.upper_spec?.lining_material_code || "",
          placement: "Upper Lining",
          color: "",
          component: "lining",
        });
      }
    }

    const effCanvasName = sample?.upper_spec?.canvas_backing || sample?.upper_spec?.canvas;
    if (effCanvasName || sample?.upper_spec?.canvas_material_id) {
      const key = sample?.upper_spec?.canvas_material_id || "canvas_mat";
      if (!seen.has(key)) {
        seen.add(key);
        list.push({
          material_id: sample?.upper_spec?.canvas_material_id || null,
          material_name: effCanvasName || "Canvas Reinforcement Backing",
          material_code: sample?.upper_spec?.canvas_material_code || "",
          placement: "Canvas Reinforcement Backing",
          color: "",
          component: "canvas_backing",
        });
      }
    }

    if (sample?.insole_spec?.socks_material_id || sample?.insole_spec?.socks_material_name) {
      const key = sample.insole_spec.socks_material_id || "socks_mat";
      if (!seen.has(key)) {
        seen.add(key);
        list.push({
          material_id: sample.insole_spec.socks_material_id || null,
          material_name: sample.insole_spec.socks_material_name || "Socks / Insole Covering",
          material_code: sample.insole_spec.socks_material_code || "",
          placement: "Insole Socks Covering",
          color: sample.insole_spec.socks_color || "",
          component: "insole_covering",
        });
      }
    }

    return list;
  })();

  const upperSpec = sample?.upper_spec || {};
  const liningName = upperSpec.lining_material_name || upperSpec.lining || "";
  const hasLining = Boolean(liningName && !["none", "null", "no", ""].includes(liningName.trim().toLowerCase()));
  const canvasName = upperSpec.canvas_backing || upperSpec.canvas || "";
  const hasCanvas = Boolean(canvasName && !["none", "null", "no", ""].includes(canvasName.trim().toLowerCase()));

  // Active scan category for Stage 1: "upper" | "lining" | "canvas"
  const [activeScanCategory, setActiveScanCategory] = useState("upper");
  // Active component category for Stage 2: "upper" | "lining" | "canvas_backing" | "strips"
  const [selectedComponentCategory, setSelectedComponentCategory] = useState("upper");
  const [savingMappedPieces, setSavingMappedPieces] = useState(false);
  const [mappedSaveSuccess, setMappedSaveSuccess] = useState("");

  const handleSaveMappedPieces = async () => {
    setSavingMappedPieces(true);
    setMappedSaveSuccess("");
    try {
      const res = await http.post(`/samples/${sid}/save-pattern-pieces`, {
        pieces: patternPieces,
        standard_strips: standardStrips,
      });
      if (res.data?.status === "success" || res.data?.ok) {
        setMappedSaveSuccess("Pattern pieces and component mappings saved separately to Digital Folders (03 Upper, 03B Lining, 03C Canvas)!");
        if (res.data.yield_spec) {
          setYieldSpec(res.data.yield_spec);
        }
        setTimeout(() => setMappedSaveSuccess(""), 4500);
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to save mapped pattern pieces"));
    } finally {
      setSavingMappedPieces(false);
    }
  };

  // Derive component list from yieldSpec.component_nestings, with backwards compatibility
  const activeComponentList = (() => {
    if (Array.isArray(yieldSpec?.component_nestings) && yieldSpec.component_nestings.length > 0) {
      return yieldSpec.component_nestings;
    }
    // Fallback: build from patternPieces, material_breakdown, and standardStrips
    const list = [];
    patternPieces.forEach((p, idx) => {
      const mb = yieldSpec?.material_breakdown?.find(
        (m) => (m.material_id && m.material_id === p.material_id) || (m.material_name && m.material_name === p.material_name)
      );
      list.push({
        key: `piece_${p.piece_id || idx}`,
        type: "pattern_piece",
        piece_id: p.piece_id || `piece_${idx}`,
        name: p.piece_name || `Component Piece ${idx + 1}`,
        component_type: p.component_type || p.component || "upper",
        material_id: p.material_id,
        material_name: p.material_name || mb?.material_name || "Upper Material",
        placement: p.placement || "Upper",
        pieces_per_pair: p.pieces_per_pair || 2,
        area_sqcm: p.area_sqcm,
        color: p.color || PIECE_COLORS[idx % PIECE_COLORS.length],
        consumption_per_pair: mb ? mb.consumption_per_pair : (yieldSpec?.consumption_per_pair || 0.05),
        consumption_unit: mb ? mb.consumption_unit : (yieldSpec?.consumption_unit || "meter"),
        yield_per_unit: mb ? mb.yield_per_unit : (yieldSpec?.yield_per_unit || 20.0),
        yield_unit_label: mb ? mb.yield_unit_label : "prs/m",
        utilization_pct: mb ? mb.utilization_pct : (yieldSpec?.utilization_pct || 90.0),
        waste_pct: mb ? mb.waste_pct : (yieldSpec?.waste_pct || 10.0),
        visual_nesting_preview: mb?.visual_nesting_preview || yieldSpec?.visual_nesting_preview,
      });
    });

    standardStrips.forEach((st, sIdx) => {
      const isUnf = st.strip_type === "unfolded";
      const cutW = st.cut_width_mm || 15.0;
      const fW = st.folded_width_mm || 8.0;
      const orientLabel = st.cut_orientation === "across_width" ? "Across Width" : "Along Length";
      list.push({
        key: `strip_${st.strip_id || sIdx}`,
        type: isUnf ? "unfolded_strip" : "folded_lace",
        strip_id: st.strip_id,
        name: isUnf
          ? `Unfolded Strip: ${st.name || "Strip"} (${cutW}mm · ${orientLabel})`
          : `Folded Lace: ${st.name || "Lace"} (${fW}mm folded · ${orientLabel})`,
        component_type: "strip",
        strip_type: st.strip_type || "folded",
        cut_orientation: st.cut_orientation || "along_length",
        material_name: st.material_name || "Strip Material",
        consumption_per_pair: st.consumption_per_pair || 0.01,
        consumption_unit: "meter",
        yield_per_unit: st.laces_yield_per_meter || 60,
        yield_unit_label: isUnf ? "strips / meter" : "laces / meter",
        color: isUnf ? "#06b6d4" : "#f97316",
        visual_nesting_preview: null,
      });
    });

    const liningMb = yieldSpec?.material_breakdown?.find((mb) => mb.is_lining);
    if (liningMb) {
      list.push({
        key: "component_lining",
        type: "lining",
        name: `Upper Lining (${liningMb.material_name})`,
        component_type: "lining",
        material_name: liningMb.material_name,
        color: "#10b981",
        consumption_per_pair: liningMb.consumption_per_pair,
        consumption_unit: "meter",
        yield_per_unit: liningMb.yield_per_unit,
        yield_unit_label: "pairs / meter",
        utilization_pct: liningMb.utilization_pct,
        waste_pct: liningMb.waste_pct,
        visual_nesting_preview: liningMb.visual_nesting_preview,
      });
    }

    const canvasMb = yieldSpec?.material_breakdown?.find((mb) => mb.is_canvas);
    if (canvasMb) {
      list.push({
        key: "component_canvas",
        type: "canvas_backing",
        name: `Canvas Reinforcement Backing (${canvasMb.specification || canvasMb.material_name})`,
        component_type: "canvas_backing",
        material_name: canvasMb.material_name,
        color: "#f59e0b",
        consumption_per_pair: canvasMb.consumption_per_pair,
        consumption_unit: "meter",
        yield_per_unit: canvasMb.yield_per_unit,
        yield_unit_label: "pairs / meter",
        utilization_pct: canvasMb.utilization_pct,
        waste_pct: canvasMb.waste_pct,
        visual_nesting_preview: canvasMb.visual_nesting_preview,
      });
    }

    return list;
  })();

  const categoryPieces = useMemo(() => {
    return activeComponentList.filter((c) => {
      if (selectedComponentCategory === "upper") {
        return (
          c.type === "pattern_piece" &&
          c.component_type !== "lining" &&
          c.component_type !== "canvas" &&
          c.component_type !== "canvas_backing" &&
          !c.name?.toLowerCase().includes("lining") &&
          !c.name?.toLowerCase().includes("canvas")
        );
      }
      if (selectedComponentCategory === "lining") {
        return (
          c.type === "lining" ||
          c.component_type === "lining" ||
          c.key?.startsWith("piece_lining_") ||
          c.name?.toLowerCase().includes("lining") ||
          c.placement?.toLowerCase().includes("lining")
        );
      }
      if (selectedComponentCategory === "canvas_backing") {
        return (
          c.type === "canvas_backing" ||
          c.component_type === "canvas" ||
          c.component_type === "canvas_backing" ||
          c.key?.startsWith("piece_canvas_") ||
          c.name?.toLowerCase().includes("canvas") ||
          c.placement?.toLowerCase().includes("canvas")
        );
      }
      if (selectedComponentCategory === "strips") {
        return (
          c.type === "folded_lace" ||
          c.type === "unfolded_strip" ||
          c.type === "strip"
        );
      }
      return true;
    });
  }, [activeComponentList, selectedComponentCategory]);

  // Keep selectedComponentKey pointing to a valid component in the active category
  useEffect(() => {
    if (categoryPieces.length > 0) {
      const isCurrentInCat = categoryPieces.some((p) => p.key === selectedComponentKey);
      if (!isCurrentInCat) {
        setSelectedComponentKey(categoryPieces[0].key);
      }
    } else if (activeComponentList.length > 0) {
      const exists = activeComponentList.some((c) => c.key === selectedComponentKey);
      if (!exists) {
        setSelectedComponentKey(activeComponentList[0].key);
      }
    }
  }, [categoryPieces, selectedComponentCategory, selectedComponentKey, activeComponentList]);

  const activeComponent =
    activeComponentList.find((c) => c.key === selectedComponentKey) ||
    categoryPieces[0] ||
    activeComponentList[0] ||
    null;

  const handlePieceMaterialChange = (pieceId, matIdentifier) => {
    setPatternPieces((prev) =>
      prev.map((p) => {
        if (p.piece_id !== pieceId) return p;
        if (!matIdentifier) {
          return { ...p, material_id: null, material_name: null, material_code: null, placement: null };
        }
        const tpMat = techPackMaterials.find((m) => m.material_id === matIdentifier || m.material_name === matIdentifier);
        if (tpMat) {
          return {
            ...p,
            material_id: tpMat.material_id,
            material_name: tpMat.material_name,
            material_code: tpMat.material_code,
            placement: tpMat.placement,
          };
        }
        const m = materialsList.find((mat) => (mat.id || mat._id) === matIdentifier);
        if (m) {
          return {
            ...p,
            material_id: m.id || m._id,
            material_name: m.name,
            material_code: m.code,
            placement: m.component_category || "Material Master",
          };
        }
        return p;
      })
    );
  };
  // Auto-assign default tech pack materials to pattern pieces if not yet assigned
  useEffect(() => {
    if (patternPieces.length > 0 && techPackMaterials.length > 0) {
      const hasUnassigned = patternPieces.some((p) => !p.material_id && !p.material_name);
      if (hasUnassigned) {
        setPatternPieces((prev) =>
          prev.map((p, idx) => {
            if (!p.material_id && !p.material_name) {
              const assignedMat = techPackMaterials[idx % techPackMaterials.length];
              return {
                ...p,
                material_id: assignedMat.material_id,
                material_name: assignedMat.material_name,
                material_code: assignedMat.material_code,
                placement: assignedMat.placement,
              };
            }
            return p;
          })
        );
      }
    }
  }, [patternPieces.length, techPackMaterials.length]);

  const [sheetLengthMm, setSheetLengthMm] = useState(sample?.yield_spec?.sheet_length_mm || 1524.0);
  const [sheetWidthMm, setSheetWidthMm] = useState(sample?.yield_spec?.sheet_width_mm || 1016.0);
  const [selvageMarginMm, setSelvageMarginMm] = useState(sample?.yield_spec?.selvage_margin_mm || 20.0);
  const [kerfSpacingMm, setKerfSpacingMm] = useState(sample?.yield_spec?.kerf_spacing_mm || 3.0);
  const [wasteAllowancePct, setWasteAllowancePct] = useState(sample?.yield_spec?.waste_allowance_pct || 5.0);

  // UI interaction states
  const [scanning, setScanning] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [previewZoom, setPreviewZoom] = useState(1.0);
  const [selectedPieceId, setSelectedPieceId] = useState(null);
  const fileInputRef = useRef(null);

  // Synchronize material dimensions with 2D Nesting settings
  const applyMaterialDimensions = (mId) => {
    setSelectedMaterialId(mId);
    if (!mId) return;
    const found = materialsList.find((m) => (m.id || m._id) === mId);
    if (found) {
      setSelectedMaterialName(found.name || "");
      if (found.material_form === "roll") {
        setMaterialType("roll");
        if (found.roll_width) {
          const wStr = String(found.roll_width);
          const matchPreset = ROLL_WIDTH_PRESETS.find((p) => String(p.inches) === wStr);
          if (matchPreset) {
            setRollWidthPreset(String(matchPreset.inches));
          } else {
            setRollWidthPreset("custom");
            setCustomRollWidthMm(found.width_mm || (found.roll_width * INCH_TO_MM));
          }
        }
        if (found.roll_length) {
          const lStr = String(found.roll_length);
          const matchLen = ROLL_LENGTH_PRESETS.find((p) => String(p.meters) === lStr);
          if (matchLen) {
            setRollLengthPreset(String(matchLen.meters));
          } else {
            setRollLengthPreset("custom");
            setCustomRollLengthMeters(found.roll_length);
          }
        }
      } else if (found.material_form === "sheet") {
        setMaterialType("sheet");
        if (found.width_mm) setSheetWidthMm(found.width_mm);
        else if (found.sheet_width) setSheetWidthMm(found.sheet_width * INCH_TO_MM);
        if (found.height_mm) setSheetLengthMm(found.height_mm);
        else if (found.sheet_height) setSheetLengthMm(found.sheet_height * INCH_TO_MM);
      }
    }
  };

  // Auto-fill material from upper spec if present
  useEffect(() => {
    if (!selectedMaterialId && sample?.upper_spec) {
      const uMat = sample.upper_spec.materials?.[0] || {};
      const targetId = uMat.material_id || sample.upper_spec.upper_top_material_id;
      if (targetId) {
        applyMaterialDimensions(targetId);
      }
    }
  }, [sample, selectedMaterialId, materialsList]);

  // Compute effective roll width in mm
  const effectiveRollWidthMm =
    rollWidthPreset === "custom"
      ? parseFloat(customRollWidthMm) || 1371.6
      : (parseFloat(rollWidthPreset) || 54.0) * INCH_TO_MM;

  // Compute effective roll length in meters
  const effectiveRollLengthMeters =
    rollLengthPreset === "custom"
      ? parseFloat(customRollLengthMeters) || 50.0
      : parseFloat(rollLengthPreset) || 1.0;

  // Pattern library loader
  const fetchLibraryPatterns = async (q = "") => {
    setLoadingLibrary(true);
    try {
      const res = await http.get(`/samples/pattern-library${q ? `?q=${encodeURIComponent(q)}` : ""}`);
      setLibraryPatterns(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Failed to load pattern library:", err);
    } finally {
      setLoadingLibrary(false);
    }
  };

  const handleOpenLibrary = () => {
    setShowLibraryModal(true);
    fetchLibraryPatterns(libraryQuery);
  };

  const handleImportPattern = async (pat) => {
    if (!pat) return;
    setImportingPattern(true);
    try {
      const res = await http.post(`/samples/${sid}/import-pattern`, {
        pattern_id: pat.id || pat._id,
        pattern_code: pat.pattern_code,
      });
      if (res.data?.ok) {
        const updated = res.data.sample || {};
        setPatternPieces(updated.pattern_pieces || []);
        setStandardStrips(updated.standard_strips || []);
        if (updated.yield_spec) setYieldSpec(updated.yield_spec);
        if (updated.pattern_scan_url) setScanUrl(updated.pattern_scan_url);
        setShowLibraryModal(false);
        if (onSaved) onSaved(updated);
        alert(`Successfully imported pattern "${pat.pattern_name || pat.pattern_code}"!`);
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to import pattern from library"));
    } finally {
      setImportingPattern(false);
    }
  };

  const handleSaveToLibrary = async () => {
    if (!saveLibraryName.trim()) {
      alert("Please provide a name for this pattern master.");
      return;
    }
    setSavingToLibrary(true);
    try {
      const res = await http.post(`/samples/${sid}/save-to-library`, {
        pattern_name: saveLibraryName.trim(),
        category: "Upper Pattern",
      });
      if (res.data?.ok) {
        setSaveSuccessMsg(`Saved pattern as ${res.data.pattern?.pattern_code || saveLibraryName}!`);
        setTimeout(() => {
          setShowSaveModal(false);
          setSaveSuccessMsg("");
        }, 1500);
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to save pattern to library"));
    } finally {
      setSavingToLibrary(false);
    }
  };

  // Upload A4 Scan with dark bed calibration
  // Upload A4 Scan with category and dark bed calibration
  const handleFileUpload = async (file, category = activeScanCategory || "upper") => {
    if (!file) return;
    setScanning(true);
    setUploadError("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await http.post(
        `/samples/${sid}/pattern-scan?background_mode=${backgroundMode}&component_category=${category}`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );

      if (res.data?.ok || res.data?.status === "success") {
        const scanRes = res.data.scan_result || {};
        setScanUrl(res.data.sample?.pattern_scan_url || res.data.scan_url || "");
        setCalibration(scanRes.calibration || null);
        const pieces = res.data.pattern_pieces || [];
        setPatternPieces(pieces);
        if (res.data.yield_spec) {
          setYieldSpec(res.data.yield_spec);
        }
        if (pieces.length > 0) {
          setSelectedPieceId(pieces[0].piece_id);
        }
      }
    } catch (err) {
      setUploadError(getErrorMessage(err, "Failed to scan and calibrate pattern"));
    } finally {
      setScanning(false);
    }
  };

  // Add a Manual Component Piece without scanning
  const handleAddManualPiece = () => {
    const lMm = parseInputToMm(newPieceLength) || 120.0;
    const wMm = parseInputToMm(newPieceWidth) || 60.0;
    const areaSqcm = parseFloat(((lMm * wMm) / 100.0 * 0.85).toFixed(2));
    const pcsPerPair = parseInt(newPiecePcsPerPair) || 2;

    const newPiece = {
      piece_id: `manual_${Date.now()}`,
      piece_name: newPieceName.trim() || "Upper Component",
      component: "upper",
      component_type: newPieceType,
      area_sqcm: areaSqcm,
      length_mm: lMm,
      width_mm: wMm,
      pieces_per_pair: pcsPerPair,
      cutting_direction: newPieceCutDir,
      measurement_unit: measurementUnit,
      bbox_page: { x_mm: 30, y_mm: 30, w_mm: wMm, h_mm: lMm },
    };

    setPatternPieces((prev) => [...prev, newPiece]);
    setSelectedPieceId(newPiece.piece_id);
    setShowAddPieceModal(false);
  };

  const handleRemovePiece = (pieceId) => {
    setPatternPieces((prev) => prev.filter((p) => p.piece_id !== pieceId));
  };

  // Add a Standard Folded Lace or Unfolded Strip with Live 1-Meter Yield Calculation & Defined Material Dimensions
  const handleAddStandardStrip = () => {
    const isUnfolded = stripType === "unfolded";
    const foldedW = parseFloat(newStripFoldedWidthMm) || 8.0;
    const cutW = isUnfolded ? (parseFloat(unfoldedStripWidthMm) || 15.0) : (2.0 * foldedW);
    let lengthMm = parseFloat(newStripLengthMm) || 650.0;
    if (newStripLengthUnit === "inch") lengthMm *= INCH_TO_MM;
    if (newStripLengthUnit === "cm") lengthMm *= 10.0;

    const pcsPerPair = parseInt(newStripPcsPerPair) || 2;

    // Convert defined lace material width to mm:
    let matWMm = parseFloat(laceMaterialWidth) || 50.0;
    if (laceMaterialWidthUnit === "inch") matWMm *= INCH_TO_MM;
    else if (laceMaterialWidthUnit === "cm") matWMm *= 10.0;

    // Convert defined lace material length to meters:
    let matLenM = parseFloat(laceMaterialLength) || 1.0;
    if (laceMaterialLengthUnit === "inch") matLenM = matLenM * 0.0254;
    else if (laceMaterialLengthUnit === "yard") matLenM = matLenM * 0.9144;

    const usableW = Math.max(50.0, matWMm - (2 * selvageMarginMm));

    let lanes, lacesPerMeter;
    if (stripCutOrientation === "across_width") {
      const cutsPerMeter = Math.max(1, Math.floor(1000.0 / (cutW + 1.0)));
      const stripsPerCut = lengthMm >= (usableW * 0.95) ? 1 : Math.max(1, Math.floor(usableW / lengthMm));
      lacesPerMeter = parseFloat((cutsPerMeter * stripsPerCut).toFixed(2));
      lanes = cutsPerMeter;
    } else {
      lanes = Math.max(1, Math.floor((usableW + 1.0) / (cutW + 1.0)));
      lacesPerMeter = lengthMm > 0 ? parseFloat(((lanes * 1000.0) / lengthMm).toFixed(2)) : 0.0;
    }

    const pairsPerMeter = pcsPerPair > 0 ? parseFloat((lacesPerMeter / pcsPerPair).toFixed(2)) : 0.0;
    const wasteMult = 1.0 + (wasteAllowancePct / 100.0);
    const consumptionPerPair = pairsPerMeter > 0 ? parseFloat(((1.0 / pairsPerMeter) * wasteMult).toFixed(5)) : 0.0;
    const totalLacesRoll = Math.round(lacesPerMeter * matLenM);
    const totalPairsRoll = Math.round(pairsPerMeter * matLenM);
    const rateVal = parseFloat(laceMaterialRate) || 0.0;
    const costPerPair = parseFloat((consumptionPerPair * rateVal).toFixed(2));

    const defaultTitle = isUnfolded
      ? `Unfolded Strip (${cutW}mm)`
      : `Folded Lace (${foldedW}mm)`;

    const newStrip = {
      strip_id: `strip_${Date.now()}`,
      name: newStripName.trim() || defaultTitle,
      strip_type: stripType,
      cut_orientation: stripCutOrientation,
      strip_width_mm: isUnfolded ? cutW : null,
      strip_width_label: isUnfolded ? `${cutW}mm` : null,
      folded_width_mm: isUnfolded ? cutW : foldedW,
      folded_width_label: isUnfolded ? `${cutW}mm raw` : `${foldedW}mm`,
      cut_width_mm: cutW,
      length_mm: lengthMm,
      pieces_per_pair: pcsPerPair,
      lanes_across_roll: lanes,
      total_lace_meters_per_roll_meter: stripCutOrientation === "across_width" ? parseFloat(((lacesPerMeter * lengthMm) / 1000.0).toFixed(2)) : lanes * 1.0,
      laces_yield_per_meter: lacesPerMeter,
      pairs_per_meter: pairsPerMeter,
      consumption_per_pair: consumptionPerPair,
      yield_per_unit: pairsPerMeter,
      yield_unit_label: isUnfolded ? "strips / meter" : "pairs / meter",
      area_sqcm: parseFloat(((cutW * lengthMm * pcsPerPair) / 100.0).toFixed(2)),
      component: isUnfolded ? "unfolded_strip" : "folded_lace",
      cutting_direction: stripCutOrientation === "across_width" ? "width_up" : "length_up",
      // Material Link & Defined Dimensions
      material_id: laceMaterialId || null,
      material_name: laceMaterialName || null,
      material_code: laceMaterialCode || null,
      material_rate: rateVal,
      material_width: parseFloat(laceMaterialWidth) || 50.0,
      material_width_unit: laceMaterialWidthUnit,
      material_width_mm: matWMm,
      material_length: parseFloat(laceMaterialLength) || 1.0,
      material_length_unit: laceMaterialLengthUnit,
      material_length_meters: matLenM,
      total_laces_full_roll: totalLacesRoll,
      total_pairs_full_roll: totalPairsRoll,
      cost_per_pair: costPerPair,
      formula_note: isUnfolded
        ? `Unfolded Strip (${cutW}mm) · Cut ${stripCutOrientation === "across_width" ? "across width" : "along length"} · ${lacesPerMeter} strips/m from ${laceMaterialName || 'Roll'} [${laceMaterialWidth}"W]`
        : `Cut Width ${cutW}mm = 2×Folded ${foldedW}mm from ${laceMaterialName || 'Roll'} [${laceMaterialWidth}"W × ${matLenM}mL] · ${lacesPerMeter} laces/m (${lanes} lanes)`,
    };

    setStandardStrips((prev) => [...prev, newStrip]);
    setNewStripName("");
  };

  const handleRemoveStandardStrip = (stripId) => {
    setStandardStrips((prev) => prev.filter((s) => s.strip_id !== stripId));
  };

  // Recalculate 2D Nesting & Yield Simulation
  const handleRecalculateYield = async () => {
    if (patternPieces.length === 0 && standardStrips.length === 0) {
      alert("No pattern pieces or standard lace components found. Please upload a scan or add components.");
      return;
    }
    setCalculating(true);
    try {
      const payload = {
        material_type: materialType,
        material_id: selectedMaterialId || null,
        material_name: selectedMaterialName || null,
        roll_width_inches: rollWidthPreset === "custom" ? (parseFloat(customRollWidthMm) / INCH_TO_MM) : parseFloat(rollWidthPreset),
        custom_roll_width_mm: rollWidthPreset === "custom" ? parseFloat(customRollWidthMm) : null,
        roll_length_meters: effectiveRollLengthMeters,
        sheet_length_mm: materialType === "sheet" ? parseFloat(sheetLengthMm) || 1524.0 : null,
        sheet_width_mm: materialType === "sheet" ? parseFloat(sheetWidthMm) || 1016.0 : null,
        selvage_margin_mm: parseFloat(selvageMarginMm) || 20.0,
        kerf_spacing_mm: parseFloat(kerfSpacingMm) || 3.0,
        waste_allowance_pct: parseFloat(wasteAllowancePct) || 5.0,
        cutting_direction: cuttingDirection,
        expected_pieces_count: parseInt(expectedPiecesCount) || null,
        measurement_unit: measurementUnit,
        pieces: patternPieces,
        standard_strips: standardStrips,
        standard_presets: factoryPresets.filter((p) => p.active),
        upper_spec: sample?.upper_spec,
        lining_material_id: sample?.upper_spec?.lining_material_id,
        lining_material_name: sample?.upper_spec?.lining_material_name,
        lining_material_code: sample?.upper_spec?.lining_material_code,
        canvas_backing: sample?.upper_spec?.canvas_backing,
      };

      const res = await http.post(`/samples/${sid}/calculate-yield`, payload);
      if (res.data?.ok) {
        setYieldSpec(res.data.yield_spec);
        if (res.data.standard_strips) setStandardStrips(res.data.standard_strips);
        if (onSaved) onSaved(res.data.sample);
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to calculate 2D nesting yield"));
    } finally {
      setCalculating(false);
    }
  };

  const handlePieceChange = (pieceId, key, value) => {
    setPatternPieces((prev) =>
      prev.map((p) => (p.piece_id === pieceId ? { ...p, [key]: value } : p))
    );
  };

  // Total Net Surface Area for 1 pair
  const totalPiecesAreaSqcm = patternPieces.reduce(
    (sum, p) => sum + (parseFloat(p.area_sqcm) || 0) * (parseInt(p.pieces_per_pair) || 2),
    0
  );
  const totalStripsAreaSqcm = standardStrips.reduce(
    (sum, s) => sum + (parseFloat(s.area_sqcm) || 0),
    0
  );
  const totalNetPairAreaSqcm = totalPiecesAreaSqcm + totalStripsAreaSqcm;

  const totalDefinedPiecesCount = patternPieces.length + standardStrips.length;
  const isPiecesCountMatched = totalDefinedPiecesCount === parseInt(expectedPiecesCount);

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5 overflow-y-auto">
      <div className="bg-[#F7F7F5] border-2 border-slate-900 shadow-ind-xl w-full max-w-[96vw] xl:max-w-[1440px] max-h-[94vh] flex flex-col overflow-hidden text-slate-900">
        
        {/* HEADER */}
        <div className="bg-slate-900 text-white px-5 py-3.5 flex items-center justify-between shrink-0 border-b-2 border-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-[#C27842] border border-amber-400 flex items-center justify-center text-white font-bold">
              <Scan className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs uppercase tracking-widest text-amber-400 font-bold">
                  {sample?.temp_code || "SMP-SAMPLE"}
                </span>
                <span className="text-slate-400">·</span>
                <h2 className="text-sm sm:text-base font-black uppercase tracking-tight text-white">
                  A4 Pattern Scanner & 2D Visual Yield Engine
                </h2>
              </div>
              <p className="text-[11px] text-slate-300 font-mono">
                {sample?.sample_name} ({sample?.profile?.toUpperCase() || "FLAT"})
                {sample?.linked_pattern_code && (
                  <span className="ml-2 text-amber-300 font-bold">· Linked Pattern: {sample.linked_pattern_code}</span>
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Unit Switcher in Header */}
            <div className="hidden sm:flex items-center gap-1 bg-slate-800 p-1 border border-slate-700 text-xs font-mono">
              <span className="text-slate-400 px-1 text-[10px] uppercase font-bold">Units:</span>
              {["mm", "cm", "inch"].map((u) => (
                <button
                  key={u}
                  type="button"
                  onClick={() => setMeasurementUnit(u)}
                  className={`px-1.5 py-0.5 uppercase font-bold text-[10px] transition ${
                    measurementUnit === u
                      ? "bg-[#C27842] text-white"
                      : "text-slate-300 hover:text-white"
                  }`}
                >
                  {u}
                </button>
              ))}
              <span className="text-slate-500">|</span>
              {["cm²", "sq in", "sq ft"].map((au) => (
                <button
                  key={au}
                  type="button"
                  onClick={() => setAreaUnit(au)}
                  className={`px-1.5 py-0.5 text-[10px] transition ${
                    areaUnit === au
                      ? "bg-emerald-600 text-white font-bold"
                      : "text-slate-300 hover:text-white"
                  }`}
                >
                  {au}
                </button>
              ))}
            </div>

            {/* Re-use from Library Button */}
            <button
              onClick={handleOpenLibrary}
              type="button"
              className="bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-600 px-3 py-1.5 text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 transition"
              title="Browse and re-use existing pattern from other styles"
            >
              <FolderOpen className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden md:inline">Pattern Library</span>
            </button>

            {/* Save to Library Button */}
            {patternPieces.length > 0 && (
              <button
                onClick={() => setShowSaveModal(true)}
                type="button"
                className="bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-600 px-3 py-1.5 text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 transition"
                title="Save this digitized pattern to reusable library"
              >
                <Bookmark className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden md:inline">Save Library</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white hover:bg-slate-800 p-1.5 transition ml-2"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* WORKFLOW TABS */}
        <div className="bg-white border-b-2 border-slate-200 px-5 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab("scan")}
              className={`px-4 py-3 text-xs font-bold uppercase tracking-wider flex items-center gap-2 border-b-2 transition ${
                activeTab === "scan"
                  ? "border-[#C27842] text-[#C27842] bg-amber-50/50"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <Scan className="w-3.5 h-3.5" />
              <span>1. Components & Pieces ({totalDefinedPiecesCount})</span>
              {expectedPiecesCount && (
                <span className={`px-1.5 py-0.2 text-[10px] font-mono font-bold rounded ${
                  isPiecesCountMatched ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                }`}>
                  {totalDefinedPiecesCount}/{expectedPiecesCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("nesting")}
              className={`px-4 py-3 text-xs font-bold uppercase tracking-wider flex items-center gap-2 border-b-2 transition ${
                activeTab === "nesting"
                  ? "border-[#C27842] text-[#C27842] bg-amber-50/50"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <Grid className="w-3.5 h-3.5" />
              <span>2. 2D Layout & Stretch Control</span>
              {yieldSpec && (
                <span className="ml-1 px-1.5 py-0.2 bg-emerald-100 text-emerald-800 text-[10px] font-mono font-bold rounded">
                  {yieldSpec.yield_per_unit} prs/{yieldSpec.consumption_unit === "meter" ? "m" : "sht"}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("bom")}
              className={`px-4 py-3 text-xs font-bold uppercase tracking-wider flex items-center gap-2 border-b-2 transition ${
                activeTab === "bom"
                  ? "border-[#C27842] text-[#C27842] bg-amber-50/50"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>3. Style BOM & PLM Archival</span>
            </button>
          </div>

          {/* Quick Metrics in Tab Bar */}
          {yieldSpec && (
            <div className="hidden sm:flex items-center gap-4 text-xs font-mono">
              <div className="text-right">
                <span className="text-slate-500 text-[10px] uppercase block">Total Net / Pr:</span>
                <span className="font-bold text-slate-900">{toDisplayArea(totalNetPairAreaSqcm)} {areaUnit}</span>
              </div>
              <div className="text-right">
                <span className="text-slate-500 text-[10px] uppercase block">Upper Consumption:</span>
                <span className="font-bold text-[#C27842]">{yieldSpec.consumption_per_pair} {yieldSpec.consumption_unit}/pr</span>
              </div>
              <div className="text-right">
                <span className="text-slate-500 text-[10px] uppercase block">Cutting Direction:</span>
                <span className="font-bold text-indigo-700 capitalize">{cuttingDirection.replace("_", "-")}</span>
              </div>
            </div>
          )}
        </div>

        {/* MODAL BODY */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">

          {/* ═══════════════════════════════════════════════════════════════════
              TAB 1: COMPONENT PIECES DEFINITION & SCANNER
              ═══════════════════════════════════════════════════════════════════ */}
          {activeTab === "scan" && (
            <div className="space-y-6">

              {/* REQUIREMENT 1: EXPECTED PIECES DEFINITION & MANAGEMENT BAR */}
              <div className="bg-white border-2 border-slate-900 p-4 space-y-3 shadow-ind">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-2.5">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#C27842]" />
                    <div>
                      <h3 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                        Upper Pattern Components Specification
                      </h3>
                      <p className="text-[11px] text-slate-500 font-mono">
                        Define expected pieces (Vamps, Quarters, Straps, Laces) and account for all pattern parts.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 bg-slate-50 border border-slate-300 px-3 py-1 text-xs font-mono">
                      <span className="text-[10px] uppercase font-bold text-slate-500">Expected Pieces:</span>
                      <input
                        type="number"
                        min="1"
                        max="20"
                        value={expectedPiecesCount}
                        onChange={(e) => setExpectedPiecesCount(parseInt(e.target.value) || 1)}
                        className="w-12 font-bold text-center border-b border-slate-400 bg-transparent focus:outline-none focus:border-slate-900"
                      />
                    </div>

                    <div className={`px-2.5 py-1 text-xs font-mono font-bold border ${
                      isPiecesCountMatched 
                        ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                        : "bg-amber-50 text-amber-800 border-amber-300"
                    }`}>
                      {totalDefinedPiecesCount} Defined / {expectedPiecesCount} Expected 
                      {isPiecesCountMatched ? " (Complete)" : ` (${Math.abs(expectedPiecesCount - totalDefinedPiecesCount)} pending)`}
                    </div>

                    <button
                      type="button"
                      onClick={() => setShowAddPieceModal(true)}
                      className="bg-slate-900 hover:bg-slate-800 text-white font-bold uppercase text-xs py-1.5 px-3 border border-slate-900 flex items-center gap-1.5 shadow-ind"
                    >
                      <Plus className="w-3.5 h-3.5 text-amber-400" />
                      <span>Add Component Piece</span>
                    </button>
                  </div>
                </div>

                {/* Quick Unit and Contrast Bar */}
                <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-mono pt-1">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500 text-[11px] uppercase">Active Measuring Unit:</span>
                    <span className="px-2 py-0.5 bg-slate-100 font-bold border border-slate-300 text-slate-800">
                      Linear: {measurementUnit.toUpperCase()} · Area: {areaUnit}
                    </span>
                  </div>

                  {/* Dark Bed vs Light Bed Selector */}
                  <div className="flex items-center gap-1.5 bg-slate-100 p-0.5 border border-slate-300">
                    <button
                      type="button"
                      onClick={() => setBackgroundMode("dark")}
                      className={`px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider flex items-center gap-1 transition ${
                        backgroundMode === "dark"
                          ? "bg-slate-900 text-white shadow"
                          : "text-slate-700 hover:text-slate-900"
                      }`}
                    >
                      <Moon className="w-3 h-3 text-amber-300" />
                      <span>Dark Bed (Contrast Pattern)</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setBackgroundMode("light")}
                      className={`px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider flex items-center gap-1 transition ${
                        backgroundMode === "light"
                          ? "bg-slate-900 text-white shadow"
                          : "text-slate-700 hover:text-slate-900"
                      }`}
                    >
                      <Sun className="w-3 h-3 text-yellow-500" />
                      <span>Light Bed</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Scan Category Switcher: Upper vs Lining vs Canvas */}
              <div className="bg-slate-100 p-2 border-2 border-slate-900 flex flex-wrap items-center justify-between gap-2 shadow-ind">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setActiveScanCategory("upper")}
                    className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider flex items-center gap-2 border transition ${
                      activeScanCategory === "upper"
                        ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                        : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <Layers className="w-3.5 h-3.5 text-blue-400" />
                    <span>Upper Patterns</span>
                    <span className="text-[10px] px-1.5 py-0.2 bg-blue-500 text-white rounded-full font-mono">
                      {patternPieces.filter((p) => (p.component || "upper") === "upper").length}
                    </span>
                  </button>

                  {hasLining && (
                    <button
                      type="button"
                      onClick={() => setActiveScanCategory("lining")}
                      className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider flex items-center gap-2 border transition ${
                        activeScanCategory === "lining"
                          ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                          : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                      <span>Lining Patterns</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                        patternPieces.some((p) => p.component === "lining") ? "bg-emerald-600 text-white" : "bg-amber-100 text-amber-900 font-bold"
                      }`}>
                        {patternPieces.filter((p) => p.component === "lining").length > 0
                          ? `${patternPieces.filter((p) => p.component === "lining").length} scanned`
                          : "Scan Required"}
                      </span>
                    </button>
                  )}

                  {hasCanvas && (
                    <button
                      type="button"
                      onClick={() => setActiveScanCategory("canvas")}
                      className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider flex items-center gap-2 border transition ${
                        activeScanCategory === "canvas"
                          ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                          : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                      <span>Canvas & Reinforcements</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                        patternPieces.some((p) => p.component === "canvas_backing" || p.component === "canvas") ? "bg-amber-600 text-white" : "bg-amber-100 text-amber-900 font-bold"
                      }`}>
                        {patternPieces.filter((p) => p.component === "canvas_backing" || p.component === "canvas").length > 0
                          ? `${patternPieces.filter((p) => p.component === "canvas_backing" || p.component === "canvas").length} scanned`
                          : "Scan Required"}
                      </span>
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2 text-xs font-mono">
                  <span className="text-slate-500">Destination PLM Folder:</span>
                  <span className="px-2 py-0.5 bg-white border border-slate-300 font-bold text-slate-800">
                    {activeScanCategory === "lining" ? "03B Lining Patterns" : activeScanCategory === "canvas" ? "03C Canvas & Reinforcements" : "03 Upper Patterns"}
                  </span>
                </div>
              </div>

              {/* Guidance alerts from Tech Pack specifications */}
              {hasLining && !patternPieces.some((p) => p.component === "lining") && (
                <div className="bg-emerald-50 border border-emerald-300 p-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-emerald-900">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>
                      Tech Pack specifies Lining: <strong>{liningName}</strong>. Please scan the separate lining pattern sheet to calculate dedicated lining consumption.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveScanCategory("lining")}
                    className="bg-emerald-700 hover:bg-emerald-800 text-white text-[11px] font-bold uppercase px-2.5 py-1"
                  >
                    Scan Lining Pattern
                  </button>
                </div>
              )}

              {hasCanvas && !patternPieces.some((p) => p.component === "canvas_backing" || p.component === "canvas") && (
                <div className="bg-amber-50 border border-amber-300 p-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-amber-900">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                    <span>
                      Tech Pack specifies Canvas: <strong>{canvasName}</strong>. Please scan the separate canvas reinforcement pattern sheet.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveScanCategory("canvas")}
                    className="bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-bold uppercase px-2.5 py-1"
                  >
                    Scan Canvas Pattern
                  </button>
                </div>
              )}

              {mappedSaveSuccess && (
                <div className="bg-emerald-100 border-2 border-emerald-500 text-emerald-900 p-3 text-xs font-bold flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>{mappedSaveSuccess}</span>
                </div>
              )}

              {/* Upload Dropzone */}
              <div className="bg-white border-2 border-dashed border-slate-300 p-5 text-center hover:border-[#C27842] transition relative">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.[0]) handleFileUpload(e.target.files[0], activeScanCategory);
                  }}
                />

                <div className="max-w-md mx-auto space-y-2.5">
                  <div className="w-10 h-10 bg-slate-100 border border-slate-300 mx-auto flex items-center justify-center text-slate-700">
                    {scanning ? (
                      <RefreshCw className="w-5 h-5 animate-spin text-[#C27842]" />
                    ) : (
                      <Upload className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-xs sm:text-sm font-bold uppercase text-slate-900">
                      {scanning
                        ? `Scanning on ${backgroundMode.toUpperCase()} Bed...`
                        : activeScanCategory === "lining"
                        ? `Upload Lining Pattern Scan — ${liningName}`
                        : activeScanCategory === "canvas"
                        ? `Upload Canvas Reinforcement Pattern Scan — ${canvasName}`
                        : "Upload A4 Upper Pattern Scan (210 × 297 mm)"}
                    </h3>
                    <p className="text-[11px] text-slate-500 font-mono">
                      {activeScanCategory === "lining"
                        ? `Place lining parts flat on scanner bed. Digital folder: 03B Lining Patterns.`
                        : activeScanCategory === "canvas"
                        ? `Place canvas/backing parts flat on scanner bed. Digital folder: 03C Canvas & Reinforcements.`
                        : "Place vamps, straps, and quarters flat on scanner. Computer vision automatically detects contours and calibrated scale."}
                    </p>
                  </div>

                  <div className="pt-1 flex items-center justify-center gap-3">
                    <button
                      type="button"
                      disabled={scanning}
                      onClick={() => fileInputRef.current?.click()}
                      className="bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase text-xs py-2 px-4 border-2 border-[#C27842] shadow-ind flex items-center gap-2 disabled:opacity-50"
                    >
                      <Scan className="w-4 h-4" />
                      <span>{scanUrl ? "Upload New Scan" : "Scan A4 Patterns"}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowAddPieceModal(true)}
                      className="bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold uppercase text-xs py-2 px-4 border-2 border-slate-300 shadow-ind flex items-center gap-2"
                    >
                      <Plus className="w-4 h-4 text-emerald-600" />
                      <span>Add Unscanned Component</span>
                    </button>
                  </div>
                </div>

                {uploadError && (
                  <div className="mt-3 p-2 bg-rose-50 border border-rose-300 text-rose-800 text-xs flex items-center gap-2 justify-center">
                    <AlertCircle className="w-4 h-4" />
                    <span>{uploadError}</span>
                  </div>
                )}
              </div>

              {/* Detected Pieces & Preview Canvas */}
              {patternPieces.length > 0 && (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
                  {/* Left: A4 Scanner Canvas Visualizer */}
                  <div className="lg:col-span-4 bg-white border-2 border-slate-900 p-4 space-y-3 flex flex-col justify-between">
                    <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                      <div className="flex items-center gap-1.5">
                        <Scan className="w-4 h-4 text-slate-700" />
                        <span className="font-bold text-xs uppercase tracking-wide">
                          A4 Scanner Bed (210 × 297 mm)
                        </span>
                      </div>
                      {calibration && (
                        <span className="text-[10px] font-mono text-slate-500">
                          {calibration.dpi} DPI · {backgroundMode.toUpperCase()}
                        </span>
                      )}
                    </div>

                    {/* SVG A4 Bed Rendering */}
                    <div className={`relative aspect-[1/1.414] border border-slate-300 p-2 shadow-inner overflow-hidden flex items-center justify-center ${backgroundMode === "dark" ? "bg-slate-900" : "bg-slate-50"}`}>
                      <svg
                        viewBox="0 0 210 297"
                        className="w-full h-full max-h-[380px] object-contain drop-shadow"
                      >
                        <rect 
                          x="0" 
                          y="0" 
                          width="210" 
                          height="297" 
                          fill={backgroundMode === "dark" ? "#1e293b" : "#ffffff"} 
                          stroke={backgroundMode === "dark" ? "#475569" : "#94a3b8"} 
                          strokeWidth="0.5" 
                        />
                        
                        {[...Array(10)].map((_, i) => (
                          <line 
                            key={`x-${i}`} 
                            x1={(i + 1) * 20} 
                            y1="0" 
                            x2={(i + 1) * 20} 
                            y2="297" 
                            stroke={backgroundMode === "dark" ? "#334155" : "#f1f5f9"} 
                            strokeWidth="0.3" 
                          />
                        ))}
                        {[...Array(14)].map((_, i) => (
                          <line 
                            key={`y-${i}`} 
                            x1="0" 
                            y1={(i + 1) * 20} 
                            x2="210" 
                            y2={(i + 1) * 20} 
                            stroke={backgroundMode === "dark" ? "#334155" : "#f1f5f9"} 
                            strokeWidth="0.3" 
                          />
                        ))}

                        {patternPieces.map((p, idx) => {
                          const isSelected = p.piece_id === selectedPieceId;
                          return (
                            <g key={p.piece_id || idx} onClick={() => setSelectedPieceId(p.piece_id)} className="cursor-pointer">
                              {p.svg_polygon ? (
                                <path
                                  d={p.svg_polygon}
                                  fill={isSelected ? "rgba(194, 120, 66, 0.7)" : (backgroundMode === "dark" ? "rgba(254, 240, 138, 0.85)" : "rgba(59, 130, 246, 0.45)")}
                                  stroke={isSelected ? "#ffffff" : (backgroundMode === "dark" ? "#ca8a04" : "#2563eb")}
                                  strokeWidth={isSelected ? "1.5" : "0.8"}
                                />
                              ) : (
                                <rect
                                  x={p.bbox_page?.x_mm || 20}
                                  y={p.bbox_page?.y_mm || 20}
                                  width={p.width_mm}
                                  height={p.length_mm}
                                  fill={isSelected ? "rgba(194, 120, 66, 0.7)" : (backgroundMode === "dark" ? "rgba(254, 240, 138, 0.85)" : "rgba(59, 130, 246, 0.45)")}
                                  stroke={isSelected ? "#ffffff" : (backgroundMode === "dark" ? "#ca8a04" : "#2563eb")}
                                  strokeWidth={isSelected ? "1.5" : "0.8"}
                                />
                              )}
                              {p.bbox_page && (
                                <text
                                  x={p.bbox_page.x_mm + p.bbox_page.w_mm / 2}
                                  y={p.bbox_page.y_mm + p.bbox_page.h_mm / 2}
                                  textAnchor="middle"
                                  fill={backgroundMode === "dark" ? "#0f172a" : "#1e293b"}
                                  fontSize="4.5"
                                  fontWeight="bold"
                                  fontFamily="monospace"
                                >
                                  {p.piece_name || `Piece ${idx + 1}`}
                                </text>
                              )}
                            </g>
                          );
                        })}
                      </svg>
                    </div>

                    <div className="flex items-center justify-between text-[11px] font-mono text-slate-600 pt-1">
                      <span>Pattern Pieces Area:</span>
                      <span className="font-bold text-slate-900">{toDisplayArea(totalPiecesAreaSqcm)} {areaUnit} / pair</span>
                    </div>
                  </div>

                  {/* Right: Detected Pattern Pieces Table with Component Types & Stretch Control */}
                  <div className="lg:col-span-8 bg-white border-2 border-slate-900 p-4 flex flex-col justify-between">
                    <div className="space-y-3 flex-1 flex flex-col min-h-0">
                      <div className="flex flex-wrap items-center justify-between border-b border-slate-200 pb-2 gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs uppercase tracking-wide">
                            Pattern Pieces ({patternPieces.length})
                          </span>
                          <span className="text-[11px] text-slate-500 font-mono">
                            · {measurementUnit.toUpperCase()} / {areaUnit}
                          </span>
                        </div>
                        <button
                          type="button"
                          disabled={savingMappedPieces || patternPieces.length === 0}
                          onClick={handleSaveMappedPieces}
                          className="bg-emerald-700 hover:bg-emerald-800 text-white font-bold uppercase text-[11px] py-1 px-3 border border-emerald-700 shadow-ind flex items-center gap-1.5 disabled:opacity-50"
                          title="Save mapped pieces to Digital Folders (03 Upper, 03B Lining, 03C Canvas)"
                        >
                          <Save className="w-3.5 h-3.5 text-emerald-200" />
                          <span>{savingMappedPieces ? "Saving..." : "Save Mapped Components"}</span>
                        </button>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[520px] overflow-y-auto pr-1 content-start">
                        {patternPieces.map((p, idx) => {
                          const isSelected = p.piece_id === selectedPieceId;
                          return (
                            <div
                              key={p.piece_id || idx}
                              onClick={() => setSelectedPieceId(p.piece_id)}
                              className={`p-3 border-2 transition cursor-pointer ${
                                isSelected
                                  ? "border-[#C27842] bg-amber-50/40"
                                  : "border-slate-200 hover:border-slate-400 bg-white"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0 space-y-1.5">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <input
                                      type="text"
                                      value={p.piece_name}
                                      onChange={(e) =>
                                        handlePieceChange(p.piece_id, "piece_name", e.target.value)
                                      }
                                      className="font-bold text-xs text-slate-900 bg-transparent border-b border-dashed border-slate-300 focus:border-slate-900 focus:outline-none flex-1 min-w-[130px]"
                                      placeholder="Component Name"
                                    />
                                    <select
                                      value={p.component || "upper"}
                                      onChange={(e) =>
                                        handlePieceChange(p.piece_id, "component", e.target.value)
                                      }
                                      className="font-mono text-[10px] font-bold border border-slate-300 bg-white px-1.5 py-0.5 text-slate-800"
                                      title="Component Category (Folder 03 Upper / 03B Lining / 03C Canvas)"
                                    >
                                      <option value="upper">Upper Component</option>
                                      <option value="lining">Upper Lining</option>
                                      <option value="canvas_backing">Canvas Reinforcement</option>
                                    </select>
                                    <select
                                      value={p.component_type || "vamp"}
                                      onChange={(e) =>
                                        handlePieceChange(p.piece_id, "component_type", e.target.value)
                                      }
                                      className="font-mono text-[10px] border border-slate-300 bg-slate-50 px-1 py-0.5"
                                      title="Part Type"
                                    >
                                      {COMPONENT_TYPES.map((ct) => (
                                        <option key={ct.value} value={ct.value}>
                                          {ct.label}
                                        </option>
                                      ))}
                                    </select>
                                  </div>

                                  <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-slate-600">
                                    <span>L: <strong className="text-slate-900">{toDisplayLength(p.length_mm)} {measurementUnit}</strong></span>
                                    <span>·</span>
                                    <span>W: <strong className="text-slate-900">{toDisplayLength(p.width_mm)} {measurementUnit}</strong></span>
                                    <span>·</span>
                                    <span>Area: <strong className="text-[#C27842]">{toDisplayArea(p.area_sqcm)} {areaUnit}</strong></span>
                                  </div>

                                  {/* Tech Pack Material Assignment */}
                                  <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono pt-1 border-t border-slate-100">
                                    <span className="text-slate-600 font-bold uppercase flex items-center gap-1">
                                      <Layers className="w-3 h-3 text-[#C27842]" />
                                      <span>Tech Pack Material:</span>
                                    </span>
                                    <select
                                      value={p.material_id || p.material_name || ""}
                                      onChange={(e) => handlePieceMaterialChange(p.piece_id, e.target.value)}
                                      className="border border-slate-300 bg-amber-50/50 px-1.5 py-0.5 text-[10px] font-bold text-slate-800 focus:border-slate-900 max-w-[260px] truncate"
                                    >
                                      <option value="">-- Assign Tech Pack Material --</option>
                                      {techPackMaterials.length > 0 && (
                                        <optgroup label="Sample Tech Pack Materials">
                                          {techPackMaterials.map((tm, tIdx) => (
                                            <option key={`tp_${tm.material_id || tIdx}`} value={tm.material_id || tm.material_name}>
                                              {tm.placement}: {tm.material_code ? `[${tm.material_code}] ` : ""}{tm.material_name}
                                            </option>
                                          ))}
                                        </optgroup>
                                      )}
                                      {materialsList.length > 0 && (
                                        <optgroup label="All Materials Master">
                                          {materialsList.map((m) => (
                                            <option key={m.id || m._id} value={m.id || m._id}>
                                              [{m.code || "MAT"}] {m.name} ({m.material_form || "roll"})
                                            </option>
                                          ))}
                                        </optgroup>
                                      )}
                                    </select>

                                    {p.material_name && (
                                      <span className="inline-flex items-center gap-1 px-1.5 py-0.2 bg-slate-100 border border-slate-300 text-slate-700 text-[9px] font-bold rounded">
                                        {p.placement ? `${p.placement}: ` : ""}{p.material_name}
                                      </span>
                                    )}
                                  </div>

                                  {/* Stretch Cutting Direction Override */}
                                  <div className="flex items-center gap-2 text-[10px] font-mono">
                                    <span className="text-slate-500 font-bold uppercase">Cutting Stretch:</span>
                                    <select
                                      value={p.cutting_direction || "inherit"}
                                      onChange={(e) =>
                                        handlePieceChange(p.piece_id, "cutting_direction", e.target.value)
                                      }
                                      className="border border-slate-300 bg-white px-1.5 py-0.5 text-[10px]"
                                    >
                                      <option value="inherit">Use Roll Default ({cuttingDirection})</option>
                                      <option value="length_up">Length-Up (No Length Stretch)</option>
                                      <option value="width_up">Width-Up (Crosswise)</option>
                                      <option value="both">Both (Optimal Yield)</option>
                                    </select>
                                  </div>
                                </div>

                                <div className="shrink-0 flex items-center gap-3">
                                  <div className="text-right">
                                    <span className="text-[9px] uppercase font-bold text-slate-400 block">
                                      Per Pair:
                                    </span>
                                    <select
                                      value={p.pieces_per_pair || 2}
                                      onChange={(e) =>
                                        handlePieceChange(
                                          p.piece_id,
                                          "pieces_per_pair",
                                          parseInt(e.target.value) || 2
                                        )
                                      }
                                      className="font-mono text-xs font-bold border border-slate-300 bg-slate-50 px-1.5 py-0.5"
                                    >
                                      <option value="1">1 pc / pr</option>
                                      <option value="2">2 pcs (Pair)</option>
                                      <option value="4">4 pcs / pr</option>
                                      <option value="6">6 pcs / pr</option>
                                    </select>
                                  </div>

                                  <button
                                    type="button"
                                    onClick={() => handleRemovePiece(p.piece_id)}
                                    className="text-slate-400 hover:text-rose-600 p-1"
                                    title="Delete component"
                                  >
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="border-t border-slate-200 pt-3 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="text-xs font-bold uppercase tracking-wider text-slate-600 hover:text-slate-900 hover:underline"
                      >
                        Re-scan Image
                      </button>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setShowAddPieceModal(true)}
                          className="bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold uppercase text-xs py-1.5 px-3 border border-slate-300 flex items-center gap-1.5"
                        >
                          <Plus className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Add Piece</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            handleRecalculateYield();
                            setActiveTab("nesting");
                          }}
                          className="bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase text-xs py-1.5 px-4 border-2 border-[#C27842] shadow-ind flex items-center gap-2"
                        >
                          <span>Proceed to 2D Nesting</span>
                          <ArrowRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* ═══════════════════════════════════════════════════════════════════
                  REQUIREMENT 3: LACES & UNFOLDED STRIPS CALCULATOR
                  ═══════════════════════════════════════════════════════════════════ */}
              <div className="bg-white border-2 border-slate-900 p-5 space-y-4 shadow-ind">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2">
                    <Scissors className="w-4 h-4 text-[#C27842]" />
                    <div>
                      <h3 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                        Laces, Straps & Unfolded Strips (Slitted / Cross-Cut Yield)
                      </h3>
                      <p className="text-[11px] text-slate-500 font-mono">
                        Support for <strong>Folded Laces</strong> (Raw Cut = 2 × Folded Width) and <strong>Unfolded Strips</strong> (Custom Flat Width). Cut along roll length or across material width.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setStripType("folded")}
                      className={`px-2.5 py-1 text-xs font-mono font-bold uppercase transition ${
                        stripType === "folded"
                          ? "bg-slate-900 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      Folded Lace (2× Width)
                    </button>
                    <button
                      type="button"
                      onClick={() => setStripType("unfolded")}
                      className={`px-2.5 py-1 text-xs font-mono font-bold uppercase transition ${
                        stripType === "unfolded"
                          ? "bg-cyan-700 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      Unfolded Strip (Raw Width)
                    </button>
                  </div>
                </div>

                {/* Lace Input Form with Flexible Length & Width Units + Material Definition */}
                <div className="p-4 bg-slate-50 border border-slate-200 space-y-3">
                  {/* Row 1: Source Material from Material Master & Material Dimensions */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-12 gap-3 text-xs bg-white p-3 border border-slate-200">
                    <div className="md:col-span-6">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-600 flex items-center justify-between mb-1">
                        <span>Source Material (From Material Master)</span>
                        {laceMaterialRate > 0 && (
                          <span className="text-emerald-700 font-bold font-mono">Rate: ₹{laceMaterialRate}/m</span>
                        )}
                      </label>
                      <select
                        value={laceMaterialId}
                        onChange={(e) => handleSelectLaceMaterial(e.target.value)}
                        className="w-full font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                        data-testid="lace-material-select"
                      >
                        <option value="">-- Generic Roll Material --</option>
                        {materialsList.map((m) => (
                          <option key={m.id || m._id} value={m.id || m._id}>
                            {m.code ? `[${m.code}] ` : ""}{m.name} ({m.category || "material"})
                            {m.roll_width ? ` · ${m.roll_width}" Roll` : (m.material_form === "sheet" ? ` · Sheet ${m.sheet_width}"×${m.sheet_height}"` : "")}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="md:col-span-3">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-600 block mb-1">
                        Material Width ({laceMaterialWidthUnit})
                      </label>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          step="0.1"
                          min="1"
                          value={laceMaterialWidth}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value) || 0;
                            setLaceMaterialWidth(val);
                            if (stripCutOrientation === "across_width") {
                              setNewStripLengthMm(val * (laceMaterialWidthUnit === "inch" ? INCH_TO_MM : (laceMaterialWidthUnit === "cm" ? 10.0 : 1.0)));
                            }
                          }}
                          className="w-2/3 font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                          data-testid="lace-material-width"
                        />
                        <select
                          value={laceMaterialWidthUnit}
                          onChange={(e) => setLaceMaterialWidthUnit(e.target.value)}
                          className="w-1/3 font-mono text-xs p-1.5 border border-slate-300 bg-white"
                        >
                          <option value="inch">in</option>
                          <option value="mm">mm</option>
                          <option value="cm">cm</option>
                        </select>
                      </div>
                    </div>

                    <div className="md:col-span-3">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-600 block mb-1">
                        Material Length ({laceMaterialLengthUnit})
                      </label>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          step="1"
                          min="0.1"
                          value={laceMaterialLength}
                          onChange={(e) => setLaceMaterialLength(parseFloat(e.target.value) || 0)}
                          className="w-2/3 font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                          data-testid="lace-material-length"
                        />
                        <select
                          value={laceMaterialLengthUnit}
                          onChange={(e) => setLaceMaterialLengthUnit(e.target.value)}
                          className="w-1/3 font-mono text-xs p-1.5 border border-slate-300 bg-white"
                        >
                          <option value="meter">m</option>
                          <option value="yard">yd</option>
                          <option value="inch">in</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Row 2: Strip / Lace Component Specifications */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-12 gap-3 text-xs">
                    <div className="md:col-span-3">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Component Name
                      </label>
                      <input
                        type="text"
                        value={newStripName}
                        onChange={(e) => setNewStripName(e.target.value)}
                        placeholder={stripType === "unfolded" ? "e.g. Unfolded Front Strap, Piping Strip" : "e.g. Main Ankle Lace, Front Strap"}
                        className="w-full font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                        data-testid="lace-component-name"
                      />
                    </div>

                    {/* Width Definition: Folded Presets vs Unfolded User-Defined Measurement */}
                    <div className="md:col-span-3">
                      {stripType === "folded" ? (
                        <>
                          <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                            Folded Width
                          </label>
                          <select
                            value={selectedLacePreset}
                            onChange={(e) => {
                              const val = e.target.value;
                              setSelectedLacePreset(val);
                              if (val !== "custom") {
                                setNewStripFoldedWidthMm(parseFloat(val));
                              }
                            }}
                            className="w-full font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                            data-testid="lace-folded-width-select"
                          >
                            {LACE_PRESETS.map((p) => (
                              <option key={p.label} value={p.folded_mm}>
                                {p.label}
                              </option>
                            ))}
                          </select>
                          {selectedLacePreset === "0" && (
                            <div className="mt-1 flex items-center gap-1">
                              <input
                                type="number"
                                step="0.5"
                                value={newStripFoldedWidthMm}
                                onChange={(e) => setNewStripFoldedWidthMm(parseFloat(e.target.value) || 0)}
                                className="w-full font-mono text-xs p-1 border border-slate-300"
                                placeholder="Width mm"
                              />
                              <span className="text-[10px] font-mono text-slate-500">mm</span>
                            </div>
                          )}
                        </>
                      ) : (
                        <>
                          <label className="font-bold uppercase tracking-wider text-[10px] text-cyan-800 font-bold block mb-1">
                            Unfolded Strip Width (mm)
                          </label>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              step="0.5"
                              min="1"
                              value={unfoldedStripWidthMm}
                              onChange={(e) => setUnfoldedStripWidthMm(parseFloat(e.target.value) || 0)}
                              className="w-full font-mono text-xs p-1.5 border-2 border-cyan-500 bg-cyan-50/30 font-bold text-cyan-900 focus:outline-none focus:border-cyan-700"
                              placeholder="e.g. 15mm, 20mm"
                              data-testid="unfolded-strip-width-input"
                            />
                            <span className="text-[10px] font-mono text-slate-500 font-bold px-1">mm</span>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Cutting Orientation Selector: Along Length vs Across Material Width */}
                    <div className="md:col-span-2">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Cut Orientation
                      </label>
                      <select
                        value={stripCutOrientation}
                        onChange={(e) => handleOrientationChange(e.target.value)}
                        className="w-full font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                        data-testid="strip-cut-orientation-select"
                      >
                        <option value="along_length">Along Length (Slitting)</option>
                        <option value="across_width">Across Width (Cross-Cut)</option>
                      </select>
                    </div>

                    {/* Strip Length: Auto-defaulted to Material Width if Cut in Width */}
                    <div className="md:col-span-2">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Length ({newStripLengthUnit})
                      </label>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          step="10"
                          min="10"
                          value={newStripLengthMm}
                          onChange={(e) => setNewStripLengthMm(parseFloat(e.target.value) || 0)}
                          className={`w-2/3 font-mono text-xs p-1.5 border bg-white focus:outline-none ${
                            stripCutOrientation === "across_width"
                              ? "border-amber-400 bg-amber-50/40 font-bold text-amber-900"
                              : "border-slate-300"
                          }`}
                          data-testid="lace-length-input"
                        />
                        <select
                          value={newStripLengthUnit}
                          onChange={(e) => {
                            const newUnit = e.target.value;
                            setNewStripLengthUnit(newUnit);
                            if (stripCutOrientation === "across_width") {
                              setNewStripLengthMm(getSelectedMaterialWidthInLengthUnits(newUnit));
                            }
                          }}
                          className="w-1/3 font-mono text-xs p-1.5 border border-slate-300 bg-white"
                        >
                          <option value="mm">mm</option>
                          <option value="cm">cm</option>
                          <option value="inch">in</option>
                        </select>
                      </div>
                      {stripCutOrientation === "across_width" && (
                        <span className="text-[9px] text-amber-800 font-bold font-mono block mt-0.5">
                          ✓ Default: Material Width ({laceMaterialWidth}&quot;)
                        </span>
                      )}
                    </div>

                    {/* Pieces Per Pair */}
                    <div className="md:col-span-2">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Pcs / Pair
                      </label>
                      <select
                        value={newStripPcsPerPair}
                        onChange={(e) => setNewStripPcsPerPair(parseInt(e.target.value) || 2)}
                        className="w-full font-mono text-xs p-1.5 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
                      >
                        <option value="1">1 pc / pr</option>
                        <option value="2">2 pcs / pr (Pair)</option>
                        <option value="4">4 pcs / pr</option>
                        <option value="6">6 pcs / pr</option>
                      </select>
                    </div>
                  </div>

                  {/* Formula & Live 1-Meter Yield Preview */}
                  {(() => {
                    const isUnf = stripType === "unfolded";
                    const fW = parseFloat(newStripFoldedWidthMm) || 8.0;
                    const cW = isUnf ? (parseFloat(unfoldedStripWidthMm) || 15.0) : (2.0 * fW);
                    let lMm = parseFloat(newStripLengthMm) || 650.0;
                    if (newStripLengthUnit === "inch") lMm *= INCH_TO_MM;
                    if (newStripLengthUnit === "cm") lMm *= 10.0;
                    const pcs = parseInt(newStripPcsPerPair) || 2;
                    let mWMm = parseFloat(laceMaterialWidth) || 50.0;
                    if (laceMaterialWidthUnit === "inch") mWMm *= INCH_TO_MM;
                    else if (laceMaterialWidthUnit === "cm") mWMm *= 10.0;
                    let mLenM = parseFloat(laceMaterialLength) || 1.0;
                    if (laceMaterialLengthUnit === "inch") mLenM *= 0.0254;
                    else if (laceMaterialLengthUnit === "yard") mLenM *= 0.9144;

                    const usableW = Math.max(50.0, mWMm - (2 * selvageMarginMm));
                    let lanes, lacesPerM, pairsPerM;

                    if (stripCutOrientation === "across_width") {
                      const cutsPerM = Math.max(1, Math.floor(1000.0 / (cW + 1.0)));
                      const stripsPerCut = lMm >= (usableW * 0.95) ? 1 : Math.max(1, Math.floor(usableW / lMm));
                      lacesPerM = (cutsPerM * stripsPerCut).toFixed(1);
                      pairsPerM = pcs > 0 ? (parseFloat(lacesPerM) / pcs).toFixed(1) : 0;
                      lanes = cutsPerM;
                    } else {
                      lanes = Math.max(1, Math.floor((usableW + 1.0) / (cW + 1.0)));
                      lacesPerM = lMm > 0 ? ((lanes * 1000.0) / lMm).toFixed(1) : 0;
                      pairsPerM = pcs > 0 ? (parseFloat(lacesPerM) / pcs).toFixed(1) : 0;
                    }

                    const totalLaces = Math.round(parseFloat(lacesPerM) * mLenM);
                    const totalPairs = Math.round(parseFloat(pairsPerM) * mLenM);

                    return (
                      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-200 text-xs font-mono">
                        <div className="space-y-1 text-slate-700">
                          <div>
                            {isUnf ? (
                              <span>Unfolded Width: <strong className="text-cyan-700">{cW} mm</strong> (Flat / Raw)</span>
                            ) : (
                              <span>Cut Width: <strong className="text-[#C27842]">{cW} mm</strong> (2 × {fW} mm)</span>
                            )}
                            <span className="mx-1.5">·</span>
                            <span>Cut Direction: <strong className={stripCutOrientation === "across_width" ? "text-amber-800" : "text-slate-800"}>
                              {stripCutOrientation === "across_width" ? "Across Width (Cross-cut)" : "Along Length (Slitting)"}
                            </strong></span>
                            <span className="mx-1.5">·</span>
                            <span>Length: <strong>{lMm.toFixed(0)} mm</strong></span>
                          </div>
                          <div className="text-[11px] text-emerald-800 font-bold flex flex-wrap items-center gap-3">
                            <span>➔ 1 Meter: {lacesPerM} {isUnf ? "strips" : "laces"} ({pairsPerM} pairs/m)</span>
                            {mLenM > 1 && (
                              <span className="text-blue-800">· Full Roll ({mLenM}m): {totalLaces} pcs ({totalPairs} pairs)</span>
                            )}
                            {laceMaterialRate > 0 && pairsPerM > 0 && (
                              <span className="text-purple-800">· Est. Cost: ₹{((1 / pairsPerM) * laceMaterialRate).toFixed(2)}/pair</span>
                            )}
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={handleAddStandardStrip}
                          className={`font-bold uppercase text-xs py-1.5 px-3 border flex items-center gap-1.5 shadow-ind ${
                            isUnf
                              ? "bg-cyan-800 hover:bg-cyan-700 text-white border-cyan-800"
                              : "bg-slate-900 hover:bg-slate-800 text-white border-slate-900"
                          }`}
                          data-testid="add-folded-lace-btn"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>{isUnf ? "Add Unfolded Strip" : "Add Folded Lace"}</span>
                        </button>
                      </div>
                    );
                  })()}
                </div>

                {/* List of Added Standard Strips */}
                {standardStrips.length > 0 && (
                  <div className="space-y-2">
                    <span className="font-bold text-[11px] uppercase tracking-wider text-slate-600 block">
                      Active Laces & Strips ({standardStrips.length})
                    </span>
                    <div className="border border-slate-200 divide-y divide-slate-100">
                      {standardStrips.map((strip, idx) => {
                        const isUnf = strip.strip_type === "unfolded";
                        return (
                          <div key={strip.strip_id || idx} className="p-3 bg-white flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
                            <div className="flex items-center gap-3">
                              <span className={`w-6 h-6 flex items-center justify-center font-bold text-[11px] rounded ${
                                isUnf ? "bg-cyan-100 text-cyan-800" : "bg-amber-100 text-[#C27842]"
                              }`}>
                                {idx + 1}
                              </span>
                              <div className="space-y-0.5">
                                <div className="flex items-center gap-2">
                                  <span className="font-bold text-slate-900">{strip.name}</span>
                                  <span className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase ${
                                    isUnf ? "bg-cyan-100 text-cyan-900 border border-cyan-300" : "bg-amber-100 text-amber-900 border border-amber-300"
                                  }`}>
                                    {isUnf ? "Unfolded Strip" : "Folded Lace"}
                                  </span>
                                  <span className="text-[9px] px-1.5 py-0.2 rounded font-bold bg-slate-100 text-slate-700 border border-slate-200">
                                    {strip.cut_orientation === "across_width" ? "Cross-Cut (Across Width)" : "Slitted (Along Length)"}
                                  </span>
                                  {strip.material_name && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200">
                                      Mat: {strip.material_code ? `[${strip.material_code}] ` : ""}{strip.material_name}
                                    </span>
                                  )}
                                </div>
                                <span className="text-[11px] text-slate-500 block">
                                  {isUnf ? (
                                    <>Unfolded Width: <strong className="text-cyan-800">{strip.cut_width_mm}mm</strong></>
                                  ) : (
                                    <>Folded: {strip.folded_width_mm}mm · Raw Cut: <strong className="text-amber-800">{strip.cut_width_mm}mm</strong></>
                                  )}
                                  <span> · Length: {strip.length_mm}mm · Pcs: {strip.pieces_per_pair}</span>
                                  {strip.material_width && (
                                    <span className="ml-2 text-slate-700">· Roll: {strip.material_width}&quot;W × {strip.material_length_meters || 1}mL</span>
                                  )}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-5">
                              <div className="text-right">
                                <span className="text-slate-500 text-[10px] block">Yield (1 Meter):</span>
                                <span className="font-black text-emerald-700">
                                  {strip.laces_yield_per_meter || "-"} {isUnf ? "strips" : "laces"}/m
                                </span>
                                <span className="text-[10px] text-slate-500 block">
                                  ({strip.pairs_per_meter || strip.yield_per_unit || "-"} prs/m)
                                  {strip.total_laces_full_roll > 0 && strip.material_length_meters > 1 && (
                                    <span className="text-blue-700 ml-1">· Full: {strip.total_laces_full_roll} pcs</span>
                                  )}
                                </span>
                              </div>

                              <button
                                type="button"
                                onClick={() => handleRemoveStandardStrip(strip.strip_id)}
                                className="text-slate-400 hover:text-rose-600 p-1"
                                title="Remove component"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Standard Factory Presets (Insole & Bottom Covering) */}
              <div className="bg-white border-2 border-slate-900 p-5 space-y-4 shadow-ind">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2">
                    <Bookmark className="w-4 h-4 text-emerald-600" />
                    <div>
                      <h3 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                        Standard Factory Presets (Insole & Bottom Covering)
                      </h3>
                      <p className="text-[11px] text-slate-500 font-mono">
                        Regular die-cut insole board and bottom covering have fixed factory standards — no scanning needed.
                      </p>
                    </div>
                  </div>

                  <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold">
                    Factory Locked Presets
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                  {factoryPresets.map((preset, idx) => (
                    <div
                      key={preset.component || idx}
                      className={`p-3.5 border-2 transition ${
                        preset.active
                          ? "border-emerald-600 bg-emerald-50/40 shadow-sm"
                          : "border-slate-200 bg-slate-50/50 opacity-75"
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <span className="font-bold text-xs text-slate-900 block">{preset.name}</span>
                          <span className="text-[10px] text-slate-500 font-mono block mt-0.5">{preset.sheet_spec}</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={preset.active}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setFactoryPresets((prev) =>
                              prev.map((p, i) => (i === idx ? { ...p, active: checked } : p))
                            );
                          }}
                          className="h-4 w-4 accent-emerald-600 cursor-pointer"
                        />
                      </div>

                      <div className="mt-3 pt-2 border-t border-slate-200 flex items-center justify-between text-xs font-mono">
                        <div>
                          <span className="text-[10px] uppercase text-slate-500 block">Factory Yield:</span>
                          <span className="font-black text-emerald-800 text-sm">
                            {preset.standard_yield} {preset.yield_unit}
                          </span>
                        </div>

                        <div className="text-right">
                          <span className="text-[10px] uppercase text-slate-500 block">Consumption:</span>
                          <span className="font-bold text-slate-900">
                            {preset.standard_consumption} {preset.consumption_unit}/pr
                          </span>
                        </div>
                      </div>

                      <p className="text-[10px] text-slate-500 italic mt-2 border-t border-dashed border-slate-200 pt-1">
                        {preset.note}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════
              TAB 2: 2D NESTING, ROLL SIZING & CUTTING DIRECTION / STRETCH CONTROL
              ═══════════════════════════════════════════════════════════════════ */}
          {activeTab === "nesting" && (
            <div className="space-y-5">
              
              {/* REQUIREMENT 2: CUTTING DIRECTION & MATERIAL STRETCH PHYSICS CARD */}
              <div className="bg-slate-900 text-white p-4 border-2 border-slate-900 shadow-ind space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700 pb-2.5">
                  <div className="flex items-center gap-2">
                    <ArrowUpDown className="w-4 h-4 text-amber-400" />
                    <div>
                      <h3 className="font-bold text-xs uppercase tracking-wider text-white">
                        Synthetic Roll Stretch Physics & Cutting Grain Direction
                      </h3>
                      <p className="text-[11px] text-slate-300 font-mono">
                        Synthetic material <strong>stretches across width</strong> and <strong>does not stretch along length</strong>.
                      </p>
                    </div>
                  </div>

                  <span className="text-[10px] font-mono px-2 py-0.5 bg-indigo-900 text-indigo-200 border border-indigo-500 font-bold">
                    Footwear Grain Control
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-mono">
                  {/* Option 1: Length-Up (Default) */}
                  <div
                    onClick={() => setCuttingDirection("length_up")}
                    className={`p-3 border-2 cursor-pointer transition ${
                      cuttingDirection === "length_up"
                        ? "border-amber-400 bg-amber-950/40 text-white"
                        : "border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-amber-300 flex items-center gap-1.5">
                        <ArrowUpDown className="w-4 h-4 text-amber-400" />
                        <span>Length-Up (Default)</span>
                      </span>
                      <span className="text-[9px] px-1 bg-amber-400/20 text-amber-200 rounded font-bold">Recommended</span>
                    </div>
                    <p className="text-[11px] text-slate-300 mt-2">
                      Piece length aligned along roll length (Warp). <strong>No length stretch</strong> when shoe is worn on foot.
                    </p>
                  </div>

                  {/* Option 2: Width-Up (Crosswise) */}
                  <div
                    onClick={() => setCuttingDirection("width_up")}
                    className={`p-3 border-2 cursor-pointer transition ${
                      cuttingDirection === "width_up"
                        ? "border-amber-400 bg-amber-950/40 text-white"
                        : "border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-amber-300 flex items-center gap-1.5">
                        <ArrowLeftRight className="w-4 h-4 text-cyan-400" />
                        <span>Crosswise / Width</span>
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-300 mt-2">
                      Piece length placed across roll width. Stretches along length of shoe if cross-stretch is required.
                    </p>
                  </div>

                  {/* Option 3: Both Directions (Optimal Yield) */}
                  <div
                    onClick={() => setCuttingDirection("both")}
                    className={`p-3 border-2 cursor-pointer transition ${
                      cuttingDirection === "both"
                        ? "border-amber-400 bg-amber-950/40 text-white"
                        : "border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-amber-300 flex items-center gap-1.5">
                        <RotateCw className="w-4 h-4 text-emerald-400" />
                        <span>Both Directions (2-Way)</span>
                      </span>
                      <span className="text-[9px] px-1 bg-emerald-400/20 text-emerald-200 rounded font-bold">Max Yield</span>
                    </div>
                    <p className="text-[11px] text-slate-300 mt-2">
                      Free 2-way interlocking rotation for maximum material savings when stretch direction is not critical.
                    </p>
                  </div>
                </div>
              </div>

              {/* REQUIREMENT 1: ROLL WIDTH & FULL ROLL LENGTH CONTROL */}
              <div className="bg-white border-2 border-slate-900 p-4 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2">
                    <Grid className="w-4 h-4 text-[#C27842]" />
                    <span className="font-bold text-xs uppercase tracking-wider text-slate-900">
                      Material Cutting & Sizing Controls
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setMaterialType("roll")}
                      className={`px-3 py-1 text-xs font-bold uppercase tracking-wider border-2 transition ${
                        materialType === "roll"
                          ? "border-[#C27842] bg-[#C27842] text-white"
                          : "border-slate-300 text-slate-700 hover:border-slate-600"
                      }`}
                    >
                      Continuous Roll (Rexine / Synthetic)
                    </button>
                    <button
                      type="button"
                      onClick={() => setMaterialType("sheet")}
                      className={`px-3 py-1 text-xs font-bold uppercase tracking-wider border-2 transition ${
                        materialType === "sheet"
                          ? "border-[#C27842] bg-[#C27842] text-white"
                          : "border-slate-300 text-slate-700 hover:border-slate-600"
                      }`}
                    >
                      Standard Sheet (EVA / Board)
                    </button>
                  </div>
                </div>

                {/* Sizing Controls Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-12 gap-3 text-xs">
                  {/* Raw Material Inventory Item */}
                  <div className="md:col-span-3">
                    <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                      Raw Material Item
                    </label>
                    <select
                      value={selectedMaterialId}
                      onChange={(e) => {
                        applyMaterialDimensions(e.target.value);
                      }}
                      className="w-full font-mono text-xs p-1.5 border-2 border-slate-300 bg-white focus:border-slate-900 focus:outline-none"
                    >
                      <option value="">-- Custom Material Specification --</option>
                      {materialsList.map((m) => (
                        <option key={m.id || m._id} value={m.id || m._id}>
                          {m.code ? `[${m.code}] ` : ""}{m.name} ({m.category || "Material"})
                          {m.material_form === "roll" && m.roll_width ? ` · ${m.roll_width}" Roll` : (m.material_form === "sheet" && m.sheet_width ? ` · Sheet ${m.sheet_width}"×${m.sheet_height}"` : "")}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Roll Width Control (Presets + Custom) */}
                  {materialType === "roll" ? (
                    <div className="md:col-span-3">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Continuous Roll Width
                      </label>
                      <select
                        value={rollWidthPreset}
                        onChange={(e) => setRollWidthPreset(e.target.value)}
                        className="w-full font-mono text-xs p-1.5 border-2 border-slate-300 bg-white focus:border-slate-900 focus:outline-none"
                      >
                        {ROLL_WIDTH_PRESETS.map((p) => (
                          <option key={p.label} value={p.inches === 0 ? "custom" : p.inches}>
                            {p.label}
                          </option>
                        ))}
                      </select>

                      {rollWidthPreset === "custom" && (
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <input
                            type="number"
                            value={customRollWidthMm}
                            onChange={(e) => setCustomRollWidthMm(parseFloat(e.target.value) || 0)}
                            className="w-2/3 font-mono text-xs p-1 border-2 border-slate-300"
                            placeholder="Custom Width"
                          />
                          <span className="text-[10px] font-mono font-bold text-slate-600">mm ({toDisplayLength(customRollWidthMm)} {measurementUnit})</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="md:col-span-3">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Sheet Dimensions L × W (mm)
                      </label>
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          value={sheetLengthMm}
                          onChange={(e) => setSheetLengthMm(e.target.value)}
                          className="w-1/2 font-mono text-xs p-1.5 border-2 border-slate-300"
                          placeholder="1524"
                        />
                        <span>×</span>
                        <input
                          type="number"
                          value={sheetWidthMm}
                          onChange={(e) => setSheetWidthMm(e.target.value)}
                          className="w-1/2 font-mono text-xs p-1.5 border-2 border-slate-300"
                          placeholder="1016"
                        />
                      </div>
                    </div>
                  )}

                  {/* Roll Length Control (Presets + Custom) */}
                  {materialType === "roll" && (
                    <div className="md:col-span-2">
                      <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                        Roll Length
                      </label>
                      <select
                        value={rollLengthPreset}
                        onChange={(e) => setRollLengthPreset(e.target.value)}
                        className="w-full font-mono text-xs p-1.5 border-2 border-slate-300 bg-white focus:border-slate-900 focus:outline-none"
                      >
                        {ROLL_LENGTH_PRESETS.map((p) => (
                          <option key={p.label} value={p.meters === 0 ? "custom" : p.meters}>
                            {p.label}
                          </option>
                        ))}
                      </select>

                      {rollLengthPreset === "custom" && (
                        <div className="mt-1 flex items-center gap-1">
                          <input
                            type="number"
                            min="1"
                            value={customRollLengthMeters}
                            onChange={(e) => setCustomRollLengthMeters(parseFloat(e.target.value) || 1)}
                            className="w-full font-mono text-xs p-1 border border-slate-300"
                            placeholder="Length (m)"
                          />
                          <span className="text-[10px] font-mono">m</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Selvage Margin (Edge Waste Control) */}
                  <div className="md:col-span-1">
                    <label className="font-bold uppercase tracking-wider text-[10px] text-amber-800 block mb-1 flex items-center justify-between" title="Edge waste margin on each side in mm">
                      <span>Selvage</span>
                      <span className="text-[9px] font-mono text-slate-400">edge</span>
                    </label>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        value={selvageMarginMm}
                        onChange={(e) => setSelvageMarginMm(parseFloat(e.target.value) || 0)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRecalculateYield();
                        }}
                        className="w-full font-mono text-xs p-1.5 border-2 border-amber-300 bg-amber-50/30 focus:border-slate-900 focus:outline-none font-bold"
                        placeholder="20"
                        data-testid="selvage-margin-input"
                        title="Selvage edge margin in mm (e.g. 0, 10, 20mm). Press Enter or click Run to apply."
                      />
                      <span className="text-[9px] font-mono text-slate-500">mm</span>
                    </div>
                    <div className="flex items-center gap-1 mt-1">
                      {[0, 10, 20].map((val) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => {
                            setSelvageMarginMm(val);
                          }}
                          className={`text-[9px] px-1 py-0.5 border font-mono rounded transition ${
                            Number(selvageMarginMm) === val
                              ? "bg-slate-900 text-white border-slate-900 font-bold"
                              : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                          }`}
                          title={`Set Selvage margin to ${val}mm`}
                        >
                          {val}m
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Blade Kerf Spacing */}
                  <div className="md:col-span-1">
                    <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1" title="Cutting die blade clearance spacing in mm">
                      Kerf
                    </label>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min="0.5"
                        max="20"
                        step="0.5"
                        value={kerfSpacingMm}
                        onChange={(e) => setKerfSpacingMm(parseFloat(e.target.value) || 2.5)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRecalculateYield();
                        }}
                        className="w-full font-mono text-xs p-1.5 border-2 border-slate-300 bg-white focus:border-slate-900 focus:outline-none"
                        placeholder="3"
                        data-testid="kerf-spacing-input"
                        title="Blade kerf clearance between pieces in mm (e.g. 2, 3mm). Press Enter or click Run to apply."
                      />
                      <span className="text-[9px] font-mono text-slate-500">mm</span>
                    </div>
                  </div>

                  {/* Scrap Buffer & Recalculate Trigger */}
                  <div className="md:col-span-2">
                    <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                      Scrap & Run
                    </label>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="number"
                        min="0"
                        max="25"
                        value={wasteAllowancePct}
                        onChange={(e) => setWasteAllowancePct(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRecalculateYield();
                        }}
                        className="w-14 font-mono text-xs p-1.5 border-2 border-slate-300"
                        placeholder="5%"
                        title="Waste allowance buffer %"
                      />
                      <button
                        type="button"
                        disabled={calculating}
                        onClick={handleRecalculateYield}
                        className="bg-slate-900 hover:bg-slate-800 text-white font-bold uppercase text-xs py-1.5 px-3 border-2 border-slate-900 shadow-ind flex items-center gap-1 disabled:opacity-50 flex-1 justify-center"
                        title="Recalculate 2D Nesting with updated selvage margin & sizing"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${calculating ? "animate-spin" : ""}`} />
                        <span>Run</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Yield Scorecard Strip (Displays Active Selected Component Metrics) */}
              {yieldSpec && (() => {
                const dispYield = activeComponent ? activeComponent.yield_per_unit : yieldSpec.yield_per_unit;
                const dispUnitLabel = activeComponent
                  ? (activeComponent.yield_unit_label || (activeComponent.consumption_unit === "sheet" ? "prs/sheet" : "prs/meter"))
                  : (yieldSpec.yield_unit_label || "prs/m");
                const dispCons = activeComponent ? activeComponent.consumption_per_pair : yieldSpec.consumption_per_pair;
                const dispConsUnit = activeComponent ? (activeComponent.consumption_unit || "meter") : yieldSpec.consumption_unit;
                const dispUtil = activeComponent ? (activeComponent.utilization_pct || yieldSpec.utilization_pct) : yieldSpec.utilization_pct;
                const dispWaste = activeComponent ? (activeComponent.waste_pct || yieldSpec.waste_pct) : yieldSpec.waste_pct;
                const dispPairsRoll = activeComponent
                  ? (activeComponent.total_pairs_per_roll || Math.round(effectiveRollLengthMeters / (dispCons || 0.14)))
                  : (yieldSpec.total_pairs_per_roll || Math.round(effectiveRollLengthMeters / (dispCons || 0.14)));
                const titleLabel = activeComponent ? `${activeComponent.name} Yield` : "Component Yield per Unit";

                return (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
                    <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                      <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider block">
                        {titleLabel}
                      </span>
                      <div className="flex items-baseline gap-1.5 mt-0.5">
                        <span className="text-2xl font-black text-[#C27842] font-mono">
                          {dispYield}
                        </span>
                        <span className="text-xs font-mono text-slate-600 font-bold">
                          {dispUnitLabel}
                        </span>
                      </div>
                    </div>

                    <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                      <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider block">
                        Consumption / Pair
                      </span>
                      <div className="flex items-baseline gap-1.5 mt-0.5">
                        <span className="text-2xl font-black text-slate-900 font-mono">
                          {dispCons}
                        </span>
                        <span className="text-xs font-mono text-slate-600 font-bold">
                          {dispConsUnit}
                        </span>
                      </div>
                    </div>

                    <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                      <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider block">
                        Full Roll Total Pairs
                      </span>
                      <div className="flex items-baseline gap-1.5 mt-0.5">
                        <span className="text-2xl font-black text-indigo-700 font-mono">
                          {dispPairsRoll}
                        </span>
                        <span className="text-xs font-mono text-slate-600 font-bold">
                          pairs / {effectiveRollLengthMeters}m roll
                        </span>
                      </div>
                    </div>

                    <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                      <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider block">
                        Cutting Efficiency
                      </span>
                      <div className="flex items-baseline gap-1.5 mt-0.5">
                        <span className="text-2xl font-black text-emerald-600 font-mono">
                          {dispUtil}%
                        </span>
                        <span className="text-xs font-mono text-slate-500">usable ({dispWaste}% scrap)</span>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* 2D Interactive Nesting Canvas: ONLY SELECTED COMPONENT MAPPED */}
              {(activeComponent?.visual_nesting_preview || yieldSpec?.visual_nesting_preview) && (() => {
                const prev = activeComponent?.visual_nesting_preview || yieldSpec?.visual_nesting_preview;
                const canvasW = prev?.canvas_width_mm || 1371.6;
                const canvasH = prev?.canvas_height_mm || 1000.0;
                const rawPlaced = prev?.placed_items || [];

                // Strictly show ONLY pieces of the active selected component on its dedicated roll
                const placed = (activeComponent?.visual_nesting_preview?.placed_items?.length > 0)
                  ? activeComponent.visual_nesting_preview.placed_items
                  : rawPlaced;

                return (
                  <div className="bg-white border-2 border-slate-900 p-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs uppercase tracking-wide text-slate-900">
                          2D Cutting Layout across {toDisplayLength(effectiveRollWidthMm)} {measurementUnit} Width
                        </span>
                        <span className="text-[11px] font-mono text-indigo-800 font-bold">
                          (Grain: {cuttingDirection.replace("_", "-").toUpperCase()})
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setPreviewZoom((z) => Math.max(0.6, z - 0.2))}
                          className="p-1 border border-slate-300 hover:bg-slate-100 text-slate-700"
                          title="Zoom Out"
                        >
                          <ZoomOut className="w-3.5 h-3.5" />
                        </button>
                        <span className="text-[10px] font-mono px-1">{Math.round(previewZoom * 100)}%</span>
                        <button
                          type="button"
                          onClick={() => setPreviewZoom((z) => Math.min(2.0, z + 0.2))}
                          className="p-1 border border-slate-300 hover:bg-slate-100 text-slate-700"
                          title="Zoom In"
                        >
                          <ZoomIn className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Component Category Dropdown & Mapped Piece Chips below */}
                    <div className="bg-slate-50 border-2 border-slate-900 p-3 space-y-2.5 shadow-2xs">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <Layers className="w-4 h-4 text-[#C27842]" />
                          <span className="font-bold text-xs uppercase tracking-wide text-slate-900">
                            Select Component Category to Map on Roll:
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          <select
                            value={selectedComponentCategory}
                            onChange={(e) => setSelectedComponentCategory(e.target.value)}
                            className="font-mono text-xs font-bold border-2 border-slate-900 bg-white px-3 py-1.5 focus:border-[#C27842] focus:outline-none cursor-pointer"
                          >
                            <option value="upper">
                              Upper Component {upperSpec.upper_top_material_name ? `[${upperSpec.upper_top_material_name}]` : ""}
                            </option>
                            {hasLining && (
                              <option value="lining">
                                Upper Lining {liningName ? `[${liningName}]` : ""}
                              </option>
                            )}
                            {hasCanvas && (
                              <option value="canvas_backing">
                                Canvas / Reinforcement Backing {canvasName ? `[${canvasName}]` : ""}
                              </option>
                            )}
                            {standardStrips.length > 0 && (
                              <option value="strips">
                                Folded Laces & Strips ({standardStrips.length} components)
                              </option>
                            )}
                          </select>
                        </div>
                      </div>

                      {/* Mapped Pieces for the Selected Component Category */}
                      <div className="space-y-1.5 pt-1 border-t border-slate-200">
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="uppercase font-bold text-slate-500">
                            Mapped Pieces ({selectedComponentCategory.replace("_", " ").toUpperCase()}):
                          </span>
                          <span className="text-slate-500">
                            {categoryPieces.length} piece{categoryPieces.length !== 1 ? "s" : ""} available
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center gap-1.5">
                          {categoryPieces.length > 0 ? (
                            categoryPieces.map((comp, idx) => {
                              const isSelected = comp.key === selectedComponentKey;
                              const isStrip = comp.type === "folded_lace" || comp.type === "unfolded_strip" || comp.type === "strip";
                              const piecePrefix = comp.type === "pattern_piece" ? `Piece ${idx + 1}: ` : isStrip ? `Lace ${idx + 1}: ` : "";
                              return (
                                <button
                                  key={comp.key}
                                  type="button"
                                  onClick={() => setSelectedComponentKey(comp.key)}
                                  className={`px-2.5 py-1 text-[11px] font-mono font-bold border transition flex items-center gap-1.5 ${
                                    isSelected
                                      ? "bg-slate-900 text-white border-slate-900 shadow-xs"
                                      : "bg-white text-slate-700 border-slate-300 hover:border-slate-500 hover:bg-slate-50"
                                  }`}
                                >
                                  <span
                                    className="w-2 h-2 rounded-full shrink-0"
                                    style={{
                                      backgroundColor:
                                        comp.color ||
                                        (selectedComponentCategory === "lining"
                                          ? "#10b981"
                                          : selectedComponentCategory === "canvas_backing"
                                          ? "#f59e0b"
                                          : isStrip
                                          ? "#f97316"
                                          : "#3b82f6"),
                                    }}
                                  />
                                  <span>{piecePrefix}{comp.name?.split("(")[0]?.trim() || comp.name}</span>
                                  <span
                                    className={`text-[9px] px-1 py-0.2 rounded font-semibold ${
                                      isSelected ? "bg-slate-800 text-amber-300" : "bg-slate-100 text-slate-600"
                                    }`}
                                  >
                                    {comp.yield_per_unit} {comp.yield_unit_label || "prs/m"}
                                  </span>
                                </button>
                              );
                            })
                          ) : (
                            <span className="text-[11px] font-mono text-slate-500 italic">
                              No pieces scanned for {selectedComponentCategory.replace("_", " ")} yet. Scan sheet in Stage 1.
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Active Component Details Strip */}
                      {activeComponent && (
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200 text-xs font-mono">
                          <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: activeComponent.color || "#3b82f6" }} />
                            <span className="font-bold text-slate-900">{activeComponent.name}</span>
                            <span className="text-slate-500">
                              · Material: <strong>{activeComponent.material_name}</strong>
                              {activeComponent.pieces_per_pair ? ` · ${activeComponent.pieces_per_pair} pcs/pr` : ""}
                              {activeComponent.area_sqcm ? ` · ${toDisplayArea(activeComponent.area_sqcm)} ${areaUnit}` : ""}
                            </span>
                          </div>
                          <span className="px-2 py-0.5 bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold text-[10px]">
                            ✓ Single Component Mapped (Zero Mixing)
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Roll Width Utilization Metric Bar */}
                    {(() => {
                      const widthUtilPct = prev?.width_utilization_pct || activeComponent?.utilization_pct || yieldSpec?.utilization_pct || 92.0;

                      return (
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono bg-slate-50 border border-slate-200 px-3 py-1.5">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-700">Roll Usable Width Utilization:</span>
                            <span className="font-extrabold text-indigo-700 text-sm">{widthUtilPct}%</span>
                            <span className="text-slate-400">· Edge-to-Edge Packed across {toDisplayLength(canvasW)} {measurementUnit}</span>
                          </div>
                          <div className="w-36 bg-slate-200 h-2.5 overflow-hidden border border-slate-300">
                            <div className="bg-indigo-600 h-full transition-all" style={{ width: `${Math.min(100, widthUtilPct)}%` }} />
                          </div>
                        </div>
                      );
                    })()}

                    {/* SVG Material Canvas: Renders ONLY the selected component's preview */}
                    <div className="overflow-x-auto bg-slate-100 border border-slate-300 p-3 flex justify-center">
                      <div
                        style={{
                          transform: `scale(${previewZoom})`,
                          transformOrigin: "top center",
                          transition: "transform 0.15s ease",
                        }}
                        className="bg-white shadow-md border border-slate-400"
                      >
                        <svg
                          width={Math.min(960, canvasW * 0.7)}
                          height={Math.min(500, canvasH * 0.7)}
                          viewBox={`0 0 ${canvasW} ${canvasH}`}
                          className="bg-amber-50/20"
                        >
                          <defs>
                            <pattern id="selvageHatch" width="10" height="10" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
                              <line x1="0" y1="0" x2="0" y2="10" stroke="#fca5a5" strokeWidth="2" />
                            </pattern>
                          </defs>

                          <rect x="0" y="0" width={canvasW} height={canvasH} fill="#fafaf9" stroke="#cbd5e1" strokeWidth="1" />

                          {/* Selvage Margins */}
                          {prev?.selvage_left_w && (
                            <rect
                              x="0"
                              y="0"
                              width={prev.selvage_left_w}
                              height={canvasH}
                              fill="url(#selvageHatch)"
                              stroke="#f87171"
                              strokeWidth="0.5"
                            />
                          )}
                          {prev?.selvage_right_x && (
                            <rect
                              x={prev.selvage_right_x}
                              y="0"
                              width={prev.selvage_right_w}
                              height={canvasH}
                              fill="url(#selvageHatch)"
                              stroke="#f87171"
                              strokeWidth="0.5"
                            />
                          )}

                          {/* Placed Items (Zero Overlap & Isolated to Selected Component) */}
                          {placed.map((item, idx) => (
                            <g
                              key={idx}
                              transform={`translate(${item.x_mm}, ${item.y_mm})`}
                            >
                              {item.svg_path || item.svg_polygon ? (
                                <path
                                  d={item.svg_path || item.svg_polygon}
                                  fill={item.color || activeComponent?.color || "#3b82f6"}
                                  fillOpacity="0.75"
                                  stroke="#1e293b"
                                  strokeWidth="0.8"
                                />
                              ) : (
                                <rect
                                  x="0"
                                  y="0"
                                  width={item.w_mm}
                                  height={item.h_mm}
                                  rx="2"
                                  fill={item.color || activeComponent?.color || "#3b82f6"}
                                  fillOpacity="0.75"
                                  stroke="#1e293b"
                                  strokeWidth="0.8"
                                />
                              )}
                              {item.w_mm >= 30 && item.h_mm >= 20 && (
                                <text
                                  x={item.w_mm / 2}
                                  y={item.h_mm / 2 + 1.5}
                                  textAnchor="middle"
                                  fill="#0f172a"
                                  fontSize={Math.max(3, Math.min(5.5, item.w_mm / 10))}
                                  fontWeight="bold"
                                  fontFamily="monospace"
                                  pointerEvents="none"
                                >
                                  {item.piece_name?.slice(0, 10)}
                                </text>
                              )}
                            </g>
                          ))}
                        </svg>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[11px] font-mono text-slate-500">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex items-center gap-1 bg-amber-50 px-2 py-0.5 border border-amber-300 rounded text-amber-900 font-medium" title="Control this using the Selvage input in the toolbar above">
                          <span>Selvage Edge Waste:</span>
                          <strong className="text-slate-900 font-bold">{selvageMarginMm}mm</strong> (each side)
                        </span>
                        <span className="inline-flex items-center gap-1 bg-slate-100 px-2 py-0.5 border border-slate-300 rounded text-slate-800" title="Control this using the Kerf input in the toolbar above">
                          <span>Blade Kerf:</span>
                          <strong className="text-slate-900 font-bold">{kerfSpacingMm}mm</strong>
                        </span>
                        <span>Direction: <strong>{cuttingDirection}</strong></span>
                        <span>Total Placed: <strong>{placed.length} pieces ({activeComponent?.name || "Selected Component"})</strong></span>
                      </div>

                      <button
                        type="button"
                        onClick={() => setActiveTab("bom")}
                        className="bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase text-xs py-1.5 px-3 border border-[#C27842] flex items-center gap-1.5"
                      >
                        <span>Proceed to BOM</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════════════
              TAB 3: STYLE MASTER BOM & PLM ARCHIVAL
              ═══════════════════════════════════════════════════════════════════ */}
          {activeTab === "bom" && (
            <div className="space-y-5">
              <div className="bg-emerald-50 border-2 border-emerald-300 p-4 flex items-start gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                <div className="text-xs text-emerald-900 space-y-1">
                  <p className="font-bold uppercase tracking-wide">
                    Ready for Style Master Bill of Materials (BOM) & Digital Style Folder
                  </p>
                  <p className="text-emerald-800">
                    Calibrated upper yields, linear laces slitting formulas, and standard factory presets are ready to populate Style Master BOM upon sample approval.
                  </p>
                </div>
              </div>

              {/* Proposed BOM Lines & Side Scorecard Grid */}
              <div className="space-y-3">
                <span className="font-bold text-xs uppercase tracking-wider text-slate-900 block">
                  Calibrated BOM Injection Items & Overall Material Footprint
                </span>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                  {/* LEFT AREA: Detailed Component Lines (8 Cols) */}
                  <div className="lg:col-span-8 space-y-4">
                    {/* Multi-Material Breakdown Lines from Tech Pack */}
                    {Array.isArray(yieldSpec?.material_breakdown) && yieldSpec.material_breakdown.length > 0 ? (
                      yieldSpec.material_breakdown.map((mb, mIdx) => {
                        const mbPrev = mb.visual_nesting_preview || yieldSpec?.visual_nesting_preview;
                        const mbItems = mbPrev?.placed_items || [];
                        const mbCanvasW = mbPrev?.canvas_width_mm || 1371.6;
                        const mbCanvasH = mbPrev?.canvas_height_mm || 600.0;
                        const mbColor = mb.is_lining ? "#10b981" : mb.is_canvas ? "#f59e0b" : "#3b82f6";

                        return (
                          <div key={mIdx} className="bg-white border-2 border-slate-900 p-4 space-y-3 shadow-ind">
                            <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                              <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: mbColor }} />
                                <span>1.{mIdx + 1} {mb.placement || (mb.is_lining ? "Upper Lining" : mb.is_canvas ? "Canvas Backing" : "Upper Top Material")}: {mb.material_name}</span>
                              </span>
                              <span className="text-[10px] font-mono px-2 py-0.5 bg-amber-100 text-amber-900 font-bold border border-amber-300">
                                {mb.pieces_count} pieces ({mb.consumption_unit})
                              </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
                              {/* Left Column: Yield Calculated Metrics */}
                              <div className="md:col-span-7 text-xs font-mono space-y-1.5 text-slate-700">
                                <p>Material: <strong>{mb.material_code ? `[${mb.material_code}] ` : ""}{mb.material_name}</strong></p>
                                <p>Net Area per Pair: <strong>{toDisplayArea(mb.net_area_sqcm_per_pair)} {areaUnit}</strong></p>
                                <div className="p-2.5 bg-slate-50 border border-slate-200 space-y-1.5 rounded-xs">
                                  <div className="flex items-center justify-between">
                                    <span className="text-slate-500">Calibrated Consumption:</span>
                                    <strong className="text-[#C27842] text-sm">{mb.consumption_per_pair} {mb.consumption_unit} / pair</strong>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span className="text-slate-500">Calibrated Yield:</span>
                                    <strong className="text-emerald-700 text-sm">{mb.yield_per_unit} {mb.yield_unit_label}</strong>
                                  </div>
                                  <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-200">
                                    <span className="text-slate-500">Cutting Efficiency:</span>
                                    <strong className="text-slate-900">{mb.utilization_pct}% ({mb.waste_pct}% scrap waste)</strong>
                                  </div>
                                </div>
                              </div>

                              {/* Right Column: Traced Photo of the Pattern / Pieces */}
                              {(() => {
                                const mappedPieces = (patternPieces || []).filter((p) => {
                                  if (mb.is_lining) {
                                    return (
                                      p.component_type === "lining" ||
                                      p.placement?.toLowerCase().includes("lining") ||
                                      p.piece_id?.startsWith("lin_") ||
                                      p.piece_name?.toLowerCase().includes("lining") ||
                                      (mb.material_name && p.material_name === mb.material_name)
                                    );
                                  }
                                  if (mb.is_canvas) {
                                    return (
                                      p.component_type === "canvas" ||
                                      p.component_type === "canvas_backing" ||
                                      p.placement?.toLowerCase().includes("canvas") ||
                                      p.piece_id?.startsWith("cv_") ||
                                      p.piece_name?.toLowerCase().includes("canvas") ||
                                      (mb.material_name && p.material_name === mb.material_name)
                                    );
                                  }
                                  return (
                                    !p.piece_name?.toLowerCase().includes("canvas") &&
                                    !p.piece_id?.startsWith("cv_") &&
                                    !p.piece_name?.toLowerCase().includes("lining") &&
                                    !p.piece_id?.startsWith("lin_") &&
                                    ((mb.material_id && p.material_id === mb.material_id) ||
                                     (mb.material_name && p.material_name === mb.material_name) ||
                                     (mb.placement && p.placement === mb.placement) ||
                                     (!mb.material_id && !mb.material_name))
                                  );
                                });
                                const piecesToRender = mappedPieces.length > 0
                                  ? mappedPieces
                                  : (mb.pieces && mb.pieces.length > 0 ? mb.pieces : (patternPieces || []));

                                const photoUrl = getSafePhotoUrl(
                                  mb.is_canvas
                                    ? (sample?.canvas_scan_url || sample?.canvas_scan_photo?.display_url || sample?.canvas_scan_photo?.url || scanUrl)
                                    : mb.is_lining
                                    ? (sample?.lining_scan_url || sample?.lining_scan_photo?.display_url || sample?.pattern_scan_photo?.display_url || sample?.pattern_scan_url || scanUrl)
                                    : (sample?.pattern_scan_photo?.display_url || sample?.pattern_scan_url || scanUrl)
                                );

                                const validBoxes = piecesToRender.map((p) => p.bbox_page).filter(Boolean);
                                const hasBoxes = validBoxes.length > 0;
                                const pad = 6;
                                const minX = hasBoxes ? Math.max(0, Math.min(...validBoxes.map((b) => b.x_mm)) - pad) : 0;
                                const minY = hasBoxes ? Math.max(0, Math.min(...validBoxes.map((b) => b.y_mm)) - pad) : 0;
                                const maxX = hasBoxes ? Math.min(210, Math.max(...validBoxes.map((b) => b.x_mm + b.w_mm)) + pad) : 210;
                                const maxY = hasBoxes ? Math.min(297, Math.max(...validBoxes.map((b) => b.y_mm + b.h_mm)) + pad) : 297;
                                const cropW = Math.max(20, maxX - minX);
                                const cropH = Math.max(20, maxY - minY);

                                const contourFill = mb.is_lining
                                  ? "rgba(16, 185, 129, 0.35)"
                                  : mb.is_canvas
                                  ? "rgba(245, 158, 11, 0.35)"
                                  : "rgba(59, 130, 246, 0.35)";
                                const contourStroke = mb.is_lining
                                  ? "#059669"
                                  : mb.is_canvas
                                  ? "#d97706"
                                  : "#1d4ed8";

                                return (
                                  <div className="md:col-span-5 flex flex-col justify-between p-2.5 bg-slate-50 border border-slate-300 rounded shadow-2xs">
                                    <div className="w-full flex items-center justify-between text-[11px] font-mono text-slate-700 pb-1.5 border-b border-slate-200">
                                      <span className="font-bold flex items-center gap-1.5 text-slate-800">
                                        <Camera className="w-3.5 h-3.5 text-[#C27842]" />
                                        <span>Traced Pattern Photo</span>
                                      </span>
                                      <span className="text-[10px] text-slate-500 font-bold">
                                        {piecesToRender.length} piece{piecesToRender.length !== 1 ? "s" : ""}
                                      </span>
                                    </div>

                                    {/* Traced Pattern Canvas */}
                                    <div className="relative w-full h-36 bg-white border border-slate-200 rounded overflow-hidden flex items-center justify-center">
                                      {photoUrl ? (
                                        <svg
                                          viewBox={`${minX} ${minY} ${cropW} ${cropH}`}
                                          className="w-full h-full object-contain"
                                        >
                                          <image
                                            href={photoUrl}
                                            x="0"
                                            y="0"
                                            width="210"
                                            height="297"
                                            preserveAspectRatio="none"
                                          />
                                          {piecesToRender.map((p, idx) => (
                                            <g key={p.piece_id || idx}>
                                              {p.svg_polygon && (
                                                <path
                                                  d={p.svg_polygon}
                                                  fill={contourFill}
                                                  stroke={contourStroke}
                                                  strokeWidth="1.2"
                                                />
                                              )}
                                              {p.bbox_page && (
                                                <text
                                                  x={p.bbox_page.x_mm + p.bbox_page.w_mm / 2}
                                                  y={p.bbox_page.y_mm + p.bbox_page.h_mm / 2}
                                                  textAnchor="middle"
                                                  fill="#0f172a"
                                                  stroke="#ffffff"
                                                  strokeWidth="0.8"
                                                  paintOrder="stroke"
                                                  fontSize="4.5"
                                                  fontWeight="bold"
                                                  fontFamily="monospace"
                                                >
                                                  {p.piece_name}
                                                </text>
                                              )}
                                            </g>
                                          ))}
                                        </svg>
                                      ) : (
                                        <svg
                                          viewBox={`${minX} ${minY} ${cropW} ${cropH}`}
                                          className="w-full h-full object-contain bg-slate-50"
                                        >
                                          <rect x="0" y="0" width="210" height="297" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.5" />
                                          {piecesToRender.map((p, idx) => (
                                            <g key={p.piece_id || idx}>
                                              {p.svg_polygon && (
                                                <path
                                                  d={p.svg_polygon}
                                                  fill={contourFill}
                                                  stroke={contourStroke}
                                                  strokeWidth="1.2"
                                                />
                                              )}
                                              {p.bbox_page && (
                                                <text
                                                  x={p.bbox_page.x_mm + p.bbox_page.w_mm / 2}
                                                  y={p.bbox_page.y_mm + p.bbox_page.h_mm / 2}
                                                  textAnchor="middle"
                                                  fill="#0f172a"
                                                  stroke="#ffffff"
                                                  strokeWidth="0.8"
                                                  paintOrder="stroke"
                                                  fontSize="4.5"
                                                  fontWeight="bold"
                                                  fontFamily="monospace"
                                                >
                                                  {p.piece_name}
                                                </text>
                                              )}
                                            </g>
                                          ))}
                                        </svg>
                                      )}
                                    </div>

                                    <div className="w-full flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1.5 mt-1 border-t border-slate-200">
                                      <span className="truncate max-w-[220px] font-medium text-slate-700">
                                        {piecesToRender.map((p) => p.piece_name).join(", ")}
                                      </span>
                                      <span className="font-bold text-emerald-700 shrink-0">1:1 Physical Scale</span>
                                    </div>
                                  </div>
                                );
                              })()}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      /* Default single upper component fallback */
                      <div className="bg-white border-2 border-slate-900 p-4 space-y-3 shadow-ind">
                        <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                          <span className="font-bold text-xs text-slate-900">1. Upper Component (Nested 2D)</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 bg-amber-100 text-amber-900 font-bold">Roll / Sheet</span>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
                          <div className="md:col-span-7 text-xs font-mono space-y-1.5 text-slate-700">
                            <p>Material: <strong>{selectedMaterialName || "Upper Top Synthetic Leather"}</strong></p>
                            <div className="p-2.5 bg-slate-50 border border-slate-200 space-y-1 rounded-xs">
                              <p className="flex justify-between">
                                <span className="text-slate-500">Consumption:</span>
                                <strong className="text-[#C27842] text-sm">{yieldSpec?.consumption_per_pair || 0.14} {yieldSpec?.consumption_unit || "meter"} / pair</strong>
                              </p>
                              <p className="flex justify-between">
                                <span className="text-slate-500">Yield:</span>
                                <strong className="text-emerald-700 text-sm">{yieldSpec?.yield_per_unit || 7.0} pairs / {yieldSpec?.consumption_unit === "sheet" ? "sheet" : "m"}</strong>
                              </p>
                              <p className="flex justify-between text-[11px] pt-1 border-t border-slate-200">
                                <span className="text-slate-500">Cutting Direction:</span>
                                <strong className="text-indigo-800">{cuttingDirection}</strong>
                              </p>
                            </div>
                          </div>
                          {(() => {
                            const photoUrl = getSafePhotoUrl(sample?.pattern_scan_photo?.display_url || sample?.pattern_scan_url || scanUrl);
                            const validBoxes = (patternPieces || []).map((p) => p.bbox_page).filter(Boolean);
                            const hasBoxes = validBoxes.length > 0;
                            const pad = 6;
                            const minX = hasBoxes ? Math.max(0, Math.min(...validBoxes.map((b) => b.x_mm)) - pad) : 0;
                            const minY = hasBoxes ? Math.max(0, Math.min(...validBoxes.map((b) => b.y_mm)) - pad) : 0;
                            const maxX = hasBoxes ? Math.min(210, Math.max(...validBoxes.map((b) => b.x_mm + b.w_mm)) + pad) : 210;
                            const maxY = hasBoxes ? Math.min(297, Math.max(...validBoxes.map((b) => b.y_mm + b.h_mm)) + pad) : 297;
                            const cropW = Math.max(20, maxX - minX);
                            const cropH = Math.max(20, maxY - minY);

                            return (
                              <div className="md:col-span-5 flex flex-col justify-between p-2.5 bg-slate-50 border border-slate-300 rounded shadow-2xs">
                                <div className="w-full flex items-center justify-between text-[11px] font-mono text-slate-700 pb-1.5 border-b border-slate-200">
                                  <span className="font-bold flex items-center gap-1.5 text-slate-800">
                                    <Camera className="w-3.5 h-3.5 text-[#C27842]" />
                                    <span>Traced Pattern Photo</span>
                                  </span>
                                  <span className="text-[10px] text-slate-500 font-bold">
                                    {(patternPieces || []).length} piece{(patternPieces || []).length !== 1 ? "s" : ""}
                                  </span>
                                </div>

                                <div className="relative w-full h-36 bg-white border border-slate-200 rounded overflow-hidden flex items-center justify-center">
                                  {photoUrl ? (
                                    <svg
                                      viewBox={`${minX} ${minY} ${cropW} ${cropH}`}
                                      className="w-full h-full object-contain"
                                    >
                                      <image
                                        href={photoUrl}
                                        x="0"
                                        y="0"
                                        width="210"
                                        height="297"
                                        preserveAspectRatio="none"
                                      />
                                      {(patternPieces || []).map((p, idx) => (
                                        <g key={p.piece_id || idx}>
                                          {p.svg_polygon && (
                                            <path
                                              d={p.svg_polygon}
                                              fill="rgba(59, 130, 246, 0.35)"
                                              stroke="#1d4ed8"
                                              strokeWidth="1.2"
                                            />
                                          )}
                                          {p.bbox_page && (
                                            <text
                                              x={p.bbox_page.x_mm + p.bbox_page.w_mm / 2}
                                              y={p.bbox_page.y_mm + p.bbox_page.h_mm / 2}
                                              textAnchor="middle"
                                              fill="#0f172a"
                                              stroke="#ffffff"
                                              strokeWidth="0.8"
                                              paintOrder="stroke"
                                              fontSize="4.5"
                                              fontWeight="bold"
                                              fontFamily="monospace"
                                            >
                                              {p.piece_name}
                                            </text>
                                          )}
                                        </g>
                                      ))}
                                    </svg>
                                  ) : (
                                    <svg
                                      viewBox={`${minX} ${minY} ${cropW} ${cropH}`}
                                      className="w-full h-full object-contain bg-slate-50"
                                    >
                                      <rect x="0" y="0" width="210" height="297" fill="#ffffff" stroke="#cbd5e1" strokeWidth="0.5" />
                                      {(patternPieces || []).map((p, idx) => (
                                        <g key={p.piece_id || idx}>
                                          {p.svg_polygon && (
                                            <path
                                              d={p.svg_polygon}
                                              fill="rgba(59, 130, 246, 0.35)"
                                              stroke="#1d4ed8"
                                              strokeWidth="1.2"
                                            />
                                          )}
                                        </g>
                                      ))}
                                    </svg>
                                  )}
                                </div>

                                <div className="w-full flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1.5 mt-1 border-t border-slate-200">
                                  <span className="truncate max-w-[220px] font-medium text-slate-700">
                                    {(patternPieces || []).map((p) => p.piece_name).join(", ")}
                                  </span>
                                  <span className="font-bold text-emerald-700 shrink-0">1:1 Physical Scale</span>
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    )}

                    {/* Line 2: Folded Laces */}
                    {standardStrips.length > 0 && (
                      <div className="bg-white border-2 border-slate-900 p-4 space-y-2 shadow-ind">
                        <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                          <span className="font-bold text-xs text-slate-900">2. Folded Laces & Straps (Formula 2× Folded Width)</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 bg-blue-100 text-blue-900 font-bold">{standardStrips.length} components</span>
                        </div>
                        <div className="text-xs font-mono space-y-1.5 text-slate-700">
                          {standardStrips.map((s, idx) => (
                            <div key={idx} className="border-b border-slate-100 pb-1">
                              <span className="font-bold text-slate-900">{s.name}</span>: Cut Width = 2 × {s.folded_width_mm}mm = <strong className="text-amber-800">{s.cut_width_mm}mm</strong> ({s.pieces_per_pair} pcs/pr)
                              <div className="text-[11px] text-emerald-800">
                                Consumption: <strong>{s.consumption_per_pair} m/pair</strong> · Yields {s.laces_yield_per_meter || (s.length_mm ? ((s.lanes_across_roll || 78) * 1000 / s.length_mm).toFixed(0) : "-")} laces/m ({s.pairs_per_meter || "-"} prs/m)
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Standard Insole Board */}
                    <div className="bg-white border-2 border-slate-900 p-4 space-y-2 shadow-ind">
                      <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                        <span className="font-bold text-xs text-slate-900">3. Standard Die-Cut Insole Board</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 bg-emerald-100 text-emerald-900 font-bold">Locked Factory Preset</span>
                      </div>
                      <div className="text-xs font-mono space-y-1 text-slate-700">
                        <p>Material: <strong>Cellulose Insole Board (40'' × 60'')</strong></p>
                        <p>Standard Yield: <strong className="text-emerald-700">26.0 pairs / sheet</strong></p>
                        <p>Standard Consumption: <strong>0.0385 sheet / pair</strong></p>
                      </div>
                    </div>

                    {/* Socks / Bottom Covering */}
                    <div className="bg-white border-2 border-slate-900 p-4 space-y-2 shadow-ind">
                      <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                        <span className="font-bold text-xs text-slate-900">4. Socks / Bottom Covering Material</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 bg-purple-100 text-purple-900 font-bold">Locked Factory Preset</span>
                      </div>
                      <div className="text-xs font-mono space-y-1 text-slate-700">
                        <p>Material: <strong>Socks Covering (54'' Roll)</strong></p>
                        <p>Standard Yield: <strong className="text-purple-700">8.0 pairs / meter</strong></p>
                        <p>Standard Consumption: <strong>0.125 meter / pair</strong></p>
                      </div>
                    </div>
                  </div>

                  {/* RIGHT AREA: Average & Total Material Consumption Scorecard (4 Cols) */}
                  <div className="lg:col-span-4 space-y-4">
                    <div className="bg-amber-50/70 border-2 border-slate-900 p-4 space-y-3.5 shadow-ind">
                      <div className="flex items-center gap-2 border-b border-amber-300 pb-2">
                        <Layers className="w-4 h-4 text-[#C27842]" />
                        <h4 className="font-extrabold text-xs uppercase tracking-wider text-slate-900">
                          Style BOM Consumption Scorecard
                        </h4>
                      </div>

                      {/* Summary Metrics List */}
                      <div className="space-y-2.5 text-xs font-mono">
                        {/* Upper Top Average & Total */}
                        <div className="bg-white p-2.5 border border-slate-300 space-y-1 shadow-2xs">
                          <span className="text-[10px] font-bold uppercase text-slate-500 block">Upper Top Materials (Main)</span>
                          <div className="flex justify-between items-baseline">
                            <span className="text-slate-600">Total Consumption:</span>
                            <span className="font-bold text-[#C27842]">
                              {yieldSpec?.bom_summary?.total_upper_top_consumption || yieldSpec?.consumption_per_pair || 0.07} m / pr
                            </span>
                          </div>
                          <div className="flex justify-between items-baseline">
                            <span className="text-slate-600">Average per Material:</span>
                            <span className="font-bold text-slate-900">
                              {yieldSpec?.bom_summary?.avg_upper_top_consumption || (yieldSpec?.consumption_per_pair ? (yieldSpec.consumption_per_pair / Math.max(1, (yieldSpec.material_breakdown?.length || 1))).toFixed(4) : 0.04)} m / pr
                            </span>
                          </div>
                        </div>

                        {/* Laces */}
                        {standardStrips.length > 0 && (
                          <div className="bg-white p-2.5 border border-slate-300 flex justify-between items-baseline shadow-2xs">
                            <span className="text-slate-700 font-bold">Folded Laces ({standardStrips.length}):</span>
                            <span className="font-bold text-amber-700">
                              {yieldSpec?.bom_summary?.laces_consumption || standardStrips.reduce((sum, s) => sum + (s.consumption_per_pair || 0), 0).toFixed(4)} m / pr
                            </span>
                          </div>
                        )}

                        {/* Lining Component from Tech Pack */}
                        <div className="bg-white p-2.5 border border-slate-300 space-y-1 shadow-2xs">
                          <span className="text-[10px] font-bold uppercase text-emerald-700 block">Lining Component</span>
                          <div className="flex justify-between items-baseline">
                            <span className="text-slate-600 truncate max-w-[130px]">
                              {sample?.upper_spec?.lining_material_name || "Upper Lining (54\")"}:
                            </span>
                            <span className="font-bold text-emerald-800">
                              {yieldSpec?.bom_summary?.lining_consumption || yieldSpec?.component_breakdown?.lining?.consumption_per_pair || 0.056} m / pr
                            </span>
                          </div>
                        </div>

                        {/* Canvas Backing / Reinforcement from Tech Pack */}
                        {sample?.upper_spec?.canvas_backing && (
                          <div className="bg-white p-2.5 border border-slate-300 space-y-1 shadow-2xs">
                            <span className="text-[10px] font-bold uppercase text-amber-700 block">Canvas / Reinforcement</span>
                            <div className="flex justify-between items-baseline">
                              <span className="text-slate-600 truncate max-w-[130px]">
                                {sample.upper_spec.canvas_backing}:
                              </span>
                              <span className="font-bold text-amber-800">
                                {yieldSpec?.bom_summary?.canvas_consumption || yieldSpec?.component_breakdown?.canvas_reinforcement?.consumption_per_pair || 0.061} m / pr
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Insole & Socks Presets */}
                        <div className="bg-white p-2.5 border border-slate-300 space-y-1 shadow-2xs">
                          <span className="text-[10px] font-bold uppercase text-purple-700 block">Bottom & Insole</span>
                          <div className="flex justify-between items-baseline">
                            <span className="text-slate-600">Cellulose Board:</span>
                            <span className="font-bold text-slate-800">0.0385 sht / pr</span>
                          </div>
                          <div className="flex justify-between items-baseline">
                            <span className="text-slate-600">Socks Covering:</span>
                            <span className="font-bold text-slate-800">0.125 m / pr</span>
                          </div>
                        </div>

                        {/* Total Shoe Roll Consumption */}
                        <div className="bg-slate-900 text-white p-3 border border-slate-900 space-y-1 mt-2">
                          <div className="flex justify-between items-baseline">
                            <span className="text-xs uppercase font-bold text-amber-400">Total Upper Roll Material:</span>
                            <span className="text-sm font-extrabold text-amber-300">
                              {yieldSpec?.bom_summary?.total_upper_consumption_per_pair || (yieldSpec?.consumption_per_pair ? (parseFloat(yieldSpec.consumption_per_pair) + standardStrips.reduce((sum, s) => sum + (s.consumption_per_pair || 0), 0)).toFixed(4) : "0.088")} m/pr
                            </span>
                          </div>
                          <div className="flex justify-between items-baseline text-[11px] text-slate-300">
                            <span>Avg Cutting Efficiency:</span>
                            <span className="font-bold text-emerald-400">
                              {yieldSpec?.bom_summary?.overall_avg_efficiency_pct || yieldSpec?.utilization_pct || 92.2}%
                            </span>
                          </div>
                          <div className="flex justify-between items-baseline text-[11px] text-slate-300">
                            <span>Total Net Area / Pair:</span>
                            <span className="font-bold text-white">
                              {toDisplayArea(totalNetPairAreaSqcm)} {areaUnit}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Digital Style Folder Badge */}
              <div className="bg-slate-900 text-white p-4 border-2 border-slate-900 flex items-center justify-between shadow-ind">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-amber-500/20 border border-amber-400 flex items-center justify-center text-amber-300">
                    <FolderOpen className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="font-bold text-xs uppercase tracking-wider text-amber-300">
                      Digital Style Folder PLM Archival
                    </h4>
                    <p className="text-[11px] text-slate-300 font-mono">
                      Upon sample transfer, pattern files are archived in <strong>Folder 03 Upper Patterns</strong> and synced to the central <strong>PLM Pattern Library</strong>.
                    </p>
                  </div>
                </div>

                <span className="text-xs font-mono text-emerald-400 font-bold bg-emerald-950/80 px-2.5 py-1 border border-emerald-600">
                  PLM Ready
                </span>
              </div>

              {/* Action Buttons */}
              <div className="border-t border-slate-200 pt-4 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setActiveTab("nesting")}
                  className="text-xs font-bold uppercase tracking-wider text-slate-600 hover:text-slate-900 hover:underline"
                >
                  Back to Nesting Canvas
                </button>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 border-2 border-slate-300 text-slate-700 hover:bg-slate-100 text-xs font-bold uppercase tracking-wider"
                  >
                    Done & Close
                  </button>

                  {sample?.status !== "transferred_to_style" && onOpenTransfer && (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        onOpenTransfer();
                      }}
                      className="bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase text-xs py-2 px-5 border-2 border-[#C27842] shadow-ind flex items-center gap-2"
                    >
                      <Layers className="w-4 h-4" />
                      <span>Transfer to Style Master Now</span>
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

        </div>

        {/* FOOTER */}
        <div className="bg-slate-100 border-t-2 border-slate-900 px-5 py-3 flex items-center justify-between text-xs font-mono text-slate-600 shrink-0">
          <div className="flex items-center gap-3">
            <span>Sample: <strong>{sample?.temp_code}</strong></span>
            <span>·</span>
            <span>Pieces: <strong>{totalDefinedPiecesCount} / {expectedPiecesCount}</strong></span>
            <span>·</span>
            <span>Grain: <strong className="text-indigo-800">{cuttingDirection}</strong></span>
            {yieldSpec && (
              <>
                <span>·</span>
                <span>Roll: <strong>{toDisplayLength(effectiveRollWidthMm)} {measurementUnit} × {effectiveRollLengthMeters}m</strong></span>
                <span>·</span>
                <span>Efficiency: <strong className="text-emerald-700">{yieldSpec.utilization_pct}%</strong></span>
              </>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="text-xs font-bold uppercase text-slate-700 hover:text-slate-900 underline"
          >
            Close Modal
          </button>
        </div>

      </div>

      {/* ═══════════════════════════════════════════════════════════════════════
          ADD MANUAL COMPONENT PIECE MODAL
          ═══════════════════════════════════════════════════════════════════════ */}
      {showAddPieceModal && (
        <div className="fixed inset-0 z-60 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 shadow-ind-xl w-full max-w-md flex flex-col text-slate-900">
            <div className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Plus className="w-4 h-4 text-emerald-400" />
                <h3 className="font-bold text-xs uppercase tracking-wider">
                  Add Upper Component Piece (Without Scanning)
                </h3>
              </div>
              <button onClick={() => setShowAddPieceModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-3.5 text-xs">
              <div>
                <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                  Component Name
                </label>
                <input
                  type="text"
                  value={newPieceName}
                  onChange={(e) => setNewPieceName(e.target.value)}
                  placeholder="e.g. Quarter Lateral, Back Counter"
                  className="w-full font-mono text-xs p-2 border-2 border-slate-300 focus:border-slate-900 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                    Component Type
                  </label>
                  <select
                    value={newPieceType}
                    onChange={(e) => setNewPieceType(e.target.value)}
                    className="w-full font-mono text-xs p-1.5 border border-slate-300"
                  >
                    {COMPONENT_TYPES.map((ct) => (
                      <option key={ct.value} value={ct.value}>
                        {ct.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                    Pcs / Pair
                  </label>
                  <select
                    value={newPiecePcsPerPair}
                    onChange={(e) => setNewPiecePcsPerPair(parseInt(e.target.value) || 2)}
                    className="w-full font-mono text-xs p-1.5 border border-slate-300"
                  >
                    <option value="1">1 pc / pr</option>
                    <option value="2">2 pcs (Pair)</option>
                    <option value="4">4 pcs / pr</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                    Length ({measurementUnit})
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={newPieceLength}
                    onChange={(e) => setNewPieceLength(e.target.value)}
                    className="w-full font-mono text-xs p-1.5 border border-slate-300"
                    placeholder="140"
                  />
                </div>

                <div>
                  <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                    Width ({measurementUnit})
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={newPieceWidth}
                    onChange={(e) => setNewPieceWidth(e.target.value)}
                    className="w-full font-mono text-xs p-1.5 border border-slate-300"
                    placeholder="75"
                  />
                </div>
              </div>

              <div>
                <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                  Cutting Direction Override
                </label>
                <select
                  value={newPieceCutDir}
                  onChange={(e) => setNewPieceCutDir(e.target.value)}
                  className="w-full font-mono text-xs p-1.5 border border-slate-300"
                >
                  <option value="inherit">Inherit Roll Default ({cuttingDirection})</option>
                  <option value="length_up">Length-Up (No Length Stretch)</option>
                  <option value="width_up">Width-Up (Crosswise)</option>
                  <option value="both">Both (Optimal Yield)</option>
                </select>
              </div>
            </div>

            <div className="p-3 bg-slate-100 border-t border-slate-200 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowAddPieceModal(false)}
                className="text-xs font-bold uppercase text-slate-600 hover:text-slate-900 px-3 py-1.5"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleAddManualPiece}
                className="bg-slate-900 hover:bg-slate-800 text-white font-bold uppercase text-xs px-4 py-1.5"
              >
                Add Piece
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════
          PATTERN LIBRARY BROWSER MODAL (RE-USE ACROSS STYLES)
          ═══════════════════════════════════════════════════════════════════════ */}
      {showLibraryModal && (
        <div className="fixed inset-0 z-60 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 shadow-ind-xl w-full max-w-2xl max-h-[85vh] flex flex-col text-slate-900">
            <div className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-4 h-4 text-amber-400" />
                <h3 className="font-bold text-xs uppercase tracking-wider">
                  Footwear Pattern Library (Cross-Style Re-Use)
                </h3>
              </div>
              <button onClick={() => setShowLibraryModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-3 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
              <input
                type="text"
                value={libraryQuery}
                onChange={(e) => {
                  setLibraryQuery(e.target.value);
                  fetchLibraryPatterns(e.target.value);
                }}
                placeholder="Search by pattern code, name, style or sample..."
                className="flex-1 text-xs font-mono p-2 border border-slate-300 bg-white focus:outline-none focus:border-slate-900"
              />
              <button
                type="button"
                onClick={() => fetchLibraryPatterns(libraryQuery)}
                className="bg-slate-900 text-white text-xs font-bold px-3 py-2"
              >
                Search
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-3 flex-1">
              {loadingLibrary ? (
                <div className="text-center py-8 text-xs font-mono text-slate-500">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-[#C27842]" />
                  Loading reusable pattern library...
                </div>
              ) : libraryPatterns.length === 0 ? (
                <div className="text-center py-8 text-xs font-mono text-slate-500">
                  No saved patterns found in library.
                </div>
              ) : (
                libraryPatterns.map((pat) => (
                  <div
                    key={pat.id || pat._id || pat.pattern_code}
                    className="p-3.5 border-2 border-slate-200 hover:border-[#C27842] bg-white transition flex items-center justify-between gap-3 shadow-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs text-slate-900">
                          {pat.pattern_name || pat.pattern_code}
                        </span>
                        <span className="text-[10px] font-mono px-1.5 py-0.2 bg-slate-100 text-slate-700 font-bold border border-slate-300">
                          {pat.pattern_code}
                        </span>
                      </div>
                      <div className="text-[11px] font-mono text-slate-500">
                        <span>Pieces: <strong>{pat.pattern_pieces?.length || 0}</strong></span>
                        {pat.style_code && <span> · Style: <strong>{pat.style_code}</strong></span>}
                        {pat.sample_code && <span> · Sample: <strong>{pat.sample_code}</strong></span>}
                      </div>
                    </div>

                    <button
                      type="button"
                      disabled={importingPattern}
                      onClick={() => handleImportPattern(pat)}
                      className="bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase text-xs py-1.5 px-3 border border-[#C27842] flex items-center gap-1.5 shrink-0 disabled:opacity-50"
                    >
                      <span>Import Pattern</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="p-3 bg-slate-100 border-t border-slate-200 flex justify-end">
              <button
                type="button"
                onClick={() => setShowLibraryModal(false)}
                className="text-xs font-bold uppercase text-slate-600 hover:text-slate-900"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════
          SAVE TO LIBRARY MODAL
          ═══════════════════════════════════════════════════════════════════════ */}
      {showSaveModal && (
        <div className="fixed inset-0 z-60 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 shadow-ind-xl w-full max-w-md flex flex-col text-slate-900">
            <div className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bookmark className="w-4 h-4 text-emerald-400" />
                <h3 className="font-bold text-xs uppercase tracking-wider">
                  Save Pattern to PLM Central Library
                </h3>
              </div>
              <button onClick={() => setShowSaveModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-3">
              <p className="text-xs text-slate-600">
                Saving this digitized pattern allows it to be reused directly in other footwear styles without re-scanning.
              </p>

              <div>
                <label className="font-bold uppercase tracking-wider text-[10px] text-slate-500 block mb-1">
                  Pattern Master Name
                </label>
                <input
                  type="text"
                  value={saveLibraryName}
                  onChange={(e) => setSaveLibraryName(e.target.value)}
                  placeholder="e.g. Lacebuckle Vamp Master"
                  className="w-full text-xs font-mono p-2 border-2 border-slate-300 focus:border-slate-900 focus:outline-none"
                />
              </div>

              {saveSuccessMsg && (
                <div className="p-2 bg-emerald-50 border border-emerald-300 text-emerald-800 text-xs font-mono flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>{saveSuccessMsg}</span>
                </div>
              )}
            </div>

            <div className="p-3 bg-slate-100 border-t border-slate-200 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowSaveModal(false)}
                className="text-xs font-bold uppercase text-slate-600 hover:text-slate-900 px-3 py-1.5"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingToLibrary}
                onClick={handleSaveToLibrary}
                className="bg-emerald-700 hover:bg-emerald-800 text-white font-bold uppercase text-xs px-4 py-1.5 border border-emerald-800 disabled:opacity-50"
              >
                {savingToLibrary ? "Saving..." : "Confirm & Save"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
