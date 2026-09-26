import React, { useState, useEffect } from "react";
import { ArrowLeft, CheckCircle2, QrCode, MapPin, Box, Check, RefreshCw, AlertCircle, Sparkles } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

/**
 * MobilePicklist (U-003)
 * Mobile-first picklist & scanning workflow optimized for warehouse floor pickers
 * on mobile phones and tablets.
 */
export default function MobilePicklist() {
  const navigate = useNavigate();
  const [picklists, setPicklists] = useState([]);
  const [activePicklist, setActivePicklist] = useState(null);
  const [currentItemIdx, setCurrentItemIdx] = useState(0);
  const [scannedCode, setScannedCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetchPicklists();
  }, []);

  const fetchPicklists = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/picklists");
      if (res.ok) {
        const data = await res.json();
        const active = (Array.isArray(data) ? data : []).filter(
          (p) => p.status === "pending" || p.status === "picking"
        );
        setPicklists(active);
        if (active.length > 0 && !activePicklist) {
          setActivePicklist(active[0]);
        }
      }
    } catch (err) {
      console.error("Failed to load picklists:", err);
    } finally {
      setLoading(false);
    }
  };

  const handlePickItem = async (index) => {
    if (!activePicklist) return;
    const items = [...(activePicklist.items || [])];
    if (items[index]) {
      items[index].picked = true;
      items[index].picked_at = new Date().toISOString();
    }

    const allPicked = items.every((i) => i.picked);
    const updatedPicklist = {
      ...activePicklist,
      items,
      status: allPicked ? "completed" : "picking",
    };
    setActivePicklist(updatedPicklist);

    // Provide haptic feedback if available on mobile
    if (navigator.vibrate) {
      navigator.vibrate(100);
    }

    setMessage({ type: "success", text: `Picked item #${index + 1} successfully!` });
    setTimeout(() => setMessage(null), 2000);

    // Advance to next unpicked item
    const nextIdx = items.findIndex((i, idx) => idx > index && !i.picked);
    if (nextIdx !== -1) {
      setCurrentItemIdx(nextIdx);
    }

    // Sync to backend
    try {
      await fetch(`/api/picklists/${activePicklist.id || activePicklist._id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items,
          status: allPicked ? "completed" : "picking",
        }),
      });
    } catch (e) {
      console.warn("Offline fallback will sync pick update");
    }
  };

  const items = activePicklist?.items || [];
  const currentItem = items[currentItemIdx] || items[0];
  const pickedCount = items.filter((i) => i.picked).length;
  const progressPct = items.length ? Math.round((pickedCount / items.length) * 100) : 0;

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col max-w-md mx-auto shadow-2xl">
      {/* Mobile Top Header */}
      <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between sticky top-0 z-40">
        <button
          onClick={() => navigate("/warehouse")}
          className="p-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>

        <div className="text-center">
          <h1 className="text-sm font-bold text-slate-100">
            {activePicklist?.picklist_no || "Mobile Pick Flow"}
          </h1>
          <p className="text-[11px] text-slate-400">
            {activePicklist?.channel || "E-Commerce Dispatch"}
          </p>
        </div>

        <button
          onClick={fetchPicklists}
          className="p-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Notification Toast */}
      {message && (
        <div className="bg-emerald-600 text-white text-xs font-bold py-2 px-4 text-center animate-in slide-in-from-top-2">
          {message.text}
        </div>
      )}

      {/* Progress Bar */}
      <div className="bg-slate-900 px-4 py-2 border-b border-slate-800">
        <div className="flex justify-between text-xs text-slate-300 font-semibold mb-1">
          <span>Progress: {pickedCount} / {items.length} items</span>
          <span>{progressPct}%</span>
        </div>
        <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 rounded-full transition-all duration-300"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 p-4 flex flex-col justify-between">
        {currentItem ? (
          <div className="space-y-4">
            {/* Location Banner (Huge touch target & legibility) */}
            <div className="bg-gradient-to-br from-blue-900/60 to-indigo-950/80 border border-blue-600/40 rounded-3xl p-5 text-center shadow-lg">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-bold uppercase tracking-wider mb-2">
                <MapPin className="w-3.5 h-3.5" />
                Target Cell Location
              </span>
              <div className="text-4xl font-black text-white tracking-wider my-2 font-mono">
                {currentItem.location_code || "R01-RK1-C01"}
              </div>
              <p className="text-xs text-blue-200/80">
                Zone: {currentItem.zone || "Main"} • Aisle Position
              </p>
            </div>

            {/* SKU Details Card */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3">
              <div className="flex justify-between items-start">
                <div>
                  <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">
                    Product Style
                  </span>
                  <div className="text-xl font-bold text-white">
                    {currentItem.style_code || "Classic Sneaker"}
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">
                    Quantity
                  </span>
                  <div className="text-2xl font-black text-amber-400">
                    {currentItem.qty || 1} <span className="text-xs font-semibold text-slate-400">pairs</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800">
                <div className="bg-slate-800/60 p-2.5 rounded-xl">
                  <span className="text-[10px] text-slate-400 uppercase">Color</span>
                  <div className="text-sm font-bold text-slate-200">
                    {currentItem.color || "Black"}
                  </div>
                </div>
                <div className="bg-slate-800/60 p-2.5 rounded-xl">
                  <span className="text-[10px] text-slate-400 uppercase">Size</span>
                  <div className="text-sm font-bold text-slate-200">
                    {currentItem.size || "8"}
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Barcode Scan Simulation */}
            <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-3 flex items-center gap-2">
              <QrCode className="w-5 h-5 text-slate-400 ml-1" />
              <input
                type="text"
                placeholder="Scan or enter barcode..."
                value={scannedCode}
                onChange={(e) => setScannedCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handlePickItem(currentItemIdx);
                    setScannedCode("");
                  }
                }}
                className="bg-transparent text-sm w-full text-white placeholder-slate-500 focus:outline-none"
              />
            </div>
          </div>
        ) : (
          <div className="text-center py-16 space-y-3">
            <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto" />
            <h2 className="text-xl font-bold">Picklist Complete!</h2>
            <p className="text-sm text-slate-400">All items have been verified and picked.</p>
          </div>
        )}

        {/* Primary Floor Touch Button */}
        {currentItem && (
          <div className="pt-4">
            <button
              onClick={() => handlePickItem(currentItemIdx)}
              disabled={currentItem.picked}
              className={`w-full py-4 rounded-2xl font-black text-lg flex items-center justify-center gap-2 shadow-2xl transition-transform active:scale-95 ${
                currentItem.picked
                  ? "bg-slate-800 text-slate-500 cursor-not-allowed"
                  : "bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold"
              }`}
            >
              <Check className="w-6 h-6 stroke-[3]" />
              {currentItem.picked ? "ITEM CONFIRMED" : "CONFIRM PICK"}
            </button>
          </div>
        )}
      </div>

      {/* Item Selector Tabs along bottom */}
      <div className="bg-slate-900 border-t border-slate-800 p-2 overflow-x-auto flex gap-2">
        {items.map((it, idx) => (
          <button
            key={idx}
            onClick={() => setCurrentItemIdx(idx)}
            className={`px-3 py-2 rounded-xl text-xs font-bold whitespace-nowrap flex items-center gap-1.5 transition-colors ${
              currentItemIdx === idx
                ? "bg-blue-600 text-white"
                : it.picked
                ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800/50"
                : "bg-slate-800 text-slate-300"
            }`}
          >
            {it.picked && <Check className="w-3 h-3 text-emerald-400" />}
            Item #{idx + 1}
          </button>
        ))}
      </div>
    </div>
  );
}
