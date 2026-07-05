import { useEffect, useState } from "react";
import { http } from "../lib/api";
import {
  PageHeader,
  Card,
  Badge,
  BtnPrimary,
  BtnSecondary,
} from "../components/ui-kit";
import { Truck, Plus, Pencil, PowerOff, X, AlertCircle } from "lucide-react";
import { useAuth } from "../lib/auth";

const EMPTY_FORM = {
  name: "",
  gstin: "",
  contact_person: "",
  phone: "",
  address: "",
  payment_terms_days: 30,
  active: true,
  notes: "",
};

export default function Vendors() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canWrite = ["admin", "manager"].includes(user?.role);

  const [vendors, setVendors] = useState([]);
  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [drawer, setDrawer] = useState(null);
  const [deactivateFor, setDeactivateFor] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const { data } = await http.get("/vendors", {
        params: { include_inactive: showInactive },
      });
      setVendors(data || []);
    } catch (e) {
      console.error("Failed to load vendors", e);
    }
  };

  useEffect(() => {
    load();
  }, [showInactive]); // eslint-disable-line

  const filtered = vendors.filter((v) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return `${v.name} ${v.gstin || ""} ${v.contact_person || ""}`
      .toLowerCase()
      .includes(q);
  });

  const active = vendors.filter((v) => v.active !== false);
  const shortTerms = active.filter((v) => (v.payment_terms_days || 30) <= 30);
  const avgTerms = active.length
    ? Math.round(
        active.reduce((s, v) => s + (v.payment_terms_days || 30), 0) /
          active.length,
      )
    : 0;

  const openAdd = () => {
    setForm(EMPTY_FORM);
    setError("");
    setDrawer({ mode: "add" });
  };
  const openEdit = (v) => {
    setForm({
      name: v.name || "",
      gstin: v.gstin || "",
      contact_person: v.contact_person || "",
      phone: v.phone || "",
      address: v.address || "",
      payment_terms_days: v.payment_terms_days ?? 30,
      active: v.active !== false,
      notes: v.notes || "",
    });
    setError("");
    setDrawer({ mode: "edit", vendor: v });
  };
  const closeDrawer = () => setDrawer(null);

  const handleSave = async () => {
    if (!form.name.trim()) {
      setError("Vendor name is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const body = {
        ...form,
        payment_terms_days: Number(form.payment_terms_days),
      };
      if (drawer.mode === "add") {
        await http.post("/vendors", body);
      } else {
        await http.patch(`/vendors/${drawer.vendor.id}`, body);
      }
      await load();
      closeDrawer();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivateFor) return;
    try {
      await http.delete(`/vendors/${deactivateFor.id}`);
      await load();
      setDeactivateFor(null);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };

  const field = (key) => ({
    value: form[key],
    onChange: (e) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  return (
    <div>
      <PageHeader
        title="Vendors"
        subtitle="Accounts Payable / Vendor Master"
        testId="vendors-header"
        action={
          canWrite && (
            <BtnPrimary onClick={openAdd} data-testid="add-vendor-btn" className="px-3 sm:px-5">
              <Plus className="w-3.5 h-3.5 inline" />
              <span className="hidden sm:inline ml-1">Add Vendor</span>
            </BtnPrimary>
          )
        }
      />

      <div className="p-4 sm:p-8 space-y-5">
        {/* Summary tiles */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="Total Vendors" value={vendors.length} accent="#0F172A" />
          <Tile label="Active" value={active.length} accent="#16A34A" />
          <Tile
            label="Net 30 or Less"
            value={shortTerms.length}
            accent="#C27842"
          />
          <Tile
            label="Avg. Payment Terms"
            value={active.length ? `${avgTerms}d` : "—"}
            accent="#2563EB"
          />
        </div>

        <Card className="overflow-hidden" data-testid="vendors-card">
          <div className="px-5 py-3 border-b-2 border-slate-200 flex items-center justify-between gap-4 flex-wrap">
            <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
              <Truck className="w-4 h-4 text-[#C27842]" />
              {showInactive ? "All vendors" : "Active vendors"}
              <span className="text-slate-500 font-mono ml-1">
                ({filtered.length})
              </span>
            </h2>
            <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto mt-2 sm:mt-0">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search vendor / GSTIN"
                data-testid="vendors-search"
                className="border-2 border-slate-300 px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-full sm:w-60"
              />
              <button
                onClick={() => setShowInactive((v) => !v)}
                data-testid="toggle-inactive-btn"
                className={`text-xs uppercase tracking-wider font-bold px-3 py-1.5 border-2 transition-colors w-full sm:w-auto text-center ${
                  showInactive
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-600 border-slate-300 hover:border-slate-900"
                }`}
              >
                {showInactive ? "Hide Inactive" : "Show Inactive"}
              </button>
            </div>
          </div>

          {filtered.length === 0 ? (
            <div
              className="p-16 text-center text-slate-400 text-sm"
              data-testid="vendors-empty"
            >
              <Truck className="w-10 h-10 mx-auto mb-3 opacity-20" />
              {vendors.length === 0
                ? "No vendors yet. Add your first vendor to start tracking payables."
                : "No vendors match your search."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="vendors-table">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-4 py-2 font-bold">Vendor Name</th>
                    <th className="px-4 py-2 font-bold">GSTIN</th>
                    <th className="px-4 py-2 font-bold">Contact Person</th>
                    <th className="px-4 py-2 font-bold">Phone</th>
                    <th className="px-4 py-2 font-bold text-right">
                      Payment Terms
                    </th>
                    <th className="px-4 py-2 font-bold text-center">Status</th>
                    <th className="px-4 py-2 font-bold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((v) => (
                    <tr
                      key={v.id}
                      data-testid={`vendor-row-${v.id}`}
                      className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${v.active === false ? "opacity-60" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <div className="font-bold">{v.name}</div>
                        {v.address && (
                          <div className="text-[11px] text-slate-400 mt-0.5 truncate max-w-[200px]">
                            {v.address}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-600">
                        {v.gstin || "—"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {v.contact_person || "—"}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-600">
                        {v.phone || "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span
                          className={`font-mono font-bold text-sm ${(v.payment_terms_days || 30) <= 30 ? "text-[#C27842]" : "text-slate-700"}`}
                        >
                          Net {v.payment_terms_days ?? 30}d
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {v.active !== false ? (
                          <Badge color="green">Active</Badge>
                        ) : (
                          <Badge color="red">Inactive</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 justify-end">
                          {canWrite && v.active !== false && (
                            <button
                              onClick={() => openEdit(v)}
                              data-testid={`edit-vendor-${v.id}`}
                              title="Edit vendor"
                              className="text-[#2563EB] border border-[#2563EB] px-2.5 py-1 text-xs font-bold uppercase tracking-wider hover:bg-[#2563EB] hover:text-white transition-colors flex items-center gap-1"
                            >
                              <Pencil className="w-3 h-3" /> Edit
                            </button>
                          )}
                          {isAdmin && v.active !== false && (
                            <button
                              onClick={() => setDeactivateFor(v)}
                              data-testid={`deactivate-vendor-${v.id}`}
                              title="Deactivate vendor"
                              className="text-red-600 border border-red-300 px-2.5 py-1 text-xs font-bold uppercase tracking-wider hover:bg-red-600 hover:text-white hover:border-red-600 transition-colors flex items-center gap-1"
                            >
                              <PowerOff className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-slate-900 text-white">
                  <tr>
                    <td className="px-4 py-3 font-bold uppercase text-[10px] tracking-wider text-[#C27842]">
                      Total
                    </td>
                    <td colSpan={4} className="px-4 py-3 font-mono text-sm">
                      {filtered.length} vendor{filtered.length !== 1 ? "s" : ""}
                    </td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Add / Edit Drawer */}
      {drawer && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          data-testid="vendor-drawer"
        >
          <div className="absolute inset-0 bg-black/40" onClick={closeDrawer} />
          <div className="relative bg-white w-full max-w-lg h-full flex flex-col shadow-2xl border-l-2 border-slate-200 overflow-y-auto">
            <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#C27842]">
                  Accounts Payable
                </div>
                <div className="text-lg font-bold">
                  {drawer.mode === "add"
                    ? "Add New Vendor"
                    : `Edit: ${drawer.vendor?.name}`}
                </div>
              </div>
              <button
                onClick={closeDrawer}
                className="hover:bg-white/10 p-1"
                data-testid="drawer-close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 p-6 space-y-4">
              {error && (
                <div className="bg-red-50 border-2 border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <FormField label="Vendor Name *">
                <input
                  data-testid="vendor-name-input"
                  {...field("name")}
                  placeholder="e.g. Sharma Leather Supplies"
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#C27842] outline-none"
                />
              </FormField>

              <FormField label="GSTIN">
                <input
                  data-testid="vendor-gstin-input"
                  {...field("gstin")}
                  placeholder="e.g. 27AADCB2230M1ZT"
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-[#C27842] outline-none uppercase"
                />
              </FormField>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="Contact Person">
                  <input
                    data-testid="vendor-contact-input"
                    {...field("contact_person")}
                    placeholder="e.g. Ramesh Sharma"
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#C27842] outline-none"
                  />
                </FormField>
                <FormField label="Phone">
                  <input
                    data-testid="vendor-phone-input"
                    {...field("phone")}
                    placeholder="+91 98765 43210"
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-[#C27842] outline-none"
                  />
                </FormField>
              </div>

              <FormField label="Address">
                <textarea
                  data-testid="vendor-address-input"
                  {...field("address")}
                  rows={3}
                  placeholder="Full address including city, state and PIN"
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#C27842] outline-none resize-none"
                />
              </FormField>

              <FormField label="Payment Terms (days)">
                <input
                  data-testid="vendor-terms-input"
                  type="number"
                  min={0}
                  max={365}
                  value={form.payment_terms_days}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      payment_terms_days: e.target.value,
                    }))
                  }
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-[#C27842] outline-none"
                />
                <div className="text-[11px] text-slate-400 mt-1">
                  Number of credit days e.g. 30 = Net 30.
                </div>
              </FormField>

              <FormField label="Notes">
                <textarea
                  data-testid="vendor-notes-input"
                  {...field("notes")}
                  rows={2}
                  placeholder="Any additional notes about this vendor"
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#C27842] outline-none resize-none"
                />
              </FormField>

              {drawer.mode === "edit" && (
                <div className="flex items-center gap-3">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                    Active
                  </label>
                  <button
                    type="button"
                    data-testid="vendor-active-toggle"
                    onClick={() =>
                      setForm((f) => ({ ...f, active: !f.active }))
                    }
                    className={`w-11 h-6 rounded-full transition-colors relative ${form.active ? "bg-green-500" : "bg-slate-300"}`}
                  >
                    <span
                      className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${form.active ? "translate-x-5" : "translate-x-0.5"}`}
                    />
                  </button>
                  <span className="text-xs text-slate-500">
                    {form.active ? "Active" : "Inactive"}
                  </span>
                </div>
              )}
            </div>

            <div className="shrink-0 border-t-2 border-slate-200 px-6 py-4 flex items-center justify-between bg-slate-50">
              <BtnSecondary onClick={closeDrawer} data-testid="drawer-cancel">
                Cancel
              </BtnSecondary>
              <BtnPrimary
                onClick={handleSave}
                disabled={saving}
                data-testid="drawer-save"
              >
                {saving
                  ? "Saving…"
                  : drawer.mode === "add"
                    ? "Create Vendor"
                    : "Save Changes"}
              </BtnPrimary>
            </div>
          </div>
        </div>
      )}

      {/* Deactivate confirm */}
      {deactivateFor && (
        <div
          className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4"
          data-testid="deactivate-dialog"
        >
          <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-sm p-6 space-y-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" />
              <div>
                <div className="font-bold text-slate-900">
                  Deactivate vendor?
                </div>
                <div className="text-sm text-slate-500 mt-1">
                  <b>{deactivateFor.name}</b> will be marked inactive. Existing
                  purchase history is preserved. You can reactivate by editing
                  the vendor.
                </div>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <BtnSecondary
                onClick={() => setDeactivateFor(null)}
                data-testid="deactivate-cancel"
              >
                Cancel
              </BtnSecondary>
              <button
                onClick={handleDeactivate}
                data-testid="deactivate-confirm"
                className="bg-red-600 text-white font-bold uppercase tracking-wider text-xs px-5 py-2.5 border-2 border-red-600 hover:bg-red-700 transition-colors"
              >
                Deactivate
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
    <Card className="p-3 sm:p-5 relative overflow-hidden">
      <div
        className="text-[10px] uppercase tracking-[0.2em] font-bold truncate"
        style={{ color: accent }}
      >
        {label}
      </div>
      <div
        className="font-mono text-lg sm:text-2xl font-bold mt-1 truncate"
        title={String(value)}
      >
        {value}
      </div>
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ background: accent }}
      />
    </Card>
  );
}

function FormField({ label, children }) {
  return (
    <div className="space-y-1">
      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
        {label}
      </div>
      {children}
    </div>
  );
}
