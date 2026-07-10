import { useEffect, useState } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, BtnSecondary, Select } from "../components/ui-kit";
import { QRCodeSVG } from "qrcode.react";
import { Printer, RefreshCw } from "lucide-react";

export default function WarehouseQRSheet() {
  const [rack, setRack]         = useState("A");
  const [locations, setLocations] = useState([]);
  const [err, setErr]           = useState("");

  useEffect(() => {
    (async () => {
      setErr("");
      try {
        const r = await http.get(`/warehouse/locations?rack=${rack}`);
        setLocations(r.data);
      } catch (e) { setErr(friendlyAxiosError(e)); }
    })();
  }, [rack]);

  return (
    <div data-testid="page-qr-sheet">
      <div className="print:hidden">
        <PageHeader
          title="Location QR Sheet"
          subtitle="Online Commerce / WMS"
          action={
            <div className="flex gap-2">
              <Select value={rack} onChange={e => setRack(e.target.value)}>
                <option value="A">Rack A</option>
                <option value="B">Rack B</option>
                <option value="C">Rack C</option>
                <option value="D">Rack D</option>
              </Select>
              <BtnSecondary onClick={() => window.print()}><Printer className="w-3.5 h-3.5 inline mr-1" />Print</BtnSecondary>
            </div>
          }
        />
      </div>

      <div className="hidden print:block px-6 py-4 border-b-2 border-slate-900">
        <div className="text-xs uppercase tracking-widest text-slate-500">SSK Footcare Warehouse</div>
        <h1 className="text-2xl font-black">Rack {rack} — Location QR Codes</h1>
      </div>

      <div className="p-4 sm:p-6 print:p-4">
        {err && <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm">{err}</div>}
        <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-3 print:grid-cols-8 print:gap-2">
          {locations.map(l => (
            <div key={l.location_code} className="border-2 border-slate-900 p-2 text-center bg-white">
              <div className="flex justify-center">
                <QRCodeSVG value={l.location_code} size={80} />
              </div>
              <div className="font-mono font-black text-xs mt-1">{l.location_code}</div>
              <div className="text-[9px] text-slate-500">Cap {l.capacity_pairs}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
