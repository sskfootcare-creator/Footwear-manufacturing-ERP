import { useEffect, useMemo, useState } from "react";
import { http, inr, num, API } from "../lib/api";
import {

  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
  ConfirmDialog,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import ImageUploader, { ImageThumb, SafeImage } from "../components/ImageUploader";
import BomEditorDrawer from "../components/BomEditorDrawer";
import SearchableSelect from "../components/SearchableSelect";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  Trash2,
  Pencil,
  Save,
  Calculator as CalcIcon,
  Upload,
  Download,
  ArrowLeftRight,
  Globe2,
  Wrench,
  Folder,
  AlertTriangle,
  CheckCircle,
  Palette,
  RotateCcw,
  Undo2,
  Layers,
  Sparkles,
} from "lucide-react";

const ONLINE_CHANNELS = ["myntra", "flipkart", "nykaa", "website"];

const SECTIONS = [
  "Upper Top",
  "Mid Layer / Reinforcement",
  "Lining",
  "Bottom Layer",
  "Insole Board + Cushion",
  "Insole Cover (PU/Leather)",
  "Sole",
  "Accessory",
  "Consumable",
  "Packing",
  "Other",
];

// Footwear GST Rate Threshold Configuration (India)
// Threshold: ₹2,500 per pair
// Price <= 2500 -> 5% GST
// Price > 2500  -> 18% GST
export const FOOTWEAR_GST_CONFIG = {
  threshold: 2500,
  rate_below_or_equal: 5,
  rate_above: 18,
};

export function suggestGstPct(price) {
  const p = Number(price);
  if (isNaN(p) || p <= 0) return FOOTWEAR_GST_CONFIG.rate_below_or_equal;
  return p > FOOTWEAR_GST_CONFIG.threshold ? FOOTWEAR_GST_CONFIG.rate_above : FOOTWEAR_GST_CONFIG.rate_below_or_equal;
}

const emptyStyle = {
  code: "",
  name: "",
  category: "Footwear",
  image_url: "",
  image_display_url: "",
  image_thumbnail_url: "",
  description: "",
  base_size: "7",
  insole_mould_name: "",
  sole_mould_name: "",
  bom: [],
  labor: [],
  overhead_pct: 8,
  packing_cost: 12,
  margin_pct: 25,
  gst_pct: 5,
  default_pairs_per_carton: {},
  color_bom_overrides: {},
};

export default function Styles() {
  const navigate = useNavigate();
  const [styles, setStyles] = useState([]);
  const [bomStyle, setBomStyle] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [open, setOpen] = useState(false);
  const [isGstOverridden, setIsGstOverridden] = useState(false);
  const [newSizeKey, setNewSizeKey] = useState("");
  const [newSizeQty, setNewSizeQty] = useState("");
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkPreview, setBulkPreview] = useState(null);
  const [bulkErrors, setBulkErrors] = useState([]);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyStyle);
  const [confirm, setConfirm] = useState(null);
  const [formError, setFormError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const [styleMappings, setStyleMappings] = useState([]);
  const [addingMapping, setAddingMapping] = useState(false);
  const [editingMappingId, setEditingMappingId] = useState(null);
  // Catalogue codes for the currently-open style (group SKU + leaf SKUs)
  const [catalogueCodes, setCatalogueCodes] = useState(null);
  const [catalogueLoading, setCatalogueLoading] = useState(false);
  // Color-specific BOM overrides state
  const [selectedBomColor, setSelectedBomColor] = useState("");
  const [colorMasterList, setColorMasterList] = useState([]);
  const [newCustomColorInput, setNewCustomColorInput] = useState("");
  const [colorSpecificAddMat, setColorSpecificAddMat] = useState(null);
  // Catalogue export modal state (Phase F)
  const [exportOpen, setExportOpen] = useState(false);
  const [exportPlatform, setExportPlatform] = useState("myntra");
  const [exportColors, setExportColors] = useState([]);          // selected colour names
  const [exportSizes, setExportSizes] = useState([]);            // selected size strings
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportPreview, setExportPreview] = useState(null);      // response from /catalogue-export/preview
  const [exportPlatformsAvailable, setExportPlatformsAvailable] = useState([]);

  const loadCatalogueCodes = async (styleId) => {
    if (!styleId) return;
    setCatalogueLoading(true);
    try {
      const res = await http.get(`/styles/${styleId}/catalogue-codes`);
      setCatalogueCodes(res.data);
    } catch (e) {
      console.error("Failed to load catalogue codes", e);
      setCatalogueCodes(null);
    } finally {
      setCatalogueLoading(false);
    }
  };

  // Open the export modal, pre-selecting all colours & sizes and loading
  // the list of platforms that have an export_template configured.
  const openExportModal = async (platform) => {
    if (!catalogueCodes) return;
    setExportError("");
    setExportPreview(null);
    setExportPlatform(platform);
    setExportColors(catalogueCodes.colors || []);
    setExportSizes(catalogueCodes.sizes || []);
    setExportOpen(true);
    // Fetch available platforms once (cached in state)
    if (exportPlatformsAvailable.length === 0) {
      try {
        const r = await http.get("/listing-format-configs?active=true");
        setExportPlatformsAvailable(
          (r.data || []).filter((c) => !!c.export_template),
        );
      } catch (e) {
        console.error("Failed to load listing format configs", e);
      }
    }
  };

  const toggleColor = (c) =>
    setExportColors((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  const toggleSize = (s) =>
    setExportSizes((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  const runExportPreview = async () => {
    setExportBusy(true);
    setExportError("");
    setExportPreview(null);
    try {
      const res = await http.post("/catalogue-export/preview", {
        style_id: editId,
        platform: exportPlatform,
        colors: exportColors,
        sizes: exportSizes,
      });
      setExportPreview(res.data);
    } catch (e) {
      setExportError(e.response?.data?.detail || e.message);
    } finally {
      setExportBusy(false);
    }
  };

  // Download the .xlsx directly. We keep this separate from preview so the
  // sku_map provisional rows are only created when the user really commits.
  const downloadExport = async () => {
    setExportBusy(true);
    setExportError("");
    try {
      const res = await http.post(
        "/catalogue-export",
        {
          style_id: editId,
          platform: exportPlatform,
          colors: exportColors,
          sizes: exportSizes,
        },
        { responseType: "blob" },
      );
      // Filename from Content-Disposition
      const cd = res.headers["content-disposition"] || "";
      const m = /filename="([^"]+)"/.exec(cd);
      const fname = m ? m[1] : `${exportPlatform}_listing.xlsx`;
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = fname.replace(/[\/\\]/g, "-");
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      // Show quick summary from response headers
      const rows = res.headers["x-rows-written"];
      const created = res.headers["x-skumap-created"];
      const updated = res.headers["x-skumap-updated"];
      setExportError(
        `Downloaded ${fname} — ${rows} rows written, ${created || 0} new SKU-map rows (${updated || 0} updated). Provisional status: pending platform confirmation.`,
      );
    } catch (e) {
      // Blob error responses need to be text-decoded
      if (e.response?.data instanceof Blob) {
        const txt = await e.response.data.text();
        try {
          const j = JSON.parse(txt);
          setExportError(j.detail || txt);
        } catch {
          setExportError(txt);
        }
      } else {
        setExportError(e.response?.data?.detail || e.message);
      }
    } finally {
      setExportBusy(false);
    }
  };
  const [newMapping, setNewMapping] = useState({
    source_type: "b2b_client",
    source_name: "",
    external_sku: "",
    external_style_name: "",
    color_map_str: "",
    size_map_str: "",
  });
  const [editingMapping, setEditingMapping] = useState({
    external_style_name: "",
    color_map_str: "",
    size_map_str: "",
  });

  const loadStyleMappings = async (styleId) => {
    try {
      const res = await http.get(`/sku-map?style_id=${styleId}`);
      setStyleMappings(res.data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAddMapping = async () => {
    if (!newMapping.source_name.trim() || !newMapping.external_sku.trim()) {
      alert("Source Name and External SKU are required.");
      return;
    }
    try {
      await http.post("/sku-map", {
        style_id: editId,
        source_type: newMapping.source_type,
        source_name: newMapping.source_name.trim(),
        external_sku: newMapping.external_sku.trim(),
        external_style_name: newMapping.external_style_name.trim(),
        color_map: stringToMap(newMapping.color_map_str),
        size_map: stringToMap(newMapping.size_map_str),
      });
      setAddingMapping(false);
      setNewMapping({
        source_type: "b2b_client",
        source_name: "",
        external_sku: "",
        external_style_name: "",
        color_map_str: "",
        size_map_str: "",
      });
      loadStyleMappings(editId);
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to add mapping.");
    }
  };

  const handleUpdateMapping = async (mid) => {
    try {
      await http.put(`/sku-map/${mid}`, {
        external_style_name: editingMapping.external_style_name.trim(),
        color_map: stringToMap(editingMapping.color_map_str),
        size_map: stringToMap(editingMapping.size_map_str),
      });
      setEditingMappingId(null);
      loadStyleMappings(editId);
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to update mapping.");
    }
  };

  const handleDeleteMapping = async (mid) => {
    if (!window.confirm("Are you sure you want to delete this mapping?")) return;
    try {
      await http.delete(`/sku-map/${mid}`);
      loadStyleMappings(editId);
    } catch (e) {
      alert("Failed to delete mapping.");
    }
  };

  const mapToString = (map) => {
    if (!map) return "";
    return Object.entries(map).map(([k, v]) => `${k}:${v}`).join(", ");
  };

  const stringToMap = (str) => {
    const map = {};
    if (!str) return map;
    str.split(",").forEach(item => {
      const parts = item.split(":");
      if (parts.length === 2) {
        const k = parts[0].trim();
        const v = parts[1].trim();
        if (k && v) map[k] = v;
      }
    });
    return map;
  };

  const load = async (filter = statusFilter, search = searchQuery) => {
    const queryParams = new URLSearchParams();
    if (filter) queryParams.append("status", filter);
    if (search) queryParams.append("search", search);
    const qs = queryParams.toString() ? `?${queryParams.toString()}` : "";
    const [s, m, cm] = await Promise.all([
      http.get(`/styles/summary${qs}`),
      http.get("/materials"),
      http.get("/color-master?active=true").catch(() => ({ data: [] })),
    ]);
    setStyles(s.data);
    setMaterials(m.data);
    setColorMasterList(cm.data || []);

    const params = new URLSearchParams(window.location.search);
    const editCode = params.get("edit");
    if (editCode && s.data.length > 0) {
      const styleToEdit = s.data.find((x) => x.code === editCode);
      if (styleToEdit) {
        startEdit(styleToEdit);
        // Clear the query parameter so it doesn't reopen on refresh
        window.history.replaceState(
          {},
          document.title,
          window.location.pathname,
        );
      }
    }
  };
  useEffect(() => {
    const timer = setTimeout(() => {
      load(statusFilter, searchQuery);
    }, 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, searchQuery]);

  const startNew = () => {
    setEditId(null);
    setIsGstOverridden(false);
    setForm({ ...emptyStyle, gst_pct: suggestGstPct(0) });
    setFormError("");
    setStyleMappings([]);
    setAddingMapping(false);
    setEditingMappingId(null);
    setCatalogueCodes(null);
    setSelectedBomColor("");
    setColorSpecificAddMat(null);
    setOpen(true);
  };
  const startEdit = async (s) => {
    setEditId(s.id);
    setFormError("");
    setStyleMappings([]);
    setAddingMapping(false);
    setEditingMappingId(null);
    setCatalogueCodes(null);
    setColorSpecificAddMat(null);
    setOpen(true);

    try {
      const { data: fullStyle } = await http.get(`/styles/${s.id}`);
      const initialSell = fullStyle.costing?.suggested_target_price || fullStyle.costing?.selling_price || fullStyle.costing?.sell || 0;
      const suggested = suggestGstPct(initialSell);
      const isOverride = fullStyle.gst_pct != null && Number(fullStyle.gst_pct) !== suggested;
      setIsGstOverridden(isOverride);
      
      const ensuredBom = (fullStyle.bom || []).map((b) => ({
        ...b,
        line_id: b.line_id || Math.random().toString(36).substring(2, 10),
      }));

      setForm({
        code: fullStyle.code,
        name: fullStyle.name,
        category: fullStyle.category,
        image_url: fullStyle.image_url || "",
        image_original_url: fullStyle.image_original_url || fullStyle.image_url || "",
        image_display_url: fullStyle.image_display_url || "",
        image_thumbnail_url: fullStyle.image_thumbnail_url || "",
        description: fullStyle.description || "",
        base_size: fullStyle.base_size || "7",
        insole_mould_name: fullStyle.insole_mould_name || "",
        sole_mould_name: fullStyle.sole_mould_name || "",
        bom: ensuredBom,
        labor: fullStyle.labor || [],
        overhead_pct: fullStyle.overhead_pct,
        packing_cost: fullStyle.packing_cost,
        margin_pct: fullStyle.margin_pct,
        gst_pct: fullStyle.gst_pct,
        default_pairs_per_carton: fullStyle.default_pairs_per_carton || {},
        color_bom_overrides: fullStyle.color_bom_overrides || {},
      });

      const overrideColors = Object.keys(fullStyle.color_bom_overrides || {});
      if (overrideColors.length > 0) {
        setSelectedBomColor(overrideColors[0]);
      } else {
        setSelectedBomColor("");
      }

      loadStyleMappings(fullStyle.id);
      loadCatalogueCodes(fullStyle.id);
    } catch (e) {
      console.error("Failed to load full style details", e);
    }
  };

  const save = async () => {
    setFormError("");
    try {
      const body = {
        ...form,
        insole_mould_name: form.insole_mould_name ? form.insole_mould_name.trim() : null,
        sole_mould_name: form.sole_mould_name ? form.sole_mould_name.trim() : null,
        overhead_pct: Number(form.overhead_pct),
        packing_cost: Number(form.packing_cost),
        margin_pct: Number(form.margin_pct),
        gst_pct: Number(form.gst_pct),
        default_pairs_per_carton: form.default_pairs_per_carton || {},
        color_bom_overrides: form.color_bom_overrides || {},
        bom: form.bom.map((b) => ({
          ...b,
          line_id: b.line_id || Math.random().toString(36).substring(2, 10),
          quantity: Number(b.quantity),
          yield_per_unit: Number(b.yield_per_unit || 1),
          waste_pct: Number(b.waste_pct || 0),
          rate: Number(b.rate),
        })),
        labor: form.labor.map((l) => ({ ...l, rate: Number(l.rate) })),
      };
      if (editId) {
        // Never send `code` on update — it's immutable server-side and rejected
        // if it doesn't match the current value. Strip it here to be safe.
        // eslint-disable-next-line no-unused-vars
        const { code: _ignored, ...bodyNoCode } = body;
        await http.patch(`/styles/${editId}`, bodyNoCode);
        setOpen(false);
        load();
      } else {
        // Do NOT send a code — backend always generates SSK_XXXXX
        // eslint-disable-next-line no-unused-vars
        const { code: _ignored, ...bodyNoCode } = body;
        const res = await http.post("/styles", bodyNoCode);
        // Slide into edit-mode for the newly-created style so the user sees
        // the assigned SSK_XXXXX code and the Catalogue Codes panel.
        setEditId(res.data.id);
        setForm((f) => ({ ...f, code: res.data.code }));
        loadStyleMappings(res.data.id);
        loadCatalogueCodes(res.data.id);
        load();
      }
    } catch (e) {
      setFormError(e.response?.data?.detail || e.message);
    }
  };

  const addSizeCarton = () => {
    if (!newSizeKey || !newSizeQty) return;
    const qtyVal = parseInt(newSizeQty, 10);
    if (isNaN(qtyVal) || qtyVal <= 0) return;
    const cur = { ...(form.default_pairs_per_carton || {}) };
    cur[newSizeKey.trim()] = qtyVal;
    setForm({ ...form, default_pairs_per_carton: cur });
    setNewSizeKey("");
    setNewSizeQty("");
  };

  const removeSizeCarton = (sz) => {
    const cur = { ...(form.default_pairs_per_carton || {}) };
    delete cur[sz];
    setForm({ ...form, default_pairs_per_carton: cur });
  };

  const remove = (id) => {
    setConfirm({
      title: "Delete Style",
      message:
        "Are you sure you want to delete this style from the Master catalog?",
      onConfirm: async () => {
        await http.delete(`/styles/${id}`);
        setConfirm(null);
        load();
      },
    });
  };

  const togglePipeline = (s) => {
    if (s.in_online_pipeline) {
      setConfirm({
        title: "Remove from Online Pipeline",
        message: `Remove "${s.code}" from the Online Style Pipeline? Its lifecycle stage and any planned components/colors/sizes will be discarded.`,
        onConfirm: async () => {
          try {
            await http.delete(`/styles/${s.id}/pipeline`);
          } catch (e) {
            alert(e.response?.data?.detail || e.message);
          }
          setConfirm(null);
          load();
        },
      });
    } else {
      setConfirm({
        title: "Send to Online Pipeline",
        message: `Add "${s.code}" to the Online Style Pipeline as Draft? You can then advance it through Sample → Photoshoot → Catalog → Price → Launch → Live.`,
        onConfirm: async () => {
          try {
            await http.post(`/styles/${s.id}/pipeline`);
          } catch (e) {
            alert(e.response?.data?.detail || e.message);
          }
          setConfirm(null);
          load();
        },
      });
    }
  };

  const onImageChange = (imgObj) => {
    setForm((f) => ({
      ...f,
      image_url: imgObj.url || "",
      image_original_url: imgObj.original_url || imgObj.url || "",
      image_display_url: imgObj.display_url || "",
      image_thumbnail_url: imgObj.thumbnail_url || "",
    }));
  };

  const generateLineId = () => Math.random().toString(36).substring(2, 10);

  const addBomRow = (material) => {
    setForm((f) => ({
      ...f,
      bom: [
        ...f.bom,
        {
          line_id: generateLineId(),
          material_id: material.id,
          material_code: material.code,
          material_name: material.name,
          unit: material.unit,
          rate: material.rate,
          quantity: 1,
          // Prefill from material's default if set; still editable per-line
          yield_per_unit: material.default_yield_per_unit ?? 1,
          waste_pct: 5,
          section: material.category,
          color: "",
        },
      ],
    }));
  };

  const updateBom = (i, key, val) =>
    setForm((f) => ({
      ...f,
      bom: f.bom.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)),
    }));
  const removeBom = (i) =>
    setForm((f) => ({ ...f, bom: f.bom.filter((_, idx) => idx !== i) }));
  const updateLabor = (i, key, val) =>
    setForm((f) => ({
      ...f,
      labor: f.labor.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)),
    }));
  const addLabor = () =>
    setForm((f) => ({ ...f, labor: [...f.labor, { name: "Labor", rate: 0 }] }));
  const removeLabor = (i) =>
    setForm((f) => ({ ...f, labor: f.labor.filter((_, idx) => idx !== i) }));

  // Color-specific BOM Overrides Helpers
  const allColorOptions = useMemo(() => {
    const list = [];
    const seen = new Set();

    // 1. Add from Color Master palette
    (colorMasterList || []).forEach((cm) => {
      const name = (cm.color_name || cm.name || cm.code || "").trim();
      if (name && !seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        list.push(name);
      }
    });

    // 2. Fallback default footwear palette if colorMasterList empty
    const defaultPalette = [
      "Tan", "Beige", "Black", "Brown", "Navy", "Blue", "White", "Cream",
      "Maroon", "Grey", "Olive", "Red", "Pink", "Gold", "Silver", "Green",
      "Yellow", "Orange", "Purple", "Rose Gold", "Nude"
    ];
    defaultPalette.forEach((name) => {
      if (!seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        list.push(name);
      }
    });

    // 3. Add any colors entered in base BOM lines
    (form.bom || []).forEach((b) => {
      const col = (b.color || "").trim();
      if (col && !seen.has(col.toLowerCase())) {
        seen.add(col.toLowerCase());
        list.push(col);
      }
    });

    return list;
  }, [colorMasterList, form.bom]);

  const availableBomColors = useMemo(() => {
    const set = new Set();
    (catalogueCodes?.colors || []).forEach((c) => c && set.add(c.trim()));
    (form.bom || []).forEach((b) => b.color && set.add(b.color.trim()));
    Object.keys(form.color_bom_overrides || {}).forEach((c) => c && set.add(c.trim()));
    if (selectedBomColor) set.add(selectedBomColor.trim());
    return Array.from(set);
  }, [catalogueCodes, form.bom, form.color_bom_overrides, selectedBomColor]);

  useEffect(() => {
    if (availableBomColors.length > 0 && (!selectedBomColor || !availableBomColors.includes(selectedBomColor))) {
      setSelectedBomColor(availableBomColors[0]);
    }
  }, [availableBomColors, selectedBomColor]);

  const updateLineOverride = (colorName, lineId, field, val) => {
    if (!colorName || !lineId) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = [...(prevMap[colorName] || [])];
      const baseLine = f.bom.find((b) => b.line_id === lineId);
      const existingIdx = colorOverrides.findIndex((ov) => ov.line_id === lineId);

      const parsedVal = (field === "rate" || field === "quantity" || field === "yield_per_unit" || field === "waste_pct")
        ? Number(val)
        : val;

      if (existingIdx >= 0) {
        colorOverrides[existingIdx] = {
          ...colorOverrides[existingIdx],
          [field]: parsedVal,
        };
      } else if (baseLine) {
        colorOverrides.push({
          line_id: lineId,
          removed: false,
          material_id: baseLine.material_id,
          material_name: baseLine.material_name,
          material_code: baseLine.material_code,
          unit: baseLine.unit,
          rate: Number(baseLine.rate),
          quantity: Number(baseLine.quantity),
          yield_per_unit: Number(baseLine.yield_per_unit || 1),
          waste_pct: Number(baseLine.waste_pct || 0),
          section: baseLine.section,
          component: baseLine.component,
          with_eva: baseLine.with_eva,
          color: baseLine.color,
          [field]: parsedVal,
        });
      }

      return {
        ...f,
        color_bom_overrides: {
          ...prevMap,
          [colorName]: colorOverrides,
        },
      };
    });
  };

  const updateLineMaterial = (colorName, lineId, matObj) => {
    if (!colorName || !lineId || !matObj) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = [...(prevMap[colorName] || [])];
      const baseLine = f.bom.find((b) => b.line_id === lineId);
      const existingIdx = colorOverrides.findIndex((ov) => ov.line_id === lineId);

      const matFields = {
        material_id: matObj.id,
        material_code: matObj.code,
        material_name: matObj.name,
        unit: matObj.unit,
        rate: Number(matObj.rate || 0),
        yield_per_unit: Number(matObj.default_yield_per_unit ?? 1),
      };

      if (existingIdx >= 0) {
        colorOverrides[existingIdx] = {
          ...colorOverrides[existingIdx],
          ...matFields,
        };
      } else if (baseLine) {
        colorOverrides.push({
          line_id: lineId,
          removed: false,
          quantity: Number(baseLine.quantity),
          waste_pct: Number(baseLine.waste_pct || 0),
          section: baseLine.section,
          component: baseLine.component,
          with_eva: baseLine.with_eva,
          color: baseLine.color,
          ...matFields,
        });
      }

      return {
        ...f,
        color_bom_overrides: {
          ...prevMap,
          [colorName]: colorOverrides,
        },
      };
    });
  };

  const removeLineForColor = (colorName, lineId) => {
    if (!colorName || !lineId) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = [...(prevMap[colorName] || [])];
      const existingIdx = colorOverrides.findIndex((ov) => ov.line_id === lineId);

      if (existingIdx >= 0) {
        colorOverrides[existingIdx] = {
          ...colorOverrides[existingIdx],
          removed: true,
        };
      } else {
        colorOverrides.push({
          line_id: lineId,
          removed: true,
        });
      }

      return {
        ...f,
        color_bom_overrides: {
          ...prevMap,
          [colorName]: colorOverrides,
        },
      };
    });
  };

  const resetLineToBase = (colorName, lineId) => {
    if (!colorName || !lineId) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = (prevMap[colorName] || []).filter(
        (ov) => ov.line_id !== lineId
      );
      const updatedMap = { ...prevMap };
      if (colorOverrides.length === 0) {
        delete updatedMap[colorName];
      } else {
        updatedMap[colorName] = colorOverrides;
      }
      return {
        ...f,
        color_bom_overrides: updatedMap,
      };
    });
  };

  const addColorSpecificLine = (colorName, matObj) => {
    if (!colorName || !matObj) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = [...(prevMap[colorName] || [])];
      colorOverrides.push({
        line_id: null,
        removed: false,
        material_id: matObj.id,
        material_code: matObj.code,
        material_name: matObj.name,
        unit: matObj.unit,
        rate: Number(matObj.rate || 0),
        quantity: 1,
        yield_per_unit: Number(matObj.default_yield_per_unit ?? 1),
        waste_pct: 5,
        section: matObj.category || "Other",
        color: colorName,
      });
      return {
        ...f,
        color_bom_overrides: {
          ...prevMap,
          [colorName]: colorOverrides,
        },
      };
    });
  };

  const updateColorSpecificAddedLine = (colorName, overrideIdx, field, val) => {
    if (!colorName) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = [...(prevMap[colorName] || [])];
      if (colorOverrides[overrideIdx]) {
        const parsedVal = (field === "rate" || field === "quantity" || field === "yield_per_unit" || field === "waste_pct")
          ? Number(val)
          : val;
        colorOverrides[overrideIdx] = {
          ...colorOverrides[overrideIdx],
          [field]: parsedVal,
        };
      }
      return {
        ...f,
        color_bom_overrides: {
          ...prevMap,
          [colorName]: colorOverrides,
        },
      };
    });
  };

  const removeColorSpecificAddedLine = (colorName, overrideIdx) => {
    if (!colorName) return;
    setForm((f) => {
      const prevMap = f.color_bom_overrides || {};
      const colorOverrides = (prevMap[colorName] || []).filter(
        (_, idx) => idx !== overrideIdx
      );
      const updatedMap = { ...prevMap };
      if (colorOverrides.length === 0) {
        delete updatedMap[colorName];
      } else {
        updatedMap[colorName] = colorOverrides;
      }
      return {
        ...f,
        color_bom_overrides: updatedMap,
      };
    });
  };

  const onPreviewBulk = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBulkFile(file);
    setBulkPreview(null);
    setBulkErrors([]);
    setBulkResult(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await http.post("/styles/bulk/preview", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setBulkPreview(res.data.preview || []);
      setBulkErrors(res.data.errors || []);
    } catch (err) {
      alert("Preview failed: " + (err.response?.data?.detail || err.message));
    }
  };

  const submitBulk = async () => {
    if (!bulkPreview || bulkPreview.length === 0) return;
    setBulkUploading(true);
    try {
      const res = await http.post("/styles/bulk", { styles: bulkPreview });
      setBulkResult(res.data);
      load();
    } catch (err) {
      alert(
        "Bulk upload failed: " + (err.response?.data?.detail || err.message),
      );
    }
    setBulkUploading(false);
  };

  // Helper to compute effective BOM for any given color
  const getEffectiveBomForColor = (colorName) => {
    const baseBom = form.bom || [];
    if (!colorName || !form.color_bom_overrides?.[colorName]) {
      return baseBom;
    }
    const overrides = form.color_bom_overrides[colorName] || [];
    const removedLineIds = new Set(
      overrides.filter((o) => o.removed && o.line_id).map((o) => o.line_id)
    );

    const merged = [];
    // 1. Process base lines
    baseBom.forEach((b) => {
      if (removedLineIds.has(b.line_id)) return; // Dropped for this color
      const ov = overrides.find((o) => o.line_id === b.line_id && !o.removed);
      if (ov) {
        merged.push({
          ...b,
          material_id: ov.material_id ?? b.material_id,
          material_name: ov.material_name ?? b.material_name,
          material_code: ov.material_code ?? b.material_code,
          unit: ov.unit ?? b.unit,
          rate: ov.rate !== undefined && ov.rate !== null ? ov.rate : b.rate,
          quantity: ov.quantity !== undefined && ov.quantity !== null ? ov.quantity : b.quantity,
          yield_per_unit: ov.yield_per_unit !== undefined && ov.yield_per_unit !== null ? ov.yield_per_unit : (b.yield_per_unit ?? 1),
          waste_pct: ov.waste_pct !== undefined && ov.waste_pct !== null ? ov.waste_pct : (b.waste_pct ?? 0),
          section: ov.section ?? b.section,
          component: ov.component ?? b.component,
          with_eva: ov.with_eva ?? b.with_eva,
          color: ov.color ?? b.color,
        });
      } else {
        merged.push(b);
      }
    });

    // 2. Append color-specific added lines
    overrides.forEach((o) => {
      if (!o.line_id || !baseBom.some((b) => b.line_id === o.line_id)) {
        if (!o.removed) {
          merged.push(o);
        }
      }
    });

    return merged;
  };

  // live costing — uses effective BOM for the selected color (or base BOM)
  const costing = useMemo(() => {
    const effectiveBom = selectedBomColor ? getEffectiveBomForColor(selectedBomColor) : form.bom;
    const matCost = effectiveBom.reduce((s, b) => {
      const yld = Number(b.yield_per_unit || 1) || 1;
      return (
        s +
        ((Number(b.rate || 0) * Number(b.quantity || 0)) / yld) *
          (1 + Number(b.waste_pct || 0) / 100)
      );
    }, 0);
    const laborKnown = form.labor.length > 0;
    const labCost = laborKnown
      ? form.labor.reduce((s, l) => s + Number(l.rate || 0), 0)
      : 0;
    // When no labor is set, base excludes labor so Total Cost is not misleadingly understated
    const base = matCost + (laborKnown ? labCost : 0);
    const oh = (base * Number(form.overhead_pct || 0)) / 100;
    const total = base + oh + Number(form.packing_cost || 0);
    const margin = (total * Number(form.margin_pct || 0)) / 100;
    const sell = total + margin;
    const gst = (sell * Number(form.gst_pct || 0)) / 100;
    const hasColorOverrides = Boolean(
      selectedBomColor && (form.color_bom_overrides?.[selectedBomColor] || []).length > 0
    );
    return {
      matCost,
      labCost,
      laborKnown,
      base,
      oh,
      total,
      margin,
      sell,
      gst,
      final: sell + gst,
      hasColorOverrides,
      colorName: selectedBomColor,
    };
  }, [form, selectedBomColor]);

  const suggestedGst = useMemo(() => suggestGstPct(costing.sell), [costing.sell]);

  useEffect(() => {
    if (open && !isGstOverridden) {
      setForm((prev) => {
        if (Number(prev.gst_pct) !== suggestedGst) {
          return { ...prev, gst_pct: suggestedGst };
        }
        return prev;
      });
    }
  }, [costing.sell, suggestedGst, isGstOverridden, open]);

  return (
    <div>
      <PageHeader
        title="Style Master"
        subtitle="Master / Styles"
        testId="styles-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary
              onClick={() => setBulkOpen(true)}
              className="px-3 sm:px-4"
            >
              <Upload className="w-4 h-4 sm:mr-1 inline" />
              <span className="hidden sm:inline">Bulk Upload</span>
            </BtnSecondary>
            <BtnPrimary
              onClick={startNew}
              data-testid="add-style-btn"
              className="px-3 sm:px-5"
            >
              <Plus className="w-4 h-4 sm:mr-1 inline" />
              <span className="hidden sm:inline">New Style</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        <div className="flex gap-2">
          <div className="flex-1 max-w-md">
            <Input
              placeholder="Search style or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full !py-1 !text-sm font-sans"
            />
          </div>
          <div className="w-32 sm:w-40">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full !py-1 !text-sm"
            >
              <option value="">All Styles</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </div>
        </div>

        {styles.length === 0 ? (
          <Card className="p-12 text-center text-slate-400">
            No styles defined yet. Create your first style to build a BOM and
            unlock automatic costing.
          </Card>
        ) : (
          <div
            className="grid md:grid-cols-2 xl:grid-cols-3 gap-4"
            data-testid="styles-grid"
          >
            {styles.map((s) => (
              <Card
                key={s.id}
                className="overflow-hidden hover:border-[#C27842] transition-colors"
                data-testid={`style-card-${s.code}`}
              >
                <SafeImage
                  image={{
                    url: s.image_url,
                    display_url: s.image_display_url,
                    thumbnail_url: s.image_thumbnail_url,
                  }}
                  alt={s.name}
                  aspectRatio="16/11"
                  className="border-b-2 border-slate-200"
                  testId={`style-card-image-${s.code}`}
                />
                <div className="p-5">
                  {(() => {
                      const targetPrice = s.costing?.suggested_target_price || s.costing?.selling_price || 0;
                      const suggestedGstRate = suggestGstPct(targetPrice);
                      const hasGstMismatch = s.gst_pct != null && Number(s.gst_pct) !== suggestedGstRate;
                      return (
                        <div className="flex items-center justify-between mb-2">
                          <div className="font-mono text-xs font-bold text-slate-500">
                            {s.code}
                          </div>
                          <div className="flex gap-2 flex-wrap justify-end">
                            <Badge color={s.status === "active" ? "green" : "gray"}>
                              {s.status === "active" ? "Active" : "Inactive"}
                            </Badge>
                            <Badge color="orange">{s.category}</Badge>
                            {s.in_online_pipeline && (
                              <Badge color="blue" data-testid={`online-badge-${s.code}`}>
                                <Globe2 className="w-3 h-3 inline mr-0.5" /> Online
                              </Badge>
                            )}
                            {s.color_bom_overrides && Object.keys(s.color_bom_overrides).length > 0 && (
                              <Badge color="purple" title={`${Object.keys(s.color_bom_overrides).length} custom color BOM(s) configured`} data-testid={`style-custom-bom-badge-${s.code}`}>
                                <Palette className="w-3 h-3 inline mr-0.5" /> {Object.keys(s.color_bom_overrides).length} Custom Colors
                              </Badge>
                            )}
                            {hasGstMismatch && (
                              <Badge
                                color="orange"
                                title={`Price ₹${targetPrice} suggests ${suggestedGstRate}% GST, currently set to ${s.gst_pct}% — check before invoicing.`}
                                data-testid={`gst-mismatch-badge-${s.code}`}
                              >
                                <AlertTriangle className="w-3 h-3 inline mr-0.5 text-amber-600" /> Price suggests {suggestedGstRate}% GST (currently {s.gst_pct}%)
                              </Badge>
                            )}
                          </div>
                        </div>
                      );
                    })()}
                  <h3 className="text-lg font-bold mb-1">{s.name}</h3>
                  <p className="text-xs text-slate-500 line-clamp-2 mb-2">
                    {s.description || "—"}
                  </p>
                  {(s.insole_mould_name || s.sole_mould_name) && (
                    <div className="flex flex-wrap gap-2 my-2 py-1.5 px-2 bg-slate-50 border border-slate-200 rounded text-xs">
                      {s.insole_mould_name && (
                        <div data-testid={`style-insole-mould-${s.code}`}>
                          <span className="font-semibold text-slate-700">Insole Mold:</span>{" "}
                          <span className="font-mono text-slate-900">{s.insole_mould_name}</span>
                        </div>
                      )}
                      {s.sole_mould_name && (
                        <div data-testid={`style-sole-mould-${s.code}`}>
                          <span className="font-semibold text-slate-700">Sole Mold:</span>{" "}
                          <span className="font-mono text-slate-900">{s.sole_mould_name}</span>
                        </div>
                      )}
                    </div>
                  )}
                  <div className="border-t border-dashed border-slate-200 pt-3 space-y-1 text-xs">
                    <Row
                      label="Materials"
                      value={inr(s.costing.materials_cost)}
                    />
                    <Row
                      label={s.costing?.is_assigned ? "Labor (Assigned)" : "Labor"}
                      value={inr(s.costing.labor_cost)}
                    />
                    <Row
                      label={s.costing?.is_assigned ? "Total Cost (Actual)" : "Total cost"}
                      value={inr(s.costing.total_cost)}
                      bold
                    />
                    <Row
                      label={`Target Price (+${s.margin_pct}%)`}
                      value={inr(s.costing.suggested_target_price || s.costing.selling_price)}
                      bold
                      color="#C27842"
                    />
                  </div>
                  <div className="text-[10px] text-slate-500 italic pt-1 flex items-center gap-1" title="To hit target margin, quote around suggested price. For actual profit, see PO Profitability.">
                    <span>💡 Suggested target price (negotiation aid). For actual profit, see PO Profitability.</span>
                  </div>
                  <div className="flex gap-2 mt-4 pt-3 border-t border-slate-200">
                    <BtnSecondary
                      onClick={() => startEdit(s)}
                      className="flex-1 min-h-[44px]"
                    >
                      <Pencil className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Edit
                    </BtnSecondary>
                    <button
                      onClick={() => togglePipeline(s)}
                      title={s.in_online_pipeline ? "Remove from Online Pipeline" : "Send to Online Pipeline"}
                      data-testid={`pipeline-toggle-${s.code}`}
                      className={`px-3 py-2 border-2 text-xs font-bold uppercase tracking-wider transition-colors min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ${
                        s.in_online_pipeline
                          ? "border-blue-500 text-blue-700 bg-blue-50 hover:bg-blue-100"
                          : "border-slate-300 hover:border-blue-500 hover:text-blue-600"
                      }`}
                    >
                      <Globe2 className="w-4 h-4 inline" />
                    </button>
                    <button
                      onClick={() => navigate("/plm")}
                      title="Digital Style Folder (PLM)"
                      data-testid={`plm-folder-${s.code}`}
                      className="px-3 py-2 border-2 border-amber-400 text-amber-700 bg-amber-50 hover:bg-amber-100 text-xs font-bold min-h-[44px] inline-flex items-center justify-center gap-1 touch-manipulation transition-colors"
                    >
                      <Folder className="w-4 h-4 inline text-amber-600" /> PLM
                    </button>
                    <button
                      onClick={() => setBomStyle(s)}
                      title="Edit Production Card (BOM)"
                      data-testid={`bom-edit-${s.code}`}
                      className="px-3 py-2 border-2 border-slate-300 hover:border-emerald-500 hover:text-emerald-600 text-xs min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation"
                    >
                      <Wrench className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => remove(s.id)}
                      className="px-3 py-2 border-2 border-slate-300 hover:border-red-500 hover:text-red-600 text-xs min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation"
                      title="Delete style"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {open && (
        <Drawer
          onClose={() => {
            setOpen(false);
            setFormError("");
          }}
          title={editId ? "Edit Style" : "New Style"}
          width="max-w-5xl"
        >
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="col-span-1 lg:col-span-2 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  {/* Style Code is system-generated (SSK_XXXXX) and immutable —
                      never accept manual input. Show a pill when known, else
                      an "auto-assigned on save" hint. */}
                  <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1">
                    Style Code
                  </label>
                  {form.code ? (
                    <div
                      className="h-10 px-3 flex items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 font-mono text-sm text-neutral-900"
                      data-testid="form-style-code"
                    >
                      <span className="font-semibold">{form.code}</span>
                      <span className="ml-auto text-[10px] uppercase tracking-wider text-neutral-500 bg-white border border-neutral-200 rounded px-1.5 py-0.5">
                        immutable
                      </span>
                    </div>
                  ) : (
                    <div
                      className="h-10 px-3 flex items-center rounded-md border border-dashed border-neutral-300 bg-neutral-50/50 text-xs text-neutral-500 italic"
                      data-testid="form-style-code-placeholder"
                    >
                      Auto-assigned on save (SSK_XXXXX)
                    </div>
                  )}
                  {formError && (
                    <p
                      className="mt-1 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2"
                      data-testid="form-style-error"
                    >
                      {formError}
                    </p>
                  )}
                </div>
                <Input
                  label="Name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  testId="form-style-name"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Input
                  label="Category"
                  value={form.category}
                  onChange={(e) =>
                    setForm({ ...form, category: e.target.value })
                  }
                />
                <Input
                  label="Base Size"
                  value={form.base_size}
                  onChange={(e) =>
                    setForm({ ...form, base_size: e.target.value })
                  }
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Input
                  label="Insole Mold Name"
                  placeholder="e.g. INS-M01 / Flat Die"
                  value={form.insole_mould_name || ""}
                  onChange={(e) =>
                    setForm({ ...form, insole_mould_name: e.target.value })
                  }
                  testId="form-style-insole-mould"
                />
                <Input
                  label="Sole Mold Name"
                  placeholder="e.g. SL-M05 / Runner Cup"
                  value={form.sole_mould_name || ""}
                  onChange={(e) =>
                    setForm({ ...form, sole_mould_name: e.target.value })
                  }
                  testId="form-style-sole-mould"
                />
              </div>
              <Input
                label="Description"
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />

              {/* Image upload */}
              <ImageUploader
                label="Style Image"
                maxSizeMB={8}
                testIdPrefix="style-image"
                value={{
                  url: form.image_url,
                  original_url: form.image_original_url || form.image_url,
                  display_url: form.image_display_url,
                  thumbnail_url: form.image_thumbnail_url,
                }}
                onChange={onImageChange}
              />

              {/* BOM */}
              <div>
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mt-4 mb-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider">
                    Bill of Materials
                  </h3>
                  <div className="w-full sm:w-64">
                    <SearchableSelect
                      options={materials}
                      value=""
                      onChange={(id) => {
                        const m = materials.find((x) => x.id === id);
                        if (m) addBomRow(m);
                      }}
                      getKey={(m) => m.id}
                      getLabel={(m) => `${m.code} — ${m.name}`}
                      placeholder="+ Add material…"
                      testId="bom-add-material"
                    />
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-2 border-slate-200">
                  <thead className="bg-slate-50">
                    <tr className="text-left">
                      <th className="px-2 py-2 font-bold">Material</th>
                      <th className="px-2 py-2 font-bold">Section</th>
                      <th className="px-2 py-2 font-bold">Color</th>
                      <th className="px-2 py-2 font-bold text-right">Rate</th>
                      <th
                        className="px-2 py-2 font-bold text-right"
                        title="Material consumption per pair"
                      >
                        Qty
                      </th>
                      <th
                        className="px-2 py-2 font-bold text-right"
                        title="Pairs produced per 1 unit of material (e.g., 10 uppers per metre)"
                      >
                        Yield
                      </th>
                      <th className="px-2 py-2 font-bold text-right">Waste%</th>
                      <th className="px-2 py-2 font-bold text-right">
                        Cost/pair
                      </th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {form.bom.length === 0 && (
                      <tr>
                        <td
                          colSpan="9"
                          className="px-2 py-6 text-center text-slate-400"
                        >
                          No items. Add from dropdown above.
                        </td>
                      </tr>
                    )}
                    {form.bom.map((b, i) => {
                      const yld = Number(b.yield_per_unit || 1) || 1;
                      const cost =
                        ((Number(b.rate) * Number(b.quantity)) / yld) *
                        (1 + Number(b.waste_pct || 0) / 100);
                      const material = materials.find(
                        (m) => m.id === b.material_id,
                      );
                      return (
                        <tr key={i} className="border-t border-slate-200">
                          <td className="px-2 py-1.5">
                            <div className="flex items-center gap-2">
                              <ImageThumb
                                image={{
                                  thumbnail_url:
                                    material?.image_thumbnail_url || "",
                                  display_url: material?.image_display_url || "",
                                  url: material?.image_url || "",
                                }}
                                size={32}
                                alt={`${b.material_code} — ${b.material_name}`}
                                clickable
                                testId={`bom-thumb-${i}`}
                              />
                              <div>
                                <div className="font-mono">
                                  {b.material_code}
                                </div>
                                <div className="text-[10px] text-slate-500">
                                  {b.material_name}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              list="bom-sections-list"
                              className="font-mono border border-slate-300 px-1 py-0.5 text-xs w-36"
                              value={b.section}
                              onChange={(e) =>
                                updateBom(i, "section", e.target.value)
                              }
                              data-testid={`bom-section-${i}`}
                              placeholder="type or pick…"
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="text"
                              className="border border-slate-300 px-1 py-0.5 text-xs w-28 placeholder:text-slate-400"
                              value={b.color || ""}
                              onChange={(e) =>
                                updateBom(i, "color", e.target.value)
                              }
                              data-testid={`bom-color-${i}`}
                              placeholder="e.g. Tan, Navy…"
                            />
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono">
                            ₹{b.rate}
                            <span className="text-[10px] text-slate-400">
                              /{b.unit}
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="number"
                              step="0.01"
                              value={b.quantity}
                              onChange={(e) =>
                                updateBom(i, "quantity", e.target.value)
                              }
                              inputMode="decimal"
                              className="w-16 text-right font-mono border border-slate-300 px-1 py-2 text-xs min-h-[44px]"
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="number"
                              step="0.5"
                              value={b.yield_per_unit ?? 1}
                              onChange={(e) =>
                                updateBom(i, "yield_per_unit", e.target.value)
                              }
                              inputMode="decimal"
                              className="w-14 text-right font-mono border border-slate-300 px-1 py-2 text-xs min-h-[44px]"
                              title="Pairs per 1 unit of material"
                              data-testid={`bom-yield-${i}`}
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="number"
                              step="0.5"
                              value={b.waste_pct}
                              onChange={(e) =>
                                updateBom(i, "waste_pct", e.target.value)
                              }
                              inputMode="decimal"
                              className="w-14 text-right font-mono border border-slate-300 px-1 py-2 text-xs min-h-[44px]"
                            />
                          </td>
                          <td className="px-2 py-1.5 text-right font-mono font-bold">
                            {inr(cost)}
                          </td>
                          <td className="px-2 py-1.5">
                            <button
                              onClick={() => removeBom(i)}
                              className="text-slate-500 hover:text-red-600"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Color-Specific BOM Overrides Section */}
            <div className="border-2 border-purple-200 bg-purple-50/30 p-4 rounded-lg mt-6" data-testid="color-bom-overrides-section">
              <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div>
                  <h3 className="text-sm font-bold uppercase tracking-wider flex items-center gap-1.5 text-purple-950">
                    <Palette className="w-4 h-4 text-purple-600" />
                    Color-Specific BOM Overrides
                  </h3>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Select a color variant to customize its materials, consumption, or rates. Colors with no overrides use the base BOM.
                  </p>
                </div>
                {/* Color Selector Pills & Add Variant dropdown */}
                <div className="flex items-center gap-2 flex-wrap">
                  {availableBomColors.map((col) => {
                    const isSelected = selectedBomColor === col;
                    const ovCount = (form.color_bom_overrides?.[col] || []).length;
                    const hasCustom = ovCount > 0;
                    return (
                      <button
                        key={col}
                        type="button"
                        onClick={() => setSelectedBomColor(col)}
                        className={`px-3 py-1.5 rounded text-xs font-semibold flex items-center gap-1.5 transition-all border ${
                          isSelected
                            ? "bg-purple-700 text-white border-purple-700 shadow-sm"
                            : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                        }`}
                        data-testid={`color-tab-${col}`}
                      >
                        <span>{col}</span>
                        {hasCustom ? (
                          <span
                            className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                              isSelected
                                ? "bg-amber-400 text-purple-950"
                                : "bg-amber-100 text-amber-900 border border-amber-300"
                            }`}
                            data-testid={`custom-bom-badge-${col}`}
                          >
                            Custom BOM
                          </span>
                        ) : (
                          <span
                            className={`text-[10px] ${
                              isSelected ? "text-purple-200" : "text-slate-400"
                            }`}
                            data-testid={`base-bom-text-${col}`}
                          >
                            using base BOM
                          </span>
                        )}
                      </button>
                    );
                  })}

                  {/* Add another color variant dropdown & custom color text input */}
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <select
                      className="border border-purple-300 rounded px-2 py-1 text-xs bg-white text-slate-800 font-semibold shadow-sm hover:border-purple-500 cursor-pointer"
                      value=""
                      onChange={(e) => {
                        if (e.target.value) {
                          const c = e.target.value.trim();
                          if (c) {
                            setSelectedBomColor(c);
                          }
                        }
                      }}
                      data-testid="add-color-override-select"
                    >
                      <option value="">+ Customize Color…</option>
                      {allColorOptions.map((colName) => (
                        <option key={colName} value={colName}>
                          {colName} {availableBomColors.includes(colName) ? "(Added)" : ""}
                        </option>
                      ))}
                    </select>

                    <div className="flex items-center gap-1 bg-white border border-purple-300 rounded px-1.5 py-0.5 shadow-sm">
                      <input
                        type="text"
                        placeholder="Type custom color…"
                        value={newCustomColorInput}
                        onChange={(e) => setNewCustomColorInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && newCustomColorInput.trim()) {
                            e.preventDefault();
                            const c = newCustomColorInput.trim();
                            setSelectedBomColor(c);
                            setNewCustomColorInput("");
                          }
                        }}
                        className="text-xs px-1.5 py-0.5 border-0 focus:outline-none w-28 placeholder:text-slate-400"
                        data-testid="custom-color-text-input"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          if (newCustomColorInput.trim()) {
                            const c = newCustomColorInput.trim();
                            setSelectedBomColor(c);
                            setNewCustomColorInput("");
                          }
                        }}
                        className="text-xs px-2 py-0.5 bg-purple-700 hover:bg-purple-800 text-white rounded font-bold"
                        data-testid="custom-color-add-btn"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Active color status indicator & Add line bar */}
              {selectedBomColor ? (
                <div>
                  <div className="flex items-center justify-between mb-3 bg-white border border-purple-200 rounded p-2.5 flex-wrap gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-slate-700 uppercase tracking-wide">
                        Selected Color:
                      </span>
                      <span className="font-bold text-sm text-purple-900">{selectedBomColor}</span>
                      {(form.color_bom_overrides?.[selectedBomColor] || []).length > 0 ? (
                        <Badge color="orange" data-testid={`custom-bom-indicator-${selectedBomColor}`}>
                          Custom BOM ({(form.color_bom_overrides[selectedBomColor] || []).length} active override{(form.color_bom_overrides[selectedBomColor] || []).length > 1 ? "s" : ""})
                        </Badge>
                      ) : (
                        <Badge color="slate" data-testid={`base-bom-indicator-${selectedBomColor}`}>
                          using base BOM
                        </Badge>
                      )}
                    </div>

                    {/* Add color-specific line picker */}
                    <div className="flex items-center gap-2">
                      <div className="w-64">
                        <SearchableSelect
                          options={materials}
                          value=""
                          onChange={(id) => {
                            const m = materials.find((x) => x.id === id);
                            if (m) {
                              addColorSpecificLine(selectedBomColor, m);
                            }
                          }}
                          getKey={(m) => m.id}
                          getLabel={(m) => `${m.code} — ${m.name}`}
                          placeholder="+ Add color-specific line…"
                          testId="add-color-line-select"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Effective BOM lines table for selectedBomColor */}
                  <div className="overflow-x-auto bg-white border border-slate-200 rounded">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200">
                        <tr className="text-left text-slate-600">
                          <th className="px-2 py-2 font-bold">Material</th>
                          <th className="px-2 py-2 font-bold">Section</th>
                          <th className="px-2 py-2 font-bold">Color</th>
                          <th className="px-2 py-2 font-bold text-right">Rate</th>
                          <th className="px-2 py-2 font-bold text-right">Qty</th>
                          <th className="px-2 py-2 font-bold text-right">Yield</th>
                          <th className="px-2 py-2 font-bold text-right">Waste%</th>
                          <th className="px-2 py-2 font-bold text-right">Cost/pair</th>
                          <th className="px-2 py-2 font-bold text-center">Status</th>
                          <th className="px-2 py-2 font-bold text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {form.bom.length === 0 && (
                          <tr>
                            <td colSpan="10" className="px-2 py-6 text-center text-slate-400">
                              Base BOM is empty. Add base items first or add a color-specific line above.
                            </td>
                          </tr>
                        )}
                        {/* 1. Base BOM lines */}
                        {form.bom.map((baseLine, bIdx) => {
                          const colorOverrides = (form.color_bom_overrides || {})[selectedBomColor] || [];
                          const ov = colorOverrides.find((o) => o.line_id === baseLine.line_id);
                          const isRemoved = Boolean(ov?.removed);
                          const isOverridden = Boolean(ov && !ov.removed);

                          if (isRemoved) {
                            return (
                              <tr key={baseLine.line_id || bIdx} className="bg-red-50/50 text-slate-400" data-testid={`color-override-row-${baseLine.line_id}`}>
                                <td className="px-2 py-2 line-through font-medium">
                                  {baseLine.material_code} — {baseLine.material_name}
                                </td>
                                <td className="px-2 py-2 line-through">{baseLine.section}</td>
                                <td className="px-2 py-2 line-through">{baseLine.color || "—"}</td>
                                <td className="px-2 py-2 text-right line-through font-mono">₹{baseLine.rate}</td>
                                <td className="px-2 py-2 text-right line-through font-mono">{baseLine.quantity}</td>
                                <td className="px-2 py-2 text-right line-through font-mono">{baseLine.yield_per_unit || 1}</td>
                                <td className="px-2 py-2 text-right line-through font-mono">{baseLine.waste_pct || 0}%</td>
                                <td className="px-2 py-2 text-right line-through font-mono">—</td>
                                <td className="px-2 py-2 text-center">
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                                    Removed for {selectedBomColor}
                                  </span>
                                </td>
                                <td className="px-2 py-2 text-right">
                                  <button
                                    type="button"
                                    onClick={() => resetLineToBase(selectedBomColor, baseLine.line_id)}
                                    className="text-xs text-blue-600 hover:text-blue-800 font-bold inline-flex items-center gap-1"
                                    data-testid={`restore-line-${baseLine.line_id}`}
                                  >
                                    <RotateCcw className="w-3 h-3" /> Restore to Base
                                  </button>
                                </td>
                              </tr>
                            );
                          }

                          // Effective values
                          const effectiveMatCode = ov?.material_code ?? baseLine.material_code;
                          const effectiveMatName = ov?.material_name ?? baseLine.material_name;
                          const effectiveUnit = ov?.unit ?? baseLine.unit;
                          const effectiveRate = ov?.rate ?? baseLine.rate;
                          const effectiveQty = ov?.quantity ?? baseLine.quantity;
                          const effectiveYield = ov?.yield_per_unit ?? (baseLine.yield_per_unit ?? 1);
                          const effectiveWaste = ov?.waste_pct ?? (baseLine.waste_pct ?? 0);
                          const effectiveSection = ov?.section ?? baseLine.section;
                          const effectiveColor = ov?.color ?? baseLine.color;

                          const yld = Number(effectiveYield || 1) || 1;
                          const cost = ((Number(effectiveRate) * Number(effectiveQty)) / yld) * (1 + Number(effectiveWaste || 0) / 100);

                          return (
                            <tr
                              key={baseLine.line_id || bIdx}
                              className={`hover:bg-slate-50 transition-colors ${
                                isOverridden ? "bg-amber-50/40" : ""
                              }`}
                              data-testid={`color-override-row-${baseLine.line_id}`}
                            >
                              <td className="px-2 py-1.5">
                                <div className="space-y-1">
                                  <div>
                                    <div className={`font-mono font-bold ${ov?.material_code && ov?.material_code !== baseLine.material_code ? "text-amber-900 font-semibold" : "text-slate-800"}`}>
                                      {effectiveMatCode}
                                    </div>
                                    <div className="text-[10px] text-slate-500 line-clamp-1">{effectiveMatName}</div>
                                  </div>
                                  <select
                                    className="text-[11px] font-mono border border-slate-200 bg-slate-50 rounded px-1 py-0.5 w-full max-w-[180px] text-slate-700 hover:border-purple-400 focus:outline-none"
                                    value={ov?.material_id || baseLine.material_id || ""}
                                    onChange={(e) => {
                                      const selectedM = materials.find((m) => m.id === e.target.value);
                                      if (selectedM) {
                                        updateLineMaterial(selectedBomColor, baseLine.line_id, selectedM);
                                      }
                                    }}
                                    title="Switch material for this color variant"
                                  >
                                    <option value="" disabled>Change material…</option>
                                    {materials.map((m) => (
                                      <option key={m.id} value={m.id}>
                                        {m.code} — {m.name}
                                      </option>
                                    ))}
                                  </select>
                                </div>
                              </td>
                              <td className="px-2 py-1.5">
                                <input
                                  className={`border px-1 py-1 text-xs w-28 rounded font-mono ${
                                    ov?.section !== undefined && ov?.section !== baseLine.section
                                      ? "border-amber-400 bg-amber-50 font-semibold"
                                      : "border-slate-300"
                                  }`}
                                  value={effectiveSection || ""}
                                  onChange={(e) =>
                                    updateLineOverride(selectedBomColor, baseLine.line_id, "section", e.target.value)
                                  }
                                />
                              </td>
                              <td className="px-2 py-1.5">
                                <input
                                  className={`border px-1 py-1 text-xs w-24 rounded ${
                                    ov?.color !== undefined && ov?.color !== baseLine.color
                                      ? "border-amber-400 bg-amber-50 font-semibold"
                                      : "border-slate-300"
                                  }`}
                                  value={effectiveColor || ""}
                                  onChange={(e) =>
                                    updateLineOverride(selectedBomColor, baseLine.line_id, "color", e.target.value)
                                  }
                                  placeholder="e.g. Cream"
                                />
                              </td>
                              <td className="px-2 py-1.5 text-right">
                                <div className="flex items-center justify-end gap-1">
                                  <span className="text-[10px] text-slate-400">₹</span>
                                  <input
                                    type="number"
                                    step="0.5"
                                    className={`w-16 text-right font-mono border px-1 py-1 text-xs rounded ${
                                      ov?.rate !== undefined && ov?.rate !== baseLine.rate
                                        ? "border-amber-400 bg-amber-50 font-bold text-amber-900"
                                        : "border-slate-300"
                                    }`}
                                    value={effectiveRate}
                                    onChange={(e) =>
                                      updateLineOverride(selectedBomColor, baseLine.line_id, "rate", e.target.value)
                                    }
                                  />
                                  <span className="text-[10px] text-slate-400">/{effectiveUnit}</span>
                                </div>
                              </td>
                              <td className="px-2 py-1.5 text-right">
                                <input
                                  type="number"
                                  step="0.01"
                                  className={`w-16 text-right font-mono border px-1 py-1 text-xs rounded ${
                                    ov?.quantity !== undefined && ov?.quantity !== baseLine.quantity
                                      ? "border-amber-400 bg-amber-50 font-bold text-amber-900"
                                      : "border-slate-300"
                                  }`}
                                  value={effectiveQty}
                                  onChange={(e) =>
                                    updateLineOverride(selectedBomColor, baseLine.line_id, "quantity", e.target.value)
                                  }
                                />
                              </td>
                              <td className="px-2 py-1.5 text-right">
                                <input
                                  type="number"
                                  step="0.5"
                                  className={`w-14 text-right font-mono border px-1 py-1 text-xs rounded ${
                                    ov?.yield_per_unit !== undefined && ov?.yield_per_unit !== baseLine.yield_per_unit
                                      ? "border-amber-400 bg-amber-50 font-bold text-amber-900"
                                      : "border-slate-300"
                                  }`}
                                  value={effectiveYield}
                                  onChange={(e) =>
                                    updateLineOverride(selectedBomColor, baseLine.line_id, "yield_per_unit", e.target.value)
                                  }
                                />
                              </td>
                              <td className="px-2 py-1.5 text-right">
                                <input
                                  type="number"
                                  step="0.5"
                                  className={`w-14 text-right font-mono border px-1 py-1 text-xs rounded ${
                                    ov?.waste_pct !== undefined && ov?.waste_pct !== baseLine.waste_pct
                                      ? "border-amber-400 bg-amber-50 font-bold text-amber-900"
                                      : "border-slate-300"
                                  }`}
                                  value={effectiveWaste}
                                  onChange={(e) =>
                                    updateLineOverride(selectedBomColor, baseLine.line_id, "waste_pct", e.target.value)
                                  }
                                />
                              </td>
                              <td className="px-2 py-1.5 text-right font-mono font-bold text-slate-800">
                                {inr(cost)}
                              </td>
                              <td className="px-2 py-1.5 text-center">
                                {isOverridden ? (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300">
                                    Overridden
                                  </span>
                                ) : (
                                  <span className="text-[10px] text-slate-400 italic">Inherited</span>
                                )}
                              </td>
                              <td className="px-2 py-1.5 text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                  {isOverridden && (
                                    <button
                                      type="button"
                                      onClick={() => resetLineToBase(selectedBomColor, baseLine.line_id)}
                                      className="text-slate-600 hover:text-blue-700 text-xs font-semibold p-1 hover:bg-slate-100 rounded"
                                      title="Reset to base BOM values"
                                      data-testid={`reset-line-${baseLine.line_id}`}
                                    >
                                      <RotateCcw className="w-3.5 h-3.5 inline mr-0.5" />
                                      Reset
                                    </button>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => removeLineForColor(selectedBomColor, baseLine.line_id)}
                                    className="text-slate-400 hover:text-red-600 p-1 hover:bg-red-50 rounded"
                                    title="Remove this line for this color"
                                    data-testid={`remove-line-${baseLine.line_id}`}
                                  >
                                    <Trash2 className="w-3.5 h-3.5 inline" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}

                        {/* 2. Color-specific added lines */}
                        {((form.color_bom_overrides || {})[selectedBomColor] || [])
                          .map((ov, ovIdx) => ({ ov, ovIdx }))
                          .filter(({ ov }) => !ov.line_id || !form.bom.some((b) => b.line_id === ov.line_id))
                          .map(({ ov, ovIdx }) => {
                            const yld = Number(ov.yield_per_unit || 1) || 1;
                            const cost = ((Number(ov.rate || 0) * Number(ov.quantity || 0)) / yld) * (1 + Number(ov.waste_pct || 0) / 100);
                            return (
                              <tr key={`added-${ovIdx}`} className="bg-emerald-50/40 hover:bg-emerald-50/60 transition-colors" data-testid={`added-color-line-${ovIdx}`}>
                                <td className="px-2 py-1.5">
                                  <div>
                                    <div className="font-mono font-bold text-emerald-950">{ov.material_code}</div>
                                    <div className="text-[10px] text-emerald-700">{ov.material_name}</div>
                                  </div>
                                </td>
                                <td className="px-2 py-1.5">
                                  <input
                                    className="border border-emerald-300 bg-white px-1 py-1 text-xs w-28 rounded font-mono"
                                    value={ov.section || ""}
                                    onChange={(e) =>
                                      updateColorSpecificAddedLine(selectedBomColor, ovIdx, "section", e.target.value)
                                    }
                                  />
                                </td>
                                <td className="px-2 py-1.5">
                                  <input
                                    className="border border-emerald-300 bg-white px-1 py-1 text-xs w-24 rounded"
                                    value={ov.color || ""}
                                    onChange={(e) =>
                                      updateColorSpecificAddedLine(selectedBomColor, ovIdx, "color", e.target.value)
                                    }
                                  />
                                </td>
                                <td className="px-2 py-1.5 text-right">
                                  <div className="flex items-center justify-end gap-1">
                                    <span className="text-[10px] text-slate-400">₹</span>
                                    <input
                                      type="number"
                                      step="0.5"
                                      className="w-16 text-right font-mono border border-emerald-300 bg-white px-1 py-1 text-xs rounded font-bold text-emerald-900"
                                      value={ov.rate ?? 0}
                                      onChange={(e) =>
                                        updateColorSpecificAddedLine(selectedBomColor, ovIdx, "rate", e.target.value)
                                      }
                                    />
                                    <span className="text-[10px] text-slate-400">/{ov.unit}</span>
                                  </div>
                                </td>
                                <td className="px-2 py-1.5 text-right">
                                  <input
                                    type="number"
                                    step="0.01"
                                    className="w-16 text-right font-mono border border-emerald-300 bg-white px-1 py-1 text-xs rounded font-bold text-emerald-900"
                                    value={ov.quantity ?? 1}
                                    onChange={(e) =>
                                      updateColorSpecificAddedLine(selectedBomColor, ovIdx, "quantity", e.target.value)
                                    }
                                  />
                                </td>
                                <td className="px-2 py-1.5 text-right">
                                  <input
                                    type="number"
                                    step="0.5"
                                    className="w-14 text-right font-mono border border-emerald-300 bg-white px-1 py-1 text-xs rounded"
                                    value={ov.yield_per_unit ?? 1}
                                    onChange={(e) =>
                                      updateColorSpecificAddedLine(selectedBomColor, ovIdx, "yield_per_unit", e.target.value)
                                    }
                                  />
                                </td>
                                <td className="px-2 py-1.5 text-right">
                                  <input
                                    type="number"
                                    step="0.5"
                                    className="w-14 text-right font-mono border border-emerald-300 bg-white px-1 py-1 text-xs rounded"
                                    value={ov.waste_pct ?? 0}
                                    onChange={(e) =>
                                      updateColorSpecificAddedLine(selectedBomColor, ovIdx, "waste_pct", e.target.value)
                                    }
                                  />
                                </td>
                                <td className="px-2 py-1.5 text-right font-mono font-bold text-emerald-900">
                                  {inr(cost)}
                                </td>
                                <td className="px-2 py-1.5 text-center">
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-900 border border-emerald-300">
                                    + Added Line
                                  </span>
                                </td>
                                <td className="px-2 py-1.5 text-right">
                                  <button
                                    type="button"
                                    onClick={() => removeColorSpecificAddedLine(selectedBomColor, ovIdx)}
                                    className="text-red-500 hover:text-red-700 p-1 hover:bg-red-50 rounded"
                                    title="Delete color-specific line"
                                    data-testid={`delete-added-line-${ovIdx}`}
                                  >
                                    <Trash2 className="w-3.5 h-3.5 inline" />
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-white border border-slate-200 rounded text-center text-xs text-slate-500 italic">
                  No color selected. Select or add a planned color variant above to customize its BOM overrides.
                </div>
              )}
            </div>

              {/* Labor */}
              <div>
                <div className="flex items-baseline justify-between mt-4 mb-1">
                  <h3 className="text-sm font-bold uppercase tracking-wider">
                    Labor Operations
                  </h3>
                  <button
                    onClick={addLabor}
                    className="text-xs uppercase font-bold tracking-wider text-[#2563EB]"
                    data-testid="labor-add"
                  >
                    + Add operation
                  </button>
                </div>
                <p className="text-[11px] text-slate-400 italic mb-2">
                  Optional — actual labor rates are set per-karigar when production starts, not here.
                </p>
                {form.labor.length === 0 ? (
                  <div className="border-2 border-dashed border-slate-200 px-4 py-3 text-xs text-slate-400 italic">
                    No labor operations added. Use "+ Add operation" above if you want to record standard rates for reference.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-2 border-slate-200">
                    <tbody>
                      {form.labor.map((l, i) => (
                        <tr
                          key={i}
                          className="border-t border-slate-200 first:border-t-0"
                        >
                          <td className="px-2 py-1.5">
                            <input
                              value={l.name}
                              onChange={(e) =>
                                updateLabor(i, "name", e.target.value)
                              }
                              className="w-full border-0 bg-transparent"
                            />
                          </td>
                          <td className="px-2 py-1.5 w-32">
                            <input
                              type="number"
                              step="0.5"
                              value={l.rate}
                              onChange={(e) =>
                                updateLabor(i, "rate", e.target.value)
                              }
                              className="w-full text-right font-mono border border-slate-300 px-1 py-0.5"
                            />
                          </td>
                          <td className="px-2 py-1.5 w-8">
                            <button
                              onClick={() => removeLabor(i)}
                              className="text-slate-500 hover:text-red-600"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                )}
            </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <Input
                  label="Overhead %"
                  type="number"
                  step="0.5"
                  value={form.overhead_pct}
                  onChange={(e) =>
                    setForm({ ...form, overhead_pct: e.target.value })
                  }
                />
                <Input
                  label="Packing ₹"
                  type="number"
                  step="0.5"
                  value={form.packing_cost}
                  onChange={(e) =>
                    setForm({ ...form, packing_cost: e.target.value })
                  }
                />
                <Input
                  label="Margin %"
                  type="number"
                  step="0.5"
                  value={form.margin_pct}
                  onChange={(e) =>
                    setForm({ ...form, margin_pct: e.target.value })
                  }
                />
                <div className="space-y-1">
                  <Input
                    label="GST %"
                    type="number"
                    step="0.5"
                    value={form.gst_pct}
                    onChange={(e) => {
                      setIsGstOverridden(true);
                      setForm({ ...form, gst_pct: e.target.value });
                    }}
                  />
                  <div className="flex items-center justify-between text-[11px] text-slate-500 px-1 font-mono">
                    <span>
                      Suggested: <strong>{suggestedGst}%</strong> ({costing.sell > FOOTWEAR_GST_CONFIG.threshold ? `> ₹${FOOTWEAR_GST_CONFIG.threshold.toLocaleString()}` : `≤ ₹${FOOTWEAR_GST_CONFIG.threshold.toLocaleString()}`})
                    </span>
                    {isGstOverridden && Number(form.gst_pct) !== suggestedGst && (
                      <button
                        type="button"
                        onClick={() => {
                          setIsGstOverridden(false);
                          setForm((prev) => ({ ...prev, gst_pct: suggestedGst }));
                        }}
                        className="text-blue-600 hover:text-blue-800 font-bold underline text-[10px]"
                      >
                        Reset to Suggested ({suggestedGst}%)
                      </button>
                    )}
                  </div>
                </div>
                <Input
                  label="Default pairs / carton"
                  type="number"
                  value={form.default_pairs_per_carton?.default || ""}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    const cur = { ...(form.default_pairs_per_carton || {}) };
                    if (isNaN(val)) {
                      delete cur.default;
                    } else {
                      cur.default = val;
                    }
                    setForm({ ...form, default_pairs_per_carton: cur });
                  }}
                  placeholder="e.g. 50"
                />
              </div>

              <div className="border-t border-slate-200 pt-4 mt-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                  Size-Specific Carton Capacity Overrides
                </h4>
                <div className="flex gap-2 items-end mb-3 flex-wrap">
                  <div className="w-24">
                    <Input
                      label="Size"
                      value={newSizeKey}
                      onChange={(e) => setNewSizeKey(e.target.value)}
                      placeholder="e.g. 37"
                    />
                  </div>
                  <div className="w-28">
                    <Input
                      label="Carton Qty"
                      type="number"
                      value={newSizeQty}
                      onChange={(e) => setNewSizeQty(e.target.value)}
                      placeholder="e.g. 35"
                    />
                  </div>
                  <BtnSecondary type="button" onClick={addSizeCarton} className="h-10 px-4">
                    Add Override
                  </BtnSecondary>
                </div>
                
                <div className="flex gap-2 flex-wrap">
                  {Object.entries(form.default_pairs_per_carton || {}).filter(([sz]) => sz !== "default").map(([sz, qty]) => (
                    <Badge key={sz} color="slate" className="flex items-center gap-1.5 py-1 px-2 border-2 border-slate-300">
                      <span className="font-mono">Sz {sz}: {qty} pairs</span>
                      <button
                        type="button"
                        onClick={() => removeSizeCarton(sz)}
                        className="text-red-500 hover:text-red-700 font-bold ml-1 text-sm focus:outline-none"
                      >
                        ×
                      </button>
                    </Badge>
                  ))}
                  {Object.keys(form.default_pairs_per_carton || {}).filter(k => k !== "default").length === 0 && (
                    <div className="text-xs italic text-slate-400">No size overrides defined.</div>
                  )}
                </div>
              </div>

              {/* Catalogue Codes — SSK-generated marketplace SKUs */}
              {editId && (
                <div className="border-2 border-amber-200 p-4 mt-6 bg-amber-50/50" data-testid="catalogue-codes-panel">
                  <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
                    <h3 className="text-sm font-bold uppercase tracking-wider flex items-center gap-1.5 text-amber-900">
                      <CalcIcon className="w-4 h-4 text-amber-600" />
                      Catalogue Codes
                    </h3>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {["myntra", "flipkart", "ajio"].map((plat) => (
                        <button
                          key={plat}
                          onClick={() => openExportModal(plat)}
                          disabled={
                            !catalogueCodes ||
                            (catalogueCodes.rows || []).length === 0 ||
                            (catalogueCodes.unmapped_colors || []).length > 0
                          }
                          className="text-[11px] uppercase tracking-wider text-white bg-amber-700 hover:bg-amber-800 disabled:bg-amber-300 disabled:cursor-not-allowed font-semibold px-2 py-1 rounded inline-flex items-center gap-1"
                          data-testid={`catalogue-export-btn-${plat}`}
                          title={
                            (catalogueCodes?.unmapped_colors || []).length > 0
                              ? `Cannot export while unmapped colours exist: ${catalogueCodes.unmapped_colors.join(", ")}`
                              : `Generate a new-listing upload file for ${plat}`
                          }
                        >
                          <Download className="w-3 h-3" /> {plat} listing
                        </button>
                      ))}
                      <button
                        onClick={() => loadCatalogueCodes(editId)}
                        className="text-[11px] uppercase tracking-wider text-amber-700 hover:text-amber-900 font-semibold ml-1"
                        data-testid="catalogue-codes-refresh"
                      >
                        Refresh
                      </button>
                    </div>
                  </div>
                  <p className="text-[11px] text-amber-800/80 mb-3 leading-snug">
                    Generated from <span className="font-mono font-semibold">{form.code || "SSK_XXXXX"}</span> and the planned colour/size matrix.
                    <span className="mx-1">·</span>
                    Group SKU = <span className="font-mono">{form.code || "SSK_XXXXX"}-COLOR</span>
                    <span className="mx-1">·</span>
                    Leaf SKU = <span className="font-mono">{form.code || "SSK_XXXXX"}-COLOR-SIZE</span>
                  </p>
                  {catalogueLoading ? (
                    <div className="text-xs text-neutral-500 italic">Loading catalogue codes…</div>
                  ) : !catalogueCodes ? (
                    <div className="text-xs text-neutral-500 italic">No catalogue data available.</div>
                  ) : catalogueCodes.rows.length === 0 ? (
                    <div className="text-xs text-neutral-600 bg-white border border-neutral-200 rounded p-3">
                      No colours/sizes planned yet — set them on the Style Lifecycle page (planned_colors &amp; planned_sizes) to generate catalogue SKUs.
                    </div>
                  ) : (
                    <>
                      {catalogueCodes.unmapped_colors.length > 0 && (
                        <div className="mb-3 text-xs bg-red-50 border border-red-200 rounded px-3 py-2 text-red-800">
                          <span className="font-semibold">Missing colour codes:</span>{" "}
                          {catalogueCodes.unmapped_colors.join(", ")}. Add them under Color Master before catalogue export.
                        </div>
                      )}
                      <div className="overflow-x-auto bg-white border border-neutral-200 rounded">
                        <table className="w-full text-xs">
                          <thead className="bg-neutral-100 text-[10px] uppercase tracking-wider text-neutral-600">
                            <tr>
                              <th className="text-left p-2 border-b border-neutral-200">Colour</th>
                              <th className="text-left p-2 border-b border-neutral-200">Code</th>
                              <th className="text-left p-2 border-b border-neutral-200">Group SKU (style · colour)</th>
                              <th className="text-left p-2 border-b border-neutral-200">Leaf SKUs (style · colour · size)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {catalogueCodes.rows.map((r) => (
                              <tr key={r.color_name} className="border-b border-neutral-100 last:border-b-0">
                                <td className="p-2 font-medium">{r.color_name}</td>
                                <td className="p-2">
                                  {r.mapped ? (
                                    <span className="font-mono font-semibold text-neutral-900">{r.color_code}</span>
                                  ) : (
                                    <span className="text-red-600 italic text-[11px]">unmapped</span>
                                  )}
                                </td>
                                <td className="p-2">
                                  {r.group_sku ? (
                                    <span className="font-mono font-semibold text-amber-900 bg-amber-100 px-2 py-0.5 rounded">
                                      {r.group_sku}
                                    </span>
                                  ) : (
                                    <span className="text-neutral-400 italic">—</span>
                                  )}
                                </td>
                                <td className="p-2">
                                  <div className="flex flex-wrap gap-1">
                                    {r.size_skus.map((s) => (
                                      <span
                                        key={s.size}
                                        className="font-mono text-[11px] bg-neutral-100 border border-neutral-200 px-1.5 py-0.5 rounded"
                                      >
                                        {s.leaf_sku || `${s.size} · unmapped`}
                                      </span>
                                    ))}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* External Codes / mappings */}
              {editId && (
                <div className="border-2 border-slate-200 p-4 mt-6 bg-slate-50">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold uppercase tracking-wider flex items-center gap-1.5 text-slate-800">
                      <ArrowLeftRight className="w-4 h-4 text-slate-500" />
                      External Codes / Mappings
                    </h3>
                    {!addingMapping && (
                      <button
                        onClick={() => {
                          setAddingMapping(true);
                          setNewMapping({
                            source_type: "b2b_client",
                            source_name: "",
                            external_sku: "",
                            external_style_name: "",
                            color_map_str: "",
                            size_map_str: "",
                          });
                        }}
                        className="text-xs uppercase font-bold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                      >
                        <Plus className="w-3.5 h-3.5" /> Add Mapping
                      </button>
                    )}
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-xs bg-white border border-slate-200" id="style-inline-mappings-table">
                      <thead className="bg-slate-100 text-left border-b border-slate-200">
                        <tr>
                          <th className="px-3 py-2 font-bold text-slate-600 sticky left-0 z-10 bg-slate-100">Source Type</th>
                          <th className="px-3 py-2 font-bold text-slate-600">Source Name</th>
                          <th className="px-3 py-2 font-bold text-slate-600">Ext. SKU</th>
                          <th className="px-3 py-2 font-bold text-slate-600">Ext. Name</th>
                          <th className="px-3 py-2 font-bold text-slate-600">Color Map</th>
                          <th className="px-3 py-2 font-bold text-slate-600">Size Map</th>
                          <th className="px-3 py-2 font-bold text-center">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {/* New Mapping inline row */}
                        {addingMapping && (
                          <tr className="bg-blue-50/50">
                            <td className="p-2 sticky left-0 z-10 bg-blue-50">
                              <select
                                className="w-full border border-slate-300 p-1"
                                value={newMapping.source_type}
                                onChange={(e) => setNewMapping({ ...newMapping, source_type: e.target.value, source_name: "" })}
                              >
                                <option value="b2b_client">B2B Client</option>
                                <option value="online_channel">Online Channel</option>
                              </select>
                            </td>
                            <td className="p-2">
                              {newMapping.source_type === "online_channel" ? (
                                <select
                                  className="w-full border border-slate-300 p-1"
                                  value={newMapping.source_name}
                                  onChange={(e) => setNewMapping({ ...newMapping, source_name: e.target.value })}
                                >
                                  <option value="">— Select —</option>
                                  {ONLINE_CHANNELS.map(ch => <option key={ch} value={ch}>{ch}</option>)}
                                </select>
                              ) : (
                                <input
                                  className="w-full border border-slate-300 p-1 font-sans text-xs"
                                  placeholder="e.g. Bata"
                                  value={newMapping.source_name}
                                  onChange={(e) => setNewMapping({ ...newMapping, source_name: e.target.value })}
                                />
                              )}
                            </td>
                            <td className="p-2">
                              <input
                                className="w-full border border-slate-300 p-1 font-mono text-xs font-bold"
                                placeholder="Ext. SKU"
                                value={newMapping.external_sku}
                                onChange={(e) => setNewMapping({ ...newMapping, external_sku: e.target.value })}
                              />
                            </td>
                            <td className="p-2">
                              <input
                                className="w-full border border-slate-300 p-1 text-xs"
                                placeholder="Description"
                                value={newMapping.external_style_name}
                                onChange={(e) => setNewMapping({ ...newMapping, external_style_name: e.target.value })}
                              />
                            </td>
                            <td className="p-2">
                              <input
                                className="w-full border border-slate-300 p-1 font-mono text-xs"
                                placeholder="ext:int, ..."
                                value={newMapping.color_map_str}
                                onChange={(e) => setNewMapping({ ...newMapping, color_map_str: e.target.value })}
                              />
                            </td>
                            <td className="p-2">
                              <input
                                className="w-full border border-slate-300 p-1 font-mono text-xs"
                                placeholder="ext:int, ..."
                                value={newMapping.size_map_str}
                                onChange={(e) => setNewMapping({ ...newMapping, size_map_str: e.target.value })}
                              />
                            </td>
                            <td className="p-2 text-center whitespace-nowrap">
                              <button onClick={handleAddMapping} className="text-green-600 hover:text-green-800 font-bold mr-2 text-xs">Save</button>
                              <button onClick={() => setAddingMapping(false)} className="text-slate-500 hover:text-slate-700 text-xs">Cancel</button>
                            </td>
                          </tr>
                        )}

                        {styleMappings.length === 0 && !addingMapping && (
                          <tr>
                            <td colSpan="7" className="px-3 py-4 text-center text-slate-400">
                              No external codes mapped to this style yet.
                            </td>
                          </tr>
                        )}

                        {styleMappings.map((m) => {
                          const isEditing = editingMappingId === m.id;
                          return (
                            <tr key={m.id} className="hover:bg-slate-50">
                              <td className="px-3 py-2 sticky left-0 z-10 bg-white">
                                <Badge color={m.source_type === "b2b_client" ? "blue" : "orange"}>
                                  {m.source_type === "b2b_client" ? "B2B" : "Online"}
                                </Badge>
                              </td>
                              <td className="px-3 py-2 font-bold text-slate-700">{m.source_name}</td>
                              <td className="px-3 py-2 font-mono font-bold text-slate-900">{m.external_sku}</td>
                              <td className="px-3 py-2">
                                {isEditing ? (
                                  <input
                                    className="w-full border border-slate-300 p-0.5 text-xs"
                                    value={editingMapping.external_style_name}
                                    onChange={(e) => setEditingMapping({ ...editingMapping, external_style_name: e.target.value })}
                                  />
                                ) : (
                                  m.external_style_name || <span className="text-slate-300">—</span>
                                )}
                              </td>
                              <td className="px-3 py-2 font-mono text-slate-600">
                                {isEditing ? (
                                  <input
                                    className="w-full border border-slate-300 p-0.5 text-xs font-mono"
                                    value={editingMapping.color_map_str}
                                    onChange={(e) => setEditingMapping({ ...editingMapping, color_map_str: e.target.value })}
                                    placeholder="ext:int, ..."
                                  />
                                ) : (
                                  mapToString(m.color_map) || <span className="text-slate-300">—</span>
                                )}
                              </td>
                              <td className="px-3 py-2 font-mono text-slate-600">
                                {isEditing ? (
                                  <input
                                    className="w-full border border-slate-300 p-0.5 text-xs font-mono"
                                    value={editingMapping.size_map_str}
                                    onChange={(e) => setEditingMapping({ ...editingMapping, size_map_str: e.target.value })}
                                    placeholder="ext:int, ..."
                                  />
                                ) : (
                                  mapToString(m.size_map) || <span className="text-slate-300">—</span>
                                )}
                              </td>
                              <td className="px-3 py-2 text-center whitespace-nowrap">
                                {isEditing ? (
                                  <>
                                    <button onClick={() => handleUpdateMapping(m.id)} className="text-green-600 hover:text-green-800 font-bold mr-2 text-xs">Save</button>
                                    <button onClick={() => setEditingMappingId(null)} className="text-slate-500 hover:text-slate-700 text-xs">Cancel</button>
                                  </>
                                ) : (
                                  <>
                                    <button
                                      onClick={() => {
                                        setEditingMappingId(m.id);
                                        setEditingMapping({
                                          external_style_name: m.external_style_name || "",
                                          color_map_str: mapToString(m.color_map),
                                          size_map_str: mapToString(m.size_map),
                                        });
                                      }}
                                      className="text-blue-600 hover:text-blue-800 mr-3 text-xs"
                                    >
                                      Edit
                                    </button>
                                    <button onClick={() => handleDeleteMapping(m.id)} className="text-red-500 hover:text-red-700 text-xs">Delete</button>
                                  </>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* Live cost preview */}
            <div className="col-span-1">
              <div className="sticky top-0 bg-[#0F172A] text-white p-5 border-2 border-[#0F172A]">
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold mb-2 flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5"><CalcIcon className="w-3.5 h-3.5" /> Live Cost Sheet</span>
                  {selectedBomColor && (
                    <span className="text-[9px] bg-purple-900 text-purple-200 border border-purple-500 px-1.5 py-0.5 rounded font-bold font-mono">
                      {selectedBomColor}
                    </span>
                  )}
                </div>
                {costing.hasColorOverrides ? (
                  <div className="text-[10px] text-amber-300 bg-amber-950/60 border border-amber-800 rounded px-2 py-1 mb-2 font-medium">
                    ✦ Costing for variant: <span className="font-bold">{costing.colorName}</span> (Custom BOM)
                  </div>
                ) : selectedBomColor ? (
                  <div className="text-[10px] text-slate-400 mb-2 italic">
                    Costing for <span className="font-medium text-slate-300">{selectedBomColor}</span> (Base BOM)
                  </div>
                ) : null}
                <CostRow label="Materials" value={inr(costing.matCost)} />
                <CostRow
                  label="Labor"
                  value={
                    form.labor.length === 0
                      ? "Not set — will be determined at production"
                      : inr(costing.labCost)
                  }
                  dim={form.labor.length === 0}
                />
                <CostRow label="Overhead" value={inr(costing.oh)} />
                <CostRow label="Packing" value={inr(form.packing_cost)} />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CostRow label="Total cost" value={inr(costing.total)} bold />
                <CostRow label="Margin" value={inr(costing.margin)} />
                <CostRow
                  label="Selling"
                  value={inr(costing.sell)}
                  bold
                  accent
                />
                <CostRow
                  label={`GST ${form.gst_pct}%`}
                  value={inr(costing.gst)}
                  small
                />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CostRow label="Final / pair" value={inr(costing.final)} big />
                <div className="mt-4 pt-3 border-t border-slate-700">
                  <BtnPrimary
                    onClick={save}
                    className="w-full bg-[#C27842] border-[#C27842] hover:bg-[#A65D24]"
                    data-testid="save-style-btn"
                  >
                    <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
                    Style
                  </BtnPrimary>
                </div>
              </div>
            </div>
          </div>
        </Drawer>
      )}

      {exportOpen && (
        <Drawer
          onClose={() => setExportOpen(false)}
          title={`Generate Listing File — ${exportPlatform.toUpperCase()}`}
          width="max-w-3xl"
        >
          <div className="p-4 sm:p-6 space-y-4" data-testid="catalogue-export-modal">
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 leading-snug">
              This generates the exact .xlsx a merchandiser uploads to{" "}
              <span className="font-semibold">{exportPlatform}</span>'s seller panel to catalogue{" "}
              <span className="font-mono font-semibold">{form.code}</span>. Our SSK codes go straight
              into the platform's SKU column, so when the platform's own export is re-imported later
              it matches with zero manual reconciliation. Provisional SKU-map rows are inserted with
              status <span className="font-mono">pending_platform_confirmation</span>.
            </div>

            {/* Platform selector — only platforms with an export_template configured */}
            <div>
              <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                Platform
              </label>
              <div className="flex flex-wrap gap-1.5">
                {(exportPlatformsAvailable.length > 0
                  ? exportPlatformsAvailable.map((c) => c.platform)
                  : ["myntra", "flipkart", "ajio"]
                ).map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      setExportPlatform(p);
                      setExportPreview(null);
                    }}
                    className={`text-xs px-2.5 py-1 rounded border font-semibold uppercase ${
                      exportPlatform === p
                        ? "bg-amber-700 text-white border-amber-700"
                        : "bg-white text-slate-700 border-slate-300 hover:border-amber-500"
                    }`}
                    data-testid={`export-platform-${p}`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            {/* Colour / size selection */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                    Colours ({exportColors.length}/{(catalogueCodes?.colors || []).length})
                  </label>
                  <div className="flex gap-2 text-[10px]">
                    <button
                      className="text-slate-600 hover:text-slate-900 underline"
                      onClick={() => setExportColors(catalogueCodes?.colors || [])}
                    >
                      all
                    </button>
                    <button
                      className="text-slate-600 hover:text-slate-900 underline"
                      onClick={() => setExportColors([])}
                    >
                      none
                    </button>
                  </div>
                </div>
                <div className="max-h-48 overflow-y-auto border border-slate-200 bg-white rounded p-2 space-y-1">
                  {(catalogueCodes?.colors || []).map((c) => (
                    <label
                      key={c}
                      className="flex items-center gap-2 text-xs cursor-pointer hover:bg-slate-50 px-1.5 py-0.5 rounded"
                    >
                      <input
                        type="checkbox"
                        checked={exportColors.includes(c)}
                        onChange={() => toggleColor(c)}
                        data-testid={`export-color-${c}`}
                      />
                      <span>{c}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                    Sizes ({exportSizes.length}/{(catalogueCodes?.sizes || []).length})
                  </label>
                  <div className="flex gap-2 text-[10px]">
                    <button
                      className="text-slate-600 hover:text-slate-900 underline"
                      onClick={() => setExportSizes(catalogueCodes?.sizes || [])}
                    >
                      all
                    </button>
                    <button
                      className="text-slate-600 hover:text-slate-900 underline"
                      onClick={() => setExportSizes([])}
                    >
                      none
                    </button>
                  </div>
                </div>
                <div className="max-h-48 overflow-y-auto border border-slate-200 bg-white rounded p-2 grid grid-cols-3 gap-1">
                  {(catalogueCodes?.sizes || []).map((s) => (
                    <label
                      key={s}
                      className="flex items-center gap-2 text-xs cursor-pointer hover:bg-slate-50 px-1.5 py-0.5 rounded"
                    >
                      <input
                        type="checkbox"
                        checked={exportSizes.includes(s)}
                        onChange={() => toggleSize(s)}
                        data-testid={`export-size-${s}`}
                      />
                      <span className="font-mono">{s}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="text-xs text-slate-600">
              Will generate <span className="font-semibold">{exportColors.length * exportSizes.length}</span>{" "}
              rows ({exportColors.length} colours × {exportSizes.length} sizes).
            </div>

            {exportError && (
              <div
                className={`text-xs px-3 py-2 rounded border ${
                  exportError.startsWith("Downloaded")
                    ? "bg-green-50 border-green-200 text-green-800"
                    : "bg-red-50 border-red-200 text-red-800"
                }`}
                data-testid="export-message"
              >
                {exportError}
              </div>
            )}

            {/* Preview panel */}
            {exportPreview && (
              <div className="border border-slate-200 rounded bg-white">
                <div className="px-3 py-2 border-b border-slate-200 text-[10px] uppercase tracking-wider font-bold text-slate-600 bg-slate-50">
                  Preview — sheet "{exportPreview.sheet_name}", header row index{" "}
                  {exportPreview.header_row_index}, {exportPreview.row_count} data rows
                </div>
                <div className="overflow-x-auto max-h-64">
                  <table className="text-[11px] w-full">
                    <thead className="bg-slate-100 sticky top-0">
                      <tr>
                        {exportPreview.header.map((h, i) => (
                          <th key={i} className="text-left px-2 py-1 border-b border-slate-200 font-mono whitespace-nowrap">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {exportPreview.rows.slice(0, 20).map((row, ri) => (
                        <tr key={ri} className="border-b border-slate-100">
                          {row.map((cell, ci) => (
                            <td key={ci} className="px-2 py-1 whitespace-nowrap">
                              {cell === null || cell === undefined || cell === ""
                                ? <span className="text-slate-300">—</span>
                                : String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {exportPreview.rows.length > 20 && (
                  <div className="px-3 py-1.5 text-[11px] text-slate-500 italic bg-slate-50 border-t">
                    …{exportPreview.rows.length - 20} more rows (download to see full file)
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200">
              <BtnSecondary onClick={() => setExportOpen(false)}>Close</BtnSecondary>
              <BtnSecondary
                onClick={runExportPreview}
                disabled={exportBusy || exportColors.length === 0 || exportSizes.length === 0}
                data-testid="catalogue-export-preview-btn"
              >
                {exportBusy && !exportPreview ? "Previewing…" : "Preview"}
              </BtnSecondary>
              <BtnPrimary
                onClick={downloadExport}
                disabled={exportBusy || exportColors.length === 0 || exportSizes.length === 0}
                data-testid="catalogue-export-download-btn"
              >
                <Download className="w-4 h-4 mr-1.5" />
                {exportBusy ? "Working…" : "Download .xlsx"}
              </BtnPrimary>
            </div>
          </div>
        </Drawer>
      )}

      {bulkOpen && (
        <Drawer
          onClose={() => {
            setBulkOpen(false);
            setBulkPreview(null);
            setBulkErrors([]);
            setBulkResult(null);
            setBulkFile(null);
          }}
          title="Bulk Upload Styles"
          width="max-w-4xl"
        >
          <div className="p-4 sm:p-8 space-y-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 bg-slate-50 p-4 border border-slate-200 rounded">
              <div>
                <div className="text-sm font-semibold text-slate-800">
                  Download Style Master Template
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  No style code column required (system auto-generates sequential SSK_XXXXX codes).
                </div>
              </div>
              <a
                href={`${API}/styles/bulk/template`}
                className="px-3 py-2 border-2 border-[#C27842] text-[#C27842] hover:bg-[#C27842] hover:text-white transition-colors text-xs font-bold uppercase tracking-wider bg-white shrink-0 inline-flex items-center gap-1.5 rounded"
                download
              >

                <Download className="w-4 h-4" />
                Download Template
              </a>
            </div>

            {!bulkResult && (
              <div className="border-2 border-dashed border-slate-300 p-8 text-center bg-slate-50 hover:bg-slate-100 transition-colors relative cursor-pointer group rounded">
                <input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                  onChange={onPreviewBulk}
                  title=""
                />
                <Upload className="w-10 h-10 mx-auto text-slate-400 group-hover:text-slate-600 mb-2 transition-colors" />
                <div className="text-slate-700 font-bold uppercase text-sm tracking-wider">
                  Drag & drop Excel file here
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  or click to browse (.xlsx, .xls, .csv)
                </div>
                {bulkFile && (
                  <div className="mt-3 text-xs font-semibold text-emerald-700 border border-emerald-300 bg-emerald-50 px-3 py-1.5 inline-block rounded">
                    File selected: {bulkFile.name}
                  </div>
                )}
              </div>
            )}

            {bulkErrors && bulkErrors.length > 0 && !bulkResult && (
              <div className="p-3.5 bg-amber-50 border border-amber-300 rounded text-amber-900 text-xs space-y-1.5 shadow-sm">
                <div className="font-bold flex items-center gap-1.5 text-amber-900">
                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>{bulkErrors.length} {bulkErrors.length === 1 ? "validation issue" : "validation issues"} found (invalid rows will be skipped):</span>
                </div>
                <ul className="list-disc list-inside space-y-1 font-mono text-[11px] text-amber-800 pl-1 max-h-36 overflow-y-auto">
                  {bulkErrors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            {bulkResult && (
              <div className="space-y-4 border border-emerald-200 rounded p-5 bg-emerald-50 shadow-sm">
                <div className="flex items-center gap-2 text-emerald-800 font-bold text-base">
                  <CheckCircle className="w-6 h-6 text-emerald-600 shrink-0" />
                  <span>
                    Bulk Upload Complete: {bulkResult.success_count} {bulkResult.success_count === 1 ? "style" : "styles"} created!
                  </span>
                </div>

                {bulkResult.errors && bulkResult.errors.length > 0 && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded text-amber-900 text-xs space-y-1">
                    <div className="font-bold flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                      <span>{bulkResult.errors.length} skipped row(s):</span>
                    </div>
                    <ul className="list-disc list-inside font-mono text-[11px] text-amber-800">
                      {bulkResult.errors.map((e, idx) => (
                        <li key={idx}>{e}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {bulkResult.created && bulkResult.created.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-bold text-emerald-900 uppercase tracking-wider">
                      Assigned Style Codes & Calculated Costing:
                    </div>
                    <div className="overflow-x-auto max-h-64 bg-white border border-emerald-200 rounded shadow-inner">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-emerald-100 text-emerald-900 sticky top-0">
                          <tr>
                            <th className="p-2.5 border-b font-bold">Source Row</th>
                            <th className="p-2.5 border-b font-bold">Assigned Code</th>
                            <th className="p-2.5 border-b font-bold">Style Name</th>
                            <th className="p-2.5 border-b font-bold text-right">Selling Price</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {bulkResult.created.map((c, idx) => (
                            <tr key={idx} className="hover:bg-slate-50">
                              <td className="p-2.5 text-slate-500 font-mono">Row {c.row}</td>
                              <td className="p-2.5 font-bold font-mono text-emerald-700 bg-emerald-50/50">{c.code}</td>
                              <td className="p-2.5 font-semibold text-slate-800">{c.name}</td>
                              <td className="p-2.5 text-right font-mono font-bold text-slate-700">
                                ₹{c.costing?.suggested_target_price || c.costing?.selling_price || c.costing?.sell || c.costing?.total_cost || 0}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="pt-2 flex justify-end gap-3">
                  <BtnSecondary
                    onClick={() => {
                      setBulkResult(null);
                      setBulkPreview(null);
                      setBulkFile(null);
                      setBulkErrors([]);
                    }}
                  >
                    Upload Another File
                  </BtnSecondary>
                  <BtnPrimary
                    onClick={() => {
                      setBulkOpen(false);
                      setBulkPreview(null);
                      setBulkErrors([]);
                      setBulkResult(null);
                      setBulkFile(null);
                    }}
                  >
                    Done
                  </BtnPrimary>
                </div>
              </div>
            )}

            {bulkPreview && !bulkResult && (
              <div className="space-y-4 border border-slate-200 rounded p-4 bg-white shadow-sm">
                <div className="text-sm font-bold border-b pb-2 flex justify-between items-center text-slate-800">
                  <span>Preview ({bulkPreview.length} valid {bulkPreview.length === 1 ? "style" : "styles"} to import)</span>
                </div>
                <div className="overflow-x-auto text-xs max-h-[40vh]">
                  <table className="w-full text-left">
                    <thead className="bg-slate-100 sticky top-0 shadow-sm text-slate-700 font-semibold">
                      <tr>
                        <th className="p-2 border-b">Row</th>
                        <th className="p-2 border-b">Generated Code</th>
                        <th className="p-2 border-b">Name</th>
                        <th className="p-2 border-b">Category</th>
                        <th className="p-2 border-b text-center">Base Size</th>
                        <th className="p-2 border-b">Insole Mould</th>
                        <th className="p-2 border-b">Sole Mould</th>
                        <th className="p-2 border-b text-center">Carton Pairs</th>
                        <th className="p-2 border-b text-center">Margin %</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {bulkPreview.map((r, i) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="p-2 text-slate-400 font-mono">Row {r.row_number || i + 2}</td>
                          <td className="p-2 font-medium">
                            <span className="italic text-slate-500 font-mono text-[11px] bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                              Auto (SSK_XXXXX)
                            </span>
                          </td>
                          <td className="p-2 font-semibold text-slate-800">{r.name}</td>
                          <td className="p-2 text-slate-600">{r.category}</td>
                          <td className="p-2 text-center text-slate-600">{r.base_size}</td>
                          <td className="p-2 text-slate-600 font-mono text-[11px]">{r.insole_mould_name || "-"}</td>
                          <td className="p-2 text-slate-600 font-mono text-[11px]">{r.sole_mould_name || "-"}</td>
                          <td className="p-2 text-center text-slate-600 font-mono">
                            {r.default_pairs_per_carton ? (r.default_pairs_per_carton.default ?? JSON.stringify(r.default_pairs_per_carton)) : "-"}
                          </td>
                          <td className="p-2 text-center text-slate-600">{r.margin_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="pt-4 border-t flex justify-end gap-3">
                  <BtnSecondary
                    onClick={() => {
                      setBulkPreview(null);
                      setBulkErrors([]);
                      setBulkFile(null);
                    }}
                  >
                    Cancel
                  </BtnSecondary>
                  <BtnPrimary onClick={submitBulk} disabled={bulkUploading || bulkPreview.length === 0}>
                    {bulkUploading ? "Uploading & Generating Codes..." : `Confirm & Upload (${bulkPreview.length} Styles)`}
                  </BtnPrimary>
                </div>
              </div>
            )}
          </div>
        </Drawer>
      )}

      <datalist id="bom-sections-list">
        {SECTIONS.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title}
        message={confirm?.message}
        onConfirm={confirm?.onConfirm}
        onCancel={() => setConfirm(null)}
      />
      {bomStyle && (
        <BomEditorDrawer
          style={bomStyle}
          onClose={() => setBomStyle(null)}
        />
      )}
    </div>
  );
}

function Row({ label, value, bold, color }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-slate-500 uppercase tracking-wider">{label}</span>
      <span
        className={`font-mono ${bold ? "font-bold" : ""}`}
        style={color ? { color } : {}}
      >
        {value}
      </span>
    </div>
  );
}
function CostRow({ label, value, bold, big, small, accent, dim }) {
  return (
    <div
      className={`flex justify-between items-baseline ${big ? "py-1" : "py-0.5"}`}
    >
      <span
        className={`uppercase tracking-wider ${small ? "text-[10px] text-slate-500" : "text-xs text-slate-400"}`}
      >
        {label}
      </span>
      <span
        className={`font-mono ${bold ? "font-bold" : ""} ${big ? "text-xl text-[#C27842]" : "text-sm"} ${accent ? "text-[#C27842]" : dim ? "text-slate-500 italic text-[10px] normal-case tracking-normal" : "text-white"}`}
      >
        {value}
      </span>
    </div>
  );
}
