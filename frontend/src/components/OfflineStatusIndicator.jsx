import React, { useState, useEffect } from "react";
import { Wifi, WifiOff, RefreshCw, CheckCircle2 } from "lucide-react";
import { getOfflineQueue, flushOfflineQueue } from "../services/offlineSync";

/**
 * OfflineStatusIndicator (U-010)
 * Persistent subtle status indicator showing network state and pending offline synced actions.
 */
export default function OfflineStatusIndicator() {
  const [isOnline, setIsOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);
  const [pendingCount, setPendingCount] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [justSynced, setJustSynced] = useState(false);

  useEffect(() => {
    updateCount();

    const handleOnline = () => {
      setIsOnline(true);
      handleManualSync();
    };
    const handleOffline = () => setIsOnline(false);
    const handleQueueUpdate = () => updateCount();

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("ssk_offline_queue_updated", handleQueueUpdate);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("ssk_offline_queue_updated", handleQueueUpdate);
    };
  }, []);

  const updateCount = () => {
    setPendingCount(getOfflineQueue().length);
  };

  const handleManualSync = async () => {
    setSyncing(true);
    const res = await flushOfflineQueue();
    setSyncing(false);
    updateCount();
    if (res.synced > 0) {
      setJustSynced(true);
      setTimeout(() => setJustSynced(false), 2500);
    }
  };

  if (isOnline && pendingCount === 0 && !justSynced) {
    return null; // Keep screen clean when normally online with no pending queue
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 animate-in fade-in slide-in-from-bottom-2">
      <div className={`px-3 py-2 rounded-2xl shadow-xl border flex items-center gap-2.5 text-xs font-semibold backdrop-blur-md ${
        !isOnline
          ? "bg-amber-950/90 border-amber-800 text-amber-200"
          : justSynced
          ? "bg-emerald-950/90 border-emerald-800 text-emerald-200"
          : "bg-slate-900/90 border-slate-700 text-slate-200"
      }`}>
        {!isOnline ? (
          <>
            <WifiOff className="w-4 h-4 text-amber-400 animate-pulse" />
            <span>Offline Mode ({pendingCount} pending)</span>
          </>
        ) : justSynced ? (
          <>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Synced with cloud!</span>
          </>
        ) : (
          <>
            <Wifi className="w-4 h-4 text-emerald-400" />
            <span>{pendingCount} offline actions pending</span>
            <button
              onClick={handleManualSync}
              disabled={syncing}
              className="ml-1 p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-white"
              title="Sync now"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
