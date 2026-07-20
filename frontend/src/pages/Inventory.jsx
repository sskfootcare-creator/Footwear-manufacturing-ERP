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
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Plus,
  ArrowDownToLine,
  ArrowUpFromLine,
  Settings2,
  Save,
  History,
  AlertTriangle,
} from "lucide-react";

const TYPE_LABEL = {
  in: "STOCK IN",
  out: "CONSUMPTION",
  adjustment: "ADJUSTMENT",
};
const TYPE_COLOR = { in: "green", out: "orange", adjustment: "slate" };

export default function Inventory() {
  const [items, setItems] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState("");
  const [filterCat, setFilterCat] = useState("");
  const [open, setOpen] = useState(null);
  const [history, setHistory] = useState(null);
  const [materials, setMaterials] = useState([]);

  const load = async () => {
    const [inv, mats, al] = await Promise.all([
      http.get("/inventory"),
      http.get("/materials"),
      http.get("/inventory/alerts"),
    ]);
    setItems(inv.data);
    setMaterials(mats.data);
    setAlerts(al.data);
  };
  useEffect(() => {
    load();
  }, []);

  const openType = (type, material = null) => setOpen({ type, material });

  const openHistory = async (row) => {
    const { data } = await http.get(
      `/inventory/movements?material_id=${row.material_id}`,
    );
    setHistory({ ...row, movements: data });
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

  // KPIs
  const totalValue = filtered.reduce((s, r) => s + r.value, 0);
  const lowStock = filtered.filter((r) => r.balance <= 0).length;
  const categories = Array.from(
    new Set(items.map((i) => i.category).filter(Boolean)),
  );

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Stock / Inventory"
        testId="inventory-header"
        action={
          <div className="flex gap-2">
            <BtnPrimary
              onClick={() => openType("in")}
              data-testid="add-stock-in-btn"
              className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36] px-3 sm:px-5"
            >
              <ArrowDownToLine className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">Stock In</span>
            </BtnPrimary>
            <BtnPrimary
              onClick={() => openType("out")}
              data-testid="add-stock-out-btn"
              className="bg-[#F97316] border-[#F97316] hover:bg-[#C25510] px-3 sm:px-5"
            >
              <ArrowUpFromLine className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">Consume</span>
            </BtnPrimary>
            <BtnPrimary
              onClick={() => openType("adjustment")}
              data-testid="add-adjustment-btn"
              className="px-3 sm:px-5"
            >
              <Settings2 className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">Adjustment</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        {alerts.length > 0 && (
          <Card
            className="border-l-4 border-l-red-600 bg-red-50/40 p-4"
            data-testid="reorder-alerts"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-bold text-red-900 uppercase tracking-wider">
                  Reorder Alert · {alerts.length} material
                  {alerts.length > 1 ? "s" : ""} at or below minimum stock
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {alerts.map((a) => (
                    <div
                      key={a.material_id}
                      className="bg-white border border-red-200 px-3 py-1.5 text-xs"
                    >
                      <span className="font-mono font-bold">{a.code}</span>
                      <span className="text-slate-600 ml-2">{a.name}</span>
                      <span className="ml-2 font-mono">
                        <span className="text-red-700 font-bold">
                          {a.balance} {a.unit}
                        </span>
                        <span className="text-slate-400 mx-1">/</span>
                        <span className="text-slate-600">
                          {a.reorder_level} min
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KpiTile label="Materials" value={items.length} accent="#0F172A" />
          <KpiTile
            label="Stock Value"
            value={inr(totalValue)}
            accent="#C27842"
          />
          <KpiTile
            label="Out of Stock"
            value={lowStock}
            accent={lowStock > 0 ? "#DC2626" : "#16A34A"}
          />
        </div>

        <div className="flex flex-wrap gap-3 items-end">
          <div className="w-full sm:flex-1 sm:max-w-md">
            <Input
              testId="inventory-search"
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
            >
              <option value="">All</option>
              {categories.map((c) => (
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
            / {items.length}
          </div>
        </div>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="inventory-table">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-3 font-bold">Code</th>
                  <th className="px-3 py-3 font-bold">Material</th>
                  <th className="px-3 py-3 font-bold">Category</th>
                  <th className="px-3 py-3 font-bold">Unit</th>
                  <th className="px-3 py-3 font-bold text-right">In</th>
                  <th className="px-3 py-3 font-bold text-right">Out</th>
                  <th className="px-3 py-3 font-bold text-right">Adj</th>
                  <th className="px-3 py-3 font-bold text-right">Balance</th>
                  <th className="px-3 py-3 font-bold text-right">Value</th>
                  <th className="px-3 py-3 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan="10"
                      className="px-6 py-10 text-center text-slate-400"
                    >
                      No inventory data. Click "Stock In" to record your first
                      material purchase.
                    </td>
                  </tr>
                ) : (
                  filtered.map((r) => (
                    <tr
                      key={r.material_id}
                      className={`border-b border-slate-100 hover:bg-slate-50 ${r.balance <= 0 ? "bg-red-50/40" : ""}`}
                    >
                      <td className="px-3 py-2 font-mono font-bold">{r.code}</td>
                      <td className="px-3 py-2">{r.name}</td>
                      <td className="px-3 py-2">
                        <Badge color="slate">{r.category}</Badge>
                      </td>
                      <td className="px-3 py-2 text-xs uppercase tracking-wider">
                        {r.unit}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-green-700">
                        {r.stock_in}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-orange-700">
                        {r.stock_out}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-slate-500">
                        {r.adjustments}
                      </td>
                      <td
                        className={`px-3 py-2 text-right font-mono font-bold ${r.balance <= 0 ? "text-red-700" : "text-slate-900"}`}
                      >
                        {r.balance <= 0 && (
                          <AlertTriangle className="w-3 h-3 inline -mt-0.5 mr-1 text-red-500" />
                        )}
                        {r.balance}
                      </td>
                      <td className="px-3 py-2 text-right font-mono">
                        {inr(r.value)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => openType("in", r)}
                          className="p-1.5 text-slate-600 hover:text-green-700"
                          title="Stock In"
                          data-testid={`row-in-${r.code}`}
                        >
                          <ArrowDownToLine className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openType("out", r)}
                          className="p-1.5 text-slate-600 hover:text-orange-700 ml-1"
                          title="Consume"
                        >
                          <ArrowUpFromLine className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openHistory(r)}
                          className="p-1.5 text-slate-600 hover:text-[#2563EB] ml-1"
                          title="History"
                          data-testid={`row-history-${r.code}`}
                        >
                          <History className="w-4 h-4" />
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
        <MovementDrawer
          type={open.type}
          material={open.material}
          materials={materials}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null);
            load();
          }}
        />
      )}
      {history && (
        <Drawer
          onClose={() => setHistory(null)}
          title={`Movement History – ${history.name}`}
          width="max-w-2xl"
        >
          <div className="overflow-x-auto">
            <table
              className="w-full text-xs"
              data-testid="movement-history-table"
            >
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-2 py-2 font-bold">Date</th>
                  <th className="px-2 py-2 font-bold">Type</th>
                  <th className="px-2 py-2 font-bold text-right">Qty</th>
                  <th className="px-2 py-2 font-bold text-right">Rate</th>
                  <th className="px-2 py-2 font-bold">Party / Note</th>
                  <th className="px-2 py-2 font-bold">By</th>
                </tr>
              </thead>
              <tbody>
                {history.movements.length === 0 ? (
                  <tr>
                    <td
                      colSpan="6"
                      className="px-3 py-8 text-center text-slate-400"
                    >
                      No movements yet.
                    </td>
                  </tr>
                ) : (
                  history.movements.map((m) => (
                    <tr key={m.id} className="border-b border-slate-100">
                      <td className="px-2 py-1.5 font-mono">
                        {(m.date || m.created_at || "").slice(0, 10)}
                      </td>
                      <td className="px-2 py-1.5">
                        <Badge color={TYPE_COLOR[m.type]}>
                          {TYPE_LABEL[m.type]}
                        </Badge>
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono font-bold">
                        {m.quantity}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {m.rate ? `₹${m.rate}` : "—"}
                      </td>
                      <td className="px-2 py-1.5">{m.party || m.notes || "—"}</td>
                      <td className="px-2 py-1.5 text-xs text-slate-500">
                        {m.by}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Drawer>
      )}
    </div>
  );
}

function KpiTile({ label, value, accent }) {
  return (
    <Card className="p-3 sm:p-5 relative overflow-hidden">
      <div>
        <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate">
          {label}
        </div>
        <div
          className="font-mono text-lg sm:text-2xl lg:text-3xl font-bold mt-2 truncate"
          title={String(value)}
        >
          {value}
        </div>
      </div>
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ background: accent }}
      />
    </Card>
  );
}

function MovementDrawer({ type, material, materials, onClose, onSaved }) {
  const [form, setForm] = useState({
    material_id: material?.material_id || material?.id || "",
    quantity: 0,
    rate: material?.last_purchase_rate || material?.current_rate || 0,
    party: "",
    notes: "",
    date: new Date().toISOString().slice(0, 10),
  });
  const titleMap = {
    in: "Stock In (Purchase)",
    out: "Consumption / Stock Out",
    adjustment: "Stock Adjustment",
  };
  const submit = async () => {
    try {
      await http.post("/inventory/movements", {
        ...form,
        type,
        quantity: Number(form.quantity),
        rate: form.rate === "" ? null : Number(form.rate),
      });
      onSaved();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };
  const selectedMaterial = materials.find((m) => m.id === form.material_id);

  return (
    <Drawer onClose={onClose} title={titleMap[type]}>
      <div className="space-y-3">
        <div>
          <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
            Material
          </label>
          <select
            value={form.material_id}
            onChange={(e) => setForm({ ...form, material_id: e.target.value })}
            className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none"
            data-testid="movement-material"
          >
            <option value="">— Select material —</option>
            {materials.map((m) => (
              <option key={m.id} value={m.id}>
                {m.code} — {m.name} ({m.unit})
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input
            label={
              type === "adjustment"
                ? `Quantity (use negative for reduction)${selectedMaterial ? ` [${selectedMaterial.unit}]` : ""}`
                : `Quantity${selectedMaterial ? ` [${selectedMaterial.unit}]` : ""}`
            }
            type="number"
            step="0.01"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            testId="movement-qty"
          />
          {type === "in" && (
            <Input
              label="Rate (₹)"
              type="number"
              step="0.01"
              value={form.rate}
              onChange={(e) => setForm({ ...form, rate: e.target.value })}
              testId="movement-rate"
            />
          )}
        </div>
        <Input
          label={type === "in" ? "Supplier" : "Reference (PO / job)"}
          value={form.party}
          onChange={(e) => setForm({ ...form, party: e.target.value })}
        />
        <Input
          label="Date"
          type="date"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
        <Input
          label="Notes"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
        />
        <div className="flex gap-2 pt-3 border-t border-slate-200">
          <BtnPrimary onClick={submit} data-testid="movement-save">
            <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
          </BtnPrimary>
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}
