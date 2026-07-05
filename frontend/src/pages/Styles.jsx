import { useEffect, useMemo, useState } from "react";
import { http, inr, num } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Input, Select, Badge, ConfirmDialog } from "../components/ui-kit";
import { Drawer } from "./Materials";
import { Plus, Trash2, Pencil, Save, Calculator as CalcIcon, Upload } from "lucide-react";

const SECTIONS = [
  "Upper Top", "Mid Layer / Reinforcement", "Lining",
  "Bottom Layer", "Insole Board + Cushion", "Insole Cover (PU/Leather)",
  "Sole", "Accessory", "Consumable", "Packing", "Other",
];

const emptyStyle = {
  code: "", name: "", category: "Footwear", image_url: "", description: "", base_size: "7",
  bom: [], labor: [
    { name: "Cutting", rate: 6 }, { name: "Fitting", rate: 12 }, { name: "Pasting", rate: 8 },
    { name: "Finishing", rate: 6 }, { name: "Packing", rate: 3 },
  ],
  overhead_pct: 8, packing_cost: 12, margin_pct: 25, gst_pct: 5,
};

export default function Styles() {
  const [styles, setStyles] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [open, setOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkPreview, setBulkPreview] = useState(null);
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyStyle);
  const [confirm, setConfirm] = useState(null);
  const [formError, setFormError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const load = async (filter = statusFilter, search = searchQuery) => {
    const queryParams = new URLSearchParams();
    if (filter) queryParams.append("status", filter);
    if (search) queryParams.append("search", search);
    const qs = queryParams.toString() ? `?${queryParams.toString()}` : "";
    const [s, m] = await Promise.all([http.get(`/styles${qs}`), http.get("/materials")]);
    setStyles(s.data); setMaterials(m.data);
    
    const params = new URLSearchParams(window.location.search);
    const editCode = params.get("edit");
    if (editCode && s.data.length > 0) {
      const styleToEdit = s.data.find(x => x.code === editCode);
      if (styleToEdit) {
        setEditId(styleToEdit.id);
        setForm({
          code: styleToEdit.code, name: styleToEdit.name, category: styleToEdit.category, image_url: styleToEdit.image_url || "",
          description: styleToEdit.description || "", base_size: styleToEdit.base_size || "7",
          bom: styleToEdit.bom || [], labor: styleToEdit.labor || [],
          overhead_pct: styleToEdit.overhead_pct, packing_cost: styleToEdit.packing_cost,
          margin_pct: styleToEdit.margin_pct, gst_pct: styleToEdit.gst_pct,
        });
        setOpen(true);
        // Clear the query parameter so it doesn't reopen on refresh
        window.history.replaceState({}, document.title, window.location.pathname);
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

  const startNew = () => { setEditId(null); setForm(emptyStyle); setFormError(""); setOpen(true); };
  const startEdit = (s) => {
    setEditId(s.id);
    setForm({
      code: s.code, name: s.name, category: s.category, image_url: s.image_url || "",
      description: s.description || "", base_size: s.base_size || "7",
      bom: s.bom || [], labor: s.labor || [],
      overhead_pct: s.overhead_pct, packing_cost: s.packing_cost,
      margin_pct: s.margin_pct, gst_pct: s.gst_pct,
    });
    setFormError("");
    setOpen(true);
  };
  const save = async () => {
    setFormError("");
    try {
      const body = {
        ...form,
        overhead_pct: Number(form.overhead_pct), packing_cost: Number(form.packing_cost),
        margin_pct: Number(form.margin_pct), gst_pct: Number(form.gst_pct),
        bom: form.bom.map(b => ({
          ...b,
          quantity: Number(b.quantity),
          yield_per_unit: Number(b.yield_per_unit || 1),
          waste_pct: Number(b.waste_pct || 0),
          rate: Number(b.rate),
        })),
        labor: form.labor.map(l => ({ ...l, rate: Number(l.rate) })),
      };
      if (editId) await http.patch(`/styles/${editId}`, body); else await http.post("/styles", body);
      setOpen(false); load();
    } catch (e) {
      setFormError(e.response?.data?.detail || e.message);
    }
  };
  const remove = (id) => {
    setConfirm({
      title: "Delete Style",
      message: "Are you sure you want to delete this style from the Master catalog?",
      onConfirm: async () => {
        await http.delete(`/styles/${id}`);
        setConfirm(null);
        load();
      }
    });
  };

  const onImageFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      alert(`Image too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Please upload an image under 5MB.`);
      e.target.value = "";
      return;
    }
    if (!/^image\/(png|jpe?g|webp|gif)$/i.test(file.type)) {
      alert("Only PNG, JPG, WEBP, or GIF allowed.");
      e.target.value = "";
      return;
    }
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await http.post("/upload/image", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setForm((f) => ({ ...f, image_url: res.data.url }));
    } catch (err) {
      console.error(err);
      alert("Failed to upload image. Please try again.");
    }
    e.target.value = "";
  };

  const addBomRow = (material) => {
    setForm((f) => ({ ...f, bom: [...f.bom, {
      material_id: material.id, material_code: material.code, material_name: material.name,
      unit: material.unit, rate: material.rate, quantity: 1, yield_per_unit: 1, waste_pct: 5, section: material.category,
    }]}));
  };

  const updateBom = (i, key, val) => setForm((f) => ({ ...f, bom: f.bom.map((r, idx) => idx === i ? { ...r, [key]: val } : r) }));
  const removeBom = (i) => setForm((f) => ({ ...f, bom: f.bom.filter((_, idx) => idx !== i) }));
  const updateLabor = (i, key, val) => setForm((f) => ({ ...f, labor: f.labor.map((r, idx) => idx === i ? { ...r, [key]: val } : r) }));
  const addLabor = () => setForm((f) => ({ ...f, labor: [...f.labor, { name: "Labor", rate: 0 }] }));
  const removeLabor = (i) => setForm((f) => ({ ...f, labor: f.labor.filter((_, idx) => idx !== i) }));

  const onPreviewBulk = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBulkFile(file);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await http.post("/styles/bulk/preview", formData, { headers: { "Content-Type": "multipart/form-data" } });
      setBulkPreview(res.data.preview);
    } catch (err) {
      alert("Preview failed: " + (err.response?.data?.detail || err.message));
    }
  };

  const submitBulk = async () => {
    if (!bulkPreview) return;
    setBulkUploading(true);
    try {
      const res = await http.post("/styles/bulk", { styles: bulkPreview });
      alert(`Bulk upload complete! ${res.data.success_count} styles created/updated.`);
      setBulkOpen(false);
      setBulkPreview(null);
      setBulkFile(null);
      load();
    } catch (err) {
      alert("Bulk upload failed: " + (err.response?.data?.detail || err.message));
    }
    setBulkUploading(false);
  };

  // live costing — uses (rate * qty / yield) * (1 + waste%)
  const costing = useMemo(() => {
    const matCost = form.bom.reduce((s, b) => {
      const yld = Number(b.yield_per_unit || 1) || 1;
      return s + (Number(b.rate) * Number(b.quantity) / yld) * (1 + Number(b.waste_pct || 0) / 100);
    }, 0);
    const labCost = form.labor.reduce((s, l) => s + Number(l.rate), 0);
    const base = matCost + labCost;
    const oh = base * Number(form.overhead_pct) / 100;
    const total = base + oh + Number(form.packing_cost);
    const margin = total * Number(form.margin_pct) / 100;
    const sell = total + margin;
    const gst = sell * Number(form.gst_pct) / 100;
    return { matCost, labCost, base, oh, total, margin, sell, gst, final: sell + gst };
  }, [form]);

  return (
    <div>
      <PageHeader
        title="Style Master"
        subtitle="Master / Styles"
        testId="styles-header"
        action={
          <div className="flex gap-2 items-center">
            <Input 
              placeholder="Search style or name..." 
              value={searchQuery} 
              onChange={e => setSearchQuery(e.target.value)}
              className="w-48 !py-1 !text-sm"
            />
            <Select 
              value={statusFilter} 
              onChange={e => setStatusFilter(e.target.value)} 
              className="w-32 !py-1 !text-sm mr-2"
            >
              <option value="">All Styles</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
            <BtnSecondary onClick={() => setBulkOpen(true)}>Bulk Upload</BtnSecondary>
            <BtnPrimary onClick={startNew} data-testid="add-style-btn"><Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> New Style</BtnPrimary>
          </div>
        }
      />

      <div className="p-8 space-y-4">
        {styles.length === 0 ? (
          <Card className="p-12 text-center text-slate-400">No styles defined yet. Create your first style to build a BOM and unlock automatic costing.</Card>
        ) : (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="styles-grid">
            {styles.map((s) => (
              <Card key={s.id} className="overflow-hidden hover:border-[#C27842] transition-colors" data-testid={`style-card-${s.code}`}>
                {s.image_url ? (
                  <div className="h-44 bg-slate-100 border-b-2 border-slate-200 overflow-hidden">
                    <img src={s.image_url} alt={s.name} className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="h-44 bg-gradient-to-br from-slate-50 to-slate-100 border-b-2 border-slate-200 grid place-items-center">
                    <div className="text-center">
                      <div className="text-3xl mb-1">👟</div>
                      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400 font-bold">No Image</div>
                    </div>
                  </div>
                )}
                <div className="p-5">
                  <div className="flex items-baseline justify-between mb-2">
                    <div className="font-mono text-xs font-bold text-slate-500">{s.code}</div>
                    <div className="flex gap-2">
                      <Badge color={s.status === 'active' ? 'green' : 'gray'}>
                        {s.status === 'active' ? 'Active' : 'Inactive'}
                      </Badge>
                      <Badge color="orange">{s.category}</Badge>
                    </div>
                  </div>
                <h3 className="text-lg font-bold mb-1">{s.name}</h3>
                <p className="text-xs text-slate-500 line-clamp-2 mb-3">{s.description || "—"}</p>
                <div className="border-t border-dashed border-slate-200 pt-3 space-y-1 text-xs">
                  <Row label="Materials" value={inr(s.costing.materials_cost)} />
                  <Row label="Labor" value={inr(s.costing.labor_cost)} />
                  <Row label="Total cost" value={inr(s.costing.total_cost)} bold />
                  <Row label={`Selling (+${s.margin_pct}%)`} value={inr(s.costing.selling_price)} bold color="#C27842" />
                </div>
                <div className="flex gap-2 mt-4 pt-3 border-t border-slate-200">
                  <BtnSecondary onClick={() => startEdit(s)} className="flex-1"><Pencil className="w-3 h-3 inline -mt-0.5 mr-1" /> Edit</BtnSecondary>
                  <button onClick={() => remove(s.id)} className="px-3 py-2 border-2 border-slate-300 hover:border-red-500 hover:text-red-600 text-xs">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {open && (
        <Drawer onClose={() => { setOpen(false); setFormError(""); }} title={editId ? "Edit Style" : "New Style"} width="max-w-5xl">
          <div className="grid grid-cols-3 gap-6">
            <div className="col-span-2 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Input label="Style Code" value={form.code} onChange={(e) => { setFormError(""); setForm({ ...form, code: e.target.value }); }} testId="form-style-code" />
                  {formError && (
                    <p className="mt-1 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2" data-testid="form-style-error">{formError}</p>
                  )}
                </div>
                <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} testId="form-style-name" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
                <Input label="Base Size" value={form.base_size} onChange={(e) => setForm({ ...form, base_size: e.target.value })} />
              </div>
              <Input label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

              {/* Image upload */}
              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">Style Image (max 5MB)</div>
                <div className="flex gap-3 items-start">
                  <div className="w-28 h-28 border-2 border-dashed border-slate-300 bg-slate-50 grid place-items-center overflow-hidden flex-shrink-0">
                    {form.image_url ? (
                      <img src={form.image_url} alt="preview" className="w-full h-full object-cover" data-testid="image-preview" />
                    ) : (
                      <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold text-center px-2">No image</div>
                    )}
                  </div>
                  <div className="flex flex-col justify-center flex-1 min-w-[200px]">
                    <div className="flex items-center gap-2 mb-2">
                      <label className="inline-block bg-white text-slate-900 font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-slate-300 hover:border-[#0F172A] transition-colors cursor-pointer" data-testid="image-upload-label">
                        <Upload className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Upload File
                        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={onImageFile} data-testid="image-upload-input" />
                      </label>
                      <span className="text-[10px] text-slate-400 font-bold">OR</span>
                      <input 
                        type="text" 
                        placeholder="Paste image URL (e.g. OneDrive)"
                        className="flex-1 bg-white border-2 border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-slate-500"
                        value={form.image_url}
                        onChange={(e) => {
                          let val = e.target.value;
                          const srcMatch = val.match(/src=["'](.*?)["']/i);
                          if (srcMatch && srcMatch[1]) val = srcMatch[1];
                          setForm({ ...form, image_url: val });
                        }}
                      />
                    </div>
                    {form.image_url && (
                      <button type="button" onClick={() => setForm({ ...form, image_url: "" })} className="text-xs uppercase tracking-wider text-slate-500 hover:text-red-600 font-bold self-start" data-testid="image-clear">Clear Image</button>
                    )}
                  </div>
                </div>
              </div>

              {/* BOM */}
              <div>
                <div className="flex items-baseline justify-between mt-4 mb-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider">Bill of Materials</h3>
                  <select
                    className="text-xs border-2 border-slate-300 px-2 py-1 bg-white"
                    onChange={(e) => { const m = materials.find(x => x.id === e.target.value); if (m) addBomRow(m); e.target.value = ""; }}
                    data-testid="bom-add-material"
                    defaultValue=""
                  >
                    <option value="">+ Add material…</option>
                    {materials.map(m => <option key={m.id} value={m.id}>{m.code} — {m.name}</option>)}
                  </select>
                </div>
                <table className="w-full text-xs border-2 border-slate-200">
                  <thead className="bg-slate-50">
                    <tr className="text-left">
                      <th className="px-2 py-2 font-bold">Material</th>
                      <th className="px-2 py-2 font-bold">Section</th>
                      <th className="px-2 py-2 font-bold text-right">Rate</th>
                      <th className="px-2 py-2 font-bold text-right" title="Material consumption per pair">Qty</th>
                      <th className="px-2 py-2 font-bold text-right" title="Pairs produced per 1 unit of material (e.g., 10 uppers per metre)">Yield</th>
                      <th className="px-2 py-2 font-bold text-right">Waste%</th>
                      <th className="px-2 py-2 font-bold text-right">Cost/pair</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {form.bom.length === 0 && (
                      <tr><td colSpan="8" className="px-2 py-6 text-center text-slate-400">No items. Add from dropdown above.</td></tr>
                    )}
                    {form.bom.map((b, i) => {
                      const yld = Number(b.yield_per_unit || 1) || 1;
                      const cost = (Number(b.rate) * Number(b.quantity) / yld) * (1 + Number(b.waste_pct || 0) / 100);
                      return (
                      <tr key={i} className="border-t border-slate-200">
                        <td className="px-2 py-1.5"><div className="font-mono">{b.material_code}</div><div className="text-[10px] text-slate-500">{b.material_name}</div></td>
                        <td className="px-2 py-1.5">
                          <input
                            list="bom-sections-list"
                            className="font-mono border border-slate-300 px-1 py-0.5 text-xs w-36"
                            value={b.section}
                            onChange={(e) => updateBom(i, "section", e.target.value)}
                            data-testid={`bom-section-${i}`}
                            placeholder="type or pick…"
                          />
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono">₹{b.rate}<span className="text-[10px] text-slate-400">/{b.unit}</span></td>
                        <td className="px-2 py-1.5"><input type="number" step="0.01" value={b.quantity} onChange={(e) => updateBom(i, "quantity", e.target.value)} className="w-16 text-right font-mono border border-slate-300 px-1 py-0.5" /></td>
                        <td className="px-2 py-1.5"><input type="number" step="0.5" value={b.yield_per_unit ?? 1} onChange={(e) => updateBom(i, "yield_per_unit", e.target.value)} className="w-14 text-right font-mono border border-slate-300 px-1 py-0.5" title="Pairs per 1 unit of material" data-testid={`bom-yield-${i}`} /></td>
                        <td className="px-2 py-1.5"><input type="number" step="0.5" value={b.waste_pct} onChange={(e) => updateBom(i, "waste_pct", e.target.value)} className="w-14 text-right font-mono border border-slate-300 px-1 py-0.5" /></td>
                        <td className="px-2 py-1.5 text-right font-mono font-bold">{inr(cost)}</td>
                        <td className="px-2 py-1.5"><button onClick={() => removeBom(i)} className="text-slate-500 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button></td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Labor */}
              <div>
                <div className="flex items-baseline justify-between mt-4 mb-2">
                  <h3 className="text-sm font-bold uppercase tracking-wider">Labor (per pair)</h3>
                  <button onClick={addLabor} className="text-xs uppercase font-bold tracking-wider text-[#2563EB]" data-testid="labor-add">+ Add operation</button>
                </div>
                <table className="w-full text-xs border-2 border-slate-200">
                  <tbody>
                    {form.labor.map((l, i) => (
                      <tr key={i} className="border-t border-slate-200 first:border-t-0">
                        <td className="px-2 py-1.5"><input value={l.name} onChange={(e) => updateLabor(i, "name", e.target.value)} className="w-full border-0 bg-transparent" /></td>
                        <td className="px-2 py-1.5 w-32"><input type="number" step="0.5" value={l.rate} onChange={(e) => updateLabor(i, "rate", e.target.value)} className="w-full text-right font-mono border border-slate-300 px-1 py-0.5" /></td>
                        <td className="px-2 py-1.5 w-8"><button onClick={() => removeLabor(i)} className="text-slate-500 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="grid grid-cols-4 gap-3 pt-2">
                <Input label="Overhead %" type="number" step="0.5" value={form.overhead_pct} onChange={(e) => setForm({ ...form, overhead_pct: e.target.value })} />
                <Input label="Packing ₹" type="number" step="0.5" value={form.packing_cost} onChange={(e) => setForm({ ...form, packing_cost: e.target.value })} />
                <Input label="Margin %" type="number" step="0.5" value={form.margin_pct} onChange={(e) => setForm({ ...form, margin_pct: e.target.value })} />
                <Input label="GST %" type="number" step="0.5" value={form.gst_pct} onChange={(e) => setForm({ ...form, gst_pct: e.target.value })} />
              </div>
            </div>

            {/* Live cost preview */}
            <div className="col-span-1">
              <div className="sticky top-0 bg-[#0F172A] text-white p-5 border-2 border-[#0F172A]">
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold mb-3 flex items-center gap-2"><CalcIcon className="w-3.5 h-3.5" /> Live Cost Sheet</div>
                <CostRow label="Materials" value={inr(costing.matCost)} />
                <CostRow label="Labor" value={inr(costing.labCost)} />
                <CostRow label="Overhead" value={inr(costing.oh)} />
                <CostRow label="Packing" value={inr(form.packing_cost)} />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CostRow label="Total cost" value={inr(costing.total)} bold />
                <CostRow label="Margin" value={inr(costing.margin)} />
                <CostRow label="Selling" value={inr(costing.sell)} bold accent />
                <CostRow label={`GST ${form.gst_pct}%`} value={inr(costing.gst)} small />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CostRow label="Final / pair" value={inr(costing.final)} big />
                <div className="mt-4 pt-3 border-t border-slate-700">
                  <BtnPrimary onClick={save} className="w-full bg-[#C27842] border-[#C27842] hover:bg-[#A65D24]" data-testid="save-style-btn">
                    <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save Style
                  </BtnPrimary>
                </div>
              </div>
            </div>
          </div>
        </Drawer>
      )}

      {bulkOpen && (
        <Drawer onClose={() => { setBulkOpen(false); setBulkPreview(null); setBulkFile(null); }} title="Bulk Upload Styles" width="max-w-4xl">
          <div className="p-8 space-y-6">
            <div className="flex justify-between items-center bg-slate-50 p-4 border border-slate-200">
              <div className="text-sm font-medium text-slate-700">Download the Excel template and fill in your styles data.</div>
              <a href={`${process.env.REACT_APP_BACKEND_URL || ""}/api/styles/bulk/template`} className="px-3 py-2 border-2 border-[#C27842] text-[#C27842] hover:bg-[#C27842] hover:text-white transition-colors text-xs font-bold uppercase tracking-wider bg-white" download>Download Template</a>
            </div>
            
            <div className="border-2 border-dashed border-slate-300 p-10 text-center bg-slate-50 hover:bg-slate-100 transition-colors relative cursor-pointer group">
              <input type="file" accept=".xlsx,.xls,.csv" className="absolute inset-0 opacity-0 cursor-pointer w-full h-full" onChange={onPreviewBulk} title="" />
              <Upload className="w-10 h-10 mx-auto text-slate-400 group-hover:text-slate-600 mb-2 transition-colors" />
              <div className="text-slate-600 font-bold uppercase text-sm tracking-wider">Drag & drop Excel file here</div>
              <div className="text-xs text-slate-400 mt-2">or click to browse</div>
              {bulkFile && <div className="mt-4 text-xs font-bold text-green-600 border border-green-200 bg-green-50 p-2 inline-block rounded">{bulkFile.name} loaded</div>}
            </div>
            
            {bulkPreview && (
              <div className="space-y-4 border border-slate-200 rounded p-4 bg-white shadow-sm">
                <div className="text-sm font-bold border-b pb-2 flex justify-between items-center">
                  <span>Preview ({bulkPreview.length} styles)</span>
                </div>
                <div className="overflow-x-auto text-xs max-h-[40vh]">
                  <table className="w-full text-left">
                    <thead className="bg-slate-100 sticky top-0 shadow-sm">
                      <tr>
                        <th className="p-2 border-b">Code</th>
                        <th className="p-2 border-b">Name</th>
                        <th className="p-2 border-b">Category</th>
                        <th className="p-2 border-b">Base Size</th>
                        <th className="p-2 border-b">Margin%</th>
                        <th className="p-2 border-b">Image</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bulkPreview.map((r, i) => (
                        <tr key={i} className="border-b hover:bg-slate-50">
                          <td className="p-2 font-medium">{r.code}</td>
                          <td className="p-2">{r.name}</td>
                          <td className="p-2">{r.category}</td>
                          <td className="p-2 text-center">{r.base_size}</td>
                          <td className="p-2 text-center">{r.margin_pct}%</td>
                          <td className="p-2 text-slate-400 text-[10px] truncate max-w-[100px]">{r.image_url || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="pt-4 border-t flex justify-end gap-3">
                  <BtnSecondary onClick={() => { setBulkPreview(null); setBulkFile(null); }}>Cancel</BtnSecondary>
                  <BtnPrimary onClick={submitBulk} disabled={bulkUploading}>{bulkUploading ? "Uploading..." : "Confirm & Upload"}</BtnPrimary>
                </div>
              </div>
            )}
          </div>
        </Drawer>
      )}
      
      <datalist id="bom-sections-list">
        {SECTIONS.map(s => <option key={s} value={s} />)}
      </datalist>
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title}
        message={confirm?.message}
        onConfirm={confirm?.onConfirm}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

function Row({ label, value, bold, color }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-slate-500 uppercase tracking-wider">{label}</span>
      <span className={`font-mono ${bold ? "font-bold" : ""}`} style={color ? { color } : {}}>{value}</span>
    </div>
  );
}
function CostRow({ label, value, bold, big, small, accent }) {
  return (
    <div className={`flex justify-between items-baseline ${big ? "py-1" : "py-0.5"}`}>
      <span className={`uppercase tracking-wider ${small ? "text-[10px] text-slate-500" : "text-xs text-slate-400"}`}>{label}</span>
      <span className={`font-mono ${bold ? "font-bold" : ""} ${big ? "text-xl text-[#C27842]" : "text-sm"} ${accent ? "text-[#C27842]" : "text-white"}`}>{value}</span>
    </div>
  );
}
