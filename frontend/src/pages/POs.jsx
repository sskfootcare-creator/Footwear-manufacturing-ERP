import { useEffect, useState, useMemo } from "react";
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
import { Drawer } from "./Materials";
import {
  Plus,
  Upload,
  Trash2,
  Eye,
  Save,
  FileText,
  Loader2,
  Sparkles,
  FileDown,
  Truck,
  Package,
  Barcode,
} from "lucide-react";
import SearchableSelect from "../components/SearchableSelect";
import PackingListPreviewModal from "../components/PackingListPreviewModal";
import PoEanCodesModal from "../components/PoEanCodesModal";

import { API } from "../lib/api";

const emptyLine = {
  style_code: "",       // Internal SSK style code (SSK_XXXXX). MUST be filled before save.
  external_sku: "",     // Client's / marketplace's raw code from PO (preserved for sku_map)
  resolution_warning: "", // Warning message if auto-resolution failed
  description: "",
  color: "",
  size: "",
  hsn_code: "",
  quantity: 0,
  unit_price: 0,
  amount: 0,
};

const emptyPO = {
  po_number: "",
  po_date: "",
  client_name: "",
  client_address: "",
  billing_address: "",
  shipping_address: "",
  client_gstin: "",
  client_state: "",
  client_state_code: "",
  delivery_date: "",
  payment_terms: "",
  currency: "INR",
  line_items: [{ ...emptyLine }],
  cgst_rate: 0,
  sgst_rate: 0,
  igst_rate: 0,
  notes: "",
};

export default function POs() {
  const [pos, setPos] = useState([]);
  const [styles, setStyles] = useState([]);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyPO);
  const [uploading, setUploading] = useState(false);
  const [view, setView] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [formError, setFormError] = useState("");
  const [statusFilter, setStatusFilter] = useState("active"); // "active" | "completed"

  const [selectedPoForInvoices, setSelectedPoForInvoices] = useState(null);
  const [poInvoicesList, setPoInvoicesList] = useState([]);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [previewPo, setPreviewPo] = useState(null);
  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false);
  const [selectedPoForEan, setSelectedPoForEan] = useState(null);
  const [poEanModalOpen, setPoEanModalOpen] = useState(false);

  const handleInvoiceClick = async (po) => {
    setSelectedPoForInvoices(po);
    setLoadingInvoices(true);
    try {
      const res = await http.get(`/pos/${po.id}/invoices`);
      const list = res.data || [];
      setPoInvoicesList(list);
      if (list.length === 0) {
        window.open(`${API}/pos/${po.id}/invoice.pdf`, "_blank");
      } else {
        setInvoiceModalOpen(true);
      }
    } catch {
      window.open(`${API}/pos/${po.id}/invoice.pdf`, "_blank");
    } finally {
      setLoadingInvoices(false);
    }
  };

  const load = async () => {
    try {
      const [posRes, stylesRes] = await Promise.all([
        http.get("/pos"),
        http.get("/styles"),
      ]);
      setPos(posRes.data);
      setStyles(stylesRes.data);
    } catch (e) {
      alert("Failed to load PO data: " + e.message);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const activePos = useMemo(() => {
    return pos.filter((p) => !p.is_completed && p.status !== "completed");
  }, [pos]);

  const completedPos = useMemo(() => {
    return pos.filter((p) => p.is_completed || p.status === "completed");
  }, [pos]);

  const displayedPos = useMemo(() => {
    if (statusFilter === "completed") return completedPos;
    return activePos;
  }, [statusFilter, activePos, completedPos]);

  const validStyleCodes = useMemo(() => {
    return new Set(styles.map((s) => s.code.trim().toUpperCase()));
  }, [styles]);

  const openView = async (p) => {
    try {
      const res = await http.get(`/pos/${p.id}`);
      setView(res.data);
    } catch {
      setView(p);
    }
  };

  const startNew = () => {
    setEditId(null);
    setForm(emptyPO);
    setFormError("");
    setOpen(true);
  };
  const onExtractFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await http.post("/pos/extract", fd);
      const clientName = data.client_name || data.vendor_name || "";
      const validCodes = new Set(styles.map((s) => s.code.trim().toUpperCase()));

      // Pre-resolve each external code via sku_map so already-mapped items land pre-picked
      const rawLines =
        data.line_items && data.line_items.length
          ? data.line_items
          : [{ ...emptyLine }];
      const resolved = await Promise.all(
        rawLines.map(async (li) => {
          const ext = String(li.style_code || li.item_code || "").trim();
          let mappedStyle = "";
          let resolutionWarning = "";
          // If the external code is itself already an SSK code, use it directly.
          if (ext && validCodes.has(ext.toUpperCase())) {
            mappedStyle = ext;
          } else if (ext && clientName) {
            try {
              const r = await http.get(
                `/sku-map/resolve?source_type=b2b_client&source_name=${encodeURIComponent(
                  clientName,
                )}&external_sku=${encodeURIComponent(ext)}`,
              );
              if (r.data?.matched && r.data.style_code) {
                mappedStyle = r.data.style_code;
              }
            } catch {
              resolutionWarning = "Could not auto-resolve SKU mapping — check manually";
            }
          }
          return {
            style_code: mappedStyle,
            external_sku: ext,
            resolution_warning: resolutionWarning,
            description: li.description || "",
            color: li.color || "",
            size: String(li.size || ""),
            hsn_code: li.hsn_code || "",
            quantity: Number(li.quantity || 0),
            unit_price: Number(li.unit_price || 0),
            amount: Number(
              li.amount ||
              Number(li.quantity || 0) * Number(li.unit_price || 0),
            ),
          };
        }),

      );

      setForm({
        po_number: data.po_number || "",
        po_date: data.po_date || "",
        client_name: clientName,
        client_address: data.client_address || "",
        billing_address: data.billing_address || "",
        shipping_address: data.shipping_address || "",
        client_gstin: data.client_gstin || "",
        client_state: data.client_state || "",
        client_state_code: data.client_state_code || "",
        delivery_date: data.delivery_date || "",
        payment_terms: data.payment_terms || "",
        currency: data.currency || "INR",
        line_items: resolved,
        cgst_rate: Number(data.cgst_rate || 0),
        sgst_rate: Number(data.sgst_rate || 0),
        igst_rate: Number(data.igst_rate || 0),
        notes: data.notes || "",
      });
      setEditId(null);
      setOpen(true);
    } catch (err) {
      alert(
        "Extraction failed: " + (err.response?.data?.detail || err.message),
      );
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const updateLine = (i, key, val) =>
    setForm((f) => {
      const li = f.line_items.map((r, idx) =>
        idx === i ? { ...r, [key]: val } : r,
      );
      if (key === "quantity" || key === "unit_price") {
        const row = li[i];
        row.amount = Number(row.quantity || 0) * Number(row.unit_price || 0);
      }
      return { ...f, line_items: li };
    });
  const addLine = () =>
    setForm((f) => ({ ...f, line_items: [...f.line_items, { ...emptyLine }] }));
  const removeLine = (i) =>
    setForm((f) => ({
      ...f,
      line_items: f.line_items.filter((_, idx) => idx !== i),
    }));

  const totals = useMemo(() => {
    const subtotal = form.line_items.reduce(
      (s, li) => s + Number(li.amount || 0),
      0,
    );
    const cgst_amount = (subtotal * Number(form.cgst_rate || 0)) / 100;
    const sgst_amount = (subtotal * Number(form.sgst_rate || 0)) / 100;
    const igst_amount = (subtotal * Number(form.igst_rate || 0)) / 100;
    const grand_total = subtotal + cgst_amount + sgst_amount + igst_amount;
    const total_quantity = form.line_items.reduce(
      (s, li) => s + Number(li.quantity || 0),
      0,
    );
    return {
      subtotal,
      cgst_amount,
      sgst_amount,
      igst_amount,
      grand_total,
      total_quantity,
    };
  }, [form]);

  const save = async () => {
    setFormError("");

    // Guard: every line must have an internal SSK style picked.
    const unresolved = form.line_items
      .map((li, i) => ({ li, i }))
      .filter(
        ({ li }) =>
          !li.style_code ||
          !validStyleCodes.has(li.style_code.trim().toUpperCase()),
      );
    if (unresolved.length > 0) {
      setFormError(
        `${unresolved.length} line item(s) still need an SSK style mapped. Pick one from the "SSK Style" dropdown for each red row before saving.`,
      );
      return;
    }

    try {
      const body = {
        ...form,
        line_items: form.line_items.map((li) => ({
          ...li,
          quantity: Number(li.quantity),
          unit_price: Number(li.unit_price),
          amount: Number(li.amount),
        })),

        cgst_rate: Number(form.cgst_rate),
        sgst_rate: Number(form.sgst_rate),
        igst_rate: Number(form.igst_rate),
        cgst_amount: totals.cgst_amount,
        sgst_amount: totals.sgst_amount,
        igst_amount: totals.igst_amount,
        subtotal: totals.subtotal,
        grand_total: totals.grand_total,
        total_quantity: totals.total_quantity,
      };
      if (editId) await http.patch(`/pos/${editId}`, body);
      else await http.post("/pos", body);
      setOpen(false);
      load();
    } catch (err) {
      setFormError(err.response?.data?.detail || err.message);
    }
  };

  const remove = (id) => {
    setConfirm({
      title: "Delete Purchase Order",
      message:
        "Are you sure you want to delete this Purchase Order? All associated production jobs will also be deleted from the system.",
      onConfirm: async () => {
        await http.delete(`/pos/${id}`);
        setConfirm(null);
        load();
      },
    });
  };

  const downloadPacking = (po) => {
    setPreviewPo(po);
  };

  return (
    <div>
      <PageHeader
        title="Purchase Orders"
        subtitle="Orders / Purchase Orders"
        testId="pos-header"
        action={
          <div className="flex gap-2 items-center">
            <label
              className="bg-[#C27842] text-white font-bold uppercase tracking-wider text-xs px-3 sm:px-5 py-2.5 border-2 border-[#C27842] shadow-ind hover:bg-[#A65D24] cursor-pointer flex items-center gap-2"
              data-testid="upload-po-label"
            >
              {uploading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">
                {uploading ? "Extracting..." : "Upload PO (AI)"}
              </span>
              {uploading && <span className="inline sm:hidden">...</span>}
              <input
                type="file"
                accept=".pdf,.xlsx,.xls"
                className="hidden"
                onChange={onExtractFile}
                disabled={uploading}
                data-testid="upload-po-input"
              />
            </label>
            <BtnPrimary
              onClick={startNew}
              data-testid="new-po-btn"
              className="px-3 sm:px-5"
            >
              <Plus className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">New PO</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        <div
          className="bg-[#1E3A8A] text-white p-4 flex items-center gap-3 border-2 border-[#1E3A8A]"
          data-testid="po-ai-banner"
        >
          <Sparkles className="w-5 h-5 text-[#C27842]" />
          <div>
            <div className="font-bold text-sm uppercase tracking-wider">
              AI-Powered PO Intake
            </div>
            <div className="text-xs text-slate-300 mt-0.5">
              Upload any PDF or Excel purchase order — we'll auto-extract line
              items, sizes, tax breakdown and create production jobs
              automatically.
            </div>
          </div>
        </div>

        {/* Tabs Bar: Active vs Completed */}
        <div className="flex items-center justify-between border-b border-slate-200">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setStatusFilter("active")}
              data-testid="tab-active-pos"
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                statusFilter === "active"
                  ? "border-[#1E3A8A] text-[#1E3A8A]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Active
              <span
                className={`px-2 py-0.5 text-[10px] rounded-full font-mono font-bold ${
                  statusFilter === "active"
                    ? "bg-[#1E3A8A] text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {activePos.length}
              </span>
            </button>
            <button
              onClick={() => setStatusFilter("completed")}
              data-testid="tab-completed-pos"
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                statusFilter === "completed"
                  ? "border-[#16A34A] text-[#16A34A]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Completed
              <span
                className={`px-2 py-0.5 text-[10px] rounded-full font-mono font-bold ${
                  statusFilter === "completed"
                    ? "bg-[#16A34A] text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {completedPos.length}
              </span>
            </button>
          </div>
        </div>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="pos-table">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-3 font-bold sticky left-0 z-10 bg-slate-50">PO #</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3 font-bold">Date</th>
                  <th className="px-4 py-3 font-bold">Client</th>
                  <th className="px-4 py-3 font-bold text-right">Lines</th>
                  <th className="px-4 py-3 font-bold text-right">Qty</th>
                  <th className="px-4 py-3 font-bold text-right">
                    Grand Total
                  </th>
                  <th className="px-4 py-3 font-bold">Delivery</th>
                  <th className="px-4 py-3 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {displayedPos.length === 0 ? (
                  <tr>
                    <td
                      colSpan="9"
                      className="px-6 py-10 text-center text-slate-400"
                    >
                      {statusFilter === "completed"
                        ? "No completed POs yet. POs with all jobs dispatched and invoiced will appear here."
                        : "No active POs. Click \"New PO\" or \"Upload PO (AI)\" to import one."}
                    </td>
                  </tr>
                ) : (
                  displayedPos.map((p) => (
                    <tr
                      key={p.id}
                      className="border-b border-slate-100 hover:bg-slate-50"
                    >
                      <td className="px-4 py-3 font-mono font-bold sticky left-0 z-10 bg-white">
                        {p.po_number}
                      </td>
                      <td className="px-4 py-3">
                        {p.is_completed || p.status === "completed" ? (
                          <Badge tone="success" className="text-[10px] uppercase font-bold tracking-wider">
                            Completed
                          </Badge>
                        ) : (
                          <Badge tone="amber" className="text-[10px] uppercase font-bold tracking-wider">
                            Active
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs">{p.po_date}</td>
                      <td className="px-4 py-3">{p.client_name}</td>
                      <td className="px-4 py-3 text-right font-mono">
                        {p.line_items?.length || 0}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {p.total_quantity}
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-bold">
                        {inr(p.grand_total)}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {p.delivery_date || "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleInvoiceClick(p)}
                          className="text-slate-600 hover:text-[#C27842] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation"
                          title="View/Download Tax Invoice"
                          data-testid={`invoice-${p.po_number}`}
                          disabled={loadingInvoices && selectedPoForInvoices?.id === p.id}
                        >
                          {loadingInvoices && selectedPoForInvoices?.id === p.id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-[#C27842]" />
                          ) : (
                            <FileDown className="w-4 h-4" />
                          )}
                        </button>
                        <a
                          href={`${API}/pos/${p.id}/challan.pdf`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-slate-600 hover:text-[#F97316] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          title="Dispatch Challan"
                          data-testid={`challan-${p.po_number}`}
                        >
                          <Truck className="w-4 h-4" />
                        </a>
                        <button
                          onClick={() => downloadPacking(p)}
                          className="text-slate-600 hover:text-[#16A34A] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          title="Generate Packing List"
                          data-testid={`packing-${p.po_number}`}
                        >
                          <Package className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => {
                            setSelectedPoForEan(p);
                            setPoEanModalOpen(true);
                          }}
                          className="text-slate-600 hover:text-[#0D9488] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          title="Client Barcodes / EAN Import"
                          data-testid={`ean-${p.po_number}`}
                        >
                          <Barcode className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openView(p)}
                          className="text-slate-600 hover:text-[#2563EB] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          data-testid={`view-po-${p.po_number}`}
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => remove(p.id)}
                          className="text-slate-600 hover:text-red-600 p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
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
          onClose={() => {
            setOpen(false);
            setFormError("");
          }}
          title={editId ? "Edit Purchase Order" : "New Purchase Order"}
          width="max-w-5xl"
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="col-span-2 sm:col-span-1">
                <Input
                  label="PO Number"
                  value={form.po_number}
                  onChange={(e) => {
                    setFormError("");
                    setForm({ ...form, po_number: e.target.value });
                  }}
                  testId="form-po-number"
                />
                {formError && (
                  <p
                    className="mt-1 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2"
                    data-testid="form-po-error"
                  >
                    {formError}
                  </p>
                )}
              </div>
              <Input
                label="PO Date"
                type="date"
                value={form.po_date}
                onChange={(e) => setForm({ ...form, po_date: e.target.value })}
              />
              <Input
                label="Delivery Date"
                type="date"
                value={form.delivery_date}
                onChange={(e) =>
                  setForm({ ...form, delivery_date: e.target.value })
                }
              />
            </div>
            <Input
              label="Client Name"
              value={form.client_name}
              onChange={(e) =>
                setForm({ ...form, client_name: e.target.value })
              }
              testId="form-po-client"
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Billing Address"
                value={form.billing_address}
                onChange={(e) =>
                  setForm({ ...form, billing_address: e.target.value })
                }
              />
              <Input
                label="Shipping Address"
                value={form.shipping_address}
                onChange={(e) =>
                  setForm({ ...form, shipping_address: e.target.value })
                }
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Input
                label="Client GSTIN"
                value={form.client_gstin}
                onChange={(e) => {
                  const gstin = e.target.value.toUpperCase();
                  let sc = form.client_state_code;
                  if (
                    gstin.length >= 2 &&
                    /^\d{2}$/.test(gstin.substring(0, 2))
                  ) {
                    sc = gstin.substring(0, 2);
                  }
                  setForm({
                    ...form,
                    client_gstin: gstin,
                    client_state_code: sc,
                  });
                }}
                testId="form-po-client-gstin"
              />
              <Input
                label="Client State"
                value={form.client_state}
                onChange={(e) =>
                  setForm({ ...form, client_state: e.target.value })
                }
              />
              <Input
                label="Client State Code"
                value={form.client_state_code}
                onChange={(e) =>
                  setForm({ ...form, client_state_code: e.target.value })
                }
              />
            </div>
            <Input
              label="Payment Terms"
              value={form.payment_terms}
              onChange={(e) =>
                setForm({ ...form, payment_terms: e.target.value })
              }
            />

            <div className="flex items-baseline justify-between pt-3">
              <h3 className="text-sm font-bold uppercase tracking-wider">
                Line Items
              </h3>
              <button
                type="button"
                onClick={addLine}
                className="text-xs font-bold uppercase tracking-wider text-[#2563EB] py-2 px-3 min-h-[44px] touch-manipulation"
                data-testid="add-line-btn"
              >
                + Add line
              </button>
            </div>
            <div className="bg-blue-50 border-2 border-blue-200 px-3 py-2 text-[11px] text-blue-900">
              <strong>SKU mapping is compulsory.</strong> Each PO line must be tied to an internal SSK style. If the client&apos;s external code hasn&apos;t been mapped yet, pick the matching style from the dropdown — we&apos;ll remember it for future POs from this client.
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-2 border-slate-200">
                <thead className="bg-slate-50">
                  <tr className="text-left">
                    <th className="px-2 py-2 font-bold sticky left-0 z-10 bg-slate-50">External SKU</th>
                    <th className="px-2 py-2 font-bold">SSK Style *</th>
                    <th className="px-2 py-2 font-bold">Description</th>
                    <th className="px-2 py-2 font-bold">Color</th>
                    <th className="px-2 py-2 font-bold">Size</th>
                    <th className="px-2 py-2 font-bold">HSN</th>
                    <th className="px-2 py-2 font-bold text-right">Qty</th>
                    <th className="px-2 py-2 font-bold text-right">Rate</th>
                    <th className="px-2 py-2 font-bold text-right">Amount</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {form.line_items.map((li, i) => {
                    const isStyleValid =
                      li.style_code &&
                      validStyleCodes.has(li.style_code.trim().toUpperCase());
                    const isNewMapping =
                      isStyleValid &&
                      li.external_sku &&
                      li.external_sku.trim().toUpperCase() !==
                      li.style_code.trim().toUpperCase();
                    return (
                      <tr
                        key={i}
                        className={`border-t border-slate-200 ${!isStyleValid ? "bg-red-50/40" : ""
                          }`}
                        data-testid={`po-line-${i}`}
                      >
                        <td className="px-1 py-1 sticky left-0 z-10 bg-white">
                          <input
                            value={li.external_sku || ""}
                            onChange={(e) =>
                              updateLine(i, "external_sku", e.target.value)
                            }
                            className="w-32 border border-slate-300 px-1 py-0.5 font-mono bg-slate-50"
                            placeholder="Client code"
                            title="External SKU from the client's PO / marketplace"
                            data-testid={`po-line-${i}-ext-sku`}
                          />
                        </td>
                        <td className="px-1 py-1 min-w-[160px] relative">
                          <SearchableSelect
                            options={styles}
                            value={li.style_code || ""}
                            onChange={(code) => updateLine(i, "style_code", code)}
                            getKey={(s) => s.code}
                            getLabel={(s) => `${s.code} · ${s.name}`}
                            placeholder="— pick SSK style —"
                            testId={`po-line-${i}-style-select`}
                          />
                          {!isStyleValid && (
                            <div
                              className="text-[9px] text-red-600 font-bold mt-0.5"
                              data-testid={`po-line-${i}-resolution-warning`}
                            >
                              {li.resolution_warning || "Mapping required"}
                            </div>
                          )}

                          {isNewMapping && (
                            <div
                              className="text-[9px] text-blue-700 font-bold mt-0.5"
                              title={`On save we'll remember: ${li.external_sku} → ${li.style_code} for ${form.client_name || "this client"}`}
                            >
                              New mapping will be saved
                            </div>
                          )}
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.description}
                            onChange={(e) =>
                              updateLine(i, "description", e.target.value)
                            }
                            className="w-44 border border-slate-300 px-1 py-0.5"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.color}
                            onChange={(e) =>
                              updateLine(i, "color", e.target.value)
                            }
                            className="w-20 border border-slate-300 px-1 py-0.5"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.size}
                            onChange={(e) =>
                              updateLine(i, "size", e.target.value)
                            }
                            className="w-12 border border-slate-300 px-1 py-0.5 text-center font-mono"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.hsn_code}
                            onChange={(e) =>
                              updateLine(i, "hsn_code", e.target.value)
                            }
                            className="w-20 border border-slate-300 px-1 py-0.5 font-mono"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            type="number"
                            value={li.quantity}
                            onChange={(e) =>
                              updateLine(i, "quantity", e.target.value)
                            }
                            inputMode="numeric"
                            className="w-16 border border-slate-300 px-1 py-2 text-right font-mono text-xs min-h-[44px]"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            type="number"
                            step="0.01"
                            value={li.unit_price}
                            onChange={(e) =>
                              updateLine(i, "unit_price", e.target.value)
                            }
                            inputMode="decimal"
                            className="w-20 border border-slate-300 px-1 py-2 text-right font-mono text-xs min-h-[44px]"
                          />
                        </td>
                        <td className="px-2 py-1 text-right font-mono font-bold">
                          {inr(li.amount)}
                        </td>
                        <td className="px-1 py-1">
                          <button
                            onClick={() => removeLine(i)}
                            className="text-slate-500 hover:text-red-600"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-6 pt-3">
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Input
                    label="CGST %"
                    type="number"
                    step="0.01"
                    value={form.cgst_rate}
                    onChange={(e) =>
                      setForm({ ...form, cgst_rate: e.target.value })
                    }
                  />
                  <Input
                    label="SGST %"
                    type="number"
                    step="0.01"
                    value={form.sgst_rate}
                    onChange={(e) =>
                      setForm({ ...form, sgst_rate: e.target.value })
                    }
                  />
                  <Input
                    label="IGST %"
                    type="number"
                    step="0.01"
                    value={form.igst_rate}
                    onChange={(e) =>
                      setForm({ ...form, igst_rate: e.target.value })
                    }
                  />
                </div>
                <Input
                  label="Notes"
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </div>
              <div className="bg-[#0F172A] text-white p-5 border-2 border-[#0F172A]">
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold mb-3">
                  Summary
                </div>
                <Total label="Subtotal" value={inr(totals.subtotal)} />
                <Total label="CGST" value={inr(totals.cgst_amount)} />
                <Total label="SGST" value={inr(totals.sgst_amount)} />
                <Total label="IGST" value={inr(totals.igst_amount)} />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <Total label="Total Qty" value={totals.total_quantity} />
                <Total
                  label="Grand Total"
                  value={inr(totals.grand_total)}
                  big
                />
              </div>
            </div>

            <div className="flex gap-2 pt-3 border-t border-slate-200">
              <BtnPrimary onClick={save} data-testid="save-po-btn">
                <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
                Purchase Order
              </BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}

      {view && (
        <Drawer
          onClose={() => setView(null)}
          title={`PO ${view.po_number}`}
          width="max-w-4xl"
        >
          <div className="space-y-4 text-sm">
            {/* PO-level Document & Barcode Actions Toolbar */}
            <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-wrap items-center justify-between gap-2.5">
              <div className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                PO Documents &amp; Operations
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => handleInvoiceClick(view)}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded shadow-sm inline-flex items-center gap-1.5 min-h-[34px]"
                  data-testid="detail-invoice-btn"
                >
                  <FileDown className="w-3.5 h-3.5 text-[#C27842]" />
                  <span>Tax Invoice</span>
                </button>
                <a
                  href={`${API}/pos/${view.id}/challan.pdf`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded shadow-sm inline-flex items-center gap-1.5 min-h-[34px]"
                  data-testid="detail-challan-btn"
                >
                  <Truck className="w-3.5 h-3.5 text-[#F97316]" />
                  <span>Dispatch Challan</span>
                </a>
                <button
                  onClick={() => downloadPacking(view)}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded shadow-sm inline-flex items-center gap-1.5 min-h-[34px]"
                  data-testid="detail-packing-btn"
                >
                  <Package className="w-3.5 h-3.5 text-[#16A34A]" />
                  <span>Packing List</span>
                </button>
                <button
                  onClick={() => {
                    setSelectedPoForEan(view);
                    setPoEanModalOpen(true);
                  }}
                  className="px-3 py-1.5 text-xs font-bold text-teal-800 bg-teal-50 hover:bg-teal-100 border border-teal-300 rounded shadow-sm inline-flex items-center gap-1.5 min-h-[34px] transition-colors"
                  data-testid="detail-upload-barcode-btn"
                  title="Upload and manage client barcode EAN mappings for this PO"
                >
                  <Barcode className="w-3.5 h-3.5 text-teal-600" />
                  <span>Upload Barcode File</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Client" value={view.client_name} />
              <Field label="Client GSTIN" value={view.client_gstin || "—"} />
              <Field
                label="Client State"
                value={
                  view.client_state
                    ? `${view.client_state} (Code: ${view.client_state_code})`
                    : "—"
                }
              />
              <Field label="PO Date" value={view.po_date} />
              <Field label="Delivery" value={view.delivery_date} />
              <Field label="Payment Terms" value={view.payment_terms} />
              <div>
                <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500 mb-1">
                  Status
                </div>
                <div>
                  {view.is_completed || view.status === "completed" ? (
                    <Badge tone="success" className="text-[10px] uppercase font-bold tracking-wider">
                      Completed
                    </Badge>
                  ) : (
                    <Badge tone="amber" className="text-[10px] uppercase font-bold tracking-wider">
                      Active
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <div>
              <Field label="Billing" value={view.billing_address} />
              <Field label="Shipping" value={view.shipping_address} />
            </div>

            <div className="pt-2">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Line Items &amp; PO Profitability
                </h3>
                <span className="text-[11px] text-slate-500 italic">
                  Profit = PO Rate − (BOM + Labor + Packing)
                </span>
              </div>
              <div className="overflow-x-auto border-2 border-slate-200">
                <table className="w-full text-xs">
                  <thead className="bg-slate-100 border-b border-slate-200">
                    <tr className="text-left font-bold text-slate-700 text-[11px]">
                      <th className="px-2.5 py-2">Style / Desc</th>
                      <th className="px-2 py-2 text-right">Qty</th>
                      <th className="px-2 py-2 text-right">PO Rate</th>
                      <th className="px-2.5 py-2">Cost Breakdown / Pair</th>
                      <th className="px-2.5 py-2 text-right">Profit / Pair</th>
                      <th className="px-2.5 py-2 text-right">Line Profit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {view.line_items.map((li, i) => {
                      const prof = li.profitability;
                      const lineProfit =
                        prof && prof.profit != null
                          ? prof.profit * Number(li.quantity || 0)
                          : null;
                      return (
                        <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                          <td className="px-2.5 py-2">
                            <div className="font-mono font-bold text-slate-900">
                              {li.style_code}
                            </div>
                            <div className="text-[11px] text-slate-500">
                              {li.description ||
                                `${li.color || ""} ${li.size ? "Sz " + li.size : ""}`}
                            </div>
                          </td>
                          <td className="px-2 py-2 text-right font-mono font-semibold">
                            {li.quantity}
                          </td>
                          <td className="px-2 py-2 text-right font-mono font-bold text-slate-800">
                            {inr(li.unit_price)}
                          </td>
                          <td className="px-2.5 py-2 text-[11px]">
                            {prof ? (
                              <div className="space-y-0.5">
                                <div className="flex gap-2 text-slate-600">
                                  <span>BOM: <strong className="font-mono">{inr(prof.bom_cost)}</strong></span>
                                  <span>Pack: <strong className="font-mono">{inr(prof.packing_cost)}</strong></span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <span>Labor: <strong className="font-mono">{inr(prof.labor_cost)}</strong></span>
                                  {prof.is_estimated ? (
                                    <span
                                      className="px-1.5 py-0.2 bg-amber-100 text-amber-900 border border-amber-300 text-[9px] font-bold uppercase rounded"
                                      title="No production job data yet; using planned style labor cost."
                                    >
                                      Estimated Labor
                                    </span>
                                  ) : (
                                    <span
                                      className="px-1.5 py-0.2 bg-emerald-100 text-emerald-900 border border-emerald-300 text-[9px] font-bold uppercase rounded"
                                      title="Computed from real production job assignments for this style."
                                    >
                                      Actual Labor
                                    </span>
                                  )}
                                </div>
                              </div>
                            ) : (
                              <span className="text-slate-400 italic">—</span>
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right font-mono">
                            {prof && prof.profit != null ? (
                              <div>
                                <div
                                  className={`font-bold ${prof.profit >= 0 ? "text-emerald-700" : "text-red-600"
                                    }`}
                                >
                                  {prof.profit >= 0 ? "+" : ""}
                                  {inr(prof.profit)}
                                </div>
                                {prof.profit_pct != null && (
                                  <div
                                    className={`text-[10px] font-semibold ${prof.profit >= 0 ? "text-emerald-600" : "text-red-500"
                                      }`}
                                  >
                                    ({prof.profit_pct}%)
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span className="text-slate-400 italic">—</span>
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right font-mono font-bold">
                            {lineProfit != null ? (
                              <span
                                className={
                                  lineProfit >= 0 ? "text-emerald-700" : "text-red-600"
                                }
                              >
                                {lineProfit >= 0 ? "+" : ""}
                                {inr(lineProfit)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bg-slate-50 p-4 grid grid-cols-2 gap-2 text-xs">
              <div>
                Subtotal:{" "}
                <span className="font-mono font-bold ml-2">
                  {inr(view.subtotal)}
                </span>
              </div>
              <div>
                CGST:{" "}
                <span className="font-mono ml-2">{inr(view.cgst_amount)}</span>
              </div>
              <div>
                SGST:{" "}
                <span className="font-mono ml-2">{inr(view.sgst_amount)}</span>
              </div>
              <div>
                IGST:{" "}
                <span className="font-mono ml-2">{inr(view.igst_amount)}</span>
              </div>
              <div className="col-span-2 text-lg font-black border-t pt-2 flex justify-between items-baseline">
                <span>
                  Grand Total:{" "}
                  <span className="font-mono text-[#C27842] ml-2">
                    {inr(view.grand_total)}
                  </span>
                </span>
              </div>
            </div>
          </div>
        </Drawer>
      )}
      {invoiceModalOpen && (
        <Drawer
          title={`Invoices for PO: ${selectedPoForInvoices?.po_number || ""}`}
          open={invoiceModalOpen}
          onClose={() => setInvoiceModalOpen(false)}
        >
          <div className="space-y-4 p-2">
            <div className="text-xs text-slate-500 pb-2 border-b border-slate-100">
              Client: <span className="font-semibold text-slate-800">{selectedPoForInvoices?.client_name}</span> | PO Total: <span className="font-semibold text-slate-800">{inr(selectedPoForInvoices?.grand_total)}</span>
            </div>

            {poInvoicesList.length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-sm">
                No existing invoices found for this PO.
              </div>
            ) : (
              <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
                {poInvoicesList.map((inv) => (
                  <div key={inv.id} className="p-3.5 bg-white hover:bg-slate-50 flex items-center justify-between gap-4">
                    <div>
                      <div className="font-mono font-bold text-slate-900 text-sm flex items-center gap-2">
                        <span>{inv.invoice_no}</span>
                        {inv.status && <Badge>{inv.status.toUpperCase()}</Badge>}
                      </div>
                      <div className="text-xs text-slate-500 mt-1">
                        Date: {inv.invoice_date} | Amount: <span className="font-mono font-semibold text-slate-700">{inr(inv.grand_total)}</span>
                      </div>
                      {inv.job_ids && inv.job_ids.length > 0 && (
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          Jobs Covered: {inv.job_ids.length} job(s)
                        </div>
                      )}
                    </div>
                    <a
                      href={`${API}/invoices/${inv.id}/file`}
                      target="_blank"
                      rel="noreferrer"
                      className="px-3.5 py-2 text-xs font-medium text-white bg-[#C27842] hover:bg-[#a86535] rounded-md inline-flex items-center gap-1.5 min-h-[38px] shadow-sm"
                    >
                      <FileDown className="w-4 h-4" /> Download PDF
                    </a>
                  </div>
                ))}
              </div>
            )}

            <div className="pt-4 border-t border-slate-200 flex justify-between items-center">
              <span className="text-xs text-slate-400">
                {poInvoicesList.length} invoice(s) found
              </span>
              <BtnSecondary onClick={() => setInvoiceModalOpen(false)}>
                Close
              </BtnSecondary>
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
      <PackingListPreviewModal
        po={previewPo}
        isOpen={!!previewPo}
        onClose={() => setPreviewPo(null)}
      />
      <PoEanCodesModal
        po={selectedPoForEan}
        isOpen={poEanModalOpen}
        onClose={() => setPoEanModalOpen(false)}
        onUpdated={load}
      />
    </div>
  );
}

function Total({ label, value, big }) {
  return (
    <div
      className={`flex justify-between items-baseline ${big ? "py-1" : "py-0.5"}`}
    >
      <span className="text-xs uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <span
        className={`font-mono ${big ? "text-xl font-bold text-[#C27842]" : "text-sm"}`}
      >
        {value}
      </span>
    </div>
  );
}
function Field({ label, value }) {
  return (
    <div className="border-b border-dashed border-slate-200 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
        {label}
      </div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
}
