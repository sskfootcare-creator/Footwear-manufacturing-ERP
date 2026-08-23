import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { http, formatApiError } from "../lib/api";
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
import SearchableSelect from "../components/SearchableSelect";
import {
  Plus, Trash2, Pencil, Save, X, ArrowLeftRight,
  Upload, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight,
  Download, Copy, Check, FileSpreadsheet, RefreshCw, FileText, ExternalLink, Image as ImageIcon,
  Link2, Unlink, Layers, ChevronUp, Info,
} from "lucide-react";

// ── constants ──────────────────────────────────────────────
const ONLINE_CHANNELS = ["myntra", "flipkart", "nykaa", "website"];
const SOURCE_TYPE_LABELS = { b2b_client: "B2B Client", online_channel: "Online Channel" };

const emptyForm = {
  style_id: "", source_type: "b2b_client", source_name: "",
  external_sku: "", external_style_name: "", image_url: "",
  color_map: [], size_map: [],
};

// ── helpers ───────────────────────────────────────────────
function dictToRows(obj = {}) {
  return Object.entries(obj).map(([from, to]) => ({ from, to }));
}
function rowsToDict(rows = []) {
  const d = {};
  rows.forEach(({ from, to }) => { if (from.trim()) d[from.trim()] = to.trim(); });
  return d;
}

function KVPairs({ label, rows, onChange }) {
  const addRow = () => onChange([...rows, { from: "", to: "" }]);
  const removeRow = (i) => onChange(rows.filter((_, idx) => idx !== i));
  const edit = (i, field, val) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)));
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">{label}</div>
        <button type="button" onClick={addRow}
          className="text-[10px] font-bold uppercase tracking-wider text-blue-600 hover:text-blue-800 flex items-center gap-1">
          <Plus className="w-3 h-3" /> Add row
        </button>
      </div>
      {rows.length === 0 && <div className="text-xs text-slate-400 italic">No entries yet.</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <input className="flex-1 border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-blue-500 focus:outline-none"
            placeholder="External (from)" value={r.from} onChange={(e) => edit(i, "from", e.target.value)} />
          <span className="text-slate-400 font-bold">→</span>
          <input className="flex-1 border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-blue-500 focus:outline-none"
            placeholder="Internal (to)" value={r.to} onChange={(e) => edit(i, "to", e.target.value)} />
          <button type="button" onClick={() => removeRow(i)} className="text-red-400 hover:text-red-600 transition-colors flex-shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ── Unmapped tab ──────────────────────────────────────────
function UnmappedTab({ styles, onDone }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  // Map modal states
  const [mappingTarget, setMappingTarget] = useState(null);
  const [mapMode, setMapMode] = useState("existing"); // "existing" | "new"
  const [selectedStyleId, setSelectedStyleId] = useState("");
  const [newStyleForm, setNewStyleForm] = useState({
    code: "", name: "", category: "Footwear", description: "",
    base_size: "7", overhead_pct: 8, packing_cost: 12, margin_pct: 25, gst_pct: 5,
  });
  const [styleSearch, setStyleSearch] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await http.get("/sku-map/unmapped");
      setGroups(r.data || []);
    } catch {
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (mappingTarget) {
      setNewStyleForm({
        code: mappingTarget.external_sku,
        name: `Style ${mappingTarget.external_sku}`,
        category: "Footwear",
        description: `Created from unmapped SKU ${mappingTarget.external_sku}`,
        base_size: "7",
        overhead_pct: 8,
        packing_cost: 12,
        margin_pct: 25,
        gst_pct: 5,
      });
      setSubmitError("");
      setSelectedStyleId("");
      setMapMode("existing");
    }
  }, [mappingTarget]);

  const filteredStylesList = useMemo(() => {
    if (!styleSearch) return styles;
    const s = styleSearch.toLowerCase();
    return styles.filter((st) =>
      st.code?.toLowerCase().includes(s) ||
      st.name?.toLowerCase().includes(s)
    );
  }, [styles, styleSearch]);

  const handleConfirmMapping = async () => {
    setSubmitError("");
    setSubmitting(true);
    try {
      let styleId = selectedStyleId;

      if (mapMode === "new") {
        if (!newStyleForm.code.trim() || !newStyleForm.name.trim()) {
          setSubmitError("Style Code and Name are required.");
          setSubmitting(false);
          return;
        }
        const styleRes = await http.post("/styles", {
          code: newStyleForm.code.trim(),
          name: newStyleForm.name.trim(),
          category: newStyleForm.category,
          description: newStyleForm.description,
          base_size: newStyleForm.base_size,
          overhead_pct: Number(newStyleForm.overhead_pct),
          packing_cost: Number(newStyleForm.packing_cost),
          margin_pct: Number(newStyleForm.margin_pct),
          gst_pct: Number(newStyleForm.gst_pct),
        });
        styleId = styleRes.data.id;
      }

      if (!styleId) {
        setSubmitError("Please select a style to map.");
        setSubmitting(false);
        return;
      }

      await http.post("/sku-map", {
        style_id: styleId,
        source_type: mappingTarget.source_type,
        source_name: mappingTarget.source_name,
        external_sku: mappingTarget.external_sku,
        external_style_name: "",
        color_map: {},
        size_map: {},
      });

      setMappingTarget(null);
      reload();
      if (onDone) onDone();
    } catch (e) {
      setSubmitError(e.response?.data?.detail || "Mapping failed.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20 text-slate-400">Loading unmapped items…</div>;

  if (groups.length === 0)
    return (
      <Card className="p-10 text-center">
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
        <div className="text-slate-600 font-semibold mb-1">All styles are mapped!</div>
        <div className="text-xs text-slate-400">No production jobs have unresolved style codes.</div>
      </Card>
    );

  return (
    <div className="space-y-3">
      {groups.map((g) => {
        const key = `${g.source_type}:${g.source_name}`;
        const isOpen = !!expanded[key];
        return (
          <Card key={key} className="overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-slate-50 transition-colors"
              onClick={() => setExpanded((e) => ({ ...e, [key]: !isOpen }))}
            >
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <div>
                  <div className="font-bold text-slate-900">{g.source_name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    <Badge color="blue">{SOURCE_TYPE_LABELS[g.source_type] || g.source_type}</Badge>
                    <span className="ml-2">{g.job_count} job{g.job_count !== 1 ? "s" : ""} unresolved</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right hidden sm:block">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">External SKUs</div>
                  <div className="text-xs font-mono text-slate-700 truncate max-w-[220px]">
                    {(g.external_skus || []).slice(0, 4).join(", ")}{(g.external_skus || []).length > 4 ? ` +${g.external_skus.length - 4} more` : ""}
                  </div>
                </div>
                {isOpen ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-slate-100 p-4 space-y-4">
                <div className="bg-slate-50 p-3 border border-slate-200">
                  <div className="text-[10px] uppercase font-bold text-slate-500 mb-2">Unresolved SKUs:</div>
                  <div className="flex flex-wrap gap-2">
                    {(g.external_skus || []).map((sku) => (
                      <div key={sku} className="flex items-center gap-2 bg-white border border-slate-300 px-2.5 py-1.5 font-mono text-xs">
                        <span className="font-bold text-slate-800">{sku}</span>
                        <button
                          onClick={() => setMappingTarget({
                            source_type: g.source_type,
                            source_name: g.source_name,
                            external_sku: sku,
                          })}
                          className="bg-[#0F172A] hover:bg-slate-800 text-white text-[10px] uppercase font-bold px-2 py-1 transition-colors"
                        >
                          Map to Style
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-left">
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">PO #</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">External SKU</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Color</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Size</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Qty</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Stage</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(g.jobs || []).map((j) => (
                        <tr key={j.id} className="hover:bg-amber-50 transition-colors">
                          <td className="px-4 py-2 font-mono text-xs">{j.po_number}</td>
                          <td className="px-4 py-2 font-mono font-bold text-red-700">{j.style_code}</td>
                          <td className="px-4 py-2 text-xs text-slate-600">{j.color || "—"}</td>
                          <td className="px-4 py-2 text-xs text-slate-600">{j.size || "—"}</td>
                          <td className="px-4 py-2 text-xs">{j.quantity}</td>
                          <td className="px-4 py-2">
                            <Badge color="yellow">{j.stage}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </Card>
        );
      })}

      {mappingTarget && (
        <Drawer onClose={() => setMappingTarget(null)} title="Map External Code to Style">
          <div className="space-y-4">
            <div className="bg-slate-100 p-3 border border-slate-200 font-mono text-xs space-y-1">
              <div><span className="text-slate-400 font-bold">SOURCE TYPE:</span> {SOURCE_TYPE_LABELS[mappingTarget.source_type]}</div>
              <div><span className="text-slate-400 font-bold">SOURCE NAME:</span> {mappingTarget.source_name}</div>
              <div><span className="text-slate-400 font-bold">EXTERNAL SKU:</span> {mappingTarget.external_sku}</div>
            </div>

            <div className="flex gap-4 border-b border-slate-200 pb-2">
              <button
                type="button"
                className={`text-xs uppercase tracking-wider font-bold pb-1 border-b-2 ${mapMode === "existing" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400"}`}
                onClick={() => setMapMode("existing")}
              >
                Map to Existing Style
              </button>
              <button
                type="button"
                className={`text-xs uppercase tracking-wider font-bold pb-1 border-b-2 ${mapMode === "new" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400"}`}
                onClick={() => setMapMode("new")}
              >
                Create New Style
              </button>
            </div>

            {mapMode === "existing" ? (
              <div className="space-y-3">
                <Input
                  label="Search Styles"
                  placeholder="Type style code or name..."
                  value={styleSearch}
                  onChange={(e) => setStyleSearch(e.target.value)}
                />
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Select Style *</div>
                  <select
                    className="w-full border-2 border-slate-300 p-2 text-sm focus:outline-none bg-white"
                    value={selectedStyleId}
                    onChange={(e) => setSelectedStyleId(e.target.value)}
                  >
                    <option value="">— Select Style —</option>
                    {filteredStylesList.map((s) => (
                      <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Style Code *"
                    value={newStyleForm.code}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, code: e.target.value })}
                  />
                  <Input
                    label="Style Name *"
                    value={newStyleForm.name}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, name: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Category"
                    value={newStyleForm.category}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, category: e.target.value })}
                  />
                  <Input
                    label="Base Size"
                    value={newStyleForm.base_size}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, base_size: e.target.value })}
                  />
                </div>
                <Input
                  label="Description"
                  value={newStyleForm.description}
                  onChange={(e) => setNewStyleForm({ ...newStyleForm, description: e.target.value })}
                />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Input
                    label="Overhead%"
                    type="number"
                    value={newStyleForm.overhead_pct}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, overhead_pct: e.target.value })}
                  />
                  <Input
                    label="Packing₹"
                    type="number"
                    value={newStyleForm.packing_cost}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, packing_cost: e.target.value })}
                  />
                  <Input
                    label="Margin%"
                    type="number"
                    value={newStyleForm.margin_pct}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, margin_pct: e.target.value })}
                  />
                  <Input
                    label="GST%"
                    type="number"
                    value={newStyleForm.gst_pct}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, gst_pct: e.target.value })}
                  />
                </div>
              </div>
            )}

            {submitError && (
              <div className="bg-red-50 border border-red-300 p-2 text-xs text-red-700 font-semibold">{submitError}</div>
            )}

            <div className="flex gap-2 pt-2">
              <BtnPrimary onClick={handleConfirmMapping} disabled={submitting} className="flex-1">
                {submitting ? "Processing..." : "Confirm & Map"}
              </BtnPrimary>
              <BtnSecondary onClick={() => setMappingTarget(null)} disabled={submitting}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}

// ── Bulk import drawer ────────────────────────────────────
function BulkImportDrawer({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const fileRef = useRef();

  const STAGE2_CSV_SAMPLE = `style_code,color,size,external_sku,source_type,source_name,external_style_name,image_url
SSK-OXF-01,Tan,8 UK,MYN-OXF-TAN-8,online_channel,myntra,Classic Oxford Formal Shoes,https://www.dropbox.com/s/sample/shoe.jpg?dl=0
SSK-OXF-01,Tan,9 UK,MYN-OXF-TAN-9,online_channel,myntra,Classic Oxford Formal Shoes,
SSK-OXF-01,Black,8 UK,MYN-OXF-BLK-8,online_channel,myntra,Classic Oxford Formal Shoes,
SSK-MOC-02,Navy,7 UK,BAT-MOC-NAV-7,b2b_client,Bata India Ltd,Navy Suede Moccasin,`;

  function downloadCsvTemplate() {
    const blob = new Blob([STAGE2_CSV_SAMPLE], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "sku_mapping_template.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function downloadXlsxTemplate() {
    try {
      const res = await http.get("/sku-map/template?format=xlsx", { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "sku_mapping_template.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      // Fallback to CSV if network fails
      downloadCsvTemplate();
    }
  }

  async function submit() {
    setError("");
    if (!file) return setError("Please choose a .xlsx or .csv template file to upload.");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post("/sku-map/bulk", fd);
      setResult(r.data);
      if (onDone) onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer?.files?.[0]) {
      const f = e.dataTransfer.files[0];
      const name = f.name.toLowerCase();
      if (name.endsWith(".xlsx") || name.endsWith(".xlsm") || name.endsWith(".csv")) {
        setFile(f);
        setError("");
      } else {
        setError("Only .xlsx or .csv files are supported.");
      }
    }
  }

  function copyErrorsToClipboard() {
    if (!result?.errors?.length) return;
    const text = result.errors.map((e) => `Row ${e.row}: ${e.reason}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadErrorReport() {
    if (!result?.errors?.length) return;
    let csvContent = "row,reason\n";
    result.errors.forEach((e) => {
      csvContent += `${e.row},"${(e.reason || "").replace(/"/g, '""')}"\n`;
    });
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `sku_map_upload_errors_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function resetForNewUpload() {
    setFile(null);
    setResult(null);
    setError("");
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <Drawer onClose={onClose} title="Bulk Import SKU Mappings (Stage 2)">
      <div className="space-y-5">
        {/* Template Instructions & Downloads */}
        <div className="bg-slate-900 text-white p-4 border border-slate-800 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-wider font-bold text-amber-400">Stage 2 Template Format</div>
              <div className="text-xs text-slate-300 mt-1">
                Upload your marketplace or client SKU sheets (.xlsx or .csv). Rows are grouped by <span className="text-white font-semibold font-mono">style + source + color</span> into mapping documents.
              </div>
            </div>
          </div>

          <div className="text-[11px] text-slate-300 font-mono bg-slate-950/60 p-2.5 border border-slate-800 rounded space-y-1">
            <div><span className="text-emerald-400 font-bold">Required:</span> style_code, color, size, external_sku, source_type, source_name</div>
            <div><span className="text-blue-400 font-bold">Optional:</span> external_style_name, image_url</div>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              id="btn-download-xlsx-template"
              onClick={downloadXlsxTemplate}
              className="inline-flex items-center gap-1.5 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold text-xs px-3 py-1.5 transition-colors shadow-sm"
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              Download Template (.xlsx)
            </button>
            <button
              type="button"
              id="btn-download-csv-template"
              onClick={downloadCsvTemplate}
              className="inline-flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs px-3 py-1.5 transition-colors border border-slate-700"
            >
              <Download className="w-3.5 h-3.5" />
              Download (.csv)
            </button>
          </div>
        </div>

        {/* Upload Dropzone */}
        {!result && (
          <div className="space-y-3">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Select or Drag File *</div>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                isDragging
                  ? "border-amber-500 bg-amber-50"
                  : file
                  ? "border-emerald-500 bg-emerald-50/40"
                  : "border-slate-300 hover:border-slate-500 bg-white"
              }`}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? "text-emerald-600" : "text-slate-400"}`} />
              {file ? (
                <div className="space-y-1">
                  <div className="text-sm font-mono font-bold text-slate-900">{file.name}</div>
                  <div className="text-xs text-slate-500 font-mono">
                    {(file.size / 1024).toFixed(1)} KB · Ready to import
                  </div>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); resetForNewUpload(); }}
                    className="text-xs text-red-600 hover:underline font-semibold mt-2"
                  >
                    Change file
                  </button>
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="text-sm font-semibold text-slate-700">Click to browse or drag file here</div>
                  <div className="text-xs text-slate-400">Supports .xlsx, .xlsm, or .csv</div>
                </div>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xlsm,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) {
                  setFile(e.target.files[0]);
                  setError("");
                }
              }}
            />
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="bg-red-50 border-2 border-red-300 p-3 text-xs text-red-700 font-semibold flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
            <div>{error}</div>
          </div>
        )}

        {/* Upload Results Summary View */}
        {result && (
          <div className="space-y-4 bg-slate-50 p-4 border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="text-xs uppercase tracking-wider font-bold text-slate-700">Import Results</div>
              <button
                type="button"
                onClick={resetForNewUpload}
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Upload Another
              </button>
            </div>

            {/* Counts Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="bg-emerald-50 border border-emerald-300 p-2.5 text-center">
                <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-800">Created</div>
                <div className="text-2xl font-bold font-mono text-emerald-700">{result.created}</div>
              </div>
              <div className="bg-blue-50 border border-blue-300 p-2.5 text-center">
                <div className="text-[10px] uppercase tracking-wider font-bold text-blue-800">Updated</div>
                <div className="text-2xl font-bold font-mono text-blue-700">{result.updated}</div>
              </div>
              <div className={`p-2.5 text-center border ${result.warnings?.length ? "bg-amber-50 border-amber-300" : "bg-slate-100 border-slate-200"}`}>
                <div className="text-[10px] uppercase tracking-wider font-bold text-amber-800">Warnings</div>
                <div className="text-2xl font-bold font-mono text-amber-700">{result.warnings?.length || 0}</div>
              </div>
              <div className={`p-2.5 text-center border ${result.errors?.length ? "bg-red-50 border-red-300" : "bg-slate-100 border-slate-200"}`}>
                <div className="text-[10px] uppercase tracking-wider font-bold text-red-800">Errors</div>
                <div className="text-2xl font-bold font-mono text-red-700">{result.errors?.length || 0}</div>
              </div>
            </div>

            {/* Warnings Section */}
            {result.warnings?.length > 0 && (
              <div className="bg-amber-50 border border-amber-300 p-3 space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                  <span>{result.warnings.length} Warning{result.warnings.length !== 1 ? "s" : ""}</span>
                </div>
                <div className="space-y-1.5 max-h-36 overflow-y-auto text-xs font-mono text-amber-900 pr-1">
                  {result.warnings.map((w, i) => (
                    <div key={i} className="bg-white/80 p-1.5 border border-amber-200 rounded">
                      <span className="font-bold text-amber-700">Row {w.row}:</span> {w.reason}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Errors Section */}
            {result.errors?.length > 0 ? (
              <div className="bg-red-50 border border-red-300 p-3 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-red-900">
                    <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                    <span>{result.errors.length} Error{result.errors.length !== 1 ? "s" : ""} (Action Required)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={copyErrorsToClipboard}
                      className="inline-flex items-center gap-1 text-[11px] font-bold bg-white text-slate-700 hover:bg-slate-100 px-2 py-1 border border-slate-300 shadow-sm"
                      title="Copy errors to clipboard"
                    >
                      {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                      {copied ? "Copied!" : "Copy Errors"}
                    </button>
                    <button
                      type="button"
                      onClick={downloadErrorReport}
                      className="inline-flex items-center gap-1 text-[11px] font-bold bg-white text-slate-700 hover:bg-slate-100 px-2 py-1 border border-slate-300 shadow-sm"
                      title="Download CSV report of error rows"
                    >
                      <Download className="w-3 h-3" />
                      Export CSV
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto max-h-52 overflow-y-auto border border-red-200 bg-white">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-red-100 text-red-900 sticky top-0 font-sans font-bold text-[10px] uppercase tracking-wider">
                      <tr>
                        <th className="px-3 py-1.5 w-16">Row</th>
                        <th className="px-3 py-1.5">Problem / Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-red-100">
                      {result.errors.map((e, i) => (
                        <tr key={i} className="hover:bg-red-50/60">
                          <td className="px-3 py-1.5 font-bold text-red-700 align-top">#{e.row}</td>
                          <td className="px-3 py-1.5 text-slate-800">{e.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-[11px] text-slate-600 italic">
                  Tip: Fix the highlighted rows in your sheet and re-upload. Existing valid mappings will automatically merge and update without duplicate entries.
                </div>
              </div>
            ) : (
              <div className="bg-emerald-50 border border-emerald-300 p-3 text-xs text-emerald-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>All valid rows were processed smoothly with 0 errors!</span>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3 pt-2">
          {!result ? (
            <BtnPrimary id="btn-bulk-upload" onClick={submit} disabled={uploading || !file} className="flex-1">
              <span className="flex items-center justify-center gap-2">
                <Upload className="w-4 h-4" />
                {uploading ? "Importing…" : "Upload & Import"}
              </span>
            </BtnPrimary>
          ) : (
            <BtnPrimary
              id="btn-done-refresh"
              onClick={() => { if (onDone) onDone(); onClose(); }}
              className="flex-1"
            >
              <span className="flex items-center justify-center gap-2">
                <Check className="w-4 h-4" /> Done & View Mappings
              </span>
            </BtnPrimary>
          )}
          <BtnSecondary onClick={onClose} disabled={uploading}>
            {result ? "Close" : "Cancel"}
          </BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

// ── Listing Import Drawer (Stage 1 → Stage 2) ────────────
const PLATFORMS = [
  { value: "myntra",   label: "Myntra" },
  { value: "flipkart", label: "Flipkart" },
  { value: "nykaa",    label: "Nykaa" },
  { value: "ajio",     label: "Ajio" },
  { value: "amazon",   label: "Amazon" },
  { value: "website",  label: "Website / Direct" },
  { value: "other",    label: "Other / Unknown" },
];

const SOURCE_TYPE_BY_PLATFORM = {
  myntra: "online_channel", flipkart: "online_channel", nykaa: "online_channel",
  ajio: "online_channel", amazon: "online_channel", website: "online_channel",
  other: "b2b_client",
};

/** A single group card inside Stage 2. */
function GroupCard({ group, decision, onDecide, styles }) {
  const [expanded, setExpanded] = useState(false);

  const linked    = decision?.style_id != null;
  const unlinked  = decision != null && decision.style_id == null;
  const undecided = decision == null;

  const selectedStyle = styles.find((s) => s.id === decision?.style_id);

  // Sibling colour labels for the hint
  const siblingColors = (group.sibling_group_keys || []).map((sk) => {
    const parts = sk.split("/");
    return parts[parts.length - 1]; // colour part after last "/"
  });

  const statusDot = undecided
    ? "bg-slate-300"
    : linked
    ? "bg-emerald-500"
    : "bg-amber-400";

  const cardBorder = undecided
    ? "border-slate-200"
    : linked
    ? "border-emerald-300"
    : "border-amber-300";

  const sizeEntries = Object.entries(group.size_sku_map || {});

  return (
    <div className={`border-2 ${cardBorder} bg-white rounded-lg overflow-hidden transition-all`}>
      {/* Card header */}
      <div className="flex items-start gap-3 p-3">
        <span className={`mt-1.5 w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusDot}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="font-semibold text-slate-900 text-sm truncate">
                {group.external_style_name || (group.external_style_id ? `Style ID: ${group.external_style_id}` : group.base_key)}
              </div>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                <span className="inline-block bg-slate-100 border border-slate-200 text-slate-700 text-[11px] font-semibold px-2 py-0.5 rounded">
                  {group.color_label || "(no colour)"}
                </span>
                <span className="text-[11px] text-slate-400 font-mono">
                  {group.sku_count} SKU{group.sku_count !== 1 ? "s" : ""}
                </span>
                {group.external_style_id && group.external_style_name && (
                  <span className="text-[11px] font-mono text-slate-400">Style ID: {group.external_style_id}</span>
                )}
              </div>
              <div className="mt-1 text-[11px] font-mono text-slate-500 truncate">
                {(group.sample_skus || []).slice(0, 3).join(", ")}
                {(group.sample_skus || []).length > 3 && ` +${(group.sample_skus || []).length - 3} more`}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="flex-shrink-0 text-slate-400 hover:text-slate-700 transition-colors mt-0.5"
              title={expanded ? "Collapse" : "Expand size map"}
            >
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>

          {/* Sibling hint */}
          {siblingColors.length > 0 && (
            <div className="mt-2 bg-blue-50 border border-blue-200 rounded p-2 flex items-start gap-2">
              <Info className="w-3.5 h-3.5 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="text-[11px] text-blue-800">
                <span className="font-semibold">{siblingColors.length} other colour{siblingColors.length !== 1 ? "s" : ""}</span>
                {" "}{siblingColors.map((c) => <span key={c} className="font-mono bg-blue-100 px-1 rounded mr-1">{c}</span>)}
                {" "}might belong to the same style.
                {linked && (
                  <button
                    type="button"
                    onClick={() => {
                      // Propagate current style_id to all sibling group_keys
                      (group.sibling_group_keys || []).forEach((sk) =>
                        onDecide(sk, decision.style_id)
                      );
                    }}
                    className="ml-2 underline font-bold text-blue-700 hover:text-blue-900"
                  >
                    Link them to the same style?
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Suggestion hint */}
          {group.suggested_base_match && !linked && (
            <div className="mt-2 text-[11px] text-slate-500 flex items-center gap-1.5">
              <span className="text-slate-400">Suggestion:</span>
              <span className="font-mono font-bold text-slate-700">{group.suggested_base_match}</span>
              <button
                type="button"
                onClick={() => {
                  const s = styles.find(
                    (st) => st.code?.toUpperCase() === group.suggested_base_match?.toUpperCase()
                  );
                  if (s) onDecide(group.group_key, s.id);
                }}
                className="text-blue-600 hover:text-blue-800 underline text-[11px]"
              >
                Use this?
              </button>
            </div>
          )}

          {/* Expanded size map */}
          {expanded && sizeEntries.length > 0 && (
            <div className="mt-2 grid grid-cols-2 gap-1">
              {sizeEntries.map(([size, sku]) => (
                <div key={size} className="text-[11px] font-mono bg-slate-50 border border-slate-200 px-2 py-1 rounded flex gap-2">
                  <span className="text-slate-500 font-bold w-12 flex-shrink-0">{size}</span>
                  <span className="text-slate-800 truncate">{sku}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Decision controls */}
      <div className="border-t border-slate-100 bg-slate-50 p-3 space-y-2.5">
        {/* Style lookup */}
        <div className="flex items-center gap-2">
          <Link2 className="w-4 h-4 text-slate-400 flex-shrink-0" />
          <div className="flex-1">
            <SearchableSelect
              options={styles}
              value={decision?.style_id || ""}
              onChange={(id) => onDecide(group.group_key, id || null)}
              getKey={(s) => s.id}
              getLabel={(s) => `${s.code} — ${s.name}`}
              renderOption={(s) => (
                <span className="flex flex-col">
                  <span className="font-mono font-bold text-slate-900">{s.code}</span>
                  <span className="text-[11px] text-slate-500">{s.name}</span>
                </span>
              )}
              placeholder="Search internal style code…"
              testId={`link-style-${group.group_key}`}
            />
          </div>
          {decision?.style_id && (
            <button
              type="button"
              onClick={() => onDecide(group.group_key, null)}
              className="text-slate-400 hover:text-red-500 transition-colors flex-shrink-0"
              title="Clear link"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Unlinked toggle */}
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            id={`unlink-${group.group_key}`}
            className="accent-amber-500 w-4 h-4"
            checked={unlinked}
            onChange={(e) => {
              if (e.target.checked) {
                // explicitly mark unlinked — style_id stays null, but decision is set
                onDecide(group.group_key, undefined); // undefined = "explicitly unlinked"
              } else {
                // revert to undecided
                onDecide(group.group_key, "__clear__");
              }
            }}
          />
          <span className={`text-xs font-semibold ${ unlinked ? "text-amber-700" : "text-slate-500" }`}>
            Leave unlinked for now — flag "needs style_code"
          </span>
          {unlinked && (
            <span className="ml-1 text-[10px] bg-amber-100 border border-amber-300 text-amber-800 px-1.5 py-0.5 rounded font-bold">
              ⚠ FLAGGED
            </span>
          )}
        </label>

        {/* Status chip */}
        <div className="flex items-center gap-1.5">
          {linked ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-[11px] text-emerald-700 font-semibold">
                Linked → <span className="font-mono">{selectedStyle?.code}</span>
              </span>
            </>
          ) : unlinked ? (
            <>
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              <span className="text-[11px] text-amber-700 font-semibold">Will import flagged — resolvable later</span>
            </>
          ) : (
            <span className="text-[11px] text-slate-400 italic">Undecided — link or flag to continue</span>
          )}
        </div>
      </div>
    </div>
  );
}

function ListingImportDrawer({ onClose, onDone, styles }) {
  // ── Stage 1 state ──────────────────────────────────────────
  const [stage, setStage]       = useState(1);   // 1 = upload, 2 = link
  const [file, setFile]         = useState(null);
  const [platform, setPlatform] = useState("myntra");
  const [isDragging, setIsDragging] = useState(false);
  const [parsing, setParsing]   = useState(false);
  const [parseError, setParseError] = useState("");
  const fileRef = useRef();

  // ── Stage 2 state ──────────────────────────────────────────
  const [session, setSession]   = useState(null);  // full parse response
  const [decisions, setDecisions] = useState({});   // group_key → { style_id } | null
  // decisions[gk] === undefined  →  undecided
  // decisions[gk] === { style_id: "abc" }  → linked
  // decisions[gk] === { style_id: null }   → explicitly unlinked

  const [committing, setCommitting] = useState(false);
  const [commitResult, setCommitResult] = useState(null);
  const [commitError, setCommitError]   = useState("");

  // ── Helpers ────────────────────────────────────────────────
  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    const name = f.name.toLowerCase();
    if (name.endsWith(".xlsx") || name.endsWith(".xlsm") || name.endsWith(".csv")) {
      setFile(f); setParseError("");
    } else {
      setParseError("Only .xlsx, .xlsm, or .csv files are supported.");
    }
  }

  async function runParse() {
    if (!file) return setParseError("Please select a file first.");
    setParseError(""); setParsing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const source_type = SOURCE_TYPE_BY_PLATFORM[platform] || "online_channel";
      const r = await http.post(
        `/sku-map/listing-import/parse?platform=${encodeURIComponent(platform)}&source_type=${encodeURIComponent(source_type)}`,
        fd
      );
      setSession(r.data);
      setDecisions({});
      setStage(2);
    } catch (e) {
      setParseError(formatApiError(e.response?.data?.detail) || "Parse failed.");
    } finally {
      setParsing(false);
    }
  }

  function onDecide(groupKey, styleIdOrSentinel) {
    setDecisions((prev) => {
      const next = { ...prev };
      if (styleIdOrSentinel === "__clear__") {
        // revert to undecided
        delete next[groupKey];
      } else if (styleIdOrSentinel === undefined) {
        // explicitly unlinked
        next[groupKey] = { style_id: null };
      } else {
        // linked to a style_id (string), or null clears the link
        if (styleIdOrSentinel === null || styleIdOrSentinel === "") {
          delete next[groupKey]; // unclear → undecided
        } else {
          next[groupKey] = { style_id: styleIdOrSentinel };
        }
      }
      return next;
    });
  }

  const groups      = session?.groups || [];
  const totalGroups = groups.length;
  const decidedCount = groups.filter((g) => decisions[g.group_key] !== undefined).length;
  const allDecided   = decidedCount === totalGroups && totalGroups > 0;
  const linkedCount  = Object.values(decisions).filter((d) => d?.style_id != null).length;
  const unlinkedCount = Object.values(decisions).filter((d) => d != null && d.style_id == null).length;

  async function commitImport() {
    setCommitError(""); setCommitting(true);
    try {
      const payload = {
        decisions: groups.map((g) => ({
          group_key: g.group_key,
          style_id:  decisions[g.group_key]?.style_id ?? null,
        })),
      };
      const r = await http.post(`/sku-map/listing-import/sessions/${session.session_id}/commit`, payload);
      setCommitResult(r.data);
      if (onDone) onDone();
    } catch (e) {
      setCommitError(formatApiError(e.response?.data?.detail) || "Commit failed.");
    } finally {
      setCommitting(false);
    }
  }

  // ── Render: Stage 1 ───────────────────────────────────────
  const renderStage1 = () => (
    <div className="space-y-5">
      {/* Header info box */}
      <div className="bg-slate-900 text-white p-4 border border-slate-800 space-y-3">
        <div className="text-xs uppercase tracking-wider font-bold text-emerald-400">Import from Listing File — Stage 1</div>
        <div className="text-xs text-slate-300">
          Upload a raw marketplace export (.xlsx / .csv). The importer will group your SKUs
          by style + colour and let you <strong className="text-white">explicitly link</strong> each
          group to an internal style in Stage 2 — no styles are auto-created.
        </div>
        <div className="text-[11px] font-mono bg-slate-950/60 p-2.5 border border-slate-700 rounded space-y-1 text-slate-300">
          <div><span className="text-emerald-400 font-bold">Auto-detected columns:</span> style name/ID, colour, size, SKU/seller ID</div>
          <div><span className="text-blue-400 font-bold">Platform aliases:</span> Myntra, Flipkart, Nykaa, Ajio, Amazon, and more</div>
        </div>
      </div>

      {/* Platform picker */}
      <div className="space-y-1">
        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Platform / Source *</div>
        <div className="grid grid-cols-3 gap-2">
          {PLATFORMS.map((p) => (
            <button
              key={p.value}
              type="button"
              id={`platform-${p.value}`}
              onClick={() => setPlatform(p.value)}
              className={`px-3 py-2 text-xs font-bold border-2 transition-all ${
                platform === p.value
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Dropzone */}
      <div className="space-y-1">
        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Listing File *</div>
        <div
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
            isDragging ? "border-emerald-500 bg-emerald-50"
            : file      ? "border-emerald-500 bg-emerald-50/40"
            : "border-slate-300 hover:border-slate-500 bg-white"
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? "text-emerald-600" : "text-slate-400"}`} />
          {file ? (
            <div className="space-y-1">
              <div className="text-sm font-mono font-bold text-slate-900">{file.name}</div>
              <div className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB · Ready to parse</div>
              <button type="button" onClick={(e) => { e.stopPropagation(); setFile(null); }}
                className="text-xs text-red-600 hover:underline font-semibold">
                Change file
              </button>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="text-sm font-semibold text-slate-700">Click or drag listing file here</div>
              <div className="text-xs text-slate-400">Supports .xlsx, .xlsm, .csv · Raw marketplace exports</div>
            </div>
          )}
        </div>
        <input ref={fileRef} type="file"
          accept=".xlsx,.xlsm,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => { if (e.target.files?.[0]) { setFile(e.target.files[0]); setParseError(""); } }}
        />
      </div>

      {parseError && (
        <div className="bg-red-50 border-2 border-red-300 p-3 text-xs text-red-700 font-semibold flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <div>{parseError}</div>
        </div>
      )}

      <div className="flex gap-3 pt-1">
        <BtnPrimary id="btn-parse-listing" onClick={runParse} disabled={parsing || !file} className="flex-1">
          <span className="flex items-center justify-center gap-2">
            <Layers className="w-4 h-4" />
            {parsing ? "Parsing…" : "Parse & Group SKUs"}
          </span>
        </BtnPrimary>
        <BtnSecondary onClick={onClose} disabled={parsing}>Cancel</BtnSecondary>
      </div>
    </div>
  );

  // ── Render: Commit result ──────────────────────────────────
  if (commitResult) {
    return (
      <Drawer onClose={onClose} title="Import from Listing File">
        <div className="space-y-5">
          <div className="bg-emerald-50 border-2 border-emerald-300 p-5 space-y-4">
            <div className="flex items-center gap-2 text-emerald-800 font-bold text-sm">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" /> Import Complete
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-emerald-100 border border-emerald-300 p-3 text-center rounded">
                <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-800">Linked</div>
                <div className="text-3xl font-bold font-mono text-emerald-700">{commitResult.linked}</div>
              </div>
              <div className={`p-3 text-center rounded border ${ commitResult.unlinked > 0 ? "bg-amber-50 border-amber-300" : "bg-slate-100 border-slate-200" }`}>
                <div className="text-[10px] uppercase tracking-wider font-bold text-amber-800">Flagged (needs style)</div>
                <div className="text-3xl font-bold font-mono text-amber-700">{commitResult.unlinked}</div>
              </div>
            </div>
            {commitResult.unlinked > 0 && (
              <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 p-2.5 rounded flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <div>
                  <strong>{commitResult.unlinked} group{commitResult.unlinked !== 1 ? "s" : ""}</strong> imported with
                  <strong> ⚠ Needs style_code</strong> flag. Find them in the main table
                  using the <strong>"Needs Style Code"</strong> filter — edit and link via the edit drawer.
                </div>
              </div>
            )}
            {commitResult.errors?.length > 0 && (
              <div className="bg-red-50 border border-red-300 p-3 rounded space-y-1">
                <div className="text-xs font-bold text-red-800">Errors ({commitResult.errors.length})</div>
                {commitResult.errors.map((e, i) => (
                  <div key={i} className="text-[11px] font-mono text-red-700">
                    <span className="font-bold">{e.group_key}:</span> {e.reason}
                  </div>
                ))}
              </div>
            )}
          </div>
          <BtnPrimary id="btn-done-listing-import" onClick={() => { onDone?.(); onClose(); }} className="w-full">
            <span className="flex items-center justify-center gap-2">
              <Check className="w-4 h-4" /> Done — View Mappings
            </span>
          </BtnPrimary>
        </div>
      </Drawer>
    );
  }

  // ── Render: Stage 2 ───────────────────────────────────────
  const renderStage2 = () => (
    <div className="space-y-4">
      {/* Session summary bar */}
      <div className="bg-slate-900 text-white px-4 py-3 flex items-center justify-between gap-3 rounded">
        <div>
          <div className="text-xs font-bold text-emerald-400 uppercase tracking-wider">Stage 2 — Link Groups to Internal Styles</div>
          <div className="text-xs text-slate-300 mt-0.5">
            {session.filename} · {totalGroups} group{totalGroups !== 1 ? "s" : ""} · {session.sku_count} SKUs total
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-xs font-bold text-white">{decidedCount} / {totalGroups}</div>
          <div className="text-[10px] text-slate-400">decided</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="bg-slate-200 rounded-full h-1.5 overflow-hidden">
        <div
          className="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
          style={{ width: totalGroups > 0 ? `${(decidedCount / totalGroups) * 100}%` : "0%" }}
        />
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[11px]">
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Linked ({linkedCount})</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-400" /> Flagged ({unlinkedCount})</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-slate-300" /> Undecided ({totalGroups - decidedCount})</span>
      </div>

      {/* Rule: all must be decided */}
      {!allDecided && (
        <div className="bg-blue-50 border border-blue-200 p-2.5 rounded text-[11px] text-blue-800 flex items-start gap-2">
          <Info className="w-3.5 h-3.5 text-blue-500 flex-shrink-0 mt-0.5" />
          For each group: <strong>link to a style</strong> or check <strong>"Leave unlinked for now"</strong>.
          Both choices import the data — the unlinked flag lets you resolve it later without blocking the batch.
        </div>
      )}

      {/* Group cards */}
      <div className="space-y-3 max-h-[55vh] overflow-y-auto pr-1">
        {groups.map((g) => (
          <GroupCard
            key={g.group_key}
            group={g}
            decision={decisions[g.group_key]}
            onDecide={onDecide}
            styles={styles}
          />
        ))}
      </div>

      {commitError && (
        <div className="bg-red-50 border-2 border-red-300 p-3 text-xs text-red-700 font-semibold flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <div>{commitError}</div>
        </div>
      )}

      <div className="flex gap-3 pt-1">
        <BtnPrimary
          id="btn-commit-listing-import"
          onClick={commitImport}
          disabled={!allDecided || committing}
          className="flex-1"
          title={!allDecided ? `${totalGroups - decidedCount} group(s) still undecided` : ""}
        >
          <span className="flex items-center justify-center gap-2">
            <Link2 className="w-4 h-4" />
            {committing ? "Committing…" : `Commit Import (${linkedCount} linked, ${unlinkedCount} flagged)`}
          </span>
        </BtnPrimary>
        <BtnSecondary onClick={() => setStage(1)} disabled={committing}>← Back</BtnSecondary>
      </div>
    </div>
  );

  return (
    <Drawer
      onClose={onClose}
      title={stage === 1 ? "Import from Listing File (Stage 1 — Parse)" : "Import from Listing File (Stage 2 — Link Groups)"}
    >
      {stage === 1 ? renderStage1() : renderStage2()}
    </Drawer>
  );
}

// ── main page ─────────────────────────────────────────────
export default function SkuMap() {
  const [tab, setTab] = useState("mappings");
  const [mappings, setMappings] = useState([]);
  const [styles, setStyles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [listingImportOpen, setListingImportOpen] = useState(false);
  const [activeMapping, setActiveMapping] = useState(null);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [filterType, setFilterType] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterNeedsStyle, setFilterNeedsStyle] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterType) params.append("source_type", filterType);
      if (filterSource.trim()) params.append("source_name", filterSource.trim());
      if (searchQuery.trim()) params.append("search", searchQuery.trim());
      if (filterNeedsStyle) params.append("needs_style_code", "true");

      const [resMap, resStyles] = await Promise.all([
        http.get(`/sku-map?${params.toString()}`),
        http.get("/styles"),
      ]);
      setMappings(resMap.data);
      setStyles(resStyles.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterType, filterSource, searchQuery, filterNeedsStyle]);

  useEffect(() => {
    load();
  }, [load]);

  function openCreate() { setEditId(null); setActiveMapping(null); setForm(emptyForm); setFormError(""); setOpen(true); }
  function openEdit(m) {
    setEditId(m.id);
    setActiveMapping(m);
    setForm({
      style_id: m.style_id, source_type: m.source_type, source_name: m.source_name,
      external_sku: m.external_sku, external_style_name: m.external_style_name || "",
      image_url: m.image_url || "",
      color_map: dictToRows(m.color_map), size_map: dictToRows(m.size_map),
    });
    setFormError(""); setOpen(true);
  }

  async function handleSave() {
    setFormError("");
    if (!form.style_id.trim()) return setFormError("Please select a style.");
    if (!form.source_name.trim()) return setFormError("Source name is required.");
    if (!form.external_sku.trim()) return setFormError("External SKU is required.");
    setSaving(true);
    try {
      if (editId) {
        await http.put(`/sku-map/${editId}`, {
          external_style_name: form.external_style_name,
          image_url: form.image_url.trim(),
          color_map: rowsToDict(form.color_map),
          size_map: rowsToDict(form.size_map),
        });
      } else {
        await http.post("/sku-map", {
          style_id: form.style_id, source_type: form.source_type,
          source_name: form.source_name.trim(), external_sku: form.external_sku.trim(),
          external_style_name: form.external_style_name.trim(),
          image_url: form.image_url.trim(),
          color_map: rowsToDict(form.color_map), size_map: rowsToDict(form.size_map),
        });
      }
      setOpen(false); load();
    } catch (e) {
      setFormError(formatApiError(e.response?.data?.detail));
    } finally { setSaving(false); }
  }

  function askDelete(m) {
    setConfirm({
      title: "Delete Mapping",
      message: `Remove the mapping for "${m.external_sku || m.style_code}" (${m.source_name})? This cannot be undone.`,
      onConfirm: async () => { await http.delete(`/sku-map/${m.id}`); setConfirm(null); load(); },
      onCancel: () => setConfirm(null),
    });
  }

  const selectedStyle = styles.find((s) => s.id === form.style_id);

  const TAB_CLS = (t) =>
    `px-5 py-3 text-sm font-bold border-b-2 transition-colors ${tab === t
      ? "border-[#C27842] text-slate-900"
      : "border-transparent text-slate-500 hover:text-slate-900"
    }`;

  return (
    <div className="bg-[#F7F7F5]">
      <PageHeader
        title="SKU Mapping"
        subtitle="Style ID ↔ External SKU"
        testId="sku-map-header"
        action={
          <div className="flex gap-2 flex-wrap">
            <BtnSecondary id="btn-listing-import" onClick={() => setListingImportOpen(true)}>
              <span className="flex items-center gap-2"><Layers className="w-4 h-4" /> Import from Listing</span>
            </BtnSecondary>
            <BtnSecondary id="btn-bulk-import" onClick={() => setBulkOpen(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Bulk Import</span>
            </BtnSecondary>
            <BtnPrimary id="btn-add-sku-map" onClick={openCreate}>
              <span className="flex items-center gap-2"><Plus className="w-4 h-4" /> Add Mapping</span>
            </BtnPrimary>
          </div>
        }
      />

      {/* Tabs */}
      <div className="bg-white border-b-2 border-slate-200 flex px-4 sm:px-8">
        <button className={TAB_CLS("mappings")} onClick={() => setTab("mappings")}>All Mappings</button>
        <button className={TAB_CLS("unmapped")} onClick={() => setTab("unmapped")}>
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> Unmapped Jobs
          </span>
        </button>
      </div>

      {tab === "unmapped" ? (
        <div className="px-4 sm:px-8 py-6">
          <UnmappedTab styles={styles} onDone={load} />
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="px-4 sm:px-8 py-4 bg-white border-b-2 border-slate-200 flex flex-wrap gap-3 items-end">
            <div className="w-44">
              <Select label="Source Type" id="filter-source-type" value={filterType}
                onChange={(e) => setFilterType(e.target.value)}>
                <option value="">All Types</option>
                <option value="b2b_client">B2B Client</option>
                <option value="online_channel">Online Channel</option>
              </Select>
            </div>
            <div className="w-52">
              <Input label="Source Name" id="filter-source-name" placeholder="Filter by client / channel…"
                value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()} />
            </div>
            <div className="flex-1 min-w-[200px]">
              <Input label="Search SKU / Style" id="filter-search" placeholder="External SKU, style code, name…"
                value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()} />
            </div>
            {/* Needs-style-code quick filter */}
            <label className="flex items-center gap-2 cursor-pointer select-none pb-1">
              <input
                type="checkbox"
                id="filter-needs-style"
                className="accent-amber-500 w-4 h-4"
                checked={filterNeedsStyle}
                onChange={(e) => setFilterNeedsStyle(e.target.checked)}
              />
              <span className="text-xs font-semibold text-amber-700 whitespace-nowrap">⚠ Needs style_code only</span>
            </label>
            <BtnSecondary id="btn-apply-filters" onClick={load}>Search</BtnSecondary>
          </div>

          {/* Stats bar */}
          <div className="px-4 sm:px-8 pt-5 pb-2 flex items-center gap-4">
            <div className="text-xs text-slate-500 font-mono">
              {loading ? "Loading…" : `${mappings.length} mapping${mappings.length !== 1 ? "s" : ""}`}
            </div>
            {!loading && mappings.filter((m) => m.needs_style_code).length > 0 && !filterNeedsStyle && (
              <button
                type="button"
                id="btn-quick-needs-style"
                onClick={() => { setFilterNeedsStyle(true); }}
                className="inline-flex items-center gap-1.5 bg-amber-50 border border-amber-300 text-amber-800 text-[11px] font-bold px-2.5 py-1 rounded hover:bg-amber-100 transition-colors"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                {mappings.filter((m) => m.needs_style_code).length} need{mappings.filter((m) => m.needs_style_code).length === 1 ? "s" : ""} style_code
              </button>
            )}
          </div>

          {/* Table */}
          <div className="px-4 sm:px-8 pb-10">
            {loading ? (
              <div className="text-center py-20 text-slate-400">Loading mappings…</div>
            ) : mappings.length === 0 ? (
              <Card className="p-10 text-center">
                <ArrowLeftRight className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <div className="text-slate-500 font-semibold mb-1">No mappings found</div>
                <div className="text-xs text-slate-400">
                  Add a mapping or use Bulk Import to link client/channel SKUs to internal styles.
                </div>
              </Card>
            ) : (
              <Card className="overflow-x-auto">
                <table className="w-full text-sm" id="sku-map-table">
                  <thead>
                    <tr className="border-b-2 border-slate-200 bg-slate-50 text-left">
                      {["Internal Style", "Source", "External SKU / Group", "Ext. Style Name", "Color / Color Map", "Size Map", "Unmapped Misses", "Actions"].map((h) => (
                        <th key={h} className="px-4 py-3 text-[10px] uppercase tracking-wider font-bold text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {mappings.map((m) => {
                      const colorEntries = Object.entries(m.color_map || {});
                      const sizeEntries = Object.entries(m.size_map || {});
                      const unmappedSizes = Object.entries(m.unmapped_encountered?.size || {});
                      const unmappedColors = Object.entries(m.unmapped_encountered?.color || {});
                      const hasUnmapped = unmappedSizes.length > 0 || unmappedColors.length > 0;
                      return (
                        <tr key={m.id} className={`hover:bg-slate-50 transition-colors ${m.needs_style_code ? "bg-amber-50/30" : ""}`}>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              {m.image_url ? (
                                <a
                                  href={m.image_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="w-10 h-10 rounded border border-slate-200 overflow-hidden bg-slate-100 flex-shrink-0 flex items-center justify-center hover:opacity-80 transition-opacity"
                                  title="View full image"
                                >
                                  <img
                                    src={m.image_url}
                                    alt={m.style_code || m.external_style_name}
                                    className="w-full h-full object-cover"
                                    onError={(e) => { e.target.style.display = "none"; }}
                                  />
                                </a>
                              ) : (
                                <div className="w-10 h-10 rounded border border-slate-200 bg-slate-50 flex-shrink-0 flex items-center justify-center text-slate-300">
                                  <ImageIcon className="w-4 h-4" />
                                </div>
                              )}
                              <div>
                                {m.needs_style_code ? (
                                  <>
                                    <div className="flex items-center gap-1.5">
                                      <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                                      <span className="text-[11px] font-bold text-amber-700 bg-amber-100 border border-amber-300 px-1.5 py-0.5 rounded">
                                        Needs style_code
                                      </span>
                                    </div>
                                    <div className="text-xs text-slate-500 mt-0.5 font-mono">
                                      {m.external_style_name || m.external_style_id || "—"}
                                    </div>
                                  </>
                                ) : (
                                  <>
                                    <div className="font-mono font-bold text-slate-900">{m.style_code}</div>
                                    <div className="text-[10px] text-slate-400 font-mono">{m.style_id}</div>
                                  </>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <Badge color={m.source_type === "b2b_client" ? "blue" : "orange"}>
                              {SOURCE_TYPE_LABELS[m.source_type] || m.source_type}
                            </Badge>
                            <div className="text-xs text-slate-600 mt-1 font-semibold">{m.source_name}</div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-mono font-bold text-slate-900">
                              {m.external_sku || (m.color ? `${m.color} Group` : "—")}
                            </div>
                            {m.color && (
                              <div className="text-[11px] text-slate-500 mt-0.5">
                                Color: <span className="font-semibold text-slate-700">{m.color}</span>
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-600">{m.external_style_name || <span className="text-slate-300">—</span>}</td>
                          <td className="px-4 py-3">
                            {m.color ? (
                              <span className="inline-block bg-slate-100 text-slate-800 text-xs font-semibold px-2 py-0.5 rounded border border-slate-200">
                                {m.color}
                              </span>
                            ) : colorEntries.length === 0 ? (
                              <span className="text-slate-300 text-xs">—</span>
                            ) : (
                              <div className="space-y-0.5">
                                {colorEntries.map(([k, v]) => (
                                  <div key={k} className="text-[11px] font-mono text-slate-600">
                                    <span className="text-slate-400">{k}</span>
                                    <span className="text-slate-400 mx-1">→</span>
                                    <span className="font-bold">{v}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {sizeEntries.length === 0 ? <span className="text-slate-300 text-xs">—</span> : (
                              <div className="space-y-0.5 max-w-[200px]">
                                {sizeEntries.slice(0, 4).map(([k, v]) => (
                                  <div key={k} className="text-[11px] font-mono text-slate-600">
                                    <span className="text-slate-500 font-semibold">{k}</span>
                                    <span className="text-slate-400 mx-1">→</span>
                                    <span className="font-bold text-slate-800">{v}</span>
                                  </div>
                                ))}
                                {sizeEntries.length > 4 && (
                                  <div className="text-[10px] text-slate-400 italic">
                                    +{sizeEntries.length - 4} more sizes
                                  </div>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {!hasUnmapped ? <span className="text-slate-300 text-xs">—</span> : (
                              <div className="space-y-1">
                                {unmappedSizes.map(([sz, count]) => (
                                  <span key={sz} className="inline-block bg-amber-100 border border-amber-300 text-amber-900 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded mr-1" title={`${count} recent miss(es)`}>
                                    size "{sz}" ({count}×)
                                  </span>
                                ))}
                                {unmappedColors.map(([col, count]) => (
                                  <span key={col} className="inline-block bg-amber-100 border border-amber-300 text-amber-900 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded mr-1" title={`${count} recent miss(es)`}>
                                    color "{col}" ({count}×)
                                  </span>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <button id={`btn-edit-${m.id}`} onClick={() => openEdit(m)}
                                className="text-slate-400 hover:text-slate-700 transition-colors" title="Edit">
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button id={`btn-delete-${m.id}`} onClick={() => askDelete(m)}
                                className="text-slate-400 hover:text-red-600 transition-colors" title="Delete">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        </>
      )}

      {/* Create / Edit Drawer */}
      {open && (
        <Drawer onClose={() => setOpen(false)} title={editId ? "Edit Mapping" : "New SKU Mapping"}>
          <div className="space-y-5">
            {/* Style selector */}
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Internal Style *</div>
              {editId ? (
                <div className="border-2 border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700">
                  {selectedStyle ? `${selectedStyle.code} — ${selectedStyle.name}` : form.style_id}
                </div>
              ) : (
                <select id="form-style-id"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  value={form.style_id} onChange={(e) => setForm({ ...form, style_id: e.target.value })}>
                  <option value="">— Select style —</option>
                  {styles.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                </select>
              )}
            </div>

            {/* Source type */}
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Source Type *</div>
              <div className="flex gap-4">
                {[["b2b_client", "B2B Client"], ["online_channel", "Online Channel"]].map(([val, label]) => (
                  <label key={val} className="flex items-center gap-2 cursor-pointer select-none">
                    <input type="radio" name="source_type" value={val} disabled={!!editId}
                      checked={form.source_type === val}
                      onChange={() => setForm({ ...form, source_type: val, source_name: "" })}
                      className="accent-slate-900" id={`radio-${val}`} />
                    <span className="text-sm font-semibold text-slate-700">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Source name */}
            {editId ? (
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Source Name</div>
                <div className="border-2 border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700">
                  {form.source_name}
                </div>
              </div>
            ) : form.source_type === "online_channel" ? (
              <Select label="Channel *" id="form-source-name-channel" value={form.source_name}
                onChange={(e) => setForm({ ...form, source_name: e.target.value })}>
                <option value="">— Select channel —</option>
                {ONLINE_CHANNELS.map((ch) => (
                  <option key={ch} value={ch}>{ch.charAt(0).toUpperCase() + ch.slice(1)}</option>
                ))}
              </Select>
            ) : (
              <Input label="Client Name *" id="form-source-name" placeholder="e.g. Bata India Ltd"
                value={form.source_name} onChange={(e) => setForm({ ...form, source_name: e.target.value })} />
            )}

            {/* External SKU */}
            {editId ? (
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">External SKU</div>
                <div className="border-2 border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700">
                  {form.external_sku}
                </div>
              </div>
            ) : (
              <Input label="External SKU *" id="form-external-sku"
                placeholder="The code that the client / platform uses"
                value={form.external_sku} onChange={(e) => setForm({ ...form, external_sku: e.target.value })} />
            )}

            <Input label="External Style Name (optional)" id="form-external-style-name"
              placeholder="How this source describes the style"
              value={form.external_style_name}
              onChange={(e) => setForm({ ...form, external_style_name: e.target.value })} />

            <div className="space-y-1">
              <Input
                label="Image URL (optional — Dropbox / Google Drive / Direct link)"
                id="form-image-url"
                placeholder="https://www.dropbox.com/... or https://drive.google.com/..."
                value={form.image_url}
                onChange={(e) => setForm({ ...form, image_url: e.target.value })}
              />
              {form.image_url && (
                <div className="flex items-center gap-2 pt-1">
                  <div className="w-8 h-8 rounded border border-slate-300 overflow-hidden bg-slate-100 flex-shrink-0">
                    <img
                      src={form.image_url}
                      alt="Preview"
                      className="w-full h-full object-cover"
                      onError={(e) => { e.target.style.display = "none"; }}
                    />
                  </div>
                  <a
                    href={form.image_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline flex items-center gap-1 font-mono truncate max-w-xs"
                  >
                    <span>Test image link</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                </div>
              )}
            </div>

            {activeMapping?.unmapped_encountered && (
              (Object.keys(activeMapping.unmapped_encountered.size || {}).length > 0 ||
               Object.keys(activeMapping.unmapped_encountered.color || {}).length > 0) && (
                <div className="bg-amber-50 border-2 border-amber-300 p-3.5 space-y-3.5">
                  <div className="flex items-center justify-between text-amber-900 font-bold text-xs uppercase tracking-wider">
                    <span className="flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                      Unmapped Values Recently Encountered
                    </span>
                    {activeMapping.last_unmapped_at && (
                      <span className="text-[10px] text-amber-700 font-mono font-normal">
                        Last: {new Date(activeMapping.last_unmapped_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>

                  {/* Sizes */}
                  {Object.keys(activeMapping.unmapped_encountered.size || {}).length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-amber-800">Unmapped Sizes:</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(activeMapping.unmapped_encountered.size).map(([val, count]) => {
                          const alreadyInForm = form.size_map.some((r) => r.from.trim() === val.trim());
                          return (
                            <div key={val} className="inline-flex items-center gap-2 bg-white border border-amber-300 px-2.5 py-1 text-xs font-mono text-amber-900 shadow-sm">
                              <span>size <strong>"{val}"</strong> ({count}×)</span>
                              {!alreadyInForm ? (
                                <button
                                  type="button"
                                  onClick={() => setForm((prev) => ({ ...prev, size_map: [...prev.size_map, { from: val, to: val }] }))}
                                  className="text-[10px] font-bold text-amber-700 hover:text-amber-900 underline ml-1"
                                >
                                  + Add to Size Map
                                </button>
                              ) : (
                                <span className="text-[10px] text-green-700 font-bold ml-1">✓ Added</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Colors */}
                  {Object.keys(activeMapping.unmapped_encountered.color || {}).length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-amber-800">Unmapped Colors:</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(activeMapping.unmapped_encountered.color).map(([val, count]) => {
                          const alreadyInForm = form.color_map.some((r) => r.from.trim() === val.trim());
                          return (
                            <div key={val} className="inline-flex items-center gap-2 bg-white border border-amber-300 px-2.5 py-1 text-xs font-mono text-amber-900 shadow-sm">
                              <span>color <strong>"{val}"</strong> ({count}×)</span>
                              {!alreadyInForm ? (
                                <button
                                  type="button"
                                  onClick={() => setForm((prev) => ({ ...prev, color_map: [...prev.color_map, { from: val, to: val }] }))}
                                  className="text-[10px] font-bold text-amber-700 hover:text-amber-900 underline ml-1"
                                >
                                  + Add to Color Map
                                </button>
                              ) : (
                                <span className="text-[10px] text-green-700 font-bold ml-1">✓ Added</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )
            )}

            <KVPairs label="Color Map (optional) — external → internal"
              rows={form.color_map} onChange={(rows) => setForm({ ...form, color_map: rows })} />
            <KVPairs label="Size Map (optional) — external → internal"
              rows={form.size_map} onChange={(rows) => setForm({ ...form, size_map: rows })} />

            {formError && (
              <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold">
                {formError}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <BtnPrimary id="btn-save-sku-map" onClick={handleSave} disabled={saving} className="flex-1">
                <span className="flex items-center justify-center gap-2">
                  <Save className="w-4 h-4" />
                  {saving ? "Saving…" : editId ? "Update Mapping" : "Create Mapping"}
                </span>
              </BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)} disabled={saving}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}

      {/* Bulk Import Drawer */}
      {bulkOpen && (
        <BulkImportDrawer onClose={() => setBulkOpen(false)} onDone={() => { load(); }} />
      )}

      {/* Listing Import Drawer (Stage 1 → Stage 2) */}
      {listingImportOpen && (
        <ListingImportDrawer
          onClose={() => setListingImportOpen(false)}
          onDone={() => load()}
          styles={styles}
        />
      )}

      <ConfirmDialog open={!!confirm} title={confirm?.title} message={confirm?.message}
        onConfirm={confirm?.onConfirm} onCancel={confirm?.onCancel} />
    </div>
  );
}
