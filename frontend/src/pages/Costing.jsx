import { useEffect, useState, useMemo } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Select, Input } from "../components/ui-kit";
import { Calculator as CalcIcon } from "lucide-react";

export default function Costing() {
  const [styles, setStyles] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [overrides, setOverrides] = useState({ margin_pct: null, gst_pct: null });

  useEffect(() => {
    http.get("/styles?status=active").then(r => setStyles(r.data));
  }, []);

  const selected = useMemo(() => styles.find(s => s.id === selectedId), [styles, selectedId]);

  const adjusted = useMemo(() => {
    if (!selected) return null;
    const margin_pct = overrides.margin_pct ?? selected.margin_pct;
    const gst_pct = overrides.gst_pct ?? selected.gst_pct;
    const total = selected.costing.total_cost;
    const margin = total * margin_pct / 100;
    const sell = total + margin;
    const gst = sell * gst_pct / 100;
    return { total, margin, sell, gst, final: sell + gst, margin_pct, gst_pct };
  }, [selected, overrides]);

  return (
    <div>
      <PageHeader title="Costing Calculator" subtitle="Tools / Costing" testId="costing-header" />

      <div className="p-8 grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 p-6">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-xl font-bold">Pick a Style</h2>
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Replicates your master sheet</span>
          </div>
          <Select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} testId="costing-style-select">
            <option value="">— Select a style —</option>
            {styles.map(s => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
          </Select>

          {selected && (
            <div className="mt-6 space-y-5">
              {selected.image_url && (
                <div className="border-2 border-slate-200 overflow-hidden bg-slate-100" data-testid="costing-style-image">
                  <img src={selected.image_url} alt={selected.name} className="w-full h-56 object-cover" />
                  <div className="bg-white px-4 py-2 border-t-2 border-slate-200 flex items-baseline justify-between">
                    <span className="font-mono text-xs font-bold text-slate-500">{selected.code}</span>
                    <span className="font-bold text-sm">{selected.name}</span>
                  </div>
                </div>
              )}
              <Section title="Bill of Materials">
                <table className="w-full text-xs border-2 border-slate-200">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-[10px] uppercase tracking-wider">
                      <th className="px-3 py-2">Code</th>
                      <th className="px-3 py-2">Material</th>
                      <th className="px-3 py-2">Section</th>
                      <th className="px-3 py-2 text-right">Rate</th>
                      <th className="px-3 py-2 text-right">Qty/pair</th>
                      <th className="px-3 py-2 text-right">Yield</th>
                      <th className="px-3 py-2 text-right">Waste</th>
                      <th className="px-3 py-2 text-right">Cost/pair</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.bom.map((b, i) => {
                      const yld = Number(b.yield_per_unit || 1) || 1;
                      const cost = (Number(b.rate) * Number(b.quantity) / yld) * (1 + Number(b.waste_pct || 0) / 100);
                      return (
                        <tr key={i} className="border-t border-slate-200">
                          <td className="px-3 py-1.5 font-mono">{b.material_code}</td>
                          <td className="px-3 py-1.5">{b.material_name}</td>
                          <td className="px-3 py-1.5"><span className="text-[10px] uppercase tracking-wider">{b.section}</span></td>
                          <td className="px-3 py-1.5 text-right font-mono">₹{b.rate}/{b.unit}</td>
                          <td className="px-3 py-1.5 text-right font-mono">{b.quantity}</td>
                          <td className="px-3 py-1.5 text-right font-mono">{yld}</td>
                          <td className="px-3 py-1.5 text-right font-mono">{b.waste_pct}%</td>
                          <td className="px-3 py-1.5 text-right font-mono font-bold">{inr(cost)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Section>

              <Section title="Labor Operations">
                <div className="grid grid-cols-3 gap-2">
                  {selected.labor.map((l, i) => (
                    <div key={i} className="border-2 border-slate-200 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{l.name}</div>
                      <div className="font-mono font-bold mt-1">{inr(l.rate)}</div>
                    </div>
                  ))}
                </div>
              </Section>
            </div>
          )}
        </Card>

        {selected && adjusted && (
          <div>
            <div className="sticky top-6 bg-[#0F172A] text-white p-6 border-2 border-[#0F172A]">
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold mb-4 flex items-center gap-2">
                <CalcIcon className="w-3.5 h-3.5" /> Cost Sheet
              </div>
              <div className="space-y-1">
                <CRow label="Materials" value={inr(selected.costing.materials_cost)} />
                <CRow label="Labor" value={inr(selected.costing.labor_cost)} />
                <CRow label="Overhead" value={inr(selected.costing.overhead_cost)} />
                <CRow label="Packing" value={inr(selected.costing.packing_cost)} />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CRow label="Total Cost" value={inr(adjusted.total)} bold />
              </div>

              <div className="mt-5 pt-4 border-t border-slate-700 space-y-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Margin %</label>
                  <input
                    type="number"
                    step="0.5"
                    value={adjusted.margin_pct}
                    onChange={(e) => setOverrides({ ...overrides, margin_pct: Number(e.target.value) })}
                    className="w-full mt-1 bg-slate-900 border border-slate-700 px-3 py-1.5 font-mono text-white"
                    data-testid="margin-pct-input"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">GST %</label>
                  <input
                    type="number"
                    step="0.5"
                    value={adjusted.gst_pct}
                    onChange={(e) => setOverrides({ ...overrides, gst_pct: Number(e.target.value) })}
                    className="w-full mt-1 bg-slate-900 border border-slate-700 px-3 py-1.5 font-mono text-white"
                  />
                </div>
              </div>

              <div className="mt-5 pt-4 border-t border-slate-700">
                <CRow label="Margin amt" value={inr(adjusted.margin)} />
                <CRow label="Selling price" value={inr(adjusted.sell)} bold accent />
                <CRow label={`GST ${adjusted.gst_pct}%`} value={inr(adjusted.gst)} small />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CRow label="Final / pair" value={inr(adjusted.final)} big />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-sm uppercase tracking-wider font-bold mb-2 text-slate-700">{title}</h3>
      {children}
    </div>
  );
}
function CRow({ label, value, bold, big, small, accent }) {
  return (
    <div className={`flex justify-between items-baseline ${big ? "py-1" : "py-0.5"}`}>
      <span className={`uppercase tracking-wider ${small ? "text-[10px] text-slate-500" : "text-xs text-slate-400"}`}>{label}</span>
      <span className={`font-mono ${bold ? "font-bold" : ""} ${big ? "text-2xl text-[#C27842]" : "text-sm"} ${accent ? "text-[#C27842]" : "text-white"}`}>{value}</span>
    </div>
  );
}
