import { useEffect, useMemo, useState, useCallback } from "react";
import { http, formatApiError, friendlyAxiosError } from "../lib/api";
import { BtnPrimary, BtnSecondary, Input, Select, Badge } from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Grid3x3, FileUp, Download, Plus, X, AlertTriangle,
  CheckCircle2, XCircle, Rows3, Layers, Loader2, FileSpreadsheet,
} from "lucide-react";

// Match the same movement types as the main page
const MOVEMENT_TYPES = [
  { value: "production_in",    label: "Production In (+ready)" },
  { value: "reserved",         label: "Reserved (+reserved)" },
  { value: "unreserved",       label: "Unreserved (-reserved)" },
  { value: "dispatched",       label: "Dispatched (-ready & -reserved)" },
  { value: "return_in",        label: "Return In (+return)" },
  { value: "return_restocked", label: "Return Restocked (-return, +ready)" },
  { value: "return_damaged",   label: "Return Damaged (-return, +damaged)" },
  { value: "liquidation_out",  label: "Liquidation Out (-ready, +liquidation)" },
];

const sortSizes = (arr) => [...arr].sort((a, b) => {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  if (!isNaN(na)) return -1;
  if (!isNaN(nb)) return  1;
  return String(a).localeCompare(String(b));
});

// ═══════════════════════════════════════════════════════════
// A chip-input: tokens rendered as pills, add via Enter/comma, remove via ×.
// ═══════════════════════════════════════════════════════════
function ChipInput({ label, tokens, onChange, placeholder, testId }) {
  const [draft, setDraft] = useState("");

  const add = (raw) => {
    const items = String(raw || "")
      .split(/[,\n\t]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!items.length) return;
    const seen = new Set(tokens.map((t) => t.toLowerCase()));
    const additions = [];
    for (const it of items) {
      if (!seen.has(it.toLowerCase())) {
        additions.push(it);
        seen.add(it.toLowerCase());
      }
    }
    if (additions.length) onChange([...tokens, ...additions]);
    setDraft("");
  };

  return (
    <div className="space-y-1">
      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">{label}</div>
      <div
        className="min-h-[40px] w-full border-2 border-slate-300 bg-white px-2 py-1.5 flex flex-wrap gap-1.5 items-center focus-within:border-blue-500"
        onClick={(e) => {
          const el = e.currentTarget.querySelector("input");
          if (el) el.focus();
        }}
      >
        {tokens.map((t) => (
          <span
            key={t}
            data-testid={`chip-${testId}-${t}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-slate-100 border border-slate-300 font-mono"
          >
            {t}
            <button
              type="button"
              className="text-slate-400 hover:text-red-600"
              onClick={(ev) => {
                ev.stopPropagation();
                onChange(tokens.filter((x) => x !== t));
              }}
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          data-testid={testId}
          className="flex-1 min-w-[100px] outline-none text-sm py-0.5"
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && tokens.length) {
              onChange(tokens.slice(0, -1));
            }
          }}
          onBlur={() => draft.trim() && add(draft)}
          onPaste={(e) => {
            const t = e.clipboardData.getData("text");
            if (t.includes(",") || t.includes("\n") || t.includes("\t")) {
              e.preventDefault();
              add(t);
            }
          }}
        />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// TAB 1 — MATRIX ENTRY
// ═══════════════════════════════════════════════════════════
function MatrixEntryTab({ styles, initialStyleId, onDone }) {
  const [styleId, setStyleId]           = useState(initialStyleId || "");
  const [movementType, setMovementType] = useState("production_in");
  const [colors, setColors]             = useState([]);
  const [sizes, setSizes]               = useState([]);
  const [grid, setGrid]                 = useState({});  // "color|size" → qty (number as string)
  const [refId, setRefId]               = useState("");
  const [notes, setNotes]               = useState("");
  const [minStockLevel, setMinStockLevel] = useState(25);
  const [busy, setBusy]                 = useState(false);
  const [result, setResult]             = useState(null);
  const [prefilling, setPrefilling]     = useState(false);

  // When style changes, prefill colors/sizes with what already exists in FG for that style
  useEffect(() => {
    let cancel = false;
    async function prefill() {
      if (!styleId) { setColors([]); setSizes([]); return; }
      setPrefilling(true);
      try {
        const r = await http.get(`/fg-inventory/by-style/${styleId}`);
        if (cancel) return;
        setColors(r.data.colors || []);
        setSizes(sortSizes(r.data.sizes || []));
      } catch {
        if (!cancel) { setColors([]); setSizes([]); }
      } finally { if (!cancel) setPrefilling(false); }
    }
    prefill();
    return () => { cancel = true; };
  }, [styleId]);

  const sortedSizes = useMemo(() => sortSizes(sizes), [sizes]);

  const setCell = (color, size, val) => {
    setGrid((g) => ({ ...g, [`${color}|${size}`]: val }));
  };

  const total = useMemo(() => {
    let t = 0;
    for (const c of colors) for (const s of sortedSizes) {
      const v = parseInt(grid[`${c}|${s}`] || "0", 10);
      if (!isNaN(v) && v > 0) t += v;
    }
    return t;
  }, [grid, colors, sortedSizes]);

  const fillAll = (n) => {
    const g = { ...grid };
    for (const c of colors) for (const s of sortedSizes) g[`${c}|${s}`] = String(n);
    setGrid(g);
  };

  async function submit() {
    setResult(null);
    if (!styleId) return setResult({ error: "Please select a style." });
    if (!colors.length) return setResult({ error: "Add at least one color." });
    if (!sortedSizes.length) return setResult({ error: "Add at least one size." });

    // Build movement list from cells with qty > 0
    const movements = [];
    for (const c of colors) for (const s of sortedSizes) {
      const raw = grid[`${c}|${s}`];
      const q = parseInt(raw || "0", 10);
      if (!isNaN(q) && q > 0) {
        movements.push({
          style_id:       styleId,
          color:          c,
          size:           s,
          movement_type:  movementType,
          quantity:       q,
          reference_type: "manual",
          reference_id:   refId.trim(),
          notes:          notes.trim(),
        });
      }
    }
    if (!movements.length) return setResult({ error: "No cells have a positive quantity yet." });

    setBusy(true);
    try {
      const r = await http.post("/fg-inventory/bulk-movements", { movements });
      setResult({ ok: true, data: r.data });

      // Optional: patch min_stock_level for any newly-created rows if user set it
      if (Number(minStockLevel) && Number(minStockLevel) !== 25) {
        try {
          const list = await http.get(`/fg-inventory/by-style/${styleId}`);
          const rows = list.data.rows || [];
          const affected = new Set(movements.map((m) => `${m.color}|${m.size}`));
          await Promise.allSettled(
            rows
              .filter((row) => affected.has(`${row.color}|${row.size}`))
              .map((row) => http.patch(`/fg-inventory/${row.id}`, { min_stock_level: Number(minStockLevel) }))
          );
        } catch { /* non-fatal */ }
      }

      onDone && onDone();
    } catch (e) {
      setResult({ error: friendlyAxiosError(e) });
    } finally { setBusy(false); }
  }

  const canSubmit = styleId && colors.length && sortedSizes.length && total > 0;

  return (
    <div className="space-y-4">
      {/* Style + movement type header */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Style *</div>
          <select
            data-testid="mtx-style"
            className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            value={styleId}
            onChange={(e) => setStyleId(e.target.value)}
          >
            <option value="">— Select style —</option>
            {styles.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
          </select>
        </div>
        <Select label="Movement Type" testId="mtx-movement-type"
          value={movementType} onChange={(e) => setMovementType(e.target.value)}>
          {MOVEMENT_TYPES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </div>

      {/* Axis definitions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <ChipInput label="Colors (row axis)"
          tokens={colors}
          onChange={setColors}
          placeholder="e.g. SILVER, GOLD"
          testId="mtx-colors" />
        <ChipInput label="Sizes (column axis)"
          tokens={sortedSizes}
          onChange={(next) => setSizes(sortSizes(next))}
          placeholder="e.g. 36, 37, 38, 39, 40, 41"
          testId="mtx-sizes" />
      </div>
      {prefilling && (
        <div className="text-[11px] text-slate-400 italic">Prefilling with this style's existing colors & sizes…</div>
      )}

      {/* The grid itself */}
      {colors.length > 0 && sortedSizes.length > 0 ? (
        <div className="border-2 border-slate-200 overflow-x-auto">
          <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 flex items-center gap-1.5">
              <Grid3x3 className="w-3 h-3" /> Enter Quantities
            </div>
            <div className="flex items-center gap-2 text-[10px] uppercase font-bold">
              <button
                data-testid="mtx-fill-all"
                onClick={() => {
                  const v = prompt("Fill every cell with this quantity:", "10");
                  if (v !== null && !isNaN(parseInt(v, 10))) fillAll(parseInt(v, 10));
                }}
                className="px-2 py-1 border border-slate-300 hover:border-slate-900 text-slate-600 hover:text-slate-900 tracking-wider"
              >
                Fill All
              </button>
              <button
                data-testid="mtx-clear-all"
                onClick={() => setGrid({})}
                className="px-2 py-1 border border-slate-300 hover:border-red-600 text-slate-600 hover:text-red-600 tracking-wider"
              >
                Clear
              </button>
            </div>
          </div>

          <table className="w-full text-xs">
            <thead className="bg-slate-100">
              <tr>
                <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider font-bold text-slate-700 border-r border-slate-300">
                  Color \ Size
                </th>
                {sortedSizes.map((sz) => (
                  <th key={sz} className="px-2 py-1.5 text-center font-mono text-[11px] font-bold text-slate-700 border-r border-slate-300 min-w-[64px]">
                    {sz}
                  </th>
                ))}
                <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-bold text-slate-900 bg-slate-200 min-w-[60px]">
                  Row Σ
                </th>
              </tr>
            </thead>
            <tbody>
              {colors.map((c) => {
                let rowTotal = 0;
                for (const s of sortedSizes) {
                  const v = parseInt(grid[`${c}|${s}`] || "0", 10);
                  if (!isNaN(v) && v > 0) rowTotal += v;
                }
                return (
                  <tr key={c} className="border-t border-slate-200">
                    <td className="px-2 py-1 font-bold text-slate-800 border-r border-slate-200 whitespace-nowrap">{c}</td>
                    {sortedSizes.map((s) => (
                      <td key={s} className="p-0 border-r border-slate-200">
                        <input
                          data-testid={`mtx-cell-${c}-${s}`}
                          type="number"
                          min="0"
                          value={grid[`${c}|${s}`] ?? ""}
                          onChange={(e) => setCell(c, s, e.target.value)}
                          placeholder="0"
                          className="w-full h-full py-1.5 px-1 text-center font-mono text-sm focus:outline-none focus:bg-blue-50 focus:ring-1 focus:ring-blue-500"
                        />
                      </td>
                    ))}
                    <td className="px-2 py-1 text-right font-mono font-bold bg-[#0F172A] text-[#C27842]">
                      {rowTotal}
                    </td>
                  </tr>
                );
              })}
              <tr className="border-t-2 border-slate-400 bg-slate-100">
                <td className="px-2 py-1.5 font-bold text-[10px] uppercase tracking-wider text-slate-900 border-r border-slate-300">
                  Col Σ
                </td>
                {sortedSizes.map((s) => {
                  let colTotal = 0;
                  for (const c of colors) {
                    const v = parseInt(grid[`${c}|${s}`] || "0", 10);
                    if (!isNaN(v) && v > 0) colTotal += v;
                  }
                  return (
                    <td key={s} className="px-2 py-1.5 text-center font-mono font-bold text-slate-900 border-r border-slate-300">
                      {colTotal}
                    </td>
                  );
                })}
                <td className="px-2 py-1.5 text-right font-mono font-bold bg-[#C27842] text-white">
                  {total}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="border-2 border-dashed border-slate-200 px-4 py-6 text-center text-xs text-slate-400">
          {styleId
            ? "Add at least one color and one size to start the grid."
            : "Select a style to begin."}
        </div>
      )}

      {/* Metadata & submit */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Input label="Reference ID (optional)" testId="mtx-ref-id"
          value={refId} onChange={(e) => setRefId(e.target.value)}
          placeholder="e.g. PO / Job number" />
        <Input label="Notes (optional)" testId="mtx-notes"
          value={notes} onChange={(e) => setNotes(e.target.value)}
          placeholder="e.g. First lot from prod. floor" />
        <Input label="Min-stock-level for new cells" testId="mtx-min"
          type="number" value={minStockLevel}
          onChange={(e) => setMinStockLevel(e.target.value)} />
      </div>

      {result?.error && (
        <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>{result.error}</div>
        </div>
      )}

      {result?.ok && (
        <div className="bg-green-50 border-2 border-green-300 px-4 py-3 text-sm text-green-800">
          <div className="font-bold flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" />
            {result.data.success} of {result.data.total} movements applied
            {result.data.failed > 0 && ` — ${result.data.failed} failed`}
          </div>
          {result.data.failed > 0 && (
            <ul className="text-xs mt-2 space-y-0.5">
              {result.data.results.filter((r) => !r.ok).slice(0, 8).map((r, i) => (
                <li key={i} className="text-red-700 font-mono">
                  row {r.index}: {r.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex gap-3 pt-2 sticky bottom-0 bg-white py-2">
        <BtnPrimary
          data-testid="mtx-submit"
          disabled={!canSubmit || busy}
          onClick={submit}
          className="flex-1"
        >
          {busy
            ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Applying…</span>
            : <span className="flex items-center justify-center gap-2"><Rows3 className="w-4 h-4" /> Apply Matrix ({total} pairs)</span>
          }
        </BtnPrimary>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// TAB 2 — CSV UPLOAD
// ═══════════════════════════════════════════════════════════
function CsvUploadTab({ onDone }) {
  const [file, setFile]       = useState(null);
  const [preview, setPreview] = useState(null);   // { parsed, errors, summary }
  const [result, setResult]   = useState(null);   // { summary, results, parse_errors }
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState("");

  const downloadTemplate = async () => {
    try {
      const r = await http.get("/fg-inventory/csv-template", { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "fg_stock_template.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(friendlyAxiosError(e));
    }
  };

  const doDryRun = async (f) => {
    setError(""); setPreview(null); setResult(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await http.post("/fg-inventory/import-csv?dry_run=true", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(r.data);
    } catch (e) {
      setError(friendlyAxiosError(e));
    } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!file) return;
    setError(""); setResult(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post("/fg-inventory/import-csv?dry_run=false", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(r.data);
      onDone && onDone();
    } catch (e) {
      setError(friendlyAxiosError(e));
    } finally { setBusy(false); }
  };

  const onPickFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setResult(null);
    doDryRun(f);
  };

  return (
    <div className="space-y-4">
      <div className="bg-slate-100 border-2 border-slate-200 px-4 py-3 text-xs text-slate-700 space-y-1">
        <div className="font-bold uppercase tracking-wider text-[10px] text-slate-500">
          CSV Bulk Import
        </div>
        <div>Required columns: <span className="font-mono">style_code, color, size, quantity</span></div>
        <div>Optional: <span className="font-mono">movement_type</span> (default <span className="font-mono">production_in</span>), <span className="font-mono">reference_id</span>, <span className="font-mono">notes</span></div>
        <div className="italic text-slate-500">Rows with quantity == 0 are silently skipped.</div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <BtnSecondary onClick={downloadTemplate} data-testid="csv-download-template">
          <span className="flex items-center gap-1.5"><Download className="w-4 h-4" /> Download Template</span>
        </BtnSecondary>

        <label className="cursor-pointer">
          <span className="inline-flex items-center gap-1.5 text-sm font-bold uppercase tracking-wider text-white bg-[#0F172A] hover:bg-[#C27842] border-2 border-[#0F172A] hover:border-[#C27842] px-4 py-2 transition-colors">
            <FileUp className="w-4 h-4" /> {file ? "Change File" : "Choose CSV"}
          </span>
          <input
            type="file"
            accept=".csv,text/csv"
            data-testid="csv-file-input"
            className="hidden"
            onChange={onPickFile}
          />
        </label>
        {file && (
          <div className="text-xs text-slate-600 font-mono flex items-center gap-1.5">
            <FileSpreadsheet className="w-3.5 h-3.5" />
            {file.name} · {(file.size / 1024).toFixed(1)} KB
          </div>
        )}
      </div>

      {busy && (
        <div className="text-sm text-slate-500 flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Processing…
        </div>
      )}

      {error && (
        <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold">
          {error}
        </div>
      )}

      {/* Dry-run preview */}
      {preview && !result && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="border-2 border-slate-200 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Total Rows</div>
              <div className="text-2xl font-bold font-mono">{preview.summary.total_rows_seen}</div>
            </div>
            <div className="border-2 border-green-200 bg-green-50 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-green-700">Valid</div>
              <div className="text-2xl font-bold font-mono text-green-800">{preview.summary.valid}</div>
            </div>
            <div className={`border-2 px-3 py-2 ${preview.summary.invalid ? "border-red-200 bg-red-50" : "border-slate-200"}`}>
              <div className={`text-[10px] uppercase tracking-wider font-bold ${preview.summary.invalid ? "text-red-700" : "text-slate-500"}`}>Errors</div>
              <div className={`text-2xl font-bold font-mono ${preview.summary.invalid ? "text-red-700" : "text-slate-300"}`}>
                {preview.summary.invalid}
              </div>
            </div>
          </div>

          {preview.errors.length > 0 && (
            <div className="border-2 border-red-200 bg-red-50 max-h-40 overflow-y-auto">
              <div className="px-3 py-1.5 text-[10px] uppercase font-bold text-red-800 tracking-wider bg-red-100 border-b border-red-200">
                Parse Errors
              </div>
              <ul className="p-3 text-xs space-y-0.5">
                {preview.errors.slice(0, 50).map((e, i) => (
                  <li key={i} className="font-mono text-red-800">line {e.line} — {e.error}</li>
                ))}
              </ul>
            </div>
          )}

          {preview.parsed.length > 0 && (
            <div className="border-2 border-slate-200 max-h-64 overflow-y-auto">
              <div className="px-3 py-1.5 text-[10px] uppercase font-bold text-slate-700 tracking-wider bg-slate-50 border-b border-slate-200 flex items-center gap-1.5">
                <Layers className="w-3 h-3" /> Preview — first 30 valid rows
              </div>
              <table className="w-full text-xs">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    {["Line", "Style ID", "Color", "Size", "Type", "Qty", "Notes"].map((h) => (
                      <th key={h} className="px-2 py-1.5 text-left text-[10px] uppercase font-bold text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.parsed.slice(0, 30).map((r) => (
                    <tr key={r._line}>
                      <td className="px-2 py-1 font-mono text-slate-400">{r._line}</td>
                      <td className="px-2 py-1 font-mono">{String(r.style_id).slice(-6)}</td>
                      <td className="px-2 py-1">{r.color}</td>
                      <td className="px-2 py-1">{r.size}</td>
                      <td className="px-2 py-1"><Badge color="slate">{r.movement_type}</Badge></td>
                      <td className="px-2 py-1 font-mono font-bold">{r.quantity}</td>
                      <td className="px-2 py-1 text-slate-500 text-[11px]">{r.notes || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {preview.summary.valid > 0 && (
            <div className="flex gap-3 pt-2 sticky bottom-0 bg-white py-2">
              <BtnPrimary
                data-testid="csv-commit"
                disabled={busy}
                onClick={commit}
                className="flex-1"
              >
                {busy
                  ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Committing…</span>
                  : `Import ${preview.summary.valid} valid row${preview.summary.valid === 1 ? "" : "s"}`
                }
              </BtnPrimary>
              <BtnSecondary onClick={() => { setFile(null); setPreview(null); }}>Cancel</BtnSecondary>
            </div>
          )}
        </>
      )}

      {/* Post-commit result */}
      {result && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="border-2 border-slate-200 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Attempted</div>
              <div className="text-2xl font-bold font-mono">{result.summary.attempted}</div>
            </div>
            <div className="border-2 border-green-200 bg-green-50 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-green-700">Applied</div>
              <div className="text-2xl font-bold font-mono text-green-800">{result.summary.success}</div>
            </div>
            <div className={`border-2 px-3 py-2 ${result.summary.failed ? "border-red-200 bg-red-50" : "border-slate-200"}`}>
              <div className={`text-[10px] uppercase tracking-wider font-bold ${result.summary.failed ? "text-red-700" : "text-slate-500"}`}>Failed</div>
              <div className={`text-2xl font-bold font-mono ${result.summary.failed ? "text-red-700" : "text-slate-300"}`}>
                {result.summary.failed}
              </div>
            </div>
          </div>
          {result.summary.failed > 0 && (
            <div className="border-2 border-red-200 bg-red-50 max-h-52 overflow-y-auto">
              <div className="px-3 py-1.5 text-[10px] uppercase font-bold text-red-800 tracking-wider bg-red-100 border-b border-red-200">
                Failed rows
              </div>
              <ul className="p-3 text-xs space-y-0.5">
                {result.results.filter((r) => !r.ok).slice(0, 100).map((r, i) => (
                  <li key={i} className="font-mono text-red-800">line {r.line ?? "?"} — {r.error}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <BtnSecondary onClick={() => { setFile(null); setPreview(null); setResult(null); }}>
              Import another file
            </BtnSecondary>
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Main drawer with tabs
// ═══════════════════════════════════════════════════════════
export default function AddStockDrawer({ styles = [], initialStyleId = "", onClose, onDone }) {
  const [tab, setTab] = useState("matrix");

  return (
    <Drawer onClose={onClose} title="Add Stock in Bulk" width="max-w-4xl">
      <div className="border-b-2 border-slate-200 -mt-2 mb-4">
        <div className="flex gap-1">
          <button
            data-testid="tab-matrix"
            onClick={() => setTab("matrix")}
            className={`px-4 py-2 text-xs font-bold uppercase tracking-wider border-b-4 transition-colors ${
              tab === "matrix"
                ? "text-[#0F172A] border-[#C27842]"
                : "text-slate-500 border-transparent hover:text-slate-900"
            }`}
          >
            <span className="flex items-center gap-1.5"><Grid3x3 className="w-4 h-4" /> Matrix Entry</span>
          </button>
          <button
            data-testid="tab-csv"
            onClick={() => setTab("csv")}
            className={`px-4 py-2 text-xs font-bold uppercase tracking-wider border-b-4 transition-colors ${
              tab === "csv"
                ? "text-[#0F172A] border-[#C27842]"
                : "text-slate-500 border-transparent hover:text-slate-900"
            }`}
          >
            <span className="flex items-center gap-1.5"><FileUp className="w-4 h-4" /> CSV Upload</span>
          </button>
        </div>
      </div>

      {tab === "matrix"
        ? <MatrixEntryTab styles={styles} initialStyleId={initialStyleId} onDone={onDone} />
        : <CsvUploadTab onDone={onDone} />}
    </Drawer>
  );
}
