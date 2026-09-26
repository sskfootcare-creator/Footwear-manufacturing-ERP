import React, { useState, useEffect } from "react";
import { History, RotateCcw, Clock, User, X, Loader2, AlertCircle, CheckCircle } from "lucide-react";

/**
 * RevisionHistoryModal (U-008)
 * Visual revision history and undo/revert controls for critical ERP entities
 * (Invoices, Purchase Orders, Finished Goods Inventory, Production Jobs).
 */
export default function RevisionHistoryModal({
  isOpen,
  onClose,
  entityType = "invoice",
  entityId,
  entityTitle = "",
  onRevertSuccess,
}) {
  const [revisions, setRevisions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedRev, setSelectedRev] = useState(null);
  const [reverting, setReverting] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && entityId) {
      fetchRevisions();
    }
  }, [isOpen, entityType, entityId]);

  const fetchRevisions = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/revisions/${entityType}/${entityId}`);
      if (res.ok) {
        const data = await res.json();
        setRevisions(data.revisions || []);
      }
    } catch (e) {
      setError("Failed to load revision history");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const handleRevert = async (revId) => {
    if (!window.confirm("Are you sure you want to revert to this revision? A safety snapshot of current data will be created first.")) {
      return;
    }

    setReverting(true);
    setError(null);
    try {
      const res = await fetch(`/api/revisions/${entityType}/${entityId}/revert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revision_id: revId }),
      });

      if (!res.ok) {
        throw new Error("Failed to restore revision");
      }

      setMessage("Entity successfully restored to selected revision snapshot!");
      await fetchRevisions();
      if (onRevertSuccess) onRevertSuccess();
      setTimeout(() => setMessage(null), 3000);
    } catch (err) {
      setError(err.message || "Failed to revert revision");
    } finally {
      setReverting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-2xl w-full p-6 shadow-2xl text-white animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <History className="w-6 h-6 text-blue-500" />
            <div>
              <h3 className="font-bold text-lg">Revision & Audit History</h3>
              <p className="text-xs text-slate-400">
                {entityType.toUpperCase()}: {entityTitle || entityId}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-xl hover:bg-slate-800 text-slate-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="py-4 space-y-4 max-h-[65vh] overflow-y-auto pr-1">
          {message && (
            <div className="bg-emerald-950/60 border border-emerald-800 p-3 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              {message}
            </div>
          )}

          {error && (
            <div className="bg-rose-950/60 border border-rose-800 p-3 rounded-xl text-xs text-rose-300 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400" />
              {error}
            </div>
          )}

          {loading ? (
            <div className="py-12 flex justify-center items-center gap-2 text-slate-400 text-sm">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
              Loading audit snapshots...
            </div>
          ) : revisions.length === 0 ? (
            <div className="py-12 text-center text-slate-400 text-sm">
              No previous revisions recorded yet for this entity.
            </div>
          ) : (
            <div className="space-y-3">
              {revisions.map((rev, idx) => {
                const isSelected = selectedRev?.id === rev.id;
                return (
                  <div
                    key={rev.id || idx}
                    className="bg-slate-800/60 border border-slate-700/70 rounded-2xl p-4 transition-all"
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <Clock className="w-3.5 h-3.5" />
                          <span>{rev.created_at ? new Date(rev.created_at).toLocaleString() : "Unknown date"}</span>
                          <span className="text-slate-600">•</span>
                          <User className="w-3.5 h-3.5" />
                          <span>{rev.created_by || "system"}</span>
                        </div>
                        <div className="text-sm font-semibold text-white mt-1">
                          {rev.reason || `Snapshot version #${revisions.length - idx}`}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setSelectedRev(isSelected ? null : rev)}
                          className="px-2.5 py-1 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium transition-colors"
                        >
                          {isSelected ? "Hide Diff" : "Inspect"}
                        </button>

                        <button
                          onClick={() => handleRevert(rev.id)}
                          disabled={reverting}
                          className="px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold flex items-center gap-1.5 transition-colors"
                        >
                          <RotateCcw className="w-3 h-3" />
                          Revert
                        </button>
                      </div>
                    </div>

                    {/* Inspected JSON / State View */}
                    {isSelected && (
                      <div className="mt-3 pt-3 border-t border-slate-700/60">
                        <pre className="bg-slate-950 p-3 rounded-xl text-[11px] text-slate-300 font-mono overflow-x-auto max-h-48">
                          {JSON.stringify(rev.snapshot, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex justify-end pt-3 border-t border-slate-800">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-sm transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
