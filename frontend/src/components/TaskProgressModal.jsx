import React, { useState, useEffect } from "react";
import { Loader2, CheckCircle, AlertCircle, Clock, X } from "lucide-react";

/**
 * TaskProgressModal (U-004)
 * Displays real-time progress and remaining ETA for long-running import,
 * bulk processing, or report generation tasks.
 */
export default function TaskProgressModal({
  taskId,
  title = "Processing Batch Job",
  isOpen,
  onClose,
  onComplete,
}) {
  const [progress, setProgress] = useState({
    percent: 0,
    processed: 0,
    total: 100,
    eta_seconds: 0,
    status: "processing",
    current_item: "",
    error: null,
  });

  useEffect(() => {
    if (!isOpen || !taskId) return;

    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/tasks/${taskId}/progress`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted) {
            setProgress(data);
            if (data.status === "completed") {
              clearInterval(interval);
              if (onComplete) onComplete(data);
            } else if (data.status === "failed") {
              clearInterval(interval);
            }
          }
        }
      } catch (err) {
        console.warn("Progress poll failed:", err);
      }
    }, 1000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isOpen, taskId, onComplete]);

  if (!isOpen) return null;

  const formatEta = (seconds) => {
    if (!seconds || seconds <= 0) return "Calculating...";
    if (seconds < 60) return `~${seconds}s remaining`;
    const mins = Math.floor(seconds / 60);
    const remSecs = seconds % 60;
    return `~${mins}m ${remSecs}s remaining`;
  };

  const isDone = progress.status === "completed";
  const isFailed = progress.status === "failed";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-lg w-full p-6 shadow-2xl text-white animate-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            {isDone ? (
              <CheckCircle className="w-6 h-6 text-emerald-500" />
            ) : isFailed ? (
              <AlertCircle className="w-6 h-6 text-rose-500" />
            ) : (
              <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
            )}
            <h3 className="font-bold text-lg text-slate-100">{title}</h3>
          </div>
          {isDone || isFailed ? (
            <button
              onClick={onClose}
              className="p-1 rounded-xl hover:bg-slate-800 text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
          ) : null}
        </div>

        <div className="py-6 space-y-4">
          {/* Progress Percent & Items */}
          <div className="flex justify-between items-baseline">
            <span className="text-3xl font-extrabold text-white">
              {Math.round(progress.percent || 0)}%
            </span>
            <span className="text-sm text-slate-400 font-medium">
              {progress.processed} of {progress.total} processed
            </span>
          </div>

          {/* Progress Bar */}
          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isDone
                  ? "bg-emerald-500"
                  : isFailed
                  ? "bg-rose-500"
                  : "bg-blue-600"
              }`}
              style={{ width: `${Math.min(100, Math.max(0, progress.percent || 0))}%` }}
            />
          </div>

          {/* Current Item & ETA */}
          <div className="flex justify-between items-center text-xs text-slate-400 pt-1">
            <div className="truncate max-w-[240px]">
              {progress.current_item ? (
                <span>Working on: <strong className="text-slate-200">{progress.current_item}</strong></span>
              ) : isDone ? (
                <span className="text-emerald-400 font-medium">Task completed successfully!</span>
              ) : (
                "Processing batch payload..."
              )}
            </div>

            {!isDone && !isFailed && (
              <div className="flex items-center gap-1 text-slate-400 font-medium shrink-0">
                <Clock className="w-3.5 h-3.5 text-blue-400" />
                <span>{formatEta(progress.eta_seconds)}</span>
              </div>
            )}
          </div>

          {isFailed && progress.error && (
            <div className="bg-rose-950/50 border border-rose-800 p-3 rounded-xl text-xs text-rose-300">
              <strong>Error:</strong> {progress.error}
            </div>
          )}
        </div>

        {(isDone || isFailed) && (
          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-sm transition-colors"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
