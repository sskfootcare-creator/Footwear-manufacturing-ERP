import { useEffect, useState, useMemo } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, BtnSecondary, Select } from "../components/ui-kit";
import { QRCodeSVG } from "qrcode.react";
import { Printer, RefreshCw } from "lucide-react";

const WAREHOUSE_ROWS = 10;

export default function WarehouseQRSheet() {
  const [row,       setRow]       = useState("1");
  const [rack,      setRack]      = useState("");      // "" = all racks in selected row
  const [locations, setLocations] = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [err,       setErr]       = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true); setErr("");
      try {
        // Build query: always filter by row; optionally also by rack
        const params = new URLSearchParams();
        // We filter client-side after fetching all for the row (server supports ?rack=N)
        const res = await http.get("/warehouse/locations");
        let locs = res.data.filter(l => String(l.row) === String(row));
        if (rack) locs = locs.filter(l => String(l.rack) === String(rack));
        // Sort by rack then cell
        locs.sort((a, b) =>
          a.rack !== b.rack ? a.rack - b.rack : a.cell - b.cell
        );
        setLocations(locs);
      } catch (e) {
        setErr(friendlyAxiosError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [row, rack]);

  const title = rack
    ? `Row ${row} / Rack ${rack} — Location QR Codes`
    : `Row ${row} (All Racks) — Location QR Codes`;

  return (
    <div data-testid="page-qr-sheet">
      {/* Screen-only header */}
      <div className="print:hidden">
        <PageHeader
          title="Location QR Sheet"
          subtitle="Online Commerce / WMS"
          action={
            <div className="flex gap-2 flex-wrap">
              {/* Row selector */}
              <Select value={row} onChange={e => setRow(e.target.value)}>
                {Array.from({ length: WAREHOUSE_ROWS }, (_, i) => i + 1).map(r => (
                  <option key={r} value={r}>Row {r}</option>
                ))}
              </Select>
              {/* Rack selector (scoped within selected row) */}
              <Select value={rack} onChange={e => setRack(e.target.value)}>
                <option value="">All racks</option>
                <option value="1">Rack 1</option>
                <option value="2">Rack 2</option>
                <option value="3">Rack 3</option>
              </Select>
              <BtnSecondary onClick={() => window.print()} disabled={loading}>
                <Printer className="w-3.5 h-3.5 inline mr-1" />Print / Save PDF
              </BtnSecondary>
            </div>
          }
        />
      </div>

      {/* Print header */}
      <div className="hidden print:block px-6 py-4 border-b-2 border-slate-900">
        <div className="text-xs uppercase tracking-widest text-slate-500">SSK Footcare Warehouse</div>
        <h1 className="text-2xl font-black">{title}</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          {locations.length} cells · location codes in <span className="font-mono">R##-RK#-C##</span> format
        </p>
      </div>

      <div className="p-4 sm:p-6 print:p-4">
        {err && (
          <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm mb-4">{err}</div>
        )}


        {loading && (
          <div className="py-8 text-center text-slate-400 text-sm">
            <RefreshCw className="w-4 h-4 animate-spin inline mr-2" />Loading locations…
          </div>
        )}

        {/* QR grid — grouped by rack for easy cutting */}
        {!loading && locations.length > 0 && (
          <div className="space-y-6 print:space-y-4">
            {[1, 2, 3]
              .filter(rk => !rack || String(rk) === String(rack))
              .map(rk => {
                const rackLocs = locations.filter(l => l.rack === rk);
                if (rackLocs.length === 0) return null;
                return (
                  <div key={rk}>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2 print:mb-1">
                      Row {row} · Rack {rk} — {rackLocs.length} cells
                    </div>
                    <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-3 print:grid-cols-8 print:gap-2">
                      {rackLocs.map(l => (
                        <div
                          key={l.location_code}
                          className="border-2 border-slate-900 p-2 text-center bg-white"
                        >
                          <div className="flex justify-center">
                            <QRCodeSVG value={l.location_code} size={72} />
                          </div>
                          <div className="font-mono font-black text-[10px] mt-1 leading-tight">
                            {l.location_code}
                          </div>
                          <div className="text-[8px] text-slate-500 mt-0.5">
                            Cap {l.capacity_pairs}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
          </div>
        )}

        {!loading && locations.length === 0 && !err && (
          <div className="py-12 text-center text-slate-400 text-sm">
            No locations found for Row {row}{rack ? `, Rack ${rack}` : ""}.
          </div>
        )}
      </div>
    </div>
  );
}
