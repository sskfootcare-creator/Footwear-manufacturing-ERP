import { useEffect, useState, useMemo } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, Card, StatTile, BtnSecondary, BtnPrimary, Badge, Input, Select } from "../components/ui-kit";
import { RefreshCw, Layers, X, QrCode, Lock, Unlock, MapPin, Grid3X3 } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useAuth } from "../lib/auth";
import { Link } from "react-router-dom";

// ─── Constants ────────────────────────────────────────────────────────────────
const WAREHOUSE_ROWS = 10;
const CELLS_PER_RACK = 8;
const ROW_PAIRS = [[1,2],[3,4],[5,6],[7,8],[9,10]];

const STATUS_COLOR = {
  empty:   "#E2E8F0",
  partial: "#FDBA74",
  full:    "#4ADE80",
  blocked: "#F87171",
};
const STATUS_TEXT = {
  empty:   "text-slate-500",
  partial: "text-orange-900",
  full:    "text-green-900",
  blocked: "text-red-900",
};
const ZONE_LABEL = {
  main: "Main Zone",
};

function utilColour(pct) {
  if (pct >= 90) return "#F87171";
  if (pct >= 60) return "#FDBA74";
  if (pct >   0) return "#60A5FA";
  return "#E2E8F0";
}

// ─── Single cell button ────────────────────────────────────────────────────────
function CellBtn({ cell, onSelect, dimmed }) {
  if (!cell) {
    return <div className="w-11 h-9 bg-slate-100 border border-slate-200 rounded-sm flex-shrink-0" />;
  }
  const bg       = dimmed ? "#F8FAFC" : (STATUS_COLOR[cell.status] || "#F1F5F9");
  const tx       = dimmed ? "text-slate-300" : (STATUS_TEXT[cell.status] || "text-slate-600");
  const isReturn = false;
  return (
    <button
      onClick={() => !dimmed && onSelect(cell.location_code)}
      title={`${cell.location_code}  ${cell.occupied_pairs}/${cell.capacity_pairs} pairs${isReturn ? "  · Return Holding" : ""}${cell.status === "blocked" ? "  · BLOCKED" : ""}`}
      className={[
        "w-11 h-9 flex-shrink-0 border text-[8px] font-mono flex flex-col items-center justify-center relative rounded-sm",
        dimmed ? "opacity-30 cursor-default" : "hover:ring-2 hover:ring-slate-700 transition-all duration-100 cursor-pointer",
        tx,
        "border-slate-300",
      ].join(" ")}
      style={{ background: bg }}
      data-testid={`cell-${cell.location_code}`}
    >
      {cell.status === "blocked" && !dimmed && <Lock className="w-1.5 h-1.5 absolute top-0.5 left-0.5 text-red-700" />}
      <div className="font-bold leading-none">{String(cell.cell).padStart(2,"0")}</div>
      <div className="text-[7px] leading-none mt-px opacity-70">{cell.occupied_pairs}/{cell.capacity_pairs}</div>
    </button>
  );
}

// ─── Rack block: label + 8 cells ─────────────────────────────────────────────
function RackBlock({ rackNo, cells, highlighted, onSelect, codeSet }) {
  return (
    <div className={[
      "rounded border",
      highlighted ? "border-[#C27842] ring-1 ring-[#C27842]" : "border-slate-200",
    ].join(" ")}>
      <div className={[
        "text-[8px] uppercase tracking-widest font-bold text-center py-px rounded-t",
        highlighted ? "bg-[#C27842] text-white" : "bg-slate-100 text-slate-500",
      ].join(" ")}>
        Rack {rackNo}
      </div>
      <div className="flex gap-px p-1 bg-white rounded-b overflow-x-auto">
        {cells.map((c, i) => (
          <CellBtn
            key={i}
            cell={c}
            onSelect={onSelect}
            dimmed={c && codeSet && !codeSet.has(c.location_code)}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Single warehouse row ─────────────────────────────────────────────────────
function WarehouseRow({ rowNum, allLocations, rackFilter, onSelect, highlightedRack, codeSet }) {
  const racks = [1, 2, 3].map(rk => {
    const cells = [];
    for (let c = 1; c <= CELLS_PER_RACK; c++) {
      const found = allLocations.find(l => l.row === rowNum && l.rack === rk && l.cell === c);
      cells.push(found || null);
    }
    return { rackNo: rk, cells };
  });
  const visible = rackFilter ? racks.filter(r => String(r.rackNo) === String(rackFilter)) : racks;

  return (
    <div className="flex items-stretch gap-2">
      <div className="w-10 flex-shrink-0 flex items-center justify-end pr-1">
        <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider select-none">
          R{String(rowNum).padStart(2,"0")}
        </span>
      </div>
      <div className="flex-1 flex gap-1.5">
        {visible.map(r => (
          <RackBlock
            key={r.rackNo}
            rackNo={r.rackNo}
            cells={r.cells}
            highlighted={highlightedRack && String(r.rackNo) === String(highlightedRack)}
            onSelect={onSelect}
            codeSet={codeSet}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Row-pair group ────────────────────────────────────────────────────────────
function RowPairGroup({ pair, allLocations, rackFilter, onSelect, highlightedRack, codeSet }) {
  const [rowA, rowB] = pair;
  const pairNum = Math.ceil(rowA / 2);
  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden shadow-sm bg-white">
      {/* pair header */}
      <div className="px-3 py-1 bg-slate-50 border-b border-slate-200 flex items-center gap-2">
        <Grid3X3 className="w-3 h-3 text-slate-400" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
          Grid Pair {pairNum} — Row {rowA} &amp; Row {rowB}
        </span>
      </div>
      {/* Row A */}
      <div className="p-2">
        <WarehouseRow
          rowNum={rowA}
          allLocations={allLocations}
          rackFilter={rackFilter}
          onSelect={onSelect}
          highlightedRack={highlightedRack}
          codeSet={codeSet}
        />
      </div>
      {/* hairline divider — rows are back-to-back, no gap */}
      <div className="mx-2 border-t border-dashed border-slate-300" />
      {/* Row B */}
      <div className="p-2">
        <WarehouseRow
          rowNum={rowB}
          allLocations={allLocations}
          rackFilter={rackFilter}
          onSelect={onSelect}
          highlightedRack={highlightedRack}
          codeSet={codeSet}
        />
      </div>
    </div>
  );
}

// ─── Aisle band between pair groups ──────────────────────────────────────────
function AisleBand({ fromPair, toPair }) {
  return (
    <div className="flex items-center gap-2 my-1">
      <div className="w-10 flex-shrink-0" />
      <div className="flex-1 h-8 rounded bg-blue-50 border border-dashed border-blue-200 flex items-center justify-center gap-2">
        <span className="text-[9px] uppercase tracking-[0.18em] font-bold text-blue-400 select-none">
          ↕&nbsp;&nbsp;Aisle / Passage — between Grid Pair {fromPair} &amp; Grid Pair {toPair}
        </span>
      </div>
    </div>
  );
}

// ─── Mini-map ─────────────────────────────────────────────────────────────────
function MiniMap({ locations, selectedRow, onRowClick }) {
  const rowStats = useMemo(() => {
    const stats = {};
    for (let r = 1; r <= WAREHOUSE_ROWS; r++) {
      const rowLocs = locations.filter(l => l.row === r);
      const cap = rowLocs.reduce((s, l) => s + (l.capacity_pairs || 0), 0);
      const occ = rowLocs.reduce((s, l) => s + (l.occupied_pairs || 0), 0);
      stats[r] = { cap, occ, pct: cap ? Math.round((occ / cap) * 100) : 0 };
    }
    return stats;
  }, [locations]);

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <MapPin className="w-3.5 h-3.5 text-[#C27842]" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Mini-Map — Occupancy by Row (click to focus)
          </span>
        </div>
        <div className="flex gap-3 text-[9px] text-slate-400">
          {[["#E2E8F0","Empty"],["#60A5FA","In use"],["#FDBA74","60%+"],["#F87171","90%+"]].map(([c,l]) => (
            <span key={l} className="flex items-center gap-1">
              <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: c }} />{l}
            </span>
          ))}
        </div>
      </div>

      {/* pair groups side by side */}
      <div className="flex gap-3">
        {ROW_PAIRS.map((pair, pi) => {
          const pairNum = pi + 1;
          return (
            <div key={pairNum} className="flex-1 rounded border border-slate-200 overflow-hidden">
              <div className="text-[8px] font-bold uppercase tracking-widest text-center text-slate-400 py-0.5 bg-slate-50 border-b border-slate-100">
                Pair {pairNum}
              </div>
              <div className="flex flex-col gap-px p-1">
                {pair.map(rowNum => {
                  const { pct, occ, cap } = rowStats[rowNum] || { pct: 0, occ: 0, cap: 0 };
                  const isSelected = String(rowNum) === String(selectedRow);
                  return (
                    <button
                      key={rowNum}
                      onClick={() => onRowClick(isSelected ? "" : String(rowNum))}
                      title={`Row ${rowNum}: ${occ}/${cap} pairs (${pct}%)`}
                      className={[
                        "w-full rounded-sm overflow-hidden relative flex items-center",
                        isSelected ? "ring-2 ring-[#C27842]" : "",
                      ].join(" ")}
                      style={{ height: 22 }}
                    >
                      <div
                        className="h-full rounded-sm transition-all duration-300"
                        style={{ width: `${Math.max(pct, 3)}%`, background: utilColour(pct) }}
                      />
                      <div className="absolute inset-0 flex items-center justify-between px-1.5">
                        <span className="text-[8px] font-bold text-slate-600">R{rowNum}</span>
                        <span className="text-[8px] text-slate-500">{pct}%</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────────
export default function WarehouseDashboard() {
  const [dash,         setDash]         = useState(null);
  const [locations,    setLocations]    = useState([]);
  const [selectedRow,  setSelectedRow]  = useState("");
  const [selectedRack, setSelectedRack] = useState("");
  const [zoneFilter,   setZoneFilter]   = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search,       setSearch]       = useState("");
  const [loading,      setLoading]      = useState(false);
  const [err,          setErr]          = useState("");
  const [selectedCell, setSelectedCell] = useState(null);
  const [showMiniMap,  setShowMiniMap]  = useState(true);

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

  // Build the set of location_codes that pass the current filters
  const filteredCodeSet = useMemo(() => {
    let out = locations;
    if (zoneFilter)   out = out.filter(l => (l.zone || "main") === zoneFilter);
    if (statusFilter) out = out.filter(l => l.status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      out = out.filter(l => l.location_code.toLowerCase().includes(q));
    }
    return new Set(out.map(l => l.location_code));
  }, [locations, zoneFilter, statusFilter, search]);

  // Which pair groups to render
  const visiblePairs = useMemo(() => {
    if (!selectedRow) return ROW_PAIRS;
    const rn = Number(selectedRow);
    return ROW_PAIRS.filter(([a, b]) => a === rn || b === rn);
  }, [selectedRow]);

  return (
    <div className="space-y-0" data-testid="page-warehouse-dashboard">
      <PageHeader
        title="Warehouse Dashboard"
        subtitle="Floor Plan · WMS"
        action={
          <div className="flex gap-2 flex-wrap">
            <BtnSecondary onClick={() => setShowMiniMap(v => !v)}>
              <MapPin className={`w-3.5 h-3.5 inline mr-1 ${showMiniMap ? "text-[#C27842]" : ""}`} />
              {showMiniMap ? "Hide Mini-Map" : "Mini-Map"}
            </BtnSecondary>
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

      <div className="p-4 sm:p-6 space-y-5">
        {err && <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm">{err}</div>}

        {/* Stat tiles */}
        {dash && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatTile label="Total Cells"      value={dash.total_cells}                    accent="#0F172A" />
            <StatTile label="Capacity (pairs)" value={dash.total_capacity?.toLocaleString()} accent="#C27842" />
            <StatTile label="Occupied"         value={dash.total_occupied?.toLocaleString()} sub={`${dash.utilization_pct}% utilized`} accent="#F97316" />
            <StatTile label="Available"        value={dash.total_available?.toLocaleString()} accent="#16A34A" />
            <StatTile label="Distinct SKUs"    value={dash.distinct_skus}                  accent="#2563EB" />
            <StatTile label="Active Picklists" value={dash.active_picklists} sub={`${dash.completed_today} done today`} accent="#7C3AED" />
          </div>
        )}

        {/* Zone summary */}
        {dash?.by_zone && (
          <div className="grid grid-cols-1 gap-3">
            <Card className="p-4 border-l-8 border-l-slate-900">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Warehouse Storage</div>
                <Badge color="slate">{dash.by_zone.main?.cells} cells</Badge>
              </div>
              <div className="mt-2 text-sm">
                <span className="font-bold text-lg">{dash.by_zone.main?.occupied_pairs?.toLocaleString()}</span>
                <span className="text-slate-500"> / {dash.by_zone.main?.capacity_pairs?.toLocaleString()} pairs occupied</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">All finished-goods storage across 240 cells (10 rows × 3 racks × 8 cells).</div>
            </Card>
          </div>
        )}

        {/* Mini-map */}
        {showMiniMap && locations.length > 0 && (
          <MiniMap
            locations={locations}
            selectedRow={selectedRow}
            onRowClick={setSelectedRow}
          />
        )}

        {/* Floor plan */}
        <Card className="p-4">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-slate-500" />
              <h2 className="font-bold text-lg">Warehouse Floor Plan</h2>
              {(selectedRow || selectedRack) && (
                <button
                  onClick={() => { setSelectedRow(""); setSelectedRack(""); }}
                  className="text-[10px] text-slate-400 underline hover:text-slate-700"
                >
                  Reset view
                </button>
              )}
            </div>
            <div className="flex gap-2 flex-wrap">
              <Select value={selectedRow} onChange={e => setSelectedRow(e.target.value)}>
                <option value="">All rows</option>
                {Array.from({ length: WAREHOUSE_ROWS }, (_, i) => i + 1).map(r => (
                  <option key={r} value={r}>Row {r}</option>
                ))}
              </Select>
              <Select value={selectedRack} onChange={e => setSelectedRack(e.target.value)}>
                <option value="">All racks</option>
                {[1,2,3].map(r => <option key={r} value={r}>Rack {r}</option>)}
              </Select>
              <Select value={zoneFilter} onChange={e => setZoneFilter(e.target.value)}>
                <option value="">All zones</option>
                <option value="main">Main zone</option>
              </Select>
              <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                <option value="">All statuses</option>
                <option value="empty">Empty</option>
                <option value="partial">Partial</option>
                <option value="full">Full</option>
                <option value="blocked">Blocked</option>
              </Select>
              <Input
                placeholder="Search code…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-36"
              />
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-4 text-xs mb-5">
            {Object.entries(STATUS_COLOR).map(([k, v]) => (
              <div key={k} className="flex items-center gap-1.5">
                <div className="w-3.5 h-3.5 rounded-sm border border-slate-300" style={{ background: v }} />
                <span className="capitalize text-slate-600">{k}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 ml-auto text-slate-400">
              <div className="flex-1 h-4 bg-blue-50 border border-dashed border-blue-200 rounded flex items-center justify-center px-3">
                <span className="text-[8px] uppercase tracking-widest font-bold text-blue-400">↕ Aisle / Passage</span>
              </div>
            </div>
          </div>

          {/* Floor plan body */}
          <div className="overflow-x-auto">
            <div className="inline-block min-w-full">

              {/* Rack column headers (shown when viewing all racks) */}
              {!selectedRack && (
                <div className="flex items-center gap-2 mb-1 ml-[52px]">
                  {[1,2,3].map(r => (
                    <div key={r} className="flex-1 text-center text-[9px] font-bold uppercase tracking-widest text-slate-400">
                      ← Rack {r} ({CELLS_PER_RACK} cells) →
                    </div>
                  ))}
                </div>
              )}

              {/* Pair groups */}
              <div className="space-y-0">
                {visiblePairs.map((pair, idx) => {
                  const globalPairNum = Math.ceil(pair[0] / 2);
                  const nextPair = visiblePairs[idx + 1];
                  const nextPairNum = nextPair ? Math.ceil(nextPair[0] / 2) : null;
                  return (
                    <div key={pair[0]}>
                      <RowPairGroup
                        pair={pair}
                        allLocations={locations}
                        rackFilter={selectedRack}
                        onSelect={setSelectedCell}
                        highlightedRack={selectedRack}
                        codeSet={
                          (zoneFilter || statusFilter || search) ? filteredCodeSet : null
                        }
                      />
                      {nextPairNum !== null && (
                        <AisleBand fromPair={globalPairNum} toPair={nextPairNum} />
                      )}
                    </div>
                  );
                })}
              </div>

              {locations.length === 0 && !loading && (
                <div className="py-12 text-center text-slate-400 text-sm">
                  No warehouse locations found.
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>

      {selectedCell && (
        <CellDetail
          code={selectedCell}
          onClose={() => setSelectedCell(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

// ─── Cell detail modal ────────────────────────────────────────────────────────
function CellDetail({ code, onClose, onChanged }) {
  const { user } = useAuth() || {};
  const isAdmin  = user && (user.role === "admin" || user.role === "manager");
  const [data, setData] = useState(null);
  const [err,  setErr]  = useState("");
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
    const isBlocked = data.location.status === "blocked";
    let reason = null;
    if (!isBlocked) {
      reason = window.prompt("Reason for blocking this cell?", "damaged / repair / maintenance");
      if (reason === null) return;
    } else {
      if (!window.confirm(`Unblock ${code}?`)) return;
    }
    setBusy(true);
    try {
      await http.patch(`/warehouse/locations/${code}/block`, { blocked: !isBlocked, reason });
      await load();
      onChanged && onChanged();
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-lg"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Warehouse Cell</div>
            <div className="font-bold text-lg font-mono">{code}</div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-900">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5">
          {err && <div className="text-red-600 text-sm mb-2 p-2 border border-red-300 bg-red-50">{err}</div>}
          {data && (
            <div className="space-y-4">
              <div className="flex gap-6 items-start">
                <div className="flex-shrink-0 bg-white border border-slate-300 p-2">
                  <QRCodeSVG value={code} size={128} />
                </div>
                <div className="space-y-1.5 text-sm">
                  <div>
                    <span className="text-slate-500">Location:</span>{" "}
                    <strong className="font-mono">{code}</strong>
                  </div>
                  <div>
                    <span className="text-slate-500">Row:</span>{" "}
                    <strong>{data.location.row}</strong>
                    {" · "}
                    <span className="text-slate-500">Rack:</span>{" "}
                    <strong>{data.location.rack}</strong>
                    {" · "}
                    <span className="text-slate-500">Cell:</span>{" "}
                    <strong>{data.location.cell}</strong>
                  </div>
                  <div>
                    <span className="text-slate-500">Pair group:</span>{" "}
                    <strong>{data.location.pair_group}</strong>
                    {" · "}
                    <span className="text-slate-500">Zone:</span>{" "}
                    <strong className="uppercase">
                      {ZONE_LABEL[data.location.zone] || data.location.zone || "main"}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-500">Capacity:</span>{" "}
                    <strong>{data.location.capacity_pairs} pairs</strong>
                  </div>
                  <div>
                    <span className="text-slate-500">Occupied:</span>{" "}
                    <strong>{data.location.occupied_pairs}</strong>
                    {" · "}
                    <span className="text-slate-500">Available:</span>{" "}
                    <strong>{data.location.available_pairs}</strong>
                  </div>
                  <div>
                    <Badge color={
                      data.location.status === "full"    ? "green"  :
                      data.location.status === "partial" ? "orange" :
                      data.location.status === "blocked" ? "red"    : "slate"
                    }>
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
                    <BtnSecondary
                      onClick={toggleBlock}
                      disabled={busy}
                      className="w-full text-red-700 border-red-300 hover:border-red-700"
                    >
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
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-2">
                  Contents ({data.contents.length})
                </div>
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
