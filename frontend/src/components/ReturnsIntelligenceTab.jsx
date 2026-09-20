import { useState, useEffect, useCallback } from "react";
import { http, inr } from "../lib/api";
import { Card, BtnPrimary, BtnSecondary, Input, Select, Badge } from "./ui-kit";
import {
  Upload, RefreshCw, ShieldAlert, CheckCircle2, AlertTriangle,
  RotateCcw, Sliders, Scissors, Camera, CheckSquare, Eye,
  ArrowRight, TrendingDown, IndianRupee, Layers, Package, Image as ImageIcon
} from "lucide-react";

export default function ReturnsIntelligenceTab({ defaultMonth = "2026-08", defaultPlatform = "myntra" }) {
  const [month, setMonth] = useState(defaultMonth);
  const [platform, setPlatform] = useState(defaultPlatform);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Upload state
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Data state
  const [analytics, setAnalytics] = useState(null);
  const [prescriptions, setPrescriptions] = useState([]);
  const [appliedActions, setAppliedActions] = useState([]);
  const [impactResults, setImpactResults] = useState([]);
  const [selectedStyleCode, setSelectedStyleCode] = useState("");

  // Action Apply Modal State
  const [actionModal, setActionModal] = useState(null); // { style_code, action_type, category, title, recommendation }
  const [appliedDate, setAppliedDate] = useState(new Date().toISOString().split("T")[0]);
  const [targetReduction, setTargetReduction] = useState(30);
  const [actionNotes, setActionNotes] = useState("");
  const [savingAction, setSavingAction] = useState(false);

  // Style Photo preview & upload state
  const [previewImage, setPreviewImage] = useState(null);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  // Load analytics, prescriptions, applied actions, impact
  const loadReturnsData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [anRes, rxRes, actRes, impRes] = await Promise.all([
        http.get(`/online-returns/analytics?month=${encodeURIComponent(month)}&platform=${encodeURIComponent(platform)}`),
        http.get(`/online-returns/prescriptions?month=${encodeURIComponent(month)}&platform=${encodeURIComponent(platform)}`),
        http.get(`/online-returns/actions`),
        http.get(`/online-returns/impact-check?platform=${encodeURIComponent(platform)}`),
      ]);

      setAnalytics(anRes.data);
      setPrescriptions(rxRes.data?.prescriptions || []);
      setAppliedActions(actRes.data || []);
      setImpactResults(impRes.data?.results || []);

      if (anRes.data?.styles?.length && !selectedStyleCode) {
        setSelectedStyleCode(anRes.data.styles[0].style_code);
      }
    } catch (err) {
      console.error("Failed to load returns intelligence:", err);
      // Non-blocking if no records yet
    } finally {
      setLoading(false);
    }
  }, [month, platform, selectedStyleCode]);

  useEffect(() => {
    loadReturnsData();
  }, [loadReturnsData]);

  // Handle Return Report CSV Upload
  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!uploadFile) {
      setError("Please select a Myntra Return Report CSV file.");
      return;
    }

    setUploading(true);
    setError("");
    setSuccessMsg("");

    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      const res = await http.post(
        `/online-returns/upload?month=${encodeURIComponent(month)}&platform=${encodeURIComponent(platform)}`,
        fd,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        }
      );
      setSuccessMsg(`Successfully ingested ${res.data?.rows_processed || "all"} return records for ${month}.`);
      setUploadFile(null);
      await loadReturnsData();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (detail?.[0]?.msg || err?.message || "Failed to upload return report.");
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  // Submit Applied Fix
  const handleSaveAction = async (e) => {
    e.preventDefault();
    if (!actionModal) return;

    setSavingAction(true);
    setError("");
    try {
      await http.post("/online-returns/actions", {
        style_code: actionModal.style_code,
        action_type: actionModal.action_type,
        category: actionModal.category,
        title: actionModal.title,
        description: actionNotes || actionModal.recommendation,
        target_month: month,
        applied_date: appliedDate,
        target_reduction_pct: parseFloat(targetReduction) || 30.0,
      });

      setActionModal(null);
      setActionNotes("");
      await loadReturnsData();
    } catch (err) {
      setError("Failed to record applied action: " + (err?.response?.data?.detail || err?.message));
    } finally {
      setSavingAction(false);
    }
  };

  // Upload or update style photo
  const handleUploadStylePhoto = async (styleCode, file) => {
    if (!file) return;
    setUploadingPhoto(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const upRes = await http.post("/upload/image", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const imgUrl = upRes.data?.url || upRes.data?.thumbnail_url || upRes.data?.display_url;
      if (imgUrl) {
        await http.post("/online-returns/style-photo", {
          style_code: styleCode,
          image_url: imgUrl,
        });
        setSuccessMsg(`Photo updated for style ${styleCode}`);
        await loadReturnsData();
      }
    } catch (err) {
      console.error("Failed to upload style photo:", err);
      setError("Failed to upload photo for " + styleCode);
    } finally {
      setUploadingPhoto(false);
    }
  };

  const selectedStyle = analytics?.styles?.find((s) => s.style_code === selectedStyleCode);

  const categoryMeta = {
    SIZING_FIT: { label: "Sizing & Fit", icon: Scissors, color: "bg-rose-50 border-rose-200 text-rose-800", badge: "red" },
    COURIER_RTO: { label: "Courier RTO", icon: RotateCcw, color: "bg-amber-50 border-amber-200 text-amber-800", badge: "yellow" },
    QUALITY_DEFECT: { label: "Quality Defect", icon: AlertTriangle, color: "bg-purple-50 border-purple-200 text-purple-800", badge: "purple" },
    CATALOG_MISMATCH: { label: "Catalog Mismatch", icon: Camera, color: "bg-blue-50 border-blue-200 text-blue-800", badge: "blue" },
    DISPATCH_ERROR: { label: "Dispatch Error", icon: Package, color: "bg-orange-50 border-orange-200 text-orange-800", badge: "orange" },
    BUYER_REMORSE: { label: "Buyer Remorse", icon: Eye, color: "bg-slate-50 border-slate-200 text-slate-800", badge: "slate" },
  };

  return (
    <div className="space-y-6" data-testid="returns-intelligence-tab">
      {/* ── HEADER TOOLBAR: Controls & Upload ────────────────────────── */}
      <Card className="p-4 bg-slate-50 border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Month</label>
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-mono font-bold bg-white text-slate-800"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
              >
                <option value="myntra">Myntra</option>
                <option value="flipkart">Flipkart</option>
              </select>
            </div>
            <div className="pt-4">
              <BtnSecondary onClick={loadReturnsData} disabled={loading} className="text-xs flex items-center gap-1.5">
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
              </BtnSecondary>
            </div>
          </div>

          {/* Quick Upload Form */}
          <form onSubmit={handleFileUpload} className="flex items-center gap-2">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Upload Return Report (.csv)
              </label>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => setUploadFile(e.target.files[0])}
                disabled={uploading}
                className="text-xs text-slate-600 file:mr-2 file:py-1.5 file:px-3 file:border-0 file:text-xs file:font-bold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer"
              />
            </div>
            <div className="pt-4">
              <BtnPrimary type="submit" disabled={uploading || !uploadFile} className="text-xs flex items-center gap-1.5">
                <Upload className="w-3.5 h-3.5" />
                {uploading ? "Ingesting..." : "Ingest Returns"}
              </BtnPrimary>
            </div>
          </form>
        </div>

        {error && (
          <div className="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div className="mt-3 p-2.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}
      </Card>

      {/* ── KPI HIGHLIGHT CARDS ───────────────────────────────────────── */}
      {analytics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card className="p-4 border-2 border-rose-200/80 bg-rose-50/30">
            <div className="text-[10px] uppercase font-bold text-slate-500">Total Returns Analyzed</div>
            <div className="text-2xl font-black font-mono text-rose-700 mt-1">
              {analytics.total_returns}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Reporting Period: <strong className="font-mono">{analytics.month}</strong>
            </div>
          </Card>

          <Card className="p-4 border-2 border-slate-200">
            <div className="text-[10px] uppercase font-bold text-slate-500">Customer vs Courier RTO</div>
            <div className="text-xl font-black font-mono text-slate-900 mt-1">
              {analytics.customer_returns} <span className="text-xs font-normal text-slate-500">cust</span> / {analytics.rto_returns} <span className="text-xs font-normal text-slate-500">rto</span>
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              RTO Rate: <strong>{analytics.total_returns > 0 ? Math.round((analytics.rto_returns / analytics.total_returns) * 100) : 0}%</strong>
            </div>
          </Card>

          <Card className="p-4 border-2 border-amber-200 bg-amber-50/20">
            <div className="text-[10px] uppercase font-bold text-slate-500">Reverse Logistics Damage</div>
            <div className="text-xl font-black font-mono text-amber-800 mt-1">
              ₹{Math.round(analytics.total_reverse_freight_damage || 0).toLocaleString()}
            </div>
            <div className="text-[10px] text-slate-500 mt-1">
              Avg ₹85 marketplace return freight penalty
            </div>
          </Card>

          <Card className="p-4 border-2 border-emerald-200 bg-emerald-50/20">
            <div className="text-[10px] uppercase font-bold text-emerald-800">Prescriptions Generated</div>
            <div className="text-2xl font-black font-mono text-emerald-700 mt-1">
              {prescriptions.length}
            </div>
            <div className="text-[10px] text-emerald-700 mt-1">
              High-impact actionable workshop fixes
            </div>
          </Card>
        </div>
      )}

      {/* ── ROOT-CAUSE CATEGORY BREAKDOWN ────────────────────────────── */}
      {analytics?.category_breakdown && (
        <Card className="p-5 border-2 border-slate-200 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-indigo-600" />
              <h4 className="font-bold text-sm uppercase tracking-wider text-slate-900">
                Footwear Return Root-Cause Taxonomy
              </h4>
            </div>
            <span className="text-xs text-slate-500">Automated Natural Language Clustering</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {Object.entries(analytics.category_breakdown).map(([catKey, count]) => {
              const meta = categoryMeta[catKey] || { label: catKey, icon: Package, color: "bg-slate-50 border-slate-200 text-slate-800", badge: "slate" };
              const IconComp = meta.icon;
              const pct = analytics.total_returns > 0 ? Math.round((count / analytics.total_returns) * 100) : 0;
              return (
                <div key={catKey} className={`p-3 rounded border ${meta.color} space-y-1`}>
                  <div className="flex items-center justify-between">
                    <IconComp className="w-4 h-4 opacity-80" />
                    <span className="text-xs font-mono font-bold">{pct}%</span>
                  </div>
                  <div className="text-lg font-black font-mono">{count}</div>
                  <div className="text-[11px] font-bold leading-tight">{meta.label}</div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* ── FOOTWEAR SIZING SKEW & LAST MOLD DEVIATION ───────────────── */}
      {analytics?.styles?.length > 0 && (
        <Card className="p-5 border-2 border-slate-200 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <h4 className="font-bold text-sm uppercase tracking-wider text-slate-900 flex items-center gap-2">
                <Scissors className="w-4 h-4 text-rose-600" />
                Footwear Sizing Skew & Last Mold Deviation
              </h4>
              <p className="text-xs text-slate-500">
                Identifies asymmetric size returns (tight fit vs loose fit) to guide lasting mold tooling alterations
              </p>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-xs font-bold text-slate-600">Select Style:</label>
              <select
                value={selectedStyleCode}
                onChange={(e) => setSelectedStyleCode(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1 text-xs font-mono font-bold bg-white text-slate-800"
              >
                {analytics.styles.map((s) => (
                  <option key={s.style_code} value={s.style_code}>
                    {`${s.style_code} (${s.total_returns} returns)`}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {selectedStyle ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-50 p-3.5 rounded border border-slate-200 text-xs">
                <div className="flex items-center gap-3">
                  <div
                    className="relative w-16 h-16 rounded border-2 border-slate-300 bg-white overflow-hidden shadow-sm shrink-0 cursor-pointer group"
                    onClick={() => selectedStyle.image_url && setPreviewImage(selectedStyle.image_url)}
                    title="Click to expand style photo"
                  >
                    {selectedStyle.image_url ? (
                      <img
                        src={selectedStyle.image_url}
                        alt={selectedStyle.style_code}
                        className="w-full h-full object-cover transition-transform group-hover:scale-105"
                      />
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center bg-slate-100 text-slate-400">
                        <ImageIcon className="w-5 h-5" />
                        <span className="text-[8px] font-bold mt-0.5">No Photo</span>
                      </div>
                    )}
                    <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
                      <Eye className="w-4 h-4" />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-black text-slate-900 font-mono text-base">{selectedStyle.style_code}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-200 text-slate-800 uppercase tracking-wider">
                        {selectedStyle.brand || "SSK"}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      Top complaint: <strong className="text-rose-700">{selectedStyle.top_reason || "None"}</strong> · Category: <strong>{selectedStyle.top_category || "OTHER"}</strong>
                    </div>
                    <label className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-700 hover:text-indigo-900 cursor-pointer mt-1">
                      <Camera className="w-3 h-3" />
                      <span>{uploadingPhoto ? "Uploading..." : "Change / Upload Photo"}</span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        disabled={uploadingPhoto}
                        onChange={(e) => handleUploadStylePhoto(selectedStyle.style_code, e.target.files[0])}
                      />
                    </label>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-4 bg-white px-3.5 py-2 rounded border border-slate-200">
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Total Returns</div>
                    <div className="font-mono font-bold text-rose-700 text-sm">{selectedStyle.total_returns}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Cust / RTO</div>
                    <div className="font-mono text-slate-800 text-xs font-semibold">{selectedStyle.customer_returns} / {selectedStyle.rto_returns}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-500">Est. Freight Loss</div>
                    <div className="font-mono font-bold text-amber-700 text-xs">₹{selectedStyle.estimated_reverse_freight}</div>
                  </div>
                </div>
              </div>

              {/* Per Size Breakdown Table */}
              <div className="overflow-x-auto border border-slate-200 rounded">
                <table className="w-full text-xs text-left border-collapse">
                  <thead className="bg-slate-100 text-slate-600 text-[10px] uppercase tracking-wider font-bold">
                    <tr>
                      <th className="p-2.5">Shoe Size</th>
                      <th className="p-2.5 text-right">Total Returns</th>
                      <th className="p-2.5 text-right text-amber-700">Tight / Too Small</th>
                      <th className="p-2.5 text-right text-purple-700">Loose / Too Large</th>
                      <th className="p-2.5 text-right text-slate-500">Other Reasons</th>
                      <th className="p-2.5">Mold Action Diagnosis</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {Object.entries(selectedStyle.sizes || {}).map(([sz, sData]) => {
                      const small = sData.too_small || 0;
                      const big = sData.too_big || 0;
                      let diagnosis = <span className="text-slate-400">Normal variance</span>;
                      if (small > big && small >= 2) {
                        diagnosis = (
                          <Badge color="red">
                            Runs Small · Expand toe box 3.5mm
                          </Badge>
                        );
                      } else if (big > small && big >= 2) {
                        diagnosis = (
                          <Badge color="purple">
                            Runs Large · Shave 2.5mm mold girth
                          </Badge>
                        );
                      }
                      return (
                        <tr key={sz} className="hover:bg-slate-50/60">
                          <td className="p-2.5 font-bold font-mono text-slate-900">Size {sz}</td>
                          <td className="p-2.5 text-right font-mono font-bold text-slate-800">{sData.total}</td>
                          <td className="p-2.5 text-right font-mono font-bold text-rose-700">{small}</td>
                          <td className="p-2.5 text-right font-mono font-bold text-purple-700">{big}</td>
                          <td className="p-2.5 text-right font-mono text-slate-500">{sData.other || 0}</td>
                          <td className="p-2.5">{diagnosis}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="p-6 text-center text-slate-400 italic">
              Select a style to inspect sizing mold variance.
            </div>
          )}
        </Card>
      )}

      {/* ── PRESCRIPTIVE REDUCTION ENGINE ───────────────────────────── */}
      {prescriptions.length > 0 && (
        <Card className="p-5 border-2 border-indigo-200/80 bg-indigo-50/10 space-y-4">
          <div className="flex items-center justify-between border-b border-indigo-100 pb-3">
            <div className="flex items-center gap-2">
              <Sliders className="w-5 h-5 text-indigo-700" />
              <h4 className="font-bold text-sm uppercase tracking-wider text-slate-900">
                Prescriptive Return Reduction Engine ({prescriptions.length} Styles Targeted)
              </h4>
            </div>
            <span className="text-xs text-indigo-700 font-semibold">Factory Lasting & QC Directives</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {prescriptions.map((p) => (
              <div key={p.style_code} className="bg-white border-2 border-slate-200 rounded p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <div className="flex items-center gap-2.5">
                    {p.image_url ? (
                      <img
                        src={p.image_url}
                        alt={p.style_code}
                        className="w-12 h-12 rounded border border-slate-300 object-cover shrink-0 cursor-pointer hover:opacity-90"
                        onClick={() => setPreviewImage(p.image_url)}
                        title="Click to expand photo"
                      />
                    ) : (
                      <div className="w-12 h-12 rounded border border-slate-200 bg-slate-100 flex items-center justify-center text-slate-400 shrink-0">
                        <Package className="w-5 h-5" />
                      </div>
                    )}
                    <div>
                      <span className="font-mono font-bold text-slate-900 text-sm">{p.style_code}</span>
                      <span className="text-slate-500 text-xs ml-2">({p.total_returns} returns)</span>
                    </div>
                  </div>
                  <Badge color={p.priority === "CRITICAL" ? "red" : p.priority === "HIGH" ? "orange" : "blue"}>
                    {p.priority} Priority
                  </Badge>
                </div>

                <div className="space-y-3">
                  {p.actions.map((act, aIdx) => (
                    <div key={aIdx} className="bg-slate-50 p-3 rounded border border-slate-200 text-xs space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800 flex items-center gap-1.5">
                          {act.title}
                        </span>
                        <Badge color="slate">{act.action_type}</Badge>
                      </div>
                      <p className="text-slate-600 leading-relaxed">
                        {act.recommendation}
                      </p>
                      <div className="flex items-center justify-between pt-1 border-t border-slate-200/60">
                        <span className="text-[11px] text-emerald-700 font-semibold flex items-center gap-1">
                          <TrendingDown className="w-3.5 h-3.5" /> {act.expected_impact}
                        </span>
                        <button
                          type="button"
                          onClick={() => setActionModal({
                            style_code: p.style_code,
                            action_type: act.action_type,
                            category: act.category,
                            title: act.title,
                            recommendation: act.recommendation,
                          })}
                          className="text-[11px] font-bold uppercase tracking-wider text-indigo-700 hover:text-indigo-900 flex items-center gap-1"
                        >
                          <CheckSquare className="w-3.5 h-3.5" /> Mark Fix Applied
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── APPLIED ACTIONS & IMPACT VERIFICATION TRACKER ───────────── */}
      <Card className="p-5 border-2 border-slate-200 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            <h4 className="font-bold text-sm uppercase tracking-wider text-slate-900">
              Applied Fixes & Impact Verification ({impactResults.length} Tracked)
            </h4>
          </div>
          <span className="text-xs text-slate-500">Real-Time Before/After Return Verification</span>
        </div>

        {impactResults.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead className="bg-slate-100 text-slate-600 text-[10px] uppercase tracking-wider font-bold">
                <tr>
                  <th className="p-2.5">Applied Date</th>
                  <th className="p-2.5">Style Code</th>
                  <th className="p-2.5">Intervention Type</th>
                  <th className="p-2.5">Action Title</th>
                  <th className="p-2.5 text-right">Pre-Fix Returns</th>
                  <th className="p-2.5 text-right">Post-Fix Returns</th>
                  <th className="p-2.5 text-right">Reduction %</th>
                  <th className="p-2.5 text-right">Saved Freight (₹)</th>
                  <th className="p-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {impactResults.map((imp) => (
                  <tr key={imp.action_id} className="hover:bg-slate-50/60">
                    <td className="p-2.5 font-mono text-slate-600">{imp.applied_date}</td>
                    <td className="p-2.5 font-mono font-bold text-slate-900">{imp.style_code}</td>
                    <td className="p-2.5">
                      <Badge color="slate">{imp.action_type}</Badge>
                    </td>
                    <td className="p-2.5 font-semibold text-slate-800">{imp.title}</td>
                    <td className="p-2.5 text-right font-mono font-bold text-slate-700">{imp.pre_fix_returns}</td>
                    <td className="p-2.5 text-right font-mono font-bold text-emerald-700">{imp.post_fix_returns}</td>
                    <td className="p-2.5 text-right font-mono font-black text-emerald-700">
                      {imp.reduction_pct}%
                    </td>
                    <td className="p-2.5 text-right font-mono font-black text-emerald-700">
                      ₹{imp.saved_freight.toLocaleString()}
                    </td>
                    <td className="p-2.5">
                      <Badge color={imp.status === "REDUCED_SUCCESSFULLY" ? "green" : imp.status === "IN_PROGRESS" ? "yellow" : "red"}>
                        {imp.status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 text-center text-slate-400 italic">
            No workshop actions logged yet. Apply prescriptive fixes above to monitor impact and track reverse freight savings.
          </div>
        )}
      </Card>

      {/* ── APPLY FIX MODAL ─────────────────────────────────────────── */}
      {actionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="max-w-lg w-full p-6 space-y-4 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b pb-3">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-700">
                  Log Production / Lasting Intervention
                </div>
                <h3 className="text-base font-bold text-slate-900">
                  {actionModal.title}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setActionModal(null)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveAction} className="space-y-4 text-xs">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                  Style Code
                </label>
                <input
                  type="text"
                  disabled
                  value={actionModal.style_code}
                  className="w-full border border-slate-300 rounded px-3 py-2 bg-slate-50 font-mono font-bold text-slate-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                    Date Applied *
                  </label>
                  <input
                    type="date"
                    required
                    value={appliedDate}
                    onChange={(e) => setAppliedDate(e.target.value)}
                    className="w-full border border-slate-300 rounded px-3 py-2 font-mono font-semibold"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                    Target Reduction %
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="100"
                    value={targetReduction}
                    onChange={(e) => setTargetReduction(e.target.value)}
                    className="w-full border border-slate-300 rounded px-3 py-2 font-mono font-semibold"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                  Factory Workshop Action Notes
                </label>
                <textarea
                  rows={3}
                  defaultValue={actionModal.recommendation}
                  onChange={(e) => setActionNotes(e.target.value)}
                  className="w-full border border-slate-300 rounded px-3 py-2 text-xs"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <BtnSecondary type="button" onClick={() => setActionModal(null)} disabled={savingAction}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={savingAction} className="flex items-center gap-1.5">
                  <CheckSquare className="w-4 h-4" />
                  {savingAction ? "Saving..." : "Confirm & Track Impact"}
                </BtnPrimary>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── IMAGE ENLARGED MODAL PREVIEW ─────────────────────────── */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-xl max-h-[85vh] bg-white rounded p-3 shadow-2xl space-y-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Style Photo Preview</span>
              <button
                type="button"
                onClick={() => setPreviewImage(null)}
                className="w-6 h-6 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold flex items-center justify-center"
              >
                ✕
              </button>
            </div>
            <img src={previewImage} alt="Style Preview" className="max-w-full max-h-[75vh] rounded object-contain mx-auto" />
          </div>
        </div>
      )}
    </div>
  );
}
