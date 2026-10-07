import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { http, friendlyAxiosError, inr } from "@/lib/api";
import {
  Landmark, LogOut, RefreshCw, CheckCircle2, Clock,
  ArrowUpRight, AlertCircle, Loader2, Eye, X, ShieldCheck, FileText
} from "lucide-react";

function investorHttp() {
  const token = localStorage.getItem("investor_token") || localStorage.getItem("token");
  return {
    get: (url, cfg) => http.get(url, { ...cfg, headers: { ...(cfg?.headers || {}), Authorization: `Bearer ${token}` } }),
  };
}

export default function InvestorPortal() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [advances, setAdvances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [activePoDetail, setActivePoDetail] = useState(null);
  const [poLoading, setPoLoading] = useState(false);
  const [poError, setPoError] = useState("");

  const api = investorHttp();

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sumRes, advRes] = await Promise.all([
        api.get("/investor-portal/summary"),
        api.get("/investor-portal/advances"),
      ]);
      setSummary(sumRes.data);
      setAdvances(advRes.data || []);
    } catch (err) {
      setError(friendlyAxiosError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleLogout = () => {
    localStorage.removeItem("investor_token");
    localStorage.removeItem("investor_user");
    localStorage.removeItem("token");
    navigate("/investor-login", { replace: true });
  };

  const handleViewPo = async (poId) => {
    setPoLoading(true);
    setPoError("");
    setActivePoDetail(null);
    try {
      const { data } = await api.get(`/investor-portal/pos/${poId}`);
      setActivePoDetail(data);
    } catch (err) {
      setPoError(friendlyAxiosError(err));
    } finally {
      setPoLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-4 sm:px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Landmark className="w-5 h-5" />
          </div>
          <div>
            <div className="font-bold text-white text-base leading-none">
              SSK Capital Partner Portal
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Welcome, {summary?.investor_name || "Partner"}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Refresh Data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-medium transition"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-6 space-y-6">
        {error && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Metric Tiles */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Total Capital Funded
            </div>
            <div className="text-2xl font-bold text-white mt-2 font-mono">
              {summary ? inr(summary.total_funded) : "₹0"}
            </div>
            <div className="text-xs text-slate-500 mt-1">Cumulative cycles</div>
          </div>

          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
            <div className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
              Principal Repaid
            </div>
            <div className="text-2xl font-bold text-emerald-400 mt-2 font-mono">
              {summary ? inr(summary.total_repaid) : "₹0"}
            </div>
            <div className="text-xs text-slate-500 mt-1">Returned to bank</div>
          </div>

          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
            <div className="text-xs font-semibold text-teal-400 uppercase tracking-wider">
              Margin / Finance Gain
            </div>
            <div className="text-2xl font-bold text-teal-400 mt-2 font-mono">
              {summary ? inr(summary.total_margin_earned) : "₹0"}
            </div>
            <div className="text-xs text-slate-500 mt-1">Total margin payouts</div>
          </div>

          <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 shadow-lg relative overflow-hidden">
            <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
              Outstanding Balance
            </div>
            <div className="text-2xl font-bold text-amber-400 mt-2 font-mono">
              {summary ? inr(summary.outstanding_balance) : "₹0"}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Active in {summary?.active_advances_count || 0} PO cycle(s)
            </div>
          </div>
        </div>

        {/* Advances List */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white">Funded Purchase Orders & Advances</h2>
              <p className="text-xs text-slate-400">Scoped strictly to your active and completed cycles</p>
            </div>
            <div className="text-xs text-slate-400 font-medium">
              {advances.length} record(s)
            </div>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
              <span className="text-sm">Loading portfolio data...</span>
            </div>
          ) : advances.length === 0 ? (
            <div className="p-12 text-center text-slate-500 text-sm">
              No advances on record yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-950/50 text-slate-400 text-xs uppercase tracking-wider border-b border-slate-800">
                    <th className="py-3 px-6 font-semibold">Advance Date</th>
                    <th className="py-3 px-6 font-semibold">PO Reference</th>
                    <th className="py-3 px-6 font-semibold text-right">Pairs</th>
                    <th className="py-3 px-6 font-semibold text-right">Funded Amount</th>
                    <th className="py-3 px-6 font-semibold text-center">Status</th>
                    <th className="py-3 px-6 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {advances.map((adv) => {
                    const statusClass =
                      adv.status === "repaid"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : adv.status === "reinvested"
                        ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                        : "bg-amber-500/10 text-amber-400 border-amber-500/30";

                    return (
                      <tr key={adv.id} className="hover:bg-slate-800/30 transition">
                        <td className="py-4 px-6 text-slate-300 font-mono text-xs">
                          {adv.advance_date}
                        </td>
                        <td className="py-4 px-6 font-medium text-white">
                          {adv.po_reference || "PO"}
                        </td>
                        <td className="py-4 px-6 text-right font-mono text-slate-300">
                          {adv.pairs?.toLocaleString("en-IN") || 0}
                        </td>
                        <td className="py-4 px-6 text-right font-mono font-bold text-white">
                          {inr(adv.amount)}
                        </td>
                        <td className="py-4 px-6 text-center">
                          <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold border ${statusClass} uppercase tracking-wider`}>
                            {adv.status}
                          </span>
                        </td>
                        <td className="py-4 px-6 text-right">
                          <button
                            onClick={() => handleViewPo(adv.po_id || adv.id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 hover:text-emerald-300 rounded-lg text-xs font-medium transition border border-slate-700"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Cycle Details</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* PO Status Modal */}
      {(poLoading || activePoDetail || poError) && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
            <button
              onClick={() => { setActivePoDetail(null); setPoError(""); setPoLoading(false); }}
              className="absolute top-4 right-4 p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
            >
              <X className="w-4 h-4" />
            </button>

            {poLoading ? (
              <div className="py-12 text-center text-slate-400 flex flex-col items-center gap-3">
                <Loader2 className="w-7 h-7 animate-spin text-emerald-400" />
                <span className="text-sm">Fetching verified order milestones...</span>
              </div>
            ) : poError ? (
              <div className="py-8 text-center text-rose-400">
                <AlertCircle className="w-8 h-8 mx-auto mb-2 text-rose-500" />
                <div className="text-sm font-semibold">{poError}</div>
              </div>
            ) : activePoDetail ? (
              <div className="space-y-5">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">
                      PO {activePoDetail.po_number}
                    </h3>
                    <div className="text-xs text-slate-400">
                      Style: <span className="text-slate-200 font-medium">{activePoDetail.style}</span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
                    <div className="text-xs text-slate-500">Order Quantity</div>
                    <div className="text-base font-bold text-white font-mono mt-0.5">
                      {activePoDetail.quantity?.toLocaleString("en-IN")} pairs
                    </div>
                  </div>
                  <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
                    <div className="text-xs text-slate-500">Your Funding</div>
                    <div className="text-base font-bold text-white font-mono mt-0.5">
                      {inr(activePoDetail.funding_total)}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 bg-slate-950/50 p-4 rounded-xl border border-slate-800/80 text-xs">
                  <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Dispatch / Production</span>
                    <span className="text-emerald-400 font-semibold">{activePoDetail.dispatch_status}</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Invoicing Status</span>
                    <span className="text-slate-200 font-medium">{activePoDetail.invoice_status}</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Client Payment Received</span>
                    <span className="text-emerald-400 font-mono font-semibold">{inr(activePoDetail.amount_received_from_client_so_far)}</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                    <span className="text-slate-400">Amount Still Receivable</span>
                    <span className="text-amber-400 font-mono font-semibold">{inr(activePoDetail.amount_still_receivable)}</span>
                  </div>
                  <div className="flex justify-between items-center py-1">
                    <span className="text-slate-400">Your Repayment Status</span>
                    <span className="uppercase tracking-wider font-bold text-white">{activePoDetail.repayment_status}</span>
                  </div>
                </div>

                <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 shrink-0 text-emerald-400" />
                  <span>Real-time status confirmed against ERP production ledger.</span>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
