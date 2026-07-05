import { useEffect, useState } from "react";
import { http } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Input, Select, Badge, ConfirmDialog } from "../components/ui-kit";
import { Drawer } from "./Materials";
import { Plus, Trash2, Pencil, Save, AlertOctagon } from "lucide-react";

const STAGES = ["procurement", "cutting", "folding", "attachment", "stitching", "lasting", "sole_pasting", "finishing"];
const DEFECT_TYPES = ["Material", "Workmanship", "Machine", "Design", "Operator Error", "Other"];
const STATUSES = ["open", "in_progress", "closed"];

const empty = {
  po_number: "", article: "", stage: "cutting", defect_type: "Workmanship",
  description: "", defective_qty: 0, root_cause: "", responsible_dept: "",
  corrective_action: "", rework_qty: 0, rework_completed: false,
  final_rejection_qty: 0, cost: 0, status: "open",
};

export default function Defects() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(empty);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    const { data } = await http.get("/defects");
    setItems(data);
  };
  useEffect(() => { load(); }, []);

  const startNew = () => { setEditId(null); setForm(empty); setOpen(true); };
  const startEdit = (d) => { setEditId(d.id); setForm({ ...empty, ...d }); setOpen(true); };
  const save = async () => {
    const body = {
      ...form,
      defective_qty: Number(form.defective_qty), rework_qty: Number(form.rework_qty),
      final_rejection_qty: Number(form.final_rejection_qty), cost: Number(form.cost),
    };
    if (editId) await http.patch(`/defects/${editId}`, body); else await http.post("/defects", body);
    setOpen(false); load();
  };
  const remove = (id) => {
    setConfirm({
      title: "Delete Defect Record",
      message: "Are you sure you want to delete this defect record? Rework and scrap costs will be deleted from reports.",
      onConfirm: async () => {
        await http.delete(`/defects/${id}`);
        setConfirm(null);
        load();
      }
    });
  };

  const statusColor = { open: "red", in_progress: "yellow", closed: "green" };

  return (
    <div>
      <PageHeader
        title="Defect & Rework Tracker"
        subtitle="Quality / Defects"
        testId="defects-header"
        action={
          <BtnPrimary onClick={startNew} data-testid="add-defect-btn" className="px-3 sm:px-5">
            <Plus className="w-3.5 h-3.5 inline -mt-0.5" />
            <span className="hidden sm:inline ml-1">Log Defect</span>
          </BtnPrimary>
        }
      />
      <div className="p-4 sm:p-8">
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="defects-table">
            <thead className="bg-slate-50 border-b-2 border-slate-200">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-3 py-3 font-bold">PO #</th>
                <th className="px-3 py-3 font-bold">Stage</th>
                <th className="px-3 py-3 font-bold">Type</th>
                <th className="px-3 py-3 font-bold">Description</th>
                <th className="px-3 py-3 font-bold text-right">Qty</th>
                <th className="px-3 py-3 font-bold text-right">Cost</th>
                <th className="px-3 py-3 font-bold">Status</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan="8" className="px-6 py-10 text-center text-slate-400">No defects logged. Quality is on track.</td></tr>
              ) : items.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono font-bold">{d.po_number}</td>
                  <td className="px-3 py-2 text-xs uppercase">{d.stage}</td>
                  <td className="px-3 py-2"><Badge color="slate">{d.defect_type}</Badge></td>
                  <td className="px-3 py-2 text-xs max-w-md truncate">{d.description}</td>
                  <td className="px-3 py-2 text-right font-mono">{d.defective_qty}</td>
                  <td className="px-3 py-2 text-right font-mono">₹{d.cost || 0}</td>
                  <td className="px-3 py-2"><Badge color={statusColor[d.status]}>{d.status.replace("_", " ")}</Badge></td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => startEdit(d)} className="p-1.5 text-slate-600 hover:text-[#2563EB]"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => remove(d.id)} className="p-1.5 text-slate-600 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {open && (
        <Drawer onClose={() => setOpen(false)} title={editId ? "Edit Defect" : "Log Defect"}>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Input label="PO Number" value={form.po_number} onChange={(e) => setForm({ ...form, po_number: e.target.value })} testId="form-defect-po" />
              <Input label="Article" value={form.article} onChange={(e) => setForm({ ...form, article: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Select label="Stage" value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>
                {STAGES.map(s => <option key={s} value={s}>{s}</option>)}
              </Select>
              <Select label="Defect Type" value={form.defect_type} onChange={(e) => setForm({ ...form, defect_type: e.target.value })}>
                {DEFECT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </Select>
            </div>
            <Input label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} testId="form-defect-desc" />
            <div className="grid grid-cols-3 gap-3">
              <Input label="Defective Qty" type="number" value={form.defective_qty} onChange={(e) => setForm({ ...form, defective_qty: e.target.value })} />
              <Input label="Rework Qty" type="number" value={form.rework_qty} onChange={(e) => setForm({ ...form, rework_qty: e.target.value })} />
              <Input label="Final Rejected" type="number" value={form.final_rejection_qty} onChange={(e) => setForm({ ...form, final_rejection_qty: e.target.value })} />
            </div>
            <Input label="Root Cause" value={form.root_cause} onChange={(e) => setForm({ ...form, root_cause: e.target.value })} />
            <Input label="Corrective Action" value={form.corrective_action} onChange={(e) => setForm({ ...form, corrective_action: e.target.value })} />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Cost (₹)" type="number" step="0.01" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
              <Select label="Status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </Select>
            </div>
            <div className="flex gap-2 pt-3">
              <BtnPrimary onClick={save} data-testid="save-defect-btn"><Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save</BtnPrimary>
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
