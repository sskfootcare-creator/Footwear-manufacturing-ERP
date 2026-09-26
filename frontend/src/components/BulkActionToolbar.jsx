import React, { useState } from "react";
import { CheckSquare, XSquare, Download, CheckCircle, Trash2, X, AlertCircle } from "lucide-react";

/**
 * BulkActionToolbar (U-001)
 * Provides mass approval, rejection, status updates, and export controls
 * for tables and record lists when multiple items are selected.
 */
export default function BulkActionToolbar({
  selectedIds = [],
  totalCount = 0,
  onClearSelection,
  onMassApprove,
  onMassReject,
  onBulkExport,
  onBulkDelete,
  entityName = "records",
  customActions = [],
}) {
  const [confirmModal, setConfirmModal] = useState(null);
  const count = selectedIds.length;

  if (count === 0) return null;

  const handleAction = (actionKey, label, onExecute, variant = "primary") => {
    setConfirmModal({
      actionKey,
      label,
      onExecute,
      variant,
    });
  };

  const executeConfirmed = async () => {
    if (confirmModal?.onExecute) {
      await confirmModal.onExecute(selectedIds);
    }
    setConfirmModal(null);
  };

  return (
    <>
      {/* Floating Action Bar */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-slate-900 text-white px-5 py-3 rounded-2xl shadow-2xl border border-slate-700 flex items-center gap-4 animate-in fade-in slide-in-from-bottom-4 duration-200">
        <div className="flex items-center gap-2 border-r border-slate-700 pr-4">
          <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-600 text-xs font-bold">
            {count}
          </span>
          <span className="text-sm font-medium text-slate-200">
            {entityName} selected
          </span>
        </div>

        <div className="flex items-center gap-2">
          {onMassApprove && (
            <button
              onClick={() => handleAction("approve", `Approve ${count} ${entityName}`, onMassApprove, "success")}
              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors"
            >
              <CheckCircle className="w-3.5 h-3.5" />
              Approve All
            </button>
          )}

          {onMassReject && (
            <button
              onClick={() => handleAction("reject", `Reject ${count} ${entityName}`, onMassReject, "danger")}
              className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors"
            >
              <XSquare className="w-3.5 h-3.5" />
              Reject All
            </button>
          )}

          {onBulkExport && (
            <button
              onClick={() => onBulkExport(selectedIds)}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 border border-slate-600 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Export Selected
            </button>
          )}

          {customActions.map((act, idx) => (
            <button
              key={idx}
              onClick={() => act.onClick(selectedIds)}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 border border-slate-600 transition-colors"
            >
              {act.icon}
              {act.label}
            </button>
          ))}

          {onBulkDelete && (
            <button
              onClick={() => handleAction("delete", `Delete ${count} ${entityName}`, onBulkDelete, "danger")}
              className="px-3 py-1.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-300 text-xs font-semibold flex items-center gap-1.5 border border-rose-800 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete
            </button>
          )}
        </div>

        <button
          onClick={onClearSelection}
          className="ml-2 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          title="Clear Selection"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Confirmation Modal */}
      {confirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl text-white">
            <div className="flex items-center gap-3 mb-4">
              <AlertCircle className={`w-6 h-6 ${confirmModal.variant === "danger" ? "text-rose-500" : "text-emerald-500"}`} />
              <h3 className="text-lg font-bold">Confirm Bulk Action</h3>
            </div>
            <p className="text-sm text-slate-300 mb-6">
              Are you sure you want to perform: <strong className="text-white">{confirmModal.label}</strong>? This action will apply to all {count} selected records.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmModal(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={executeConfirmed}
                className={`px-4 py-2 rounded-xl text-sm font-bold text-white transition-colors ${
                  confirmModal.variant === "danger"
                    ? "bg-rose-600 hover:bg-rose-500"
                    : "bg-emerald-600 hover:bg-emerald-500"
                }`}
              >
                Confirm & Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
