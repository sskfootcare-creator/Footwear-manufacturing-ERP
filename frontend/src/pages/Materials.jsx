import { useEffect, useState } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Input, Select, Badge, ConfirmDialog } from "../components/ui-kit";
import { Plus, Trash2, Pencil, X, Save } from "lucide-react";

const CATEGORIES = ["upper", "sole", "lining", "accessory", "consumable", "packing", "other"];
const UNITS = ["sqft", "pcs", "kg", "gm", "ltr", "ml", "mtr", "set"];

const emptyForm = { code: "", name: "", category: "upper", unit: "sqft", rate: 0, reorder_level: 0, notes: "" };

export default function Materials() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("");
  const [filterCat, setFilterCat] = useState("");
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    const { data } = await http.get("/materials");
    setItems(data);
  };
  useEffect(() => { load(); }, []);

  const startNew = () => { setEdit(null); setForm(emptyForm); setOpen(true); };
  const startEdit = (m) => { setEdit(m.id); setForm({ code: m.code, name: m.name, category: m.category, unit: m.unit, rate: m.rate, reorder_level: m.reorder_level || 0, notes: m.notes || "" }); setOpen(true); };
  const save = async () => {
    try {
      const body = { ...form, rate: Number(form.rate), reorder_level: Number(form.reorder_level || 0) };
      if (edit) await http.patch(`/materials/${edit}`, body); else await http.post("/materials", body);
      setOpen(false); load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };
  const remove = (id) => {
    setConfirm({
      title: "Delete Material",
      message: "Are you sure you want to delete this material? This will remove the material from catalog listings and history references.",
      onConfirm: async () => {
        await http.delete(`/materials/${id}`);
        setConfirm(null);
        load();
      }
    });
  };

  const filtered = items.filter((m) => {
    if (filterCat && m.category !== filterCat) return false;
    if (filter && !`${m.code} ${m.name}`.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

  return (
    <div>
      <PageHeader
        title="Materials Rate Card"
        subtitle="Master / Materials"
        testId="materials-header"
        action={<BtnPrimary onClick={startNew} data-testid="add-material-btn"><Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Add Material</BtnPrimary>}
      />

      <div className="p-8 space-y-4">
        <div className="flex gap-3 items-end">
          <div className="flex-1 max-w-md">
            <Input testId="materials-search" label="Search" placeholder="Code or name..." value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
          <div className="w-48">
            <Select label="Category" value={filterCat} onChange={(e) => setFilterCat(e.target.value)} testId="materials-filter-cat">
              <option value="">All categories</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </div>
          <div className="ml-auto text-xs uppercase tracking-wider text-slate-500 pb-2">
            <span className="font-bold text-slate-900 font-mono text-lg">{filtered.length}</span> / {items.length} materials
          </div>
        </div>

        <Card className="overflow-hidden">
          <table className="w-full text-sm" data-testid="materials-table">
            <thead className="bg-slate-50 border-b-2 border-slate-200 sticky top-0">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-4 py-3 font-bold">Code</th>
                <th className="px-4 py-3 font-bold">Name</th>
                <th className="px-4 py-3 font-bold">Category</th>
                <th className="px-4 py-3 font-bold">Unit</th>
                <th className="px-4 py-3 font-bold text-right">Rate (₹)</th>
                <th className="px-4 py-3 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan="6" className="px-6 py-10 text-center text-slate-400">No materials yet. Click "Add Material" to start.</td></tr>
              ) : filtered.map((m) => (
                <tr key={m.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono font-bold">{m.code}</td>
                  <td className="px-4 py-3">{m.name}</td>
                  <td className="px-4 py-3"><Badge color="slate">{m.category}</Badge></td>
                  <td className="px-4 py-3 text-xs uppercase tracking-wider">{m.unit}</td>
                  <td className="px-4 py-3 font-mono font-bold text-right">{inr(m.rate)}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => startEdit(m)} className="text-slate-600 hover:text-[#2563EB] p-1.5"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => remove(m.id)} className="text-slate-600 hover:text-red-600 p-1.5 ml-1"><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {open && (
        <Drawer onClose={() => setOpen(false)} title={edit ? "Edit Material" : "New Material"}>
          <div className="space-y-3">
            <Input label="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} testId="form-mat-code" />
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} testId="form-mat-name" />
            <div className="grid grid-cols-2 gap-3">
              <Select label="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
              <Select label="Unit" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })}>
                {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
              </Select>
            </div>
            <Input label="Rate (INR)" type="number" step="0.01" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} testId="form-mat-rate" />
            <Input label="Reorder Level (min stock)" type="number" step="0.5" value={form.reorder_level} onChange={(e) => setForm({ ...form, reorder_level: e.target.value })} testId="form-mat-reorder" />
            <Input label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            <div className="flex gap-2 pt-3">
              <BtnPrimary onClick={save} data-testid="save-material-btn"><Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}
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

export function Drawer({ title, onClose, children, width = "max-w-lg" }) {
  return (
    <div className="fixed inset-0 z-50 flex" data-testid="drawer-overlay">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className={`w-full ${width} bg-white border-l-2 border-slate-200 shadow-2xl flex flex-col`}>
        <div className="px-6 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-100"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </div>
    </div>
  );
}
