import { useEffect, useState } from "react";
import { http } from "../lib/api";
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
import { Plus, Trash2, Pencil, Save, Phone } from "lucide-react";

const SKILLS = [
  { key: "cutting", label: "Cutting" },
  { key: "upper", label: "Upper Making" },
  { key: "bottom", label: "Bottom / Insole" },
  { key: "stitching", label: "Stitching" },
  { key: "lasting", label: "Lasting" },
  { key: "sole_pasting", label: "Sole Pasting" },
  { key: "finishing", label: "Finishing" },
  { key: "qc_pack", label: "QC & Pack" },
  { key: "general", label: "General" },
];

const SKILL_COLOR = {
  cutting: "blue",
  upper: "orange",
  bottom: "yellow",
  stitching: "red",
  lasting: "slate",
  sole_pasting: "orange",
  finishing: "green",
  qc_pack: "indigo",
  general: "slate",
};

const empty = {
  name: "",
  phone: "",
  skill: "general",
  rate_per_pair: 0,
  active: true,
  notes: "",
  bonus_pct: 0,
  target_cycle_days: 0,
};

export default function Workers() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(empty);
  const [filterSkill, setFilterSkill] = useState("");
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    const { data } = await http.get("/workers");
    setItems(data);
  };
  useEffect(() => {
    load();
  }, []);

  const startNew = () => {
    setEditId(null);
    setForm(empty);
    setOpen(true);
  };
  const startEdit = (w) => {
    setEditId(w.id);
    setForm({ ...empty, ...w });
    setOpen(true);
  };
  const save = async () => {
    const body = {
      ...form,
      rate_per_pair: Number(form.rate_per_pair || 0),
      active: !!form.active,
      bonus_pct: Number(form.bonus_pct || 0),
      target_cycle_days: Number(form.target_cycle_days || 0),
    };
    if (editId) await http.patch(`/workers/${editId}`, body);
    else await http.post("/workers", body);
    setOpen(false);
    load();
  };
  const remove = (w) => {
    if (w.active !== false) {
      setConfirm({
        title: "Deactivate Karigar",
        message: `Are you sure you want to deactivate karigar "${w.name}"?`,
        onConfirm: async () => {
          await http.delete(`/workers/${w.id}`);
          setConfirm(null);
          load();
        },
      });
    } else {
      setConfirm({
        title: "Reactivate Karigar",
        message: `Are you sure you want to reactivate karigar "${w.name}"?`,
        onConfirm: async () => {
          await http.patch(`/workers/${w.id}`, { ...w, active: true });
          setConfirm(null);
          load();
        },
      });
    }
  };

  const filtered = items.filter((w) => !filterSkill || w.skill === filterSkill);

  return (
    <div>
      <PageHeader
        title="Karigars / Labour"
        subtitle="Master / Karigars"
        testId="workers-header"
        action={
          <BtnPrimary
            onClick={startNew}
            data-testid="add-worker-btn"
            className="px-3 sm:px-5"
          >
            <Plus className="w-3.5 h-3.5 inline -mt-0.5" />
            <span className="hidden sm:inline ml-1">Add Karigar</span>
          </BtnPrimary>
        }
      />
      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        <div className="flex gap-3 items-end">
          <div className="w-60">
            <Select
              label="Filter by Skill"
              value={filterSkill}
              onChange={(e) => setFilterSkill(e.target.value)}
              testId="filter-skill"
            >
              <option value="">All skills</option>
              {SKILLS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="ml-auto text-xs uppercase tracking-wider text-slate-500 pb-2">
            <span className="font-bold text-slate-900 font-mono text-lg">
              {filtered.length}
            </span>{" "}
            / {items.length} karigars
          </div>
        </div>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="workers-table">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-3 font-bold">Name</th>
                  <th className="px-4 py-3 font-bold">Skill</th>
                  <th className="px-4 py-3 font-bold">Phone</th>
                  <th className="px-4 py-3 font-bold text-right">Rate/pair</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan="6"
                      className="px-6 py-10 text-center text-slate-400"
                    >
                      No karigars yet. Add your first karigar so you can assign
                      them to production cards.
                    </td>
                  </tr>
                ) : (
                  filtered.map((w) => (
                    <tr
                      key={w.id}
                      className={`border-b border-slate-100 hover:bg-slate-50 ${w.active === false ? "opacity-50 line-through bg-slate-50 text-slate-400" : ""}`}
                    >
                      <td className="px-4 py-3 font-bold">{w.name}</td>
                      <td className="px-4 py-3">
                        <Badge color={SKILL_COLOR[w.skill] || "slate"}>
                          {(SKILLS.find((s) => s.key === w.skill) || {})
                            .label || w.skill}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        <Phone className="w-3 h-3 inline -mt-0.5 mr-1 text-slate-400" />
                        {w.phone || "—"}
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-bold">
                        ₹{w.rate_per_pair}
                      </td>
                      <td className="px-4 py-3">
                        <Badge color={w.active === false ? "red" : "green"}>
                          {w.active === false ? "Inactive" : "Active"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => startEdit(w)}
                          className="text-slate-600 hover:text-[#2563EB] p-1.5"
                          disabled={w.active === false}
                          title="Edit"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => remove(w)}
                          className="text-slate-600 hover:text-red-600 p-1.5 ml-1"
                          title={
                            w.active === false ? "Reactivate" : "Deactivate"
                          }
                          data-testid={`delete-worker-${w.name}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {open && (
        <Drawer
          onClose={() => setOpen(false)}
          title={editId ? "Edit Karigar" : "New Karigar"}
        >
          <div className="space-y-3">
            <Input
              label="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              testId="form-worker-name"
            />
            <Input
              label="Phone"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
            <Select
              label="Skill"
              value={form.skill}
              onChange={(e) => setForm({ ...form, skill: e.target.value })}
              testId="form-worker-skill"
            >
              {SKILLS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </Select>
            <Input
              label="Rate per pair (₹) – default"
              type="number"
              step="0.5"
              value={form.rate_per_pair}
              onChange={(e) =>
                setForm({ ...form, rate_per_pair: e.target.value })
              }
            />
            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-dashed border-slate-200">
              <Input
                label="Productivity Bonus %"
                type="number"
                step="0.5"
                value={form.bonus_pct}
                onChange={(e) =>
                  setForm({ ...form, bonus_pct: e.target.value })
                }
                testId="form-worker-bonus"
              />
              <Input
                label="Target Cycle (days)"
                type="number"
                step="0.5"
                value={form.target_cycle_days}
                onChange={(e) =>
                  setForm({ ...form, target_cycle_days: e.target.value })
                }
                testId="form-worker-cycle"
              />
            </div>
            <div className="text-[10px] text-slate-500 italic">
              If a job is completed within Target Cycle days of assignment,
              karigar earns extra Bonus % on that job. Set both to 0 to disable.
            </div>
            <Input
              label="Notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm({ ...form, active: e.target.checked })}
                className="w-4 h-4"
              />
              <span>Active</span>
            </label>
            <div className="flex gap-2 pt-3">
              <BtnPrimary onClick={save} data-testid="save-worker-btn">
                <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
              </BtnPrimary>
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
