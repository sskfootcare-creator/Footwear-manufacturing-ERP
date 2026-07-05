import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Badge, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { FileText, Plus, Pencil, Trash2, X, AlertCircle, Calendar } from "lucide-react";
import { useAuth } from "../lib/auth";

const STATUS_COLOR = {
  draft: "slate",
  sent: "blue",
  partially_received: "yellow",
  received: "green",
  cancelled: "red"
};


const EMPTY_LINE = { material_id: "", quantity: 0, rate: 0, amount: 0 };

export default function VendorPOs() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const canWrite = ["admin", "manager"].includes(user?.role);

  const [pos, setPos] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [drawer, setDrawer] = useState(null); // null | { mode: "add" | "edit", po?: {} }
  const [form, setForm] = useState({ vendor_id: "", status: "draft", expected_delivery_date: "", notes: "", line_items: [] });
  const [receiveModal, setReceiveModal] = useState(null); // null | po
  const [receiveForm, setReceiveForm] = useState({ receipt_id: "", items: [] });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [poRes, vendorRes, matRes] = await Promise.all([
        http.get("/vendor-pos"),
        http.get("/vendors?include_inactive=true"),
        http.get("/materials")
      ]);
      setPos(poRes.data || []);
      setVendors(vendorRes.data || []);
      setMaterials(matRes.data || []);
    } catch (e) {
      console.error("Failed to load PO data", e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // Handle prefilled data from shortage redirect
  useEffect(() => {
    if (location.state && location.state.prefill && vendors.length > 0 && materials.length > 0) {
      const { vendor_id, items } = location.state.prefill;

      // Clear location state to prevent triggering on page refreshes
      navigate(location.pathname, { replace: true, state: {} });

      const mappedLines = items.map(it => {
        // match material_id
        const mat = materials.find(m => m.id === it.material_id || m.code === it.code);
        return {
          material_id: mat ? mat.id : "",
          quantity: it.shortage || 0,
          rate: mat ? mat.rate : 0,
          amount: (it.shortage || 0) * (mat ? mat.rate : 0)
        };
      });

      setForm({
        vendor_id: vendor_id || "",
        status: "draft",
        expected_delivery_date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0], // default +7d
        notes: "Raised automatically from stock shortage check.",
        line_items: mappedLines
      });
      setError("");
      setDrawer({ mode: "add" });
    }
  }, [location.state, vendors, materials, navigate, location.pathname]);

  const filtered = pos.filter(po => {
    const vName = po.vendor_name || "";
    const poNo = po.po_number || "";
    const matchesSearch = `${poNo} ${vName}`.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = filterStatus === "all" || po.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  // Calculate totals
  const totalCount = pos.length;
  const draftCount = pos.filter(p => p.status === "draft").length;
  const sentCount = pos.filter(p => p.status === "sent" || p.status === "partially_received").length;
  const receivedCount = pos.filter(p => p.status === "received").length;

  const openAdd = () => {
    setForm({
      vendor_id: vendors[0]?.id || "",
      status: "draft",
      expected_delivery_date: "",
      notes: "",
      line_items: [{ ...EMPTY_LINE }]
    });
    setError("");
    setDrawer({ mode: "add" });
  };

  const openEdit = (po) => {
    setForm({
      vendor_id: po.vendor_id || "",
      status: po.status || "draft",
      expected_delivery_date: po.expected_delivery_date || "",
      notes: po.notes || "",
      line_items: (po.line_items || []).map(li => ({
        material_id: li.material_id || "",
        quantity: li.quantity || 0,
        rate: li.rate || 0,
        amount: li.amount || 0,
        received_quantity: li.received_quantity || 0
      }))
    });
    setError("");
    setDrawer({ mode: "edit", po });
  };

  const openReceive = (po) => {
    const rId = "rcpt_" + Date.now().toString(36) + Math.random().toString(36).substring(2, 7);
    setReceiveForm({
      receipt_id: rId,
      items: (po.line_items || []).map(li => ({
        material_id: li.material_id,
        quantity: 0.0,
        material_code: materials.find(m => m.id === li.material_id)?.code || "",
        material_name: materials.find(m => m.id === li.material_id)?.name || "",
        ordered: li.quantity || 0,
        received: li.received_quantity || 0
      }))
    });
    setReceiveModal(po);
    setError("");
  };

  const handleReceive = async () => {
    const validItems = receiveForm.items.filter(item => Number(item.quantity) > 0);
    if (validItems.length === 0) {
      setError("Please enter a positive quantity to receive for at least one item.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        receipt_id: receiveForm.receipt_id,
        items: validItems.map(item => ({
          material_id: item.material_id,
          quantity: Number(item.quantity)
        }))
      };
      await http.post(`/vendor-pos/${receiveModal.id}/receive`, payload);
      await load();
      setReceiveModal(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const closeDrawer = () => setDrawer(null);

  const addLine = () => {
    setForm(f => ({ ...f, line_items: [...f.line_items, { ...EMPTY_LINE }] }));
  };

  const removeLine = (idx) => {
    setForm(f => ({ ...f, line_items: f.line_items.filter((_, i) => i !== idx) }));
  };

  const handleLineChange = (idx, key, val) => {
    setForm(f => {
      const nextLines = [...f.line_items];
      const line = { ...nextLines[idx] };
      line[key] = val;

      // Auto lookup rate if material changes
      if (key === "material_id") {
        const mat = materials.find(m => m.id === val);
        if (mat) {
          line.rate = mat.rate;
        }
      }

      // Recompute amount
      const q = Number(line.quantity || 0);
      const r = Number(line.rate || 0);
      line.amount = roundTo2(q * r);

      nextLines[idx] = line;
      return { ...f, line_items: nextLines };
    });
  };

  const handleSave = async () => {
    if (!form.vendor_id) { setError("Please select a vendor."); return; }
    const validLines = form.line_items.filter(li => li.material_id && Number(li.quantity) > 0);
    if (validLines.length === 0) { setError("PO must contain at least one line item with a material and positive quantity."); return; }

    setSaving(true);
    setError("");
    try {
      const payload = {
        vendor_id: form.vendor_id,
        status: form.status,
        expected_delivery_date: form.expected_delivery_date || "",
        notes: form.notes || "",
        line_items: validLines.map(li => ({
          material_id: li.material_id,
          quantity: Number(li.quantity),
          rate: Number(li.rate),
          amount: Number(li.amount)
        }))
      };

      if (drawer.mode === "add") {
        await http.post("/vendor-pos", payload);
      } else {
        await http.patch(`/vendor-pos/${drawer.po.id}`, payload);
      }
      await load();
      closeDrawer();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (po) => {
    if (!window.confirm(`Are you sure you want to delete ${po.po_number}?`)) return;
    try {
      await http.delete(`/vendor-pos/${po.id}`);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };

  const poGrandTotal = (po) => {
    return (po.line_items || []).reduce((s, li) => s + (li.amount || 0), 0);
  };

  const formGrandTotal = form.line_items.reduce((s, li) => s + (li.amount || 0), 0);

  const roundTo2 = (num) => Math.round((num + Number.EPSILON) * 100) / 100;

  return (
    <div>
      <PageHeader
        title="Vendor Purchase Orders"
        subtitle="Accounts Payable / POs to Vendors"
        testId="vendor-pos-header"
        action={
          canWrite && (
            <BtnPrimary onClick={openAdd} data-testid="add-vendor-po-btn">
              <Plus className="w-3.5 h-3.5 inline mr-1.5" /> Raise PO
            </BtnPrimary>
          )
        }
      />

      <div className="p-8 space-y-5">
        {/* KPI Tiles */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="Total Raised" value={totalCount} accent="#0F172A" />
          <Tile label="Drafts" value={draftCount} accent="#64748B" />
          <Tile label="Open / Pending" value={sentCount} accent="#2563EB" />
          <Tile label="Fully Received" value={receivedCount} accent="#16A34A" />
        </div>

        {/* List card */}
        <Card className="overflow-hidden" data-testid="vendor-pos-card">
          <div className="px-5 py-3 border-b-2 border-slate-200 flex items-center justify-between gap-4 flex-wrap">
            <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#C27842]" />
              Purchase Orders List
              <span className="text-slate-500 font-mono ml-1">({filtered.length})</span>
            </h2>
            <div className="flex items-center gap-3">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search PO / Vendor..."
                className="border-2 border-slate-300 px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-60 font-mono"
              />
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="border-2 border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-[#C27842] outline-none"
              >
                <option value="all">All Statuses</option>
                <option value="draft">Draft</option>
                <option value="sent">Sent</option>
                <option value="partially_received">Partially Received</option>
                <option value="received">Received</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="p-16 text-center text-slate-400 text-sm" data-testid="vendor-pos-empty">
              <FileText className="w-10 h-10 mx-auto mb-3 opacity-20" />
              No vendor purchase orders found.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="vendor-pos-table">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-4 py-2 font-bold">PO Number</th>
                    <th className="px-4 py-2 font-bold">Vendor</th>
                    <th className="px-4 py-2 font-bold">Items Count</th>
                    <th className="px-4 py-2 font-bold text-right">Grand Total</th>
                    <th className="px-4 py-2 font-bold">Expected Delivery</th>
                    <th className="px-4 py-2 font-bold text-center">Status</th>
                    <th className="px-4 py-2 font-bold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(po => (
                    <tr key={po.id} data-testid={`vendor-po-row-${po.id}`} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-mono font-bold">{po.po_number}</td>
                      <td className="px-4 py-3 font-bold">{po.vendor_name}</td>
                      <td className="px-4 py-3 font-mono text-slate-600">{(po.line_items || []).length} lines</td>
                      <td className="px-4 py-3 text-right font-mono font-bold">{inr(poGrandTotal(po))}</td>
                      <td className="px-4 py-3 font-mono text-slate-600">
                        {po.expected_delivery_date ? (
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3.5 h-3.5 text-slate-400" />
                            {po.expected_delivery_date}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Badge color={STATUS_COLOR[po.status]}>{po.status.replace('_', ' ')}</Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center gap-2 justify-end">
                          {canWrite && ["sent", "partially_received"].includes(po.status) && (
                            <button
                              onClick={() => openReceive(po)}
                              className="text-[#16A34A] border border-[#16A34A] px-2.5 py-1 text-xs font-bold uppercase tracking-wider hover:bg-[#16A34A] hover:text-white transition-colors flex items-center gap-1"
                              data-testid={`receive-po-btn-${po.id}`}
                            >
                              <Plus className="w-3 h-3" /> Receive
                            </button>
                          )}
                          {canWrite && (
                            <button
                              onClick={() => openEdit(po)}
                              className="text-[#2563EB] border border-[#2563EB] px-2.5 py-1 text-xs font-bold uppercase tracking-wider hover:bg-[#2563EB] hover:text-white transition-colors flex items-center gap-1"
                            >
                              <Pencil className="w-3 h-3" /> Edit
                            </button>
                          )}
                          {canWrite && (
                            <button
                              onClick={() => handleDelete(po)}
                              className="text-red-600 border border-red-300 px-2.5 py-1 text-xs font-bold uppercase tracking-wider hover:bg-red-600 hover:text-white hover:border-red-600 transition-colors flex items-center gap-1"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Slide-over Drawer Form */}
      {drawer && (
        <div className="fixed inset-0 z-50 flex justify-end" data-testid="vendor-po-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={closeDrawer} />
          <div className="relative bg-white w-full max-w-2xl h-full flex flex-col shadow-2xl border-l-2 border-slate-200 overflow-y-auto">
            {/* Header */}
            <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#C27842]">Accounts Payable</div>
                <div className="text-lg font-bold">
                  {drawer.mode === "add" ? "Raise New Purchase Order" : `Edit PO: ${drawer.po?.po_number}`}
                </div>
              </div>
              <button onClick={closeDrawer} className="hover:bg-white/10 p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form Fields */}
            <div className="flex-1 p-6 space-y-4">
              {error && (
                <div className="bg-red-50 border-2 border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Vendor *</label>
                  <select
                    value={form.vendor_id}
                    onChange={(e) => setForm(f => ({ ...f, vendor_id: e.target.value }))}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] outline-none font-bold"
                  >
                    <option value="">-- Choose Vendor --</option>
                    {vendors.map(v => (
                      <option key={v.id} value={v.id}>{v.name}</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Expected Delivery</label>
                  <input
                    type="date"
                    value={form.expected_delivery_date}
                    onChange={(e) => setForm(f => ({ ...f, expected_delivery_date: e.target.value }))}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-[#C27842] outline-none"
                  />
                </div>
              </div>

              {/* Status selection (only editable for admins/managers or on edit) */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">PO Status</label>
                <select
                  value={form.status}
                  onChange={(e) => setForm(f => ({ ...f, status: e.target.value }))}
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] outline-none font-bold"
                >
                  <option value="draft">Draft</option>
                  <option value="sent">Sent</option>
                  <option value="partially_received">Partially Received</option>
                  <option value="received">Fully Received</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>

              {/* Line items editor */}
              <div className="space-y-2 pt-2">
                <div className="flex justify-between items-center border-b border-slate-200 pb-1">
                  <span className="text-[11px] uppercase tracking-wider font-black text-[#C27842]">PO Line Items</span>
                  <button
                    type="button"
                    onClick={addLine}
                    className="text-xs uppercase tracking-wider font-black text-blue-600 hover:underline flex items-center gap-1"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Line
                  </button>
                </div>

                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                  {form.line_items.map((line, idx) => (
                    <div key={idx} className="flex gap-2 items-center bg-slate-50 p-2 border border-slate-200 relative group">
                      <div className="flex-1">
                        <select
                          value={line.material_id}
                          onChange={(e) => handleLineChange(idx, "material_id", e.target.value)}
                          className="w-full border border-slate-300 bg-white px-2 py-1.5 text-xs focus:border-[#C27842] outline-none"
                        >
                          <option value="">-- Choose Material --</option>
                          {materials.map(m => (
                            <option key={m.id} value={m.id}>[{m.code}] {m.name} (₹{m.rate}/{m.unit})</option>
                          ))}
                        </select>
                        {drawer.mode === "edit" && (
                          <div className="text-[10px] text-slate-500 mt-1 pl-1">
                            Received So Far: <span className="font-mono font-bold text-green-700">{line.received_quantity || 0}</span>
                          </div>
                        )}
                      </div>

                      <div className="w-20">
                        <input
                          type="number"
                          value={line.quantity || ""}
                          placeholder="Qty"
                          onChange={(e) => handleLineChange(idx, "quantity", e.target.value)}
                          className="w-full border border-slate-300 px-2 py-1.5 text-xs font-mono text-center focus:border-[#C27842] outline-none"
                        />
                      </div>

                      <div className="w-20">
                        <input
                          type="number"
                          value={line.rate || ""}
                          placeholder="Rate"
                          onChange={(e) => handleLineChange(idx, "rate", e.target.value)}
                          className="w-full border border-slate-300 px-2 py-1.5 text-xs font-mono text-right focus:border-[#C27842] outline-none"
                        />
                      </div>

                      <div className="w-24 text-right font-mono text-xs font-bold text-slate-700 px-2">
                        {inr(line.amount)}
                      </div>

                      <button
                        type="button"
                        onClick={() => removeLine(idx)}
                        className="text-slate-400 hover:text-red-600 transition-colors p-1"
                        title="Remove line"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>

                <div className="flex justify-between items-center bg-slate-900 text-white p-3 font-mono text-sm font-bold">
                  <span className="uppercase text-[10px] tracking-wider text-[#C27842]">PO Grand Total</span>
                  <span>{inr(formGrandTotal)}</span>
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Notes / Remarks</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  placeholder="Terms, instructions or notes to vendor"
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#C27842] outline-none resize-none"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="shrink-0 border-t-2 border-slate-200 px-6 py-4 flex items-center justify-between bg-slate-50">
              <BtnSecondary onClick={closeDrawer}>Cancel</BtnSecondary>
              <BtnPrimary onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : drawer.mode === "add" ? "Raise Vendor PO" : "Save Changes"}
              </BtnPrimary>
            </div>
          </div>
        </div>
      )}

      {/* Receive Modal */}
      {receiveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" data-testid="receive-po-modal">
          <div className="absolute inset-0 bg-black/40" onClick={() => setReceiveModal(null)} />
          <div className="relative bg-white w-full max-w-lg shadow-2xl border-2 border-slate-200 rounded-lg overflow-hidden flex flex-col m-4">
            {/* Header */}
            <div className="bg-[#16A34A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-80">Inventory Inward</div>
                <div className="text-lg font-bold">Receive Materials: {receiveModal.po_number}</div>
              </div>
              <button onClick={() => setReceiveModal(null)} className="hover:bg-white/10 p-1 rounded-full">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4 flex-1 overflow-y-auto max-h-[400px]">
              {error && (
                <div className="bg-red-50 border-2 border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="text-xs text-slate-500 mb-2">
                Specify quantities received in this shipment. A stock-in record will be created.
              </div>

              <div className="space-y-3">
                {receiveForm.items.map((item, idx) => (
                  <div key={item.material_id} className="bg-slate-50 p-3 border border-slate-200 rounded flex flex-col gap-2 font-sans">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold text-sm">[{item.material_code}] {item.material_name}</div>
                        <div className="text-xs text-slate-500">
                          Ordered: <span className="font-mono">{item.ordered}</span> · Received So Far: <span className="font-mono font-bold text-green-700">{item.received}</span>
                        </div>
                      </div>
                      <div className="text-xs font-mono text-slate-500 bg-slate-200/60 px-1.5 py-0.5 rounded">
                        Remaining: {Math.max(0, item.ordered - item.received)}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 mt-1">
                      <label className="text-xs font-bold text-slate-600 shrink-0">Receive Now:</label>
                      <input
                        type="number"
                        min="0"
                        placeholder="Qty"
                        value={item.quantity || ""}
                        onChange={(e) => {
                          const val = Number(e.target.value);
                          setReceiveForm(f => {
                            const nextItems = [...f.items];
                            nextItems[idx] = { ...nextItems[idx], quantity: val };
                            return { ...f, items: nextItems };
                          });
                        }}
                        className="w-full border border-slate-300 px-3 py-1 text-sm font-mono focus:border-[#16A34A] outline-none rounded"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="shrink-0 border-t border-slate-200 px-6 py-4 flex items-center justify-between bg-slate-50 font-sans">
              <BtnSecondary onClick={() => setReceiveModal(null)}>Cancel</BtnSecondary>
              <button
                onClick={handleReceive}
                disabled={saving}
                className="bg-[#16A34A] hover:bg-[#15803d] text-white font-bold px-5 py-2 text-sm uppercase tracking-wider rounded transition-colors disabled:opacity-50"
              >
                {saving ? "Saving…" : "Post Receipt"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, accent }) {
  return (
    <Card className="p-5 relative overflow-hidden">
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500" style={{ color: accent }}>{label}</div>
      <div className="font-mono text-2xl font-bold mt-1">{value}</div>
      <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: accent }} />
    </Card>
  );
}
