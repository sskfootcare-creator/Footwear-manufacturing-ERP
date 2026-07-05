import { useEffect, useState, useCallback } from "react";
import { http, inr, num } from "../lib/api";
import { PageHeader, Card, Badge } from "../components/ui-kit";
import {
  TrendingUp,
  Clock,
  AlertOctagon,
  BarChart3,
  Users as UsersIcon,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const PALETTE = [
  "#C27842",
  "#2563EB",
  "#16A34A",
  "#7C3AED",
  "#F59E0B",
  "#DC2626",
  "#0EA5E9",
  "#A65D24",
];
const STAGE_LABEL = {
  procurement: "Procurement",
  cutting: "Cutting",
  folding: "Folding",
  attachment: "Attachment",
  stitching: "Stitching",
  lasting: "Lasting",
  sole_pasting: "Sole Pasting",
  finishing: "Finishing",
  dispatched: "Dispatched",
};

const fmtMonth = (m) => {
  if (!m) return "";
  const [y, mo] = m.split("-");
  const d = new Date(Number(y), Number(mo) - 1, 1);
  return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
};

export default function Reports() {
  const [tab, setTab] = useState("monthly");
  const [monthly, setMonthly] = useState([]);
  const [karigar, setKarigar] = useState([]);
  const [variance, setVariance] = useState([]);
  const [cycle, setCycle] = useState([]);
  const [defects, setDefects] = useState(null);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const load = useCallback(async () => {
    const params = {};
    if (fromDate) params.from_date = fromDate;
    if (toDate) params.to_date = toDate;

    try {
      const [monthlyRes, karigarRes, varianceRes, cycleRes, defectsRes] =
        await Promise.all([
          http.get("/reports/monthly-production", { params }),
          http.get("/reports/karigar-output", { params }),
          http.get("/reports/cost-variance", { params }),
          http.get("/reports/stage-cycle-time", { params }),
          http.get("/reports/defect-rate", { params }),
        ]);
      setMonthly(monthlyRes.data || []);
      setKarigar(karigarRes.data || []);
      setVariance(varianceRes.data || []);
      setCycle(cycleRes.data || []);
      setDefects(defectsRes.data);
    } catch (e) {
      console.error(e);
    }
  }, [fromDate, toDate]);

  useEffect(() => {
    load();
  }, [load]);

  const tabs = [
    { key: "monthly", label: "Production Trend", icon: TrendingUp },
    { key: "karigar", label: "Karigar Output", icon: UsersIcon },
    { key: "variance", label: "Cost Variance", icon: BarChart3 },
    { key: "cycle", label: "Cycle Time", icon: Clock },
    { key: "defects", label: "Defect Analytics", icon: AlertOctagon },
  ];

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Analytics / Visual Reports"
        testId="reports-header"
        action={null}
      />
      <div className="p-4 sm:p-8 space-y-4">
        <div className="flex flex-wrap gap-2 items-center bg-white p-4 border-2 border-slate-200 justify-between">
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
            <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500 w-full sm:w-auto">
              Filter Period :
            </span>
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="border border-slate-300 px-2 py-1 text-xs focus:border-[#C27842] focus:outline-none w-full sm:w-auto font-mono"
                data-testid="report-from-date"
              />
              <span className="text-slate-400 text-xs">—</span>
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="border border-slate-300 px-2 py-1 text-xs focus:border-[#C27842] focus:outline-none w-full sm:w-auto font-mono"
                data-testid="report-to-date"
              />
              {(fromDate || toDate) && (
                <button
                  onClick={() => {
                    setFromDate("");
                    setToDate("");
                  }}
                  className="text-xs font-bold uppercase tracking-wider text-red-600 hover:text-red-800 ml-2"
                  data-testid="report-clear-dates"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="flex border-b-2 border-slate-200 mb-6 overflow-y-hidden overflow-x-auto no-scrollbar">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              data-testid={`tab-${t.key}`}
              className={`px-5 py-3 text-xs font-bold uppercase tracking-wider border-b-4 -mb-0.5 transition-colors flex items-center gap-2 whitespace-nowrap ${
                tab === t.key
                  ? "border-[#C27842] text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-900"
              }`}
            >
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>

        {tab === "monthly" && <MonthlyReport rows={monthly} />}
        {tab === "karigar" && <KarigarReport rows={karigar} />}
        {tab === "variance" && <VarianceReport rows={variance} />}
        {tab === "cycle" && <CycleReport rows={cycle} />}
        {tab === "defects" && <DefectReport data={defects} />}
      </div>
    </div>
  );
}

/* ------------------------------- MONTHLY ------------------------------- */
function MonthlyReport({ rows }) {
  if (!rows.length)
    return (
      <Empty label="No production data yet — process some POs to see monthly trends." />
    );
  const chartData = rows.map((r) => ({ ...r, month: fmtMonth(r.month) }));
  const totalStarted = rows.reduce((s, r) => s + (r.started || 0), 0);
  const totalDispatched = rows.reduce((s, r) => s + (r.dispatched || 0), 0);
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Stat label="Months Tracked" value={rows.length} />
        <Stat
          label="Total Started"
          value={totalStarted.toLocaleString("en-IN")}
        />
        <Stat
          label="Total Dispatched"
          value={totalDispatched.toLocaleString("en-IN")}
          accent="#16A34A"
        />
      </div>
      <Card className="p-6">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-4">
          Pairs · Started vs Dispatched · last {rows.length} month(s)
        </h2>
        <div className="w-full h-80" data-testid="monthly-chart">
          <ResponsiveContainer>
            <LineChart
              data={chartData}
              margin={{ top: 5, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
              />
              <Legend
                wrapperStyle={{
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                }}
              />
              <Line
                type="monotone"
                dataKey="started"
                stroke="#C27842"
                strokeWidth={2.5}
                dot={{ r: 4 }}
                name="Started"
              />
              <Line
                type="monotone"
                dataKey="dispatched"
                stroke="#16A34A"
                strokeWidth={2.5}
                dot={{ r: 4 }}
                name="Dispatched"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------- KARIGAR ------------------------------- */
function KarigarReport({ rows }) {
  if (!rows.length)
    return <Empty label="No karigar output for current month yet." />;
  const top = rows.slice(0, 10);
  const totalPairs = rows.reduce((s, r) => s + (r.pairs || 0), 0);
  const totalEarnings = rows.reduce((s, r) => s + (r.earnings || 0), 0);
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Stat
          label="Active Karigars"
          value={rows.filter((r) => r.pairs > 0).length}
        />
        <Stat
          label="Total Pairs Produced"
          value={totalPairs.toLocaleString("en-IN")}
        />
        <Stat
          label="Total Wages Earned"
          value={inr(totalEarnings)}
          accent="#C27842"
        />
      </div>
      <Card className="p-6">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-4">
          Top 10 Karigars by Output (pairs · current month)
        </h2>
        <div className="w-full h-96" data-testid="karigar-output-chart">
          <ResponsiveContainer>
            <BarChart
              data={top}
              layout="vertical"
              margin={{ top: 5, right: 24, left: 60, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 11, fontWeight: 700 }}
                width={100}
              />
              <Tooltip
                contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
                formatter={(v, n) => (n === "earnings" ? inr(v) : v)}
              />
              <Bar dataKey="pairs" fill="#C27842" name="Pairs" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------- VARIANCE ------------------------------- */
function VarianceReport({ rows }) {
  if (!rows.length)
    return (
      <Empty label="No variance data — add Styles and POs to see cost variance." />
    );
  // Top 10 worst margins
  const worst = rows
    .slice(0, 10)
    .map((r) => ({ ...r, label: `${r.style_code} · ${r.po_number}` }));
  const profitable = rows.filter((r) => r.margin_pct > 0).length;
  const losing = rows.filter((r) => r.margin_pct < 0).length;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Stat label="PO Line Items" value={rows.length} />
        <Stat label="Profitable" value={profitable} accent="#16A34A" />
        <Stat label="Loss-Making" value={losing} accent="#DC2626" />
      </div>
      <Card className="p-6">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-4">
          Margin % · 10 worst-performing PO line items
        </h2>
        <div className="w-full h-80" data-testid="variance-chart">
          <ResponsiveContainer>
            <BarChart
              data={worst}
              margin={{ top: 5, right: 16, left: 0, bottom: 60 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10 }}
                angle={-25}
                textAnchor="end"
                interval={0}
                height={70}
              />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip
                contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
                formatter={(v) => `${num(v, 1)}%`}
              />
              <Bar dataKey="margin_pct" name="Margin %">
                {worst.map((r, i) => (
                  <Cell
                    key={i}
                    fill={
                      r.margin_pct < 0
                        ? "#DC2626"
                        : r.margin_pct < 10
                          ? "#F59E0B"
                          : "#16A34A"
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card className="overflow-hidden">
        <div className="px-5 py-3 border-b-2 border-slate-200">
          <h2 className="text-sm font-bold uppercase tracking-wider">
            Detailed table
          </h2>
        </div>
        <table className="w-full text-sm" data-testid="variance-table">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
              <th className="px-4 py-2 font-bold">PO</th>
              <th className="px-4 py-2 font-bold">Client</th>
              <th className="px-4 py-2 font-bold">Style</th>
              <th className="px-4 py-2 font-bold text-right">Qty</th>
              <th className="px-4 py-2 font-bold text-right">Computed</th>
              <th className="px-4 py-2 font-bold text-right">PO Price</th>
              <th className="px-4 py-2 font-bold text-right">Margin %</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const color =
                r.margin_pct < 0
                  ? "red"
                  : r.margin_pct < 10
                    ? "yellow"
                    : "green";
              return (
                <tr
                  key={i}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-4 py-2 font-mono text-xs font-bold">
                    {r.po_number}
                  </td>
                  <td className="px-4 py-2 text-xs">{r.client}</td>
                  <td className="px-4 py-2 font-mono text-xs">
                    {r.style_code}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {r.quantity}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {inr(r.computed_cost)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {inr(r.po_unit_price)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Badge color={color}>{num(r.margin_pct, 1)}%</Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ------------------------------- CYCLE TIME ------------------------------- */
function CycleReport({ rows }) {
  if (!rows.length)
    return (
      <Empty label="No cycle-time data yet — move production jobs across stages to populate." />
    );
  const chartData = rows.map((r) => ({
    label: `${r.from_stage} → ${r.to_stage}`,
    avg: r.avg_hours,
    samples: r.samples,
  }));
  return (
    <div className="space-y-5">
      <Card className="p-6">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-4">
          Avg hours between stage transitions
        </h2>
        <div className="w-full h-80" data-testid="cycle-chart">
          <ResponsiveContainer>
            <BarChart
              data={chartData}
              margin={{ top: 5, right: 16, left: 0, bottom: 70 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10 }}
                angle={-25}
                textAnchor="end"
                interval={0}
                height={80}
              />
              <YAxis tick={{ fontSize: 11 }} unit="h" />
              <Tooltip
                contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
                formatter={(v) => `${num(v, 1)} hrs`}
              />
              <Bar dataKey="avg" name="Avg Hours" fill="#2563EB" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card className="overflow-hidden">
        <div className="px-5 py-3 border-b-2 border-slate-200">
          <h2 className="text-sm font-bold uppercase tracking-wider">
            Per-transition stats
          </h2>
        </div>
        <table className="w-full text-sm" data-testid="cycle-table">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
              <th className="px-4 py-2 font-bold">From</th>
              <th className="px-4 py-2 font-bold">To</th>
              <th className="px-4 py-2 font-bold text-right">Samples</th>
              <th className="px-4 py-2 font-bold text-right">Avg (hrs)</th>
              <th className="px-4 py-2 font-bold text-right">Min</th>
              <th className="px-4 py-2 font-bold text-right">Max</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={i}
                className="border-b border-slate-100 hover:bg-slate-50"
              >
                <td className="px-4 py-2 uppercase text-xs">{r.from_stage}</td>
                <td className="px-4 py-2 uppercase text-xs">→ {r.to_stage}</td>
                <td className="px-4 py-2 text-right font-mono">{r.samples}</td>
                <td className="px-4 py-2 text-right font-mono font-bold">
                  {num(r.avg_hours, 1)}
                </td>
                <td className="px-4 py-2 text-right font-mono text-slate-500">
                  {num(r.min_hours, 1)}
                </td>
                <td className="px-4 py-2 text-right font-mono text-slate-500">
                  {num(r.max_hours, 1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ------------------------------- DEFECTS ------------------------------- */
function DefectReport({ data }) {
  if (!data) return <Empty label="Loading defect data..." />;
  if (!data.totals.total_incidents)
    return <Empty label="No defects logged. Quality is clean." />;
  const byTypePie = data.by_type.map((r) => ({
    name: r.type,
    value: r.defective,
  }));
  const byStageBar = data.by_stage.map((r) => ({
    stage: STAGE_LABEL[r.stage] || r.stage,
    rate: r.defect_rate_pct,
    defective: r.defective_qty,
  }));
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Stat label="Total Incidents" value={data.totals.total_incidents} />
        <Stat
          label="Total Defective Pairs"
          value={data.totals.total_defective}
          accent="#DC2626"
        />
        <Stat
          label="Total Cost"
          value={inr(data.totals.total_cost)}
          accent="#C27842"
        />
      </div>
      <div className="grid lg:grid-cols-2 gap-5">
        <Card className="p-6">
          <h2 className="text-sm font-bold uppercase tracking-wider mb-4">
            Defect rate % by stage
          </h2>
          <div className="w-full h-72" data-testid="defect-stage-chart">
            <ResponsiveContainer>
              <BarChart
                data={byStageBar}
                margin={{ top: 5, right: 16, left: 0, bottom: 40 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis
                  dataKey="stage"
                  tick={{ fontSize: 10 }}
                  angle={-20}
                  textAnchor="end"
                  interval={0}
                  height={50}
                />
                <YAxis tick={{ fontSize: 11 }} unit="%" />
                <Tooltip
                  contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
                  formatter={(v) => `${num(v, 2)}%`}
                />
                <Bar dataKey="rate" name="Defect %">
                  {byStageBar.map((r, i) => (
                    <Cell
                      key={i}
                      fill={
                        r.rate > 5
                          ? "#DC2626"
                          : r.rate > 2
                            ? "#F59E0B"
                            : "#16A34A"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="p-6">
          <h2 className="text-sm font-bold uppercase tracking-wider mb-4">
            Defective pairs by type
          </h2>
          <div className="w-full h-72" data-testid="defect-type-chart">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={byTypePie}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={(e) => e.name}
                >
                  {byTypePie.map((_, i) => (
                    <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Card className="overflow-hidden">
        <div className="px-5 py-3 border-b-2 border-slate-200">
          <h2 className="text-sm font-bold uppercase tracking-wider">
            By stage
          </h2>
        </div>
        <table className="w-full text-sm" data-testid="defect-stage-table">
          <thead className="bg-slate-50">
            <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600 border-b border-slate-200">
              <th className="px-4 py-2 font-bold">Stage</th>
              <th className="px-4 py-2 font-bold text-right">Defective</th>
              <th className="px-4 py-2 font-bold text-right">Rework</th>
              <th className="px-4 py-2 font-bold text-right">Rejected</th>
              <th className="px-4 py-2 font-bold text-right">Cost</th>
              <th className="px-4 py-2 font-bold text-right">Defect %</th>
            </tr>
          </thead>
          <tbody>
            {data.by_stage.map((r, i) => (
              <tr
                key={i}
                className="border-b border-slate-100 hover:bg-slate-50"
              >
                <td className="px-4 py-2 uppercase text-xs font-bold">
                  {r.stage}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {r.defective_qty}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {r.rework_qty}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {r.rejected_qty}
                </td>
                <td className="px-4 py-2 text-right font-mono">
                  {inr(r.cost)}
                </td>
                <td className="px-4 py-2 text-right">
                  <Badge
                    color={
                      r.defect_rate_pct > 5
                        ? "red"
                        : r.defect_rate_pct > 2
                          ? "yellow"
                          : "green"
                    }
                  >
                    {num(r.defect_rate_pct, 2)}%
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Stat({ label, value, accent = "#0F172A" }) {
  return (
    <Card className="p-3 sm:p-5 relative overflow-hidden">
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate">
        {label}
      </div>
      <div className="font-mono text-lg sm:text-2xl font-bold mt-1 sm:mt-2 truncate" title={String(value)}>{value}</div>
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ background: accent }}
      />
    </Card>
  );
}

function Empty({ label }) {
  return (
    <Card className="p-12 text-center text-slate-400 text-sm">{label}</Card>
  );
}
