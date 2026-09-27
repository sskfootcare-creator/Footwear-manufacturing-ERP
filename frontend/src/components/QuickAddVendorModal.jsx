import { useState } from "react";
import { http } from "../lib/api";
import { broadcastSync } from "../lib/sync";
import { BtnPrimary, BtnSecondary, Input } from "./ui-kit";
import { X, Building2, Check, AlertCircle } from "lucide-react";

export default function QuickAddVendorModal({ open, onClose, onSuccess }) {
  const [form, setForm] = useState({
    name: "",
    contact_person: "",
    phone: "",
    gstin: "",
    payment_terms_days: 30,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setError("");
    const trimmedName = form.name.trim();
    if (!trimmedName) {
      setError("Vendor name is required.");
      return;
    }

    setSaving(true);
    try {
      const res = await http.post("/vendors", {
        name: trimmedName,
        contact_person: form.contact_person.trim(),
        phone: form.phone.trim(),
        gstin: form.gstin.trim(),
        payment_terms_days: Number(form.payment_terms_days) || 30,
        active: true,
      });
      const createdVendor = res.data;
      broadcastSync("vendors", { action: "create", data: createdVendor });
      if (onSuccess) {
        onSuccess(createdVendor);
      }
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to create vendor.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[150] flex items-center justify-center bg-black/50 p-4"
      data-testid="quick-add-vendor-modal"
    >
      <div className="bg-white border-2 border-slate-300 shadow-2xl max-w-md w-full p-5 space-y-4 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between border-b pb-3 border-slate-200">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-blue-50 text-[#2563EB] rounded">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base">Add New Vendor</h3>
              <p className="text-xs text-slate-500">Register vendor into Vendor Master</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1 rounded hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div
            className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2 rounded"
            data-testid="quick-vendor-error"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            label="Vendor / Company Name *"
            placeholder="e.g. Apex Leather Mills"
            value={form.name}
            onChange={(e) => {
              setError("");
              setForm({ ...form, name: e.target.value });
            }}
            testId="quick-vendor-name"
            autoFocus
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Contact Person"
              placeholder="e.g. Rajesh Kumar"
              value={form.contact_person}
              onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
              testId="quick-vendor-contact"
            />
            <Input
              label="Phone / Mobile"
              placeholder="e.g. 9876543210"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              testId="quick-vendor-phone"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="GSTIN (optional)"
              placeholder="e.g. 09ABCDE1234F1Z5"
              value={form.gstin}
              onChange={(e) => setForm({ ...form, gstin: e.target.value })}
              testId="quick-vendor-gstin"
            />
            <Input
              label="Payment Terms (Days)"
              type="number"
              min="0"
              value={form.payment_terms_days}
              onChange={(e) => setForm({ ...form, payment_terms_days: e.target.value })}
              testId="quick-vendor-terms"
            />
          </div>

          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary
              type="submit"
              disabled={saving}
              className="flex-1 flex items-center justify-center gap-1.5"
              testId="quick-vendor-save-btn"
            >
              <Check className="w-4 h-4" />
              {saving ? "Saving Vendor..." : "Save Vendor"}
            </BtnPrimary>
            <BtnSecondary
              type="button"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </BtnSecondary>
          </div>
        </form>
      </div>
    </div>
  );
}
