import { useEffect, useState } from "react";
import { http, inr } from "../lib/api";
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
import ImageUploader, { ImageThumb } from "../components/ImageUploader";
import { Plus, Trash2, Pencil, X, Save } from "lucide-react";

const CATEGORIES = [
  "upper",
  "sole",
  "lining",
  "accessory",
  "consumable",
  "packing",
  "other",
];
const UNITS = ["sqft", "pcs", "kg", "gm", "ltr", "ml", "mtr", "set"];

const emptyForm = {
  code: "",
  name: "",
  category: "upper",
  unit: "sqft",
  rate: 0,
  reorder_level: 0,
  preferred_vendor_id: "",
  notes: "",
  image_url: "",
  image_display_url: "",
  image_thumbnail_url: "",
};

export default function Materials() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("");
  const [filterCat, setFilterCat] = useState("");
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [confirm, setConfirm] = useState(null);

  const [vendors, setVendors] = useState([]);

  const load = async () => {
    const [matsRes, vendorsRes] = await Promise.all([
      http.get("/materials"),
      http.get("/vendors?include_inactive=true"),
    ]);
    setItems(matsRes.data || []);
    setVendors(vendorsRes.data || []);
  };
  useEffect(() => {
    load();
  }, []);

  const startNew = () => {
    setEdit(null);
    setForm(emptyForm);
    setFormError("");
    setOpen(true);
  };
  const startEdit = (m) => {
    setEdit(m.id);
    setForm({
      code: m.code,
      name: m.name,
      category: m.category,
      unit: m.unit,
      rate: m.rate,
      reorder_level: m.reorder_level || 0,
      preferred_vendor_id: m.preferred_vendor_id || "",
      notes: m.notes || "",
      image_url: m.image_url || "",
      image_display_url: m.image_display_url || "",
      image_thumbnail_url: m.image_thumbnail_url || "",
    });
    setFormError("");
    setOpen(true);
  };
  const save = async () => {
    setFormError("");
    try {
      const body = {
        ...form,
        rate: Number(form.rate),
        reorder_level: Number(form.reorder_level || 0),
      };
      if (edit) await http.patch(`/materials/${edit}`, body);
      else await http.post("/materials", body);
      setOpen(false);
      load();
    } catch (e) {
      setFormError(e.response?.data?.detail || e.message);
    }
  };
  const remove = (id) => {
    setConfirm({
      title: "Delete Material",
      message:
        "Are you sure you want to delete this material? This will remove the material from catalog listings and history references.",
      onConfirm: async () => {
        await http.delete(`/materials/${id}`);
        setConfirm(null);
        load();
      },
    });
  };

  const filtered = items.filter((m) => {
    if (filterCat && m.category !== filterCat) return false;
    if (
      filter &&
      !`${m.code} ${m.name}`.toLowerCase().includes(filter.toLowerCase())
    )
      return false;
    return true;
  });

  return (
    <div>
      <PageHeader
        title="Materials Rate Card"
        subtitle="Master / Materials"
        testId="materials-header"
        action={
          <BtnPrimary
            onClick={startNew}
            data-testid="add-material-btn"
            className="px-3 sm:px-5"
          >
            <Plus className="w-3.5 h-3.5 inline -mt-0.5" />
            <span className="hidden sm:inline ml-1">Add Material</span>
          </BtnPrimary>
        }
      />

      <div className="p-4 sm:p-8 space-y-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="w-full sm:flex-1 sm:max-w-md">
            <Input
              testId="materials-search"
              label="Search"
              placeholder="Code or name..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="w-full sm:w-48">
            <Select
              label="Category"
              value={filterCat}
              onChange={(e) => setFilterCat(e.target.value)}
              testId="materials-filter-cat"
            >
              <option value="">All categories</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          <div className="ml-auto text-xs uppercase tracking-wider text-slate-500 pb-2">
            <span className="font-bold text-slate-900 font-mono text-lg">
              {filtered.length}
            </span>{" "}
            / {items.length} materials
          </div>
        </div>

        <Card className="overflow-hidden">
          <table className="w-full text-sm" data-testid="materials-table">
            <thead className="bg-slate-50 border-b-2 border-slate-200 sticky top-0">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-4 py-3 font-bold w-14"></th>
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
                <tr>
                  <td
                    colSpan="7"
                    className="px-6 py-10 text-center text-slate-400"
                  >
                    No materials yet. Click &quot;Add Material&quot; to start.
                  </td>
                </tr>
              ) : (
                filtered.map((m) => (
                  <tr
                    key={m.id}
                    className="border-b border-slate-100 hover:bg-slate-50"
                    data-testid={`material-row-${m.code}`}
                  >
                    <td className="px-4 py-2">
                      <ImageThumb
                        image={{
                          thumbnail_url: m.image_thumbnail_url,
                          display_url: m.image_display_url,
                          url: m.image_url,
                        }}
                        size={36}
                        alt={`${m.code} — ${m.name}`}
                        className="rounded"
                        clickable
                        testId={`material-thumb-${m.code}`}
                      />
                    </td>
                    <td className="px-4 py-3 font-mono font-bold">{m.code}</td>
                    <td className="px-4 py-3">{m.name}</td>
                    <td className="px-4 py-3">
                      <Badge color="slate">{m.category}</Badge>
                    </td>
                    <td className="px-4 py-3 text-xs uppercase tracking-wider">
                      {m.unit}
                    </td>
                    <td className="px-4 py-3 font-mono font-bold text-right">
                      {inr(m.rate)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => startEdit(m)}
                        className="text-slate-600 hover:text-[#2563EB] p-1.5"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => remove(m.id)}
                        className="text-slate-600 hover:text-red-600 p-1.5 ml-1"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </div>

      {open && (
        <Drawer
          onClose={() => {
            setOpen(false);
            setFormError("");
          }}
          title={edit ? "Edit Material" : "New Material"}
        >
          <div className="space-y-3">
            <ImageUploader
              label="Material Image"
              maxSizeMB={8}
              testIdPrefix="material-image"
              value={{
                url: form.image_url,
                display_url: form.image_display_url,
                thumbnail_url: form.image_thumbnail_url,
              }}
              onChange={(imgObj) =>
                setForm((f) => ({
                  ...f,
                  image_url: imgObj.url || "",
                  image_display_url: imgObj.display_url || "",
                  image_thumbnail_url: imgObj.thumbnail_url || "",
                }))
              }
            />
            <div>
              <Input
                label="Code"
                value={form.code}
                onChange={(e) => {
                  setFormError("");
                  setForm({ ...form, code: e.target.value });
                }}
                testId="form-mat-code"
              />
              {formError && (
                <p
                  className="mt-1 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2"
                  data-testid="form-mat-error"
                >
                  {formError}
                </p>
              )}
            </div>
            <Input
              label="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              testId="form-mat-name"
            />
            <div className="grid grid-cols-2 gap-3">
              <Select
                label="Category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
              <Select
                label="Unit"
                value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })}
              >
                {UNITS.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </Select>
            </div>
            <Input
              label="Rate (INR)"
              type="number"
              step="0.01"
              value={form.rate}
              onChange={(e) => setForm({ ...form, rate: e.target.value })}
              testId="form-mat-rate"
            />
            <Input
              label="Reorder Level (min stock)"
              type="number"
              step="0.5"
              value={form.reorder_level}
              onChange={(e) =>
                setForm({ ...form, reorder_level: e.target.value })
              }
              testId="form-mat-reorder"
            />
            <Select
              label="Preferred Vendor"
              value={form.preferred_vendor_id}
              onChange={(e) =>
                setForm({ ...form, preferred_vendor_id: e.target.value })
              }
              testId="form-mat-vendor"
            >
              <option value="">-- No Preferred Vendor --</option>
              {vendors.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </Select>
            <Input
              label="Notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
            <div className="flex gap-2 pt-3">
              <BtnPrimary onClick={save} data-testid="save-material-btn">
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

export function Drawer({ title, onClose, children, width = "max-w-lg" }) {
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "unset";
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      data-testid="drawer-overlay"
    >
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className={`relative w-full ${width} bg-white border-l-2 border-slate-200 shadow-2xl flex flex-col h-full z-10`}
      >
        <div className="px-4 sm:px-6 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-100">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">{children}</div>
      </div>
    </div>
  );
}
