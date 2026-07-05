import { useEffect, useState, useCallback, useRef } from "react";
import { http } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Upload, Download, ShoppingBag, CheckCircle2,
  AlertTriangle, X, RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";

const CHANNELS = ["myntra", "flipkart", "nykaa", "website"];

const CHANNEL_COLORS = {
  myntra:   "pink",
  flipkart: "blue",
  nykaa:    "orange",
  website:  "slate",
};

const STATUS_COLORS = {
  matched: "green",
  mapped:  "blue",
  unmatched: "red",
};

const CSV_TEMPLATE = `order_id,style_sku,quantity,color,size,unit_price,delivery_date,description
MYN-ORD-001,MYN-SKU-101,2,Black,8,899.00,2026-07-20,Casual loafer black
MYN-ORD-002,MYN-SKU-102,1,Brown,9,1299.00,2026-07-22,Oxford brown`;

function downloadTemplate() {
  const blob = new Blob([CSV_TEMPLATE], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "online_orders_template.csv";
  a.click();
}

// ── Import Drawer ────────────────────────────────────────
function ImportDrawer({ onClose, onDone }) {
  const [channel, setChannel]     = useState("myntra");
  const [orderDate, setOrderDate] = useState(new Date().toISOString().slice(0, 10));
  const [file, setFile]           = useState(null);
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState("");
  const fileRef = useRef();

  async function submit() {
    setError(""); setResult(null);
    if (!file) return setError("Please select a CSV file.");
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("channel", channel);
      fd.append("order_date", orderDate);
      const r = await http.post("/online-orders/import", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(r.data);
      onDone();
    } catch (e) {
      setError(e.response?.data?.detail || "Import failed.");
    } finally { setLoading(false); }
  }

  return (
    <Drawer onClose={onClose} title="Import Online Orders (CSV)">
      <div className="space-y-5">

        {/* Info banner */}
        <div className="bg-blue-50 border-2 border-blue-200 px-4 py-3 text-sm text-blue-800">
          <div className="font-bold mb-1">Required CSV columns:</div>
          <div className="font-mono text-xs">order_id, style_sku, quantity</div>
          <div className="font-bold mt-2 mb-1">Optional:</div>
          <div className="font-mono text-xs">color, size, unit_price, delivery_date, description</div>
          <div className="mt-2 text-xs text-blue-700">
            Unresolved SKUs are <span className="font-bold">not auto-created</span> — they appear
            in the error list. Add their mappings at{" "}
            <Link to="/sku-map" className="underline font-bold">SKU Mapping</Link> then re-import.
          </div>
          <button onClick={downloadTemplate}
            className="mt-2 flex items-center gap-1 text-xs font-bold underline hover:text-blue-900">
            <Download className="w-3 h-3" /> Download template
          </button>
        </div>

        {/* Channel */}
        <Select label="Channel *" id="import-channel" value={channel}
          onChange={(e) => setChannel(e.target.value)}>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
          ))}
        </Select>

        {/* Order date */}
        <Input label="Order / Import Date" id="import-date" type="date"
          value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />

        {/* File picker */}
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">CSV File *</div>
          <div
            className="border-2 border-dashed border-slate-300 hover:border-slate-500 px-4 py-6 text-center cursor-pointer transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
            {file
              ? <div className="text-sm font-mono font-bold text-slate-700">{file.name}</div>
              : <div className="text-sm text-slate-500">Click to choose a .csv file</div>}
          </div>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
            onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>

        {error && (
          <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold">{error}</div>
        )}

        {/* Result summary */}
        {result && (
          <div className="space-y-2">
            <div className="bg-green-50 border-2 border-green-300 px-4 py-3">
              <div className="font-bold text-green-800 text-sm">
                ✓ {result.imported} job{result.imported !== 1 ? "s" : ""} created
              </div>
              {result.unresolved > 0 && (
                <div className="text-amber-700 text-xs mt-1 font-semibold">
                  ⚠ {result.unresolved} row{result.unresolved !== 1 ? "s" : ""} unresolved — add SKU mappings and re-import
                </div>
              )}
            </div>
            {result.errors.length > 0 && (
              <div className="bg-amber-50 border-2 border-amber-300 px-4 py-3 max-h-52 overflow-y-auto space-y-1.5">
                <div className="font-bold text-amber-800 text-sm">{result.errors.length} row issue{result.errors.length !== 1 ? "s" : ""}:</div>
                {result.errors.map((e, i) => (
                  <div key={i} className="text-xs">
                    <span className="font-mono text-slate-500">Row {e.row}</span>
                    {e.order_id && <span className="font-mono font-bold text-slate-700 ml-2">{e.order_id}</span>}
                    {e.style_sku && <span className="font-mono text-red-600 ml-2">SKU: {e.style_sku}</span>}
                    <div className="text-slate-600 ml-2 mt-0.5">{e.reason}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <BtnPrimary id="btn-do-import" onClick={submit} disabled={loading} className="flex-1">
            <span className="flex items-center justify-center gap-2">
              <Upload className="w-4 h-4" />
              {loading ? "Importing…" : "Import Orders"}
            </span>
          </BtnPrimary>
          <BtnSecondary onClick={onClose} disabled={loading}>Close</BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

// ── Main page ─────────────────────────────────────────────
export default function OnlineOrders() {
  const [jobs, setJobs]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [importOpen, setImportOpen] = useState(false);

  // Filters
  const [filterChannel, setFilterChannel]   = useState("");
  const [filterStatus, setFilterStatus]     = useState("");
  const [filterFrom, setFilterFrom]         = useState("");
  const [filterTo, setFilterTo]             = useState("");

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

  // Summary stats
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
        subtitle="Channel Imports"
        testId="online-orders-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary id="btn-refresh-orders" onClick={load}>
              <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
            </BtnSecondary>
            <BtnPrimary id="btn-import-orders" onClick={() => setImportOpen(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Import CSV</span>
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
            {CHANNELS.map((c) => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
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
            <div className="text-xs text-slate-400 mb-4">Import a CSV to get started.</div>
            <BtnPrimary onClick={() => setImportOpen(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Import CSV</span>
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

      {importOpen && (
        <ImportDrawer onClose={() => setImportOpen(false)} onDone={load} />
      )}
    </div>
  );
}
