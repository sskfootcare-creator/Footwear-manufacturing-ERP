import React, { useState, useEffect } from "react";
import { AlertCircle, CheckCircle, XCircle, FileText, X, Loader2, ArrowRight } from "lucide-react";

/**
 * InvoiceVarianceModal (U-006)
 * Variance explanation workflow for invoice or cost mismatches with manager approval controls.
 */
export default function InvoiceVarianceModal({
  isOpen,
  onClose,
  invoice,
  onSuccess,
  canApprove = false,
}) {
  const [variances, setVariances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState("dispatch_shortage");
  const [amount, setAmount] = useState(0);
  const [notes, setNotes] = useState("");
  const [approvalNotes, setApprovalNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && invoice?.id) {
      fetchVariances();
    }
  }, [isOpen, invoice]);

  const fetchVariances = async () => {
    try {
      setLoading(true);
      const res = await fetch(`/api/invoices/${invoice.id || invoice._id}/variance`);
      if (res.ok) {
        const data = await res.json();
        setVariances(data.variances || []);
      }
    } catch (err) {
      console.warn("Could not fetch invoice variances:", err);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !invoice) return null;

  const handleSubmitVariance = async (e) => {
    e.preventDefault();
    if (!reason || !amount) {
      setError("Please specify reason and variance amount");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/invoices/${invoice.id || invoice._id}/variance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variance_reason: reason,
          variance_category: category,
          variance_amount: parseFloat(amount),
          notes,
        }),
      });

      if (!res.ok) {
        throw new Error("Failed to record variance");
      }

      await fetchVariances();
      setReason("");
      setAmount(0);
      setNotes("");
      if (onSuccess) onSuccess();
    } catch (err) {
      setError(err.message || "Failed to submit variance");
    } finally {
      setSubmitting(false);
    }
  };

  const handleApproval = async (approved) => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/invoices/${invoice.id || invoice._id}/variance/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved,
          approval_notes: approvalNotes,
        }),
      });

      if (!res.ok) {
        throw new Error("Failed to update approval status");
      }

      await fetchVariances();
      if (onSuccess) onSuccess();
    } catch (err) {
      setError(err.message || "Failed to update approval status");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-xl w-full p-6 shadow-2xl text-white">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <FileText className="w-6 h-6 text-amber-500" />
            <div>
              <h3 className="font-bold text-lg">Invoice Variance Explanation</h3>
              <p className="text-xs text-slate-400">Invoice #{invoice.invoice_no}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-xl hover:bg-slate-800 text-slate-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="py-4 space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          {error && (
            <div className="bg-rose-950/60 border border-rose-800 p-3 rounded-xl text-xs text-rose-300">
              {error}
            </div>
          )}

          {/* Variance History List */}
          {variances.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Logged Explanations & Status
              </h4>
              <div className="space-y-2">
                {variances.map((v, idx) => (
                  <div
                    key={idx}
                    className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-3 text-xs space-y-1"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white capitalize">
                        {v.variance_category?.replace(/_/g, " ")}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        v.status === "approved"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : v.status === "rejected"
                          ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      }`}>
                        {v.status?.toUpperCase()}
                      </span>
                    </div>
                    <p className="text-slate-300">{v.variance_reason}</p>
                    <div className="flex justify-between text-[11px] text-slate-400 pt-1">
                      <span>Amount: <strong className="text-amber-400">₹{v.variance_amount}</strong></span>
                      <span>By: {v.submitted_by}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Submit New Variance Form */}
          <form onSubmit={handleSubmitVariance} className="space-y-3 pt-2 border-t border-slate-800">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Submit New Variance Reason
            </h4>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-300">Category *</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="dispatch_shortage">Dispatch Shortage</option>
                  <option value="price_renegotiation">Price Renegotiation / Discount</option>
                  <option value="off_standard_freight">Off-Standard Freight Surcharge</option>
                  <option value="sample_allowance">Sample / Marketing Allowance</option>
                  <option value="damaged_in_transit">Damaged in Transit</option>
                  <option value="other">Other Charge Adjustment</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300">Variance Amount (₹) *</label>
                <input
                  type="number"
                  step="0.01"
                  required
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="e.g. 1500"
                  className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-300">Detailed Explanation *</label>
              <textarea
                required
                rows={2}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain the cause of variance for audit records..."
                className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl p-3 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs flex items-center gap-1.5 transition-colors"
              >
                {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                Record Variance Explanation
              </button>
            </div>
          </form>

          {/* Manager Approval Controls */}
          {canApprove && (
            <div className="pt-3 border-t border-slate-800 space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Manager Variance Review
              </h4>
              <input
                type="text"
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                placeholder="Audit notes or approval conditions..."
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => handleApproval(false)}
                  disabled={submitting}
                  className="px-3 py-1.5 rounded-xl bg-rose-600/80 hover:bg-rose-600 text-white text-xs font-bold flex items-center gap-1 transition-colors"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  Reject
                </button>
                <button
                  type="button"
                  onClick={() => handleApproval(true)}
                  disabled={submitting}
                  className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1 transition-colors"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  Approve Variance
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
