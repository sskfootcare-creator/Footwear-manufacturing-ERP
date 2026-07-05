import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { http } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { useAuth } from "../lib/auth";
import { FileDown, Check, UserPlus, Edit3, ClipboardList, X, HardHat, GripVertical, Printer, MessageCircle, AlertTriangle, Clock, Package, Archive, Eye, CheckCircle } from "lucide-react";

const STAGES = [
  { key: "procurement", label: "Procurement", color: "#64748B" },
  { key: "cutting", label: "Cutting", color: "#2563EB" },
  { key: "folding", label: "Folding", color: "#0284C7" },
  { key: "attachment", label: "Attachment", color: "#7C3AED" },
  { key: "stitching", label: "Stitching", color: "#C27842" },
  { key: "lasting", label: "Lasting", color: "#A65D24" },
  { key: "sole_pasting", label: "Sole Pasting", color: "#F59E0B" },
  { key: "finishing", label: "Finish / QC / Pack", color: "#16A34A" },
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
        key, po_number: j.po_number, po_id: j.po_id, style_code: j.style_code,
        client_name: j.client_name, description: j.description, delivery_date: j.delivery_date,
        color, rows: [], sizes: new Set(),
      };
    }
    groups[key].rows.push(j);
    groups[key].sizes.add(String(j.size || "—"));
  }
  return Object.values(groups).map(g => ({
    ...g,
    sizes: Array.from(g.sizes).sort(sortSizes),
    totalQty: g.rows.reduce((s, r) => s + (r.quantity || 0), 0),
    components: aggregateComponents(g.rows),
    assignments: aggregateAssignments(g.rows),
    overdueHours: aggregateOverdue(g.rows),
  }));
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
  const [savedPackingLists, setSavedPackingLists] = useState([]);
  const { user } = useAuth();
  const canEdit = ["admin", "manager", "production"].includes(user?.role);

  const load = async () => {
    const [j, w, s, ar, pl] = await Promise.all([
      http.get("/production/jobs"),
      http.get("/workers"),
      http.get("/styles"),
      http.get("/production/archive"),
      http.get("/packing-lists"),
    ]);
    setJobs(j.data); setWorkers(w.data); setStyles(s.data);
    setArchivedJobs(ar.data); setSavedPackingLists(pl.data || []);
  };
  useEffect(() => { load(); }, []);

  const styleByCode = useMemo(() => {
    const m = {};
    for (const s of styles) m[s.code] = s;
    return m;
  }, [styles]);

  const printCard = async (group) => {
    try {
      const res = await http.post("/production/card.pdf",
        { job_ids: group.rows.map(r => r.id) }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Print failed: " + (e.response?.data?.detail || e.message)); }
  };

  // Open packing list modal for a single group OR a merged set of jobs.
  const openPackingForGroup = (group) => setPackingFor({ kind: "single", group });
  const openPackingMerged = () => {
    const groupsArr = Object.values(selected);
    if (!groupsArr.length) return;
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
      alert("Packing list failed: " + (e.response?.data?.detail || e.message));
    }
  };

  const triggerDownload = (blobData, filename) => {
    const blob = new Blob([blobData], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
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
      const res = await http.post("/production/card.pdf",
        { job_ids: group.rows.map(r => r.id) }, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      // trigger download with a descriptive filename
      const a = document.createElement("a");
      a.href = url;
      a.download = `ProductionCard_${group.po_number}_${group.style_code}_${(group.color || "color").replace(/\s+/g, "")}.pdf`;
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
    const next = { ...s }; if (next[group.key]) delete next[group.key]; else next[group.key] = group; return next;
  });
  const downloadGroupInvoice = async (group) => {
    try {
      const res = await http.post("/invoices/job", { po_id: group.po_id, job_ids: group.rows.map(r => r.id) }, { responseType: "blob" });
      window.open(URL.createObjectURL(new Blob([res.data], { type: "application/pdf" })), "_blank");
    } catch (e) { alert("Invoice failed: " + (e.response?.data?.detail || e.message)); }
  };
  const downloadMergedInvoice = async () => {
    const groups = Object.values(selected); if (!groups.length) return;
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
    } catch (e) { alert("Material requirement failed: " + (e.response?.data?.detail || e.message)); }
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
  const onDropStage = (stageKey, stageJobs) => (e) => {
    e.preventDefault();
    const role = STAGE_TO_ROLE[stageKey];
    if (!role || !draggingWorker || !stageJobs.length) { setDropZone(null); return; }
    setBulkConfirm({
      worker: draggingWorker, role, stageKey,
      job_ids: stageJobs.map(j => j.id),
      stage_label: STAGES.find(s => s.key === stageKey)?.label || stageKey,
      card_count: groupJobsByColor(stageJobs).length,
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
                className={`text-xs font-bold uppercase tracking-wider px-3 py-2 border-2 ${dockOpen ? "bg-[#C27842] text-white border-[#C27842]" : "bg-white text-slate-900 border-slate-300 hover:border-[#0F172A]"}`}>
                <HardHat className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Karigars
              </button>
            )}
            <button onClick={() => setViewArchive(v => !v)} data-testid="toggle-archive"
              className={`text-xs font-bold uppercase tracking-wider px-3 py-2 border-2 ${viewArchive ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white text-slate-900 border-slate-300 hover:border-[#0F172A]"}`}>
              <Archive className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Archive ({groupJobsByColor(archivedJobs).length})
            </button>
            {procSelectedCount > 0 && (
              <>
                <BtnPrimary onClick={() => { downloadMaterialRequirement(Object.values(procSelected), `${procSelectedCount} procurement cards`); setProcSelected({}); }} data-testid="merged-mr-btn">
                  <ClipboardList className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Material Requirement ({procSelectedCount})
                </BtnPrimary>
                <BtnSecondary onClick={() => checkShortage(Object.values(procSelected))} data-testid="check-shortage-btn" className="!bg-amber-50 hover:!bg-amber-100 border-amber-300 text-amber-900">
                  <AlertTriangle className="w-3.5 h-3.5 inline -mt-0.5 mr-1 text-amber-600 animate-pulse" /> Check Shortage ({procSelectedCount})
                </BtnSecondary>
              </>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={downloadMergedInvoice} disabled={merging} data-testid="merged-invoice-btn">
                <FileDown className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                {merging ? "..." : `Merge Invoice (${dispatchedCount})`}
              </BtnPrimary>
            )}
            {dispatchedCount > 0 && (
              <BtnPrimary onClick={openPackingMerged} data-testid="merged-packing-btn"
                className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]">
                <Package className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                Merge Packing ({dispatchedCount})
              </BtnPrimary>
            )}
          </div>
        }
      />

      <div className="p-8">
        {viewArchive ? (
          <ArchivePanel
            jobs={archivedJobs}
            styleByCode={styleByCode}
            onPrint={printCard}
            onPacking={openPackingForGroup}
            onViewDetails={(g) => setDetailFor(g)}
            savedPackingLists={savedPackingLists}
            onReDownloadPacking={reDownloadSavedPacking}
          />
        ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {STAGES.map((s) => {
              const stageJobs = jobs.filter((j) => j.stage === s.key);
              const groups = groupJobsByColor(stageJobs);
              const totalQty = stageJobs.reduce((sum, j) => sum + j.quantity, 0);
              const isProc = s.key === "procurement";
              const isDisp = s.key === "dispatched";
              return (
                <div key={s.key} className="w-[400px] flex-shrink-0" data-testid={`column-${s.key}`}>
                  <div
                    className={`bg-white border-2 mb-3 p-3 transition-all ${dropZone === s.key ? "border-[#C27842] bg-orange-50 shadow-ind" : "border-slate-200"} border-t-4`}
                    style={{ borderTopColor: s.color }}
                    onDragOver={STAGE_TO_ROLE[s.key] ? onDragOverStage(s.key) : undefined}
                    onDragLeave={() => setDropZone(null)}
                    onDrop={STAGE_TO_ROLE[s.key] ? onDropStage(s.key, stageJobs) : undefined}
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
                        onMove={moveGroup}
                        onToggleComponent={toggleComponent}
                        onOpenAssign={(role) => setAssignFor({ group: g, role })}
                        onOpenQty={(rowId) => setQtyFor({ group: g, rowId })}
                        onPrint={() => printCard(g)}
                        onWhatsApp={() => setWaFor({ group: g })}
                        onPacking={() => openPackingForGroup(g)}
                        isProc={isProc}
                        isDispatched={isDisp}
                        onMatReq={() => downloadMaterialRequirement([g], `${g.style_code} · ${g.color}`)}
                        procSelected={!!procSelected[g.key]}
                        onToggleProcSelect={toggleProcSelect}
                        onDownloadInvoice={downloadGroupInvoice}
                        isSelected={!!selected[g.key]}
                        onToggleSelect={toggleSelect}
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

      {packingFor && (
        <PackingListDialog
          payload={packingFor}
          onClose={() => setPackingFor(null)}
          onSubmit={submitPacking}
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
    procSelected, onToggleProcSelect, isSelected, onToggleSelect, onDownloadInvoice } = props;
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
            {group.overdueHours >= 24 ? `${(group.overdueHours / 24).toFixed(1)} d late` : `${group.overdueHours.toFixed(1)} h late`}
          </span>
        </div>
      )}
      {consumeError && (
        <div className="bg-amber-600 text-white px-3 py-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold animate-pulse" data-testid={`consume-error-${group.key}`}>
          <AlertTriangle className="w-3 h-3" />
          <span>⚠ {consumeError.inventory_consume_error}</span>
        </div>
      )}
      {style?.image_url && (
        <div className="h-28 bg-slate-100 border-b border-slate-200 overflow-hidden">
          <img src={style.image_url} alt={style.name} className="w-full h-full object-cover" data-testid={`card-img-${group.key}`} />
        </div>
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
              <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(group)} className="w-4 h-4 accent-[#C27842]" data-testid={`select-${group.key}`} />
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
              <th className="px-2 py-1 text-left text-[10px] uppercase tracking-wider font-bold text-slate-600 border-r border-slate-200">Size</th>
              {group.sizes.map(sz => (
                <th key={sz} className="px-2 py-1 text-center font-mono text-[11px] font-bold text-slate-700 border-r border-slate-200 last:border-r-0">{sz}</th>
              ))}
              <th className="px-2 py-1 text-right text-[10px] uppercase tracking-wider font-bold text-slate-900 bg-slate-100">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-200">
              <td className="px-2 py-1.5 font-bold text-slate-700 border-r border-slate-200">{group.color}</td>
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
        <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-slate-500 mb-1.5">Components</div>
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
            <button onClick={() => onDownloadInvoice(group)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#C27842] hover:bg-[#A65D24] px-3 py-1 flex items-center gap-1" data-testid={`invoice-btn-${group.key}`}>
              <FileDown className="w-3 h-3" /> Invoice
            </button>
          )}
          {isDispatched && (
            <button onClick={onPacking} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#16A34A] hover:bg-[#0F7A36] px-3 py-1 flex items-center gap-1" data-testid={`packing-btn-${group.key}`}>
              <Package className="w-3 h-3" /> Packing List
            </button>
          )}
          {canEdit && prevStage && (
            <button disabled={!effectiveCanEdit} onClick={() => onMove(group, prevStage.key)} className={`text-[10px] uppercase tracking-wider font-bold border px-2 py-1 ${effectiveCanEdit ? 'text-slate-500 hover:text-slate-900 border-slate-300' : 'text-slate-300 border-slate-200 cursor-not-allowed'}`}>← {prevStage.label}</button>
          )}
          {canEdit && nextStage && (
            <button disabled={!effectiveCanEdit} onClick={() => onMove(group, nextStage.key)} className={`text-[10px] uppercase tracking-wider font-bold text-white px-3 py-1 ${effectiveCanEdit ? 'bg-[#0F172A] hover:bg-[#C27842]' : 'bg-slate-300 cursor-not-allowed'}`} data-testid={`move-next-${group.key}`}>{nextStage.label} →</button>
          )}
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
  const onPickWorker = (w) => {
    setSelectedWid(w.id);
    if (rate === "" || rate === null || rate === undefined) setRate(w.rate_per_pair);
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" data-testid="assign-dialog">
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Assign Karigar</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · {roleObj?.label}</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 max-h-[55vh] overflow-y-auto">
          {sorted.length === 0 ? (
            <div className="text-center text-sm text-slate-500 py-8">No karigars yet.</div>
          ) : (
            <div className="space-y-1.5">
              <button
                onClick={() => onSave(null, null)}
                data-testid="assign-clear"
                className="w-full text-left px-3 py-2 border border-slate-200 hover:border-red-500 hover:text-red-700 text-xs font-bold uppercase tracking-wider"
              >
                ✕ Unassign
              </button>
              {sorted.map(w => (
                <button
                  key={w.id}
                  onClick={() => onPickWorker(w)}
                  data-testid={`assign-worker-${w.id}`}
                  className={`w-full text-left px-3 py-2 border ${selectedWid === w.id ? "border-[#C27842] bg-orange-50" : "border-slate-200"} hover:border-[#0F172A] flex items-center justify-between`}
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
                className="w-full mt-1 border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#C27842] focus:outline-none"
              />
              <div className="text-[10px] text-slate-500 mt-1">
                Different styles can have different rates per role. This is the negotiated rate for this card.
              </div>
            </div>
            <div className="flex gap-2">
              <BtnPrimary onClick={() => onSave(selectedWid, rate === "" ? null : rate)} data-testid="assign-save">
                <Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Assign at ₹{rate || selectedWorker?.rate_per_pair || 0}/pair
              </BtnPrimary>
              <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
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
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Edit Quantity</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · Size {row?.size}</div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Stage: {row?.stage}</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Planned Qty (pairs)</label>
            <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} data-testid="qty-input-planned"
              className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#2563EB] focus:outline-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Completed</label>
              <input type="number" value={completed} onChange={(e) => setCompleted(e.target.value)} data-testid="qty-input-completed"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono focus:border-[#16A34A] focus:outline-none" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Rejected</label>
              <input type="number" value={rejected} onChange={(e) => setRejected(e.target.value)} data-testid="qty-input-rejected"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono focus:border-red-500 focus:outline-none" />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Reason (optional)</label>
            <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="e.g., 5 pairs damaged in cutting"
              className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none" />
          </div>
          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary onClick={save} data-testid="qty-save"><Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
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
      <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-lg">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between" style={{ background: "#25D366", color: "white" }}>
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">Share via WhatsApp</div>
            <div className="font-bold text-base">{group.style_code} · {group.color} · {group.totalQty} pairs</div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/20"><X className="w-5 h-5" /></button>
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
                    className={`w-full flex items-center justify-between px-3 py-2 border-2 text-left ${picked === w.id ? "border-[#25D366] bg-green-50" : "border-slate-200 hover:border-slate-400"}`}>
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
function ArchivePanel({ jobs, styleByCode, onPrint, onPacking, onViewDetails, savedPackingLists, onReDownloadPacking }) {
  const groups = groupJobsByColor(jobs);
  return (
    <div className="space-y-5" data-testid="archive-list">
      <Card className="bg-slate-50 border-2 border-slate-200 p-4">
        <div className="flex items-baseline justify-between">
          <div>
            <h2 className="text-lg font-bold flex items-center gap-2"><Archive className="w-4 h-4 text-slate-700" /> Archived Production Cards</h2>
            <p className="text-xs text-slate-600 mt-1">Cards that have both invoice + packing list generated land here. Click <b>View details</b> to inspect full production history.</p>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            {groups.length} group{groups.length !== 1 ? "s" : ""} · {jobs.length} job{jobs.length !== 1 ? "s" : ""}
          </div>
        </div>
      </Card>

      {groups.length === 0 ? (
        <Card className="p-12 text-center text-slate-400 text-sm" data-testid="archive-empty">
          Nothing archived yet — once both <b>Invoice</b> and <b>Packing List</b> are generated for a card it moves here automatically.
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="archive-grid">
          {groups.map(g => (
            <Card key={g.key} className="border-l-4 border-slate-400 hover:border-[#0F172A] transition-colors" data-testid={`archive-card-${g.key}`}>
              {styleByCode[g.style_code]?.image_url && (
                <div className="h-32 overflow-hidden bg-slate-100">
                  <img src={styleByCode[g.style_code].image_url} alt="" className="w-full h-full object-cover" />
                </div>
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
                  <button onClick={() => onViewDetails(g)} className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#2563EB] hover:bg-[#1E40AF] px-2 py-1 flex items-center gap-1" data-testid={`archive-details-${g.key}`}>
                    <Eye className="w-3 h-3" /> View details
                  </button>
                  <button onClick={() => onPrint(g)} className="text-[10px] uppercase tracking-wider font-bold text-slate-700 border border-slate-300 hover:bg-slate-900 hover:text-white px-2 py-1 flex items-center gap-1">
                    <Printer className="w-3 h-3" /> Card PDF
                  </button>
                  <button onClick={() => onPacking(g)} className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-2 py-1 flex items-center gap-1">
                    <Package className="w-3 h-3" /> Packing
                  </button>
                </div>
              </div>
            </Card>
          ))}
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
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-4 py-2 font-bold">When</th>
                <th className="px-4 py-2 font-bold">PO #(s)</th>
                <th className="px-4 py-2 font-bold">Client</th>
                <th className="px-4 py-2 font-bold">Type</th>
                <th className="px-4 py-2 font-bold">Notes</th>
                <th className="px-4 py-2 font-bold text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {savedPackingLists.map(pl => (
                <tr key={pl.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`saved-pl-${pl.id}`}>
                  <td className="px-4 py-2 font-mono text-[11px] text-slate-700 whitespace-nowrap">
                    {pl.created_at ? new Date(pl.created_at).toLocaleString("en-IN", { hour12: false }) : "—"}
                  </td>
                  <td className="px-4 py-2 font-mono font-bold">
                    {pl.merged ? (pl.po_numbers || []).join(" + ") : pl.po_number}
                  </td>
                  <td className="px-4 py-2 text-xs">{pl.client_name || "—"}</td>
                  <td className="px-4 py-2">
                    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 ${pl.merged ? "bg-[#0F172A] text-white" : "bg-slate-100 text-slate-700"}`}>
                      {pl.merged ? "MERGED" : "SINGLE"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-600 max-w-md truncate">
                    {pl.options?.notes || pl.options?.transporter || "—"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button onClick={() => onReDownloadPacking(pl)} className="text-[10px] uppercase tracking-wider font-bold text-[#16A34A] border border-[#16A34A] hover:bg-[#16A34A] hover:text-white px-2 py-1" data-testid={`redownload-pl-${pl.id}`}>
                      <FileDown className="w-3 h-3 inline -mt-0.5 mr-1" /> Re-download
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
                  <th className="px-3 py-2 font-bold">Karigar</th>
                  <th className="px-3 py-2 font-bold text-right">Rate / Pair</th>
                </tr>
              </thead>
              <tbody>
                {ASSIGNMENT_ROLES.map(role => {
                  const a = group.assignments?.[role.key];
                  return (
                    <tr key={role.key} className="border-t border-slate-200">
                      <td className="px-3 py-2 font-bold uppercase text-[10px] tracking-wider">{role.label}</td>
                      <td className="px-3 py-2">{a?.worker_name || "—"}</td>
                      <td className="px-3 py-2 text-right font-mono">{a?.rate_per_pair != null ? `₹${a.rate_per_pair}` : "—"}</td>
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
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="packing-dialog">
      <div className="bg-white w-full max-w-3xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
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
            <Field label="Pcs / Carton">
              <input type="number" min="1" value={form.pcs_per_box} onChange={e => set("pcs_per_box", Number(e.target.value))}
                data-testid="pl-pcs-per-box" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
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
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">{children}</div>
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
                        <th className="px-4 py-2">Code</th>
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
                          <td className="px-4 py-2.5 font-mono font-bold">{item.code}</td>
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
