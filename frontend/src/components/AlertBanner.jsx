import React, { useState, useEffect } from "react";
import { AlertTriangle, AlertOctagon, Info, ChevronRight, X, RefreshCw, ShoppingCart } from "lucide-react";

/**
 * AlertBanner (U-002)
 * Real-time low-stock and urgent alert banners with severity-based notifications.
 */
export default function AlertBanner({ onActionClick }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetchStockAlerts();
  }, []);

  const fetchStockAlerts = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/reports/safety-stock?service_level_z=1.65");
      if (res.ok) {
        const data = await res.json();
        const critical = (data.recommendations || []).filter(
          (r) => r.status === "STOCKOUT_CRITICAL" || r.status === "REORDER_NOW"
        );
        setAlerts(critical);
      }
    } catch (err) {
      console.warn("Could not load stock alerts:", err);
    } finally {
      setLoading(false);
    }
  };

  if (dismissed || alerts.length === 0) return null;

  const criticalCount = alerts.filter((a) => a.status === "STOCKOUT_CRITICAL").length;
  const isCritical = criticalCount > 0;

  return (
    <div className={`w-full border-b transition-all duration-300 ${
      isCritical
        ? "bg-rose-950/40 border-rose-800 text-rose-200"
        : "bg-amber-950/40 border-amber-800 text-amber-200"
    }`}>
      <div className="max-w-7xl mx-auto px-4 py-2.5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {isCritical ? (
            <AlertOctagon className="w-5 h-5 text-rose-500 shrink-0 animate-pulse" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
          )}

          <div className="text-xs sm:text-sm font-medium">
            <span className="font-bold mr-1">
              {isCritical ? "CRITICAL STOCK ALERT:" : "INVENTORY WARNING:"}
            </span>
            <span>
              {criticalCount > 0 ? `${criticalCount} SKUs in critical stockout risk.` : ""} {alerts.length} items have fallen below safety reorder thresholds.
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-black/30 hover:bg-black/50 border border-white/10 flex items-center gap-1 transition-colors"
          >
            {expanded ? "Hide Details" : "View Critical SKUs"}
            <ChevronRight className={`w-3.5 h-3.5 transition-transform ${expanded ? "rotate-90" : ""}`} />
          </button>

          <button
            onClick={() => setDismissed(true)}
            className="p-1 rounded-lg hover:bg-white/10 transition-colors text-slate-400 hover:text-white"
            title="Dismiss Alert"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Expanded Alert Drawer */}
      {expanded && (
        <div className="max-w-7xl mx-auto px-4 pb-4 pt-1 border-t border-white/5">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 max-h-56 overflow-y-auto pr-1">
            {alerts.slice(0, 12).map((item, idx) => (
              <div
                key={idx}
                className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-xl flex items-center justify-between text-xs"
              >
                <div>
                  <div className="font-bold text-white flex items-center gap-1.5">
                    <span>{item.style_code}</span>
                    <span className="text-slate-400 font-normal">Sz: {item.size}</span>
                  </div>
                  <div className="text-slate-400 text-[11px] mt-0.5">
                    Current: <strong className="text-rose-400">{item.current_ready_stock}</strong> / Safety: {item.safety_stock}
                  </div>
                </div>

                <div className="text-right">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    item.status === "STOCKOUT_CRITICAL"
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                  }`}>
                    {item.status === "STOCKOUT_CRITICAL" ? "Critical" : "Reorder"}
                  </span>
                  <div className="text-emerald-400 text-[11px] font-semibold mt-1">
                    +{item.recommended_order_qty} pairs rec.
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
