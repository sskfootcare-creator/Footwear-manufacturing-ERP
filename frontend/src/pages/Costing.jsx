import { useEffect, useState, useMemo } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Select, Input } from "../components/ui-kit";
import { SafeImage } from "../components/ImageUploader";
import { Calculator as CalcIcon, UserCheck, Info, Palette } from "lucide-react";

export default function Costing() {
  const [styles, setStyles] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedColor, setSelectedColor] = useState("");
  const [overrides, setOverrides] = useState({
    margin_pct: null,
    gst_pct: null,
  });

  useEffect(() => {
    http.get("/styles?status=active").then((r) => setStyles(r.data));
  }, []);

  const selected = useMemo(
    () => styles.find((s) => s.id === selectedId),
    [styles, selectedId],
  );

  const customColors = useMemo(
    () => Object.keys(selected?.color_bom_overrides || {}),
    [selected],
  );

  const effectiveBom = useMemo(() => {
    if (!selected) return [];
    const base = selected.bom || [];
    if (!selectedColor || !selected.color_bom_overrides?.[selectedColor]) return base;
    const overridesList = selected.color_bom_overrides[selectedColor] || [];
    const removedLineIds = new Set(
      overridesList.filter((o) => o.removed && o.line_id).map((o) => o.line_id)
    );
    const result = [];
    base.forEach((item, idx) => {
      const lid = item.line_id || `line_${idx}`;
      if (removedLineIds.has(lid)) return;
      const mod = overridesList.find((o) => !o.removed && o.line_id === lid);
      if (mod) {
        result.push({ ...item, ...mod, is_override: true });
      } else {
        result.push(item);
      }
    });
    overridesList
      .filter((o) => !o.line_id && !o.removed)
      .forEach((custom) => {
        result.push({ ...custom, is_custom_addition: true });
      });
    return result;
  }, [selected, selectedColor]);

  const activeCosting = useMemo(() => {
    if (!selected) return null;
    if (selectedColor && selected.color_costing?.[selectedColor]) {
      return {
        ...selected.costing,
        ...selected.color_costing[selectedColor],
      };
    }
    return selected.costing;
  }, [selected, selectedColor]);

  const adjusted = useMemo(() => {
    if (!selected || !activeCosting) return null;
    const margin_pct = overrides.margin_pct ?? selected.margin_pct;
    const gst_pct = overrides.gst_pct ?? selected.gst_pct;
    const total = activeCosting.total_cost;
    const margin = (total * margin_pct) / 100;
    const sell = total + margin;
    const gst = (sell * gst_pct) / 100;
    return { total, margin, sell, gst, final: sell + gst, margin_pct, gst_pct };
  }, [selected, activeCosting, overrides]);

  return (
    <div>
      <PageHeader
        title="Costing Calculator"
        subtitle="Tools / Costing"
        testId="costing-header"
      />

      <div className="p-4 sm:p-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 p-6">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-xl font-bold">Pick a Style</h2>
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
              Replicates your master sheet
            </span>
          </div>
          <Select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            testId="costing-style-select"
          >
            <option value="">— Select a style —</option>
            {styles.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} — {s.name}
              </option>
            ))}
          </Select>

          {selected && (
            <div className="mt-6 space-y-5">
              {(selected.image_url ||
                selected.image_display_url ||
                selected.image_thumbnail_url) && (
                <div
                  className="border-2 border-slate-200 overflow-hidden bg-slate-100"
                  data-testid="costing-style-image"
                >
                  <SafeImage
                    image={{
                      url: selected.image_url,
                      display_url: selected.image_display_url,
                      thumbnail_url: selected.image_thumbnail_url,
                    }}
                    alt={selected.name}
                    aspectRatio="16/9"
                    testId={`costing-image-${selected.code}`}
                  />
                  <div className="bg-white px-4 py-2 border-t-2 border-slate-200 flex items-baseline justify-between">
                    <span className="font-mono text-xs font-bold text-slate-500">
                      {selected.code}
                    </span>
                    <span className="font-bold text-sm">{selected.name}</span>
                  </div>
                </div>
              )}
              {customColors.length > 0 && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase font-bold text-slate-700 tracking-wider flex items-center gap-1.5">
                      <Palette className="w-3.5 h-3.5 text-purple-600" /> Color Variant Costing
                    </span>
                    {selectedColor ? (
                      <span className="text-[10px] font-bold text-purple-800 bg-purple-100 px-2 py-0.5 rounded border border-purple-200">
                        {selectedColor} Custom BOM Active
                      </span>
                    ) : (
                      <span className="text-[10px] font-bold text-slate-500 bg-slate-200 px-2 py-0.5 rounded">
                        Standard Base BOM
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      type="button"
                      onClick={() => setSelectedColor("")}
                      className={`px-3 py-1 text-xs font-bold rounded border transition-colors ${
                        !selectedColor
                          ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                          : "bg-white text-slate-700 border-slate-300 hover:bg-slate-100"
                      }`}
                      data-testid="costing-variant-base"
                    >
                      Base BOM
                    </button>
                    {customColors.map((color) => (
                      <button
                        key={color}
                        type="button"
                        onClick={() => setSelectedColor(color)}
                        className={`px-3 py-1 text-xs font-bold rounded border transition-colors flex items-center gap-1.5 ${
                          selectedColor === color
                            ? "bg-purple-700 text-white border-purple-700 shadow-sm"
                            : "bg-white text-purple-700 border-purple-300 hover:bg-purple-50"
                        }`}
                        data-testid={`costing-variant-${color}`}
                      >
                        <Palette className="w-3 h-3" /> {color}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <Section title={`Bill of Materials${selectedColor ? ` — ${selectedColor} Variant` : ""}`}>
                <div className="overflow-x-auto">
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
                    {effectiveBom.map((b, i) => {
                      const yld = Number(b.yield_per_unit || 1) || 1;
                      const cost =
                        ((Number(b.rate) * Number(b.quantity)) / yld) *
                        (1 + Number(b.waste_pct || 0) / 100);
                      return (
                        <tr key={i} className={`border-t border-slate-200 ${b.is_custom_addition ? "bg-purple-50/50" : b.is_override ? "bg-amber-50/50" : ""}`}>
                          <td className="px-3 py-1.5 font-mono">
                            {b.material_code}
                          </td>
                          <td className="px-3 py-1.5">
                            <div className="flex items-center gap-1">
                              <span>{b.material_name}</span>
                              {b.is_custom_addition && (
                                <span className="text-[9px] bg-purple-100 text-purple-700 font-bold px-1.5 py-0.2 rounded">Added</span>
                              )}
                              {b.is_override && (
                                <span className="text-[9px] bg-amber-100 text-amber-700 font-bold px-1.5 py-0.2 rounded">Override</span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-1.5">
                            <span className="text-[10px] uppercase tracking-wider">
                              {b.section}
                            </span>
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">
                            ₹{b.rate}/{b.unit}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">
                            {b.quantity}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">
                            {yld}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono">
                            {b.waste_pct}%
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono font-bold">
                            {inr(cost)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Section>

              <Section title="Labor Operations (Planned)">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {selected.labor.map((l, i) => (
                    <div key={i} className="border-2 border-slate-200 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
                        {l.name}
                      </div>
                      <div className="font-mono font-bold mt-1">
                        {inr(l.rate)}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>

              {/* Real Job Assignments & Worker Rates */}
              {selected.costing?.is_assigned && (
                <Section title="Active Production Job Assignments (Worker Rates)">
                  <div className="bg-emerald-50 border-2 border-emerald-300 p-4 rounded-md space-y-3" data-testid="actual-job-assignments-section">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-emerald-900 font-bold text-xs uppercase tracking-wider">
                        <UserCheck className="w-4 h-4 text-emerald-600" />
                        Worker Job Assignments & Actual Labor Rates
                      </div>
                      <span className="px-2 py-0.5 bg-emerald-700 text-white text-[10px] font-bold rounded uppercase tracking-wider">
                        Live Production
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      {selected.costing.assigned_roles.map((asgn, i) => (
                        <div key={i} className="bg-white border border-emerald-200 p-2.5 rounded shadow-sm flex items-center justify-between">
                          <div>
                            <div className="font-bold uppercase text-[10px] text-emerald-900 tracking-wider">
                              {asgn.role}
                            </div>
                            <div className="text-slate-700 font-medium text-xs mt-0.5">
                              {asgn.worker_name || "Assigned Karigar"}
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono font-bold text-emerald-700 text-sm">
                              {inr(asgn.rate_per_pair)}
                            </div>
                            <div className="text-[9px] text-slate-400 font-mono">per pair</div>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="pt-2 border-t border-emerald-200 flex items-center justify-between text-xs">
                      <span className="text-emerald-900 font-medium">Total Assigned Worker Labor Cost:</span>
                      <span className="font-mono font-black text-emerald-800 text-sm">
                        {inr(selected.costing.labor_cost)} / pair
                      </span>
                    </div>
                  </div>
                </Section>
              )}
            </div>
          )}
        </Card>

        {selected && adjusted && (
          <div>
            <div className="lg:sticky lg:top-6 bg-[#0F172A] text-white p-4 sm:p-6 border-2 border-[#0F172A]">
              <div className="flex items-center justify-between mb-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold flex items-center gap-2">
                  <CalcIcon className="w-3.5 h-3.5" /> Cost Sheet
                </div>
                {selected.costing?.is_assigned ? (
                  <span
                    className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[9px] font-bold uppercase rounded flex items-center gap-1"
                    title="Calculated from active worker job assignments in production"
                    data-testid="assigned-labor-badge"
                  >
                    <UserCheck className="w-3 h-3" /> Actual Job Assigned
                  </span>
                ) : (
                  <span
                    className="px-2 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[9px] font-bold uppercase rounded flex items-center gap-1"
                    title="No production job assignments found yet; using planned style labor cost"
                    data-testid="estimated-labor-badge"
                  >
                    <Info className="w-3 h-3" /> Estimated Labor
                  </span>
                )}
              </div>
              {selectedColor && (
                <div data-testid="active-variant-badge" className="mb-3 px-2.5 py-1.5 bg-purple-500/20 border border-purple-400 text-purple-200 text-xs rounded flex items-center justify-between">
                  <span className="font-bold flex items-center gap-1.5">
                    <Palette className="w-3.5 h-3.5 text-purple-300" />
                    <span>Variant: {selectedColor}</span>
                  </span>
                  <span className="text-[10px] uppercase font-bold tracking-wider bg-purple-900/60 px-1.5 py-0.5 rounded text-purple-300">
                    Custom BOM
                  </span>
                </div>
              )}
              <div className="space-y-1">
                <CRow
                  label="Materials"
                  value={inr(activeCosting.materials_cost)}
                />
                <CRow
                  label={activeCosting?.is_assigned ? "Labor (Job Assigned)" : "Labor (Estimated)"}
                  value={inr(activeCosting.labor_cost)}
                  accent={activeCosting?.is_assigned}
                />
                <CRow
                  label="Overhead"
                  value={inr(activeCosting.overhead_cost != null ? activeCosting.overhead_cost : selected.costing.overhead_cost)}
                />
                <CRow
                  label="Packing"
                  value={inr(activeCosting.packing_cost != null ? activeCosting.packing_cost : selected.costing.packing_cost)}
                />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <CRow label="Total Cost of Production" value={inr(adjusted.total)} bold big />
              </div>

              <div className="mt-5 pt-4 border-t border-slate-700 space-y-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
                    Margin %
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={adjusted.margin_pct}
                    onChange={(e) =>
                      setOverrides({
                        ...overrides,
                        margin_pct: Number(e.target.value),
                      })
                    }
                    className="w-full mt-1 bg-slate-900 border border-slate-700 px-3 py-1.5 font-mono text-white"
                    data-testid="margin-pct-input"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
                    GST %
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={adjusted.gst_pct}
                    onChange={(e) =>
                      setOverrides({
                        ...overrides,
                        gst_pct: Number(e.target.value),
                      })
                    }
                    className="w-full mt-1 bg-slate-900 border border-slate-700 px-3 py-1.5 font-mono text-white"
                  />
                </div>
              </div>

              <div className="mt-5 pt-4 border-t border-slate-700">
                <CRow label="Margin amt" value={inr(adjusted.margin)} />
                <CRow
                  label="Selling price"
                  value={inr(adjusted.sell)}
                  bold
                  accent
                />
                <CRow
                  label={`GST ${adjusted.gst_pct}%`}
                  value={inr(adjusted.gst)}
                  small
                />
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
      <h3 className="text-sm uppercase tracking-wider font-bold mb-2 text-slate-700">
        {title}
      </h3>
      {children}
    </div>
  );
}
function CRow({ label, value, bold, big, small, accent }) {
  return (
    <div
      className={`flex justify-between items-baseline ${big ? "py-1" : "py-0.5"}`}
    >
      <span
        className={`uppercase tracking-wider ${small ? "text-[10px] text-slate-500" : "text-xs text-slate-400"}`}
      >
        {label}
      </span>
      <span
        className={`font-mono ${bold ? "font-bold" : ""} ${big ? "text-2xl text-[#C27842]" : "text-sm"} ${accent ? "text-[#C27842]" : "text-white"}`}
      >
        {value}
      </span>
    </div>
  );
}
