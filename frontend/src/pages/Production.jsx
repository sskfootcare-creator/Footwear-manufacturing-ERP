import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { SafeImage } from "../components/ImageUploader";
import ImageViewModal from "../components/ImageViewModal";
import { useAuth } from "../lib/auth";
import { FileDown, FileText, Check, UserPlus, Edit3, ClipboardList, X, HardHat, GripVertical, Printer, MessageCircle, AlertTriangle, Clock, Package, Archive, Eye, CheckCircle, Trash2, Save, Plus, ChevronDown, ChevronUp, Layers, Truck, FileSpreadsheet, Loader2, CheckCircle2, AlertCircle, Barcode, Zap, RefreshCw, ChevronRight, Palette, Calendar, ShoppingCart, Maximize2 } from "lucide-react";
import ResponsiveTable from "../components/ResponsiveTable";
import ComponentProductionBoard from "../components/ComponentProductionBoard";

const STAGES = [
  { key: "planning", label: "Planning", color: "#8B5CF6" },
  { key: "procurement", label: "Procurement", color: "#64748B" },
  { key: "cutting", label: "Cutting", color: "#2563EB" },
  { key: "folding", label: "Folding", color: "#0284C7" },
  { key: "attachment", label: "Attachment", color: "#7C3AED" },
  { key: "stitching", label: "Stitching", color: "#C27842" },
  { key: "lasting", label: "Lasting", color: "#A65D24" },
  { key: "sole_pasting", label: "Sole Pasting", color: "#F59E0B" },
  { key: "finishing", label: "Finishing", color: "#16A34A" },
  { key: "qc_pack", label: "QC & Pack", color: "#0D9488" },
  { key: "dispatched", label: "Dispatched", color: "#F97316" },
];

const COMPONENT_LAYERS = {
  upper: ["Upper Top", "Mid Layer / Reinforcement", "Lining"],
  bottom: ["Bottom Layer", "Insole Board + Cushion", "Insole Cover (PU/Leather)"],
  sole: ["Sole"],
  heel_gola: ["Heel / Platform", "Cover / Gola"],
};

// Process sub-tasks specific to each parallel component that can be assigned to other workers
const COMPONENT_SUBTASK_ROLES = {
  upper: [
    { key: "upper.cutting", fallbackKey: "upper", label: "Cutting", icon: "✂" },
    { key: "upper.stitching", fallbackKey: "stitching", label: "Stitching", icon: "🧵" },
    { key: "upper.folding", fallbackKey: null, label: "Folding", icon: "📐" },
    { key: "upper.attachment", fallbackKey: null, label: "Attachment", icon: "🔧" },
  ],
  bottom: [
    { key: "bottom.cutting", fallbackKey: "bottom", label: "Cutting", icon: "✂" },
    { key: "bottom.stitching", fallbackKey: null, label: "Stitching", icon: "🧵" },
    { key: "bottom.stamping", fallbackKey: null, label: "Stamping / Brand Marking", icon: "🏷️" },
    { key: "bottom.assembly", fallbackKey: null, label: "Assembly", icon: "🔧" },
  ],
  sole: [
    { key: "sole.prep", fallbackKey: "sole", label: "Sole Prep", icon: "👟" },
  ],
  heel_gola: [
    { key: "heel_gola.cutting", fallbackKey: "heel_gola", label: "Cover Cutting", icon: "✂" },
    { key: "heel_gola.assembly", fallbackKey: null, label: "Assembly", icon: "🔧" },
  ],
};

const COMPONENT_KARIGAR_ROLES = COMPONENT_SUBTASK_ROLES;

export const isSoleReadyToUse = (group, style) => {
  if (style?.sole_ready_to_use || style?.ready_to_use_sole || style?.sole_type === "ready_to_use") return true;
  const firstRow = group?.rows?.[0];
  if (firstRow?.sole_ready_to_use || firstRow?.ready_to_use_sole) return true;
  const soleSpec = group?.component_specs?.components?.sole || firstRow?.component_specs?.components?.sole;
  if (soleSpec?.is_ready_to_use) return true;
  // Check style BOM
  if (style?.bom && Array.isArray(style.bom)) {
    const soleBom = style.bom.find(b => {
      const sec = (b.section || "").toLowerCase();
      const comp = (b.component || "").toLowerCase();
      return sec.includes("sole") || comp.includes("sole");
    });
    if (soleBom && (soleBom.ready_to_use || soleBom.is_ready_to_use)) return true;
  }
  return false;
};

const ASSIGNMENT_ROLES = [
  // Component parallel tracks (Main component assigned person)
  { key: "upper", label: "Upper Track", category: "component" },
  { key: "bottom", label: "Bottom Track", category: "component" },
  { key: "sole", label: "Sole Track", category: "component" },
  { key: "heel_gola", label: "Heel/Gola Track", category: "component" },
  // Component sub-process roles (assigned to other workers)
  { key: "upper.cutting", label: "Upper — Cutting", category: "component" },
  { key: "upper.stitching", label: "Upper — Stitching", category: "component" },
  { key: "upper.folding", label: "Upper — Folding", category: "component" },
  { key: "upper.attachment", label: "Upper — Attachment", category: "component" },
  { key: "bottom.cutting", label: "Bottom — Cutting", category: "component" },
  { key: "bottom.stitching", label: "Bottom — Stitching", category: "component" },
  { key: "bottom.stamping", label: "Bottom — Stamping / Brand Marking", category: "component" },
  { key: "bottom.brand_marking", label: "Bottom — Stamping / Brand Marking", category: "component" },
  { key: "bottom.assembly", label: "Bottom — Assembly", category: "component" },
  { key: "sole.prep", label: "Sole Prep", category: "component" },
  { key: "heel_gola.cutting", label: "Heel/Gola — Cover Cutting", category: "component" },
  { key: "heel_gola.assembly", label: "Heel/Gola — Assembly", category: "component" },
  // Legacy / prep roles
  { key: "cutting", label: "Cutting", category: "prep" },
  { key: "stitching", label: "Stitching", category: "prep" },
  // Assembly line roles
  { key: "lasting", label: "Lasting", category: "assembly" },
  { key: "sole_pasting", label: "Sole Pasting", category: "assembly" },
  { key: "finishing", label: "Finishing", category: "assembly" },
  { key: "qc_pack", label: "QC & Pack", category: "assembly" },
];

const ASSEMBLY_ROLES = [
  { key: "lasting", label: "Lasting", stageKey: "lasting" },
  { key: "sole_pasting", label: "Sole Pasting", stageKey: "sole_pasting" },
  { key: "finishing", label: "Finishing", stageKey: "finishing" },
  { key: "qc_pack", label: "QC & Pack", stageKey: "qc_pack" },
];

function getComponentAssignment(assignments = {}, compKey) {
  if (!assignments) return null;
  if (compKey === "upper") {
    return assignments["upper"] || assignments["upper.cutting"] || assignments["cutting"] || assignments["stitching"] || null;
  }
  if (compKey === "bottom") {
    return assignments["bottom"] || assignments["bottom.cutting"] || null;
  }
  if (compKey === "sole") {
    return assignments["sole"] || assignments["sole.cutting"] || null;
  }
  if (compKey === "heel_gola") {
    return assignments["heel_gola"] || assignments["heel_gola.cover_cutting"] || null;
  }
  return assignments[compKey] || null;
}

// Stage → most likely role mapping for bulk-drag assignment
const STAGE_TO_ROLE = {
  cutting: "upper",
  folding: "upper",
  attachment: "upper",
  stitching: "upper",
  lasting: "lasting",
  sole_pasting: "sole_pasting",
  finishing: "finishing",
  qc_pack: "qc_pack",
};

const sortSizes = (a, b) => {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b));
};

function groupJobsByColor(jobs) {
  const groups = {};
  for (const j of jobs) {
    const color = j.color || "—";
    const key = `${j.po_number}::${j.style_code}::${color}`;
    if (!groups[key]) {
      groups[key] = {
        key, po_number: j.po_number, po_id: j.po_id, style_id: j.style_id, style_code: j.style_code,
        po_style_code: j.po_style_code || j.mapped_from_sku || j.customer_style_code || j.external_sku || "",
        created_at: j.created_at || j.stage_entered_at || "",
        client_name: j.client_name, description: j.description, delivery_date: j.delivery_date,
        po_date: j.po_date || j.po_created_date || "",
        color, rows: [], sizes: new Set(),
      };
    }
    groups[key].rows.push(j);
    groups[key].sizes.add(String(j.size || "—"));
    if (!groups[key].po_style_code && (j.po_style_code || j.mapped_from_sku || j.customer_style_code || j.external_sku)) {
      groups[key].po_style_code = j.po_style_code || j.mapped_from_sku || j.customer_style_code || j.external_sku;
    }
    if (!groups[key].created_at && (j.created_at || j.stage_entered_at)) {
      groups[key].created_at = j.created_at || j.stage_entered_at;
    }
    if (!groups[key].po_date && (j.po_date || j.po_created_date)) {
      groups[key].po_date = j.po_date || j.po_created_date;
    }
    if (!groups[key].delivery_date && (j.delivery_date || j.expected_delivery_date)) {
      groups[key].delivery_date = j.delivery_date || j.expected_delivery_date;
    }
  }
  return Object.values(groups).map(g => {
    const poStyleCode = g.po_style_code || g.rows.find(r => r.po_style_code || r.mapped_from_sku || r.customer_style_code || r.external_sku)?.po_style_code || g.rows.find(r => r.mapped_from_sku)?.mapped_from_sku || g.rows.find(r => r.customer_style_code)?.customer_style_code || g.rows.find(r => r.external_sku)?.external_sku || "";
    const skuId = (
      g.rows.find(r => r.sku_id)?.sku_id ||
      g.rows.find(r => r.sku)?.sku ||
      g.rows.find(r => r.external_sku)?.external_sku ||
      g.rows.find(r => r.mapped_from_sku)?.mapped_from_sku ||
      g.rows.find(r => r.customer_style_code)?.customer_style_code ||
      poStyleCode ||
      ""
    );
    const hasMappedCode = !!(poStyleCode && String(poStyleCode).trim() && String(poStyleCode).trim().toUpperCase() !== String(g.style_code || "").trim().toUpperCase());
    const styleDisplay = hasMappedCode ? `${g.style_code}/${poStyleCode}` : (g.style_code || "—");

    const rawCreated = g.created_at || g.rows.find(r => r.created_at)?.created_at || g.rows[0]?.created_at || g.rows[0]?.stage_entered_at || "";
    let cardCreatedDate = "";
    if (rawCreated) {
      try {
        const d = new Date(rawCreated);
        if (!isNaN(d.getTime())) {
          const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
          const day = String(d.getDate()).padStart(2, "0");
          const mon = months[d.getMonth()];
          const yr = d.getFullYear();
          cardCreatedDate = `${day} ${mon} ${yr}`;
        }
      } catch (e) {
        cardCreatedDate = String(rawCreated).slice(0, 10);
      }
    }

    const rawPoDate = g.po_date || g.rows.find(r => r.po_date)?.po_date || g.rows[0]?.po_date || "";
    const rawDeliveryDate = g.delivery_date || g.rows.find(r => r.delivery_date)?.delivery_date || g.rows[0]?.delivery_date || "";
    const poDateFormatted = rawPoDate ? String(rawPoDate).slice(0, 10) : "";
    const deliveryDateFormatted = rawDeliveryDate ? String(rawDeliveryDate).slice(0, 10) : "";

    return {
      ...g,
      po_style_code: poStyleCode,
      sku_id: skuId,
      has_mapped_code: hasMappedCode,
      style_display: styleDisplay,
      created_at: rawCreated,
      card_created_date: cardCreatedDate,
      po_date: poDateFormatted,
      delivery_date: deliveryDateFormatted,
      stage: g.rows[0]?.stage,
      sizes: Array.from(g.sizes).sort(sortSizes),
      totalQty: g.rows.reduce((s, r) => s + (r.quantity || 0), 0),
      components: aggregateComponents(g.rows),
      component_tracks: g.rows[0]?.component_tracks || {},
      component_specs: g.rows[0]?.component_specs || {},
      footwear_type: g.rows[0]?.component_specs?.footwear_type || "flat",
      assignments: aggregateAssignments(g.rows),
      overdueHours: aggregateOverdue(g.rows),
    };
  });
}

/**
 * Derived clustering pass ONLY for Archived groups.
 * Clusters archived groups by shared invoice_id (e.g. from merged dispatches).
 * Groups sharing one invoice_id go into one cluster (cluster.groups = [g1, g2, ...]).
 * Groups with their own individual invoice (or no invoice) remain as single-item clusters.
 *
 * @param {Array} groups - array of job groups from groupJobsByColor(archivedJobs)
 * @param {Object} dispatchRecordByJobId - map of job_id -> dispatch_record
 * @param {Array} invoices - array of invoice objects
 * @returns {Array} array of cluster objects: { id, invoice_id, invoice_no, is_merged, groups: [...] }
 */
export function clusterArchivedGroups(groups, dispatchRecordByJobId = {}, invoices = []) {
  if (!groups || !groups.length) return [];

  // Map job_id -> invoice (specifically accounts for merged: true invoices)
  const invoiceByJobId = {};
  for (const inv of invoices || []) {
    if (inv && Array.isArray(inv.job_ids)) {
      for (const jid of inv.job_ids) {
        if (jid) invoiceByJobId[String(jid)] = inv;
      }
    }
  }

  const clustersMap = new Map();

  for (const g of groups) {
    let resolvedInvoiceId = null;
    let resolvedInvoiceNo = null;
    let isMerged = false;
    let matchedInvoice = null;
    let matchedDr = null;

    for (const row of g.rows || []) {
      const inv = invoiceByJobId[String(row.id)];
      if (inv) {
        resolvedInvoiceId = inv.id || String(inv._id);
        resolvedInvoiceNo = inv.invoice_no;
        isMerged = Boolean(inv.merged);
        matchedInvoice = inv;
        break;
      }

      const dr = dispatchRecordByJobId[row.id];
      if (dr) {
        resolvedInvoiceId = dr.invoice_id || dr.id;
        resolvedInvoiceNo = dr.invoice_no;
        matchedDr = dr;
        break;
      }
    }

    if (!resolvedInvoiceId) {
      for (const row of g.rows || []) {
        if (row.invoice_id) {
          resolvedInvoiceId = String(row.invoice_id);
          resolvedInvoiceNo = row.invoice_no || resolvedInvoiceNo;
          break;
        }
        if (row.invoice_no) {
          resolvedInvoiceId = String(row.invoice_no);
          resolvedInvoiceNo = row.invoice_no;
          break;
        }
      }
    }
    if (!resolvedInvoiceId && g.invoice_id) {
      resolvedInvoiceId = String(g.invoice_id);
      resolvedInvoiceNo = g.invoice_no || resolvedInvoiceNo;
    }

    const clusterKey = resolvedInvoiceId ? `inv:${resolvedInvoiceId}` : `group:${g.key}`;

    if (!clustersMap.has(clusterKey)) {
      clustersMap.set(clusterKey, {
        id: clusterKey,
        invoice_id: resolvedInvoiceId,
        invoice_no: resolvedInvoiceNo,
        is_merged: isMerged,
        invoice: matchedInvoice,
        dispatch_record: matchedDr,
        groups: [g],
      });
    } else {
      const cluster = clustersMap.get(clusterKey);
      cluster.groups.push(g);
      cluster.is_merged = true; // Multiple groups share this invoice
      if (matchedInvoice && !cluster.invoice) cluster.invoice = matchedInvoice;
      if (matchedDr && !cluster.dispatch_record) cluster.dispatch_record = matchedDr;
    }
  }

  return Array.from(clustersMap.values());
}

function aggregateComponents(rows) {
  const all = (key) => rows.every(r => r.components?.[key]);
  const heelReady = rows.every(r => r.component_tracks?.heel_gola?.status === "ready");
  return {
    upper_done: all("upper_done"),
    bottom_done: all("bottom_done"),
    sole_done: all("sole_done"),
    heel_gola_done: heelReady,
  };
}

// take assignment from the first row for display (all rows in the group share)
function aggregateAssignments(rows) {
  const r0 = rows[0] || {};
  return r0.assignments || {};
}

// Compute the worst overdue hours across all rows in a group; 0 means not overdue.
function aggregateOverdue(rows) {
  let worst = 0;
  const nowMs = Date.now();
  for (const r of rows) {
    if (r.stage === "dispatched" || !r.stage_deadline) continue;
    const dl = new Date(r.stage_deadline).getTime();
    if (Number.isNaN(dl)) continue;
    const hrs = (nowMs - dl) / 3600000;
    if (hrs > worst) worst = hrs;
  }
  return Math.round(worst * 10) / 10;
}

const triggerDownload = (blobData, filename, mimeType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") => {
  const safeFilename = filename.replace(/[\/\\]/g, "-");
  const blob = new Blob([blobData], { type: mimeType });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = safeFilename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
};

const formatError = (err) => {
  if (!err) return "";
  if (typeof err === "string") return err;
  if (Array.isArray(err)) {
    return err.map(e => {
      const field = e.loc ? e.loc.filter(l => l !== "body" && l !== "query").join(".") : "";
      return (field ? `[${field}] ` : "") + (e.msg || JSON.stringify(e));
    }).join(", ");
  }
  if (typeof err === "object") {
    return err.message || err.detail || JSON.stringify(err);
  }
  return String(err);
};

export default function Production() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [styles, setStyles] = useState([]);
  const [selected, setSelected] = useState({});
  const [procSelected, setProcSelected] = useState({});
  const [qcPackSelected, setQcPackSelected] = useState({});
  const [shortageModal, setShortageModal] = useState(null);
  const [merging, setMerging] = useState(false);
  const [assignFor, setAssignFor] = useState(null);
  const [qtyFor, setQtyFor] = useState(null);
  const [dockOpen, setDockOpen] = useState(false);
  const [draggingWorker, setDraggingWorker] = useState(null);
  const [dropZone, setDropZone] = useState(null);
  const [bulkConfirm, setBulkConfirm] = useState(null);
  const [waFor, setWaFor] = useState(null);
  const [viewArchive, setViewArchive] = useState(false);
  const [boardMode, setBoardMode] = useState("assembly"); // "assembly" | "component"
  // Stage 4: archive state — summaries only, lazy-loaded, paginated
  const [archiveSummaries, setArchiveSummaries] = useState([]);
  const [archiveMeta, setArchiveMeta] = useState({ total: 0, page: 1, pages: 1, page_size: 50 });
  const [archiveFilters, setArchiveFilters] = useState({ from_date: "", to_date: "", style_code: "", po_number: "", karigar_name: "", color: "" });
  const [archivePage, setArchivePage] = useState(1);
  const [archiveLoaded, setArchiveLoaded] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [detailFor, setDetailFor] = useState(null);
  const [packingFor, setPackingFor] = useState(null); // {kind:'single'|'merged', group?, jobs?}
  const [cartonPackFor, setCartonPackFor] = useState(null); // job group
  const [dispatchFor, setDispatchFor] = useState(null);     // group to dispatch
  const [savedPackingLists, setSavedPackingLists] = useState([]);
  const [dispatchRecords, setDispatchRecords] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [dispatchDetailFor, setDispatchDetailFor] = useState(null);
  const [planningAllocationFor, setPlanningAllocationFor] = useState(null);
  const [previewImageModal, setPreviewImageModal] = useState(null);
  const { user } = useAuth();
  const canEdit = ["admin", "manager", "production"].includes(user?.role);

  const load = async () => {
    const [j, w, s, pl, dr, invs, vends] = await Promise.all([
      http.get("/production/jobs"),
      http.get("/workers"),
      http.get("/styles"),
      http.get("/packing-lists"),
      http.get("/dispatch-records?limit=1000"),
      http.get("/invoices").catch(() => ({ data: [] })),
      http.get("/vendors").catch(() => ({ data: [] })),
    ]);
    setJobs(j.data); setWorkers(w.data); setStyles(s.data);
    setSavedPackingLists(pl.data || []);
    setDispatchRecords(dr.data || []);
    setInvoices(invs.data || []);
    setVendors(vends.data || []);
  };
  useEffect(() => { load(); }, []);

  // Stage 4: load archive summaries (lazy, only when tab is first opened or filters/page change)
  const loadArchive = useCallback(async (filters = archiveFilters, page = archivePage) => {
    setArchiveLoading(true);
    try {
      const params = new URLSearchParams({ page, page_size: 50 });
      if (filters.from_date) params.set("from_date", filters.from_date);
      if (filters.to_date) params.set("to_date", filters.to_date);
      if (filters.style_code) params.set("style_code", filters.style_code);
      if (filters.po_number) params.set("po_number", filters.po_number);
      if (filters.karigar_name) params.set("karigar_name", filters.karigar_name);
      if (filters.color) params.set("color", filters.color);
      const res = await http.get(`/production/archive?${params}`);
      const items = Array.isArray(res.data) ? res.data : (res.data?.items || []);
      setArchiveSummaries(items);
      setArchiveMeta({
        total: Array.isArray(res.data) ? res.data.length : (res.data?.total || 0),
        page: res.data?.page || 1,
        pages: res.data?.pages || 1,
        page_size: res.data?.page_size || 50,
      });
      setArchiveLoaded(true);
    } catch (e) {
      console.error("Archive load error", e);
    } finally {
      setArchiveLoading(false);
    }
  }, [archiveFilters, archivePage]);

  // Trigger load when archive tab opens for the first time
  useEffect(() => {
    if (viewArchive && !archiveLoaded) {
      loadArchive(archiveFilters, 1);
    }
  }, [viewArchive, archiveLoaded, loadArchive, archiveFilters]);

  const dispatchRecordByJobId = useMemo(() => {
    const m = {};
    for (const dr of dispatchRecords) {
      if (dr.job_ids) {
        for (const jid of dr.job_ids) {
          m[jid] = dr;
        }
      }
    }
    return m;
  }, [dispatchRecords]);

  const downloadDispatchFile = async (drId, type, filename, mimeType) => {
    try {
      const res = await http.get(`/dispatch-records/${drId}/${type}`, { responseType: "blob" });
      triggerDownload(res.data, filename, mimeType);
    } catch (e) {
      alert("Download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const styleByCode = useMemo(() => {
    const m = {};
    for (const s of styles) m[s.code] = s;
    return m;
  }, [styles]);

  const stageDataByStageKey = useMemo(() => {
    const map = {};
    for (const s of STAGES) {
      const stageJobs = jobs.filter((j) => j.stage === s.key);
      const groups = groupJobsByColor(stageJobs);
      const totalQty = stageJobs.reduce((sum, j) => sum + (j.quantity || 0), 0);
      map[s.key] = { stageJobs, groups, totalQty };
    }
    return map;
  }, [jobs]);

  // Stage 4: archive count comes from server total
  const archivedGroupsCount = archiveMeta.total;

  const allGroups = useMemo(() => {
    return groupJobsByColor(jobs);
  }, [jobs]);


  const printCard = async (group, variant = "dual") => {
    try {
      const res = await http.post(`/production/card.pdf?variant=${variant}`,
        { job_ids: group.rows.map(r => r.id), variant }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Print failed: " + (e.response?.data?.detail || e.message)); }
  };

  // Open packing list modal for a single group OR a merged set of jobs.
  const openPackingForGroup = (group) => setPackingFor({ kind: "single", group });
  const openPackingMerged = () => {
    const groupsArr = Object.values(selected);
    if (!groupsArr.length) return;
    const firstPo = groupsArr[0].po_number;
    if (groupsArr.some((g) => g.po_number !== firstPo)) {
      alert("Cannot merge cards from different POs.");
      return;
    }
    const jobIds = new Set(groupsArr.flatMap(g => g.rows.map(r => r.id)));
    const jobsFlat = jobs.filter(j => jobIds.has(j.id));
    setPackingFor({ kind: "merged", jobs: jobsFlat });
  };

  // Submit the modal — actually generate + download + persist.
  const submitPacking = async (form) => {
    try {
      if (packingFor.kind === "single") {
        const g = packingFor.group;
        const res = await http.post("/packing-lists/job",
          { po_id: g.po_id, job_ids: g.rows.map(r => r.id), ...form },
          { responseType: "blob" });
        triggerDownload(res.data, `PackingList-${g.po_number}-${g.style_code}-${(g.color || "color").replace(/\s+/g, "")}.xlsx`);
      } else {
        const job_ids = packingFor.jobs.map(j => j.id);
        const res = await http.post("/packing-lists/merged",
          { job_ids, ...form },
          { responseType: "blob" });
        triggerDownload(res.data, `PackingList-MERGED-${new Date().toISOString().slice(0, 10)}.xlsx`);
      }
      setPackingFor(null);
      load();
    } catch (e) {
      alert("Packing list failed: " + formatError(e.response?.data?.detail || e.message));
    }
  };

  const reDownloadSavedPacking = async (pl) => {
    try {
      const res = await http.get(`/packing-lists/${pl.id}/file`, { responseType: "blob" });
      const fname = pl.merged
        ? `PackingList-MERGED-${(pl.created_at || "").slice(0, 10)}.xlsx`
        : `PackingList-${pl.po_number}-${(pl.created_at || "").slice(0, 10)}.xlsx`;
      triggerDownload(res.data, fname);
    } catch (e) {
      alert("Download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  // WhatsApp share: download production card PDF AND open WhatsApp Web with a
  // pre-filled message to the chosen karigar. The user drag-drops the downloaded
  // PDF into the chat (browsers cannot programmatically attach files to wa.me).
  const shareViaWhatsApp = async (group, phone) => {
    try {
      const res = await http.post("/production/card.pdf?variant=dual",
        { job_ids: group.rows.map(r => r.id), variant: "dual" }, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      // trigger download with a descriptive filename
      const a = document.createElement("a");
      a.href = url;
      const safePo = (group.po_number || "").replace(/[\/\\]/g, "-");
      a.download = `ProductionCard_${safePo}_${group.style_code}_${(group.color || "color").replace(/\s+/g, "")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      // build message
      const sizeBreak = group.sizes.map(sz => {
        const row = group.rows.find(r => String(r.size || "—") === sz);
        return `${sz}:${row?.quantity || 0}`;
      }).join("  ");
      const lines = [
        `SSK FOOTCARE - Production Card`,
        `PO: ${group.po_number}`,
        `Style: ${group.style_display || group.style_code}  Color: ${group.color}`,
        `Total: ${group.totalQty} pairs`,
        `Sizes: ${sizeBreak}`,
        group.card_created_date ? `Created: ${group.card_created_date}` : "",
        group.delivery_date ? `Delivery: ${group.delivery_date}` : "",
        ``,
        `Please process as per the attached production card PDF (auto-downloaded).`,
      ].filter(Boolean);
      const text = encodeURIComponent(lines.join("\n"));
      // normalise phone (keep digits & leading +). wa.me prefers no '+' or leading 0.
      let cleaned = (phone || "").replace(/[^\d+]/g, "");
      if (cleaned.startsWith("+")) cleaned = cleaned.slice(1);
      if (cleaned.startsWith("0")) cleaned = cleaned.slice(1);
      // If only 10 digits, assume India +91
      if (/^\d{10}$/.test(cleaned)) cleaned = "91" + cleaned;
      const waUrl = cleaned
        ? `https://wa.me/${cleaned}?text=${text}`
        : `https://wa.me/?text=${text}`;
      window.open(waUrl, "_blank");
      setWaFor(null);
    } catch (e) { alert("WhatsApp share failed: " + (e.response?.data?.detail || e.message)); }
  };

  const moveGroup = async (group, nextStage) => {
    try {
      await Promise.all(group.rows.map(j => http.patch(`/production/jobs/${j.id}`, { stage: nextStage })));
      load();
    } catch (e) {
      alert("Stage transition failed: " + (e.response?.data?.detail || e.message));
    }
  };
  const handleMoveGroup = (group, nextStage) => {
    if (nextStage === "qc_pack") {
      setCartonPackFor(group);
    } else {
      moveGroup(group, nextStage);
    }
  };
  const toggleComponent = async (group, key, val) => {
    if (key === "heel_gola_done") {
      await Promise.all(group.rows.map(j =>
        http.patch(`/production/jobs/${j.id}/component-stage`, {
          component: "heel_gola",
          stage: val ? "ready" : (j.component_specs?.components?.heel_gola?.stages?.[0] || "cover_cutting"),
          completed_qty: j.quantity,
        })
      ));
    } else {
      await Promise.all(group.rows.map(j => http.patch(`/production/jobs/${j.id}/components`, { [key]: val })));
    }
    load();
  };
  const assignWorker = async (group, role, workerId, rate, overwrite = false) => {
    if ((role === "sole" || role.startsWith("sole.")) && isSoleReadyToUse(group, styleByCode[group.style_code])) {
      alert("Sub-task assignment is disabled: this style uses a ready-to-use sole.");
      return;
    }

    const rateNum = (rate === undefined || rate === "" || rate === null) ? null : Number(rate);
    const worker = workers.find(w => w.id === workerId);
    const workerName = worker?.name || "";
    const effectiveRate = rateNum !== null ? rateNum : (worker?.rate_per_pair || 0);

    try {
      if (role.includes(".")) {
        // Sub-task assignment (e.g. upper.cutting, upper.stitching)
        const [comp, substage] = role.split(".");
        await Promise.all(group.rows.map(j =>
          http.patch(`/production/jobs/${j.id}/sub-task-assignment`, {
            component: comp,
            substage,
            worker_id: workerId || null,
            rate_per_pair: rateNum,
            job_ids: [j.id],
          })
        ));
        group.rows.forEach(r => {
          r.assignments = r.assignments || {};
          if (workerId) {
            r.assignments[role] = {
              worker_id: workerId,
              worker_name: workerName,
              rate_per_pair: effectiveRate,
              assigned_at: new Date().toISOString(),
            };
          } else {
            delete r.assignments[role];
          }
        });
        if (group.assignments) {
          if (workerId) {
            group.assignments[role] = {
              worker_id: workerId,
              worker_name: workerName,
              rate_per_pair: effectiveRate,
              assigned_at: new Date().toISOString(),
            };
          } else {
            delete group.assignments[role];
          }
        }
      } else if (["upper", "bottom", "sole", "heel_gola"].includes(role)) {
        // Component-level assignment: bulk-assigns all unassigned subtasks under this component
        if (workerId) {
          await Promise.all(group.rows.map(j =>
            http.post(`/production/jobs/${j.id}/components/${role}/bulk-assign`, {
              worker_id: workerId,
              rate_per_pair: rateNum,
              overwrite: Boolean(overwrite),
              job_ids: [j.id],
            })
          ));
          const compStages = group.component_specs?.components?.[role]?.stages || (
            role === "upper" ? ["cutting", "stitching", "folding", "attachment"] :
            role === "bottom" ? ["cutting", "stitching", "stamping"] :
            []
          );
          group.rows.forEach(r => {
            r.assignments = r.assignments || {};
            r.assignments[role] = {
              worker_id: workerId,
              worker_name: workerName,
              rate_per_pair: effectiveRate,
              assigned_at: new Date().toISOString(),
            };
            compStages.forEach(st => {
              const stKey = `${role}.${st}`;
              if (overwrite || !r.assignments[stKey]?.worker_id) {
                r.assignments[stKey] = {
                  worker_id: workerId,
                  worker_name: workerName,
                  rate_per_pair: effectiveRate,
                  assigned_at: new Date().toISOString(),
                };
              }
            });
          });
          if (group.assignments) {
            group.assignments[role] = {
              worker_id: workerId,
              worker_name: workerName,
              rate_per_pair: effectiveRate,
              assigned_at: new Date().toISOString(),
            };
            compStages.forEach(st => {
              const stKey = `${role}.${st}`;
              if (overwrite || !group.assignments[stKey]?.worker_id) {
                group.assignments[stKey] = {
                  worker_id: workerId,
                  worker_name: workerName,
                  rate_per_pair: effectiveRate,
                  assigned_at: new Date().toISOString(),
                };
              }
            });
          }
        } else {
          // Unassign main component
          await Promise.all(group.rows.map(j =>
            http.patch(`/production/jobs/${j.id}/assignment`, {
              role, worker_id: null, rate_per_pair: null,
            })
          ));
          group.rows.forEach(r => {
            if (r.assignments) delete r.assignments[role];
          });
          if (group.assignments) delete group.assignments[role];
        }
      } else {
        // Assembly roles: lasting, sole_pasting, finishing, qc_pack
        await Promise.all(group.rows.map(j =>
          http.patch(`/production/jobs/${j.id}/assignment`, {
            role, worker_id: workerId || null,
            rate_per_pair: rateNum,
          })
        ));
        group.rows.forEach(r => {
          r.assignments = r.assignments || {};
          if (workerId) {
            r.assignments[role] = {
              worker_id: workerId,
              worker_name: workerName,
              rate_per_pair: effectiveRate,
              assigned_at: new Date().toISOString(),
            };
          } else {
            delete r.assignments[role];
          }
        });
        if (group.assignments) {
          if (workerId) {
            group.assignments[role] = {
              worker_id: workerId,
              worker_name: workerName,
              rate_per_pair: effectiveRate,
              assigned_at: new Date().toISOString(),
            };
          } else {
            delete group.assignments[role];
          }
        }
      }
    } catch (err) {
      console.error("Assignment error:", err);
      alert("Failed to assign: " + (err.response?.data?.detail || err.message));
    } finally {
      setAssignFor(null);
      load();
    }
  };
  const saveQuantity = async (rowId, body) => {
    await http.patch(`/production/jobs/${rowId}/quantity`, body);
    setQtyFor(null);
    load();
  };

  // Dispatched merge invoice
  const toggleSelect = (group) => setSelected(s => {
    const next = { ...s };
    if (next[group.key]) {
      delete next[group.key];
    } else {
      const values = Object.values(next);
      if (values.length > 0) {
        const first = values[0];
        if (first.po_number !== group.po_number) {
          alert("Cannot merge cards from different POs.");
          return s;
        }
      }
      next[group.key] = group;
    }
    return next;
  });
  const downloadGroupInvoice = async (group) => {
    const jobIds = group.rows ? group.rows.map((r) => r.id) : [];

    // 1. Check dispatchRecordByJobId for any matching dispatch records
    const matchingRecordsMap = new Map();
    for (const id of jobIds) {
      const dr = dispatchRecordByJobId[id];
      if (dr) {
        matchingRecordsMap.set(dr.id, dr);
      }
    }

    if (matchingRecordsMap.size > 1) {
      console.warn("Multiple distinct dispatch records found for job group:", Array.from(matchingRecordsMap.keys()));
      alert("Warning: Jobs in this card were dispatched across multiple separate dispatch batches.");
    }

    const matchedDr = Array.from(matchingRecordsMap.values())[0];

    // 2. If dispatch record is found, re-download the exact dispatch invoice
    if (matchedDr) {
      const invNo = matchedDr.invoice_no || "dispatch";
      await downloadDispatchFile(matchedDr.id, "invoice", `Invoice-${invNo}.pdf`, "application/pdf");
      return;
    }

    // 3. Fallback: if no dispatch record is found, call /invoices/job
    try {
      const res = await http.post("/invoices/job", { po_id: group.po_id, job_ids: jobIds }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Invoice failed: " + (e.response?.data?.detail || e.message)); }
  };
  const downloadMergedInvoice = async () => {
    const groups = Object.values(selected); if (!groups.length) return;
    const firstPo = groups[0].po_number;
    if (groups.some((g) => g.po_number !== firstPo)) {
      alert("Cannot merge items from different POs.");
      return;
    }
    const byPo = {};
    for (const g of groups) {
      if (!byPo[g.po_id]) byPo[g.po_id] = { po_id: g.po_id, job_ids: [] };
      byPo[g.po_id].job_ids.push(...g.rows.map(r => r.id));
    }
    try {
      setMerging(true);
      const res = await http.post("/invoices/merged", { entries: Object.values(byPo) }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
      setSelected({});
    } catch (e) { alert("Merged failed: " + (e.response?.data?.detail || e.message)); }
    finally { setMerging(false); }
  };

  const downloadMergedLabels = async () => {
    const groups = Object.values(selected); if (!groups.length) return;
    const firstPo = groups[0].po_number;
    if (groups.some((g) => g.po_number !== firstPo)) {
      alert("Cannot merge items from different POs.");
      return;
    }
    const jobIds = groups.flatMap(g => g.rows.map(r => r.id)).join(",");
    try {
      setMerging(true);
      const res = await http.get(`/production/jobs/carton-labels?job_ids=${jobIds}`, { responseType: "blob" });
      const first = groups[0];
      const safePo = (first.po_number || "merged").replace(/[\/\\]/g, "-");
      triggerDownload(res.data, `MergedLabels-${safePo}-${first.style_code}.pdf`, "application/pdf");
      setSelected({});
    } catch (e) {
      alert("Merged Labels download failed: " + formatError(e.response?.data?.detail || e.message));
    } finally { setMerging(false); }
  };

  const downloadMergedCartonList = async () => {
    const groups = Object.values(selected); if (!groups.length) return;
    const firstPo = groups[0].po_number;
    if (groups.some((g) => g.po_number !== firstPo)) {
      alert("Cannot merge items from different POs.");
      return;
    }
    const jobIds = groups.flatMap(g => g.rows.map(r => r.id)).join(",");
    try {
      setMerging(true);
      const res = await http.get(`/production/jobs/carton-list?job_ids=${jobIds}`, { responseType: "blob" });
      const first = groups[0];
      const safePo = (first.po_number || "merged").replace(/[\/\\]/g, "-");
      triggerDownload(res.data, `MergedCartonList-${safePo}-${first.style_code}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
      setSelected({});
    } catch (e) {
      alert("Merged Carton List download failed: " + formatError(e.response?.data?.detail || e.message));
    } finally { setMerging(false); }
  };

  const isSelectionDisabled = (group) => {
    const values = Object.values(selected);
    if (values.length === 0) return false;
    const first = values[0];
    return first.po_number !== group.po_number;
  };

  // QC & Pack: select cards & generate merged dispatch documents for same PO
  const toggleQcPackSelect = (group) => setQcPackSelected(s => {
    const next = { ...s };
    if (next[group.key]) {
      delete next[group.key];
    } else {
      const values = Object.values(next);
      if (values.length > 0) {
        const first = values[0];
        if (first.po_number !== group.po_number) {
          alert(`Cannot merge cards from different POs. All selected cards must share PO: ${first.po_number}`);
          return s;
        }
      }
      next[group.key] = group;
    }
    return next;
  });

  const isQcPackSelectionDisabled = (group) => {
    const values = Object.values(qcPackSelected);
    if (values.length === 0) return false;
    const first = values[0];
    return first.po_number !== group.po_number;
  };

  // Procurement: select cards & generate material requirement
  const toggleProcSelect = (group) => setProcSelected(s => {
    const next = { ...s }; if (next[group.key]) delete next[group.key]; else next[group.key] = group; return next;
  });
  const downloadMaterialRequirement = async (groups, label, splitByColor = true) => {
    const job_ids = [];
    groups.forEach(g => g.rows.forEach(r => job_ids.push(r.id)));
    const isMerged = groups.length > 1;
    try {
      const res = await http.post("/procurement/requirement.pdf",
        {
          job_ids,
          scope_label: label || (isMerged ? `${groups.length} procurement cards` : `${groups.length} card(s)`),
          split_by_color: isMerged ? false : splitByColor,
          is_merged: isMerged,
        },
        { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Material requirement failed: " + friendlyAxiosError(e)); }
  };

  const checkShortage = async (groups) => {
    const job_ids = [];
    groups.forEach(g => g.rows.forEach(r => job_ids.push(r.id)));
    setShortageModal({ loading: true, shortage: [] });
    try {
      const { data } = await http.post("/inventory/shortage", { job_ids });
      setShortageModal({ loading: false, shortage: data.shortage || [] });
    } catch (e) {
      alert("Shortage calculation failed: " + (e.response?.data?.detail || e.message));
      setShortageModal(null);
    }
  };

  // ---- Drag & Drop bulk assignment ----
  const onDragStartWorker = (w) => (e) => {
    setDraggingWorker(w);
    try { e.dataTransfer.setData("text/plain", w.id); } catch {}
    e.dataTransfer.effectAllowed = "copy";
  };
  const onDragEndWorker = () => { setDraggingWorker(null); setDropZone(null); };
  const onDragOverStage = (stageKey) => (e) => {
    if (!draggingWorker) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDropZone(stageKey);
  };
  const onDropStage = (stageKey) => (e) => {
    e.preventDefault();
    const role = STAGE_TO_ROLE[stageKey];
    const stageInfo = stageDataByStageKey[stageKey] || { stageJobs: [], groups: [] };
    if (!role || !draggingWorker || !stageInfo.stageJobs.length) { setDropZone(null); return; }
    setBulkConfirm({
      worker: draggingWorker, role, stageKey,
      job_ids: stageInfo.stageJobs.map(j => j.id),
      stage_label: STAGES.find(s => s.key === stageKey)?.label || stageKey,
      card_count: stageInfo.groups.length,
      rate: draggingWorker.rate_per_pair,
    });
    setDropZone(null);
  };
  const runBulkAssign = async () => {
    if (!bulkConfirm) return;
    try {
      await http.post("/production/bulk-assign", {
        job_ids: bulkConfirm.job_ids,
        role: bulkConfirm.role,
        worker_id: bulkConfirm.worker.id,
        rate_per_pair: bulkConfirm.rate === "" || bulkConfirm.rate === null || bulkConfirm.rate === undefined
          ? null : Number(bulkConfirm.rate),
      });
      setBulkConfirm(null);
      load();
    } catch (e) { alert("Bulk assignment failed: " + (e.response?.data?.detail || e.message)); }
  };

  const archiveDispatchedJobs = async (jobIds, label = "card(s)") => {
    if (!jobIds || jobIds.length === 0) return;
    const ok = window.confirm(`Verify and move ${label} to Archive?`);
    if (!ok) return;
    try {
      const res = await http.post("/production/jobs/archive", { job_ids: jobIds });
      const count = res.data?.archived_count || jobIds.length;
      setSelected({});
      setQcPackSelected({});
      await load();
      alert(`Successfully verified and moved ${count} card(s) to Archive.`);
    } catch (e) {
      alert("Archiving failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const dispatchedCount = Object.keys(selected).length;
  const procSelectedCount = Object.keys(procSelected).length;
  const qcPackSelectedCount = Object.keys(qcPackSelected).length;

  return (
    <div>
      <PageHeader
        title="Production Floor"
        subtitle="Manufacturing / Kanban"
        testId="production-header"
        action={
          <div className="flex gap-2 items-center">
            {/* Board Mode Switcher */}
            <div className="inline-flex rounded border border-slate-300 p-0.5 bg-slate-100 mr-1 shadow-xs">
              <button
                type="button"
                onClick={() => { setBoardMode("assembly"); setViewArchive(false); }}
                className={`text-xs font-bold uppercase tracking-wider px-3 py-1.5 rounded transition-all ${
                  !viewArchive && boardMode === "assembly"
                    ? "bg-[#0F172A] text-white shadow-xs"
                    : "text-slate-700 hover:text-slate-900"
                }`}
                data-testid="toggle-assembly-board"
              >
                Assembly &amp; Finishing
              </button>
              <button
                type="button"
                onClick={() => { setBoardMode("component"); setViewArchive(false); }}
                className={`text-xs font-bold uppercase tracking-wider px-3 py-1.5 rounded transition-all ${
                  !viewArchive && boardMode === "component"
                    ? "bg-[#C27842] text-white shadow-xs"
                    : "text-slate-700 hover:text-slate-900"
                }`}
                data-testid="toggle-component-board"
              >
                Component Production
              </button>
            </div>

            {canEdit && (
              <button onClick={() => setDockOpen(d => !d)} data-testid="toggle-karigar-dock"
                className={`text-xs font-bold uppercase tracking-wider px-3 py-2 border-2 flex items-center gap-1 ${dockOpen ? "bg-[#C27842] text-white border-[#C27842]" : "bg-white text-slate-900 border-slate-300 hover:border-[#0F172A]"}`}>
                <HardHat className="w-3.5 h-3.5 inline" />
                <span className="hidden sm:inline">Karigars</span>
              </button>
            )}
            <button onClick={() => setViewArchive(v => !v)} data-testid="toggle-archive"
              className={`text-xs font-bold uppercase tracking-wider px-3 py-2 border-2 flex items-center gap-1 ${viewArchive ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white text-slate-900 border-slate-300 hover:border-[#0F172A]"}`}>
              <Archive className="w-3.5 h-3.5 inline" />
              <span className="hidden sm:inline">Archive ({archivedGroupsCount})</span>
              <span className="inline sm:hidden">({archivedGroupsCount})</span>
            </button>
            {procSelectedCount > 0 && (
              <>
                <BtnPrimary onClick={() => { downloadMaterialRequirement(Object.values(procSelected), `${procSelectedCount} procurement cards`, false); setProcSelected({}); }} data-testid="merged-mr-btn" className="px-3 sm:px-4 flex items-center gap-1">
                  <ClipboardList className="w-3.5 h-3.5 inline" />
                  <span className="hidden sm:inline">Material Requirement ({procSelectedCount})</span>
                  <span className="inline sm:hidden">({procSelectedCount})</span>
                </BtnPrimary>
                <BtnSecondary onClick={() => checkShortage(Object.values(procSelected))} data-testid="check-shortage-btn" className="!bg-amber-50 hover:!bg-amber-100 border-amber-300 text-amber-900 px-3 sm:px-4 flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5 inline text-amber-600 animate-pulse" />
                  <span className="hidden sm:inline">Check Shortage ({procSelectedCount})</span>
                  <span className="inline sm:hidden">({procSelectedCount})</span>
                </BtnSecondary>
              </>
            )}
            {qcPackSelectedCount > 0 && (
              <BtnPrimary
                onClick={() => setDispatchFor({ groups: Object.values(qcPackSelected) })}
                data-testid="qc-pack-merge-dispatch-btn"
                className="bg-[#0D9488] border-[#0D9488] hover:bg-[#0B7A70] text-white px-3 sm:px-4 flex items-center gap-1.5 shadow-sm"
              >
                <Truck className="w-3.5 h-3.5 inline" />
                <span className="hidden sm:inline">Merge Dispatch Docs ({qcPackSelectedCount})</span>
                <span className="inline sm:hidden">Dispatch ({qcPackSelectedCount})</span>
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={downloadMergedInvoice} disabled={merging} data-testid="merged-invoice-btn" className="px-3 sm:px-4 flex items-center gap-1">
                <FileDown className="w-3.5 h-3.5 inline" />
                <span className="hidden sm:inline">{merging ? "..." : `Merge Invoice (${dispatchedCount})`}</span>
                <span className="inline sm:hidden">({dispatchedCount})</span>
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={openPackingMerged} data-testid="merged-packing-btn"
                className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36] px-3 sm:px-4 flex items-center gap-1">
                <Package className="w-3.5 h-3.5 inline" />
                <span className="hidden sm:inline">Merge Packing ({dispatchedCount})</span>
                <span className="inline sm:hidden">({dispatchedCount})</span>
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={downloadMergedLabels} disabled={merging} data-testid="merged-labels-btn"
                className="bg-[#0D9488] border-[#0D9488] hover:bg-[#0B7A70] px-3 sm:px-4 flex items-center gap-1">
                <FileDown className="w-3.5 h-3.5 inline" />
                <span className="hidden sm:inline">{merging ? "..." : `Merge Labels (${dispatchedCount})`}</span>
                <span className="inline sm:hidden">({dispatchedCount})</span>
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={downloadMergedCartonList} disabled={merging} data-testid="merged-carton-list-btn"
                className="bg-[#EAB308] border-[#EAB308] hover:bg-[#CA8A04] text-white px-3 sm:px-4 flex items-center gap-1">
                <FileDown className="w-3.5 h-3.5 inline" />
                <span className="hidden sm:inline">{merging ? "..." : `Merge Carton List (${dispatchedCount})`}</span>
                <span className="inline sm:hidden">({dispatchedCount})</span>
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary
                onClick={() => {
                  const sel = Object.values(selected);
                  const allJids = sel.flatMap(g => (g.rows || []).map(r => r.id));
                  archiveDispatchedJobs(allJids, `${sel.length} merged production card(s)`);
                }}
                data-testid="archive-selected-dispatched-btn"
                className="bg-[#0F172A] border-[#0F172A] hover:bg-slate-800 text-white px-3 sm:px-4 flex items-center gap-1.5 shadow-sm"
              >
                <Archive className="w-3.5 h-3.5 inline text-amber-400" />
                <span className="hidden sm:inline">Verify &amp; Move to Archive ({dispatchedCount})</span>
                <span className="inline sm:hidden">Archive ({dispatchedCount})</span>
              </BtnPrimary>
            )}
          </div>
        }
      />

      <div className="p-4 sm:p-8">
        {viewArchive ? (
          <ArchivePanel
            summaries={archiveSummaries}
            meta={archiveMeta}
            filters={archiveFilters}
            loading={archiveLoading}
            onFiltersChange={(newFilters) => {
              setArchiveFilters(newFilters);
              setArchivePage(1);
              loadArchive(newFilters, 1);
            }}
            onPageChange={(p) => {
              setArchivePage(p);
              loadArchive(archiveFilters, p);
            }}
            styleByCode={styleByCode}
            onPrint={printCard}
            onPacking={openPackingForGroup}
            onViewDetails={(g) => setDetailFor(g)}
            onViewDispatchDetails={(item) => setDispatchDetailFor(item)}
            savedPackingLists={savedPackingLists}
            onReDownloadPacking={reDownloadSavedPacking}
            dispatchRecordByJobId={dispatchRecordByJobId}
            onDownloadDispatchFile={downloadDispatchFile}
            onDownloadInvoice={downloadGroupInvoice}
            invoices={invoices}
            onPreviewImage={(img) => setPreviewImageModal(img)}
          />
        ) : boardMode === "component" ? (
          <ComponentProductionBoard
            jobs={jobs}
            groups={allGroups}
            workers={workers}
            styleByCode={styleByCode}
            canEdit={canEdit}
            onRefresh={load}
          />
        ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {STAGES.map((s) => {
              const { stageJobs, groups, totalQty } = stageDataByStageKey[s.key] || { stageJobs: [], groups: [], totalQty: 0 };
              const isPlanning = s.key === "planning";
              const isProc = s.key === "procurement";
              const isDisp = s.key === "dispatched";
              return (
                <div key={s.key} className="w-[400px] flex-shrink-0" data-testid={`column-${s.key}`}>
                  <div
                    className={`bg-white border-2 mb-3 p-3 transition-all ${dropZone === s.key ? "border-[#C27842] bg-orange-50 shadow-ind" : "border-slate-200"} border-t-4`}
                    style={{ borderTopColor: s.color }}
                    onDragOver={STAGE_TO_ROLE[s.key] ? onDragOverStage(s.key) : undefined}
                    onDragLeave={() => setDropZone(null)}
                    onDrop={STAGE_TO_ROLE[s.key] ? onDropStage(s.key) : undefined}
                    data-testid={`column-header-${s.key}`}
                  >
                    <div className="flex items-baseline justify-between">
                      <div className="font-bold uppercase tracking-wider text-sm">{s.label}</div>
                      <div className="font-mono text-xs text-slate-500">
                        {groups.length} · <span className="font-bold text-slate-900">{totalQty}</span>
                      </div>
                    </div>
                    {STAGE_TO_ROLE[s.key] && draggingWorker && (
                      <div className="mt-1 text-[10px] uppercase tracking-wider font-bold text-[#C27842]">
                        Drop here → assign to {STAGE_TO_ROLE[s.key]} role on {groups.length} card(s)
                      </div>
                    )}
                    {s.key === "qc_pack" && qcPackSelectedCount > 0 && (
                      <div className="mt-2 pt-2 border-t border-teal-200 flex items-center justify-between gap-1 text-[11px] text-teal-800">
                        <span className="font-bold truncate">Selected: {qcPackSelectedCount} card(s)</span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            type="button"
                            onClick={() => setDispatchFor({ groups: Object.values(qcPackSelected) })}
                            className="px-2 py-0.5 bg-[#0D9488] text-white font-bold text-[10px] uppercase rounded hover:bg-[#0B7A70] transition-colors"
                            data-testid="column-merge-dispatch-btn"
                          >
                            Merge Dispatch
                          </button>
                          <button
                            type="button"
                            onClick={() => setQcPackSelected({})}
                            className="px-1.5 py-0.5 text-slate-500 hover:text-slate-800 text-[10px] font-bold"
                            title="Clear selection"
                          >
                            Clear
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="space-y-3">
                    {groups.length === 0 && (
                      <div className="border-2 border-dashed border-slate-200 p-6 text-center text-xs text-slate-400">Empty</div>
                    )}
                    {groups.map((g) => (
                      <ColorGroupCard
                        key={g.key}
                        group={g}
                        style={styleByCode[g.style_code]}
                        workers={workers}
                        vendors={vendors}
                        stageColor={s.color}
                        stageIdx={STAGES.findIndex(x => x.key === s.key)}
                        canEdit={canEdit}
                        onMove={handleMoveGroup}
                        onToggleComponent={toggleComponent}
                        onOpenAssign={(role) => setAssignFor({ group: g, role })}
                        onOpenQty={(rowId) => setQtyFor({ group: g, rowId })}
                        onPrint={() => printCard(g)}
                        onWhatsApp={() => setWaFor({ group: g })}
                        onPacking={() => openPackingForGroup(g)}
                        onPackCartons={() => setCartonPackFor(g)}
                        onDispatch={() => setDispatchFor(g)}
                        isPlanning={isPlanning}
                        isProc={isProc}
                        isDispatched={isDisp}
                        isQcPack={s.key === "qc_pack"}
                        isQcPackSelected={!!qcPackSelected[g.key]}
                        onToggleQcPackSelect={toggleQcPackSelect}
                        isQcPackSelectDisabled={isQcPackSelectionDisabled(g)}
                        onMatReq={(split = true) => downloadMaterialRequirement([g], `${g.style_code} · ${g.color}`, split)}
                        procSelected={!!procSelected[g.key]}
                        onToggleProcSelect={toggleProcSelect}
                        onDownloadInvoice={downloadGroupInvoice}
                        isSelected={!!selected[g.key]}
                        onToggleSelect={toggleSelect}
                        isSelectDisabled={isSelectionDisabled(g)}
                        dispatchRecordByJobId={dispatchRecordByJobId}
                        onDownloadDispatchFile={downloadDispatchFile}
                        onOpenDispatchDetails={(group) => setDispatchDetailFor(group)}
                        onArchiveDispatched={(jids, lbl) => archiveDispatchedJobs(jids, lbl)}
                        onPreviewImage={(img) => setPreviewImageModal(img)}
                        onOpenPlanningAllocation={(group, req) => setPlanningAllocationFor({ group, req })}
                        onDropWorkerToComponent={(grp, role, worker) => assignWorker(grp, role, worker.id, worker.rate_per_pair)}
                        draggingWorker={draggingWorker}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        )}
        {!viewArchive && jobs.length === 0 && (
          <Card className="p-12 text-center text-slate-400 mt-4">No production jobs yet.</Card>
        )}
      </div>

      {assignFor && (
        <AssignDialog
          group={assignFor.group}
          role={assignFor.role}
          workers={workers}
          styleByCode={styleByCode}
          current={assignFor.group.assignments?.[assignFor.role]}
          onSave={(wid, rate, overwrite) => assignWorker(assignFor.group, assignFor.role, wid, rate, overwrite)}
          onClose={() => setAssignFor(null)}
        />
      )}

      {qtyFor && (
        <QuantityDialog
          group={qtyFor.group}
          row={qtyFor.group.rows.find(r => r.id === qtyFor.rowId)}
          onSave={(body) => saveQuantity(qtyFor.rowId, body)}
          onClose={() => setQtyFor(null)}
        />
      )}

      {dockOpen && (
        <div className="fixed left-64 right-0 bottom-0 bg-white border-t-2 border-slate-200 shadow-2xl z-40 p-3" data-testid="karigar-dock">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs uppercase tracking-[0.2em] font-bold text-slate-600">
              Drag a karigar onto any stage column to assign them across all cards in that column
            </div>
            <button onClick={() => setDockOpen(false)} className="p-1 hover:bg-slate-100"><X className="w-4 h-4" /></button>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {workers.length === 0 && <div className="text-xs text-slate-400 py-3">No karigars. Add some in the Karigars tab first.</div>}
            {workers.filter(w => w.active !== false).map(w => (
              <div
                key={w.id}
                draggable
                onDragStart={onDragStartWorker(w)}
                onDragEnd={onDragEndWorker}
                data-testid={`drag-worker-${w.id}`}
                className={`flex items-center gap-2 px-3 py-2 border-2 cursor-grab active:cursor-grabbing select-none ${draggingWorker?.id === w.id ? "border-[#C27842] bg-orange-50" : "border-slate-300 bg-white hover:border-[#0F172A]"}`}
              >
                <GripVertical className="w-3.5 h-3.5 text-slate-400" />
                <div>
                  <div className="font-bold text-sm leading-tight">{w.name}</div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">{w.skill} · ₹{w.rate_per_pair}/pr</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {waFor && (
        <WhatsAppDialog
          group={waFor.group}
          workers={workers}
          onClose={() => setWaFor(null)}
          onSend={(phone) => shareViaWhatsApp(waFor.group, phone)}
        />
      )}

      {detailFor && (
        <DetailModal group={detailFor} onClose={() => setDetailFor(null)} />
      )}

      {dispatchDetailFor && (
        <DispatchDetailsModal
          item={dispatchDetailFor}
          dispatchRecordByJobId={dispatchRecordByJobId}
          invoices={invoices}
          styleByCode={styleByCode}
          onClose={() => setDispatchDetailFor(null)}
          onDownloadDispatchFile={downloadDispatchFile}
          onArchive={viewArchive ? null : archiveDispatchedJobs}
          onPreviewImage={(img) => setPreviewImageModal(img)}
        />
      )}

      {previewImageModal && (
        <ImageViewModal
          isOpen={!!previewImageModal}
          src={previewImageModal.src || previewImageModal.url}
          title={previewImageModal.title || "Style Preview"}
          subtitle={previewImageModal.subtitle}
          alt={previewImageModal.alt || "Style Preview"}
          onClose={() => setPreviewImageModal(null)}
        />
      )}

      {packingFor && (
        <PackingListDialog
          payload={packingFor}
          onClose={() => setPackingFor(null)}
          onSubmit={submitPacking}
        />
      )}
      {cartonPackFor && (
        <PackCartonDialog
          group={cartonPackFor}
          style={styleByCode[cartonPackFor.style_code]}
          onClose={() => setCartonPackFor(null)}
          load={load}
        />
      )}

      {dispatchFor && (
        <DispatchDialog
          group={dispatchFor.groups ? null : dispatchFor}
          groups={dispatchFor.groups || null}
          onClose={() => setDispatchFor(null)}
          load={load}
          onSuccess={() => setQcPackSelected({})}
        />
      )}

      {bulkConfirm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 overflow-y-auto" data-testid="bulk-assign-dialog">
          <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
            <div className="px-5 py-4 border-b-2 border-slate-200">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Bulk Assignment</div>
              <div className="font-bold text-base">{bulkConfirm.worker.name} → {bulkConfirm.role.toUpperCase()}</div>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-sm text-slate-700">
                Assign <b>{bulkConfirm.worker.name}</b> ({bulkConfirm.worker.skill}) as the <b>{bulkConfirm.role}</b> karigar on <b>{bulkConfirm.card_count}</b> card(s) currently in <b>{bulkConfirm.stage_label}</b> stage?
              </p>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Rate per pair (₹) for these jobs</label>
                <input type="number" step="0.5" value={bulkConfirm.rate}
                  onChange={(e) => setBulkConfirm({ ...bulkConfirm, rate: e.target.value })}
                  className="w-full mt-1 border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#C27842] focus:outline-none"
                  data-testid="bulk-rate-input" />
                <div className="text-[10px] text-slate-500 mt-1">Negotiated rate that will apply to all selected cards. Default is the karigar's standard rate.</div>
              </div>
              <p className="text-xs text-slate-500">Overwrites any existing {bulkConfirm.role} assignment on these cards. History preserved.</p>
              <div className="flex gap-2 pt-2 border-t border-slate-200">
                <BtnPrimary onClick={runBulkAssign} data-testid="bulk-confirm-save"><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Assign to all</BtnPrimary>
                <BtnSecondary onClick={() => setBulkConfirm(null)}>Cancel</BtnSecondary>
              </div>
            </div>
          </div>
        </div>
      )}

      {shortageModal && (
        <ShortageModal
          state={shortageModal}
          onClose={() => setShortageModal(null)}
          navigate={navigate}
        />
      )}

      {planningAllocationFor && (
        <PlanningVendorAllocationModal
          group={planningAllocationFor.group}
          req={planningAllocationFor.req}
          onClose={() => setPlanningAllocationFor(null)}
          onSuccess={() => {
            setPlanningAllocationFor(null);
            load();
          }}
          navigate={navigate}
        />
      )}
    </div>
  );
}

function PlanningVendorAllocationModal({ group, req, onClose, onSuccess, navigate }) {
  const [vendors, setVendors] = useState([]);
  const [loadingVendors, setLoadingVendors] = useState(true);
  const [expectedDate, setExpectedDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 7);
    return d.toISOString().split("T")[0];
  });
  const [notes, setNotes] = useState("");
  const [allocations, setAllocations] = useState(() => {
    return (req?.materials || []).map(m => ({
      material_id: m.material_id || "",
      code: m.code || "",
      name: m.name || "",
      color: m.color || "",
      unit: m.unit || "",
      category: m.category || "other",
      total_qty_required: m.total_qty_required || 0,
      rate: m.rate || 0,
      vendor_id: m.preferred_vendor_id || "",
    }));
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    http.get("/vendors?include_inactive=false")
      .then(res => {
        setVendors(res.data || []);
      })
      .catch(e => {
        console.error("Failed to load vendors:", e);
      })
      .finally(() => setLoadingVendors(false));
  }, []);

  const updateItem = (idx, field, val) => {
    setAllocations(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: val };
      return next;
    });
  };

  const { totalAmount, vendorCount, unassignedCount } = useMemo(() => {
    let total = 0;
    const vSet = new Set();
    let unassigned = 0;
    for (const a of allocations) {
      const amt = (parseFloat(a.total_qty_required) || 0) * (parseFloat(a.rate) || 0);
      total += amt;
      if (a.vendor_id) {
        vSet.add(a.vendor_id);
      } else {
        unassigned++;
      }
    }
    return {
      totalAmount: Math.round(total * 100) / 100,
      vendorCount: vSet.size,
      unassignedCount: unassigned,
    };
  }, [allocations]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (unassignedCount > 0) {
      setError(`Please select a vendor for all materials (${unassignedCount} unassigned).`);
      return;
    }
    setSubmitting(true);
    setError("");

    try {
      const payload = {
        job_ids: group.rows.map(r => r.id),
        customer_po_number: group.po_number || "",
        style_code: group.style_code || "",
        color: group.color || "",
        expected_delivery_date: expectedDate,
        notes: notes.trim() || `Generated from Planning Stage for ${group.po_number} (${group.style_code} - ${group.color})`,
        allocations: allocations.map(a => ({
          material_id: a.material_id,
          material_code: a.code,
          material_name: a.name,
          category: a.category,
          unit: a.unit,
          color: a.color || "",
          quantity: parseFloat(a.total_qty_required) || 0,
          rate: parseFloat(a.rate) || 0,
          amount: Math.round((parseFloat(a.total_qty_required) || 0) * (parseFloat(a.rate) || 0) * 100) / 100,
          vendor_id: a.vendor_id,
          vendor_name: vendors.find(v => v.id === a.vendor_id)?.name || "",
        })),
      };

      const { data } = await http.post("/production/planning/generate-vendor-pos", payload);
      const poNos = data.vendor_po_numbers || [];
      alert(`Success! Generated ${poNos.length} Vendor Purchase Order(s):\n${poNos.join(", ")}`);
      onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to generate Vendor POs");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4 overflow-y-auto" data-testid="planning-vendor-allocation-modal">
      <div className="bg-white w-full max-w-4xl max-h-[90vh] overflow-y-auto border-2 border-slate-200 shadow-2xl flex flex-col">
        <div className="bg-violet-800 text-white px-6 py-4 flex items-center justify-between shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-violet-200">Production Planning Stage</div>
            <h3 className="text-lg font-bold">Allocate Materials to Vendors &amp; Generate POs</h3>
            <div className="text-xs text-violet-200 mt-0.5">
              PO: <span className="font-mono font-bold text-white">{group.po_number}</span> · Client: <span className="text-white font-bold">{group.client_name}</span> · Style: <span className="font-mono font-bold text-white">{group.style_code}</span> ({group.color}) · <span className="text-white font-bold">{group.totalQty}</span> pairs
            </div>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1 rounded transition-colors"><X className="w-5 h-5" /></button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4 flex-1 overflow-y-auto flex flex-col">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 text-xs flex items-center gap-2 rounded">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="border border-slate-200 rounded overflow-hidden">
            <div className="max-h-[350px] overflow-y-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-100 text-slate-700 font-bold uppercase text-[10px] tracking-wider sticky top-0 border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3">Material</th>
                    <th className="py-2.5 px-3 text-right">Required Qty</th>
                    <th className="py-2.5 px-3 text-right w-24">Rate (₹)</th>
                    <th className="py-2.5 px-3">Assign Vendor</th>
                    <th className="py-2.5 px-3 text-right">Est. Amount (₹)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {allocations.map((a, idx) => {
                    const rowAmt = (parseFloat(a.total_qty_required) || 0) * (parseFloat(a.rate) || 0);
                    return (
                      <tr key={idx} className="hover:bg-slate-50 transition-colors">
                        <td className="py-2 px-3">
                          <div className="font-mono font-bold text-slate-900">{a.code}</div>
                          <div className="text-slate-500 text-[11px] truncate max-w-xs">{a.name}</div>
                          {a.color && (
                            <span className="inline-block text-[9px] font-bold px-1.5 py-0.2 bg-violet-50 text-violet-700 border border-violet-200 rounded mt-0.5">
                              {a.color}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-right font-mono font-semibold text-slate-800 whitespace-nowrap">
                          {a.total_qty_required} <span className="text-slate-400 text-[10px]">{a.unit}</span>
                        </td>
                        <td className="py-2 px-3 text-right">
                          <input
                            type="number"
                            min="0"
                            step="any"
                            value={a.rate}
                            onChange={(e) => updateItem(idx, "rate", e.target.value)}
                            className="w-20 text-right font-mono px-1.5 py-1 border border-slate-300 rounded text-xs focus:outline-none focus:border-violet-500"
                            data-testid={`alloc-rate-input-${idx}`}
                          />
                        </td>
                        <td className="py-2 px-3">
                          <select
                            value={a.vendor_id}
                            onChange={(e) => updateItem(idx, "vendor_id", e.target.value)}
                            className={`w-full max-w-xs px-2 py-1 border text-xs rounded focus:outline-none focus:border-violet-500 ${!a.vendor_id ? "border-amber-400 bg-amber-50/50" : "border-slate-300"}`}
                            data-testid={`alloc-vendor-select-${idx}`}
                          >
                            <option value="">-- Select Vendor --</option>
                            {vendors.map(v => (
                              <option key={v.id} value={v.id}>
                                {v.name} {v.city ? `(${v.city})` : ""}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-3 text-right font-mono font-bold text-violet-900 whitespace-nowrap">
                          ₹{rowAmt.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                Expected Vendor Delivery Date
              </label>
              <input
                type="date"
                value={expectedDate}
                onChange={(e) => setExpectedDate(e.target.value)}
                className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded focus:outline-none focus:border-violet-500"
                data-testid="alloc-expected-date"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                PO Notes / Special Instructions
              </label>
              <input
                type="text"
                placeholder="Optional notes for vendor purchase order…"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full text-xs px-2.5 py-1.5 border border-slate-300 rounded focus:outline-none focus:border-violet-500"
                data-testid="alloc-notes"
              />
            </div>
          </div>

          <div className="bg-violet-50 border border-violet-200 rounded p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div>
              <div className="text-[10px] uppercase font-bold text-violet-700">Summary</div>
              <div className="text-slate-700">
                <span className="font-bold">{allocations.length}</span> materials · <span className="font-bold text-violet-800">{vendorCount}</span> distinct vendor(s)
                {unassignedCount > 0 && (
                  <span className="text-amber-700 font-bold ml-2">({unassignedCount} unassigned)</span>
                )}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase font-bold text-slate-500">Total Estimated Procurement</div>
              <div className="text-lg font-mono font-bold text-violet-900">
                ₹{totalAmount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
          </div>

          <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-200">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || unassignedCount > 0}
              className="px-5 py-2 text-xs font-bold uppercase tracking-wider bg-violet-700 hover:bg-violet-800 disabled:opacity-50 text-white rounded flex items-center gap-1.5 shadow transition-all"
              data-testid="alloc-submit-btn"
            >
              {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShoppingCart className="w-3.5 h-3.5" />}
              <span>Generate {vendorCount > 0 ? `${vendorCount} Vendor PO(s)` : "Vendor POs"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ColorGroupCard(props) {
  const { group, style, stageColor, stageIdx, canEdit, onMove, onToggleComponent,
    onOpenAssign, onOpenQty, onPrint, onWhatsApp, onPacking, isPlanning, isProc, isDispatched,
    isQcPack, isQcPackSelected, onToggleQcPackSelect, isQcPackSelectDisabled, onMatReq,
    procSelected, onToggleProcSelect, isSelected, onToggleSelect, onDownloadInvoice, onPackCartons, onDispatch,
    dispatchRecordByJobId, onDownloadDispatchFile, isSelectDisabled, onOpenDispatchDetails, onArchiveDispatched,
    onOpenPlanningAllocation, onDropWorkerToComponent, draggingWorker, workers = [], vendors = [],
    onPreviewImage } = props;
  const navigate = useNavigate();
  const [localPreview, setLocalPreview] = useState(null);
  const nextStage = STAGES[stageIdx + 1];
  const prevStage = STAGES[stageIdx - 1];
  // Track which parallel component is selected/expanded for karigar assignment
  const [activeComp, setActiveComp] = useState(null);

  const consumeError = group.rows.find(r => r.inventory_consume_error);

  const sizeTotals = useMemo(() => {
    const t = {}; const rowIdBySize = {};
    for (const sz of group.sizes) {
      const row = group.rows.find(r => String(r.size || "—") === sz);
      t[sz] = row?.quantity || 0;
      rowIdBySize[sz] = row?.id;
    }
    return { t, rowIdBySize };
  }, [group]);

  const completedTotal = group.rows.reduce((s, r) => s + (r.completed_qty || 0), 0);
  const a = group.assignments || {};
  const overdue = (group.overdueHours || 0) > 0;
  
  let drec = null;
  if (dispatchRecordByJobId && group.rows) {
    for (const row of group.rows) {
      if (dispatchRecordByJobId[row.id]) {
        drec = dispatchRecordByJobId[row.id];
        break;
      }
    }
  }

  const isInactive = style?.status === "inactive";
  const effectiveCanEdit = canEdit && !isInactive;

  // ─── Outside Labour Work state (from jobs or style master fallback) ──────
  const initialOutsideLabour = useMemo(() => {
    if (group.rows?.[0]?.outside_labour && group.rows[0].outside_labour.length > 0) {
      return group.rows[0].outside_labour;
    }
    const fromStyle = (style?.outside_labour || []).concat(
      (style?.labor || []).filter(l => l.is_outside)
    );
    return fromStyle;
  }, [group, style]);

  const [outsideLabour, setOutsideLabour] = useState(initialOutsideLabour);
  useEffect(() => {
    setOutsideLabour(initialOutsideLabour);
  }, [initialOutsideLabour]);

  const handleUpdateOutsideLabour = async (newItems) => {
    setOutsideLabour(newItems);
    try {
      await http.post("/production/job-groups/outside-labour", {
        job_ids: group.rows.map(r => r.id),
        outside_labour: newItems,
      });
      group.rows.forEach(r => { r.outside_labour = newItems; });
    } catch (e) {
      console.error("Failed to update outside labour", e);
      alert("Failed to update outside labour: " + (e.response?.data?.detail || e.message));
    }
  };

  const handleCompleteOutsideLabour = async (itemId) => {
    try {
      const res = await http.post(`/production/jobs/${group.rows[0].id}/outside-labour/${itemId}/complete`, {
        completed_qty: group.totalQty,
      });
      const updatedList = res.data.outside_labour;
      if (updatedList) {
        setOutsideLabour(updatedList);
        group.rows.forEach(r => { r.outside_labour = updatedList; });
      }
      alert("Outside Labour marked complete! Vendor Bill posted to AP ledger.");
    } catch (e) {
      console.error("Failed to complete outside labour", e);
      alert("Failed to complete outside labour: " + (e.response?.data?.detail || e.message));
    }
  };

  // Derive dynamic sub-tasks from component_specs.{compKey}.stages
  const getSubtasksForComp = useCallback((compKey) => {
    if (!compKey) return [];
    if (compKey === "sole" && isSoleReadyToUse(group, style)) {
      return [];
    }
    const compSpecs = group.component_specs?.components?.[compKey];
    let compStages = compSpecs?.stages;
    if (compKey === "bottom") {
      const baseBottom = ["cutting", "stitching", "stamping"];
      if (!Array.isArray(compStages) || compStages.length === 0) {
        compStages = baseBottom;
      } else {
        const merged = [...compStages];
        baseBottom.forEach(b => {
          if (!merged.includes(b) && !merged.some(s => s.includes("stamp") || s.includes("brand"))) {
            merged.push(b);
          }
        });
        compStages = merged;
      }
    }
    if (Array.isArray(compStages)) {
      return compStages.map(st => {
        const predefined = (COMPONENT_SUBTASK_ROLES[compKey] || []).find(
          r => r.key === `${compKey}.${st}` || r.key.endsWith(`.${st}`) || r.substage === st || (st.includes("stamp") && r.key === "bottom.stamping")
        );
        const formatLabel = (s) => {
          if (s === "stamping" || s === "brand_marking" || s === "stamping_brand_marking") return "Stamping / Brand Marking";
          return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");
        };
        return {
          key: `${compKey}.${st}`,
          substage: st,
          fallbackKey: predefined?.fallbackKey || null,
          label: predefined?.label || formatLabel(st),
          icon: predefined?.icon || (st.includes("cut") ? "✂" : st.includes("stitch") ? "🧵" : st.includes("stamp") || st.includes("brand") ? "🏷️" : st.includes("fold") ? "📐" : "🔧"),
        };
      });
    }
    return COMPONENT_SUBTASK_ROLES[compKey] || [];
  }, [group, style]);

  const dynamicSubtasks = useMemo(() => getSubtasksForComp(activeComp), [activeComp, getSubtasksForComp]);

  // ─── Planning stage: material requirement preview ───────────────────────
  const [planMatReq, setPlanMatReq] = useState(null);
  const [planMatLoading, setPlanMatLoading] = useState(false);
  const [planNotes, setPlanNotes] = useState(group.rows[0]?.planning_notes || "");
  const [planNotesSaving, setPlanNotesSaving] = useState(false);
  const hasColorBom = !!(style?.color_bom_overrides?.[group.color]?.length ||
    style?.color_material_overrides?.[group.color]);

  const loadPlanMatReq = async () => {
    setPlanMatLoading(true);
    try {
      const job_ids = group.rows.map(r => r.id);
      const { data } = await http.post("/procurement/requirement", { job_ids });
      setPlanMatReq(data);
    } catch (e) {
      console.error("Material preview failed:", e);
    } finally {
      setPlanMatLoading(false);
    }
  };

  const savePlanNotes = async () => {
    setPlanNotesSaving(true);
    try {
      await Promise.all(group.rows.map(j =>
        http.patch(`/production/jobs/${j.id}`, { planning_notes: planNotes })
      ));
    } catch (e) { /* silent */ }
    finally { setPlanNotesSaving(false); }
  };

  const linkedVpos = useMemo(() => {
    const set = new Set();
    (group.rows || []).forEach(r => {
      (r.vendor_po_numbers || []).forEach(no => { if (no) set.add(no); });
    });
    return Array.from(set);
  }, [group]);

  return (
    <Card
      className={`border-l-4 transition-colors ${overdue ? "ring-2 ring-red-500 ring-inset" : "hover:border-[#C27842]"}`}
      style={{ borderLeftColor: overdue ? "#DC2626" : stageColor }}
      data-testid={`group-${group.key}`}
    >
      {isInactive && (
        <div className="bg-red-600 text-white px-3 py-1.5 flex items-center justify-between text-[10px] uppercase tracking-wider font-bold animate-pulse">
          <span className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Action Required: Missing BOM</span>
          <a href={`/styles?edit=${encodeURIComponent(style?.code || "")}`} rel="noreferrer" className="underline hover:text-slate-200">
            Fix in Styles
          </a>
        </div>
      )}
      {overdue && (
        <div className="bg-red-600 text-white px-3 py-1 flex items-center justify-between text-[10px] uppercase tracking-wider font-bold" data-testid={`overdue-${group.key}`}>
          <span className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> OVERDUE</span>
          <span className="font-mono">
            {group.overdueHours >= 10 ? `${(group.overdueHours / 10).toFixed(1)} d late` : `${group.overdueHours.toFixed(1)} h late`}

          </span>
        </div>
      )}
      {consumeError && (
        <div className="bg-amber-600 text-white px-3 py-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold animate-pulse" data-testid={`consume-error-${group.key}`}>
          <AlertTriangle className="w-3 h-3" />
          <span>⚠ {consumeError.inventory_consume_error}</span>
        </div>
      )}
      {/* Top Header Bar: Top Left = Card Creation Date, Top Right = Combine / Merge Checkbox */}
      <div className="px-3 py-1 bg-slate-50/90 border-b border-slate-100 flex items-center justify-between gap-2 text-[10px] min-h-[26px]">
        {/* Top Left Corner: Date of creation */}
        <div className="flex items-center gap-1 font-mono text-slate-500" data-testid={`created-date-${group.key}`}>
          <Clock className="w-3 h-3 text-slate-400 flex-shrink-0" />
          <span className="text-slate-400 uppercase font-semibold text-[8.5px] tracking-wider">Created: </span>
          <span className="text-slate-700 font-bold text-[10px]">
            {group.card_created_date || (group.created_at ? String(group.created_at).slice(0, 10) : "—")}
          </span>
        </div>

        {/* Top Right Corner: Combine / Merge checkbox */}
        <div className="flex items-center gap-2 flex-shrink-0 ml-auto">
          {isProc && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer bg-blue-50 hover:bg-blue-100 border border-blue-200 px-2 py-0.5 rounded shadow-2xs transition-colors" data-testid={`proc-combine-label-${group.key}`}>
              <input
                type="checkbox"
                checked={procSelected}
                onChange={() => onToggleProcSelect(group)}
                className="w-3.5 h-3.5 accent-[#2563EB]"
                data-testid={`proc-select-${group.key}`}
              />
              <span className="text-[10px] uppercase tracking-wider font-bold text-blue-900">Combine</span>
            </label>
          )}
          {isQcPack && (
            <label
              className="inline-flex items-center gap-1.5 cursor-pointer bg-teal-50 hover:bg-teal-100 border border-teal-200 px-2 py-0.5 rounded shadow-2xs transition-colors"
              title={isQcPackSelectDisabled && !isQcPackSelected ? "Cannot merge with cards from a different PO" : "Select card to merge dispatch docs"}
            >
              <input
                type="checkbox"
                checked={isQcPackSelected}
                disabled={isQcPackSelectDisabled && !isQcPackSelected}
                onChange={() => onToggleQcPackSelect(group)}
                className={`w-3.5 h-3.5 accent-[#0D9488] ${isQcPackSelectDisabled && !isQcPackSelected ? "cursor-not-allowed opacity-50" : ""}`}
                data-testid={`qc-pack-select-${group.key}`}
              />
              <span className="text-[10px] uppercase tracking-wider font-bold text-teal-800">Merge</span>
            </label>
          )}
          {isDispatched && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer bg-amber-50 hover:bg-amber-100 border border-amber-200 px-2 py-0.5 rounded shadow-2xs transition-colors">
              <input
                type="checkbox"
                checked={isSelected}
                disabled={isSelectDisabled && !isSelected}
                onChange={() => onToggleSelect(group)}
                className={`w-3.5 h-3.5 accent-[#C27842] ${isSelectDisabled && !isSelected ? "cursor-not-allowed opacity-50" : ""}`}
                data-testid={`select-${group.key}`}
              />
              <span className="text-[10px] uppercase tracking-wider font-bold text-amber-900">Merge</span>
            </label>
          )}
        </div>
      </div>

      {/* 2-COLUMN HEADER: Left = Image, Right = PO Number, Style, SKU, Details & Dates */}
      <div className="p-2.5 border-b border-slate-200 bg-white flex gap-3 items-center">
        {/* Left Column: Image (resized to fit, with rounded border & fallback, clickable to view in modal) */}
        {(() => {
          const styleImgUrl = style?.image_url || style?.image_display_url || style?.image_thumbnail_url;
          return (
            <div
              className={`w-24 h-24 sm:w-28 sm:h-28 flex-shrink-0 rounded-md overflow-hidden border border-slate-200 bg-slate-50 relative flex items-center justify-center shadow-xs ${
                styleImgUrl ? "cursor-pointer group hover:border-[#C27842] hover:ring-2 hover:ring-[#C27842]/30 transition-all" : ""
              }`}
              onClick={styleImgUrl ? () => {
                const data = {
                  src: style.image_url || style.image_display_url || style.image_thumbnail_url,
                  title: `${style.name ? `${style.name} (${group.style_code})` : group.style_code}${group.color ? ` · ${group.color}` : ""}`,
                  subtitle: `PO #${group.po_number || "—"}${group.totalQty ? ` · ${group.totalQty} pairs` : ""}`,
                  alt: style.name || group.style_code,
                };
                if (onPreviewImage) onPreviewImage(data);
                else setLocalPreview(data);
              } : undefined}
              title={styleImgUrl ? "Click to view full image in modal" : undefined}
              data-testid={`card-img-container-${group.key}`}
            >
              {styleImgUrl ? (
                <>
                  <SafeImage
                    image={{
                      url: style.image_url,
                      display_url: style.image_display_url,
                      thumbnail_url: style.image_thumbnail_url,
                    }}
                    alt={style.name || group.style_code}
                    aspectRatio="1/1"
                    fit="cover"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                    testId={`card-img-${group.key}`}
                  />
                  <div
                    className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center text-white pointer-events-none"
                    data-testid={`card-img-overlay-${group.key}`}
                  >
                    <Maximize2 className="w-5 h-5 drop-shadow" />
                    <span className="text-[9px] font-bold uppercase tracking-wider mt-1 bg-black/60 px-1.5 py-0.5 rounded shadow">
                      View
                    </span>
                  </div>
                </>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center text-slate-300 p-2">
                  <Package className="w-6 h-6 text-slate-300 stroke-[1.5]" />
                  <span className="text-[8.5px] uppercase tracking-wider font-semibold text-slate-400 mt-1">No Image</span>
                </div>
              )}
            </div>
          );
        })()}

        {/* Right Column: PO Number, Style Number, SKU / External ID, Color, Qty, and Dates */}
        <div className="flex-1 min-w-0 flex flex-col justify-between self-stretch py-0.5">
          <div>
            <div className="flex items-center justify-between gap-1.5 flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                <span
                  className="text-[11px] font-mono font-bold text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200"
                  title="PO Number"
                  data-testid={`po-number-${group.key}`}
                >
                  {group.po_number}
                </span>
                <span
                  className="font-mono font-bold text-xs text-slate-900"
                  title={group.style_display || group.style_code}
                  data-testid={`style-code-${group.key}`}
                >
                  {group.style_display || group.style_code}
                </span>
                {group.sku_id && (
                  <span
                    className="text-[10px] font-mono font-semibold text-violet-800 bg-violet-50 border border-violet-200 px-1.5 py-0.5 rounded"
                    title={`SKU ID: ${group.sku_id}`}
                    data-testid={`sku-id-${group.key}`}
                  >
                    SKU: {group.sku_id}
                  </span>
                )}
                <span className="text-slate-300">·</span>
                <span className="text-xs font-bold text-[#C27842]">{group.color}</span>
                <span className="text-slate-400">·</span>
                <span className="text-xs text-slate-600 font-mono font-medium">{group.totalQty} pairs</span>
                {group.client_name && (
                  <>
                    <span className="text-slate-400">·</span>
                    <span
                      className="text-xs uppercase tracking-wider font-semibold text-slate-700 truncate max-w-[180px]"
                      title={`Client: ${group.client_name}`}
                      data-testid={`client-name-${group.key}`}
                    >
                      {group.client_name}
                    </span>
                  </>
                )}
                {completedTotal > 0 && (
                  <>
                    <span className="text-slate-400">·</span>
                    <span className="text-xs text-green-700 font-mono font-semibold">{completedTotal} done</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Dates row: PO date, delivery date */}
          <div className="flex items-center gap-3 text-[10px] text-slate-500 flex-wrap pt-1.5 border-t border-slate-100 mt-1.5">
            {group.po_date && (
              <div className="flex items-center gap-1 font-mono">
                <Calendar className="w-3 h-3 text-slate-400" />
                <span className="text-slate-400 uppercase font-semibold text-[9px]">PO:</span>
                <span className="text-slate-700 font-medium">{group.po_date}</span>
              </div>
            )}
            {group.delivery_date && (
              <div className="flex items-center gap-1 font-mono">
                <Truck className="w-3 h-3 text-[#C27842]" />
                <span className="text-slate-400 uppercase font-semibold text-[9px]">Deliver:</span>
                <span className="text-slate-800 font-bold">{group.delivery_date}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {isPlanning && (
        <div className="border-b-2 border-violet-200 bg-gradient-to-br from-violet-50 to-indigo-50" data-testid={`planning-panel-${group.key}`}>
          {/* Planning header */}
          <div className="flex items-center justify-between px-3 py-2 bg-violet-700 text-white">
            <div className="flex items-center gap-2">
              <Layers className="w-3.5 h-3.5" />
              <span className="text-[10px] uppercase tracking-[0.15em] font-bold">Planning Stage</span>
            </div>
            {canEdit && (
              <button
                onClick={() => onMove(group, "procurement")}
                className="text-[9px] uppercase tracking-wider font-bold bg-white text-violet-700 hover:bg-violet-50 px-3 py-1.5 rounded-full flex items-center gap-1.5 transition-all shadow-sm hover:shadow whitespace-nowrap"
                data-testid={`release-to-procurement-${group.key}`}
              >
                <CheckCircle className="w-3 h-3" /> Confirm Plan → Procurement
              </button>
            )}
          </div>

          {/* Linked Vendor POs */}
          {linkedVpos.length > 0 && (
            <div className="flex items-center justify-between px-3 py-1.5 bg-violet-100/90 border-b border-violet-200 flex-wrap gap-1" data-testid={`linked-vpos-panel-${group.key}`}>
              <div className="flex items-center gap-1 text-[10px] font-bold text-violet-900">
                <ShoppingCart className="w-3 h-3 text-violet-700" />
                <span>Vendor PO(s):</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {linkedVpos.map(vpo => (
                  <button
                    key={vpo}
                    type="button"
                    onClick={() => navigate("/vendor-pos", { state: { search: vpo } })}
                    className="text-[9px] font-mono font-bold bg-white text-violet-800 hover:bg-violet-700 hover:text-white border border-violet-300 px-1.5 py-0.5 rounded shadow-xs transition-colors"
                    title="View in Vendor POs"
                    data-testid={`linked-vpo-badge-${vpo}`}
                  >
                    {vpo}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Color BOM warning */}
          {!hasColorBom && (
            <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 border-b border-amber-200 text-amber-800">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 text-amber-500 flex-shrink-0" />
              <div className="text-[10px]">
                <span className="font-bold">No color-specific BOM configured</span> for <span className="font-bold">{group.color}</span>.
                Material requirement will use the base BOM.{" "}
                <a href={`/styles?edit=${encodeURIComponent(group.style_code)}`} className="underline text-amber-700 hover:text-amber-900 font-bold">
                  Configure Color BOM →
                </a>
              </div>
            </div>
          )}
          {hasColorBom && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border-b border-emerald-200 text-emerald-800 text-[10px]">
              <CheckCircle2 className="w-3 h-3 text-emerald-500 flex-shrink-0" />
              <span className="font-bold">Color-specific BOM active</span> — Material requirement will use <span className="font-bold text-emerald-700">{group.color}</span> overrides.
            </div>
          )}

          {/* Material Preview */}
          <div className="px-3 py-2">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-violet-700">Material Preview</div>
              <div className="flex items-center gap-1.5">
                {planMatReq && (
                  <button
                    onClick={() => onMatReq?.(true)}
                    className="text-[9px] uppercase tracking-wider font-bold text-violet-700 hover:text-white hover:bg-violet-600 border border-violet-300 px-2 py-0.5 rounded flex items-center gap-1 transition-colors"
                    title="Download color-split requirement PDF"
                    data-testid={`print-plan-pdf-${group.key}`}
                  >
                    <Printer className="w-3 h-3" /> PDF
                  </button>
                )}
                <button
                  onClick={loadPlanMatReq}
                  disabled={planMatLoading}
                  className="text-[9px] uppercase tracking-wider font-bold text-violet-600 hover:text-violet-900 border border-violet-300 px-2 py-0.5 rounded hover:bg-violet-100 flex items-center gap-1 transition-colors"
                  data-testid={`preview-mat-req-${group.key}`}
                >
                  {planMatLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                  {planMatReq ? "Refresh" : "Load"}
                </button>
              </div>
            </div>

            {!planMatReq && !planMatLoading && (
              <div className="text-[10px] text-slate-400 italic text-center py-2 border border-dashed border-violet-200 rounded">
                Click "Load" to preview color-specific material requirements
              </div>
            )}
            {planMatLoading && (
              <div className="flex items-center justify-center gap-2 py-4 text-violet-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-[10px]">Calculating color-aware BOM…</span>
              </div>
            )}
            {planMatReq && !planMatLoading && (
              <div className="space-y-0.5 max-h-40 overflow-y-auto">
                {planMatReq.materials.slice(0, 12).map((m, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px] py-0.5 border-b border-violet-100 last:border-0">
                    <div className="flex-1 min-w-0">
                      <span className="font-mono font-bold text-slate-800 truncate block">{m.code}</span>
                      <span className="text-slate-500 truncate block">{m.name}{m.color ? <span className="ml-1 text-violet-600 font-semibold">({m.color})</span> : ""}</span>
                    </div>
                    <div className="flex items-center gap-2 ml-2 flex-shrink-0 text-right">
                      <span className="font-mono font-bold text-violet-700">{m.total_qty_required} <span className="text-slate-400 font-normal">{m.unit}</span></span>
                    </div>
                  </div>
                ))}
                {planMatReq.materials.length > 12 && (
                  <div className="text-[9px] text-slate-400 text-center pt-1">+{planMatReq.materials.length - 12} more materials</div>
                )}
                {planMatReq.materials.length === 0 && (
                  <div className="text-[10px] text-slate-400 italic text-center py-2">No materials in BOM</div>
                )}
              </div>
            )}

            {planMatReq && !planMatLoading && planMatReq.materials?.length > 0 && (
              <div className="mt-2 pt-2 border-t border-violet-200 flex items-center justify-between gap-2">
                <div className="text-[10px] text-violet-700 font-semibold">
                  {planMatReq.materials.length} material(s)
                </div>
                <button
                  type="button"
                  onClick={() => onOpenPlanningAllocation?.(group, planMatReq)}
                  className="text-[10px] font-bold bg-violet-600 hover:bg-violet-700 text-white px-2.5 py-1 rounded flex items-center gap-1 shadow-sm transition-all whitespace-nowrap"
                  data-testid={`allocate-vendors-btn-${group.key}`}
                >
                  <ShoppingCart className="w-3 h-3" /> Allocate &amp; Raise POs
                </button>
              </div>
            )}
          </div>

          {/* Planner Notes */}
          <div className="px-3 pb-2">
            <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-violet-700 mb-1">Planner Notes</div>
            <div className="flex gap-1">
              <textarea
                value={planNotes}
                onChange={e => setPlanNotes(e.target.value)}
                placeholder="Add planning notes, material concerns, special client requirements…"
                className="flex-1 text-[10px] border border-violet-200 rounded px-2 py-1.5 placeholder:text-slate-400 focus:outline-none focus:border-violet-400 resize-none bg-white"
                rows={2}
                data-testid={`planning-notes-${group.key}`}
              />
              <button
                onClick={savePlanNotes}
                disabled={planNotesSaving}
                className="text-[9px] px-2 py-1 bg-violet-600 hover:bg-violet-700 text-white rounded font-bold flex-shrink-0 self-end transition-colors"
              >
                {planNotesSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              </button>
            </div>
          </div>
        </div>
      )}


      {/* Size matrix with click-to-edit qty */}
      <div className="p-3 overflow-x-auto">
        <table className="w-full text-xs border border-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-2 py-1 text-left text-[10px] uppercase tracking-wider font-bold text-slate-600 border-r border-slate-200 sticky left-0 z-10 bg-slate-50">Size</th>
              {group.sizes.map(sz => (
                <th key={sz} className="px-2 py-1 text-center font-mono text-[11px] font-bold text-slate-700 border-r border-slate-200 last:border-r-0">{sz}</th>
              ))}
              <th className="px-2 py-1 text-right text-[10px] uppercase tracking-wider font-bold text-slate-900 bg-slate-100">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-200">
              <td className="px-2 py-1.5 font-bold text-slate-700 border-r border-slate-200 sticky left-0 z-10 bg-white">{group.color}</td>
              {group.sizes.map(sz => (
                <td key={sz} className="px-2 py-1.5 text-center font-mono border-r border-slate-200 last:border-r-0">
                  {effectiveCanEdit ? (
                    <button onClick={() => onOpenQty(sizeTotals.rowIdBySize[sz])} className="hover:text-[#C27842] hover:underline w-full" data-testid={`qty-${group.key}-${sz}`}>
                      {sizeTotals.t[sz]}
                    </button>
                  ) : sizeTotals.t[sz]}
                </td>
              ))}
              <td className="px-2 py-1.5 text-right font-mono font-bold bg-[#0F172A] text-[#C27842]">{group.totalQty}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* --- UNIFIED PARALLEL COMPONENTS & KARIGAR ASSIGNMENT --- */}
      <div className="px-3 pb-2.5">
        {/* Component Cards: Upper, Bottom/Insole, Sole, Heel (if heel) */}
        {/* Click a component to expand its karigar assignment panel below */}
        <div className={`grid ${group.footwear_type === "heel" ? "grid-cols-4" : "grid-cols-3"} gap-2`}>
          {[
            { compKey: "upper", label: "Upper", doneKey: "upper_done", done: group.components.upper_done },
            { compKey: "bottom", label: "Bottom", doneKey: "bottom_done", done: group.components.bottom_done },
            { compKey: "sole", label: "Sole", doneKey: "sole_done", done: group.components.sole_done },
            ...(group.footwear_type === "heel"
              ? [{ compKey: "heel_gola", label: "Heel/Gola", doneKey: "heel_gola_done", done: group.components.heel_gola_done }]
              : []),
          ].map(({ compKey, label, doneKey, done }) => (
            <ParallelComponentCard
              key={compKey}
              compKey={compKey}
              label={label}
              done={done}
              layers={COMPONENT_LAYERS[compKey]}
              assignment={getComponentAssignment(a, compKey)}
              assignments={a}
              subtasks={getSubtasksForComp(compKey)}
              outsideCount={(outsideLabour || []).filter(o => (o.component || "").toLowerCase() === compKey).length}
              disabled={!effectiveCanEdit}
              groupKey={group.key}
              isActive={activeComp === compKey}
              onSelect={() => setActiveComp(prev => prev === compKey ? null : compKey)}
              onToggle={(v) => onToggleComponent(group, doneKey, v)}
              onOpenAssign={onOpenAssign}
              onDropWorker={onDropWorkerToComponent ? (w) => onDropWorkerToComponent(group, compKey, w) : undefined}
              draggingWorker={draggingWorker}
              isReadySole={compKey === "sole" && isSoleReadyToUse(group, style)}
            />
          ))}
        </div>

        {/* Inline Karigar Assignment Panel — shows when a component is selected */}
        {activeComp && (
          <ComponentKarigarPanel
            compKey={activeComp}
            label={activeComp === "upper" ? "Upper" : activeComp === "bottom" ? "Bottom / Insole" : activeComp === "sole" ? "Sole" : "Heel / Gola"}
            subtasks={dynamicSubtasks}
            assignments={a}
            outsideLabour={outsideLabour}
            workers={workers}
            vendors={vendors}
            canEdit={effectiveCanEdit}
            onOpenAssign={onOpenAssign}
            onSaveOutsideLabour={handleUpdateOutsideLabour}
            onCompleteOutsideLabour={handleCompleteOutsideLabour}
            groupKey={group.key}
            totalQty={group.totalQty}
            isReadySole={activeComp === "sole" && isSoleReadyToUse(group, style)}
          />
        )}

        {/* --- COMPACT ASSEMBLY LINE KARIGARS --- */}
        <div className="mt-2.5 pt-2 border-t border-slate-100">
          <div className="text-[9px] uppercase tracking-wider font-bold text-slate-400 mb-1">
            <span>Assembly Karigars</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
            {ASSEMBLY_ROLES.map((r) => {
              const asgn = a[r.key];
              const isCurrentStage = group.stage === r.stageKey;
              return (
                <button
                  key={r.key}
                  type="button"
                  disabled={!effectiveCanEdit}
                  onClick={() => onOpenAssign(r.key)}
                  data-testid={`assign-${group.key}-${r.key}`}
                  title={`Assign ${r.label} Karigar`}
                  className={`flex items-center justify-between gap-1 px-2 py-1 rounded text-left transition-all border ${
                    isCurrentStage
                      ? "border-[#A65D24] bg-amber-50/80 ring-1 ring-[#A65D24]/40"
                      : asgn
                      ? "border-slate-300 bg-slate-50/80 hover:border-slate-400"
                      : "border-dashed border-slate-200 bg-white hover:border-slate-400"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1">
                      <span className={`text-[8.5px] uppercase font-bold tracking-wider ${
                        isCurrentStage ? "text-[#A65D24]" : "text-slate-500"
                      }`}>
                        {r.label}
                      </span>
                      {isCurrentStage && (
                        <span className="w-1.5 h-1.5 rounded-full bg-[#A65D24] animate-pulse" />
                      )}
                    </div>
                    <div className={`text-[10px] font-bold truncate ${
                      asgn ? "text-slate-900" : "text-slate-400 italic"
                    }`}>
                      {asgn?.worker_name || "+ Assign"}
                    </div>
                  </div>
                  {asgn?.rate_per_pair != null && (
                    <span className="text-[9px] font-mono text-[#C27842] flex-shrink-0 font-semibold">
                      {`₹${asgn.rate_per_pair}`}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="px-3 pb-3 flex items-center justify-end gap-2 flex-wrap">
        <div className="flex gap-2 ml-auto items-center flex-wrap">
          {effectiveCanEdit && (
            <button onClick={onPrint} title="Print production card" data-testid={`print-${group.key}`}
              className="text-[10px] uppercase tracking-wider font-bold text-slate-700 hover:text-white hover:bg-[#0F172A] border border-slate-300 px-2 py-1 flex items-center gap-1">
              <Printer className="w-3 h-3" /> Print
            </button>
          )}
          {effectiveCanEdit && (
            <button onClick={onWhatsApp} title="Share via WhatsApp" data-testid={`whatsapp-${group.key}`}
              className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#25D366] hover:bg-[#1DA851] border border-[#25D366] px-2 py-1 flex items-center gap-1">
              <MessageCircle className="w-3 h-3" /> WhatsApp
            </button>
          )}
          {isProc && (
            <div className="inline-flex rounded shadow-sm">
              <button
                onClick={() => onMatReq?.(false)}
                className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-2.5 py-1 flex items-center gap-1 rounded-l"
                data-testid={`mat-req-${group.key}`}
                title="Download consolidated Material Requirement sheet"
              >
                <ClipboardList className="w-3 h-3" /> Mat. Req
              </button>
              <button
                onClick={() => onMatReq?.(true)}
                className="text-[10px] uppercase tracking-wider font-bold text-white bg-indigo-600 hover:bg-indigo-700 px-2 py-1 flex items-center gap-1 border-l border-indigo-500 rounded-r"
                data-testid={`mat-req-color-${group.key}`}
                title="Download Color-Split Material Requirement sheet"
              >
                <Palette className="w-3 h-3" /> By Color
              </button>
            </div>
          )}
          {isDispatched && (
            <button onClick={() => onOpenDispatchDetails?.(group)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-3 py-1 flex items-center gap-1 transition-colors" data-testid={`dispatch-details-btn-${group.key}`}>
              <Truck className="w-3 h-3" /> View Dispatch Details
            </button>
          )}
          {isDispatched && (
            <button
              onClick={() => {
                const jids = (group.rows || []).map(r => r.id);
                onArchiveDispatched?.(jids, `${group.style_code} (${group.color})`);
              }}
              className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-3 py-1 flex items-center gap-1 transition-colors shadow-sm"
              data-testid={`archive-btn-${group.key}`}
              title="Verify and move this card (and any merged constituent cards) to Archive"
            >
              <Archive className="w-3 h-3 text-amber-400" /> Move to Archive
            </button>
          )}
          {isDispatched && (
            <button onClick={() => onDownloadInvoice(group)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#C27842] hover:bg-[#A65D24] px-3 py-1 flex items-center gap-1" data-testid={`invoice-btn-${group.key}`}>
              <FileDown className="w-3 h-3" /> Invoice
            </button>
          )}
          {isDispatched && (
            <button onClick={onPacking} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#16A34A] hover:bg-[#0F7A36] px-3 py-1 flex items-center gap-1" data-testid={`packing-btn-${group.key}`}>
              <Package className="w-3 h-3" /> Packing List
            </button>
          )}
          {isDispatched && (
            <>
              <button
                onClick={async () => {
                  if (drec) {
                    onDownloadDispatchFile(drec.id, "carton-labels", `CartonLabels-${drec.invoice_no}.pdf`, "application/pdf");
                  } else {
                    try {
                      const res = await http.get(`/production/jobs/carton-labels?job_ids=${group.rows.map(r => r.id).join(",")}`, { responseType: "blob" });
                      triggerDownload(res.data, `CartonLabels-${(group.po_number || "dispatch").replace(/[\/\\]/g, "-")}-${group.style_code}.pdf`, "application/pdf");
                    } catch (e) {
                      alert("Carton Labels download failed: " + (e.response?.data?.detail || e.message));
                    }
                  }
                }}
                className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-3 py-1 flex items-center gap-1"
                data-testid={`labels-btn-${group.key}`}
              >
                <FileDown className="w-3 h-3" /> Carton Labels
              </button>
              <button
                onClick={async () => {
                  if (drec) {
                    onDownloadDispatchFile(drec.id, "carton-list", `CartonList-${drec.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
                  } else {
                    try {
                      const res = await http.get(`/production/jobs/carton-list?job_ids=${group.rows.map(r => r.id).join(",")}`, { responseType: "blob" });
                      triggerDownload(res.data, `CartonList-${(group.po_number || "dispatch").replace(/[\/\\]/g, "-")}-${group.style_code}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
                    } catch (e) {
                      alert("Carton List download failed: " + (e.response?.data?.detail || e.message));
                    }
                  }
                }}
                className="text-[10px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-3 py-1 flex items-center gap-1"
                data-testid={`carton-list-btn-${group.key}`}
              >
                <FileDown className="w-3 h-3" /> Carton List
              </button>
            </>
          )}
          {group.stage === "qc_pack" && (
            <button onClick={onPackCartons} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#7C3AED] hover:bg-[#6D28D9] px-3 py-1 flex items-center gap-1" data-testid={`pack-carton-btn-${group.key}`}>
              <Package className="w-3 h-3" /> Pack Carton
            </button>
          )}
          {group.stage === "qc_pack" && (
            <button onClick={onDispatch} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-3 py-1 flex items-center gap-1" data-testid={`dispatch-btn-${group.key}`}>
              <FileDown className="w-3 h-3" /> Dispatch Docs
            </button>
          )}
          {canEdit && prevStage && (
            <button disabled={!effectiveCanEdit} onClick={() => onMove(group, prevStage.key)} className={`text-[10px] uppercase tracking-wider font-bold border px-2 py-1 ${effectiveCanEdit ? 'text-slate-500 hover:text-slate-900 border-slate-300' : 'text-slate-300 border-slate-200 cursor-not-allowed'}`}>← {prevStage.label}</button>
          )}
          {canEdit && nextStage && group.stage !== "qc_pack" && (() => {
            const isLastingTarget = nextStage.key === "lasting";
            const isBlocked = isLastingTarget && (!group.components.upper_done || !group.components.bottom_done);
            const isDisabled = !effectiveCanEdit || isBlocked;
            return (
              <button
                disabled={isDisabled}
                onClick={() => onMove(group, nextStage.key)}
                title={isBlocked ? "Cannot move to lasting: upper and/or bottom not completed" : ""}
                className={`text-[10px] uppercase tracking-wider font-bold text-white px-3 py-1 ${
                  !isDisabled ? 'bg-[#0F172A] hover:bg-[#C27842]' : 'bg-slate-300 cursor-not-allowed opacity-60'
                }`}
                data-testid={`move-next-${group.key}`}
              >
                {nextStage.label} →
              </button>
            );
          })()}
        </div>
      </div>
      {localPreview && (
        <ImageViewModal
          isOpen={!!localPreview}
          src={localPreview.src}
          title={localPreview.title}
          subtitle={localPreview.subtitle}
          alt={localPreview.alt}
          onClose={() => setLocalPreview(null)}
        />
      )}
    </Card>
  );
}

/**
 * ParallelComponentCard — clickable tab-style card for each component track.
 * Displays the primary assigned person for this component, status toggle,
 * and quick summary of subtasks & outside work.
 * Clicking expands the full inline assignment & outside work panel below.
 */
function ParallelComponentCard({
  compKey,
  label,
  done,
  layers = [],
  assignment,
  assignments = {},
  outsideCount = 0,
  subtasks: propSubtasks,
  onToggle,
  onSelect,
  onOpenAssign,
  isActive,
  disabled,
  groupKey,
  onDropWorker,
  draggingWorker,
  isReadySole = false,
}) {
  const [isOver, setIsOver] = useState(false);
  const subtasks = propSubtasks !== undefined ? propSubtasks : (COMPONENT_SUBTASK_ROLES[compKey] || []);

  return (
    <div
      onDragOver={(e) => {
        if (!draggingWorker || !onDropWorker || isReadySole) return;
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        if (!draggingWorker || !onDropWorker || isReadySole) return;
        e.preventDefault();
        setIsOver(false);
        onDropWorker(draggingWorker);
      }}
      className={`rounded-lg flex flex-col border-2 transition-all cursor-pointer select-none ${
        isOver
          ? "border-[#C27842] bg-orange-100/70 shadow-md scale-[1.02]"
          : isActive
          ? "border-[#C27842] bg-amber-50/60 shadow-md ring-2 ring-[#C27842]/20"
          : done
          ? "border-emerald-300 bg-emerald-50/40 shadow-xs hover:border-emerald-400"
          : "border-slate-200 bg-white hover:border-[#C27842]/50 shadow-xs"
      }`}
      data-testid={`component-card-${compKey}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); } }}
      aria-expanded={isActive}
      aria-label={`${label} component — click to ${isActive ? "collapse" : "expand"} karigar assignment`}
    >
      {/* Component name + status badge */}
      <div className="px-2 pt-2 pb-1">
        <div className="flex items-center justify-between gap-1">
          <span className={`text-[11px] uppercase font-black tracking-wider truncate ${
            isActive ? "text-[#A65D24]" : done ? "text-emerald-700" : "text-slate-800"
          }`} title={label}>
            {label}
          </span>
          <span className={`text-[10px] transition-transform duration-200 ${
            isActive ? "rotate-180 text-[#C27842]" : "text-slate-400"
          }`}>▼</span>
        </div>

        {/* Ready / Pending toggle */}
        <div className="mt-1 flex items-center justify-between gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onToggle(!done)}
            data-testid={`toggle-comp-${groupKey}-${compKey}`}
            title={done ? "Click to mark In Progress" : "Click to mark Ready"}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold transition-all border ${
              done
                ? "bg-emerald-600 text-white border-emerald-600 shadow-xs hover:bg-emerald-700"
                : "bg-slate-100 text-slate-600 border-slate-300 hover:bg-slate-200"
            }`}
          >
            {done ? (
              <><Check className="w-2.5 h-2.5 stroke-[3]" /><span>Ready</span></>
            ) : (
              <span>Pending</span>
            )}
          </button>

          {outsideCount > 0 && (
            <span
              className="text-[8px] font-bold px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 flex items-center gap-0.5"
              title={`${outsideCount} Outside Labour operation(s)`}
            >
              {`🏭 ${outsideCount} Outside`}
            </span>
          )}
        </div>
      </div>

      {/* Main Assigned Person for this component */}
      <div className="px-2 pb-1.5">
        {isReadySole ? (
          <div className="px-2 py-1.5 rounded bg-emerald-50/70 border border-emerald-200" data-testid={`ready-sole-indicator-${groupKey}`}>
            <div className="flex items-center justify-between gap-1">
              <div className="text-[10px] font-bold text-emerald-800 truncate flex items-center gap-1 min-w-0">
                <Check className="w-3 h-3 text-emerald-600 flex-shrink-0" />
                <span>Ready-to-use Sole</span>
              </div>
              <span className="text-[8px] uppercase font-bold text-emerald-700 bg-emerald-100/90 px-1 py-0.5 rounded border border-emerald-300">
                No Sub-tasks
              </span>
            </div>
            <button
              type="button"
              disabled={true}
              data-testid={`assign-${groupKey}-${compKey}`}
              className="sr-only"
              aria-label="Sole assignment disabled - ready to use"
            >
              Disabled
            </button>
          </div>
        ) : (
          <div
            className="px-2 py-1.5 rounded bg-slate-50 border border-slate-200 hover:border-[#C27842]/60 transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onOpenAssign?.(compKey);
            }}
          >
            <div className="flex items-center justify-between gap-1">
              <div className="text-[10.5px] font-bold text-slate-900 truncate flex items-center gap-1 min-w-0">
                {assignment?.worker_name ? (
                  <>
                    <span className="text-[10px] flex-shrink-0">👤</span>
                    <span className="truncate">{assignment.worker_name}</span>
                  </>
                ) : (
                  <span className="text-slate-400 italic font-normal text-[10px]">+ Assign Person</span>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <button
                  type="button"
                  disabled={disabled}
                  data-testid={`assign-${groupKey}-${compKey}`}
                  className="text-[8.5px] uppercase font-bold text-[#C27842] hover:text-[#A65D24] px-1 py-0.5 rounded hover:bg-orange-50 transition-colors"
                >
                  {assignment?.worker_name ? "Change" : "Assign"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Subtasks summary badges (only assigned specialists) */}
      {!isReadySole && subtasks.some(st => assignments[st.key]?.worker_name) && (
        <div className="px-2 pb-1.5 mt-auto">
          <div className="flex items-center gap-1 flex-wrap">
            {subtasks.filter(st => assignments[st.key]?.worker_name).map((st) => {
              const stAsgn = assignments[st.key];
              return (
                <span
                  key={st.key}
                  title={`${st.label}: ${stAsgn.worker_name}`}
                  className="inline-flex items-center gap-0.5 text-[8px] font-bold px-1.5 py-0.5 rounded-full border bg-[#C27842]/10 text-[#A65D24] border-[#C27842]/30"
                >
                  <span>{st.icon}</span>
                  <span className="truncate max-w-[44px]">
                    {stAsgn.worker_name.split(" ")[0]}
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * ComponentKarigarPanel — shown below the component grid when a component is selected.
 * Displays:
 * 1. Component Main Assigned Person (Lead / Karigar)
 * 2. Process Sub-tasks (Cutting, Stitching, Folding, etc.) assigned to other workers
 * 3. Extra Outside Labour Work (Job Work / Outsourced) belonging strictly to Upper, Bottom, or Sole
 */
function ComponentKarigarPanel({
  compKey,
  label,
  subtasks = [],
  assignments = {},
  outsideLabour = [],
  workers = [],
  vendors = [],
  canEdit,
  onOpenAssign,
  onSaveOutsideLabour,
  onCompleteOutsideLabour,
  groupKey,
  totalQty = 0,
  isReadySole = false,
}) {
  const compColors = {
    upper: { bg: "bg-sky-50/60", border: "border-sky-300", header: "bg-sky-700", accent: "text-sky-700", badge: "bg-sky-100 text-sky-800 border-sky-200" },
    bottom: { bg: "bg-violet-50/60", border: "border-violet-300", header: "bg-violet-700", accent: "text-violet-700", badge: "bg-violet-100 text-violet-800 border-violet-200" },
    sole: { bg: "bg-teal-50/60", border: "border-teal-300", header: "bg-teal-700", accent: "text-teal-700", badge: "bg-teal-100 text-teal-800 border-teal-200" },
    heel_gola: { bg: "bg-rose-50/60", border: "border-rose-300", header: "bg-rose-700", accent: "text-rose-700", badge: "bg-rose-100 text-rose-800 border-rose-200" },
  };
  const c = compColors[compKey] || compColors.upper;

  // Filter outside labour belonging strictly to this component
  const compOutsideLabour = (outsideLabour || []).filter(o => (o.component || "").toLowerCase() === compKey);
  const isEligibleForOutside = ["upper", "bottom", "sole"].includes(compKey);

  const mainAssignee = assignments[compKey];
  const [showAddOutside, setShowAddOutside] = useState(false);
  const [newOutsideName, setNewOutsideName] = useState("");
  const [newOutsideSubstage, setNewOutsideSubstage] = useState("");
  const [newOutsideVendorId, setNewOutsideVendorId] = useState("");
  const [newOutsideVendor, setNewOutsideVendor] = useState("");
  const [newOutsideRate, setNewOutsideRate] = useState("");
  const [newOutsideQty, setNewOutsideQty] = useState(totalQty || "");
  const [newOutsideNotes, setNewOutsideNotes] = useState("");

  const handleAddOutside = () => {
    if (!newOutsideName.trim()) {
      alert("Please enter work / operation name.");
      return;
    }
    if (!newOutsideVendorId && !newOutsideVendor.trim()) {
      alert("Vendor is required for outside labour work. Please select a registered vendor.");
      return;
    }
    const newItem = {
      id: Math.random().toString(36).slice(2, 11),
      name: newOutsideName.trim(),
      component: compKey,
      substage: newOutsideSubstage || "job_work",
      vendor_id: newOutsideVendorId,
      vendor_name: newOutsideVendor.trim(),
      vendor: newOutsideVendor.trim(),
      rate: Number(newOutsideRate) || 0,
      qty: Number(newOutsideQty) || (totalQty || 0),
      notes: newOutsideNotes.trim(),
      is_outside: true,
      completed: false,
    };
    onSaveOutsideLabour?.([...(outsideLabour || []), newItem]);
    setNewOutsideName("");
    setNewOutsideSubstage("");
    setNewOutsideVendorId("");
    setNewOutsideVendor("");
    setNewOutsideRate("");
    setNewOutsideQty(totalQty || "");
    setNewOutsideNotes("");
    setShowAddOutside(false);
  };

  const handleDeleteOutside = (idxToDelete) => {
    const updated = (outsideLabour || []).filter((_, idx) => idx !== idxToDelete);
    onSaveOutsideLabour?.(updated);
  };

  return (
    <div className={`mt-2 rounded-lg border-2 ${c.border} ${c.bg} overflow-hidden shadow-xs`}
      data-testid={`comp-karigar-panel-${compKey}`}
    >
      {/* Panel header */}
      <div className={`${c.header} text-white px-3 py-1.5 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <HardHat className="w-3.5 h-3.5" />
          <span className="text-[11px] font-black uppercase tracking-wider">{label} Track Assignment</span>
        </div>
      </div>

      <div className="p-2.5 space-y-3">
        {/* SECTION 1: COMPONENT ASSIGNED PERSON */}
        <div>
          <div className="text-[9.5px] uppercase tracking-wider font-black text-slate-700 mb-1 flex items-center gap-1">
            <span>👤</span>
            <span>1. Component Assigned Person</span>
          </div>
          <div className="bg-white border-2 border-slate-200 rounded-lg p-2.5 flex items-center justify-between gap-3 shadow-xs">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-black flex-shrink-0 ${
                mainAssignee?.worker_name ? "bg-amber-100 text-amber-800 border border-amber-300" : "bg-slate-100 text-slate-400"
              }`}>
                👤
              </div>
              <div className="min-w-0">
                <div className="text-[12px] font-bold text-slate-900 truncate">
                  {isReadySole ? (
                    <span className="text-emerald-800 font-semibold flex items-center gap-1">
                      <Check className="w-3.5 h-3.5 text-emerald-600" /> Ready-to-Use Sole (Vendor-Supplied)
                    </span>
                  ) : (
                    mainAssignee?.worker_name || <span className="text-slate-400 italic">No Karigar Assigned</span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {mainAssignee?.rate_per_pair != null && (
                <span className="text-[11px] font-mono font-bold text-[#C27842] px-2 py-0.5 rounded bg-orange-50 border border-orange-200">
                  ₹{mainAssignee.rate_per_pair}/pr
                </span>
              )}
              {isReadySole ? (
                <button
                  type="button"
                  disabled={true}
                  className="text-[10px] uppercase tracking-wider font-bold bg-slate-100 text-slate-400 px-3 py-1.5 rounded border border-slate-200 cursor-not-allowed"
                  title="Sub-task and karigar assignment is disabled because this style uses a ready-to-use sole"
                >
                  Assignment Disabled
                </button>
              ) : (
                canEdit && (
                  <button
                    type="button"
                    onClick={() => onOpenAssign(compKey)}
                    data-testid={`assign-lead-${groupKey}-${compKey}`}
                    className="text-[10px] uppercase tracking-wider font-bold bg-[#0F172A] text-white hover:bg-slate-800 px-3 py-1.5 rounded shadow-xs transition-colors"
                  >
                    {mainAssignee?.worker_name ? "Change Person" : "Assign Person"}
                  </button>
                )
              )}
            </div>
          </div>
        </div>

        {/* SECTION 2: PROCESS SUB-TASKS */}
        <div>
          <div className="text-[9.5px] uppercase tracking-wider font-black text-slate-700 mb-1 flex items-center gap-1">
            <span>⚡</span>
            <span>2. Process Sub-tasks</span>
          </div>

          {isReadySole ? (
            <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-lg flex items-start gap-2.5" data-testid="sole-ready-to-use-disabled-banner">
              <Check className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-bold text-emerald-950 flex items-center gap-1.5">
                  <span>Ready-to-Use Sole</span>
                  <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-emerald-200 text-emerald-900 font-extrabold">Sub-tasks Disabled</span>
                </div>
                <div className="text-[11px] text-emerald-800 mt-0.5 leading-relaxed">
                  This style uses a pre-formed / vendor-supplied sole. Sub-task assignment is disabled because no in-house sole cutting, prep, or processing is required.
                </div>
              </div>
            </div>
          ) : subtasks.length === 0 ? (
            <div className="text-[10px] text-slate-400 italic bg-white/70 border border-dashed border-slate-300 rounded px-3 py-2 text-center">
              Vendor-supplied / Ready-to-use component. No internal sub-tasks required.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {subtasks.map((st) => {
                const asgn = assignments[st.key] || (st.fallbackKey ? assignments[st.fallbackKey] : null);
                const isDirectlyAssigned = !!assignments[st.key]?.worker_name;
                return (
                  <button
                    key={st.key}
                    type="button"
                    disabled={!canEdit}
                    onClick={(e) => { e.stopPropagation(); onOpenAssign(st.key); }}
                    data-testid={`assign-${groupKey}-${st.key}`}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border text-left transition-all group ${
                      asgn?.worker_name
                        ? "bg-white border-[#C27842]/40 hover:border-[#C27842] shadow-xs"
                        : "bg-white/70 border-dashed border-slate-300 hover:border-[#C27842] hover:bg-white"
                    } ${!canEdit ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    <span className="text-base flex-shrink-0" aria-hidden>{st.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[9.5px] uppercase font-bold text-slate-500 tracking-wider">
                        {st.label}
                      </div>
                      <div className={`text-[11px] font-bold truncate ${
                        asgn?.worker_name ? "text-slate-900" : "text-slate-400 italic"
                      }`}>
                        {asgn?.worker_name ? (
                          <span>
                            {asgn.worker_name}
                            {!isDirectlyAssigned && (
                              <span className="ml-1 text-[8.5px] text-slate-400 font-normal">(Component Lead)</span>
                            )}
                          </span>
                        ) : (
                          "+ Assign other worker"
                        )}
                      </div>
                    </div>
                    {asgn?.rate_per_pair != null ? (
                      <span className="text-[10px] font-mono font-bold text-[#C27842] flex-shrink-0">
                        ₹{asgn.rate_per_pair}/pr
                      </span>
                    ) : (
                      canEdit && <UserPlus className="w-3.5 h-3.5 text-slate-300 group-hover:text-[#C27842] flex-shrink-0 transition-colors" />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* SECTION 3: OUTSIDE LABOUR WORK */}
        {isEligibleForOutside && (
          <div className="pt-2 border-t border-slate-200">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-xs">🏭</span>
                <span className="text-[9.5px] uppercase tracking-wider font-black text-amber-900">
                  3. Outside Labour Work
                </span>
              </div>
              {canEdit && !showAddOutside && (
                <button
                  type="button"
                  onClick={() => setShowAddOutside(true)}
                  className="text-[9px] uppercase font-bold text-amber-700 hover:text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-300 px-2 py-0.5 rounded shadow-xs transition-colors"
                >
                  + Add Outside Work
                </button>
              )}
            </div>

            {/* List existing outside labour work for this component */}
            {compOutsideLabour.length === 0 && !showAddOutside && (
              <div className="text-[9.5px] text-slate-400 italic bg-white/60 border border-dashed border-slate-300 rounded px-3 py-1.5 flex items-center justify-between">
                <span>No outside job work linked to {label}.</span>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => setShowAddOutside(true)}
                    className="text-[9px] font-bold text-amber-700 hover:underline"
                  >
                    + Add now
                  </button>
                )}
              </div>
            )}

            {compOutsideLabour.length > 0 && (
              <div className="space-y-1">
                {compOutsideLabour.map((item, idx) => {
                  const globalIdx = (outsideLabour || []).indexOf(item);
                  return (
                    <div
                      key={item.id || idx}
                      className="bg-white border border-amber-200 rounded px-2.5 py-1.5 flex items-center justify-between gap-2 shadow-xs"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-[10.5px] font-bold text-slate-900 flex items-center gap-1.5 truncate">
                          <span>{item.name}</span>
                          {item.completed ? (
                            <span className="text-[8px] bg-emerald-100 text-emerald-800 border border-emerald-300 px-1.5 py-0.2 rounded uppercase font-semibold">
                              ✓ Billed (AP)
                            </span>
                          ) : (
                            <span className="text-[8px] bg-amber-100 text-amber-800 px-1.5 py-0.2 rounded uppercase font-semibold">
                              Outsourced
                            </span>
                          )}
                        </div>
                        {item.vendor && (
                          <div className="text-[9.5px] text-slate-500 truncate flex items-center gap-1.5">
                            <span>Vendor: <span className="font-semibold text-slate-700">{item.vendor}</span></span>
                            {item.qty && <span className="text-slate-400">· {item.qty} pr</span>}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {item.rate != null && (
                          <span className="text-[10px] font-mono font-bold text-amber-800 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                            ₹{item.rate}/pr
                          </span>
                        )}
                        {!item.completed && canEdit && (
                          <button
                            type="button"
                            onClick={() => onCompleteOutsideLabour?.(item.id || item.name)}
                            data-testid={`complete-outside-${item.id || idx}`}
                            className="text-[8.5px] uppercase font-bold text-white bg-amber-700 hover:bg-amber-800 px-2 py-0.5 rounded shadow-xs transition-colors"
                            title="Mark completed and post vendor bill to Accounts Payable"
                          >
                            Mark Done &amp; Bill
                          </button>
                        )}
                        {canEdit && !item.completed && (
                          <button
                            type="button"
                            onClick={() => handleDeleteOutside(globalIdx)}
                            className="text-slate-400 hover:text-red-600 p-0.5 transition-colors"
                            title="Remove outside work"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Inline Add Form */}
            {showAddOutside && (
              <div className="mt-1.5 p-2 bg-amber-50/70 border border-amber-300 rounded-lg shadow-xs space-y-2">
                <div className="text-[9.5px] font-bold uppercase text-amber-900 flex items-center gap-1">
                  <span>🏭</span>
                  <span>New Outside Labour Work for {label} (AP Vendor Payable)</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  <input
                    value={newOutsideName}
                    onChange={(e) => setNewOutsideName(e.target.value)}
                    placeholder="Work name (e.g. Screen Printing, Embossing)"
                    className="border border-slate-300 rounded px-2 py-1 text-xs focus:border-amber-500 focus:outline-none bg-white"
                    data-testid="outside-work-name-input"
                  />
                  <div>
                    <select
                      value={newOutsideVendorId}
                      onChange={(e) => {
                        const vid = e.target.value;
                        setNewOutsideVendorId(vid);
                        const v = vendors.find(vend => (vend.id || vend._id) === vid);
                        setNewOutsideVendor(v ? v.name : "");
                      }}
                      className="w-full border border-slate-300 rounded px-2 py-1 text-xs focus:border-amber-500 focus:outline-none bg-white font-medium"
                      data-testid="outside-vendor-select"
                    >
                      <option value="">-- Select Vendor / Contractor --</option>
                      {vendors.map((v) => (
                        <option key={v.id || v._id} value={v.id || v._id}>
                          {v.name} ({v.category || "Vendor"})
                        </option>
                      ))}
                    </select>
                    {vendors.length === 0 && (
                      <div className="text-[9px] text-amber-800 mt-0.5 italic">
                        No vendors found. Add in Vendor Master first.
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                  <div>
                    <label className="text-[9px] font-bold uppercase text-slate-500">Rate (₹/pr)</label>
                    <input
                      type="number"
                      step="0.5"
                      value={newOutsideRate}
                      onChange={(e) => setNewOutsideRate(e.target.value)}
                      placeholder="Rate ₹"
                      className="w-full border border-slate-300 rounded px-2 py-1 text-xs font-mono focus:border-amber-500 focus:outline-none bg-white"
                      data-testid="outside-rate-input"
                    />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold uppercase text-slate-500">Pairs (Qty)</label>
                    <input
                      type="number"
                      value={newOutsideQty}
                      onChange={(e) => setNewOutsideQty(e.target.value)}
                      placeholder="Qty"
                      className="w-full border border-slate-300 rounded px-2 py-1 text-xs font-mono focus:border-amber-500 focus:outline-none bg-white"
                    />
                  </div>
                  <div>
                    <label className="text-[9px] font-bold uppercase text-slate-500">Substage / Notes</label>
                    <input
                      value={newOutsideNotes}
                      onChange={(e) => setNewOutsideNotes(e.target.value)}
                      placeholder="Notes (optional)"
                      className="w-full border border-slate-300 rounded px-2 py-1 text-xs focus:border-amber-500 focus:outline-none bg-white"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-1 border-t border-amber-200">
                  <button
                    type="button"
                    onClick={() => setShowAddOutside(false)}
                    className="text-[9.5px] font-bold text-slate-500 hover:text-slate-700 px-2 py-1"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleAddOutside}
                    data-testid="save-outside-labour-btn"
                    className="text-[9.5px] font-bold uppercase tracking-wider bg-amber-700 hover:bg-amber-800 text-white px-3 py-1 rounded shadow-xs"
                  >
                    Save Outside Work
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ComponentCell({ label, done, layers = [], onToggle, disabled }) {
  return (
    <div className={`border-2 p-2 ${done ? "border-[#16A34A] bg-green-50" : "border-slate-200 bg-white"}`}>
      <button type="button" disabled={disabled} onClick={() => onToggle(!done)}
        className="w-full flex items-center justify-between gap-1 text-left">
        <span className="text-[10px] uppercase tracking-wider font-bold text-slate-700">{label}</span>
        <span className={`w-4 h-4 grid place-items-center border-2 ${done ? "bg-[#16A34A] border-[#16A34A]" : "border-slate-400 bg-white"}`}>
          {done && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
        </span>
      </button>
      <div className="mt-1 space-y-0.5">
        {(layers || []).map(l => <div key={l} className="text-[9px] text-slate-500 leading-tight">• {l}</div>)}
      </div>
    </div>
  );
}

function AssignDialog({ group, role, workers, current, onSave, onClose, styleByCode = {} }) {
  const [selectedWid, setSelectedWid] = useState(current?.worker_id || "");
  const [rate, setRate] = useState(current?.rate_per_pair ?? "");
  const [overwriteSubtasks, setOverwriteSubtasks] = useState(false);
  const selectedWorker = workers.find(w => w.id === selectedWid);

  const style = styleByCode[group.style_code];
  const isReadySoleDisabled = (role === "sole" || role.startsWith("sole.")) && isSoleReadyToUse(group, style);

  const isComponentRole = ["upper", "bottom", "sole", "heel_gola"].includes(role);
  const isSubTaskRole = role.includes(".");
  const roleObj = ASSIGNMENT_ROLES.find(r => r.key === role);

  let roleLabel = roleObj?.label;
  if (!roleLabel && isSubTaskRole) {
    const [c, ...s] = role.split(".");
    const substageName = s.join(" ");
    if (substageName === "stamping" || substageName === "brand_marking" || substageName === "stamping_brand_marking") {
      roleLabel = `${c.toUpperCase()} · Stamping / Brand Marking`;
    } else {
      roleLabel = `${c.toUpperCase()} · ${substageName.replace(/_/g, " ")}`;
    }
  } else if (!roleLabel) {
    roleLabel = role.replace(/_/g, " ");
  }

  const matchingSkill =
    role.includes("stitch") ? "stitching" :
    role.startsWith("upper") || role.startsWith("bottom") ? "cutting" :
    role.startsWith("sole") || role.startsWith("heel_gola") ? "finishing" :
    role;
  const sorted = [...workers]
    .filter(w => w.active !== false || w.id === selectedWid)
    .sort((a, b) => {
      const am = (a.skill === matchingSkill || a.skill === "general") ? 0 : 1;
      const bm = (b.skill === matchingSkill || b.skill === "general") ? 0 : 1;
      return am - bm;
    });

  const roleHistory = useMemo(() => {
    const events = [];
    const seen = new Set();
    (group.rows || []).forEach(r => {
      (r.history || []).forEach(h => {
        if (!h) return;
        const isAssignment = (h.event === "assignment_update" || h.event === "bulk_assignment") && h.role === role;
        const isCompletion = (h.role === role || h.stage === role) && (h.completed_qty != null || h.completed_by != null);
        if (isAssignment || isCompletion) {
          const key = `${h.at}_${h.worker_id || h.completed_by?.worker_id}_${h.event || h.stage}_${h.completed_qty}`;
          if (!seen.has(key)) {
            seen.add(key);
            events.push(h);
          }
        }
      });
    });
    return events.sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0));
  }, [group, role]);

  const onPickWorker = (w) => {
    if (isReadySoleDisabled) return;
    setSelectedWid(w.id);
    if (rate === "" || rate === null || rate === undefined) setRate(w.rate_per_pair);
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 overflow-y-auto" data-testid="assign-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md max-h-[100dvh] overflow-y-auto">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Assign Karigar</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · {roleLabel}</div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 touch-manipulation"><X className="w-5 h-5" /></button>
        </div>

        {isReadySoleDisabled && (
          <div className="px-5 py-3 bg-amber-50 border-b border-amber-200 text-xs text-amber-900 flex items-start gap-2.5" data-testid="assign-sole-disabled-warning">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-bold">Sub-task Assignment Disabled</div>
              <div className="text-[11px] text-amber-800 mt-0.5 leading-relaxed">
                This style uses a ready-to-use / vendor-supplied sole. Sub-task and karigar assignment is disabled because no in-house sole preparation is required.
              </div>
            </div>
          </div>
        )}

        {current?.worker_name && (
          <div className="px-5 py-2.5 bg-amber-50 border-b border-amber-200 text-xs flex items-center justify-between" data-testid="current-assignee-banner">
            <div>
              <span className="text-[10px] uppercase font-bold text-amber-800 tracking-wider">Current Assignee: </span>
              <span className="font-bold text-slate-900">{current.worker_name}</span>
            </div>
            {current.rate_per_pair != null && (
              <span className="font-mono font-bold text-amber-900">₹{current.rate_per_pair}/pr</span>
            )}
          </div>
        )}

        <div className="p-5 max-h-[40vh] overflow-y-auto">
          {isReadySoleDisabled ? (
            <div className="text-center text-xs text-slate-500 py-8 bg-slate-50 border border-dashed border-slate-200 rounded-lg" data-testid="assign-sole-disabled-placeholder">
              Karigar assignment is disabled for ready-to-use soles.
            </div>
          ) : sorted.length === 0 ? (
            <div className="text-center text-sm text-slate-500 py-8">No karigars yet.</div>
          ) : (
            <div className="space-y-1.5">
              <button
                onClick={() => onSave(null, null, overwriteSubtasks)}
                data-testid="assign-clear"
                className="w-full text-left px-3 py-3 border border-slate-200 hover:border-red-500 hover:text-red-700 text-xs font-bold uppercase tracking-wider min-h-[44px] touch-manipulation"
              >
                ✕ Unassign
              </button>
              {sorted.map(w => (
                <button
                  key={w.id}
                  onClick={() => onPickWorker(w)}
                  data-testid={`assign-worker-${w.id}`}
                  className={`w-full text-left px-3 py-3 border ${selectedWid === w.id ? "border-[#C27842] bg-orange-50" : "border-slate-200"} hover:border-[#0F172A] flex items-center justify-between min-h-[44px] touch-manipulation`}
                >
                  <div>
                    <div className="font-bold text-sm">{w.name}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">{w.skill}{w.phone ? ` · ${w.phone}` : ""}</div>
                  </div>
                  <div className="text-xs font-mono">default ₹{w.rate_per_pair}/pr</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {roleHistory.length > 0 && (
          <div className="px-5 py-3 border-t-2 border-slate-200 bg-slate-50" data-testid="assignment-history-section">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-2 flex items-center justify-between">
              <span>Assignment & Completion History</span>
              <span className="font-mono text-slate-400 font-normal">({roleHistory.length} events)</span>
            </div>
            <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
              {roleHistory.map((h, i) => {
                const wName = h.completed_by?.worker_name || h.worker_name || (h.worker_id ? (workers.find(w => w.id === h.worker_id)?.name || h.worker_id) : "Unassigned");
                const wRate = h.completed_by?.rate_per_pair ?? h.rate_per_pair;
                const isCompletion = h.completed_qty != null || h.completed_by != null;
                return (
                  <div key={i} className="text-xs p-2 bg-white border border-slate-200 rounded flex items-center justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded ${isCompletion ? "bg-emerald-100 text-emerald-800" : "bg-blue-100 text-blue-800"}`}>
                          {isCompletion ? "Completed" : "Assigned"}
                        </span>
                        <span className="font-bold text-slate-800">{wName}</span>
                        {isCompletion && h.completed_qty != null && (
                          <span className="text-[10px] text-slate-500 font-mono">({h.completed_qty} pairs)</span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-0.5">
                        {h.at ? new Date(h.at).toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                        {h.by ? ` · by ${h.by}` : ""}
                      </div>
                    </div>
                    {wRate != null && (
                      <div className="font-mono font-bold text-slate-700 text-right text-[11px]">
                        ₹{wRate}/pr
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {!isReadySoleDisabled && selectedWid && (
          <div className="px-5 py-4 border-t-2 border-slate-200 bg-slate-50 space-y-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                Rate for THIS style/role (₹/pair) — overrides default
              </label>
              <input
                type="number" step="0.5" value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder={`Default ₹${selectedWorker?.rate_per_pair || 0}/pair`}
                data-testid="assign-rate-input"
                inputMode="decimal"
                className="w-full mt-1 border-2 border-slate-300 px-3 py-3 font-mono text-lg focus:border-[#C27842] focus:outline-none min-h-[44px]"
              />
              <div className="text-[10px] text-slate-500 mt-1">
                Different styles can have different rates per role. This is the negotiated rate for this card.
              </div>
            </div>
            {isComponentRole && (
              <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-700 bg-amber-50/60 p-2.5 rounded border border-amber-200" data-testid="assign-overwrite-container">
                <input
                  type="checkbox"
                  checked={overwriteSubtasks}
                  onChange={(e) => setOverwriteSubtasks(e.target.checked)}
                  className="rounded text-[#C27842] focus:ring-[#C27842] w-4 h-4"
                  data-testid="assign-overwrite-checkbox"
                />
                <span>Overwrite already-assigned sub-tasks</span>
              </label>
            )}
            <div className="flex gap-2">
              <BtnPrimary onClick={() => onSave(selectedWid, rate === "" ? null : rate, overwriteSubtasks)} className="min-h-[44px]" data-testid="assign-save">
                <Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Assign at ₹{rate || selectedWorker?.rate_per_pair || 0}/pair
              </BtnPrimary>
              <BtnSecondary onClick={onClose} className="min-h-[44px]">Cancel</BtnSecondary>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function QuantityDialog({ group, row, onSave, onClose }) {
  const [qty, setQty] = useState(row?.quantity || 0);
  const [completed, setCompleted] = useState(row?.completed_qty || 0);
  const [rejected, setRejected] = useState(row?.rejected_qty || 0);
  const [reason, setReason] = useState("");

  const save = () => {
    onSave({
      quantity: Number(qty),
      completed_qty: Number(completed),
      rejected_qty: Number(rejected),
      reason,
    });
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 overflow-y-auto" data-testid="qty-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md max-h-[100dvh] overflow-y-auto">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Edit Quantity</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · Size {row?.size}</div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Stage: {row?.stage}</div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 touch-manipulation"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Planned Qty (pairs)</label>
            <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} data-testid="qty-input-planned"
              inputMode="numeric"
              className="w-full border-2 border-slate-300 px-3 py-3 font-mono text-lg focus:border-[#2563EB] focus:outline-none min-h-[44px]" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Completed</label>
              <input type="number" value={completed} onChange={(e) => setCompleted(e.target.value)} data-testid="qty-input-completed"
                inputMode="numeric"
                className="w-full border-2 border-slate-300 px-3 py-3 font-mono focus:border-[#16A34A] focus:outline-none min-h-[44px]" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Rejected</label>
              <input type="number" value={rejected} onChange={(e) => setRejected(e.target.value)} data-testid="qty-input-rejected"
                inputMode="numeric"
                className="w-full border-2 border-slate-300 px-3 py-3 font-mono focus:border-red-500 focus:outline-none min-h-[44px]" />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Reason (optional)</label>
            <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="e.g., 5 pairs damaged in cutting"
              className="w-full border-2 border-slate-300 px-3 py-3 text-sm focus:border-[#2563EB] focus:outline-none min-h-[44px]" />
          </div>
          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary onClick={save} className="min-h-[44px]" data-testid="qty-save"><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
            <BtnSecondary onClick={onClose} className="min-h-[44px]">Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}


function WhatsAppDialog({ group, workers, onClose, onSend }) {
  // Pull phones from any karigar assigned on this card; allow custom too.
  const assigned = Object.values(group.assignments || {})
    .map(a => a?.worker_id)
    .filter(Boolean);
  const candidates = workers.filter(w => assigned.includes(w.id) && (w.phone || "").trim());
  const fallback = workers.filter(w => (w.phone || "").trim() && !candidates.find(c => c.id === w.id));
  const [phone, setPhone] = useState(candidates[0]?.phone || "");
  const [picked, setPicked] = useState(candidates[0]?.id || "");

  const pick = (w) => { setPicked(w.id); setPhone(w.phone); };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 overflow-y-auto" data-testid="whatsapp-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-lg max-h-[100dvh] overflow-y-auto">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between" style={{ background: "#25D366", color: "white" }}>
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">Share via WhatsApp</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · {group.totalQty} pairs</div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/20 touch-manipulation"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="text-xs text-slate-600 leading-relaxed bg-amber-50 border border-amber-200 px-3 py-2">
            The PDF will be <b>auto-downloaded</b> to your computer. WhatsApp Web will open with a pre-filled message. <b>Drag the downloaded PDF into the chat</b> to send it.
          </div>

          {candidates.length > 0 && (
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Assigned karigars on this card</label>
              <div className="space-y-1 mt-1">
                {candidates.map(w => (
                  <button key={w.id} onClick={() => pick(w)} data-testid={`wa-pick-${w.id}`}
                    className={`w-full flex items-center justify-between px-3 py-3 border-2 text-left min-h-[44px] touch-manipulation ${picked === w.id ? "border-[#25D366] bg-green-50" : "border-slate-200 hover:border-slate-400"}`}>
                    <div>
                      <div className="font-bold text-sm">{w.name}</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">{w.skill}</div>
                    </div>
                    <div className="font-mono text-xs">{w.phone}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {fallback.length > 0 && (
            <details>
              <summary className="text-[10px] uppercase tracking-wider font-bold text-slate-600 cursor-pointer">Other karigars</summary>
              <div className="space-y-1 mt-1 max-h-40 overflow-y-auto">
                {fallback.map(w => (
                  <button key={w.id} onClick={() => pick(w)} data-testid={`wa-pick-other-${w.id}`}
                    className={`w-full flex items-center justify-between px-3 py-2 border text-left text-sm ${picked === w.id ? "border-[#25D366] bg-green-50" : "border-slate-200 hover:border-slate-400"}`}>
                    <span><b>{w.name}</b> <span className="text-slate-500 text-xs">{w.skill}</span></span>
                    <span className="font-mono text-xs">{w.phone}</span>
                  </button>
                ))}
              </div>
            </details>
          )}

          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Phone number</label>
            <input
              value={phone} onChange={(e) => { setPhone(e.target.value); setPicked(""); }}
              placeholder="+91 98765 43210 (or leave blank to pick chat in WhatsApp)"
              data-testid="wa-phone-input"
              className="w-full mt-1 border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#25D366] focus:outline-none"
            />
            <div className="text-[10px] text-slate-500 mt-1">10-digit Indian numbers will be auto-prefixed with +91.</div>
          </div>

          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary onClick={() => onSend(phone)} data-testid="wa-send"
              className="bg-[#25D366] border-[#25D366] hover:bg-[#1DA851]">
              <MessageCircle className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Download PDF & open WhatsApp
            </BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}


/* -------------------- ARCHIVE PANEL (Stage 4 + 5 Clustered) -------------------- */
function ArchivePanel({
  summaries = [], meta = {}, filters = {}, loading = false,
  onFiltersChange, onPageChange,
  styleByCode = {}, onPrint, onPacking, onViewDetails, onViewDispatchDetails,
  savedPackingLists = [], onReDownloadPacking, dispatchRecordByJobId = {},
  onDownloadDispatchFile, onDownloadInvoice, invoices = [], onPreviewImage,
}) {
  const [expandedClusters, setExpandedClusters] = useState({});
  const toggleCluster = (id) => setExpandedClusters(prev => ({ ...prev, [id]: !prev[id] }));

  // Stage 5: per-job lazy detail state
  const [detailCache, setDetailCache] = useState({});
  const [expandedDetails, setExpandedDetails] = useState({});

  const loadDetail = async (id) => {
    if (!id || (detailCache[id] && detailCache[id] !== "loading")) return;
    setDetailCache(prev => ({ ...prev, [id]: "loading" }));
    try {
      const res = await http.get(`/production/archive/${id}`);
      setDetailCache(prev => ({ ...prev, [id]: res.data }));
    } catch (e) {
      setDetailCache(prev => ({ ...prev, [id]: null }));
      alert("Failed to load job detail: " + (e.response?.data?.detail || e.message));
    }
  };

  const toggleDetail = async (id) => {
    const next = !expandedDetails[id];
    setExpandedDetails(prev => ({ ...prev, [id]: next }));
    if (next) await loadDetail(id);
  };

  // Group by color/style and cluster by invoice
  const groups = useMemo(() => groupJobsByColor(summaries), [summaries]);
  const clusters = useMemo(() => clusterArchivedGroups(groups, dispatchRecordByJobId, invoices), [groups, dispatchRecordByJobId, invoices]);

  // Local filter input state (controlled, applied on submit/enter)
  const [localFilters, setLocalFilters] = useState(filters);
  const applyFilters = () => onFiltersChange?.(localFilters);
  const clearFilters = () => {
    const empty = { from_date: "", to_date: "", style_code: "", po_number: "", karigar_name: "", color: "" };
    setLocalFilters(empty);
    onFiltersChange?.(empty);
  };

  const toGroupLike = (doc) => {
    if (!doc) return null;
    const q = doc.quantity || doc.total_pairs || doc.totalQty || 0;
    const id = doc.id || doc._id;
    return {
      ...doc,
      id,
      po_number: doc.po_number,
      style_code: doc.style_code,
      color: doc.color,
      client_name: doc.client_name,
      rows: (doc.rows && doc.rows.length) ? doc.rows : [{
        ...doc,
        id,
        size: doc.size || "—",
        quantity: q,
        completed_qty: doc.completed_qty ?? q,
        rejected_qty: doc.rejected_qty || 0,
        stage: doc.stage || "dispatched",
        history: doc.history || [],
      }],
      totalQty: q,
      sizes: (doc.rows && doc.rows.length) ? doc.rows.map(r => r.size) : [doc.size || "—"],
      style_display: doc.style_code || "—",
      card_created_date: doc.created_at ? new Date(doc.created_at).toLocaleDateString("en-IN") : "—",
      delivery_date: doc.delivery_date || "—",
    };
  };

  const downloadInvoiceFile = async (invoiceId, invoiceNo) => {
    try {
      const res = await http.get(`/invoices/${invoiceId}/file`, { responseType: "blob" });
      triggerDownload(res.data, `Invoice-${invoiceNo || "merged"}.pdf`, "application/pdf");
    } catch (e) {
      alert("Invoice download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const downloadInvoiceCartonLabels = async (invoiceId, invoiceNo, fallbackJobIds = []) => {
    try {
      if (invoiceId) {
        try {
          const res = await http.get(`/invoices/${invoiceId}/carton-labels`, { responseType: "blob" });
          triggerDownload(res.data, `CartonLabels-${invoiceNo || "merged"}.pdf`, "application/pdf");
          return;
        } catch (err) {}
      }
      if (fallbackJobIds && fallbackJobIds.length) {
        const res = await http.get(`/production/jobs/carton-labels?job_ids=${fallbackJobIds.join(",")}`, { responseType: "blob" });
        triggerDownload(res.data, `CartonLabels-${invoiceNo || "merged"}.pdf`, "application/pdf");
      }
    } catch (e) {
      alert("Carton Labels download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const downloadCombinedCartonList = async (jobIds = [], invoiceNo = "") => {
    try {
      const res = await http.get(`/production/jobs/carton-list?job_ids=${jobIds.join(",")}`, { responseType: "blob" });
      triggerDownload(res.data, `CartonList-${invoiceNo || "merged"}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    } catch (e) {
      alert("Carton List download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const { total = 0, page = 1, pages = 1 } = meta;
  const inputCls = "border border-slate-300 px-2 py-1.5 text-xs focus:outline-none focus:border-[#C27842] w-full";

  return (
    <div className="space-y-5" data-testid="archive-list">
      {/* Header + filters */}
      <Card className="bg-slate-50 border-2 border-slate-200 p-4">
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2"><Archive className="w-4 h-4 text-slate-700" /> Archived Production Cards</h2>
            <p className="text-xs text-slate-600 mt-1">Cards that have both invoice + packing list generated land here. Grouped according to invoices. Click <b>Expand</b> to see full production history.</p>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{total} total jobs</div>
        </div>
        {/* Filter bar */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-2">
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">From date</div>
            <input type="date" value={localFilters.from_date || ""} onChange={e => setLocalFilters(f => ({ ...f, from_date: e.target.value }))} className={inputCls} data-testid="archive-filter-from" />
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">To date</div>
            <input type="date" value={localFilters.to_date || ""} onChange={e => setLocalFilters(f => ({ ...f, to_date: e.target.value }))} className={inputCls} data-testid="archive-filter-to" />
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">Style</div>
            <input placeholder="e.g. SSK-001" value={localFilters.style_code || ""} onChange={e => setLocalFilters(f => ({ ...f, style_code: e.target.value }))} onKeyDown={e => e.key === "Enter" && applyFilters()} className={inputCls} data-testid="archive-filter-style" />
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">PO Number</div>
            <input placeholder="e.g. PO-12345" value={localFilters.po_number || ""} onChange={e => setLocalFilters(f => ({ ...f, po_number: e.target.value }))} onKeyDown={e => e.key === "Enter" && applyFilters()} className={inputCls} data-testid="archive-filter-po" />
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">Color</div>
            <input placeholder="e.g. Black" value={localFilters.color || ""} onChange={e => setLocalFilters(f => ({ ...f, color: e.target.value }))} onKeyDown={e => e.key === "Enter" && applyFilters()} className={inputCls} data-testid="archive-filter-color" />
          </div>
          <div>
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 mb-1">Karigar</div>
            <input placeholder="Worker name" value={localFilters.karigar_name || ""} onChange={e => setLocalFilters(f => ({ ...f, karigar_name: e.target.value }))} onKeyDown={e => e.key === "Enter" && applyFilters()} className={inputCls} data-testid="archive-filter-karigar" />
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={applyFilters} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-700 px-3 py-1.5 flex items-center gap-1" data-testid="archive-filter-apply">
            <Eye className="w-3 h-3" /> Search
          </button>
          <button onClick={clearFilters} className="text-[10px] uppercase tracking-wider font-bold text-slate-600 border border-slate-300 hover:bg-slate-100 px-3 py-1.5 flex items-center gap-1" data-testid="archive-filter-clear">
            <X className="w-3 h-3" /> Clear
          </button>
        </div>
      </Card>

      {loading ? (
        <Card className="p-12 text-center text-slate-400 text-sm" data-testid="archive-loading">
          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-400" />
          Loading archive…
        </Card>
      ) : clusters.length === 0 ? (
        <Card className="p-12 text-center text-slate-400 text-sm" data-testid="archive-empty">
          Nothing archived yet — once both <b>Invoice</b> and <b>Packing List</b> are generated for a card it moves here automatically.
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="archive-grid">
          {clusters.map(cluster => {
            if (cluster.is_merged && cluster.groups.length > 1) {
              const isExpanded = !!expandedClusters[cluster.id];
              const allJobIds = cluster.groups.flatMap(g => g.rows.map(r => r.id || r._id)).filter(Boolean);
              const totalClusterQty = cluster.groups.reduce((sum, g) => sum + (g.totalQty || 0), 0);
              const poNumbers = Array.from(new Set(cluster.groups.map(g => g.po_number).filter(Boolean)));
              const clientName = cluster.groups[0]?.client_name;

              return (
                <Card key={cluster.id} className="border-l-4 border-[#0F172A] hover:border-blue-600 transition-colors shadow-sm" data-testid={`archive-merged-card-${cluster.id}`}>
                  <div className="p-4 space-y-3">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5 flex-wrap mb-1">
                          <span className="font-mono text-xs text-slate-500 font-bold">PO {poNumbers.join(" + ") || "—"}</span>
                          <span className="bg-[#0F172A] text-white text-[9px] font-bold px-2 py-0.5 uppercase tracking-wider rounded flex items-center gap-1">
                            <Layers className="w-2.5 h-2.5" /> Merged Dispatch ({cluster.groups.length} Styles)
                          </span>
                        </div>
                        <div className="font-mono text-sm font-bold text-slate-800">
                          Invoice: <span className="text-[#C27842]">{cluster.invoice_no || "—"}</span>
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Total Qty</div>
                        <div className="font-mono font-bold text-xl text-[#C27842]">{totalClusterQty} prs</div>
                      </div>
                    </div>

                    {clientName && (
                      <div className="text-xs text-slate-600">
                        <span className="font-bold uppercase tracking-wider text-[10px] text-slate-500">Client:</span> {clientName}
                      </div>
                    )}

                    {/* Constituent Styles & Colors List */}
                    <div className="bg-slate-50 p-2.5 rounded border border-slate-200 space-y-1.5">
                      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
                        Constituent Styles &amp; Quantities:
                      </div>
                      <div className="divide-y divide-slate-200">
                        {cluster.groups.map(g => {
                          const styleImg = styleByCode[g.style_code]?.image_thumbnail_url || styleByCode[g.style_code]?.image_url || styleByCode[g.style_code]?.image_display_url;
                          const sizeDisplay = Array.isArray(g.sizes) ? g.sizes.join(" · ") : Array.from(g.sizes || []).join(" · ");
                          return (
                            <div key={g.key} className="py-1.5 flex items-center justify-between text-xs gap-2">
                              <div className="flex items-center gap-2 min-w-0">
                                {styleImg && (
                                  <img
                                    src={styleImg}
                                    alt=""
                                    className="w-7 h-7 object-cover rounded border border-slate-200 flex-shrink-0 cursor-pointer hover:ring-2 hover:ring-[#C27842]"
                                    onClick={() => {
                                      const st = styleByCode[g.style_code];
                                      const url = st?.image_url || st?.image_display_url || styleImg;
                                      if (url) onPreviewImage?.({ src: url, title: `${g.style_code}${g.color ? ` · ${g.color}` : ""}`, subtitle: `PO #${g.po_number || "—"} · ${g.totalQty || 0} pairs` });
                                    }}
                                  />
                                )}
                                <div className="truncate">
                                  <span className="font-bold text-slate-900">{g.style_code}</span>
                                  <span className="text-slate-600 ml-1 font-semibold">({g.color})</span>
                                  <div className="text-[10px] text-slate-500 truncate">
                                    Sizes: <span className="font-mono">{sizeDisplay}</span>
                                  </div>
                                </div>
                              </div>
                              <div className="font-mono font-bold text-slate-700 text-sm whitespace-nowrap">{g.totalQty} prs</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Collapsed/Primary Action Bar */}
                    <div className="flex gap-1.5 flex-wrap pt-2 border-t border-slate-200 items-center">
                      <button
                        onClick={() => onViewDispatchDetails?.(cluster)}
                        className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-2 py-1 flex items-center gap-1 transition-colors"
                        data-testid={`archive-merged-dispatch-details-${cluster.id}`}
                      >
                        <Truck className="w-3 h-3" /> View Dispatch Details
                      </button>

                      <button
                        onClick={() => toggleCluster(cluster.id)}
                        className={`text-[10px] uppercase tracking-wider font-bold px-2 py-1 flex items-center gap-1 transition-colors ${isExpanded ? "bg-slate-800 text-white" : "bg-[#2563EB] hover:bg-[#1E40AF] text-white"}`}
                        data-testid={`archive-merged-details-btn-${cluster.id}`}
                      >
                        <Eye className="w-3 h-3" /> {isExpanded ? "Hide Cards" : "View Cards"}
                        {isExpanded ? <ChevronUp className="w-3 h-3 ml-0.5" /> : <ChevronDown className="w-3 h-3 ml-0.5" />}
                      </button>

                      {cluster.invoice_id && (
                        <button
                          onClick={() => downloadInvoiceFile(cluster.invoice_id, cluster.invoice_no)}
                          className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1"
                          data-testid={`archive-merged-invoice-btn-${cluster.id}`}
                        >
                          <FileDown className="w-3 h-3" /> Invoice
                        </button>
                      )}

                      <button
                        onClick={() => downloadInvoiceCartonLabels(cluster.invoice_id, cluster.invoice_no, allJobIds)}
                        className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-2 py-1 flex items-center gap-1"
                        data-testid={`archive-merged-labels-btn-${cluster.id}`}
                      >
                        <FileDown className="w-3 h-3" /> Labels
                      </button>

                      <button
                        onClick={() => downloadCombinedCartonList(allJobIds, cluster.invoice_no)}
                        className="text-[10px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-2 py-1 flex items-center gap-1"
                        data-testid={`archive-merged-cartonlist-btn-${cluster.id}`}
                      >
                        <FileDown className="w-3 h-3" /> Carton List
                      </button>
                    </div>

                    {/* Expanded Drill-down for individual constituent cards and pre-merge documents */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t-2 border-dashed border-slate-300 space-y-2.5 bg-slate-100/80 p-3 rounded" data-testid={`archive-merged-drilldown-${cluster.id}`}>
                        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                          Individual Pre-Merge Cards &amp; Original Documents:
                        </div>
                        {cluster.groups.map(g => {
                          let drec = null;
                          if (dispatchRecordByJobId) {
                            for (const row of g.rows || []) {
                              if (dispatchRecordByJobId[row.id]) {
                                drec = dispatchRecordByJobId[row.id];
                                break;
                              }
                            }
                          }
                          const sizeDisplay = Array.isArray(g.sizes) ? g.sizes.join(" · ") : Array.from(g.sizes || []).join(" · ");
                          return (
                            <div key={`drill-${g.key}`} className="bg-white p-2.5 rounded border border-slate-200 shadow-2xs space-y-2">
                              <div className="flex items-baseline justify-between">
                                <div>
                                  <span className="font-bold text-xs text-slate-900">{g.style_code}</span>
                                  <span className="text-[11px] text-slate-600 ml-1.5 font-bold">({g.color})</span>
                                  <div className="text-[10px] text-slate-500 font-mono">Sizes: {sizeDisplay}</div>
                                </div>
                                <div className="font-mono font-bold text-xs text-[#C27842]">{g.totalQty} prs</div>
                              </div>
                              <div className="flex gap-1 flex-wrap pt-1.5 border-t border-slate-100">
                                <button onClick={() => onViewDispatchDetails?.(g)} className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-1.5 py-0.5 flex items-center gap-1" data-testid={`archive-merged-drilldown-dispatch-details-${g.key}`}>
                                  <Truck className="w-2.5 h-2.5" /> Dispatch Details
                                </button>
                                <button onClick={() => onViewDetails?.(g)} className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-1.5 py-0.5 flex items-center gap-1">
                                  <Eye className="w-2.5 h-2.5" /> Details Modal
                                </button>
                                <button onClick={() => onPrint?.(g)} className="text-[9px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-1.5 py-0.5 flex items-center gap-1">
                                  <Printer className="w-2.5 h-2.5" /> Card PDF
                                </button>
                                <button onClick={() => onPacking?.(g)} className="text-[9px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-1.5 py-0.5 flex items-center gap-1">
                                  <Package className="w-2.5 h-2.5" /> Packing List (New)
                                </button>
                                {drec ? (
                                  <>
                                    <button
                                      onClick={() => onDownloadDispatchFile(drec.id, "invoice", `Invoice-${drec.invoice_no}.pdf`, "application/pdf")}
                                      className="text-[9px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Orig. Invoice
                                    </button>
                                    <button
                                      onClick={() => onDownloadDispatchFile(drec.id, "packing-list", `PackingList-${drec.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                                      className="text-[9px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Orig. Packing List
                                    </button>
                                    <button
                                      onClick={() => onDownloadDispatchFile(drec.id, "carton-labels", `CartonLabels-${drec.invoice_no}.pdf`, "application/pdf")}
                                      className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Orig. Labels
                                    </button>
                                    <button
                                      onClick={() => onDownloadDispatchFile(drec.id, "carton-list", `CartonList-${drec.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                                      className="text-[9px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Orig. Carton List
                                    </button>
                                  </>
                                ) : (
                                  <>
                                    {g.rows[0]?.invoice_id && (
                                      <button
                                        onClick={() => downloadInvoiceFile(g.rows[0]?.invoice_id, cluster.invoice_no || g.po_number)}
                                        className="text-[9px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-1.5 py-0.5 flex items-center gap-1"
                                      >
                                        <FileDown className="w-2.5 h-2.5" /> Invoice
                                      </button>
                                    )}
                                    <button
                                      onClick={() => downloadInvoiceCartonLabels(g.rows[0]?.invoice_id, cluster.invoice_no, g.rows.map(r => r.id))}
                                      className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Labels
                                    </button>
                                    <button
                                      onClick={() => downloadCombinedCartonList(g.rows.map(r => r.id), cluster.invoice_no || g.po_number)}
                                      className="text-[9px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Carton List
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </Card>
              );
            }

            // Single group card
            const g = cluster.groups[0];
            const firstJobId = g.rows[0]?.id || g.id;
            const isDetailExpanded = !!expandedDetails[firstJobId];
            const detailDoc = detailCache[firstJobId];
            const isLoadingDetail = detailDoc === "loading";
            const styleImg = styleByCode[g.style_code]?.image_thumbnail_url || styleByCode[g.style_code]?.image_url || styleByCode[g.style_code]?.image_display_url;
            const dispatchedRaw = g.dispatched_at || g.rows[0]?.dispatched_at || g.rows[0]?.archived_at || g.archived_at;
            const dispatchedDate = dispatchedRaw ? new Date(dispatchedRaw).toLocaleDateString("en-IN") : "—";
            const laborCost = g.rows.reduce((sum, r) => sum + (Number(r.total_labor_cost) || 0), 0);
            const karigars = Array.from(new Set(g.rows.flatMap(r => r.karigars_involved || []))).filter(Boolean);
            const sizeDisplay = Array.isArray(g.sizes) ? g.sizes.join(" · ") : Array.from(g.sizes || []).join(" · ");

            let drec = null;
            if (dispatchRecordByJobId) {
              for (const row of g.rows || []) {
                if (dispatchRecordByJobId[row.id]) {
                  drec = dispatchRecordByJobId[row.id];
                  break;
                }
              }
            }

            return (
              <Card key={g.key} className="border-l-4 border-slate-300 hover:border-[#C27842] transition-colors" data-testid={`archive-card-${g.key}`}>
                <div className="p-4 space-y-3">
                  <div className="flex items-start gap-3">
                    {styleImg && (
                      <img
                        src={styleImg}
                        alt=""
                        className="w-14 h-14 object-cover rounded border border-slate-200 flex-shrink-0 cursor-pointer hover:ring-2 hover:ring-[#C27842] transition-all"
                        onClick={() => {
                          const st = styleByCode[g.style_code];
                          const url = st?.image_url || st?.image_display_url || styleImg;
                          if (url) onPreviewImage?.({ src: url, title: `${g.style_code}${g.color ? ` · ${g.color}` : ""}`, subtitle: `PO #${g.po_number || "—"} · ${g.totalQty || 0} pairs` });
                        }}
                        data-testid={`archive-img-${g.key}`}
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline justify-between mb-1">
                        <div>
                          <div className="font-mono text-xs text-slate-500 font-bold">PO {g.po_number || "—"}</div>
                          <div className="font-bold text-base text-slate-900">{g.style_display || g.style_code || "—"}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{g.color || "—"}</div>
                          <div className="font-mono font-bold text-lg text-[#C27842]">{g.totalQty ?? 0} prs</div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-600 mt-1">
                        <div><span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Client:</span> {g.client_name || "—"}</div>
                        <div><span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Dispatched:</span> {dispatchedDate}</div>
                        <div><span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Sizes:</span> <span className="font-mono">{sizeDisplay}</span></div>
                        <div><span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Invoice:</span> <span className="font-mono text-slate-800">{cluster.invoice_no || g.rows[0]?.invoice_no || "—"}</span></div>
                        {laborCost > 0 && <div><span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Labor:</span> ₹{laborCost.toLocaleString("en-IN")}</div>}
                        {karigars.length > 0 && <div className="col-span-2 truncate"><span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Karigars:</span> {karigars.join(", ")}</div>}
                      </div>
                    </div>
                  </div>

                  {/* Action Bar */}
                  <div className="flex gap-1.5 flex-wrap pt-2 border-t border-slate-200 items-center">
                    <button
                      onClick={() => onViewDispatchDetails?.(g)}
                      className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-2 py-1 flex items-center gap-1 transition-colors"
                      data-testid={`archive-dispatch-details-${g.key}`}
                    >
                      <Truck className="w-3 h-3" /> View Dispatch Details
                    </button>

                    <button
                      onClick={() => {
                        if (detailDoc && detailDoc !== "loading") {
                          onViewDetails?.(toGroupLike(detailDoc));
                        } else {
                          toggleDetail(firstJobId);
                        }
                      }}
                      className={`text-[10px] uppercase tracking-wider font-bold px-2 py-1 flex items-center gap-1 transition-colors ${isDetailExpanded || (detailDoc && detailDoc !== "loading") ? "bg-slate-800 text-white" : "bg-[#2563EB] hover:bg-[#1E40AF] text-white"}`}
                      data-testid={`archive-expand-${firstJobId}`}
                    >
                      {isLoadingDetail ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />}
                      {detailDoc && detailDoc !== "loading" ? "View Detail" : isDetailExpanded ? "Loading…" : "Expand Detail"}
                    </button>

                    <button
                      onClick={() => onViewDetails?.(g)}
                      className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-2 py-1 flex items-center gap-1"
                      data-testid={`archive-details-${g.key}`}
                    >
                      <Eye className="w-3 h-3" /> Production History
                    </button>

                    <button
                      onClick={() => onPrint?.(g)}
                      className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1"
                    >
                      <Printer className="w-3 h-3" /> Card PDF
                    </button>

                    <button
                      onClick={() => onPacking?.(g)}
                      className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-2 py-1 flex items-center gap-1"
                    >
                      <Package className="w-3 h-3" /> Packing List (New)
                    </button>

                    {drec ? (
                      <>
                        <button
                          onClick={() => onDownloadDispatchFile(drec.id, "invoice", `Invoice-${drec.invoice_no}.pdf`, "application/pdf")}
                          className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Invoice
                        </button>
                        <button
                          onClick={() => onDownloadDispatchFile(drec.id, "packing-list", `PackingList-${drec.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                          className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Packing List
                        </button>
                        <button
                          onClick={() => onDownloadDispatchFile(drec.id, "carton-labels", `CartonLabels-${drec.invoice_no}.pdf`, "application/pdf")}
                          className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Labels
                        </button>
                        <button
                          onClick={() => onDownloadDispatchFile(drec.id, "carton-list", `CartonList-${drec.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                          className="text-[10px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Carton List
                        </button>
                      </>
                    ) : (
                      <>
                        {(cluster.invoice_id || g.rows[0]?.invoice_id) ? (
                          <button
                            onClick={() => downloadInvoiceFile(cluster.invoice_id || g.rows[0]?.invoice_id, cluster.invoice_no || g.po_number)}
                            className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1"
                          >
                            <FileDown className="w-3 h-3" /> Invoice
                          </button>
                        ) : (
                          <button
                            onClick={() => onDownloadInvoice?.(g)}
                            className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1"
                          >
                            <FileDown className="w-3 h-3" /> Invoice
                          </button>
                        )}
                        <button
                          onClick={() => downloadInvoiceCartonLabels(cluster.invoice_id || g.rows[0]?.invoice_id, cluster.invoice_no, g.rows.map(r => r.id))}
                          className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Labels
                        </button>
                        <button
                          onClick={() => downloadCombinedCartonList(g.rows.map(r => r.id), cluster.invoice_no || g.po_number)}
                          className="text-[10px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Carton List
                        </button>
                      </>
                    )}
                  </div>

                  {/* Stage 5: Expanded detail pane (once loaded) */}
                  {isDetailExpanded && detailDoc && detailDoc !== "loading" && (
                    <div className="mt-4 pt-4 border-t-2 border-dashed border-slate-300 space-y-3" data-testid={`archive-detail-pane-${firstJobId}`}>
                      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Full Production Record</div>
                      {detailDoc.component_summary && Object.keys(detailDoc.component_summary).length > 0 && (
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                          {Object.entries(detailDoc.component_summary).map(([comp, status]) => (
                            <div key={comp} className={`text-[10px] px-2 py-1 rounded font-bold uppercase tracking-wider flex items-center gap-1 ${status === "done" ? "bg-green-50 text-green-700 border border-green-200" : "bg-amber-50 text-amber-700 border border-amber-200"}`}>
                              {status === "done" ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                              {comp}: {status}
                            </div>
                          ))}
                        </div>
                      )}
                      {Array.isArray(detailDoc.history) && detailDoc.history.length > 0 && (
                        <div className="max-h-56 overflow-y-auto space-y-1">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Production History</div>
                          {[...detailDoc.history].reverse().map((h, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs bg-slate-50 px-2 py-1 rounded border border-slate-100">
                              <span className="font-mono text-slate-500 whitespace-nowrap flex-shrink-0">{h.at ? new Date(h.at).toLocaleString("en-IN", { hour12: false }) : "—"}</span>
                              <span className="font-bold text-slate-700 uppercase tracking-wider flex-shrink-0">{h.stage}</span>
                              {h.notes && <span className="text-slate-500 truncate">{h.notes}</span>}
                              {h.worker_name && <span className="text-[#C27842] font-bold ml-auto flex-shrink-0">{h.worker_name}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-1.5 flex-wrap">
                        <button onClick={() => onViewDetails?.(toGroupLike(detailDoc))} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-700 px-2 py-1 flex items-center gap-1">
                          <Eye className="w-3 h-3" /> Full Detail Modal
                        </button>
                        <button onClick={() => setExpandedDetails(prev => ({ ...prev, [firstJobId]: false }))} className="text-[10px] uppercase tracking-wider font-bold text-slate-600 border border-slate-200 hover:bg-slate-100 px-2 py-1 flex items-center gap-1">
                          <ChevronUp className="w-3 h-3" /> Collapse
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2" data-testid="archive-pagination">
          <button disabled={page <= 1} onClick={() => onPageChange?.(page - 1)} className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 border border-slate-300 disabled:opacity-40 hover:bg-slate-100">← Prev</button>
          <span className="text-xs text-slate-600 font-mono">Page {page} / {pages}  ({total} total)</span>
          <button disabled={page >= pages} onClick={() => onPageChange?.(page + 1)} className="text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 border border-slate-300 disabled:opacity-40 hover:bg-slate-100">Next →</button>
        </div>
      )}

      {/* Saved packing lists ledger */}
      <Card className="overflow-hidden" data-testid="saved-packing-lists">
        <div className="px-5 py-3 border-b-2 border-slate-200 flex items-baseline justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
            <Package className="w-4 h-4 text-[#16A34A]" /> Saved Packing Lists
          </h2>
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{savedPackingLists?.length || 0} total</span>
        </div>
        {!savedPackingLists?.length ? (
          <div className="p-10 text-center text-slate-400 text-sm">No packing lists generated yet.</div>
        ) : (
          <ResponsiveTable
            columns={[
              {
                key: "created_at",
                header: "When",
                primary: true,
                className: "font-mono text-[11px] text-slate-700 whitespace-nowrap",
                render: (pl) => pl.created_at
                  ? new Date(pl.created_at).toLocaleString("en-IN", { hour12: false })
                  : "—",
              },
              {
                key: "po_number",
                header: "PO #(s)",
                primary: true,
                className: "font-mono font-bold",
                render: (pl) => pl.merged ? (pl.po_numbers || []).join(" + ") : pl.po_number,
              },
              {
                key: "client_name",
                header: "Client",
                className: "text-xs",
                render: (pl) => pl.client_name || "—",
              },
              {
                key: "type",
                header: "Type",
                render: (pl) => (
                  <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 ${
                    pl.merged ? "bg-[#0F172A] text-white" : "bg-slate-100 text-slate-700"
                  }`}>
                    {pl.merged ? "MERGED" : "SINGLE"}
                  </span>
                ),
              },
              {
                key: "notes",
                header: "Notes",
                className: "text-xs text-slate-600 max-w-md truncate",
                render: (pl) => pl.options?.notes || pl.options?.transporter || "—",
              },
              {
                key: "action",
                header: "",
                action: true,
                render: (pl) => (
                  <button
                    onClick={() => onReDownloadPacking(pl)}
                    className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-3 py-2 flex items-center gap-1 transition-colors"
                    data-testid={`redownload-pl-${pl.id}`}
                    style={{ minHeight: 44 }}
                  >
                    <FileDown className="w-3 h-3" /> Re-download
                  </button>
                ),
              },
            ]}
            rows={savedPackingLists}
            rowKey={(pl) => pl.id}
            testId="saved-packing-lists-table"
          />
        )}
      </Card>
    </div>
  );
}


/* -------------------- DETAIL MODAL -------------------- */
function DetailModal({ group, onClose }) {
  if (!group) return null;
  const allHistory = group.rows.flatMap(r => (r.history || []).map(h => ({ ...h, size: r.size, qty: r.quantity })));
  allHistory.sort((a, b) => new Date(a.at) - new Date(b.at));
  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4 overflow-y-auto" data-testid="detail-modal">
      <div className="bg-white w-full max-w-4xl max-h-[90vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold">Production Card · Archive</div>
            <div className="text-xl font-bold">{group.style_display || group.style_code} · {group.color} · {group.totalQty} pairs</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1" data-testid="detail-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <DLPair label="PO Number" value={group.po_number} />
            <DLPair label="Client" value={group.client_name} />
            <DLPair label="Style" value={group.style_display || group.style_code} />
            <DLPair label="Color" value={group.color} />
            <DLPair label="Created" value={group.card_created_date || "—"} />
            <DLPair label="Delivery" value={group.delivery_date || "—"} />
            <DLPair label="Total Pairs" value={group.totalQty} />
          </div>

          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider mb-2">Size breakdown</h3>
            <table className="w-full text-xs border-2 border-slate-200">
              <thead className="bg-slate-50">
                <tr className="text-left">
                  <th className="px-3 py-2 font-bold">Size</th>
                  <th className="px-3 py-2 font-bold text-right">Quantity</th>
                  <th className="px-3 py-2 font-bold text-right">Completed</th>
                  <th className="px-3 py-2 font-bold text-right">Rejected</th>
                  <th className="px-3 py-2 font-bold">Final Stage</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((r, i) => (
                  <tr key={i} className="border-t border-slate-200">
                    <td className="px-3 py-2 font-mono font-bold">{r.size || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">{r.quantity}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#16A34A]">{r.completed_qty || 0}</td>
                    <td className="px-3 py-2 text-right font-mono text-red-600">{r.rejected_qty || 0}</td>
                    <td className="px-3 py-2 uppercase text-[10px] tracking-wider">{r.stage}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider mb-2">Karigar Assignments</h3>
            <table className="w-full text-xs border-2 border-slate-200">
              <thead className="bg-slate-50">
                <tr className="text-left">
                  <th className="px-3 py-2 font-bold">Role</th>
                  <th className="px-3 py-2 font-bold">Current Karigar</th>
                  <th className="px-3 py-2 font-bold">Assignment History</th>
                  <th className="px-3 py-2 font-bold text-right">Rate / Pair</th>
                </tr>
              </thead>
              <tbody>
                {ASSIGNMENT_ROLES.map(role => {
                  const a = group.assignments?.[role.key];
                  const roleHist = [];
                  const seenKeys = new Set();
                  (group.rows || []).forEach(r => {
                    (r.history || []).forEach(h => {
                      if (!h) return;
                      const isAsgn = (h.event === "assignment_update" || h.event === "bulk_assignment") && h.role === role.key;
                      const isComp = (h.role === role.key || h.stage === role.key) && (h.completed_qty != null || h.completed_by != null);
                      if (isAsgn || isComp) {
                        const k = `${h.at}_${h.worker_id || h.completed_by?.worker_id}_${h.event || h.stage}_${h.completed_qty}`;
                        if (!seenKeys.has(k)) {
                          seenKeys.add(k);
                          roleHist.push(h);
                        }
                      }
                    });
                  });
                  roleHist.sort((x, y) => new Date(y.at || 0) - new Date(x.at || 0));

                  return (
                    <tr key={role.key} className="border-t border-slate-200">
                      <td className="px-3 py-2 font-bold uppercase text-[10px] tracking-wider align-top">{role.label}</td>
                      <td className="px-3 py-2 align-top">
                        <span className="font-semibold">{a?.worker_name || "—"}</span>
                      </td>
                      <td className="px-3 py-2 align-top" data-testid={`history-${role.key}`}>
                        {roleHist.length === 0 ? (
                          <span className="text-slate-400 italic text-[11px]">No assignment history</span>
                        ) : (
                          <div className="space-y-1">
                            {roleHist.map((h, hi) => {
                              const wName = h.completed_by?.worker_name || h.worker_name || (h.worker_id ? `Worker #${h.worker_id}` : "Unassigned");
                              const wRate = h.completed_by?.rate_per_pair ?? h.rate_per_pair;
                              const isComp = h.completed_qty != null || h.completed_by != null;
                              return (
                                <div key={hi} className="text-[11px] flex items-center justify-between gap-2 border-b border-slate-100 last:border-0 pb-0.5">
                                  <div className="flex items-center gap-1">
                                    <span className={`text-[9px] uppercase px-1 py-0.2 rounded font-bold ${isComp ? "bg-emerald-100 text-emerald-800" : "bg-blue-100 text-blue-800"}`}>
                                      {isComp ? "Done" : "Asgn"}
                                    </span>
                                    <span className="text-slate-700">{wName}</span>
                                    {wRate != null && <span className="font-mono text-slate-500">(@ ₹{wRate})</span>}
                                    {isComp && h.completed_qty != null && (
                                      <span className="font-mono text-emerald-700 font-bold">[{h.completed_qty} prs]</span>
                                    )}
                                  </div>
                                  <span className="font-mono text-[9px] text-slate-400 whitespace-nowrap">
                                    {h.at ? new Date(h.at).toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right font-mono align-top">{a?.rate_per_pair != null ? `₹${a.rate_per_pair}` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider mb-2">Stage History ({allHistory.length} entries)</h3>
            <div className="border-2 border-slate-200 max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-left">
                    <th className="px-3 py-2 font-bold">When</th>
                    <th className="px-3 py-2 font-bold">Size</th>
                    <th className="px-3 py-2 font-bold">Stage</th>
                    <th className="px-3 py-2 font-bold">By</th>
                    <th className="px-3 py-2 font-bold">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {allHistory.map((h, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-3 py-1.5 font-mono text-[10px] text-slate-600 whitespace-nowrap">{h.at ? new Date(h.at).toLocaleString("en-IN", { hour12: false }) : "—"}</td>
                      <td className="px-3 py-1.5 font-mono">{h.size}</td>
                      <td className="px-3 py-1.5 font-bold uppercase text-[10px] tracking-wider">{h.stage}</td>
                      <td className="px-3 py-1.5 text-slate-600">{h.by}</td>
                      <td className="px-3 py-1.5">{h.notes || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DLPair({ label, value }) {
  return (
    <div className="border-b border-dashed border-slate-200 pb-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{label}</div>
      <div className="font-mono font-bold">{value || "—"}</div>
    </div>
  );
}


/* -------------------- DISPATCH DETAILS MODAL -------------------- */
function DispatchDetailsModal({ item, dispatchRecordByJobId = {}, invoices = [], styleByCode = {}, onClose, onDownloadDispatchFile, onArchive, onPreviewImage }) {
  const [modalPreview, setModalPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dispatchRecord, setDispatchRecord] = useState(null);
  const [cartons, setCartons] = useState([]);
  const [invoiceData, setInvoiceData] = useState(null);

  const groups = useMemo(() => {
    if (!item) return [];
    const rawGroups = item.groups && Array.isArray(item.groups) ? item.groups : [item];
    return rawGroups.map(g => {
      if (g.rows && g.rows.length) return g;
      return {
        ...g,
        rows: [{
          ...g,
          id: g.id || g._id,
          size: g.size || "—",
          quantity: g.quantity || g.total_pairs || g.totalQty || 0,
          completed_qty: g.completed_qty ?? g.quantity ?? g.total_pairs ?? g.totalQty ?? 0,
          stage: g.stage || "dispatched",
        }],
      };
    });
  }, [item]);

  const allRows = useMemo(() => groups.flatMap(g => g.rows || []), [groups]);
  const jobIds = useMemo(() => allRows.map(r => r.id || r._id).filter(Boolean), [allRows]);

  const isAlreadyArchived = useMemo(() => {
    if (item?.archived) return true;
    if (groups.some(g => g.archived || (g.rows && g.rows.some(r => r.archived)))) return true;
    return false;
  }, [item, groups]);

  const primaryGroup = groups[0] || {};
  const poNumbers = useMemo(() => {
    const list = groups.map(g => g.po_number).filter(Boolean);
    return Array.from(new Set(list));
  }, [groups]);

  const clientName = primaryGroup.client_name || dispatchRecord?.client_name || "—";

  useEffect(() => {
    let isMounted = true;
    const fetchDetails = async () => {
      setLoading(true);
      try {
        // 1. Locate dispatch record
        let drec = null;
        for (const jid of jobIds) {
          if (dispatchRecordByJobId[jid]) {
            drec = dispatchRecordByJobId[jid];
            break;
          }
        }
        if (!drec && jobIds.length > 0) {
          try {
            const drRes = await http.get(`/dispatch-records?job_id=${jobIds[0]}`);
            if (drRes.data && drRes.data.length > 0) {
              drec = drRes.data[0];
            }
          } catch (e) {
            console.log("Could not load dispatch-record by job_id", e);
          }
        }

        let fullDrec = drec;
        if (drec?.id) {
          try {
            const singleRes = await http.get(`/dispatch-records/${drec.id}`);
            if (singleRes.data) fullDrec = singleRes.data;
          } catch {}
        }

        // 2. Fetch cartons from /packing/cartons or fallback to snapshot
        let fetchedCartons = [];
        if (jobIds.length > 0) {
          try {
            const cRes = await http.get(`/packing/cartons?job_ids=${jobIds.join(",")}`);
            if (cRes.data && cRes.data.length > 0) {
              fetchedCartons = cRes.data;
            }
          } catch {}
        }
        if (fetchedCartons.length === 0 && fullDrec?.packing_cartons_snapshot) {
          fetchedCartons = fullDrec.packing_cartons_snapshot;
        }

        // 3. Match invoice data
        let inv = null;
        const invId = fullDrec?.invoice_id || item?.invoice_id;
        const invNo = fullDrec?.invoice_no || item?.invoice_no;
        if (invId) {
          inv = invoices.find(i => String(i.id || i._id) === String(invId));
          if (!inv) {
            try {
              const iRes = await http.get(`/invoices/${invId}`);
              if (iRes.data) inv = iRes.data;
            } catch {}
          }
        } else if (invNo) {
          inv = invoices.find(i => i.invoice_no === invNo);
        }

        if (isMounted) {
          setDispatchRecord(fullDrec);
          setCartons(fetchedCartons);
          setInvoiceData(inv);
        }
      } catch (err) {
        console.error("Error loading dispatch details:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchDetails();
    return () => { isMounted = false; };
  }, [item, jobIds, dispatchRecordByJobId, invoices]);

  // Size-wise quantity breakdown
  const sizeBreakdown = useMemo(() => {
    const list = [];
    for (const g of groups) {
      for (const r of g.rows || []) {
        const qty = r.completed_qty || r.quantity || 0;
        list.push({
          style_code: g.style_code,
          style_name: styleByCode[g.style_code]?.name || g.style_code,
          color: g.color,
          size: r.size || "—",
          qty: qty,
        });
      }
    }
    return list;
  }, [groups, styleByCode]);

  const totalDispatchedPairs = useMemo(() => {
    if (dispatchRecord?.total_qty) return dispatchRecord.total_qty;
    return sizeBreakdown.reduce((sum, item) => sum + (Number(item.qty) || 0), 0);
  }, [dispatchRecord, sizeBreakdown]);

  const totalCartonCount = useMemo(() => {
    if (dispatchRecord?.total_cartons) return dispatchRecord.total_cartons;
    if (cartons?.length > 0) return cartons.length;
    return 0;
  }, [dispatchRecord, cartons]);

  const resolvedInvoiceNo = dispatchRecord?.invoice_no || invoiceData?.invoice_no || item?.invoice_no || "—";
  const dispatchDate = dispatchRecord?.dispatched_at
    ? new Date(dispatchRecord.dispatched_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
    : (invoiceData?.supply_date || invoiceData?.invoice_date || "—");

  const transportMode = invoiceData?.transport_mode || dispatchRecord?.transport_mode || "—";
  const vehicleNo = invoiceData?.vehicle_no || dispatchRecord?.vehicle_no || "—";
  const transporterName = invoiceData?.transporter || dispatchRecord?.transporter || invoiceData?.transporter_name || "—";
  const driverName = invoiceData?.driver_name || dispatchRecord?.driver_name || "—";
  const driverPhone = invoiceData?.driver_phone || dispatchRecord?.driver_phone || "—";

  const downloadDoc = async (type, filename, mimeType) => {
    if (dispatchRecord?.id) {
      onDownloadDispatchFile(dispatchRecord.id, type, filename, mimeType);
    } else if (invoiceData?.id && type === "invoice") {
      try {
        const res = await http.get(`/invoices/${invoiceData.id}/file`, { responseType: "blob" });
        triggerDownload(res.data, filename, "application/pdf");
      } catch (e) {
        alert("Download failed: " + (e.response?.data?.detail || e.message));
      }
    } else if (invoiceData?.id && type === "ewaybill") {
      try {
        const res = await http.get(`/invoices/${invoiceData.id}/ewaybill`, { responseType: "blob" });
        triggerDownload(res.data, filename, "application/json");
      } catch (e) {
        alert("Download failed: " + (e.response?.data?.detail || e.message));
      }
    } else if (jobIds.length > 0) {
      if (type === "carton-labels") {
        try {
          const res = await http.get(`/production/jobs/carton-labels?job_ids=${jobIds.join(",")}`, { responseType: "blob" });
          triggerDownload(res.data, filename, "application/pdf");
        } catch (e) {
          alert("Download failed: " + (e.response?.data?.detail || e.message));
        }
      } else if (type === "carton-list") {
        try {
          const res = await http.get(`/production/jobs/carton-list?job_ids=${jobIds.join(",")}`, { responseType: "blob" });
          triggerDownload(res.data, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        } catch (e) {
          alert("Download failed: " + (e.response?.data?.detail || e.message));
        }
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 grid place-items-center p-2 sm:p-4 overflow-y-auto" data-testid="dispatch-details-modal">
      <div className="bg-white w-full max-w-4xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl flex flex-col my-auto">
        {/* Header */}
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-baseline justify-between shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold flex items-center gap-1.5">
              <Truck className="w-3.5 h-3.5" /> Dispatch Record Details
            </div>
            <div className="text-xl font-black mt-0.5">
              {groups
                .map(g => {
                  const style = g.style_code || g.po_style_code || (g.rows && g.rows[0]?.style_code) || "Style";
                  const color = g.color || (g.rows && g.rows[0]?.color) || "—";
                  return `${style} (${color})`;
                })
                .join(" + ") || "Dispatch Details"}
            </div>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1 text-slate-300 hover:text-white" data-testid="dispatch-details-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6 flex-1 overflow-y-auto">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-[#C27842]" />
              <div className="text-xs uppercase tracking-wider font-bold">Loading dispatch details…</div>
            </div>
          ) : (
            <>
              {/* Summary Metadata Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-4 border border-slate-200">
                <DLPair label="PO Number(s)" value={poNumbers.join(", ") || "—"} />
                <DLPair label="Client" value={clientName} />
                <DLPair label="Invoice #" value={resolvedInvoiceNo} />
                <DLPair label="Dispatch Date" value={dispatchDate} />
                <DLPair label="Transporter" value={transporterName} />
                <DLPair label="Vehicle No." value={vehicleNo} />
                <DLPair label="Transport Mode" value={transportMode} />
                <DLPair label="Driver Info" value={driverName !== "—" ? `${driverName} (${driverPhone})` : "—"} />
                <DLPair label="Total Dispatched" value={`${totalDispatchedPairs} pairs`} />
                <DLPair label="Total Cartons" value={totalCartonCount ? `${totalCartonCount} cartons` : "—"} />
                <DLPair label="Dispatched By" value={dispatchRecord?.dispatched_by || "system"} />
                <DLPair label="Notes" value={invoiceData?.notes || dispatchRecord?.notes || "—"} />
              </div>

              {/* Consolidated Generated Documents */}
              <div className="border border-slate-200 p-4 bg-white space-y-2.5">
                <div className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                  <FileDown className="w-4 h-4 text-[#C27842]" /> Generated Dispatch Documents
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    onClick={() => downloadDoc("invoice", `Invoice-${resolvedInvoiceNo}.pdf`, "application/pdf")}
                    className="text-xs uppercase tracking-wider font-bold text-slate-800 bg-slate-100 hover:bg-[#0F172A] hover:text-white border border-slate-300 px-3 py-2 flex items-center gap-1.5 transition-colors"
                    data-testid="dispatch-modal-download-invoice"
                  >
                    <FileDown className="w-4 h-4 text-[#C27842]" /> Tax Invoice PDF ({resolvedInvoiceNo})
                  </button>

                  <button
                    onClick={() => downloadDoc("packing-list", `PackingList-${resolvedInvoiceNo}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                    className="text-xs uppercase tracking-wider font-bold text-emerald-800 bg-emerald-50 hover:bg-emerald-700 hover:text-white border border-emerald-300 px-3 py-2 flex items-center gap-1.5 transition-colors"
                    data-testid="dispatch-modal-download-packing"
                  >
                    <FileSpreadsheet className="w-4 h-4 text-emerald-600" /> Packing List (XLSX)
                  </button>

                  <button
                    onClick={() => downloadDoc("carton-labels", `CartonLabels-${resolvedInvoiceNo}.pdf`, "application/pdf")}
                    className="text-xs uppercase tracking-wider font-bold text-teal-800 bg-teal-50 hover:bg-teal-700 hover:text-white border border-teal-300 px-3 py-2 flex items-center gap-1.5 transition-colors"
                    data-testid="dispatch-modal-download-labels"
                  >
                    <Package className="w-4 h-4 text-teal-600" /> Carton Labels (PDF)
                  </button>

                  <button
                    onClick={() => downloadDoc("carton-list", `CartonList-${resolvedInvoiceNo}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                    className="text-xs uppercase tracking-wider font-bold text-amber-800 bg-amber-50 hover:bg-amber-700 hover:text-white border border-amber-300 px-3 py-2 flex items-center gap-1.5 transition-colors"
                    data-testid="dispatch-modal-download-cartonlist"
                  >
                    <FileSpreadsheet className="w-4 h-4 text-amber-600" /> Carton List (XLSX)
                  </button>
                  <button
                    onClick={() => downloadDoc("ewaybill", `EWayBill-${resolvedInvoiceNo}.json`, "application/json")}
                    className="text-xs uppercase tracking-wider font-bold text-sky-800 bg-sky-50 hover:bg-sky-700 hover:text-white border border-sky-300 px-3 py-2 flex items-center gap-1.5 transition-colors"
                    data-testid="dispatch-modal-download-ewaybill"
                  >
                    <FileText className="w-4 h-4 text-sky-600" /> E-Way Bill (JSON)
                  </button>
                </div>
              </div>

              {/* Size-wise Quantity Breakdown */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Size-wise Quantity Breakdown
                  </h3>
                  <span className="text-[11px] font-mono text-slate-500 font-bold">
                    Total: <strong className="text-[#C27842]">{totalDispatchedPairs} pairs</strong>
                  </span>
                </div>
                <div className="border border-slate-200 overflow-x-auto">
                  <table className="w-full text-xs" data-testid="dispatch-size-breakdown-table">
                    <thead className="bg-slate-100 border-b border-slate-200">
                      <tr className="text-left font-bold text-slate-700 uppercase text-[10px]">
                        <th className="px-3 py-2 w-12 text-center">Image</th>
                        <th className="px-3 py-2">Style Code</th>
                        <th className="px-3 py-2">Color</th>
                        <th className="px-3 py-2 text-center">Size</th>
                        <th className="px-3 py-2 text-right">Dispatched Qty</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {sizeBreakdown.length === 0 ? (
                        <tr>
                          <td colSpan="5" className="px-3 py-4 text-center text-slate-400">No size breakdown available.</td>
                        </tr>
                      ) : (
                        sizeBreakdown.map((row, idx) => {
                          const st = styleByCode[row.style_code];
                          const thumb = st?.image_thumbnail_url || st?.image_display_url || st?.image_url;
                          const fullImg = st?.image_url || st?.image_display_url || st?.image_thumbnail_url;
                          return (
                            <tr key={idx} className="hover:bg-slate-50 transition-colors">
                              <td className="px-3 py-1.5 text-center">
                                {thumb ? (
                                  <div
                                    className="relative group w-9 h-9 mx-auto rounded border border-slate-200 bg-slate-50 overflow-hidden cursor-pointer shadow-2xs hover:border-[#C27842] hover:ring-2 hover:ring-[#C27842]/30 transition-all flex items-center justify-center"
                                    onClick={() => {
                                      const data = {
                                        src: fullImg || thumb,
                                        title: `${row.style_name || row.style_code} (${row.color})`,
                                        subtitle: `Size: ${row.size} · Dispatched: ${row.qty} prs`,
                                        alt: row.style_code,
                                      };
                                      if (onPreviewImage) onPreviewImage(data);
                                      else setModalPreview(data);
                                    }}
                                    title="Click to view full image in modal"
                                    data-testid={`dispatch-row-img-${idx}`}
                                  >
                                    <img
                                      src={thumb}
                                      alt={row.style_code}
                                      className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-200"
                                    />
                                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white pointer-events-none">
                                      <Maximize2 className="w-3.5 h-3.5" />
                                    </div>
                                  </div>
                                ) : (
                                  <div className="w-9 h-9 mx-auto rounded border border-slate-100 bg-slate-50 flex items-center justify-center text-slate-300">
                                    <Package className="w-4 h-4 text-slate-300" />
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-2 font-mono font-bold">{row.style_code}</td>
                              <td className="px-3 py-2 font-medium">{row.color}</td>
                              <td className="px-3 py-2 text-center font-mono font-bold text-slate-800">{row.size}</td>
                              <td className="px-3 py-2 text-right font-mono font-bold text-[#C27842]">{row.qty} prs</td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                    {sizeBreakdown.length > 0 && (
                      <tfoot className="bg-slate-50 border-t-2 border-slate-200 font-bold">
                        <tr>
                          <td colSpan="4" className="px-3 py-2 text-right uppercase text-[10px] text-slate-600">Total Dispatched Pairs:</td>
                          <td className="px-3 py-2 text-right font-mono text-sm text-[#C27842]">{totalDispatchedPairs} prs</td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>

              {/* Carton Assignments */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Carton Assignments (Packed Cartons)
                  </h3>
                  <span className="text-[11px] font-mono text-slate-500 font-bold">
                    {cartons.length} Carton{cartons.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <div className="border border-slate-200 overflow-x-auto max-h-72 overflow-y-auto">
                  <table className="w-full text-xs" data-testid="dispatch-cartons-table">
                    <thead className="bg-slate-100 border-b border-slate-200 sticky top-0 z-10">
                      <tr className="text-left font-bold text-slate-700 uppercase text-[10px]">
                        <th className="px-3 py-2">Box #</th>
                        <th className="px-3 py-2">Style</th>
                        <th className="px-3 py-2">Color</th>
                        <th className="px-3 py-2 text-center">Size</th>
                        <th className="px-3 py-2 text-right">Quantity</th>
                        <th className="px-3 py-2 font-mono">Barcode / EAN</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {cartons.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="px-4 py-6 text-center text-slate-400 italic">
                            No carton assignment records found for this dispatch.
                          </td>
                        </tr>
                      ) : (
                        cartons.map((c, idx) => (
                          <tr key={idx} className="hover:bg-slate-50">
                            <td className="px-3 py-2 font-mono font-bold text-slate-900">
                              Carton #{c.box_number != null ? c.box_number : (idx + 1)}
                            </td>
                            <td className="px-3 py-2 font-mono">{c.style_code || primaryGroup.style_code || "—"}</td>
                            <td className="px-3 py-2">{c.color || primaryGroup.color || "—"}</td>
                            <td className="px-3 py-2 text-center font-mono font-bold">{c.size || "—"}</td>
                            <td className="px-3 py-2 text-right font-mono font-bold text-slate-800">{c.qty != null ? `${c.qty} prs` : "—"}</td>
                            <td className="px-3 py-2 font-mono text-[11px] text-slate-500">{c.ean_code || "—"}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-50 border-t border-slate-200 px-6 py-3.5 flex items-center justify-between shrink-0 gap-3">
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
          {onArchive && !isAlreadyArchived && (
            <button
              type="button"
              onClick={async () => {
                await onArchive(jobIds, `${groups.length} production card(s)`);
                onClose();
              }}
              className="px-4 py-2 bg-[#0F172A] hover:bg-slate-800 text-white font-bold text-xs uppercase tracking-wider flex items-center gap-1.5 shadow-md transition-colors"
              data-testid="dispatch-details-archive-btn"
            >
              <Archive className="w-3.5 h-3.5 text-amber-400" />
              Verify &amp; Move to Archive
            </button>
          )}
        </div>
      </div>
      {modalPreview && (
        <ImageViewModal
          isOpen={!!modalPreview}
          src={modalPreview.src}
          title={modalPreview.title}
          subtitle={modalPreview.subtitle}
          alt={modalPreview.alt}
          onClose={() => setModalPreview(null)}
        />
      )}
    </div>
  );
}


/* -------------------- PACKING LIST DIALOG -------------------- */
function PackingListDialog({ payload, onClose, onSubmit }) {
  const isMerged = payload.kind === "merged";
  const summary = isMerged
    ? `${payload.jobs.length} job(s) across ${new Set(payload.jobs.map(j => j.po_id)).size} PO(s)`
    : `${payload.group?.style_code} · ${payload.group?.color} · ${payload.group?.totalQty} pairs`;

  const [form, setForm] = useState({
    carton_dim: "60x50x30 CMS",
    pcs_per_box: 20,
    net_wt_per_carton: 10.8,
    gross_wt_per_carton: 12.0,
    dispatch_date: new Date().toISOString().slice(0, 10),
    transporter: "",
    vehicle_no: "",
    driver_name: "",
    driver_phone: "",
    site_code: "",
    destination: "",
    port: "",
    notes: "",
    sectioned: false,
  });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const [submitting, setSubmitting] = useState(false);

  const [hasCartons, setHasCartons] = useState(false);

  useEffect(() => {
    const jobIds = isMerged
      ? payload.jobs?.map(j => j.id).join(",")
      : payload.group?.rows?.map(r => r.id).join(",");
    if (!jobIds) return;
    http.get(`/packing/cartons?job_ids=${jobIds}`).then(res => {
      const cartons = res.data || [];
      if (cartons.length > 0) {
        setHasCartons(true);
        const firstQty = cartons[0].qty;
        if (firstQty) {
          setForm(f => ({ ...f, pcs_per_box: firstQty }));
        }
      }
    }).catch(err => console.log("Failed to load cartons:", err));
  }, [payload, isMerged]);

  const submit = async () => {
    setSubmitting(true);
    try {
      const payload2 = { ...form };
      if (!isMerged) delete payload2.sectioned;
      await onSubmit(payload2);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-0 sm:p-4 overflow-y-auto" data-testid="packing-dialog">
      <div className="bg-white w-full sm:max-w-3xl max-h-[100dvh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#16A34A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">
              {isMerged ? "Merged Packing List" : "Packing List"}
            </div>
            <div className="text-lg font-bold">{summary}</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/20" data-testid="packing-close"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-6 space-y-5">
          <div className="bg-amber-50 border border-amber-200 px-4 py-2 text-xs text-slate-700">
            <b className="text-[#C27842]">Tip:</b> The system auto-fills line items from the production data (PO / Style / Colour / Sizes / Qty). Use this form to add <b>shipping & carton info</b> that isn't on the production card. The packing list is saved in the Archive and can be re-downloaded any time.
          </div>

          {/* Carton */}
          <Section title="Carton specification">
            {!hasCartons && (
              <Field label="Pcs / Carton">
                <input type="number" min="1" value={form.pcs_per_box} onChange={e => set("pcs_per_box", Number(e.target.value))}
                  data-testid="pl-pcs-per-box" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
              </Field>
            )}
            <Field label="Carton dimension">
              <input value={form.carton_dim} onChange={e => set("carton_dim", e.target.value)}
                data-testid="pl-carton-dim" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Net wt / Carton (kg)">
              <input type="number" step="0.1" value={form.net_wt_per_carton} onChange={e => set("net_wt_per_carton", Number(e.target.value))}
                data-testid="pl-net-wt" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Gross wt / Carton (kg)">
              <input type="number" step="0.1" value={form.gross_wt_per_carton} onChange={e => set("gross_wt_per_carton", Number(e.target.value))}
                data-testid="pl-gross-wt" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
          </Section>

          <Section title="Dispatch & Vehicle">
            <Field label="Dispatch date">
              <input type="date" value={form.dispatch_date} onChange={e => set("dispatch_date", e.target.value)}
                data-testid="pl-dispatch-date" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Transporter">
              <input value={form.transporter} onChange={e => set("transporter", e.target.value)}
                data-testid="pl-transporter" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Vehicle no">
              <input value={form.vehicle_no} onChange={e => set("vehicle_no", e.target.value)}
                data-testid="pl-vehicle" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Driver name">
              <input value={form.driver_name} onChange={e => set("driver_name", e.target.value)}
                data-testid="pl-driver-name" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Driver phone">
              <input value={form.driver_phone} onChange={e => set("driver_phone", e.target.value)}
                data-testid="pl-driver-phone" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
          </Section>

          <Section title="Destination & Site">
            <Field label="Site code (eg. SAUY)">
              <input value={form.site_code} onChange={e => set("site_code", e.target.value)}
                data-testid="pl-site-code" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Destination / Hub">
              <input value={form.destination} onChange={e => set("destination", e.target.value)}
                data-testid="pl-destination" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Port (for export)">
              <input value={form.port} onChange={e => set("port", e.target.value)}
                data-testid="pl-port" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
          </Section>

          <div>
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">Notes / Special instructions</div>
            <textarea rows={3} value={form.notes} onChange={e => set("notes", e.target.value)}
              data-testid="pl-notes" placeholder="Fragile, stack max 3 high, handle with care…"
              className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
          </div>

          {isMerged && (
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="pl-sectioned-label">
              <input type="checkbox" checked={form.sectioned} onChange={e => set("sectioned", e.target.checked)} data-testid="pl-sectioned" className="w-4 h-4" />
              <span><b>Sectioned layout</b> — group lines per PO with header rows (otherwise all lines combined into one block).</span>
            </label>
          )}

          <div className="flex gap-2 pt-4 border-t border-slate-200">
            <BtnPrimary onClick={submit} disabled={submitting} data-testid="pl-submit"
              className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]">
              <Printer className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
              {submitting ? "Generating…" : "Generate, Save & Download"}
            </BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.2em] text-[#C27842] font-bold mb-2 border-b border-slate-200 pb-1">{title}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">{children}</div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">{label}</div>
      {children}
    </div>
  );
}

/* ------------------- SHORTAGE CHECK MODAL & PO AUTO-RAISE ------------------- */
function ShortageModal({ state, onClose, navigate }) {
  const { loading, shortage } = state;

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4 overflow-y-auto">
        <Card className="p-8 max-w-sm w-full text-center space-y-4">
          <div className="w-10 h-10 border-4 border-[#C27842] border-t-transparent rounded-full animate-spin mx-auto" />
          <div className="text-sm font-bold text-slate-800">Calculating inventory requirements & shortage...</div>
        </Card>
      </div>
    );
  }

  // Filter materials below reorder level (current stock < reorder level)
  const qualifying = shortage.filter(item => item.in_stock < item.reorder_level);

  // Group by preferred vendor
  const grouped = {};
  qualifying.forEach(item => {
    const vId = item.preferred_vendor_id || "unassigned";
    const vName = item.preferred_vendor_name || "No Preferred Vendor";
    if (!grouped[vId]) {
      grouped[vId] = { vendor_id: vId, vendor_name: vName, items: [] };
    }
    grouped[vId].items.push(item);
  });

  const hasShortages = qualifying.length > 0;

  const raisePoForVendor = (group) => {
    navigate("/vendor-pos", {
      state: {
        prefill: {
          vendor_id: group.vendor_id === "unassigned" ? "" : group.vendor_id,
          items: group.items
        }
      }
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4 overflow-y-auto" data-testid="shortage-modal">
      <div className="bg-white w-full max-w-4xl max-h-[85vh] overflow-y-auto border-2 border-slate-200 shadow-2xl flex flex-col">
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#C27842]">Inventory Analytics</div>
            <h3 className="text-lg font-bold">Shortage & Reorder Alert Analysis</h3>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-6 space-y-6 flex-1 overflow-y-auto">
          {!hasShortages ? (
            <div className="text-center py-12 text-slate-500">
              <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
              <p className="font-bold">No materials are below their minimum reorder level!</p>
              <p className="text-xs text-slate-400 mt-1">All required materials for selected jobs are currently in sufficient supply.</p>
            </div>
          ) : (
            <div className="space-y-6">
              <p className="text-xs text-slate-600">
                The following materials are required for the selected production jobs and their current stock level is at or below the reorder threshold. Grouped by preferred vendor.
              </p>

              {Object.values(grouped).map(group => (
                <div key={group.vendor_id} className="border-2 border-slate-200" data-testid={`shortage-group-${group.vendor_id}`}>
                  <div className="bg-slate-100 px-4 py-3 flex items-center justify-between border-b border-slate-200 flex-wrap gap-2">
                    <div>
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Preferred Vendor:</span>
                      <span className="ml-2 font-bold text-slate-900">{group.vendor_name}</span>
                    </div>
                    {group.vendor_id !== "unassigned" && (
                      <button
                        onClick={() => raisePoForVendor(group)}
                        className="bg-[#0F172A] text-white font-bold uppercase tracking-wider text-[10px] px-3 py-1.5 hover:bg-slate-800 transition-colors flex items-center gap-1"
                        data-testid={`raise-po-${group.vendor_id}`}
                      >
                        <Plus className="w-3 h-3" /> Raise Vendor PO
                      </button>
                    )}
                  </div>
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr className="text-left text-[9px] uppercase tracking-wider text-slate-600 font-bold">
                        <th className="px-4 py-2 sticky left-0 z-10 bg-slate-50">Code</th>
                        <th className="px-4 py-2">Material Name</th>
                        <th className="px-4 py-2 text-right">Job Requirement</th>
                        <th className="px-4 py-2 text-right">Current Stock</th>
                        <th className="px-4 py-2 text-right">Reorder Level</th>
                        <th className="px-4 py-2 text-right text-red-600">Shortage Qty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.items.map(item => (
                        <tr key={item.code} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-4 py-2.5 font-mono font-bold sticky left-0 z-10 bg-white group-hover:bg-slate-50">{item.code}</td>
                          <td className="px-4 py-2.5">{item.name}</td>
                          <td className="px-4 py-2.5 text-right font-mono">{item.required} {item.unit}</td>
                          <td className="px-4 py-2.5 text-right font-mono">{item.in_stock} {item.unit}</td>
                          <td className="px-4 py-2.5 text-right font-mono font-bold text-[#C27842]">{item.reorder_level} {item.unit}</td>
                          <td className="px-4 py-2.5 text-right font-mono font-bold text-red-600">{item.shortage} {item.unit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 border-t-2 border-slate-200 px-6 py-4 flex justify-end bg-slate-50">
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
        </div>
      </div>
    </div>
  );
}


/* -------------------- CARTON PACKING DIALOG -------------------- */
function PackCartonDialog({ group, style, onClose, load }) {
  const [cartons, setCartons] = useState([]);
  const [eanCodes, setEanCodes] = useState({});
  const [eanInputs, setEanInputs] = useState({});
  const [eanSourceMeta, setEanSourceMeta] = useState({}); // size -> { source: "client" | "global" | "manual", originalVal: string }
  const [cartonRows, setCartonRows] = useState({}); // size -> array of carton quantities
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const jobIds = useMemo(() => group.rows.map(r => r.id).join(","), [group]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const poId = group.po_id || group.rows?.[0]?.po_id;
      const styleCode = group.style_code || group.rows?.[0]?.style_code;
      const color = group.color || group.rows?.[0]?.color || "";

      const promises = [
        http.get(`/packing/cartons?job_ids=${jobIds}`),
        http.get(`/packing/ean-codes?style_id=${group.style_id}&color=${encodeURIComponent(group.color)}`),
      ];
      if (poId) {
        promises.push(http.get(`/pos/${poId}/ean-codes`).catch(() => ({ data: { items: [] } })));
      }

      const [cartonsRes, eanRes, poEanRes] = await Promise.all(promises);
      const existingCartons = cartonsRes.data || [];
      setCartons(existingCartons);

      // 1. Look up po_ean_codes for this job group's po_id + style_code + color
      const poEans = {};
      if (poEanRes?.data?.items) {
        for (const item of poEanRes.data.items) {
          const matchStyle = (item.style_code || "").trim().toLowerCase() === (styleCode || "").trim().toLowerCase();
          const matchColor = !item.color || !color || (item.color || "").trim().toLowerCase() === (color || "").trim().toLowerCase();
          if (matchStyle && matchColor && item.size && item.ean_code) {
            poEans[String(item.size)] = item.ean_code.trim();
          }
        }
      }

      // 2. Global sku_ean_codes fallback
      const globalEans = {};
      for (const item of eanRes.data || []) {
        if (item.size && item.ean_code) {
          globalEans[String(item.size)] = item.ean_code.trim();
        }
      }

      const sources = {};
      const initialInputs = {};

      for (const sz of group.sizes) {
        if (poEans[sz]) {
          initialInputs[sz] = poEans[sz];
          sources[sz] = { source: "client", originalVal: poEans[sz] };
        } else if (globalEans[sz]) {
          initialInputs[sz] = globalEans[sz];
          sources[sz] = { source: "global", originalVal: globalEans[sz] };
        } else {
          initialInputs[sz] = "";
          sources[sz] = { source: "manual", originalVal: "" };
        }
      }

      setEanSourceMeta(sources);
      setEanInputs(initialInputs);

      // Initialize carton rows
      const rowsMap = {};
      for (const sz of group.sizes) {
        const szCartons = existingCartons.filter(c => c.size === sz);
        if (szCartons.length > 0) {
          rowsMap[sz] = szCartons.map(c => c.qty);
        } else {
          const row = group.rows.find(r => String(r.size || "—") === sz);
          const completed = row?.completed_qty || 0;
          if (completed <= 0) {
            rowsMap[sz] = [];
          } else {
            let defaultQty = null;
            if (style?.default_pairs_per_carton) {
              if (style.default_pairs_per_carton[sz]) {
                defaultQty = style.default_pairs_per_carton[sz];
              } else if (style.default_pairs_per_carton.default) {
                defaultQty = style.default_pairs_per_carton.default;
              }
            }
            if (defaultQty) {
              // Populate the expected number of rows but leave them empty for the user to explicitly input
              const rows = [];
              let rem = completed;
              while (rem > 0) {
                rows.push("");
                rem -= defaultQty;
              }
              rowsMap[sz] = rows.length > 0 ? rows : [""];
            } else {
              rowsMap[sz] = [""];
            }
          }
        }
      }
      setCartonRows(rowsMap);

    } catch (e) {
      setError("Failed to load packing data: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, [group, jobIds, style]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const addCartonRow = (sz) => {
    setCartonRows(prev => ({
      ...prev,
      [sz]: [...(prev[sz] || []), ""]
    }));
  };

  const updateCartonRow = (sz, index, val) => {
    setCartonRows(prev => {
      const arr = [...(prev[sz] || [])];
      arr[index] = val === "" ? "" : parseInt(val, 10) || 0;
      return { ...prev, [sz]: arr };
    });
  };

  const removeCartonRow = (sz, index) => {
    setCartonRows(prev => {
      const arr = (prev[sz] || []).filter((_, idx) => idx !== index);
      return { ...prev, [sz]: arr };
    });
  };

  const handleConfirm = async () => {
    setError("");
    const missingEanSizes = [];
    const eanList = [];
    const cartonList = [];

    for (const sz of group.sizes) {
      const row = group.rows.find(r => String(r.size || "—") === sz);
      const completed = row?.completed_qty || 0;
      
      if (completed > 0) {
        const ean = (eanInputs[sz] || "").trim();
        if (!ean) {
          missingEanSizes.push(sz);
        } else {
          eanList.push({ size: sz, ean_code: ean });
        }
        
        const rows = cartonRows[sz] || [];
        const sum = rows.reduce((s, r) => s + (parseInt(r, 10) || 0), 0);
        if (sum !== completed) {
          setError(`Size ${sz} sum of cartons (${sum}) must match completed qty (${completed}) exactly.`);
          return;
        }
        
        if (rows.some(r => r === "" || parseInt(r, 10) <= 0)) {
          setError(`Size ${sz} has invalid carton quantities. Each carton must have a qty > 0.`);
          return;
        }

        for (const qty of rows) {
          cartonList.push({ size: sz, qty: parseInt(qty, 10) });
        }
      }
    }

    if (missingEanSizes.length > 0) {
      setError(`Please enter EAN codes for size(s): ${missingEanSizes.join(", ")}`);
      return;
    }

    try {
      await http.post("/packing/confirm-qc-pack", {
        job_ids: group.rows.map(r => r.id),
        eans: eanList,
        cartons: cartonList
      });
      onClose();
      load();
    } catch (e) {
      setError("Failed to confirm: " + formatError(e.response?.data?.detail || e.message));
    }
  };

  const isAlreadyInQcPack = group.stage === "qc_pack";

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4 overflow-y-auto" data-testid="carton-pack-dialog">
      <div className="bg-white w-full max-w-5xl max-h-[92vh] border-2 border-slate-900 shadow-2xl flex flex-col rounded-none overflow-hidden">
        
        {/* Header */}
        <div className="bg-[#0D9488] text-white px-6 py-4 flex items-center justify-between shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">
              {isAlreadyInQcPack ? "Carton Packing Configuration (QC & Pack Stage)" : "QC & Pack — Setup & Confirm"}
            </div>
            <div className="text-lg font-bold">{group.style_code} · {group.color} · PO {group.po_number}</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/20 transition-colors" data-testid="pack-dialog-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {error && <div className="text-red-600 text-sm p-3 border border-red-300 bg-red-50 font-bold">{error}</div>}

          {loading ? (
            <div className="p-12 text-center text-slate-400">Loading packing details...</div>
          ) : (
            <div className="space-y-6">
              
              {/* Main Matrix Form */}
              <Card className="p-4 border-2 border-slate-200 overflow-hidden">
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700 mb-3">Sizes, Completed Quantities & Cartons split</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr className="text-left text-[9px] uppercase tracking-wider text-slate-600 font-bold">
                        <th className="px-3 py-2 w-16 sticky left-0 z-10 bg-slate-50">Size</th>
                        <th className="px-3 py-2 text-right w-24">Completed Qty</th>
                        <th className="px-3 py-2 w-56">EAN Code</th>
                        <th className="px-3 py-2">Cartons Configuration (Row values)</th>
                        <th className="px-3 py-2 text-right w-36">Cartons Sum</th>
                        <th className="px-3 py-2 text-center w-24">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.sizes.map(sz => {
                        const row = group.rows.find(r => String(r.size || "—") === sz);
                        const completed = row?.completed_qty || 0;
                        const eanInput = eanInputs[sz] || "";
                        const rows = cartonRows[sz] || [];
                        const sum = rows.reduce((s, r) => s + (parseInt(r, 10) || 0), 0);
                        const isMatch = sum === completed;
                        const isEanMissing = completed > 0 && !eanInput.trim();

                        return (
                          <tr key={sz} className="border-b border-slate-100 hover:bg-slate-50">
                            {/* Size */}
                            <td className="px-3 py-3 font-mono font-bold text-slate-800 sticky left-0 z-10 bg-white">Sz {sz}</td>
                            
                            {/* Completed Qty */}
                            <td className="px-3 py-3 text-right font-mono font-bold text-slate-900">{completed}</td>
                            
                            {/* EAN Code */}
                            <td className="px-3 py-3">
                              {completed > 0 ? (
                                <div className="space-y-1.5">
                                  <input
                                    value={eanInput}
                                    onChange={e => setEanInputs(prev => ({ ...prev, [sz]: e.target.value }))}
                                    placeholder="Enter/Scan EAN..."
                                    data-testid={`ean-input-${sz}`}
                                    className={`w-full border px-2 py-1 text-[11px] font-mono outline-none transition-colors focus:border-teal-500 ${isEanMissing ? 'border-red-400 bg-red-50/30' : 'border-slate-300'}`}
                                  />
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    {eanSourceMeta[sz]?.source === "client" ? (
                                      eanInput.trim() === eanSourceMeta[sz]?.originalVal ? (
                                        <span
                                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-emerald-50 text-emerald-700 border border-emerald-200"
                                          data-testid={`ean-source-client-${sz}`}
                                          title="Auto-filled from client barcode file"
                                        >
                                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
                                          Auto-filled from client file
                                        </span>
                                      ) : (
                                        <span
                                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-blue-50 text-blue-700 border border-blue-200"
                                          data-testid={`ean-source-modified-${sz}`}
                                          title="Pre-filled from client file, then manually edited"
                                        >
                                          Manual override (edited)
                                        </span>
                                      )
                                    ) : (
                                      <span
                                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-amber-50 text-amber-700 border border-amber-200"
                                        data-testid={`ean-source-manual-${sz}`}
                                        title="Needs manual entry — no matching barcode in client file for this size"
                                      >
                                        <AlertCircle className="w-2.5 h-2.5 text-amber-600" />
                                        Needs manual entry
                                      </span>
                                    )}
                                    {isEanMissing && (
                                      <span className="text-[9px] text-red-500 font-bold block" data-testid={`ean-required-${sz}`}>
                                        * Required
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ) : (
                                <span className="text-slate-400 italic">No items completed</span>
                              )}
                            </td>
                            
                            {/* Cartons Configuration */}
                            <td className="px-3 py-3">
                              {completed > 0 ? (
                                <div className="flex flex-wrap items-center gap-2">
                                  {rows.map((qty, idx) => (
                                    <div key={idx} className="flex items-center border border-slate-200 bg-slate-50 px-1 py-0.5 gap-1">
                                      <span className="text-[10px] text-slate-400 font-mono">B{idx+1}:</span>
                                      <input
                                        type="number"
                                        min="1"
                                        value={qty}
                                        onChange={e => updateCartonRow(sz, idx, e.target.value)}
                                        className="w-12 border border-slate-300 px-1 py-0.5 text-center text-[11px] font-mono focus:border-teal-500 outline-none"
                                      />
                                      <button
                                        type="button"
                                        onClick={() => removeCartonRow(sz, idx)}
                                        className="text-slate-400 hover:text-red-600 p-0.5"
                                      >
                                        <X className="w-3 h-3" />
                                      </button>
                                    </div>
                                  ))}
                                  <button
                                    type="button"
                                    onClick={() => addCartonRow(sz)}
                                    className="px-2 py-1 border border-dashed border-teal-500 text-teal-600 hover:bg-teal-50 font-bold text-[10px] uppercase flex items-center gap-0.5"
                                  >
                                    <Plus className="w-3 h-3" /> Add Box
                                  </button>
                                </div>
                              ) : (
                                <span className="text-slate-400">—</span>
                              )}
                            </td>
                            
                            {/* Cartons Sum */}
                            <td className="px-3 py-3 text-right font-mono font-bold text-slate-700">
                              {completed > 0 ? `${sum} prs` : "0 prs"}
                            </td>
                            
                            {/* Status */}
                            <td className="px-3 py-3 text-center">
                              {completed > 0 ? (
                                isMatch ? (
                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-800 border border-green-200">
                                    <Check className="w-3 h-3 mr-0.5" /> OK
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                                    Mismatch ({sum - completed > 0 ? `+${sum - completed}` : sum - completed})
                                  </span>
                                )
                              ) : (
                                <span className="text-slate-400 font-mono">—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>

            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-50 border-t border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <button
            type="button"
            disabled={loading}
            onClick={handleConfirm}
            data-testid="confirm-carton-packing-btn"
            className="px-6 py-2 bg-[#0D9488] hover:bg-[#0B7A70] text-white font-bold uppercase tracking-wider text-xs shadow-md disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
          >
            {isAlreadyInQcPack ? "Save Configuration" : "Confirm Packing & Move to QC & Pack"}
          </button>
        </div>

      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
//  DispatchDialog — invoice + packing list + carton labels
// ═══════════════════════════════════════════════════════════
function DispatchField({ label, children }) {
  return (
    <div className="space-y-1">
      <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-500">{label}</label>
      {children}
    </div>
  );
}

function DispatchDialog({ group, groups, onClose, load, onSuccess }) {
  const activeGroups = useMemo(() => {
    if (groups && Array.isArray(groups) && groups.length > 0) return groups;
    if (group) return [group];
    return [];
  }, [group, groups]);

  const isMerged = activeGroups.length > 1;
  const primaryGroup = activeGroups[0] || {};
  const poNumber = primaryGroup.po_number || "";
  const clientName = primaryGroup.client_name || "";
  const poId = primaryGroup.po_id || primaryGroup.rows?.[0]?.po_id || "";

  const allRows = useMemo(() => activeGroups.flatMap(g => g.rows || []), [activeGroups]);
  const jobIds = useMemo(() => allRows.map(r => r.id).filter(Boolean), [allRows]);
  const totalPairs = allRows.reduce((s, r) => s + (r.quantity || 0), 0);
  const sizes = Array.from(new Set(allRows.map(r => String(r.size || "—")))).sort(sortSizes).join(", ");

  const [form, setForm] = useState({
    transport_mode: "",
    vehicle_no: "",
    supply_date: new Date().toISOString().slice(0, 10),
    transporter: "",
    dispatch_date: new Date().toISOString().slice(0, 10),
    carton_dim: "60x50x30 CMS",
    net_wt_per_carton: "",
    gross_wt_per_carton: "",
    notes: "",
    transporter_id: "",
    trans_distance: "",
    to_pincode: "",
    to_place: "",
  });
  const [dispatchQuantities, setDispatchQuantities] = useState(() => {
    const init = {};
    allRows.forEach(r => {
      init[r.id] = r.completed_qty != null ? r.completed_qty : (r.quantity || 0);
    });
    return init;
  });
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);
  const [unpackedCards, setUnpackedCards] = useState([]);
  const [archiving, setArchiving] = useState(false);

  const handleVerifyAndArchive = async () => {
    if (!jobIds.length) return;
    setArchiving(true);
    try {
      const res = await http.post("/production/jobs/archive", { job_ids: jobIds });
      const count = res.data?.archived_count || jobIds.length;
      alert(`Verified and moved ${count} production card(s) to Archive.`);
      onSuccess?.();
      await load();
      onClose();
    } catch (e) {
      alert("Archiving failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setArchiving(false);
    }
  };

  useEffect(() => {
    if (!jobIds.length) return;
    http.get(`/packing/cartons?job_ids=${jobIds.join(",")}`)
      .then(res => {
        const cartons = res.data || [];
        const cartonsWithJobId = cartons.filter(c => c && c.job_id);
        if (cartonsWithJobId.length > 0 && isMerged) {
          const packedJobIds = new Set(cartonsWithJobId.map(c => String(c.job_id)));
          const missing = [];
          activeGroups.forEach(g => {
            const gJobIds = (g.rows || []).map(r => String(r.id));
            const hasPacked = gJobIds.some(jid => packedJobIds.has(jid));
            if (!hasPacked) missing.push(g);
          });
          setUnpackedCards(missing);
        } else {
          setUnpackedCards([]);
        }
      })
      .catch(() => {});
  }, [jobIds, activeGroups, isMerged]);

  const downloadFile = async (type, filename, mimeType) => {
    if (!done?.dispatch_record_id) return;
    try {
      const res = await http.get(`/dispatch-records/${done.dispatch_record_id}/${type}`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = filename.replace(/[\/\\]/g, "-");
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const totalDispatchPairs = useMemo(() => {
    return allRows.reduce((acc, r) => {
      const q = dispatchQuantities[r.id];
      return acc + (q !== "" && q !== undefined ? Number(q) : (r.completed_qty || r.quantity || 0));
    }, 0);
  }, [allRows, dispatchQuantities]);

  const handleDispatch = useCallback(async () => {
    if (!poId) { setErr("Cannot find PO for this group — contact admin."); return; }
    if (!jobIds.length) { setErr("No job IDs available."); return; }
    if (isMerged && unpackedCards.length > 0) {
      setErr(`Please pack cartons for all selected cards before dispatching: ${unpackedCards.map(g => `${g.style_code} (${g.color})`).join(", ")}`);
      return;
    }
    setLoading(true); setErr(null);
    try {
      const payload = {
        job_ids: jobIds,
        po_id: poId,
        dispatch_quantities: Object.fromEntries(
          Object.entries(dispatchQuantities).map(([k, v]) => [k, v === "" ? 0 : Number(v)])
        ),
        ...form,
        trans_distance: form.trans_distance ? parseFloat(form.trans_distance) : null,
        transporter_id: form.transporter_id || "",
        to_pincode: form.to_pincode || "",
        to_place: form.to_place || "",
        net_wt_per_carton: form.net_wt_per_carton ? parseFloat(form.net_wt_per_carton) : null,
        gross_wt_per_carton: form.gross_wt_per_carton ? parseFloat(form.gross_wt_per_carton) : null,
      };
      const resp = await http.post("/dispatch", payload, { responseType: "blob" });
      const blob = new Blob([resp.data], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const invoiceNo = resp.headers?.["x-invoice-no"] || "dispatch";
      const safeInvoiceNo = invoiceNo.replace(/[\/\\]/g, "-");
      const drId = resp.headers?.["x-dispatch-record-id"] || "";
      a.href = url; a.download = `Dispatch-${safeInvoiceNo}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      setDone({ dispatch_record_id: drId, invoice_no: invoiceNo });
      onSuccess?.();
      await load();
    } catch (e) {
      let msg = "Dispatch failed — check server logs.";
      try {
        const txt = await e?.response?.data?.text();
        if (txt) {
          const parsed = JSON.parse(txt);
          msg = formatError(parsed?.detail || parsed);
        }
      } catch {}
      setErr(msg);
    } finally { setLoading(false); }
  }, [form, poId, jobIds, dispatchQuantities, unpackedCards, onSuccess, load]);

  const ic = "w-full border border-slate-300 px-2.5 py-2.5 text-sm text-slate-800 focus:border-[#0D9488] outline-none min-h-[44px]";

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4 overflow-y-auto" data-testid="dispatch-dialog">
      <div className="bg-white shadow-2xl w-full sm:max-w-xl flex flex-col max-h-[100dvh]">
        {/* Header */}
        <div className="bg-[#0D9488] px-6 py-4 shrink-0 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-teal-100 font-bold">
              {isMerged ? "Generate Merged Dispatch Documents" : "Generate Dispatch Documents"}
            </div>
            {isMerged ? (
              <>
                <div className="text-white font-bold text-lg mt-0.5" data-testid="dispatch-dialog-title">
                  PO: {poNumber} · Merged Dispatch ({activeGroups.length} Cards)
                </div>
                <div className="text-xs text-teal-100 mt-0.5 font-medium flex items-center gap-1 flex-wrap" data-testid="dispatch-dialog-subtitle">
                  {clientName && <span>{clientName} • </span>}
                  <span>{activeGroups.map(g => `${g.style_code} (${g.color})`).join(", ")}</span>
                </div>
              </>
            ) : (
              <div className="text-white font-bold text-lg mt-0.5" data-testid="dispatch-dialog-title">{primaryGroup.style_code} · {primaryGroup.color}</div>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 touch-manipulation flex-shrink-0"
            aria-label="Close"
          >
            <X className="w-5 h-5 text-white" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          {/* Summary strip */}
          <div className="bg-slate-50 border border-slate-200 p-4 rounded">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">
              {isMerged ? "Merged Dispatch Summary" : "Dispatch Summary"}
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div><div className="text-2xl font-black text-teal-700" data-testid="dispatch-total-pairs">{totalDispatchPairs}</div><div className="text-[10px] text-slate-400 uppercase">Dispatch Pairs</div></div>
              <div><div className="text-2xl font-black text-[#0F172A]">{jobIds.length}</div><div className="text-[10px] text-slate-400 uppercase">Job Lines</div></div>
              <div>
                <div className="text-sm font-bold text-[#0F172A] truncate" title={isMerged ? activeGroups.map(g => `${g.style_code} (${g.color})`).join(", ") : sizes}>
                  {isMerged ? `${activeGroups.length} Cards` : (sizes || "—")}
                </div>
                <div className="text-[10px] text-slate-400 uppercase">{isMerged ? "Cards Merged" : "Sizes"}</div>
              </div>
            </div>
            <p className="mt-3 pt-3 border-t border-slate-200 text-[11px] text-slate-500">
              {isMerged
                ? "Single invoice will be created containing 1 line item per style & color. Cartons sequentially numbered 1..N across all cards."
                : "Box numbers assigned 1..N (sorted by size). Invoice uses actual packed qty from carton rows."
              }
            </p>
          </div>

          {unpackedCards.length > 0 && (
            <div className="bg-amber-50 border border-amber-300 text-amber-900 px-4 py-3 rounded text-xs space-y-1" data-testid="unpacked-warning">
              <div className="font-bold flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                Missing Packed Cartons
              </div>
              <div>
                The following card(s) do not have packed cartons yet:{" "}
                <strong>{unpackedCards.map(g => `${g.style_code} (${g.color})`).join(", ")}</strong>.
                Please click <em>Pack Carton</em> for these cards in QC &amp; Pack before dispatching.
              </div>
            </div>
          )}

          {/* Dispatch Quantities & Partial Split Section */}
          <div className="bg-slate-50 border border-slate-200 p-4 rounded space-y-3" data-testid="dispatch-quantities-section">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                Dispatch Quantities per Size / Job Line
              </div>
              <span className="text-[11px] font-mono text-slate-500">
                Total to dispatch: <strong className="text-teal-700">{totalDispatchPairs}</strong> / {totalPairs} pairs
              </span>
            </div>

            <div className="space-y-3">
              {isMerged ? (
                activeGroups.map((g) => (
                  <div key={g.key} className="bg-white border border-slate-200 rounded p-3 space-y-2 shadow-sm">
                    <div className="flex items-center justify-between border-b pb-1.5 border-slate-100 flex-wrap gap-1">
                      <div>
                        <span className="font-mono font-bold text-sm text-slate-900 mr-2">{g.style_code}</span>
                        <span className="text-xs font-bold text-[#C27842]">{g.color}</span>
                      </div>
                      <span className="text-xs font-mono text-slate-500 font-bold">{g.totalQty} pairs</span>
                    </div>
                    <div className="space-y-2 pt-1">
                      {(g.rows || []).map((r) => {
                        const fullQty = r.quantity || 0;
                        const completedQty = r.completed_qty != null ? r.completed_qty : fullQty;
                        const currentVal = dispatchQuantities[r.id] !== undefined ? dispatchQuantities[r.id] : completedQty;
                        const nowQty = currentVal === "" ? 0 : Number(currentVal);
                        const remainder = Math.max(0, fullQty - nowQty);
                        const stageObj = STAGES.find(s => s.key === r.stage);
                        const stageLabel = stageObj?.label || r.stage || "Production";

                        return (
                          <div key={r.id} className="bg-slate-50 border border-slate-200 p-2.5 rounded space-y-1.5">
                            <div className="flex items-center justify-between gap-3 flex-wrap">
                              <div>
                                <span className="font-mono font-bold text-sm text-slate-900 mr-2">Size {r.size || "—"}</span>
                                <span className="text-xs text-slate-500">Full: <strong className="font-mono text-slate-700">{fullQty} prs</strong></span>
                                {r.completed_qty != null && (
                                  <span className="text-xs text-slate-400 ml-2">({r.completed_qty} completed)</span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                <label className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">Dispatch now:</label>
                                <input
                                  type="number"
                                  min="0"
                                  max={fullQty}
                                  data-testid={`dispatch-qty-input-${r.id}`}
                                  value={currentVal}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setDispatchQuantities(prev => ({
                                      ...prev,
                                      [r.id]: v === "" ? "" : Math.max(0, Math.min(fullQty, parseInt(v, 10) || 0))
                                    }));
                                  }}
                                  className="w-24 border-2 border-slate-300 px-2.5 py-1.5 font-mono text-sm text-right font-bold text-slate-900 focus:border-[#0D9488] outline-none bg-white"
                                />
                                <span className="text-xs font-mono text-slate-500">prs</span>
                              </div>
                            </div>
                            {remainder > 0 && (
                              <div className="text-[11px] bg-amber-50 border border-amber-200 text-amber-800 px-2 py-0.5 rounded flex items-center gap-1.5" data-testid={`remainder-indicator-${r.id}`}>
                                <span>⚠️</span>
                                <span><strong>{remainder} pairs</strong> will remain active in <strong>{stageLabel}</strong></span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))
              ) : (
                (primaryGroup.rows || []).map((r) => {
                  const fullQty = r.quantity || 0;
                  const completedQty = r.completed_qty != null ? r.completed_qty : fullQty;
                  const currentVal = dispatchQuantities[r.id] !== undefined ? dispatchQuantities[r.id] : completedQty;
                  const nowQty = currentVal === "" ? 0 : Number(currentVal);
                  const remainder = Math.max(0, fullQty - nowQty);
                  const stageObj = STAGES.find(s => s.key === r.stage);
                  const stageLabel = stageObj?.label || r.stage || "Production";

                  return (
                    <div key={r.id} className="bg-white border border-slate-200 p-3 rounded space-y-2">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div>
                          <span className="font-mono font-bold text-sm text-slate-900 mr-2">Size {r.size || "—"}</span>
                          <span className="text-xs text-slate-500">Full Job Qty: <strong className="font-mono text-slate-700">{fullQty} prs</strong></span>
                          {r.completed_qty != null && (
                            <span className="text-xs text-slate-400 ml-2">({r.completed_qty} completed)</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <label className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">Dispatch now:</label>
                          <input
                            type="number"
                            min="0"
                            max={fullQty}
                            data-testid={`dispatch-qty-input-${r.id}`}
                            value={currentVal}
                            onChange={(e) => {
                              const v = e.target.value;
                              setDispatchQuantities(prev => ({
                                ...prev,
                                [r.id]: v === "" ? "" : Math.max(0, Math.min(fullQty, parseInt(v, 10) || 0))
                              }));
                            }}
                            className="w-24 border-2 border-slate-300 px-2.5 py-1.5 font-mono text-sm text-right font-bold text-slate-900 focus:border-[#0D9488] outline-none"
                          />
                          <span className="text-xs font-mono text-slate-500">prs</span>
                        </div>
                      </div>

                      {remainder > 0 && (
                        <div className="text-[11px] bg-amber-50 border border-amber-200 text-amber-800 px-2.5 py-1 rounded flex items-center gap-1.5" data-testid={`remainder-indicator-${r.id}`}>
                          <span>⚠️</span>
                          <span>
                            <strong>{remainder} pairs</strong> will remain active in <strong>{stageLabel}</strong> stage
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Shipping fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <DispatchField label="Transport Mode"><input className={ic} value={form.transport_mode} placeholder="By Road" data-testid="dispatch-input-transport-mode" onChange={e => set("transport_mode", e.target.value)} /></DispatchField>
            <DispatchField label="Vehicle No."><input className={ic} value={form.vehicle_no} placeholder="MH-01-AB-1234" data-testid="dispatch-input-vehicle-no" onChange={e => set("vehicle_no", e.target.value)} /></DispatchField>
            <DispatchField label="Transporter"><input className={ic} value={form.transporter} placeholder="Transporter name" data-testid="dispatch-input-transporter" onChange={e => set("transporter", e.target.value)} /></DispatchField>
            <DispatchField label="Transporter ID / GSTIN"><input className={ic} value={form.transporter_id} placeholder="e.g. 27AABCT1234A1Z5" data-testid="dispatch-input-transporter-id" onChange={e => set("transporter_id", e.target.value)} /></DispatchField>
            <DispatchField label="Approx Distance (KM)"><input type="number" className={ic} value={form.trans_distance} placeholder="e.g. 150" min="0" data-testid="dispatch-input-trans-distance" onChange={e => set("trans_distance", e.target.value)} /></DispatchField>
            <DispatchField label="Supply / Dispatch Date"><input type="date" className={ic} value={form.supply_date} data-testid="dispatch-input-supply-date" onChange={e => set("supply_date", e.target.value)} /></DispatchField>
            <DispatchField label="Destination Pincode"><input className={ic} value={form.to_pincode} placeholder="Auto from PO if empty" data-testid="dispatch-input-to-pincode" onChange={e => set("to_pincode", e.target.value)} /></DispatchField>
            <DispatchField label="Destination City"><input className={ic} value={form.to_place} placeholder="Auto from PO if empty" data-testid="dispatch-input-to-place" onChange={e => set("to_place", e.target.value)} /></DispatchField>
            <DispatchField label="Carton Dimensions"><input className={ic} value={form.carton_dim} placeholder="60x50x30 CMS" data-testid="dispatch-input-carton-dim" onChange={e => set("carton_dim", e.target.value)} /></DispatchField>
            <DispatchField label="Net Wt/Carton (kg)"><input type="number" className={ic} value={form.net_wt_per_carton} placeholder="10.8" inputMode="decimal" data-testid="dispatch-input-net-wt" onChange={e => set("net_wt_per_carton", e.target.value)} /></DispatchField>
            <DispatchField label="Gross Wt/Carton (kg)"><input type="number" className={ic} value={form.gross_wt_per_carton} placeholder="12.0" inputMode="decimal" data-testid="dispatch-input-gross-wt" onChange={e => set("gross_wt_per_carton", e.target.value)} /></DispatchField>
            <DispatchField label="Notes"><input className={ic} value={form.notes} placeholder="Optional" data-testid="dispatch-input-notes" onChange={e => set("notes", e.target.value)} /></DispatchField>
          </div>

          {err && <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded">{err}</div>}
          {done && (
            <div className="bg-teal-50 border border-teal-200 text-teal-800 text-sm px-4 py-4 rounded space-y-3" data-testid="dispatch-success-msg">
              <div>
                <div className="font-bold">✅ Dispatched — Invoice {done.invoice_no}</div>
                <div className="text-xs text-teal-700 mt-1">
                  {isMerged ? `ZIP downloaded. Single invoice generated for ${activeGroups.length} production cards.` : "ZIP downloaded."} Re-download individual documents:
                </div>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => downloadFile("invoice", `Invoice-${done.invoice_no}.pdf`, "application/pdf")}
                  className="px-3 py-1.5 bg-white border border-teal-600 text-teal-700 text-xs font-bold uppercase tracking-wider hover:bg-teal-50 transition-colors"
                >
                  Invoice PDF
                </button>
                <button
                  type="button"
                  onClick={() => downloadFile("packing-list", `PackingList-${done.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                  className="px-3 py-1.5 bg-white border border-teal-600 text-teal-700 text-xs font-bold uppercase tracking-wider hover:bg-teal-50 transition-colors"
                >
                  Packing List XLSX
                </button>
                <button
                  type="button"
                  onClick={() => downloadFile("carton-labels", `CartonLabels-${done.invoice_no}.pdf`, "application/pdf")}
                  className="px-3 py-1.5 bg-white border border-teal-600 text-teal-700 text-xs font-bold uppercase tracking-wider hover:bg-teal-50 transition-colors"
                >
                  Carton Labels PDF
                </button>
                <button
                  type="button"
                  onClick={() => downloadFile("carton-list", `CartonList-${done.invoice_no}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                  className="px-3 py-1.5 bg-white border border-teal-600 text-teal-700 text-xs font-bold uppercase tracking-wider hover:bg-teal-50 transition-colors"
                >
                  Carton List XLSX
                </button>
                <button
                  type="button"
                  onClick={() => downloadFile("ewaybill", `EWayBill-${done.invoice_no}.json`, "application/json")}
                  className="px-3 py-1.5 bg-white border border-teal-600 text-teal-700 text-xs font-bold uppercase tracking-wider hover:bg-teal-50 transition-colors"
                  data-testid="dispatch-download-ewaybill-btn"
                >
                  E-Way Bill JSON
                </button>
              </div>

              <div className="pt-3 border-t border-teal-200/80 flex items-center justify-between gap-3 flex-wrap">
                <div className="text-xs text-teal-900 font-medium">
                  Verified documents? Move dispatched cards to Archive:
                </div>
                <button
                  type="button"
                  onClick={handleVerifyAndArchive}
                  disabled={archiving}
                  className="px-4 py-2 bg-[#0F172A] hover:bg-slate-800 text-white font-bold text-xs uppercase tracking-wider flex items-center gap-1.5 shadow-md transition-all disabled:opacity-50"
                  data-testid="dispatch-verify-archive-btn"
                >
                  <Archive className="w-3.5 h-3.5 text-amber-400" />
                  {archiving ? "Archiving..." : `Verify & Move ${isMerged ? `All (${activeGroups.length} Cards)` : "Card"} to Archive`}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-50 border-t border-slate-200 px-6 py-4 flex items-center justify-between shrink-0 gap-3">
          <button onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 font-medium">{done ? "Close" : "Cancel"}</button>
          {done ? (
            <button
              type="button"
              onClick={handleVerifyAndArchive}
              disabled={archiving}
              className="px-6 py-2.5 bg-[#0F172A] hover:bg-slate-800 text-white font-bold uppercase tracking-wider text-xs shadow-md transition-colors flex items-center gap-2 disabled:opacity-50"
              data-testid="dispatch-dialog-archive-footer-btn"
            >
              <Archive className="w-4 h-4 text-amber-400" />
              {archiving ? "Moving..." : `Verify & Move to Archive ${isMerged ? `(${activeGroups.length} Cards)` : ""}`}
            </button>
          ) : (
            <button
              type="button"
              disabled={loading || !poId || (isMerged && unpackedCards.length > 0 && !done)}
              onClick={handleDispatch}
              data-testid="dispatch-confirm-btn"
              className="px-6 py-2.5 bg-[#0D9488] hover:bg-[#0B7A70] text-white font-bold uppercase tracking-wider text-xs shadow-md disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading
                ? <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Generating…</>
                : <><FileDown className="w-4 h-4" /> {isMerged ? "Generate Merged Docs & Download ZIP" : "Generate & Download ZIP"}</>
              }
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
