import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { http } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Upload, ShoppingBag, RefreshCw, FileWarning, Settings2,
  ChevronLeft, PlayCircle, CheckCircle2, AlertTriangle, Truck, ScrollText,
} from "lucide-react";
import { Link } from "react-router-dom";

const CHANNEL_COLORS = {
  myntra:   "pink",
  flipkart: "blue",
  nykaa:    "orange",
  ajio:     "purple",
  amazon:   "yellow",
  website:  "slate",
};

const STATUS_COLORS = {
  matched: "green",
  mapped:  "blue",
  unmatched: "red",
};

// ═══════════════════════════════════════════════════════════════════════
// Import Drawer — config-driven (Phase G)
//
// Flow:
//   1. Choose platform (dropdown driven by /order-import-format-configs)
//   2. Pick file → PREVIEW (dry_run=true) shows canonical rows, distinguishing
//      "order rows" (have order_id) from "picklist rows" (Myntra-style, no
//      order_id) and highlighting unmatched rows that will go to the
//      exception queue.
//   3. Confirm → COMMIT (dry_run=false) writes online_orders /
//      online_order_items / online_order_exceptions.
//
// If the platform has no config yet, the drawer surfaces a CTA linking to
// /order-import-formats so the admin can onboard it without a code change.
// ═══════════════════════════════════════════════════════════════════════
function ImportDrawer({ onClose, onDone }) {
  const [configs, setConfigs]     = useState(null); // null = still loading
  const [platform, setPlatform]   = useState("");
  const [file, setFile]           = useState(null);
  const [step, setStep]           = useState("choose"); // choose | preview | done
  const [preview, setPreview]     = useState(null);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [committed, setCommitted] = useState(null);
  const [error, setError]         = useState("");
  const fileRef = useRef();

  useEffect(() => {
    (async () => {
      try {
        const r = await http.get("/order-import-format-configs?active=true");
        setConfigs(r.data || []);
        if (r.data?.length) setPlatform(r.data[0].platform);
      } catch (e) {
        setConfigs([]);
      }
    })();
  }, []);

  const selectedCfg = useMemo(
    () => (configs || []).find((c) => c.platform === platform) || null,
    [configs, platform]
  );

  async function runPreview() {
    setError("");
    if (!file) return setError("Please select a file.");
    if (!platform) return setError("Please choose a platform.");
    setPreviewing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/import-configured?platform=${encodeURIComponent(platform)}&dry_run=true`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      setPreview(r.data);
      setStep("preview");
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Preview failed."));
    } finally {
      setPreviewing(false);
    }
  }

  async function runCommit() {
    setError("");
    setCommitting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/import-configured?platform=${encodeURIComponent(platform)}&dry_run=false`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      setCommitted(r.data);
      setStep("done");
      onDone();
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Import failed."));
    } finally {
      setCommitting(false);
    }
  }

  function reset() {
    setPreview(null);
    setCommitted(null);
    setStep("choose");
    setError("");
  }

  const noConfigs = configs !== null && configs.length === 0;

  return (
    <Drawer
      onClose={onClose}
      title={
        step === "choose"  ? "Import orders — step 1: choose file" :
        step === "preview" ? "Import orders — step 2: review & commit" :
                             "Import orders — done"
      }
      width="max-w-4xl"
    >
      <div className="space-y-5">

        {/* ── No configs yet ─────────────────────────────────────── */}
        {noConfigs && step === "choose" && (
          <div className="bg-amber-50 border-2 border-amber-300 px-4 py-4 text-sm text-amber-900">
            <div className="font-bold mb-1 flex items-center gap-2">
              <FileWarning className="w-4 h-4" /> No order-import formats configured yet.
            </div>
            <div className="text-xs mb-3">
              Every platform's order or picklist file format is stored as one config row —
              adding a new marketplace does NOT require a code change.
            </div>
            <Link to="/order-import-formats" onClick={onClose}>
              <BtnPrimary>
                <span className="flex items-center gap-2">
                  <Settings2 className="w-4 h-4" /> Configure a platform
                </span>
              </BtnPrimary>
            </Link>
          </div>
        )}

        {/* ── STEP 1: choose ─────────────────────────────────────── */}
        {step === "choose" && configs && configs.length > 0 && (
          <>
            <div className="bg-blue-50 border-2 border-blue-200 px-4 py-3 text-sm text-blue-900">
              <div className="font-bold mb-1">Config-driven order/picklist import</div>
              <div className="text-xs">
                The platform dropdown drives which config row is used. Adding a 4th/5th
                platform's format is a{" "}
                <Link to="/order-import-formats" className="underline font-bold">
                  new config row
                </Link>
                , not new code. Files that resolve cleanly become <span className="font-semibold">online_orders</span>{" "}
                / <span className="font-semibold">online_order_items</span>; rows that don't resolve go to
                the same exception queue used everywhere else.
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Select label="Platform *" id="import-platform" value={platform}
                onChange={(e) => setPlatform(e.target.value)}>
                {configs.map((c) => (
                  <option key={c.platform} value={c.platform}>
                    {c.platform.charAt(0).toUpperCase() + c.platform.slice(1)}
                    {c.is_picklist ? "  (picklist)" : "  (order)"}
                  </option>
                ))}
              </Select>

              {selectedCfg && (
                <div className="pt-6 text-xs space-y-1">
                  <div>
                    <span className="text-neutral-500">Type:</span>{" "}
                    {selectedCfg.is_picklist ? (
                      <Badge color="purple">picklist (batch, no order_id)</Badge>
                    ) : (
                      <Badge color="blue">order</Badge>
                    )}
                  </div>
                  <div className="font-mono text-[11px] text-neutral-600">
                    leaf_sku column: {selectedCfg.column_map?.leaf_sku || "—"}
                  </div>
                  {(selectedCfg.known_sku_prefixes_to_strip || []).length > 0 && (
                    <div className="font-mono text-[11px] text-amber-700">
                      strips prefixes: {(selectedCfg.known_sku_prefixes_to_strip || []).join(", ")}
                    </div>
                  )}
                  {Object.keys(selectedCfg.known_sku_prefix_replacements || {}).length > 0 && (
                    <div className="font-mono text-[11px] text-purple-700">
                      replaces: {Object.entries(selectedCfg.known_sku_prefix_replacements || {}).map(([k, v]) => `${k}→${v}`).join(", ")}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* File picker */}
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">File *</div>
              <div
                className="border-2 border-dashed border-slate-300 hover:border-slate-500 px-4 py-6 text-center cursor-pointer transition-colors"
                onClick={() => fileRef.current?.click()}
                data-testid="oo-import-file-drop"
              >
                <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
                {file
                  ? <div className="text-sm font-mono font-bold text-slate-700">{file.name}</div>
                  : <div className="text-sm text-slate-500">Click to choose .csv / .xlsx</div>}
              </div>
              <input ref={fileRef} type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="hidden"
                onChange={(e) => setFile(e.target.files[0] || null)} />
              {selectedCfg?.is_picklist && file && (
                <div className="text-[11px] text-purple-700 mt-1">
                  Picklist mode: filename stem <span className="font-mono font-bold">{file.name.replace(/\.[^.]+$/, "")}</span> will be stored as <span className="font-mono">picklist_batch_id</span>.
                </div>
              )}
            </div>

            {error && (
              <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold whitespace-pre-line">
                {error}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <BtnPrimary id="btn-preview-import" onClick={runPreview}
                disabled={previewing || !file} className="flex-1">
                <span className="flex items-center justify-center gap-2">
                  <PlayCircle className="w-4 h-4" />
                  {previewing ? "Parsing preview…" : "Preview import"}
                </span>
              </BtnPrimary>
              <BtnSecondary onClick={onClose} disabled={previewing}>Cancel</BtnSecondary>
            </div>
          </>
        )}

        {/* ── STEP 2: preview + commit ───────────────────────────── */}
        {step === "preview" && preview && (
          <PreviewPanel
            preview={preview}
            error={error}
            committing={committing}
            onBack={() => { setStep("choose"); setPreview(null); }}
            onCommit={runCommit}
          />
        )}

        {/* ── STEP 3: done ───────────────────────────────────────── */}
        {step === "done" && committed && (
          <div className="space-y-3">
            <div className="bg-green-50 border-2 border-green-300 px-4 py-4 text-sm text-green-900">
              <div className="font-bold flex items-center gap-2 text-base mb-1">
                <CheckCircle2 className="w-5 h-5" /> Import committed
              </div>
              <div className="text-xs font-mono mb-1">batch: {committed.import_batch_id}</div>
              <div className="grid grid-cols-3 gap-2 mt-3">
                <MiniStat label="orders" value={committed.committed?.orders_created ?? 0} accent="#0F172A" />
                <MiniStat label="items"  value={committed.committed?.items_created  ?? 0} accent="#C27842" />
                <MiniStat label="exceptions" value={committed.committed?.exceptions_queued ?? 0} accent="#DC2626" />
              </div>
            </div>
            <div className="flex gap-3">
              <BtnSecondary onClick={reset}>
                <ChevronLeft className="w-4 h-4 mr-1.5" /> Import another
              </BtnSecondary>
              <BtnPrimary onClick={onClose} className="flex-1">Close</BtnPrimary>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}

function MiniStat({ label, value, accent }) {
  return (
    <div className="border-2 border-neutral-200 bg-white px-3 py-2 relative overflow-hidden">
      <div className="absolute left-0 top-0 bottom-0 w-1" style={{ background: accent }} />
      <div className="text-[9px] uppercase tracking-wider font-bold text-slate-500">{label}</div>
      <div className="font-mono text-xl font-bold">{value}</div>
    </div>
  );
}

function PreviewPanel({ preview, error, committing, onBack, onCommit }) {
  const rows = preview.rows || [];
  const stats = preview.stats || {};
  const isPicklist = !!preview.is_picklist;

  return (
    <div className="space-y-4">
      {/* Header meta */}
      <div className="bg-slate-50 border-2 border-slate-200 px-4 py-3 text-xs text-slate-800 font-mono space-y-1">
        <div>platform: <span className="font-bold">{preview.platform}</span></div>
        <div>file: {preview.filename}</div>
        {isPicklist && (
          <div className="text-purple-700">
            picklist_batch_id (from filename): <span className="font-bold">{preview.picklist_batch_id}</span>
          </div>
        )}
        <div>header row (1-based): {preview.header_row_1_based}</div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        <MiniStat label="total"       value={stats.total_rows_read     ?? 0} accent="#0F172A" />
        <MiniStat label="matched"     value={stats.matched             ?? 0} accent="#16A34A" />
        <MiniStat label="unmatched"   value={stats.unmatched           ?? 0} accent="#DC2626" />
        <MiniStat label="order rows"  value={stats.order_style_rows    ?? 0} accent="#2563EB" />
        <MiniStat label="picklist rows" value={stats.picklist_rows     ?? 0} accent="#7C3AED" />
        <MiniStat label="distinct orders" value={stats.distinct_orders ?? 0} accent="#C27842" />
      </div>

      {(stats.derivation_failed > 0 || stats.empty_leaf_sku > 0) && (
        <div className="bg-amber-50 border-2 border-amber-300 px-4 py-2 text-xs text-amber-900 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            {stats.derivation_failed > 0 && <span className="mr-3">group_id derivation failed on <b>{stats.derivation_failed}</b> row(s).</span>}
            {stats.empty_leaf_sku > 0 && <span>empty leaf_sku on <b>{stats.empty_leaf_sku}</b> row(s).</span>}
            <span> These will go to the exception queue.</span>
          </div>
        </div>
      )}

      {/* Row preview table */}
      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[420px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2 border-b">Row #</th>
                <th className="text-left p-2 border-b">Type</th>
                <th className="text-left p-2 border-b">Order / Batch</th>
                <th className="text-left p-2 border-b">Raw leaf_sku</th>
                <th className="text-left p-2 border-b">Group → size</th>
                <th className="text-left p-2 border-b">Style code</th>
                <th className="text-right p-2 border-b">Qty</th>
                <th className="text-left p-2 border-b">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 300).map((r, i) => {
                const isOrderRow    = !!r.order_id;
                const isPicklistRow = !isOrderRow;
                const matched       = !!r.matched;
                return (
                  <tr key={i} className={`border-b border-neutral-100 ${!matched ? "bg-red-50/40" : "hover:bg-slate-50"}`}>
                    <td className="p-2 font-mono">{r.source_row_index}</td>
                    <td className="p-2">
                      {isOrderRow
                        ? <Badge color="blue">order</Badge>
                        : <Badge color="purple">picklist</Badge>}
                    </td>
                    <td className="p-2 font-mono">
                      {isOrderRow
                        ? r.order_id
                        : <span className="text-purple-700">{r.picklist_batch_id || "—"}</span>}
                    </td>
                    <td className="p-2 font-mono">
                      {r.leaf_sku_raw || "—"}
                      {r.leaf_sku_replaced_prefix && (
                        <span className="ml-1 text-[9px] text-purple-800 bg-purple-100 border border-purple-300 rounded px-1">
                          {r.leaf_sku_replaced_prefix}→fix
                        </span>
                      )}
                      {r.leaf_sku_stripped_prefix && (
                        <span className="ml-1 text-[9px] text-amber-700 bg-amber-100 border border-amber-300 rounded px-1">
                          -{r.leaf_sku_stripped_prefix}
                        </span>
                      )}
                    </td>
                    <td className="p-2 font-mono text-[11px]">
                      {r.group_id || "—"}{" → "}{r.derived_size || r.size || "—"}
                    </td>
                    <td className="p-2 font-mono">{r.style_code || "—"}</td>
                    <td className="p-2 font-mono text-right">{r.qty}</td>
                    <td className="p-2">
                      {matched ? (
                        <Badge color="green">
                          {r.match_via || "matched"}
                        </Badge>
                      ) : (
                        <div className="text-red-700 text-[10px] leading-tight">
                          <Badge color="red">exception</Badge>
                          <div className="mt-1 max-w-[220px]">{r.exception_reason}</div>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {rows.length > 300 && (
                <tr>
                  <td colSpan={8} className="p-3 text-center text-xs text-slate-500 italic">
                    Showing first 300 of {rows.length} rows. All rows will be committed.
                  </td>
                </tr>
              )}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-sm text-slate-400 italic">
                    No rows parsed — check header row + column map.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold whitespace-pre-line">
          {error}
        </div>
      )}

      <div className="flex gap-3 pt-2 border-t border-slate-200">
        <BtnSecondary onClick={onBack} disabled={committing}>
          <ChevronLeft className="w-4 h-4 mr-1.5" /> Back
        </BtnSecondary>
        <BtnPrimary onClick={onCommit} disabled={committing || rows.length === 0} className="flex-1">
          <span className="flex items-center justify-center gap-2">
            <Upload className="w-4 h-4" />
            {committing ? "Committing…" :
             `Commit ${rows.length} row${rows.length !== 1 ? "s" : ""} → online_orders`}
          </span>
        </BtnPrimary>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Dispatch Import Drawer — daily "what got packed today" (Phase H)
//
// Different from ImportDrawer because:
//   - Uses /online-orders/dispatch-import (role="dispatch" configs)
//   - Preview surfaces packed_on / order_release_id / tracking / destination
//   - Commit posts fg_stock_movements — with implicit-reserve fallback for
//     first-time dispatches (Myntra's file is often the FIRST record)
//   - Rows are always 1 unit per row (unlike picklist which can be qty>1)
// ═══════════════════════════════════════════════════════════════════════
function DispatchImportDrawer({ onClose, onDone }) {
  const [configs, setConfigs]     = useState(null);
  const [platform, setPlatform]   = useState("");
  const [file, setFile]           = useState(null);
  const [step, setStep]           = useState("choose");
  const [preview, setPreview]     = useState(null);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [committed, setCommitted] = useState(null);
  const [error, setError]         = useState("");
  const fileRef = useRef();

  useEffect(() => {
    (async () => {
      try {
        const r = await http.get("/order-import-format-configs?role=dispatch&active=true");
        setConfigs(r.data || []);
        if (r.data?.length) setPlatform(r.data[0].platform);
      } catch (e) {
        setConfigs([]);
      }
    })();
  }, []);

  const selectedCfg = useMemo(
    () => (configs || []).find((c) => c.platform === platform) || null,
    [configs, platform]
  );

  async function runPreview() {
    setError("");
    if (!file) return setError("Please select a file.");
    if (!platform) return setError("Please choose a platform.");
    setPreviewing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/dispatch-import?platform=${encodeURIComponent(platform)}&dry_run=true`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      setPreview(r.data);
      setStep("preview");
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Preview failed."));
    } finally {
      setPreviewing(false);
    }
  }

  async function runCommit() {
    setError("");
    setCommitting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/dispatch-import?platform=${encodeURIComponent(platform)}&dry_run=false`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      setCommitted(r.data);
      setStep("done");
      onDone();
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Commit failed."));
    } finally {
      setCommitting(false);
    }
  }

  function reset() {
    setPreview(null); setCommitted(null); setStep("choose"); setError("");
  }

  const noConfigs = configs !== null && configs.length === 0;

  return (
    <Drawer
      onClose={onClose}
      title={
        step === "choose"  ? "Import daily dispatch — step 1: choose file" :
        step === "preview" ? "Import daily dispatch — step 2: review & commit" :
                             "Dispatch import — done"
      }
      width="max-w-5xl"
    >
      <div className="space-y-5">
        {noConfigs && step === "choose" && (
          <div className="bg-amber-50 border-2 border-amber-300 px-4 py-4 text-sm text-amber-900">
            <div className="font-bold mb-1 flex items-center gap-2">
              <FileWarning className="w-4 h-4" /> No dispatch-import formats configured yet.
            </div>
            <div className="text-xs mb-3">
              Each platform's daily "what got packed" file format lives as a config row with role="dispatch".
            </div>
            <Link to="/order-import-formats" onClick={onClose}>
              <BtnPrimary>
                <span className="flex items-center gap-2">
                  <Settings2 className="w-4 h-4" /> Configure a dispatch format
                </span>
              </BtnPrimary>
            </Link>
          </div>
        )}

        {step === "choose" && configs && configs.length > 0 && (
          <>
            <div className="bg-emerald-50 border-2 border-emerald-200 px-4 py-3 text-sm text-emerald-900">
              <div className="font-bold mb-1 flex items-center gap-2">
                <Truck className="w-4 h-4" /> Daily dispatch import (config-driven)
              </div>
              <div className="text-xs">
                Each row = 1 unit dispatched. On commit, posts a <span className="font-mono">dispatched</span> fg_stock_movement
                per unit → decrements <span className="font-mono">ready_stock_qty</span> and releases any matching reservation.
                If no reservation exists (first-time dispatch), an implicit <span className="font-mono">reserved</span> is
                posted first so the ledger stays honest. Rows that can't resolve or that would push inventory below zero
                go to the exception queue.
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Select label="Platform *" id="dispatch-platform" value={platform}
                onChange={(e) => setPlatform(e.target.value)}>
                {configs.map((c) => (
                  <option key={c.platform} value={c.platform}>
                    {c.platform.charAt(0).toUpperCase() + c.platform.slice(1)}
                  </option>
                ))}
              </Select>

              {selectedCfg && (
                <div className="pt-6 text-xs space-y-1">
                  <div>
                    <Badge color="green">dispatch</Badge>{" "}
                    <span className="ml-1 text-neutral-500">config for {selectedCfg.platform}</span>
                  </div>
                  <div className="font-mono text-[11px] text-neutral-600">
                    leaf_sku column: {selectedCfg.column_map?.leaf_sku || "—"} · packed_on: {selectedCfg.column_map?.packed_on || "—"}
                  </div>
                  {Object.keys(selectedCfg.known_sku_prefix_replacements || {}).length > 0 && (
                    <div className="font-mono text-[11px] text-purple-700">
                      replaces: {Object.entries(selectedCfg.known_sku_prefix_replacements || {}).map(([k, v]) => `${k}→${v}`).join(", ")}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">File *</div>
              <div
                className="border-2 border-dashed border-slate-300 hover:border-slate-500 px-4 py-6 text-center cursor-pointer transition-colors"
                onClick={() => fileRef.current?.click()}
                data-testid="dispatch-import-file-drop"
              >
                <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
                {file
                  ? <div className="text-sm font-mono font-bold text-slate-700">{file.name}</div>
                  : <div className="text-sm text-slate-500">Click to choose the daily dispatch .csv / .xlsx</div>}
              </div>
              <input ref={fileRef} type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="hidden"
                onChange={(e) => setFile(e.target.files[0] || null)} />
            </div>

            {error && (
              <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold whitespace-pre-line">
                {error}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <BtnPrimary id="btn-dispatch-preview" onClick={runPreview}
                disabled={previewing || !file} className="flex-1">
                <span className="flex items-center justify-center gap-2">
                  <PlayCircle className="w-4 h-4" />
                  {previewing ? "Parsing preview…" : "Preview dispatch"}
                </span>
              </BtnPrimary>
              <BtnSecondary onClick={onClose} disabled={previewing}>Cancel</BtnSecondary>
            </div>
          </>
        )}

        {step === "preview" && preview && (
          <DispatchPreviewPanel
            preview={preview}
            error={error}
            committing={committing}
            onBack={() => { setStep("choose"); setPreview(null); }}
            onCommit={runCommit}
          />
        )}

        {step === "done" && committed && (
          <div className="space-y-3">
            <div className="bg-emerald-50 border-2 border-emerald-300 px-4 py-4 text-sm text-emerald-900">
              <div className="font-bold flex items-center gap-2 text-base mb-1">
                <CheckCircle2 className="w-5 h-5" /> Dispatch committed
              </div>
              <div className="text-xs font-mono mb-1">batch: {committed.import_batch_id}</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
                <MiniStat label="units dispatched" value={committed.committed?.movements_posted ?? 0} accent="#059669" />
                <MiniStat label="implicit reserves" value={committed.committed?.implicit_reserves ?? 0} accent="#D97706" />
                <MiniStat label="orders upserted" value={committed.committed?.orders_upserted ?? 0} accent="#0F172A" />
                <MiniStat label="items upserted" value={committed.committed?.items_upserted ?? 0} accent="#C27842" />
                <MiniStat label="already-dispatched" value={committed.committed?.already_dispatched ?? 0} accent="#64748B" />
                <MiniStat label="exceptions" value={committed.committed?.exceptions_queued ?? 0} accent="#DC2626" />
              </div>
            </div>
            <div className="flex gap-3">
              <BtnSecondary onClick={reset}>
                <ChevronLeft className="w-4 h-4 mr-1.5" /> Import another
              </BtnSecondary>
              <BtnPrimary onClick={onClose} className="flex-1">Close</BtnPrimary>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}

function DispatchPreviewPanel({ preview, error, committing, onBack, onCommit }) {
  const rows = preview.rows || [];
  const stats = preview.stats || {};

  return (
    <div className="space-y-4">
      <div className="bg-slate-50 border-2 border-slate-200 px-4 py-3 text-xs text-slate-800 font-mono space-y-1">
        <div>platform: <span className="font-bold">{preview.platform}</span> · role: <span className="font-bold">dispatch</span></div>
        <div>file: {preview.filename}</div>
        <div>header row (1-based): {preview.header_row_1_based}</div>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        <MiniStat label="total rows"        value={stats.total_rows_read         ?? 0} accent="#0F172A" />
        <MiniStat label="matched"           value={stats.matched                 ?? 0} accent="#16A34A" />
        <MiniStat label="unmatched"         value={stats.unmatched               ?? 0} accent="#DC2626" />
        <MiniStat label="empty leaf_sku"    value={stats.empty_leaf_sku          ?? 0} accent="#D97706" />
        <MiniStat label="distinct releases" value={stats.distinct_order_releases ?? 0} accent="#2563EB" />
      </div>

      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[420px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2 border-b">Row #</th>
                <th className="text-left p-2 border-b">Order / Release</th>
                <th className="text-left p-2 border-b">Raw leaf_sku</th>
                <th className="text-left p-2 border-b">Group → Size</th>
                <th className="text-left p-2 border-b">Style code</th>
                <th className="text-left p-2 border-b">Packed on</th>
                <th className="text-left p-2 border-b">Tracking</th>
                <th className="text-left p-2 border-b">Destination</th>
                <th className="text-right p-2 border-b">Qty</th>
                <th className="text-left p-2 border-b">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 300).map((r, i) => {
                const matched = !!r.matched;
                return (
                  <tr key={i} className={`border-b border-neutral-100 ${!matched ? "bg-red-50/40" : "hover:bg-slate-50"}`}>
                    <td className="p-2 font-mono">{r.source_row_index}</td>
                    <td className="p-2 font-mono text-[11px]">
                      <div>{r.order_id || "—"}</div>
                      <div className="text-emerald-700">{r.order_release_id || "—"}</div>
                    </td>
                    <td className="p-2 font-mono">
                      {r.leaf_sku_raw || "—"}
                      {r.leaf_sku_replaced_prefix && (
                        <span className="ml-1 text-[9px] text-purple-800 bg-purple-100 border border-purple-300 rounded px-1">
                          {r.leaf_sku_replaced_prefix}→fix
                        </span>
                      )}
                      {r.leaf_sku_stripped_prefix && (
                        <span className="ml-1 text-[9px] text-amber-700 bg-amber-100 border border-amber-300 rounded px-1">
                          -{r.leaf_sku_stripped_prefix}
                        </span>
                      )}
                    </td>
                    <td className="p-2 font-mono text-[11px]">
                      {r.group_id || "—"}{" → "}{r.derived_size || r.size || "—"}
                    </td>
                    <td className="p-2 font-mono">{r.style_code || "—"}</td>
                    <td className="p-2 text-[11px] whitespace-nowrap">{r.packed_on || "—"}</td>
                    <td className="p-2 font-mono text-[11px]">{r.tracking_id || "—"}</td>
                    <td className="p-2 text-[11px]">
                      {r.destination_city || "—"}{r.destination_state ? `, ${r.destination_state}` : ""}
                    </td>
                    <td className="p-2 font-mono text-right">{r.qty}</td>
                    <td className="p-2">
                      {matched ? (
                        <Badge color="green">{r.match_via || "matched"}</Badge>
                      ) : (
                        <div className="text-red-700 text-[10px] leading-tight">
                          <Badge color="red">exception</Badge>
                          <div className="mt-1 max-w-[220px]">{r.exception_reason}</div>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {rows.length > 300 && (
                <tr>
                  <td colSpan={10} className="p-3 text-center text-xs text-slate-500 italic">
                    Showing first 300 of {rows.length} rows. All rows will be committed.
                  </td>
                </tr>
              )}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={10} className="p-6 text-center text-sm text-slate-400 italic">
                    No rows parsed — check header row + column map.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold whitespace-pre-line">
          {error}
        </div>
      )}

      <div className="flex gap-3 pt-2 border-t border-slate-200">
        <BtnSecondary onClick={onBack} disabled={committing}>
          <ChevronLeft className="w-4 h-4 mr-1.5" /> Back
        </BtnSecondary>
        <BtnPrimary onClick={onCommit} disabled={committing || rows.length === 0 || stats.matched === 0} className="flex-1">
          <span className="flex items-center justify-center gap-2">
            <Truck className="w-4 h-4" />
            {committing ? "Committing…" :
             `Commit dispatch — decrement ready_stock for ${stats.matched} matched row${stats.matched !== 1 ? "s" : ""}`}
          </span>
        </BtnPrimary>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════
// Monthly Report Import Drawer (Phase 2 — inventory reconciliation)
//
// Uploads the Monthly_order_report.csv → dry_run classification preview
// (packed / returned_to_stock / pending / net_sold + reason breakdown)
// → commit: upserts online_order_items with the classification fields
// and posts return_in + return_restocked movements for every
// was_returned_to_stock row (idempotent per (order_release_id, leaf_sku)).
// ═══════════════════════════════════════════════════════════════════════
function MonthlyReportDrawer({ onClose, onDone }) {
  const [configs, setConfigs]     = useState(null);
  const [platform, setPlatform]   = useState("");
  const [file, setFile]           = useState(null);
  const [step, setStep]           = useState("choose");
  const [preview, setPreview]     = useState(null);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [committed, setCommitted] = useState(null);
  const [error, setError]         = useState("");
  const fileRef = useRef();

  useEffect(() => {
    (async () => {
      try {
        const r = await http.get("/order-import-format-configs?role=monthly_report&active=true");
        setConfigs(r.data || []);
        if (r.data?.length) setPlatform(r.data[0].platform);
      } catch (e) {
        setConfigs([]);
      }
    })();
  }, []);

  async function runPreview() {
    setError("");
    if (!file) return setError("Please select a file.");
    setPreviewing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/monthly-report-import?platform=${encodeURIComponent(platform)}&dry_run=true`,
        fd, { headers: { "Content-Type": "multipart/form-data" } }
      );
      setPreview(r.data);
      setStep("preview");
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Preview failed."));
    } finally { setPreviewing(false); }
  }

  async function runCommit() {
    setError("");
    setCommitting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/monthly-report-import?platform=${encodeURIComponent(platform)}&dry_run=false`,
        fd, { headers: { "Content-Type": "multipart/form-data" } }
      );
      setCommitted(r.data);
      setStep("done");
      onDone();
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Commit failed."));
    } finally { setCommitting(false); }
  }

  function reset() { setPreview(null); setCommitted(null); setStep("choose"); setError(""); }
  const noConfigs = configs !== null && configs.length === 0;

  return (
    <Drawer
      onClose={onClose}
      title={
        step === "choose"  ? "Monthly reconciliation — step 1: choose file" :
        step === "preview" ? "Monthly reconciliation — step 2: review & commit" :
                             "Monthly reconciliation — done"
      }
      width="max-w-6xl"
    >
      <div className="space-y-5">
        {noConfigs && step === "choose" && (
          <div className="bg-amber-50 border-2 border-amber-300 px-4 py-4 text-sm text-amber-900">
            <div className="font-bold mb-1 flex items-center gap-2">
              <FileWarning className="w-4 h-4" /> No monthly-report configs yet.
            </div>
            <Link to="/order-import-formats" onClick={onClose}>
              <BtnPrimary>
                <span className="flex items-center gap-2">
                  <Settings2 className="w-4 h-4" /> Configure a platform
                </span>
              </BtnPrimary>
            </Link>
          </div>
        )}

        {step === "choose" && configs && configs.length > 0 && (
          <>
            <div className="bg-indigo-50 border-2 border-indigo-200 px-4 py-3 text-sm text-indigo-900">
              <div className="font-bold mb-1 flex items-center gap-2">
                <ScrollText className="w-4 h-4" /> Monthly report — inventory reconciliation
              </div>
              <div className="text-xs leading-snug">
                The daily dispatch file only records packing. This monthly report tells us which of those
                units were <span className="font-bold">returned</span> (RTO / customer return /
                cancelled-after-pack) and must go back to <span className="font-mono">ready_stock_qty</span>.
                Classification is <b>NOT</b> "status=C means sold" — a "C" (delivered) row with a
                <span className="font-mono"> return_creation_date</span> is a return, and an "F" (cancelled)
                row with a <span className="font-mono">packed_on</span> date consumed inventory before
                cancellation. This importer applies the exact rules from the spec.
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Select label="Platform *" id="monthly-platform" value={platform}
                onChange={(e) => setPlatform(e.target.value)}>
                {configs.map((c) => (
                  <option key={c.platform} value={c.platform}>
                    {c.platform.charAt(0).toUpperCase() + c.platform.slice(1)}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Monthly file *</div>
              <div
                className="border-2 border-dashed border-slate-300 hover:border-slate-500 px-4 py-6 text-center cursor-pointer transition-colors"
                onClick={() => fileRef.current?.click()}
                data-testid="monthly-import-file-drop"
              >
                <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
                {file
                  ? <div className="text-sm font-mono font-bold text-slate-700">{file.name}</div>
                  : <div className="text-sm text-slate-500">Click to choose the monthly .csv / .xlsx</div>}
              </div>
              <input ref={fileRef} type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="hidden"
                onChange={(e) => setFile(e.target.files[0] || null)} />
            </div>

            {error && (
              <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold whitespace-pre-line">
                {error}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <BtnPrimary id="btn-monthly-preview" onClick={runPreview}
                disabled={previewing || !file} className="flex-1">
                <span className="flex items-center justify-center gap-2">
                  <PlayCircle className="w-4 h-4" />
                  {previewing ? "Classifying rows…" : "Preview classification"}
                </span>
              </BtnPrimary>
              <BtnSecondary onClick={onClose} disabled={previewing}>Cancel</BtnSecondary>
            </div>
          </>
        )}

        {step === "preview" && preview && (
          <MonthlyPreviewPanel
            preview={preview}
            error={error}
            committing={committing}
            onBack={() => { setStep("choose"); setPreview(null); }}
            onCommit={runCommit}
          />
        )}

        {step === "done" && committed && (
          <div className="space-y-3">
            <div className="bg-indigo-50 border-2 border-indigo-300 px-4 py-4 text-sm text-indigo-900">
              <div className="font-bold flex items-center gap-2 text-base mb-1">
                <CheckCircle2 className="w-5 h-5" /> Reconciliation committed
              </div>
              <div className="text-xs font-mono mb-3">batch: {committed.import_batch_id}</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <MiniStat label="items upserted"     value={committed.committed?.items_upserted        ?? 0} accent="#0F172A" />
                <MiniStat label="orders upserted"    value={committed.committed?.orders_upserted       ?? 0} accent="#C27842" />
                <MiniStat label="returns restocked"  value={committed.committed?.returns_posted        ?? 0} accent="#16A34A" />
                <MiniStat label="returns damaged"    value={committed.committed?.return_damaged_posted ?? 0} accent="#B91C1C" />
                <MiniStat label="idempotent skipped" value={committed.committed?.returns_skipped       ?? 0} accent="#64748B" />
                <MiniStat label="exceptions"         value={committed.committed?.exceptions_queued     ?? 0} accent="#DC2626" />
              </div>
            </div>
            <div className="flex gap-3">
              <BtnSecondary onClick={reset}>
                <ChevronLeft className="w-4 h-4 mr-1.5" /> Import another
              </BtnSecondary>
              <BtnPrimary onClick={onClose} className="flex-1">Close</BtnPrimary>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}

function MonthlyPreviewPanel({ preview, error, committing, onBack, onCommit }) {
  const rows  = preview.rows  || [];
  const stats = preview.stats || {};
  const breakdown = stats.reason_breakdown || {};

  return (
    <div className="space-y-4">
      <div className="bg-slate-50 border-2 border-slate-200 px-4 py-3 text-xs text-slate-800 font-mono space-y-1">
        <div>platform: <span className="font-bold">{preview.platform}</span> · role: <span className="font-bold">monthly_report</span></div>
        <div>file: {preview.filename}</div>
      </div>

      {/* ── Funnel: Packed → minus Returned/Pending → Net Sold ── */}
      <FunnelViz stats={stats} breakdown={breakdown} />

      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        <MiniStat label="total rows"        value={stats.total_rows              ?? 0} accent="#0F172A" />
        <MiniStat label="matched sku"       value={stats.matched                 ?? 0} accent="#16A34A" />
        <MiniStat label="unmatched sku"     value={stats.unmatched               ?? 0} accent="#DC2626" />
        <MiniStat label="never touched inv" value={stats.never_touched_inventory ?? 0} accent="#64748B" />
        <MiniStat label="pending in transit"value={stats.pending                 ?? 0} accent="#EAB308" />
        <MiniStat label="empty leaf_sku"    value={stats.empty_leaf_sku          ?? 0} accent="#D97706" />
      </div>

      {/* Rows table — status columns instead of dispatch fields */}
      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[400px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2 border-b">Row #</th>
                <th className="text-left p-2 border-b">Release</th>
                <th className="text-left p-2 border-b">Status</th>
                <th className="text-left p-2 border-b">Leaf SKU</th>
                <th className="text-left p-2 border-b">packed_on</th>
                <th className="text-left p-2 border-b">delivered_on</th>
                <th className="text-left p-2 border-b">return / rto / cancel</th>
                <th className="text-left p-2 border-b">Classification</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 300).map((r, i) => (
                <tr key={i} className={`border-b border-neutral-100 ${!r.matched ? "bg-red-50/40" : "hover:bg-slate-50"}`}>
                  <td className="p-2 font-mono">{r.source_row_index}</td>
                  <td className="p-2 font-mono text-[11px]">
                    <div>{r.order_id || "—"}</div>
                    <div className="text-emerald-700">{r.order_release_id || "—"}</div>
                  </td>
                  <td className="p-2 font-mono">{r.order_status || "—"}</td>
                  <td className="p-2 font-mono">
                    {r.leaf_sku_raw || "—"}
                    {r.leaf_sku_replaced_prefix && (
                      <span className="ml-1 text-[9px] text-purple-800 bg-purple-100 border border-purple-300 rounded px-1">
                        {r.leaf_sku_replaced_prefix}→fix
                      </span>
                    )}
                  </td>
                  <td className="p-2 text-[11px] whitespace-nowrap">{r.packed_on || "—"}</td>
                  <td className="p-2 text-[11px] whitespace-nowrap">{r.delivered_on || "—"}</td>
                  <td className="p-2 text-[11px] whitespace-nowrap">
                    {r.return_creation_date && <div className="text-red-700">ret: {r.return_creation_date}</div>}
                    {r.rto_creation_date    && <div className="text-red-700">rto: {r.rto_creation_date}</div>}
                    {r.cancelled_on         && <div className="text-amber-700">cxl: {r.cancelled_on}</div>}
                    {(!r.return_creation_date && !r.rto_creation_date && !r.cancelled_on) && "—"}
                  </td>
                  <td className="p-2">
                    <ClassificationBadges r={r} />
                  </td>
                </tr>
              ))}
              {rows.length > 300 && (
                <tr>
                  <td colSpan={8} className="p-3 text-center text-xs text-slate-500 italic">
                    Showing first 300 of {rows.length} rows. All rows will be committed.
                  </td>
                </tr>
              )}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-sm text-slate-400 italic">
                    No rows parsed — check header row + column map.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold whitespace-pre-line">
          {error}
        </div>
      )}

      <div className="flex gap-3 pt-2 border-t border-slate-200">
        <BtnSecondary onClick={onBack} disabled={committing}>
          <ChevronLeft className="w-4 h-4 mr-1.5" /> Back
        </BtnSecondary>
        <BtnPrimary onClick={onCommit} disabled={committing || rows.length === 0 || stats.matched === 0} className="flex-1">
          <span className="flex items-center justify-center gap-2">
            <ScrollText className="w-4 h-4" />
            {committing ? "Committing…" :
             `Commit reconciliation — ${stats.returned_to_stock} return-restocks + ${stats.matched} classifications`}
          </span>
        </BtnPrimary>
      </div>
    </div>
  );
}

function ClassificationBadges({ r }) {
  if (!r.matched) {
    return (
      <div className="text-red-700 text-[10px] leading-tight">
        <Badge color="red">unresolved</Badge>
        <div className="mt-1 max-w-[200px]">{r.exception_reason}</div>
      </div>
    );
  }
  if (r.is_net_sold)            return <Badge color="green">net sold</Badge>;
  if (r.was_returned_to_stock)  return <Badge color="red">returned · {r.return_reason}</Badge>;
  if (r.is_pending)             return <Badge color="yellow">pending</Badge>;
  if (r.never_touched_inventory) return <Badge color="slate">never packed</Badge>;
  return <Badge color="slate">—</Badge>;
}

// A compact funnel: total → packed → minus reversals → net sold.
function FunnelViz({ stats, breakdown }) {
  const total       = stats.total_rows              ?? 0;
  const packed      = stats.packed                  ?? 0;
  const returned    = stats.returned_to_stock       ?? 0;
  const pending     = stats.pending                 ?? 0;
  const netSold     = stats.net_sold                ?? 0;
  const neverTouched= stats.never_touched_inventory ?? 0;
  const barW = (n) => (total > 0 ? Math.max(4, Math.round((n / total) * 100)) : 0);

  const stages = [
    { label: "Total rows",       count: total,      color: "bg-slate-700",     text: "text-white"    },
    { label: "Never packed (ignore)", count: neverTouched, color: "bg-slate-300", text: "text-slate-800" },
    { label: "Packed",           count: packed,     color: "bg-blue-600",      text: "text-white"    },
    { label: "− Returned to stock", count: -returned, color: "bg-red-500",     text: "text-white",  sub: breakdown },
    { label: "− Still in transit",  count: -pending,  color: "bg-amber-400",   text: "text-amber-900" },
    { label: "= Net sold",       count: netSold,    color: "bg-emerald-600",   text: "text-white",   emphasize: true },
  ];

  return (
    <div className="bg-white border-2 border-slate-200 rounded p-4 space-y-2">
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Funnel</div>
      {stages.map((s) => (
        <div key={s.label} className={`flex items-center gap-3 ${s.emphasize ? "pt-2 mt-1 border-t border-slate-200" : ""}`}>
          <div className={`text-xs font-semibold ${s.emphasize ? "text-emerald-700" : "text-slate-700"}`} style={{ minWidth: 190 }}>
            {s.label}
          </div>
          <div className={`h-6 flex items-center px-2 font-mono text-xs font-bold ${s.color} ${s.text}`}
               style={{ width: `${Math.min(100, Math.abs(barW(s.count)))}%`, minWidth: 40 }}>
            {s.count >= 0 ? s.count : `${s.count}`}
          </div>
          {s.sub && Object.values(s.sub).some((v) => v > 0) && (
            <div className="text-[10px] text-slate-500 font-mono ml-2 whitespace-nowrap">
              (rto: {s.sub.rto}, cust: {s.sub.customer_return}, cxl-post-pack: {s.sub.cancelled_after_pack})
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// Read-side reconciliation summary card — feeds off /reconciliation-summary
function ReconciliationSummaryCard({ platform, month, onOpenImport }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (platform) params.append("platform", platform);
      if (month)    params.append("month", month);
      const r = await http.get(`/online-orders/reconciliation-summary?${params.toString()}`);
      setData(r.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [platform, month]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Current reconciliation state</div>
          <div className="text-sm text-slate-600 mt-0.5">
            {platform ? platform : "all platforms"}{month ? ` · ${month}` : " · all time"}
          </div>
        </div>
        <div className="flex gap-2">
          <BtnSecondary onClick={load} disabled={loading}>
            <span className="flex items-center gap-1.5"><RefreshCw className="w-3.5 h-3.5" /> Refresh</span>
          </BtnSecondary>
          <BtnPrimary onClick={onOpenImport}>
            <span className="flex items-center gap-1.5"><Upload className="w-3.5 h-3.5" /> Import monthly file</span>
          </BtnPrimary>
        </div>
      </div>

      {loading ? (
        <div className="py-6 text-center text-sm text-slate-400 italic">Loading…</div>
      ) : !data || data.total_rows === 0 ? (
        <div className="py-6 text-center text-sm text-slate-400 italic">
          No reconciled data yet. Import a monthly report to populate the funnel.
        </div>
      ) : (
        <FunnelViz stats={data} breakdown={data.reason_breakdown || {}} />
      )}
    </Card>
  );
}


// ── Main page ─────────────────────────────────────────────
export default function OnlineOrders() {
  const [tab, setTab]           = useState("orders"); // "orders" | "reconciliation"
  const [jobs, setJobs]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [importOpen, setImportOpen] = useState(false);
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [monthlyOpen, setMonthlyOpen]   = useState(false);
  const [reconPlatform, setReconPlatform] = useState("");
  const [reconMonth, setReconMonth]       = useState("");

  const [filterChannel, setFilterChannel]   = useState("");
  const [filterStatus, setFilterStatus]     = useState("");
  const [filterFrom, setFilterFrom]         = useState("");
  const [filterTo, setFilterTo]             = useState("");

  // channel filter is now derived from active configs so it stays in sync
  const [channelOptions, setChannelOptions] = useState(["myntra", "flipkart", "nykaa", "website"]);
  useEffect(() => {
    (async () => {
      try {
        const r = await http.get("/order-import-format-configs?active=true");
        const platforms = (r.data || []).map((c) => c.platform);
        if (platforms.length) {
          // Merge with defaults so legacy jobs still filterable
          const merged = Array.from(new Set([...platforms, "myntra", "flipkart", "nykaa", "website"]));
          setChannelOptions(merged);
        }
      } catch { /* keep defaults */ }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterChannel) params.append("channel", filterChannel);
      if (filterStatus)  params.append("style_match_status", filterStatus);
      if (filterFrom)    params.append("from_date", filterFrom);
      if (filterTo)      params.append("to_date",   filterTo);
      const qs = params.toString() ? `?${params}` : "";
      const r = await http.get(`/online-orders${qs}`);
      setJobs(r.data);
    } finally { setLoading(false); }
  }, [filterChannel, filterStatus, filterFrom, filterTo]);

  useEffect(() => { load(); }, [load]);

  const stats = jobs.reduce(
    (acc, j) => {
      acc.total++;
      acc.qty += j.quantity || 0;
      if (j.style_match_status === "matched" || j.style_match_status === "mapped") acc.resolved++;
      else acc.unresolved++;
      return acc;
    },
    { total: 0, qty: 0, resolved: 0, unresolved: 0 }
  );

  return (
    <div className="min-h-screen bg-[#F7F7F5]">
      <PageHeader
        title="Online Orders"
        subtitle={tab === "orders"
          ? "Config-driven marketplace order & picklist imports"
          : "Monthly report → returns/RTO/cancellations → inventory reconciliation"}
        testId="online-orders-header"
        action={
          <div className="flex gap-2">
            <Link to="/order-import-formats">
              <BtnSecondary id="btn-import-formats">
                <span className="flex items-center gap-1.5">
                  <Settings2 className="w-4 h-4" /> Formats
                </span>
              </BtnSecondary>
            </Link>
            {tab === "orders" && (
              <>
                <BtnSecondary id="btn-refresh-orders" onClick={load}>
                  <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
                </BtnSecondary>
                <BtnSecondary id="btn-dispatch-import" onClick={() => setDispatchOpen(true)}>
                  <span className="flex items-center gap-2"><Truck className="w-4 h-4" /> Import dispatch</span>
                </BtnSecondary>
                <BtnPrimary id="btn-import-orders" onClick={() => setImportOpen(true)}>
                  <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Import orders</span>
                </BtnPrimary>
              </>
            )}
            {tab === "reconciliation" && (
              <BtnPrimary id="btn-monthly-import" onClick={() => setMonthlyOpen(true)}>
                <span className="flex items-center gap-2"><ScrollText className="w-4 h-4" /> Import monthly report</span>
              </BtnPrimary>
            )}
          </div>
        }
      />

      {/* ── Tab bar ── */}
      <div className="px-4 sm:px-8 bg-white border-b-2 border-slate-200 flex gap-1">
        {[
          { key: "orders",         label: "Orders",                  icon: ShoppingBag },
          { key: "reconciliation", label: "Monthly Reconciliation", icon: ScrollText  },
        ].map((t) => {
          const Ic = t.icon; const active = tab === t.key;
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`px-4 py-3 text-sm font-semibold border-b-2 -mb-0.5 transition-colors inline-flex items-center gap-2 ${
                active
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
              data-testid={`oo-tab-${t.key}`}>
              <Ic className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "reconciliation" ? (
        <div className="px-4 sm:px-8 py-6 space-y-6">
          {/* Filters */}
          <div className="bg-white border-2 border-slate-200 px-4 py-3 flex flex-wrap gap-3 items-end">
            <div className="w-40">
              <Select label="Platform" id="recon-platform" value={reconPlatform}
                onChange={(e) => setReconPlatform(e.target.value)}>
                <option value="">All platforms</option>
                {channelOptions.map((c) => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </Select>
            </div>
            <div className="w-40">
              <Input label="Month (YYYY-MM)" id="recon-month" type="month"
                value={reconMonth} onChange={(e) => setReconMonth(e.target.value)} />
            </div>
            <button
              className="text-xs text-slate-400 hover:text-slate-700 underline self-end mb-0.5"
              onClick={() => { setReconPlatform(""); setReconMonth(""); }}
            >Clear</button>
          </div>

          <ReconciliationSummaryCard
            platform={reconPlatform || null}
            month={reconMonth || null}
            onOpenImport={() => setMonthlyOpen(true)}
          />
        </div>
      ) : (
        <>
      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 px-4 sm:px-8 py-5">
        {[
          { label: "Total Jobs", value: stats.total, accent: "#0F172A" },
          { label: "Total Qty", value: stats.qty, accent: "#C27842" },
          { label: "Resolved", value: stats.resolved, accent: "#16A34A" },
          { label: "Unresolved", value: stats.unresolved, accent: "#DC2626" },
        ].map(({ label, value, accent }) => (
          <Card key={label} className="p-4 relative overflow-hidden">
            <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: accent }} />
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate">{label}</div>
            <div className="font-mono text-2xl font-bold mt-2">{value}</div>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="px-4 sm:px-8 py-4 bg-white border-y-2 border-slate-200 flex flex-wrap gap-3 items-end">
        <div className="w-40">
          <Select label="Channel" id="filter-channel" value={filterChannel}
            onChange={(e) => setFilterChannel(e.target.value)}>
            <option value="">All Channels</option>
            {channelOptions.map((c) => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
          </Select>
        </div>
        <div className="w-40">
          <Select label="Match Status" id="filter-status" value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All Statuses</option>
            <option value="mapped">Mapped</option>
            <option value="matched">Matched</option>
            <option value="unmatched">Unmatched</option>
          </Select>
        </div>
        <div className="w-36">
          <Input label="From Date" id="filter-from" type="date"
            value={filterFrom} onChange={(e) => setFilterFrom(e.target.value)} />
        </div>
        <div className="w-36">
          <Input label="To Date" id="filter-to" type="date"
            value={filterTo} onChange={(e) => setFilterTo(e.target.value)} />
        </div>
        <BtnSecondary id="btn-filter-apply" onClick={load}>Apply</BtnSecondary>
        <button
          className="text-xs text-slate-400 hover:text-slate-700 underline self-end mb-0.5"
          onClick={() => { setFilterChannel(""); setFilterStatus(""); setFilterFrom(""); setFilterTo(""); }}
        >Clear</button>
      </div>

      {/* Table */}
      <div className="px-4 sm:px-8 py-6">
        {loading ? (
          <div className="text-center py-20 text-slate-400">Loading orders…</div>
        ) : jobs.length === 0 ? (
          <Card className="p-10 text-center">
            <ShoppingBag className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <div className="text-slate-500 font-semibold mb-1">No online orders found</div>
            <div className="text-xs text-slate-400 mb-4">Import a marketplace order or picklist file to get started.</div>
            <BtnPrimary onClick={() => setImportOpen(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Import orders</span>
            </BtnPrimary>
          </Card>
        ) : (
          <Card className="overflow-x-auto">
            <table className="w-full text-sm" id="online-orders-table">
              <thead>
                <tr className="border-b-2 border-slate-200 bg-slate-50 text-left">
                  {["Channel", "Order ID", "Internal Style", "Color", "Size", "Qty", "Unit ₹", "Stage", "Match Status", "Order Date"].map((h) => (
                    <th key={h} className="px-4 py-3 text-[10px] uppercase tracking-wider font-bold text-slate-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {jobs.map((j) => (
                  <tr key={j.id} className={`hover:bg-slate-50 transition-colors ${j.style_match_status === "unmatched" ? "bg-red-50/40" : ""}`}>
                    <td className="px-4 py-3">
                      <Badge color={CHANNEL_COLORS[j.channel] || "slate"}>
                        {j.channel}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{j.po_number}</td>
                    <td className="px-4 py-3">
                      <div className="font-mono font-bold text-slate-900">{j.style_code}</div>
                      {j.mapped_from_sku && (
                        <div className="text-[10px] text-slate-400 font-mono">← {j.mapped_from_sku}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">{j.color || "—"}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">{j.size  || "—"}</td>
                    <td className="px-4 py-3 font-mono font-bold">{j.quantity}</td>
                    <td className="px-4 py-3 font-mono text-xs">{j.unit_price ? `₹${j.unit_price.toLocaleString("en-IN")}` : "—"}</td>
                    <td className="px-4 py-3"><Badge color="slate">{j.stage}</Badge></td>
                    <td className="px-4 py-3">
                      <Badge color={STATUS_COLORS[j.style_match_status] || "slate"}>
                        {j.style_match_status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                      {j.order_date || j.created_at?.slice(0, 10)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
        </>
      )}

      {importOpen && (
        <ImportDrawer onClose={() => setImportOpen(false)} onDone={load} />
      )}

      {dispatchOpen && (
        <DispatchImportDrawer onClose={() => setDispatchOpen(false)} onDone={load} />
      )}

      {monthlyOpen && (
        <MonthlyReportDrawer onClose={() => setMonthlyOpen(false)} onDone={load} />
      )}
    </div>
  );
}
