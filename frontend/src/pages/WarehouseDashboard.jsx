import { useEffect, useState, useMemo } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, Card, StatTile, BtnSecondary, BtnPrimary, Badge, Input, Select } from "../components/ui-kit";
import { Warehouse, RefreshCw, Layers, PackageCheck, PackageOpen, Boxes, Search, X, QrCode, Lock, Unlock, RotateCcw } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useAuth } from "../lib/auth";
import { Link } from "react-router-dom";

const RACKS = ["A", "B", "C"];

const STATUS_COLOR = {
  empty:   "#E2E8F0",   // slate-200
  partial: "#FDBA74",   // orange-300
  full:    "#4ADE80",   // green-400
  blocked: "#F87171",   // red-400
};
const STATUS_TEXT = {
  empty: "text-slate-600",
  partial: "text-orange-900",
  full: "text-green-900",
  blocked: "text-red-900",
};

const ZONE_LABEL = {
  main:            "Main Zone",
  return_holding:  "Return Holding",
};

export default function WarehouseDashboard() {
  const [dash, setDash]           = useState(null);
  const [locations, setLocations] = useState([]);
  const [selectedRack, setSelectedRack] = useState("A");
  const [zoneFilter, setZoneFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch]       = useState("");
  const [loading, setLoading]     = useState(false);
  const [err, setErr]             = useState("");
  const [selectedCell, setSelectedCell] = useState(null);

  async function load() {
    setLoading(true); setErr("");
    try {
      const [d, l] = await Promise.all([
        http.get("/warehouse/dashboard"),
        http.get("/warehouse/locations"),
      ]);
      setDash(d.data);
      setLocations(l.data);
    } catch (e) {
      setErr(friendlyAxiosError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    let out = locations;
    if (selectedRack) out = out.filter(l => l.rack === selectedRack);
    if (zoneFilter)   out = out.filter(l => (l.zone || "main") === zoneFilter);
    if (statusFilter) out = out.filter(l => l.status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      out = out.filter(l => l.location_code.toLowerCase().includes(q));
    }
    return out;
  }, [locations, selectedRack, zoneFilter, statusFilter, search]);

  // Build a 10x8 grid for the selected rack
  const grid = useMemo(() => {
    const rows = [];
    for (let r = 1; r <= 10; r++) {
      const row = [];
      for (let c = 1; c <= 8; c++) {
        const cell = filtered.find(l => l.rack === selectedRack && l.row === r && l.column === c);
        row.push(cell || null);
      }
      rows.push({ row: r, cells: row });
    }
    return rows;
  }, [filtered, selectedRack]);

  return (
    <div className="space-y-0" data-testid="page-warehouse-dashboard">
      <PageHeader
        title="Warehouse Dashboard"
        subtitle="Online Commerce / WMS"
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={load} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 inline mr-1 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </BtnSecondary>
            <Link to="/warehouse/qr" className="inline-block">
              <BtnSecondary><QrCode className="w-3.5 h-3.5 inline mr-1" />QR Sheet</BtnSecondary>
            </Link>
          </div>
        }
      />

      <div className="p-4 sm:p-6 space-y-6">
        {err && <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm">{err}</div>}

        {/* Stat tiles */}
        {dash && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatTile label="Total Cells" value={dash.total_cells} accent="#0F172A" />
            <StatTile label="Capacity (pairs)" value={dash.total_capacity.toLocaleString()} accent="#C27842" />
            <StatTile label="Occupied" value={dash.total_occupied.toLocaleString()} sub={`${dash.utilization_pct}% utilized`} accent="#F97316" />
            <StatTile label="Available" value={dash.total_available.toLocaleString()} accent="#16A34A" />
            <StatTile label="Distinct SKUs" value={dash.distinct_skus} accent="#2563EB" />
            <StatTile label="Active Picklists" value={dash.active_picklists} sub={`${dash.completed_today} done today`} accent="#7C3AED" />
          </div>
        )}

        {/* Zone strip */}
        {dash && dash.by_zone && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Card className="p-4 border-l-8 border-l-slate-900">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Main Zone</div>
                <Badge color="slate">{dash.by_zone.main.cells} cells</Badge>
              </div>
              <div className="mt-2 text-sm">
                <span className="font-bold text-lg">{dash.by_zone.main.occupied_pairs.toLocaleString()}</span>
                <span className="text-slate-500"> / {dash.by_zone.main.capacity_pairs.toLocaleString()} pairs occupied</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Used for regular finished-goods storage (production_in, dispatch, restocked returns).
              </div>
            </Card>
            <Card className="p-4 border-l-8 border-l-amber-500">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-wider font-bold text-amber-700 flex items-center gap-1">
                  <RotateCcw className="w-3.5 h-3.5" />Return Holding
                </div>
                <Badge color="orange">{dash.by_zone.return_holding.cells} cells</Badge>
              </div>
              <div className="mt-2 text-sm">
                <span className="font-bold text-lg">{dash.by_zone.return_holding.occupied_pairs.toLocaleString()}</span>
                <span className="text-slate-500"> / {dash.by_zone.return_holding.capacity_pairs.toLocaleString()} pairs quarantined</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                Fresh <code>return_in</code> movements land here for inspection. Cleared items move to main via <code>return_restocked</code>.
              </div>
            </Card>
          </div>
        )}

        {/* Per-rack breakdown */}
        {dash && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Object.keys(dash.by_rack || {}).sort().map(r => {
              const rd = dash.by_rack[r] || {};
              const cap = rd.capacity_pairs || 0;
              const util = cap ? Math.round((rd.occupied_pairs || 0) / cap * 100) : 0;
              return (
                <Card key={r} className={`p-4 cursor-pointer ${selectedRack === r ? "ring-2 ring-[#C27842]" : ""}`} onClick={() => setSelectedRack(r)}>
                  <div className="flex items-center justify-between">
                    <div className="text-2xl font-black">Rack {r}</div>
                    <Badge color={util > 90 ? "red" : util > 60 ? "orange" : util > 0 ? "blue" : "slate"}>{util}%</Badge>
                  </div>
                  <div className="text-xs text-slate-500 mt-2">{rd.occupied_pairs} / {rd.capacity_pairs} pairs</div>
                  <div className="h-2 bg-slate-200 mt-2 relative overflow-hidden">
                    <div className="absolute inset-y-0 left-0 bg-[#C27842]" style={{ width: `${util}%` }} />
                  </div>
                  <div className="grid grid-cols-3 gap-1 mt-3 text-[10px] uppercase tracking-wider text-center">
                    <div><div className="font-bold">{rd.empty_cells}</div><div className="text-slate-500">Empty</div></div>
                    <div><div className="font-bold text-orange-700">{rd.partial_cells}</div><div className="text-slate-500">Partial</div></div>
                    <div><div className="font-bold text-green-700">{rd.full_cells}</div><div className="text-slate-500">Full</div></div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {/* Rack heatmap */}
        <Card className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-slate-500" />
              <h2 className="font-bold text-lg">Rack {selectedRack} — Layout (10 rows × 8 columns)</h2>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Select value={selectedRack} onChange={(e) => setSelectedRack(e.target.value)}>
                {RACKS.map(r => <option key={r} value={r}>Rack {r}</option>)}
              </Select>
              <Select value={zoneFilter} onChange={(e) => setZoneFilter(e.target.value)}>
                <option value="">All zones</option>
                <option value="main">Main zone</option>
                <option value="return_holding">Return holding</option>
              </Select>
              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All statuses</option>
                <option value="empty">Empty</option>
                <option value="partial">Partial</option>
                <option value="full">Full</option>
                <option value="blocked">Blocked</option>
              </Select>
              <Input placeholder="Search code…" value={search} onChange={e => setSearch(e.target.value)} className="w-40" />
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-3 text-xs mb-4">
            {Object.entries(STATUS_COLOR).map(([k, v]) => (
              <div key={k} className="flex items-center gap-1.5">
                <div className="w-4 h-4 border border-slate-300" style={{ background: v }} />
                <span className="capitalize">{k}</span>
              </div>
            ))}
            <div className="flex items-center gap-1.5">
              <div className="w-4 h-4 border-2 border-amber-500 border-dashed" />
              <span>Return Holding zone</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Lock className="w-3 h-3 text-red-800" />
              <span>Blocked</span>
            </div>
          </div>

          {/* Column headers */}
          <div className="overflow-x-auto">
            <div className="inline-block min-w-full">
              <div className="flex gap-1 mb-1">
                <div className="w-12 flex-shrink-0" />
                {[1,2,3,4,5,6,7,8].map(c => (
                  <div key={c} className="w-16 sm:w-20 text-center text-[10px] uppercase tracking-wider font-bold text-slate-500">Col {c}</div>
                ))}
              </div>
              {grid.map(g => (
                <div key={g.row} className="flex gap-1 mb-1">
                  <div className="w-12 flex-shrink-0 text-right pr-2 text-[10px] uppercase tracking-wider font-bold text-slate-500 self-center">Row {String(g.row).padStart(2, "0")}</div>
                  {g.cells.map((cell, ci) => {
                    if (!cell) return <div key={ci} className="w-16 sm:w-20 h-14 bg-slate-100 border border-slate-200" />;
                    const bg = STATUS_COLOR[cell.status] || "#F1F5F9";
                    const tx = STATUS_TEXT[cell.status] || "text-slate-600";
                    const isReturn = cell.zone === "return_holding";
                    return (
                      <button
                        key={cell.location_code}
                        onClick={() => setSelectedCell(cell.location_code)}
                        title={`${cell.location_code} · ${cell.occupied_pairs}/${cell.capacity_pairs}${isReturn ? " · Return Holding" : ""}${cell.status === "blocked" ? " · BLOCKED: " + (cell.block_reason || "") : ""}`}
                        className={`w-16 sm:w-20 h-14 border-2 text-[10px] font-mono hover:border-[#0F172A] transition-colors ${tx} flex flex-col items-center justify-center relative ${isReturn ? "border-amber-500 border-dashed" : "border-slate-300"}`}
                        style={{ background: bg }}
                        data-testid={`cell-${cell.location_code}`}
                      >
                        {isReturn && <RotateCcw className="w-2.5 h-2.5 absolute top-0.5 right-0.5 text-amber-700" />}
                        {cell.status === "blocked" && <Lock className="w-2.5 h-2.5 absolute top-0.5 left-0.5 text-red-800" />}
                        <div className="font-bold">{cell.row ? `${String(cell.row).padStart(2,"0")}-${String(cell.column).padStart(2,"0")}` : cell.location_code}</div>
                        <div className="text-[9px]">{cell.occupied_pairs}/{cell.capacity_pairs}</div>
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {selectedCell && <CellDetail code={selectedCell} onClose={() => setSelectedCell(null)} onChanged={load} />}
    </div>
  );
}

function CellDetail({ code, onClose, onChanged }) {
  const { user } = useAuth() || {};
  const isAdmin  = user && (user.role === "admin" || user.role === "manager");
  const [data, setData] = useState(null);
  const [err, setErr]   = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setErr("");
    try {
      const r = await http.get(`/warehouse/locations/${code}`);
      setData(r.data);
    } catch (e) { setErr(friendlyAxiosError(e)); }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [code]);

  async function toggleBlock() {
    if (!data) return;
    const currentlyBlocked = data.location.status === "blocked";
    let reason = null;
    if (!currentlyBlocked) {
      reason = window.prompt("Reason for blocking this cell?", "damaged / repair / maintenance");
      if (reason === null) return;
    } else {
      if (!window.confirm(`Unblock ${code}?`)) return;
    }
    setBusy(true);
    try {
      await http.patch(`/warehouse/locations/${code}/block`, {
        blocked: !currentlyBlocked,
        reason,
      });
      await load();
      onChanged && onChanged();
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Warehouse Cell</div>
            <div className="font-bold text-lg font-mono">{code}</div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-900"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5">
          {err && <div className="text-red-600 text-sm mb-2 p-2 border border-red-300 bg-red-50">{err}</div>}
          {data && (
            <div className="space-y-4">
              <div className="flex gap-6 items-start">
                <div className="flex-shrink-0 bg-white border border-slate-300 p-2">
                  <QRCodeSVG value={code} size={128} />
                </div>
                <div className="space-y-2 text-sm">
                  <div><span className="text-slate-500">Rack:</span> <strong>{data.location.rack}</strong></div>
                  <div><span className="text-slate-500">Row:</span> <strong>{data.location.row}</strong> · <span className="text-slate-500">Col:</span> <strong>{data.location.column}</strong></div>
                  <div><span className="text-slate-500">Zone:</span> <strong className="uppercase">{ZONE_LABEL[data.location.zone] || data.location.zone || "main"}</strong></div>
                  <div><span className="text-slate-500">Capacity:</span> <strong>{data.location.capacity_pairs} pairs</strong></div>
                  <div><span className="text-slate-500">Occupied:</span> <strong>{data.location.occupied_pairs}</strong></div>
                  <div><span className="text-slate-500">Available:</span> <strong>{data.location.available_pairs}</strong></div>
                  <div>
                    <Badge color={data.location.status === "full" ? "green" : data.location.status === "partial" ? "orange" : data.location.status === "blocked" ? "red" : "slate"}>
                      {data.location.status}
                    </Badge>
                    {data.location.block_reason && (
                      <div className="text-xs text-red-700 mt-1">🔒 {data.location.block_reason}</div>
                    )}
                  </div>
                </div>
              </div>

              {isAdmin && (
                <div className="pt-2 border-t border-slate-200">
                  {data.location.status === "blocked" ? (
                    <BtnPrimary onClick={toggleBlock} disabled={busy} className="w-full">
                      <Unlock className="w-3.5 h-3.5 inline mr-1" />
                      {busy ? "Unblocking…" : "Unblock this cell"}
                    </BtnPrimary>
                  ) : (
                    <BtnSecondary onClick={toggleBlock} disabled={busy} className="w-full text-red-700 border-red-300 hover:border-red-700">
                      <Lock className="w-3.5 h-3.5 inline mr-1" />
                      {busy ? "Blocking…" : "Block for repair / maintenance"}
                    </BtnSecondary>
                  )}
                  <div className="text-[10px] text-slate-500 mt-1 italic">
                    Blocked cells are excluded from auto-allocation. Existing contents remain untouched.
                  </div>
                </div>
              )}

              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">Contents ({data.contents.length})</div>
                <div className="border border-slate-200 max-h-56 overflow-auto">
                  {data.contents.length === 0 ? (
                    <div className="p-3 text-sm text-slate-500 italic">Empty cell</div>
                  ) : (
                    <table className="w-full text-xs">
                      <thead className="bg-slate-100">
                        <tr>
                          <th className="text-left px-3 py-2">Style</th>
                          <th className="text-left px-3 py-2">Color</th>
                          <th className="text-left px-3 py-2">Size</th>
                          <th className="text-right px-3 py-2">Qty</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.contents.map((c, i) => (
                          <tr key={i} className="border-t border-slate-100">
                            <td className="px-3 py-2 font-mono">{c.style_code}</td>
                            <td className="px-3 py-2">{c.color}</td>
                            <td className="px-3 py-2">{c.size}</td>
                            <td className="px-3 py-2 text-right font-bold">{c.qty}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
