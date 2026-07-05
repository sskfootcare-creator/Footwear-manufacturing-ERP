import { useEffect, useState, useMemo } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, StatTile, Card, BtnSecondary } from "../components/ui-kit";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";
import {
  AlertTriangle, Clock, ArrowRight, Receipt, Wrench,
  Factory, ShoppingBag, BarChart3, Database, Calendar
} from "lucide-react";

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

  const workspace = localStorage.getItem("workspace") || "management";
  const [dashTab, setDashTab] = useState(workspace === "management" ? "consolidated" : workspace);

  // Sync tab if workspace changes
  useEffect(() => {
    setDashTab(workspace === "management" ? "consolidated" : workspace);
  }, [workspace]);

  useEffect(() => {
    http.get("/dashboard/stats").then((r) => setStats(r.data)).catch(() => {});
    http.get("/dashboard/overdue").then((r) => setOverdue(r.data || [])).catch(() => {});
    http.get("/invoices/overdue").then((r) => setOverdueInvoices(r.data || [])).catch(() => {});
    http.get("/production/unmatched-styles").then((r) => setUnmatchedStyles(r.data || [])).catch(() => {});
  }, []);

  const seedDemo = async () => {
    try { await http.post("/seed/demo"); window.location.reload(); } catch {}
  };

  const currentStageCounts = useMemo(() => {
    if (!stats) return {};
    if (dashTab === "consolidated") return stats.stage_counts;
    if (dashTab === "b2b") return stats.b2b.stage_counts;
    return stats.online.stage_counts;
  }, [stats, dashTab]);

  if (!stats) return <div className="p-8 text-sm text-slate-500">Loading factory data...</div>;

  const maxStage = Math.max(...Object.values(currentStageCounts), 1);

  return (
    <div>
      <PageHeader
        title={workspace === "management" ? "Management Control Room" : `${workspace === "b2b" ? "B2B Manufacturing" : "Online Commerce"} Console`}
        subtitle="Dashboard"
        testId="dashboard-header"
        action={
          user?.role === "admin" && stats.materials_count === 0 ? (
            <BtnSecondary onClick={seedDemo} data-testid="seed-demo-btn">Seed demo materials</BtnSecondary>
          ) : (
            <div className="flex items-center gap-2 text-xs text-slate-500 uppercase tracking-wider font-bold">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              <span>{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", year: "numeric" })}</span>
            </div>
          )
        }
      />

      {/* Management Selector Tabs */}
      {workspace === "management" && (
        <div className="mx-4 sm:mx-8 mt-4 bg-white border-b-2 border-slate-200 flex px-4">
          {[
            { id: "consolidated", label: "Consolidated Overview", icon: BarChart3 },
            { id: "b2b", label: "B2B Manufacturing", icon: Factory },
            { id: "online", label: "Online Commerce", icon: ShoppingBag }
          ].map((t) => {
            const Icon = t.icon;
            const active = dashTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setDashTab(t.id)}
                className={`flex items-center gap-2 px-5 py-3.5 text-xs uppercase tracking-wider font-bold border-b-4 -mb-[2px] transition-colors ${
                  active
                    ? "border-[#C27842] text-slate-900 font-extrabold"
                    : "border-transparent text-slate-400 hover:text-slate-600"
                }`}
                data-testid={`dash-tab-${t.id}`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      )}

      <div className="p-4 sm:p-8 space-y-6">
        
        {/* Overdue B2B Invoices - Hide on online tab */}
        {dashTab !== "online" && overdueInvoices.length > 0 && (
          <Card className="bg-red-50 border-2 border-red-300 px-5 py-3 flex items-center justify-between" data-testid="overdue-invoices-banner">
            <div className="flex items-center gap-3">
              <Receipt className="w-5 h-5 text-red-600" />
              <div>
                <div className="font-bold text-red-700 text-sm">
                  {overdueInvoices.length} overdue payment{overdueInvoices.length > 1 ? "s" : ""} · {inr(overdueInvoices.reduce((s, r) => s + (r.outstanding || 0), 0))} receivable
                </div>
                <div className="text-xs text-red-600">B2B invoice terms exceeded — review and chase up.</div>
              </div>
            </div>
            <Link to="/invoices" className="text-xs uppercase tracking-wider font-bold text-red-700 hover:underline">Open invoices →</Link>
          </Card>
        )}

        {/* Unmatched Styles (SKU mapping alert) - Show only on online / consolidated */}
        {dashTab !== "b2b" && unmatchedStyles.length > 0 && (
          <Card className="bg-amber-50 border-2 border-amber-400 overflow-hidden" data-testid="unmatched-styles-banner">
            <div className="bg-amber-500 text-white px-5 py-2 flex items-baseline justify-between">
              <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-xs">
                <Wrench className="w-4 h-4" />
                {unmatchedStyles.reduce((s, g) => s + g.job_count, 0)} job{unmatchedStyles.reduce((s, g) => s + g.job_count, 0) !== 1 ? "s" : ""} with unresolved style code{unmatchedStyles.length !== 1 ? "s" : ""} — inventory will NOT be deducted
              </div>
              <Link to="/sku-map" className="text-[10px] uppercase tracking-wider font-bold hover:underline flex items-center gap-1">
                Open SKU Mapping <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="px-5 py-3 space-y-2" data-testid="unmatched-styles-list">
              <p className="text-xs text-amber-800 font-medium mb-2">
                The following style codes don't match any entry in the Style Master. Fix them in
                {" "}<Link to="/sku-map" className="underline font-bold">SKU Mapping</Link> to resolve jobs automatically.
              </p>
              {unmatchedStyles.slice(0, 3).map((g) => (
                <div key={g.style_code} className="flex items-start gap-3 border border-amber-200 bg-white px-3 py-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono font-bold text-sm text-amber-900">{g.style_code}</span>
                      <span className="text-[10px] uppercase tracking-wider text-amber-700 font-bold">{g.job_count} job{g.job_count !== 1 ? "s" : ""}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Overdue B2B jobs alert - Hide on online */}
        {dashTab !== "online" && overdue.length > 0 && (
          <Card className="bg-red-50 border-2 border-red-300 overflow-hidden" data-testid="overdue-alert-banner">
            <div className="bg-red-600 text-white px-5 py-2 flex items-baseline justify-between">
              <div className="flex items-center gap-2 font-bold uppercase tracking-wider text-xs">
                <AlertTriangle className="w-4 h-4" /> {overdue.length} Overdue Production Task{overdue.length > 1 ? "s" : ""}
              </div>
              <Link to="/production" className="text-[10px] uppercase tracking-wider font-bold hover:underline flex items-center gap-1">
                Open production floor <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="max-h-52 overflow-auto">
              <table className="w-full text-xs">
                <tbody>
                  {overdue.slice(0, 5).map((j) => (
                    <tr key={j.id} className="border-b border-red-100 hover:bg-red-100/60">
                      <td className="px-4 py-2 font-mono font-bold">{j.po_number}</td>
                      <td className="px-4 py-2 font-mono">{j.style_code}</td>
                      <td className="px-4 py-2 text-right font-mono">{j.quantity} pairs</td>
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

        {/* ── Stat Tiles ────────────────────────────────────────── */}
        {dashTab === "consolidated" && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatTile label="Grand Total Revenue" value={inr(stats.revenue)} sub="B2B + Online Commerce" accent="#0F172A" />
            <StatTile label="Total WIP Pairs" value={stats.pairs_in_wip} sub="across both branches" accent="#C27842" />
            <StatTile label="Active Styles" value={stats.styles_count} sub="available in catalog" accent="#16A34A" />
            <StatTile label="Materials Count" value={stats.materials_count} sub="raw materials registered" accent="#2563EB" />
          </div>
        )}

        {dashTab === "b2b" && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatTile label="B2B Grand Total" value={inr(stats.b2b.revenue)} sub="from B2B POs" accent="#0F172A" />
            <StatTile label="B2B WIP Pairs" value={stats.b2b.wip} sub="active on production floor" accent="#C27842" />
            <StatTile label="Dispatched Pairs" value={stats.b2b.dispatched} sub="lifetime B2B delivery" accent="#16A34A" />
            <StatTile label="Active Purchase Orders" value={stats.b2b.total_pos} sub={`${stats.b2b.pending_pos} pending`} accent="#2563EB" />
          </div>
        )}

        {dashTab === "online" && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatTile label="Online Grand Total" value={inr(stats.online.revenue)} sub="from marketplace CSVs" accent="#0F172A" />
            <StatTile label="Online WIP Pairs" value={stats.online.wip} sub="active online orders" accent="#C27842" />
            <StatTile label="Dispatched Pairs" value={stats.online.dispatched} sub="fulfilled marketplace shipments" accent="#16A34A" />
            <StatTile label="Total Import Rows" value={stats.online.total_qty} sub={`${stats.online.total_orders} imported orders`} accent="#2563EB" />
          </div>
        )}

        {/* ── Consolidated Branch Breakdown ────────────────────────── */}
        {dashTab === "consolidated" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="p-5 border-l-4 border-blue-500">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 mb-4 flex items-center gap-1.5">
                <Factory className="w-4 h-4 text-blue-500" /> B2B Manufacturing Branch
              </h3>
              <div className="space-y-2.5">
                <Row label="B2B Order Value" value={inr(stats.b2b.revenue)} />
                <Row label="WIP Pairs" value={`${stats.b2b.wip} pairs`} />
                <Row label="Dispatched Pairs" value={`${stats.b2b.dispatched} pairs`} />
                <Row label="Active Purchase Orders" value={`${stats.b2b.total_pos} POs (${stats.b2b.pending_pos} pending)`} />
              </div>
            </Card>

            <Card className="p-5 border-l-4 border-pink-500">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500 mb-4 flex items-center gap-1.5">
                <ShoppingBag className="w-4 h-4 text-pink-500" /> Online Commerce Branch
              </h3>
              <div className="space-y-2.5">
                <Row label="Online Order Value" value={inr(stats.online.revenue)} />
                <Row label="WIP Pairs" value={`${stats.online.wip} pairs`} />
                <Row label="Fulfilled Pairs" value={`${stats.online.dispatched} pairs`} />
                <Row label="Total Ingested Orders" value={`${stats.online.total_orders} orders`} />
              </div>
            </Card>
          </div>
        )}

        {/* ── Funnel & Side Panels ───────────────────────────────── */}
        <div className="grid lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2 p-4 sm:p-6">
            <div className="flex items-baseline justify-between mb-5">
              <h2 className="text-lg sm:text-xl font-bold">Production Funnel</h2>
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Pairs by stage</span>
            </div>
            <div className="space-y-3" data-testid="production-funnel">
              {Object.entries(currentStageCounts).map(([stage, count]) => (
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

          <Card className="p-4 sm:p-6">
            <h2 className="text-lg sm:text-xl font-bold mb-4 flex items-center gap-2"><Clock className="w-4 h-4 text-[#C27842]" /> Quick Stats</h2>
            <div className="space-y-3 text-sm">
              <Row label="Materials Count" value={stats.materials_count} />
              <Row label="Styles Registered" value={stats.styles_count} />
              {dashTab !== "online" && (
                <>
                  <Row label="Total B2B POs" value={stats.total_pos} />
                  <Row label="Overdue B2B Tasks" value={overdue.length} highlight={overdue.length > 0} />
                </>
              )}
              {dashTab !== "b2b" && (
                <>
                  <Row label="Online Orders Count" value={stats.online.total_orders} />
                  <Row label="Online Ingested Pairs" value={stats.online.total_qty} />
                </>
              )}
            </div>
            <div className="mt-6 pt-4 border-t border-slate-200 space-y-2">
              <Link to="/pos" className="block text-xs uppercase tracking-wider font-bold text-[#2563EB] hover:underline">→ Manage Purchase Orders</Link>
              <Link to="/production" className="block text-xs uppercase tracking-wider font-bold text-[#C27842] hover:underline">→ View Production Board</Link>
              <Link to="/reports" className="block text-xs uppercase tracking-wider font-bold text-[#16A34A] hover:underline">→ View Visual Reports</Link>
            </div>
          </Card>
        </div>

        {/* ── Recent Tables Split ────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-6">
          {/* Recent POs - Show on consolidated / b2b */}
          {dashTab !== "online" && (
            <Card className="overflow-hidden">
              <div className="px-4 sm:px-6 py-4 border-b-2 border-slate-200 flex items-baseline justify-between bg-slate-50">
                <h2 className="text-lg sm:text-xl font-bold text-slate-800">Recent Purchase Orders (B2B)</h2>
                <Link to="/pos" className="text-xs uppercase tracking-wider font-bold text-slate-600 hover:text-[#C27842]">View all →</Link>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="recent-pos-table">
                  <thead className="bg-slate-100 border-b border-slate-200">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                      <th className="px-6 py-3 font-bold">PO #</th>
                      <th className="px-6 py-3 font-bold">Client</th>
                      <th className="px-6 py-3 font-bold text-right">Qty</th>
                      <th className="px-6 py-3 font-bold text-right">Value</th>
                      <th className="px-6 py-3 font-bold">Delivery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.b2b.recent_pos.length === 0 ? (
                      <tr><td colSpan="5" className="px-6 py-10 text-center text-slate-400">No purchase orders yet.</td></tr>
                    ) : stats.b2b.recent_pos.map((po) => (
                      <tr key={po.id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-6 py-3 font-mono font-bold text-slate-700">{po.po_number}</td>
                        <td className="px-6 py-3">{po.client_name}</td>
                        <td className="px-6 py-3 text-right font-mono">{po.total_quantity}</td>
                        <td className="px-6 py-3 text-right font-mono font-bold text-slate-800">{inr(po.grand_total)}</td>
                        <td className="px-6 py-3 text-xs text-slate-600">{po.delivery_date || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Recent Online Orders - Show on consolidated / online */}
          {dashTab !== "b2b" && (
            <Card className="overflow-hidden">
              <div className="px-4 sm:px-6 py-4 border-b-2 border-slate-200 flex items-baseline justify-between bg-slate-50">
                <h2 className="text-lg sm:text-xl font-bold text-slate-800">Recent Marketplace Orders (Online)</h2>
                <Link to="/online-orders" className="text-xs uppercase tracking-wider font-bold text-slate-600 hover:text-[#C27842]">View all →</Link>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-100 border-b border-slate-200">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                      <th className="px-6 py-3 font-bold">Order ID</th>
                      <th className="px-6 py-3 font-bold">Channel</th>
                      <th className="px-6 py-3 font-bold">Style</th>
                      <th className="px-6 py-3 font-bold text-right">Qty</th>
                      <th className="px-6 py-3 font-bold text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.online.recent_orders.length === 0 ? (
                      <tr><td colSpan="5" className="px-6 py-10 text-center text-slate-400">No online orders imported yet.</td></tr>
                    ) : stats.online.recent_orders.map((ord) => (
                      <tr key={ord.id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-6 py-3 font-mono font-bold text-slate-700">{ord.po_number}</td>
                        <td className="px-6 py-3 uppercase text-xs font-semibold text-slate-600">{ord.channel}</td>
                        <td className="px-6 py-3 font-mono text-xs">{ord.style_code} ({ord.color} · Sz {ord.size})</td>
                        <td className="px-6 py-3 text-right font-mono">{ord.quantity}</td>
                        <td className="px-6 py-3 text-right font-mono font-bold text-slate-800">{inr(ord.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>

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
