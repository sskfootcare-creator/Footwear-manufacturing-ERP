import { useEffect, useState } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, Card, StatTile, BtnSecondary, Select, Badge } from "../components/ui-kit";
import { BarChart3, RefreshCw, Boxes, Timer, TrendingUp } from "lucide-react";

const TABS = [
  { key: "capacity", label: "Capacity",             icon: Boxes },
  { key: "utilization", label: "Location Utilization", icon: BarChart3 },
  { key: "picking",  label: "Picking Efficiency",    icon: Timer },
];

export default function WarehouseReports() {
  const [tab, setTab] = useState("capacity");
  return (
    <div data-testid="page-warehouse-reports">
      <PageHeader title="Warehouse Reports" subtitle="Online Commerce / WMS" />
      <div className="p-4 sm:p-6">
        <div className="flex gap-1 border-b-2 border-slate-200 mb-4 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-bold uppercase tracking-wider whitespace-nowrap border-b-4 -mb-0.5 transition-colors flex items-center gap-1 ${tab === t.key ? "border-[#C27842] text-[#0F172A]" : "border-transparent text-slate-500 hover:text-slate-900"}`}>
              <t.icon className="w-3.5 h-3.5" />{t.label}
            </button>
          ))}
        </div>
        {tab === "capacity"    && <CapacityReport />}
        {tab === "utilization" && <LocationUtilizationReport />}
        {tab === "picking"     && <PickingEfficiencyReport />}
      </div>
    </div>
  );
}

function CapacityReport() {
  const [data, setData] = useState(null);
  const [err, setErr]   = useState("");
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true); setErr("");
    try { const r = await http.get("/warehouse/reports/capacity"); setData(r.data); }
    catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  if (err) return <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm">{err}</div>;
  if (!data) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  return (
    <div className="space-y-4" data-testid="report-capacity">
      <div className="flex justify-end">
        <BtnSecondary onClick={load} disabled={loading}><RefreshCw className={`w-3.5 h-3.5 inline mr-1 ${loading ? "animate-spin" : ""}`} />Refresh</BtnSecondary>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatTile label="Total Cells" value={data.total_cells} accent="#0F172A" />
        <StatTile label="Capacity (pairs)" value={data.total_capacity.toLocaleString()} accent="#C27842" />
        <StatTile label="Occupied" value={data.total_occupied.toLocaleString()} accent="#F97316" />
        <StatTile label="Available" value={data.total_available.toLocaleString()} accent="#16A34A" />
        <StatTile label="Utilization" value={`${data.utilization_pct}%`} accent="#2563EB" />
      </div>

      <Card>
        <table className="w-full text-sm">
          <thead className="bg-slate-100 border-b-2 border-slate-200">
            <tr>
              <th className="text-left px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Rack</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Cells</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Capacity</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Occupied</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Available</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Utilization %</th>
              <th className="px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Bar</th>
            </tr>
          </thead>
          <tbody>
            {data.by_rack.map(r => (
              <tr key={r.rack} className="border-t border-slate-100">
                <td className="px-4 py-3 font-black text-lg">{r.rack}</td>
                <td className="px-4 py-3 text-right">{r.cells}</td>
                <td className="px-4 py-3 text-right">{r.capacity_pairs.toLocaleString()}</td>
                <td className="px-4 py-3 text-right font-bold">{r.occupied_pairs.toLocaleString()}</td>
                <td className="px-4 py-3 text-right">{r.available_pairs.toLocaleString()}</td>
                <td className="px-4 py-3 text-right"><Badge color={r.utilization_pct > 90 ? "red" : r.utilization_pct > 60 ? "orange" : r.utilization_pct > 0 ? "blue" : "slate"}>{r.utilization_pct}%</Badge></td>
                <td className="px-4 py-3 w-64">
                  <div className="h-3 bg-slate-200 relative overflow-hidden">
                    <div className="absolute inset-y-0 left-0 bg-[#C27842]" style={{ width: `${r.utilization_pct}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function LocationUtilizationReport() {
  const [data, setData] = useState(null);
  const [err, setErr]   = useState("");
  const [tab, setTab]   = useState("fullest");
  useEffect(() => {
    (async () => {
      try { const r = await http.get("/warehouse/reports/location-utilization"); setData(r.data); }
      catch (e) { setErr(friendlyAxiosError(e)); }
    })();
  }, []);
  if (err) return <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm">{err}</div>;
  if (!data) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  const rows = tab === "fullest" ? data.fullest : tab === "emptiest" ? data.emptiest : data.rows;

  return (
    <div className="space-y-4" data-testid="report-utilization">
      <div className="flex gap-2 justify-end">
        <BtnSecondary onClick={() => setTab("fullest")}  className={tab === "fullest"  ? "bg-slate-900 text-white border-slate-900" : ""}>Top 20 Fullest</BtnSecondary>
        <BtnSecondary onClick={() => setTab("emptiest")} className={tab === "emptiest" ? "bg-slate-900 text-white border-slate-900" : ""}>Top 20 Emptiest</BtnSecondary>
        <BtnSecondary onClick={() => setTab("all")}      className={tab === "all"      ? "bg-slate-900 text-white border-slate-900" : ""}>All 240</BtnSecondary>
      </div>
      <Card>
        <div className="overflow-auto max-h-[70vh]">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 border-b-2 border-slate-200 sticky top-0">
              <tr>
                <th className="text-left px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Location</th>
                <th className="text-left px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Rack</th>
                <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Row</th>
                <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Cell</th>
                <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Capacity</th>
                <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Occupied</th>
                <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Available</th>
                <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Util %</th>
                <th className="text-left px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.location_code} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-mono font-bold">{r.location_code}</td>
                  <td className="px-4 py-3">{r.rack}</td>
                  <td className="px-4 py-3 text-right">{r.row}</td>
                  <td className="px-4 py-3 text-right">{r.cell}</td>
                  <td className="px-4 py-3 text-right">{r.capacity_pairs}</td>
                  <td className="px-4 py-3 text-right font-bold">{r.occupied_pairs}</td>
                  <td className="px-4 py-3 text-right">{r.available_pairs}</td>
                  <td className="px-4 py-3 text-right">{r.utilization_pct}%</td>
                  <td className="px-4 py-3">
                    <Badge color={r.status === "full" ? "green" : r.status === "partial" ? "orange" : r.status === "blocked" ? "red" : "slate"}>{r.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function PickingEfficiencyReport() {
  const [data, setData] = useState(null);
  const [err, setErr]   = useState("");
  const [days, setDays] = useState(30);
  async function load(d) {
    try { const r = await http.get(`/warehouse/reports/picking-efficiency?days=${d}`); setData(r.data); }
    catch (e) { setErr(friendlyAxiosError(e)); }
  }
  useEffect(() => { load(days); }, [days]);

  if (err) return <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm">{err}</div>;
  if (!data) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  return (
    <div className="space-y-4" data-testid="report-picking">
      <div className="flex justify-end">
        <Select value={days} onChange={e => setDays(e.target.value)}>
          <option value={1}>Last 24h</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </Select>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Picklists Completed" value={data.grand_total.picklists} accent="#0F172A" />
        <StatTile label="Items Picked" value={data.grand_total.items} accent="#F97316" />
        <StatTile label="Pairs Picked" value={data.grand_total.qty} accent="#16A34A" />
        <StatTile label="Avg Time / Picklist" value={`${data.grand_total.avg_minutes_per_picklist} min`} sub={`${data.grand_total.items_per_hour} items/hr`} accent="#2563EB" />
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead className="bg-slate-100 border-b-2 border-slate-200">
            <tr>
              <th className="text-left px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Picker</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Picklists</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Items</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Pairs</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Total Minutes</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Avg / Picklist</th>
              <th className="text-right px-4 py-3 font-bold text-[10px] uppercase tracking-wider">Items / Hour</th>
            </tr>
          </thead>
          <tbody>
            {data.per_picker.length === 0 && (
              <tr><td colSpan={7} className="p-8 text-center text-slate-500">No completed picklists in this range.</td></tr>
            )}
            {data.per_picker.map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="px-4 py-3 font-mono">{r.picker}</td>
                <td className="px-4 py-3 text-right font-bold">{r.picklists}</td>
                <td className="px-4 py-3 text-right">{r.items}</td>
                <td className="px-4 py-3 text-right">{r.qty}</td>
                <td className="px-4 py-3 text-right">{r.total_minutes}</td>
                <td className="px-4 py-3 text-right">{r.avg_minutes_per_picklist} min</td>
                <td className="px-4 py-3 text-right">{r.items_per_hour}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
