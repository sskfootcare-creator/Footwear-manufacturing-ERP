import { useEffect, useState } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, StatTile, Card, BtnSecondary } from "../components/ui-kit";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { AlertTriangle, Clock, ArrowRight, Receipt, Wrench } from "lucide-react";

const STAGE_COLORS = {
  procurement: "#64748B", cutting: "#2563EB", folding: "#0284C7",
  attachment: "#7C3AED", stitching: "#C27842", lasting: "#A65D24",
  sole_pasting: "#F59E0B", finishing: "#16A34A", dispatched: "#F97316",
};

const STAGE_LABEL = {
  procurement: "Procurement", cutting: "Cutting", folding: "Folding",
  attachment: "Attachment", stitching: "Stitching", lasting: "Lasting",
  sole_pasting: "Sole Pasting", finishing: "Finishing", dispatched: "Dispatched",
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [overdue, setOverdue] = useState([]);
  const [overdueInvoices, setOverdueInvoices] = useState([]);
  const [unmatchedStyles, setUnmatchedStyles] = useState([]);
  const { user } = useAuth();

  useEffect(() => {
    http.get("/dashboard/stats").then((r) => setStats(r.data)).catch(() => {});
    http.get("/dashboard/overdue").then((r) => setOverdue(r.data || [])).catch(() => {});
    http.get("/invoices/overdue").then((r) => setOverdueInvoices(r.data || [])).catch(() => {});
    http.get("/production/unmatched-styles").then((r) => setUnmatchedStyles(r.data || [])).catch(() => {});
  }, []);

  const seedDemo = async () => {
    try { await http.post("/seed/demo"); window.location.reload(); } catch {}
  };

  if (!stats) return <div className="p-8 text-sm text-slate-500">Loading factory data...</div>;
  const maxStage = Math.max(...Object.values(stats.stage_counts), 1);

  return (
    <div>
      <PageHeader
        title="Control Room"
        subtitle="Dashboard"
        testId="dashboard-header"
        action={
          user?.role === "admin" && stats.materials_count === 0 ? (
            <BtnSecondary onClick={seedDemo} data-testid="seed-demo-btn">Seed demo materials</BtnSecondary>
          ) : (
            <div className="text-xs text-slate-500 uppercase tracking-wider">
              <span className="font-bold text-slate-900">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric" })}</span>
            </div>
          )
        }
      />

      <div className="p-8 space-y-6">
        {overdueInvoices.length > 0 && (
          <Card className="bg-red-50 border-2 border-red-300 px-5 py-3 flex items-center justify-between" data-testid="overdue-invoices-banner">
            <div className="flex items-center gap-3">
              <Receipt className="w-5 h-5 text-red-600" />
              <div>
                <div className="font-bold text-red-700 text-sm">
                  {overdueInvoices.length} overdue payment{overdueInvoices.length > 1 ? "s" : ""} · {inr(overdueInvoices.reduce((s, r) => s + (r.outstanding || 0), 0))} receivable
                </div>
                <div className="text-xs text-red-600">Payment terms exceeded — review and chase up.</div>
              </div>
            </div>
            <Link to="/invoices" className="text-xs uppercase tracking-wider font-bold text-red-700 hover:underline">Open invoices →</Link>
          </Card>
        )}

        {overdue.length > 0 && (
          <Card className="bg-red-50 border-2 border-red-300 overflow-hidden" data-testid="overdue-alert-banner">
            <div className="bg-red-600 text-white px-5 py-2 flex items-baseline justify-between">
              <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-xs">
                <AlertTriangle className="w-4 h-4" /> {overdue.length} Overdue Production Task{overdue.length > 1 ? "s" : ""}
              </div>
              <Link to="/production" className="text-[10px] uppercase tracking-wider font-bold hover:underline flex items-center gap-1">
                Open production floor <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="max-h-72 overflow-y-auto">
              <table className="w-full text-xs" data-testid="overdue-table">
                <thead className="bg-red-100 sticky top-0">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-red-800 border-b border-red-200">
                    <th className="px-4 py-2 font-bold">PO</th>
                    <th className="px-4 py-2 font-bold">Style</th>
                    <th className="px-4 py-2 font-bold">Color · Size</th>
                    <th className="px-4 py-2 font-bold">Stage</th>
                    <th className="px-4 py-2 font-bold text-right">Pairs</th>
                    <th className="px-4 py-2 font-bold text-right">Overdue by</th>
                  </tr>
                </thead>
                <tbody>
                  {overdue.slice(0, 50).map((j) => (
                    <tr key={j.id} className="border-b border-red-100 hover:bg-red-100/60" data-testid={`overdue-row-${j.id}`}>
                      <td className="px-4 py-2 font-mono font-bold">{j.po_number}</td>
                      <td className="px-4 py-2 font-mono">{j.style_code}</td>
                      <td className="px-4 py-2">{j.color || "—"} · {j.size || "—"}</td>
                      <td className="px-4 py-2 uppercase font-bold" style={{ color: STAGE_COLORS[j.stage] }}>{STAGE_LABEL[j.stage] || j.stage}</td>
                      <td className="px-4 py-2 text-right font-mono">{j.quantity}</td>
                      <td className="px-4 py-2 text-right font-mono font-bold text-red-700">
                        {j.overdue_hours >= 24 ? `${(j.overdue_hours / 24).toFixed(1)} d` : `${j.overdue_hours.toFixed(1)} h`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {unmatchedStyles.length > 0 && (
          <Card className="bg-amber-50 border-2 border-amber-400 overflow-hidden" data-testid="unmatched-styles-banner">
            <div className="bg-amber-500 text-white px-5 py-2 flex items-baseline justify-between">
              <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-xs">
                <Wrench className="w-4 h-4" />
                {unmatchedStyles.reduce((s, g) => s + g.job_count, 0)} job{unmatchedStyles.reduce((s, g) => s + g.job_count, 0) !== 1 ? "s" : ""} with unresolved style code{unmatchedStyles.length !== 1 ? "s" : ""} — inventory will NOT be deducted
              </div>
              <Link to="/production" className="text-[10px] uppercase tracking-wider font-bold hover:underline flex items-center gap-1">
                Open production floor <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="px-5 py-3 space-y-2" data-testid="unmatched-styles-list">
              <p className="text-xs text-amber-800 font-medium mb-2">
                The following style codes don't match any entry in the Style Master. Fix them in
                {" "}<Link to="/styles" className="underline font-bold">Styles</Link> or correct the PO line items.
              </p>
              {unmatchedStyles.map((g) => (
                <div key={g.style_code} className="flex items-start gap-3 border border-amber-200 bg-white px-3 py-2" data-testid={`unmatched-${g.style_code}`}>
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono font-bold text-sm text-amber-900">{g.style_code}</span>
                      <span className="text-[10px] uppercase tracking-wider text-amber-700 font-bold">{g.job_count} job{g.job_count !== 1 ? "s" : ""}</span>
                    </div>
                    <div className="text-[11px] text-amber-700 mt-0.5">
                      {g.jobs.slice(0, 3).map((j) => `PO ${j.po_number} · ${j.color || "—"} · Sz ${j.size || "—"} · ${j.quantity} pairs`).join("   |   ")}
                      {g.jobs.length > 3 && <span className="italic"> + {g.jobs.length - 3} more</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile testId="stat-active-pos" label="Active POs" value={stats.total_pos} sub={`${stats.pending_pos} pending`} accent="#0F172A" />
          <StatTile testId="stat-wip" label="Pairs in WIP" value={stats.pairs_in_wip} sub="across all stages" accent="#C27842" />
          <StatTile testId="stat-dispatched" label="Dispatched" value={stats.dispatched} sub="lifetime pairs" accent="#16A34A" />
          <StatTile testId="stat-revenue" label="Order Value" value={inr(stats.revenue)} sub="cumulative" accent="#2563EB" />
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2 p-6">
            <div className="flex items-baseline justify-between mb-5">
              <h2 className="text-xl font-bold">Production Funnel</h2>
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Pairs by stage</span>
            </div>
            <div className="space-y-3" data-testid="production-funnel">
              {Object.entries(stats.stage_counts).map(([stage, count]) => (
                <div key={stage}>
                  <div className="flex items-baseline justify-between mb-1">
                    <span className="text-xs uppercase tracking-wider font-bold">{STAGE_LABEL[stage] || stage}</span>
                    <span className="font-mono text-sm font-bold">{count}</span>
                  </div>
                  <div className="h-6 bg-slate-100 relative overflow-hidden">
                    <div className="h-full transition-all"
                      style={{ width: `${(count / maxStage) * 100}%`, background: STAGE_COLORS[stage] || "#94A3B8" }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6">
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2"><Clock className="w-4 h-4 text-[#C27842]" /> Quick Stats</h2>
            <div className="space-y-3 text-sm">
              <Row label="Materials" value={stats.materials_count} />
              <Row label="Styles" value={stats.styles_count} />
              <Row label="Total POs" value={stats.total_pos} />
              <Row label="Pending POs" value={stats.pending_pos} />
              <Row label="Overdue Jobs" value={overdue.length} highlight={overdue.length > 0} />
            </div>
            <div className="mt-6 pt-4 border-t border-slate-200 space-y-2">
              <Link to="/pos" className="block text-xs uppercase tracking-wider font-bold text-[#2563EB] hover:underline">→ Manage Purchase Orders</Link>
              <Link to="/production" className="block text-xs uppercase tracking-wider font-bold text-[#C27842] hover:underline">→ View Production Board</Link>
              <Link to="/reports" className="block text-xs uppercase tracking-wider font-bold text-[#16A34A] hover:underline">→ View Visual Reports</Link>
            </div>
          </Card>
        </div>

        <Card className="overflow-hidden">
          <div className="px-6 py-4 border-b-2 border-slate-200 flex items-baseline justify-between">
            <h2 className="text-xl font-bold">Recent Purchase Orders</h2>
            <Link to="/pos" className="text-xs uppercase tracking-wider font-bold text-slate-600 hover:text-[#C27842]">View all →</Link>
          </div>
          <table className="w-full text-sm" data-testid="recent-pos-table">
            <thead className="bg-slate-50 border-b-2 border-slate-200">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-6 py-3 font-bold">PO #</th>
                <th className="px-6 py-3 font-bold">Client</th>
                <th className="px-6 py-3 font-bold text-right">Qty</th>
                <th className="px-6 py-3 font-bold text-right">Value</th>
                <th className="px-6 py-3 font-bold">Delivery</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_pos.length === 0 ? (
                <tr><td colSpan="5" className="px-6 py-10 text-center text-slate-400">No purchase orders yet. Upload your first PO from the Purchase Orders module.</td></tr>
              ) : stats.recent_pos.map((po) => (
                <tr key={po.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="px-6 py-3 font-mono font-bold">{po.po_number}</td>
                  <td className="px-6 py-3">{po.client_name}</td>
                  <td className="px-6 py-3 text-right font-mono">{po.total_quantity}</td>
                  <td className="px-6 py-3 text-right font-mono font-bold">{inr(po.grand_total)}</td>
                  <td className="px-6 py-3 text-xs text-slate-600">{po.delivery_date || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, highlight = false }) {
  return (
    <div className="flex items-baseline justify-between border-b border-dashed border-slate-200 pb-2">
      <span className="text-xs uppercase tracking-wider text-slate-500 font-bold">{label}</span>
      <span className={`font-mono font-bold ${highlight ? "text-red-600 text-lg" : ""}`}>{value}</span>
    </div>
  );
}
