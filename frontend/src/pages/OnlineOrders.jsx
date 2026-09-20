import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { http } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge, PaginationControls,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Upload, ShoppingBag, RefreshCw, FileWarning, Settings2,
  ChevronLeft, PlayCircle, CheckCircle2, AlertTriangle, Truck,
} from "lucide-react";
import { Link } from "react-router-dom";

import ResponsiveTable from "../components/ResponsiveTable";

const CHANNEL_COLORS = {
  myntra: "pink",
  flipkart: "blue",
  nykaa: "orange",
  ajio: "purple",
  amazon: "yellow",
  website: "slate",
};

const STATUS_COLORS = {
  matched: "green",
  mapped: "blue",
  unmatched: "red",
};

// Column config for the main online orders list (shared by ResponsiveTable)
const ONLINE_ORDERS_COLUMNS = [
  {
    key: "channel",
    header: "Channel",
    primary: true,
    render: (j) => <Badge color={CHANNEL_COLORS[j.channel] || "slate"}>{j.channel}</Badge>,
  },
  {
    key: "style_code",
    header: "Internal Style",
    primary: true,
    render: (j) => (
      <div>
        <div className="font-mono font-bold text-slate-900">{j.style_code}</div>
        {j.mapped_from_sku && (
          <div className="text-[10px] text-slate-400 font-mono">← {j.mapped_from_sku}</div>
        )}
      </div>
    ),
  },
  {
    key: "po_number",
    header: "Order ID",
    className: "font-mono text-xs text-slate-700",
    render: (j) => j.po_number,
  },
  {
    key: "color",
    header: "Color",
    className: "text-xs text-slate-600",
    render: (j) => j.color || "—",
  },
  {
    key: "size",
    header: "Size",
    className: "text-xs text-slate-600",
    render: (j) => j.size || "—",
  },
  {
    key: "quantity",
    header: "Qty",
    className: "font-mono font-bold",
    render: (j) => j.quantity,
  },
  {
    key: "unit_price",
    header: "Unit ₹",
    className: "font-mono text-xs",
    render: (j) => j.unit_price ? `₹${j.unit_price.toLocaleString("en-IN")}` : "—",
  },
  {
    key: "stage",
    header: "Stage",
    render: (j) => <Badge color="slate">{j.stage}</Badge>,
  },
  {
    key: "style_match_status",
    header: "Match Status",
    render: (j) => (
      <Badge color={STATUS_COLORS[j.style_match_status] || "slate"}>
        {j.style_match_status}
      </Badge>
    ),
  },
  {
    key: "order_date",
    header: "Order Date",
    className: "text-xs text-slate-500 whitespace-nowrap",
    render: (j) => j.order_date || j.created_at?.slice(0, 10) || "—",
  },
];

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
  const [configs, setConfigs] = useState(null); // null = still loading
  const [platform, setPlatform] = useState("");
  const [file, setFile] = useState(null);
  const [step, setStep] = useState("choose"); // choose | preview | done
  const [preview, setPreview] = useState(null);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [committed, setCommitted] = useState(null);
  const [error, setError] = useState("");
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
        fd);
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
        fd);
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
        step === "choose" ? "Import orders — step 1: choose file" :
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
                data-testid="import-order-file-input"
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
                <CheckCircle2 className="w-5 h-5 text-emerald-600" /> Import committed successfully
              </div>
              <div className="text-xs font-mono mb-1">batch: {committed.import_batch_id}</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
                <MiniStat label="picklists" value={committed.committed?.picklists_created ?? 0} accent="#059669" />
                <MiniStat label="stock fulfilled" value={committed.committed?.pairs_fulfilled_from_stock ?? 0} accent="#10B981" />
                <MiniStat label="to manufacture" value={committed.committed?.pairs_to_manufacture ?? (committed.committed?.jobs_created ?? 0)} accent="#D97706" />
                <MiniStat label="exceptions" value={committed.committed?.exceptions_queued ?? 0} accent="#DC2626" />
              </div>

              {committed.committed?.picklist_details?.length > 0 && (
                <div className="mt-3 bg-white p-3 border border-emerald-300 rounded">
                  <div className="font-bold text-xs uppercase tracking-wider text-emerald-900 mb-1.5">
                    Generated ERP Picklists ({committed.committed.picklist_details.length}):
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {committed.committed.picklist_details.map((pl, idx) => (
                      <span key={idx} className="font-mono text-xs bg-emerald-100 text-emerald-800 border border-emerald-300 px-2.5 py-1 rounded font-bold">
                        {pl.picklist_no} ({pl.total_qty} pairs)
                      </span>
                    ))}
                  </div>
                </div>
              )}
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

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [filterMode, setFilterMode] = useState("all"); // "all" | "unmatched" | "matched"

  const filteredRows = useMemo(() => {
    if (filterMode === "unmatched") return rows.filter((r) => !r.matched);
    if (filterMode === "matched") return rows.filter((r) => !!r.matched);
    return rows;
  }, [rows, filterMode]);

  const effectivePageSize = pageSize === 0 ? filteredRows.length || 1 : pageSize;
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / effectivePageSize));
  const currentPage = Math.min(page, totalPages);
  const startIdx = (currentPage - 1) * effectivePageSize;
  const paginatedRows = pageSize === 0 ? filteredRows : filteredRows.slice(startIdx, startIdx + effectivePageSize);

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
        <MiniStat label="total" value={stats.total_rows_read ?? 0} accent="#0F172A" />
        <MiniStat label="matched" value={stats.matched ?? 0} accent="#16A34A" />
        <MiniStat label="unmatched" value={stats.unmatched ?? 0} accent="#DC2626" />
        <MiniStat label="order rows" value={stats.order_style_rows ?? 0} accent="#2563EB" />
        <MiniStat label="picklist rows" value={stats.picklist_rows ?? 0} accent="#7C3AED" />
        <MiniStat label="distinct orders" value={stats.distinct_orders ?? 0} accent="#C27842" />
      </div>

      {/* Two-tier fulfillment preview summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <MiniStat label="In-Stock (ERP Picklist)" value={stats.pairs_fulfilled_from_stock ?? 0} accent="#059669" />
        <MiniStat label="To Manufacture" value={stats.pairs_to_manufacture ?? 0} accent="#D97706" />
        <MiniStat label="Ready to Cut (BOM OK)" value={stats.ready_to_produce_pairs ?? 0} accent="#2563EB" />
        <MiniStat label="Shortage / No BOM" value={stats.shortage_pairs ?? 0} accent="#DC2626" />
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

      {/* Filter and pagination bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 border-2 border-slate-200 p-2.5 rounded text-xs">
        <div className="flex items-center gap-1.5">
          <span className="font-bold text-slate-500 uppercase tracking-wider text-[10px] mr-1">Filter:</span>
          <button
            type="button"
            onClick={() => { setFilterMode("all"); setPage(1); }}
            className={`px-2.5 py-1 rounded font-semibold transition-colors ${filterMode === "all" ? "bg-slate-900 text-white" : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-100"}`}
            data-testid="preview-filter-all"
          >
            All ({rows.length})
          </button>
          <button
            type="button"
            onClick={() => { setFilterMode("unmatched"); setPage(1); }}
            className={`px-2.5 py-1 rounded font-semibold transition-colors ${filterMode === "unmatched" ? "bg-red-600 text-white" : "bg-white text-red-700 border border-red-200 hover:bg-red-50"}`}
            data-testid="preview-filter-unmatched"
          >
            Exceptions ({stats.unmatched ?? 0})
          </button>
          <button
            type="button"
            onClick={() => { setFilterMode("matched"); setPage(1); }}
            className={`px-2.5 py-1 rounded font-semibold transition-colors ${filterMode === "matched" ? "bg-emerald-600 text-white" : "bg-white text-emerald-700 border border-emerald-200 hover:bg-emerald-50"}`}
            data-testid="preview-filter-matched"
          >
            Matched ({stats.matched ?? 0})
          </button>
        </div>

        <PaginationControls
          currentPage={currentPage}
          totalItems={filteredRows.length}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          pageSizeOptions={[50, 100, 250, 500]}
          allowAll
          rangeTextFormat="compact"
          testIdPrefix="preview"
          prevTestId="preview-prev-page"
          nextTestId="preview-next-page"
          pageSizeTestId="preview-page-size"
          showFirstLast={false}
          className="pt-0 border-t-0"
        />
      </div>

      {/* Row preview table */}
      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[460px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs" data-testid="preview-rows-table">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2 border-b sticky left-0 z-10 bg-slate-100">Row #</th>
                <th className="text-left p-2 border-b">Type</th>
                <th className="text-left p-2 border-b">Order / Batch</th>
                <th className="text-left p-2 border-b">Raw leaf_sku</th>
                <th className="text-left p-2 border-b">Group → size</th>
                <th className="text-left p-2 border-b">Style code</th>
                <th className="text-right p-2 border-b">Qty</th>
                <th className="text-left p-2 border-b">Mapping</th>
                <th className="text-left p-2 border-b">Fulfillment Plan</th>
              </tr>
            </thead>
            <tbody>
              {paginatedRows.map((r, i) => {
                const isOrderRow = !!r.order_id;
                const isPicklistRow = !isOrderRow;
                const matched = !!r.matched;
                return (
                  <tr key={i} className={`border-b border-neutral-100 ${!matched ? "bg-red-50/40" : "hover:bg-slate-50"}`}>
                    <td className="p-2 font-mono sticky left-0 z-10 bg-white">{r.source_row_index}</td>
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
                    <td className="p-2">
                      {matched ? (
                        r.fulfillment_status === "in_stock_picklist" ? (
                          <Badge color="green">
                            <CheckCircle2 className="w-3 h-3 inline mr-1" /> Stock Picklist ({r.covered_qty ?? r.qty} prs)
                          </Badge>
                        ) : r.fulfillment_status === "partial_stock" ? (
                          <div className="space-y-0.5">
                            <Badge color="amber">
                              Partial ({r.covered_qty} stock / {r.remaining_qty} mfg)
                            </Badge>
                            <div className="text-[10px] text-slate-500">
                              {r.components_available ? "Components OK -> cutting" : (r.has_bom === false ? "No BOM -> procurement" : "Comp shortage -> procurement")}
                            </div>
                          </div>
                        ) : r.fulfillment_status === "produce_ready" ? (
                          <Badge color="blue">
                            Cutting ({r.remaining_qty ?? r.qty} prs - ready)
                          </Badge>
                        ) : (
                          <div className="space-y-0.5">
                            <Badge color="red">
                              <AlertTriangle className="w-3 h-3 inline mr-1" />
                              {r.has_bom === false ? "No BOM Mapped" : "Shortage"} ({r.remaining_qty ?? r.qty} prs)
                            </Badge>
                            <div className="text-[10px] text-red-600">Pending Shortage Queue</div>
                          </div>
                        )
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {paginatedRows.length === 0 && (
                <tr>
                  <td colSpan={9} className="p-6 text-center text-sm text-slate-400 italic">
                    {rows.length === 0 ? "No rows parsed — check header row + column map." : "No rows match current filter."}
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
  const [configs, setConfigs] = useState(null);
  const [platform, setPlatform] = useState("");
  const [file, setFile] = useState(null);
  const [step, setStep] = useState("choose");
  const [preview, setPreview] = useState(null);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [committed, setCommitted] = useState(null);
  const [error, setError] = useState("");
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
        fd);
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
        fd);
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
        step === "choose" ? "Import daily dispatch — step 1: choose file" :
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

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [filterMode, setFilterMode] = useState("all"); // "all" | "unmatched" | "matched"

  const filteredRows = useMemo(() => {
    if (filterMode === "unmatched") return rows.filter((r) => !r.matched);
    if (filterMode === "matched") return rows.filter((r) => !!r.matched);
    return rows;
  }, [rows, filterMode]);

  const effectivePageSize = pageSize === 0 ? filteredRows.length || 1 : pageSize;
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / effectivePageSize));
  const currentPage = Math.min(page, totalPages);
  const startIdx = (currentPage - 1) * effectivePageSize;
  const paginatedRows = pageSize === 0 ? filteredRows : filteredRows.slice(startIdx, startIdx + effectivePageSize);

  return (
    <div className="space-y-4">
      <div className="bg-slate-50 border-2 border-slate-200 px-4 py-3 text-xs text-slate-800 font-mono space-y-1">
        <div>platform: <span className="font-bold">{preview.platform}</span> · role: <span className="font-bold">dispatch</span></div>
        <div>file: {preview.filename}</div>
        <div>header row (1-based): {preview.header_row_1_based}</div>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        <MiniStat label="total rows" value={stats.total_rows_read ?? 0} accent="#0F172A" />
        <MiniStat label="matched" value={stats.matched ?? 0} accent="#16A34A" />
        <MiniStat label="unmatched" value={stats.unmatched ?? 0} accent="#DC2626" />
        <MiniStat label="empty leaf_sku" value={stats.empty_leaf_sku ?? 0} accent="#D97706" />
        <MiniStat label="distinct releases" value={stats.distinct_order_releases ?? 0} accent="#2563EB" />
      </div>

      {/* Filter and pagination bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 border-2 border-slate-200 p-2.5 rounded text-xs">
        <div className="flex items-center gap-1.5">
          <span className="font-bold text-slate-500 uppercase tracking-wider text-[10px] mr-1">Filter:</span>
          <button
            type="button"
            onClick={() => { setFilterMode("all"); setPage(1); }}
            className={`px-2.5 py-1 rounded font-semibold transition-colors ${filterMode === "all" ? "bg-slate-900 text-white" : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-100"}`}
          >
            All ({rows.length})
          </button>
          <button
            type="button"
            onClick={() => { setFilterMode("unmatched"); setPage(1); }}
            className={`px-2.5 py-1 rounded font-semibold transition-colors ${filterMode === "unmatched" ? "bg-red-600 text-white" : "bg-white text-red-700 border border-red-200 hover:bg-red-50"}`}
          >
            Exceptions ({stats.unmatched ?? 0})
          </button>
          <button
            type="button"
            onClick={() => { setFilterMode("matched"); setPage(1); }}
            className={`px-2.5 py-1 rounded font-semibold transition-colors ${filterMode === "matched" ? "bg-emerald-600 text-white" : "bg-white text-emerald-700 border border-emerald-200 hover:bg-emerald-50"}`}
          >
            Matched ({stats.matched ?? 0})
          </button>
        </div>

        <PaginationControls
          currentPage={currentPage}
          totalItems={filteredRows.length}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          pageSizeOptions={[50, 100, 250, 500]}
          allowAll
          rangeTextFormat="compact"
          testIdPrefix="picklist-preview"
          showFirstLast={false}
          className="pt-0 border-t-0"
        />
      </div>

      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[460px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2 border-b sticky left-0 z-10 bg-slate-100">Row #</th>
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
              {paginatedRows.map((r, i) => {
                const matched = !!r.matched;
                return (
                  <tr key={i} className={`border-b border-neutral-100 ${!matched ? "bg-red-50/40" : "hover:bg-slate-50"}`}>
                    <td className="p-2 font-mono sticky left-0 z-10 bg-white">{r.source_row_index}</td>
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
              {paginatedRows.length === 0 && (
                <tr>
                  <td colSpan={10} className="p-6 text-center text-sm text-slate-400 italic">
                    {rows.length === 0 ? "No rows parsed — check header row + column map." : "No rows match current filter."}
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


// ── Main page ─────────────────────────────────────────────
export default function OnlineOrders() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImportOpen] = useState(false);
  const [dispatchOpen, setDispatchOpen] = useState(false);

  const [filterChannel, setFilterChannel] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");

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
      if (filterStatus) params.append("style_match_status", filterStatus);
      if (filterFrom) params.append("from_date", filterFrom);
      if (filterTo) params.append("to_date", filterTo);
      const qs = params.toString() ? `?${params}` : "";
      const r = await http.get(`/online-orders${qs}`);
      setJobs(r?.data || []);
    } catch {
      setJobs([]);
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
    <div className="bg-[#F7F7F5]">
      <PageHeader
        title="Online Orders"
        subtitle="Config-driven marketplace order & picklist imports"
        testId="online-orders-header"
        action={
          <div className="flex gap-2 items-center">
            <Link to="/order-import-formats">
              <BtnSecondary id="btn-import-formats">
                <span className="flex items-center gap-1.5">
                  <Settings2 className="w-4 h-4" /> Formats
                </span>
              </BtnSecondary>
            </Link>
            <BtnSecondary id="btn-refresh-orders" onClick={load}>
              <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
            </BtnSecondary>
            <BtnSecondary id="btn-dispatch-import" onClick={() => setDispatchOpen(true)}>
              <span className="flex items-center gap-2"><Truck className="w-4 h-4" /> Import dispatch</span>
            </BtnSecondary>
            <BtnPrimary id="btn-import-orders" onClick={() => setImportOpen(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Import orders</span>
            </BtnPrimary>
          </div>
        }
      />

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
          <Card className="overflow-hidden">
            <ResponsiveTable
              columns={ONLINE_ORDERS_COLUMNS}
              rows={[]}
              loading={true}
              testId="online-orders-table"
            />
          </Card>
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
          <Card className="overflow-hidden">
            <ResponsiveTable
              columns={ONLINE_ORDERS_COLUMNS}
              rows={jobs}
              rowKey={(j) => j.id}
              rowClassName={(j) => j.style_match_status === "unmatched" ? "bg-red-50/40" : ""}
              testId="online-orders-table"
            />
          </Card>
        )}
      </div>

      {importOpen && (
        <ImportDrawer onClose={() => setImportOpen(false)} onDone={load} />
      )}

      {dispatchOpen && (
        <DispatchImportDrawer onClose={() => setDispatchOpen(false)} onDone={load} />
      )}
    </div>
  );
}
