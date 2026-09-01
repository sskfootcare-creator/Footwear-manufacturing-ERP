import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { SafeImage } from "../components/ImageUploader";
import { useAuth } from "../lib/auth";
import { FileDown, Check, UserPlus, Edit3, ClipboardList, X, HardHat, GripVertical, Printer, MessageCircle, AlertTriangle, Clock, Package, Archive, Eye, CheckCircle, Trash2, Save, Plus, ChevronDown, ChevronUp, Layers, Truck, FileSpreadsheet, Loader2, CheckCircle2, AlertCircle, Barcode } from "lucide-react";
import ResponsiveTable from "../components/ResponsiveTable";

const STAGES = [
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
};

const ASSIGNMENT_ROLES = [
  { key: "cutting", label: "Cutting" },
  { key: "upper", label: "Upper" },
  { key: "bottom", label: "Bottom/Insole" },
  { key: "stitching", label: "Stitching" },
  { key: "lasting", label: "Lasting" },
  { key: "sole_pasting", label: "Sole Pasting" },
  { key: "finishing", label: "Finishing" },
  { key: "qc_pack", label: "QC & Pack" },
];

// Stage → most likely role mapping for bulk-drag assignment
const STAGE_TO_ROLE = {
  cutting: "cutting",
  folding: "upper",
  attachment: "upper",
  stitching: "stitching",
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
        client_name: j.client_name, description: j.description, delivery_date: j.delivery_date,
        color, rows: [], sizes: new Set(),
      };
    }
    groups[key].rows.push(j);
    groups[key].sizes.add(String(j.size || "—"));
  }
  return Object.values(groups).map(g => ({
    ...g,
    stage: g.rows[0]?.stage,
    sizes: Array.from(g.sizes).sort(sortSizes),
    totalQty: g.rows.reduce((s, r) => s + (r.quantity || 0), 0),
    components: aggregateComponents(g.rows),
    assignments: aggregateAssignments(g.rows),
    overdueHours: aggregateOverdue(g.rows),
  }));
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
  return { upper_done: all("upper_done"), bottom_done: all("bottom_done"), sole_done: all("sole_done") };
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
  const [archivedJobs, setArchivedJobs] = useState([]);
  const [detailFor, setDetailFor] = useState(null);
  const [packingFor, setPackingFor] = useState(null); // {kind:'single'|'merged', group?, jobs?}
  const [cartonPackFor, setCartonPackFor] = useState(null); // job group
  const [dispatchFor, setDispatchFor] = useState(null);     // group to dispatch
  const [savedPackingLists, setSavedPackingLists] = useState([]);
  const [dispatchRecords, setDispatchRecords] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [dispatchDetailFor, setDispatchDetailFor] = useState(null);
  const { user } = useAuth();
  const canEdit = ["admin", "manager", "production"].includes(user?.role);

  const load = async () => {
    const [j, w, s, ar, pl, dr, invs] = await Promise.all([
      http.get("/production/jobs"),
      http.get("/workers"),
      http.get("/styles"),
      http.get("/production/archive"),
      http.get("/packing-lists"),
      http.get("/dispatch-records?limit=1000"),
      http.get("/invoices").catch(() => ({ data: [] })),
    ]);
    setJobs(j.data); setWorkers(w.data); setStyles(s.data);
    setArchivedJobs(ar.data); setSavedPackingLists(pl.data || []);
    setDispatchRecords(dr.data || []);
    setInvoices(invs.data || []);
  };
  useEffect(() => { load(); }, []);

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

  const archivedGroupsCount = useMemo(() => {
    return groupJobsByColor(archivedJobs).length;
  }, [archivedJobs]);


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
        `Style: ${group.style_code}  Color: ${group.color}`,
        `Total: ${group.totalQty} pairs`,
        `Sizes: ${sizeBreak}`,
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
    await Promise.all(group.rows.map(j => http.patch(`/production/jobs/${j.id}/components`, { [key]: val })));
    load();
  };
  const assignWorker = async (group, role, workerId, rate) => {
    await Promise.all(group.rows.map(j =>
      http.patch(`/production/jobs/${j.id}/assignment`, {
        role, worker_id: workerId || null,
        rate_per_pair: rate === undefined || rate === "" ? null : Number(rate),
      })
    ));
    setAssignFor(null);
    load();
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

  // Procurement: select cards & generate material requirement
  const toggleProcSelect = (group) => setProcSelected(s => {
    const next = { ...s }; if (next[group.key]) delete next[group.key]; else next[group.key] = group; return next;
  });
  const downloadMaterialRequirement = async (groups, label) => {
    const job_ids = [];
    groups.forEach(g => g.rows.forEach(r => job_ids.push(r.id)));
    try {
      const res = await http.post("/procurement/requirement.pdf",
        { job_ids, scope_label: label || `${groups.length} card(s)` }, { responseType: "blob" });
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

  const dispatchedCount = Object.keys(selected).length;
  const procSelectedCount = Object.keys(procSelected).length;

  return (
    <div>
      <PageHeader
        title="Production Floor"
        subtitle="Manufacturing / Kanban"
        testId="production-header"
        action={
          <div className="flex gap-2 items-center">
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
                <BtnPrimary onClick={() => { downloadMaterialRequirement(Object.values(procSelected), `${procSelectedCount} procurement cards`); setProcSelected({}); }} data-testid="merged-mr-btn" className="px-3 sm:px-4 flex items-center gap-1">
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
          </div>
        }
      />

      <div className="p-4 sm:p-8">
        {viewArchive ? (
          <ArchivePanel
            jobs={archivedJobs}
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
          />
        ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {STAGES.map((s) => {
              const { stageJobs, groups, totalQty } = stageDataByStageKey[s.key] || { stageJobs: [], groups: [], totalQty: 0 };
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
                        isProc={isProc}
                        isDispatched={isDisp}
                        onMatReq={() => downloadMaterialRequirement([g], `${g.style_code} · ${g.color}`)}
                        procSelected={!!procSelected[g.key]}
                        onToggleProcSelect={toggleProcSelect}
                        onDownloadInvoice={downloadGroupInvoice}
                        isSelected={!!selected[g.key]}
                        onToggleSelect={toggleSelect}
                        isSelectDisabled={isSelectionDisabled(g)}
                        dispatchRecordByJobId={dispatchRecordByJobId}
                        onDownloadDispatchFile={downloadDispatchFile}
                        onOpenDispatchDetails={(group) => setDispatchDetailFor(group)}
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
          current={assignFor.group.assignments?.[assignFor.role]}
          onSave={(wid, rate) => assignWorker(assignFor.group, assignFor.role, wid, rate)}
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
          group={dispatchFor}
          onClose={() => setDispatchFor(null)}
          load={load}
        />
      )}

      {bulkConfirm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="bulk-assign-dialog">
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
    </div>
  );
}

function ColorGroupCard(props) {
  const { group, style, stageColor, stageIdx, canEdit, onMove, onToggleComponent,
    onOpenAssign, onOpenQty, onPrint, onWhatsApp, onPacking, isProc, isDispatched, onMatReq,
    procSelected, onToggleProcSelect, isSelected, onToggleSelect, onDownloadInvoice, onPackCartons, onDispatch,
    dispatchRecordByJobId, onDownloadDispatchFile, isSelectDisabled, onOpenDispatchDetails } = props;
  const nextStage = STAGES[stageIdx + 1];
  const prevStage = STAGES[stageIdx - 1];

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
      {(style?.image_url ||
        style?.image_display_url ||
        style?.image_thumbnail_url) && (
        <SafeImage
          image={{
            url: style.image_url,
            display_url: style.image_display_url,
            thumbnail_url: style.image_thumbnail_url,
          }}
          alt={style.name}
          aspectRatio="16/7"
          className="border-b border-slate-200"
          testId={`card-img-${group.key}`}
        />
      )}
      <div className="p-3 pb-2 border-b border-slate-100">
        <div className="flex items-baseline justify-between mb-0.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{group.po_number}</div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{group.client_name}</div>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <div className="font-mono font-bold text-sm">{group.style_code}</div>
            <div className="text-xs">
              <span className="font-bold text-[#C27842]">{group.color}</span>
              <span className="text-slate-400 mx-1">·</span>
              <span className="text-slate-600 font-mono">{group.totalQty} pairs</span>
              {completedTotal > 0 && (
                <>
                  <span className="text-slate-400 mx-1">·</span>
                  <span className="text-green-700 font-mono">{completedTotal} done</span>
                </>
              )}
            </div>
          </div>
          {isDispatched && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={isSelected} disabled={isSelectDisabled && !isSelected} onChange={() => onToggleSelect(group)} className={`w-4 h-4 accent-[#C27842] ${isSelectDisabled && !isSelected ? "cursor-not-allowed opacity-50" : ""}`} data-testid={`select-${group.key}`} />
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Merge</span>
            </label>
          )}
          {isProc && (
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={procSelected} onChange={() => onToggleProcSelect(group)} className="w-4 h-4 accent-[#2563EB]" data-testid={`proc-select-${group.key}`} />
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Combine</span>
            </label>
          )}
        </div>
      </div>

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
        {effectiveCanEdit && (
          <div className="text-[9px] text-slate-400 mt-1 italic">Click any qty cell to edit / adjust completed / rejected</div>
        )}
      </div>

      {/* Components */}
      <div className="px-3 pb-2">
        <div className="flex items-center justify-between mb-1.5">
          <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-slate-500">Components</div>
          <div className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
            group.components.upper_done && group.components.bottom_done
              ? "bg-green-50 text-green-700 border-green-200"
              : "bg-amber-50 text-amber-700 border-amber-200"
          }`}>
            Upper {group.components.upper_done ? "✓" : "pending"} / Bottom {group.components.bottom_done ? "✓" : "pending"}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <ComponentCell label="Upper" done={group.components.upper_done} layers={COMPONENT_LAYERS.upper}
            disabled={!effectiveCanEdit} onToggle={(v) => onToggleComponent(group, "upper_done", v)} />
          <ComponentCell label="Bottom/Insole" done={group.components.bottom_done} layers={COMPONENT_LAYERS.bottom}
            disabled={!effectiveCanEdit} onToggle={(v) => onToggleComponent(group, "bottom_done", v)} />
          <ComponentCell label="Sole" done={group.components.sole_done} layers={COMPONENT_LAYERS.sole}
            disabled={!effectiveCanEdit} onToggle={(v) => onToggleComponent(group, "sole_done", v)} />
        </div>
      </div>

      {/* Karigar assignments */}
      <div className="px-3 pb-2">
        <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-slate-500 mb-1.5">Karigars</div>
        <div className="grid grid-cols-2 gap-1.5">
          {ASSIGNMENT_ROLES.map(r => (
            <button
              key={r.key}
              disabled={!effectiveCanEdit}
              onClick={() => onOpenAssign(r.key)}
              data-testid={`assign-${group.key}-${r.key}`}
              className={`flex items-center justify-between gap-1 px-2 py-1 border ${a[r.key] ? "border-[#C27842] bg-orange-50" : "border-dashed border-slate-300 bg-white"} hover:border-slate-900 text-left transition-colors`}
            >
              <span className="text-[9px] uppercase tracking-wider font-bold text-slate-500">{r.label}</span>
              <div className="text-right">
                <div className={`text-[10px] font-bold truncate ${a[r.key] ? "text-[#0F172A]" : "text-slate-400 italic"}`}>
                  {a[r.key]?.worker_name || "Assign…"}
                </div>
                {a[r.key]?.rate_per_pair !== undefined && a[r.key]?.rate_per_pair !== null && (
                  <div className="text-[9px] font-mono text-[#C27842]">₹{a[r.key].rate_per_pair}/pr</div>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="px-3 pb-3 flex items-center justify-between gap-2 flex-wrap">
        {group.delivery_date && <div className="text-[10px] text-slate-500">Deliver: {group.delivery_date}</div>}
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
            <button onClick={onMatReq} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-3 py-1 flex items-center gap-1" data-testid={`mat-req-${group.key}`}>
              <ClipboardList className="w-3 h-3" /> Material Req.
            </button>
          )}
          {isDispatched && (
            <button onClick={() => onOpenDispatchDetails?.(group)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-3 py-1 flex items-center gap-1 transition-colors" data-testid={`dispatch-details-btn-${group.key}`}>
              <Truck className="w-3 h-3" /> View Dispatch Details
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
    </Card>
  );
}

function ComponentCell({ label, done, layers, onToggle, disabled }) {
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
        {layers.map(l => <div key={l} className="text-[9px] text-slate-500 leading-tight">• {l}</div>)}
      </div>
    </div>
  );
}

function AssignDialog({ group, role, workers, current, onSave, onClose }) {
  const [selectedWid, setSelectedWid] = useState(current?.worker_id || "");
  const [rate, setRate] = useState(current?.rate_per_pair ?? "");
  const selectedWorker = workers.find(w => w.id === selectedWid);

  const roleObj = ASSIGNMENT_ROLES.find(r => r.key === role);
  const matchingSkill = role;
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
    setSelectedWid(w.id);
    if (rate === "" || rate === null || rate === undefined) setRate(w.rate_per_pair);
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="assign-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md max-h-[100dvh] overflow-y-auto">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Assign Karigar</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · {roleObj?.label}</div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 touch-manipulation"><X className="w-5 h-5" /></button>
        </div>

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
          {sorted.length === 0 ? (
            <div className="text-center text-sm text-slate-500 py-8">No karigars yet.</div>
          ) : (
            <div className="space-y-1.5">
              <button
                onClick={() => onSave(null, null)}
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

        {selectedWid && (
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
            <div className="flex gap-2">
              <BtnPrimary onClick={() => onSave(selectedWid, rate === "" ? null : rate)} className="min-h-[44px]" data-testid="assign-save">
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
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="qty-dialog">
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
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="whatsapp-dialog">
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


/* -------------------- ARCHIVE PANEL -------------------- */
function ArchivePanel({ jobs, styleByCode, onPrint, onPacking, onViewDetails, onViewDispatchDetails, savedPackingLists, onReDownloadPacking, dispatchRecordByJobId, onDownloadDispatchFile, onDownloadInvoice, invoices = [] }) {
  const [expandedClusters, setExpandedClusters] = useState({});
  const toggleExpand = (id) => setExpandedClusters(prev => ({ ...prev, [id]: !prev[id] }));

  const groups = useMemo(() => groupJobsByColor(jobs), [jobs]);
  const clusters = useMemo(() => clusterArchivedGroups(groups, dispatchRecordByJobId, invoices), [groups, dispatchRecordByJobId, invoices]);


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
        } catch (err) {
          // fallback to job_ids endpoint
        }
      }
      if (fallbackJobIds.length) {
        const res = await http.get(`/production/jobs/carton-labels?job_ids=${fallbackJobIds.join(",")}`, { responseType: "blob" });
        triggerDownload(res.data, `CartonLabels-${invoiceNo || "merged"}.pdf`, "application/pdf");
      }
    } catch (e) {
      alert("Carton Labels download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const downloadCombinedCartonList = async (jobIds, invoiceNo) => {
    try {
      const res = await http.get(`/production/jobs/carton-list?job_ids=${jobIds.join(",")}`, { responseType: "blob" });
      triggerDownload(res.data, `CartonList-${invoiceNo || "merged"}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    } catch (e) {
      alert("Carton List download failed: " + (e.response?.data?.detail || e.message));
    }
  };

  return (
    <div className="space-y-5" data-testid="archive-list">
      <Card className="bg-slate-50 border-2 border-slate-200 p-4">
        <div className="flex items-baseline justify-between">
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2"><Archive className="w-4 h-4 text-slate-700" /> Archived Production Cards</h2>
            <p className="text-xs text-slate-600 mt-1">Cards that have both invoice + packing list generated land here. Click <b>View details</b> to inspect full production history.</p>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            {clusters.length} card{clusters.length !== 1 ? "s" : ""} ({groups.length} group{groups.length !== 1 ? "s" : ""}) · {jobs.length} job{jobs.length !== 1 ? "s" : ""}
          </div>
        </div>
      </Card>

      {clusters.length === 0 ? (
        <Card className="p-12 text-center text-slate-400 text-sm" data-testid="archive-empty">
          Nothing archived yet — once both <b>Invoice</b> and <b>Packing List</b> are generated for a card it moves here automatically.
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="archive-grid">
          {clusters.map(cluster => {
            if (cluster.is_merged && cluster.groups.length > 1) {
              const isExpanded = !!expandedClusters[cluster.id];
              const allJobIds = cluster.groups.flatMap(g => g.rows.map(r => r.id));
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
                        <div className="font-mono font-bold text-xl text-[#C27842]">{totalClusterQty}</div>
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
                        {cluster.groups.map(g => (
                          <div key={g.key} className="py-1.5 flex items-center justify-between text-xs gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              {(styleByCode[g.style_code]?.image_thumbnail_url || styleByCode[g.style_code]?.image_url) && (
                                <img
                                  src={styleByCode[g.style_code]?.image_thumbnail_url || styleByCode[g.style_code]?.image_url}
                                  alt=""
                                  className="w-7 h-7 object-cover rounded border border-slate-200 flex-shrink-0"
                                />
                              )}
                              <div className="truncate">
                                <span className="font-bold text-slate-900">{g.style_code}</span>
                                <span className="text-slate-600 ml-1 font-semibold">({g.color})</span>
                                <div className="text-[10px] text-slate-500 truncate">
                                  Sizes: <span className="font-mono">{g.sizes.join(" · ")}</span>
                                </div>
                              </div>
                            </div>
                            <div className="font-mono font-bold text-slate-700 text-sm whitespace-nowrap">{g.totalQty} prs</div>
                          </div>
                        ))}
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
                        onClick={() => toggleExpand(cluster.id)}
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
                          return (
                            <div key={`drill-${g.key}`} className="bg-white p-2.5 rounded border border-slate-200 shadow-2xs space-y-2">
                              <div className="flex items-baseline justify-between">
                                <div>
                                  <span className="font-bold text-xs text-slate-900">{g.style_code}</span>
                                  <span className="text-[11px] text-slate-600 ml-1.5 font-bold">({g.color})</span>
                                  <div className="text-[10px] text-slate-500 font-mono">Sizes: {g.sizes.join(" · ")}</div>
                                </div>
                                <div className="font-mono font-bold text-xs text-[#C27842]">{g.totalQty} prs</div>
                              </div>
                              <div className="flex gap-1 flex-wrap pt-1.5 border-t border-slate-100">
                                <button onClick={() => onViewDispatchDetails?.(g)} className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-1.5 py-0.5 flex items-center gap-1" data-testid={`archive-merged-drilldown-dispatch-details-${g.key}`}>
                                  <Truck className="w-2.5 h-2.5" /> Dispatch Details
                                </button>
                                <button onClick={() => onViewDetails(g)} className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-1.5 py-0.5 flex items-center gap-1">
                                  <Eye className="w-2.5 h-2.5" /> Details Modal
                                </button>
                                <button onClick={() => onPrint(g)} className="text-[9px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-1.5 py-0.5 flex items-center gap-1">
                                  <Printer className="w-2.5 h-2.5" /> Card PDF
                                </button>
                                <button onClick={() => onPacking(g)} className="text-[9px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-1.5 py-0.5 flex items-center gap-1">
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
                                    <button
                                      onClick={async () => {
                                        try {
                                          const res = await http.get(`/production/jobs/carton-labels?job_ids=${g.rows.map(r => r.id).join(",")}`, { responseType: "blob" });
                                          triggerDownload(res.data, `CartonLabels-${(g.po_number || "dispatch").replace(/[\/\\]/g, "-")}-${g.style_code}.pdf`, "application/pdf");
                                        } catch (e) {
                                          alert("Carton Labels download failed: " + (e.response?.data?.detail || e.message));
                                        }
                                      }}
                                      className="text-[9px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Orig. Labels
                                    </button>
                                    <button
                                      onClick={async () => {
                                        try {
                                          const res = await http.get(`/production/jobs/carton-list?job_ids=${g.rows.map(r => r.id).join(",")}`, { responseType: "blob" });
                                          triggerDownload(res.data, `CartonList-${(g.po_number || "dispatch").replace(/[\/\\]/g, "-")}-${g.style_code}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
                                        } catch (e) {
                                          alert("Carton List download failed: " + (e.response?.data?.detail || e.message));
                                        }
                                      }}
                                      className="text-[9px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-1.5 py-0.5 flex items-center gap-1"
                                    >
                                      <FileDown className="w-2.5 h-2.5" /> Orig. Carton List
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

            // Non-merged single-item cluster — render EXACTLY as before
            const g = cluster.groups[0];
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
              <Card key={g.key} className="border-l-4 border-slate-400 hover:border-[#0F172A] transition-colors" data-testid={`archive-card-${g.key}`}>
                {(styleByCode[g.style_code]?.image_url ||
                  styleByCode[g.style_code]?.image_display_url ||
                  styleByCode[g.style_code]?.image_thumbnail_url) && (
                  <SafeImage
                    image={{
                      url: styleByCode[g.style_code]?.image_url,
                      display_url:
                        styleByCode[g.style_code]?.image_display_url,
                      thumbnail_url:
                        styleByCode[g.style_code]?.image_thumbnail_url,
                    }}
                    alt=""
                    aspectRatio="16/8"
                    testId={`archive-img-${g.key}`}
                  />
                )}
                <div className="p-4">
                  <div className="flex items-baseline justify-between mb-2">
                    <div>
                      <div className="font-mono text-xs text-slate-500">PO {g.po_number}</div>
                      <div className="font-bold text-base">{g.style_code}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{g.color}</div>
                      <div className="font-mono font-bold text-lg text-[#C27842]">{g.totalQty}</div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-600 mb-1">
                    <span className="font-bold uppercase tracking-wider text-[10px] text-slate-500">Client:</span> {g.client_name}
                  </div>
                  <div className="text-xs text-slate-600 mb-3">
                    <span className="font-bold uppercase tracking-wider text-[10px] text-slate-500">Sizes:</span>{" "}
                    <span className="font-mono">{g.sizes.join(" · ")}</span>
                  </div>
                  <div className="flex gap-1 flex-wrap pt-2 border-t border-slate-200">
                    <button onClick={() => onViewDispatchDetails?.(g)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0F172A] hover:bg-slate-800 px-2 py-1 flex items-center gap-1 transition-colors" data-testid={`archive-dispatch-details-${g.key}`}>
                      <Truck className="w-3 h-3" /> View Dispatch Details
                    </button>
                    <button onClick={() => onViewDetails(g)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-2 py-1 flex items-center gap-1" data-testid={`archive-details-${g.key}`}>
                      <Eye className="w-3 h-3" /> Production History
                    </button>
                    <button onClick={() => onPrint(g)} className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1">
                      <Printer className="w-3 h-3" /> Card PDF
                    </button>
                    <button onClick={() => onPacking(g)} className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-2 py-1 flex items-center gap-1">
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
                        <button
                          onClick={() => onDownloadInvoice(g)}
                          className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Invoice
                        </button>
                        <button
                          onClick={() => { onPacking(g); }}
                          className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Packing List
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              const res = await http.get(`/production/jobs/carton-labels?job_ids=${g.rows.map(r => r.id).join(",")}`, { responseType: "blob" });
                              triggerDownload(res.data, `CartonLabels-${(g.po_number || "dispatch").replace(/[\/\\]/g, "-")}-${g.style_code}.pdf`, "application/pdf");
                            } catch (e) {
                              alert("Carton Labels download failed: " + (e.response?.data?.detail || e.message));
                            }
                          }}
                          className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#0D9488] hover:bg-[#0B7A70] px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Labels
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              const res = await http.get(`/production/jobs/carton-list?job_ids=${g.rows.map(r => r.id).join(",")}`, { responseType: "blob" });
                              triggerDownload(res.data, `CartonList-${(g.po_number || "dispatch").replace(/[\/\\]/g, "-")}-${g.style_code}.xlsx`, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
                            } catch (e) {
                              alert("Carton List download failed: " + (e.response?.data?.detail || e.message));
                            }
                          }}
                          className="text-[10px] uppercase tracking-wider font-bold text-[#EAB308] border border-[#EAB308] hover:bg-[#EAB308] hover:text-white px-2 py-1 flex items-center gap-1"
                        >
                          <FileDown className="w-3 h-3" /> Carton List
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
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
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="detail-modal">
      <div className="bg-white w-full max-w-4xl max-h-[90vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold">Production Card · Archive</div>
            <div className="text-xl font-bold">{group.style_code} · {group.color} · {group.totalQty} pairs</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1" data-testid="detail-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <DLPair label="PO Number" value={group.po_number} />
            <DLPair label="Client" value={group.client_name} />
            <DLPair label="Style" value={group.style_code} />
            <DLPair label="Color" value={group.color} />
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
function DispatchDetailsModal({ item, dispatchRecordByJobId = {}, invoices = [], styleByCode = {}, onClose, onDownloadDispatchFile }) {
  const [loading, setLoading] = useState(true);
  const [dispatchRecord, setDispatchRecord] = useState(null);
  const [cartons, setCartons] = useState([]);
  const [invoiceData, setInvoiceData] = useState(null);

  const groups = useMemo(() => {
    if (!item) return [];
    if (item.groups && Array.isArray(item.groups)) return item.groups;
    return [item];
  }, [item]);

  const allRows = useMemo(() => groups.flatMap(g => g.rows || []), [groups]);
  const jobIds = useMemo(() => allRows.map(r => r.id).filter(Boolean), [allRows]);

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
              {groups.map(g => `${g.style_code} (${g.color})`).join(" + ")}
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
                        <th className="px-3 py-2">Style Code</th>
                        <th className="px-3 py-2">Color</th>
                        <th className="px-3 py-2 text-center">Size</th>
                        <th className="px-3 py-2 text-right">Dispatched Qty</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {sizeBreakdown.length === 0 ? (
                        <tr>
                          <td colSpan="4" className="px-3 py-4 text-center text-slate-400">No size breakdown available.</td>
                        </tr>
                      ) : (
                        sizeBreakdown.map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-50">
                            <td className="px-3 py-2 font-mono font-bold">{row.style_code}</td>
                            <td className="px-3 py-2 font-medium">{row.color}</td>
                            <td className="px-3 py-2 text-center font-mono font-bold text-slate-800">{row.size}</td>
                            <td className="px-3 py-2 text-right font-mono font-bold text-[#C27842]">{row.qty} prs</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                    {sizeBreakdown.length > 0 && (
                      <tfoot className="bg-slate-50 border-t-2 border-slate-200 font-bold">
                        <tr>
                          <td colSpan="3" className="px-3 py-2 text-right uppercase text-[10px] text-slate-600">Total Dispatched Pairs:</td>
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
        <div className="bg-slate-50 border-t border-slate-200 px-6 py-3.5 flex justify-end shrink-0">
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
        </div>
      </div>
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
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-0 sm:p-4" data-testid="packing-dialog">
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
      <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4">
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
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="shortage-modal">
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
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="carton-pack-dialog">
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
function DispatchDialog({ group, onClose, load }) {
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
  });
  const [dispatchQuantities, setDispatchQuantities] = useState(() => {
    const init = {};
    (group.rows || []).forEach(r => {
      init[r.id] = r.completed_qty != null ? r.completed_qty : (r.quantity || 0);
    });
    return init;
  });
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);

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

  const totalPairs = group.rows?.reduce((s, r) => s + (r.quantity || 0), 0) || 0;
  const sizes = group.rows?.map(r => r.size).join(", ") || "";
  const poId = group.po_id || group.rows?.[0]?.po_id || "";
  const jobIds = useMemo(() => group.rows?.map(r => r.id).filter(Boolean) || [], [group.rows]);

  const totalDispatchPairs = useMemo(() => {
    return (group.rows || []).reduce((acc, r) => {
      const q = dispatchQuantities[r.id];
      return acc + (q !== "" && q !== undefined ? Number(q) : (r.completed_qty || r.quantity || 0));
    }, 0);
  }, [group.rows, dispatchQuantities]);

  const handleDispatch = useCallback(async () => {
    if (!poId) { setErr("Cannot find PO for this group — contact admin."); return; }
    if (!jobIds.length) { setErr("No job IDs available."); return; }
    setLoading(true); setErr(null);
    try {
      const payload = {
        job_ids: jobIds,
        po_id: poId,
        dispatch_quantities: Object.fromEntries(
          Object.entries(dispatchQuantities).map(([k, v]) => [k, v === "" ? 0 : Number(v)])
        ),
        ...form,
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
  }, [form, poId, jobIds, dispatchQuantities, load]);

  const Field = ({ label, children }) => (
    <div className="space-y-1">
      <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-500">{label}</label>
      {children}
    </div>
  );
  const ic = "w-full border border-slate-300 px-2.5 py-2.5 text-sm text-slate-800 focus:border-[#0D9488] outline-none min-h-[44px]";

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4">
      <div className="bg-white shadow-2xl w-full sm:max-w-xl flex flex-col max-h-[100dvh]">
        {/* Header */}
        <div className="bg-[#0D9488] px-6 py-4 shrink-0 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-teal-100 font-bold">Generate Dispatch Documents</div>
            <div className="text-white font-bold text-lg mt-0.5">{group.style_code} · {group.color}</div>
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
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">Dispatch Summary</div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div><div className="text-2xl font-black text-teal-700" data-testid="dispatch-total-pairs">{totalDispatchPairs}</div><div className="text-[10px] text-slate-400 uppercase">Dispatch Pairs</div></div>
              <div><div className="text-2xl font-black text-[#0F172A]">{jobIds.length}</div><div className="text-[10px] text-slate-400 uppercase">Job Lines</div></div>
              <div><div className="text-sm font-bold text-[#0F172A]">{sizes || "—"}</div><div className="text-[10px] text-slate-400 uppercase">Sizes</div></div>
            </div>
            <p className="mt-3 pt-3 border-t border-slate-200 text-[11px] text-slate-500">
              Box numbers assigned 1..N (sorted by size). Invoice uses actual packed qty from carton rows.
            </p>
          </div>

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

            <div className="space-y-2">
              {(group.rows || []).map((r) => {
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
              })}
            </div>
          </div>

          {/* Shipping fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Transport Mode"><input className={ic} value={form.transport_mode} placeholder="By Road" onChange={e => set("transport_mode", e.target.value)} /></Field>
            <Field label="Vehicle No."><input className={ic} value={form.vehicle_no} placeholder="MH-01-AB-1234" onChange={e => set("vehicle_no", e.target.value)} /></Field>
            <Field label="Transporter"><input className={ic} value={form.transporter} placeholder="Transporter name" onChange={e => set("transporter", e.target.value)} /></Field>
            <Field label="Supply / Dispatch Date"><input type="date" className={ic} value={form.supply_date} onChange={e => set("supply_date", e.target.value)} /></Field>
            <Field label="Carton Dimensions"><input className={ic} value={form.carton_dim} placeholder="60x50x30 CMS" onChange={e => set("carton_dim", e.target.value)} /></Field>
            <Field label="Net Wt/Carton (kg)"><input type="number" className={ic} value={form.net_wt_per_carton} placeholder="10.8" inputMode="decimal" onChange={e => set("net_wt_per_carton", e.target.value)} /></Field>
            <Field label="Gross Wt/Carton (kg)"><input type="number" className={ic} value={form.gross_wt_per_carton} placeholder="12.0" inputMode="decimal" onChange={e => set("gross_wt_per_carton", e.target.value)} /></Field>
            <Field label="Notes"><input className={ic} value={form.notes} placeholder="Optional" onChange={e => set("notes", e.target.value)} /></Field>
          </div>

          {err && <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded">{err}</div>}
          {done && (
            <div className="bg-teal-50 border border-teal-200 text-teal-800 text-sm px-4 py-4 rounded space-y-3">
              <div>
                <div className="font-bold">✅ Dispatched — Invoice {done.invoice_no}</div>
                <div className="text-xs text-teal-700 mt-1">ZIP downloaded. Re-download individual documents:</div>
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
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-50 border-t border-slate-200 px-6 py-4 flex items-center justify-between shrink-0">
          <button onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 font-medium">{done ? "Close" : "Cancel"}</button>
          {!done && (
            <button type="button" disabled={loading || !poId} onClick={handleDispatch} data-testid="dispatch-confirm-btn"
              className="px-6 py-2.5 bg-[#0D9488] hover:bg-[#0B7A70] text-white font-bold uppercase tracking-wider text-xs shadow-md disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2">
              {loading
                ? <><svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> Generating…</>
                : <><FileDown className="w-4 h-4" /> Generate &amp; Download ZIP</>
              }
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
