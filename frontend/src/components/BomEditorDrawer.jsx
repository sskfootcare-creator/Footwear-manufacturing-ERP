import { useEffect, useState, useCallback } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { BtnPrimary, BtnSecondary } from "./ui-kit";
import { SafeImage } from "./ImageUploader";
import SearchableSelect from "./SearchableSelect";
import { X, Loader2, Trash2, Save, Plus, Wrench, ToggleLeft, ToggleRight } from "lucide-react";

/**
 * BomEditorDrawer — inspect and edit a style's Production Card (BOM).
 *
 * Props:
 *   - style:  { id, code, name, image_url, image_display_url, image_thumbnail_url } (required)
 *   - onClose(): required
 *   - onSaved(): optional — fires after any create/update/delete succeeds
 *
 * Backend endpoints:
 *   GET    /api/style-component-mapping?style_id=<id>
 *   POST   /api/style-component-mapping          (add row)
 *   PUT    /api/style-component-mapping/{id}     (edit qty / wastage / active)
 *   DELETE /api/style-component-mapping/{id}     (remove row)
 *   GET    /api/components                       (component picker source)
 */
export default function BomEditorDrawer({ style, onClose, onSaved }) {
  const [rows, setRows]             = useState([]);
  const [components, setComponents] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [err, setErr]               = useState("");
  const [dirtyById, setDirtyById]   = useState({}); // id → {qpp, waste, active}
  const [saving, setSaving]         = useState(null); // id being saved
  const [adding, setAdding]         = useState(false);
  const [newPick, setNewPick]       = useState({ component_id: "", quantity_per_pair: 1, wastage_percent: 5 });

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const [r1, r2] = await Promise.all([
        http.get(`/style-component-mapping?style_id=${style.id}`),
        http.get("/components"),
      ]);
      setRows(r1.data || []);
      setComponents(r2.data || []);
      setDirtyById({});
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setLoading(false); }
  }, [style.id]);

  useEffect(() => { load(); }, [load]);

  const componentById = (cid) => components.find((c) => c.id === cid);
  const componentLabel = (cid) => {
    const c = componentById(cid);
    if (!c) return "(missing)";
    return `${c.component_code} · ${c.component_name}${c.color ? ` (${c.color})` : ""}`;
  };
  const componentStock = (cid) => {
    const c = componentById(cid);
    if (!c) return null;
    const avail = Number(c.available_stock ?? (c.current_stock - (c.reserved_stock || 0)) ?? 0);
    return { avail, total: Number(c.current_stock || 0), reserved: Number(c.reserved_stock || 0) };
  };

  const rowValue = (row, key) => {
    if (dirtyById[row.id] && key in dirtyById[row.id]) return dirtyById[row.id][key];
    return row[key];
  };
  const setRowDirty = (row, key, val) =>
    setDirtyById((prev) => ({ ...prev, [row.id]: { ...prev[row.id], [key]: val } }));

  const saveRow = async (row) => {
    const patch = dirtyById[row.id];
    if (!patch) return;
    setSaving(row.id); setErr("");
    try {
      const payload = {
        quantity_per_pair: Number(patch.quantity_per_pair ?? row.quantity_per_pair),
        wastage_percent:   Number(patch.wastage_percent   ?? row.wastage_percent),
        active:            patch.active !== undefined ? patch.active : row.active,
      };
      await http.put(`/style-component-mapping/${row.id}`, payload);
      onSaved && onSaved();
      await load();
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setSaving(null); }
  };

  const removeRow = async (row) => {
    if (!window.confirm(`Remove ${componentLabel(row.component_id)} from ${style.code}'s BOM?`)) return;
    setSaving(row.id); setErr("");
    try {
      await http.delete(`/style-component-mapping/${row.id}`);
      onSaved && onSaved();
      await load();
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setSaving(null); }
  };

  const toggleActive = async (row) => {
    const next = !row.active;
    setSaving(row.id); setErr("");
    try {
      await http.put(`/style-component-mapping/${row.id}`, { active: next });
      onSaved && onSaved();
      await load();
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setSaving(null); }
  };

  const addNewRow = async () => {
    if (!newPick.component_id) return setErr("Pick a component first.");
    setAdding(true); setErr("");
    try {
      await http.post("/style-component-mapping", {
        style_id:          style.id,
        component_id:      newPick.component_id,
        quantity_per_pair: Number(newPick.quantity_per_pair) || 1,
        wastage_percent:   Number(newPick.wastage_percent)   || 0,
        active:            true,
      });
      setNewPick({ component_id: "", quantity_per_pair: 1, wastage_percent: 5 });
      onSaved && onSaved();
      await load();
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setAdding(false); }
  };

  // Components not yet in this style's BOM (avoid dup key on backend)
  const alreadyMapped = new Set(rows.map((r) => r.component_id));
  const pickable = components.filter((c) => !alreadyMapped.has(c.id));

  const getComponentKey   = (c) => c.id;
  const getComponentLabel = (c) => {
    const avail = Number(c.available_stock ?? (c.current_stock - (c.reserved_stock || 0)) ?? 0);
    return `${c.component_code} · ${c.component_name}${c.color ? ` (${c.color})` : ""}`;
  };
  const renderComponentOption = (c) => {
    const avail = Number(c.available_stock ?? (c.current_stock - (c.reserved_stock || 0)) ?? 0);
    const stockLabel = avail <= 0 ? "OUT OF STOCK" : `${avail} in stock`;
    const stockColor = avail <= 0 ? "text-red-600" : "text-emerald-700";
    return (
      <div className="flex-1 min-w-0">
        <div className="font-mono font-bold text-slate-900 truncate">
          {c.component_code} · {c.component_name}{c.color ? ` (${c.color})` : ""}
        </div>
        <div className={`text-[10px] font-bold ${stockColor}`}>{stockLabel}</div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={onClose}>
      <div
        className="bg-white w-full sm:max-w-3xl border-2 border-slate-900 shadow-ind-lg max-h-[100dvh] sm:max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="bom-editor-drawer"
      >
        {/* Header */}
        <div className="px-4 sm:px-5 py-4 border-b-2 border-slate-900 bg-slate-50 flex items-start justify-between gap-3 sticky top-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            <SafeImage
              image={{
                url: style.image_url,
                display_url: style.image_display_url,
                thumbnail_url: style.image_thumbnail_url,
              }}
              alt={style.code}
              aspectRatio="1/1"
              className="w-14 h-14 flex-shrink-0"
            />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold flex items-center gap-1">
                <Wrench className="w-3 h-3" /> Production Card (BOM)
              </div>
              <div className="font-mono font-black text-lg truncate">{style.code}</div>
              <div className="text-xs text-slate-600 truncate">{style.name}</div>
            </div>
          </div>
          {/* Close button — min 44px tap target */}
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-200 rounded touch-manipulation flex-shrink-0"
            data-testid="bom-close"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 sm:p-5 space-y-4">
          <div className="text-xs text-slate-600">
            Components below are auto-deducted from Component Inventory every time this style is produced.
            Deactivate a row instead of deleting if you want to preserve history but skip deduction temporarily.
          </div>

          {err && (
            <div className="p-2 border-2 border-red-300 bg-red-50 text-red-900 text-xs">{err}</div>
          )}

          {loading ? (
            <div className="text-center py-8 text-slate-400 text-sm">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="p-4 border-2 border-dashed border-slate-300 text-center text-slate-500 text-sm">
              No components mapped yet. Add the first one below — the system will auto-deduct it on every production of {style.code}.
            </div>
          ) : (
            <>
              {/* ── DESKTOP TABLE (md+) ── */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-xs border-2 border-slate-200">
                  <thead className="bg-slate-50 text-left">
                    <tr>
                      <th className="px-2 py-2 font-bold">Component</th>
                      <th className="px-2 py-2 font-bold text-right w-28">In stock</th>
                      <th className="px-2 py-2 font-bold text-right w-24">Qty / pair</th>
                      <th className="px-2 py-2 font-bold text-right w-20">Waste %</th>
                      <th className="px-2 py-2 font-bold text-center w-16">Active</th>
                      <th className="px-2 py-2 w-24" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const dirty = !!dirtyById[row.id];
                      const stock = componentStock(row.component_id);
                      const stockClass =
                        !stock ? "text-slate-400" :
                        stock.avail <= 0 ? "text-red-700 bg-red-50" :
                        stock.avail < 10 ? "text-amber-800 bg-amber-50" :
                        "text-emerald-800";
                      return (
                        <tr
                          key={row.id}
                          className={`border-t border-slate-200 ${!row.active ? "bg-slate-50 text-slate-400" : ""} ${dirty ? "bg-amber-50" : ""}`}
                          data-testid={`bom-row-${row.id}`}
                        >
                          <td className="px-2 py-1.5 font-mono">{componentLabel(row.component_id)}</td>
                          <td className={`px-2 py-1.5 text-right font-mono font-bold ${stockClass}`}>
                            {stock ? (
                              <>
                                {stock.avail.toLocaleString()}
                                {stock.reserved > 0 && (
                                  <span className="text-[10px] font-normal text-slate-500 ml-1" title={`${stock.total} total − ${stock.reserved} reserved`}>
                                    ({stock.total}−{stock.reserved})
                                  </span>
                                )}
                              </>
                            ) : "—"}
                          </td>
                          <td className="px-2 py-1.5 text-right">
                            <input
                              type="number" step="0.01"
                              value={rowValue(row, "quantity_per_pair")}
                              onChange={(e) => setRowDirty(row, "quantity_per_pair", e.target.value)}
                              className="w-20 border border-slate-300 px-1 py-0.5 text-right font-mono"
                              inputMode="decimal"
                              disabled={!row.active}
                            />
                          </td>
                          <td className="px-2 py-1.5 text-right">
                            <input
                              type="number" step="0.1"
                              value={rowValue(row, "wastage_percent")}
                              onChange={(e) => setRowDirty(row, "wastage_percent", e.target.value)}
                              className="w-16 border border-slate-300 px-1 py-0.5 text-right font-mono"
                              inputMode="decimal"
                              disabled={!row.active}
                            />
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <button
                              onClick={() => toggleActive(row)}
                              disabled={saving === row.id}
                              title={row.active ? "Deactivate (skip in production)" : "Reactivate"}
                              data-testid={`bom-toggle-${row.id}`}
                              className="p-1 text-slate-600 hover:text-slate-900 touch-manipulation"
                            >
                              {row.active
                                ? <ToggleRight className="w-6 h-6 text-emerald-600 mx-auto" />
                                : <ToggleLeft  className="w-6 h-6 text-slate-400  mx-auto" />}
                            </button>
                          </td>
                          <td className="px-2 py-1.5 text-right">
                            {dirty ? (
                              <button
                                onClick={() => saveRow(row)}
                                disabled={saving === row.id}
                                className="p-1 text-emerald-700 hover:text-emerald-900 mr-1 touch-manipulation"
                                title="Save changes"
                                data-testid={`bom-save-${row.id}`}
                              >
                                {saving === row.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                              </button>
                            ) : null}
                            <button
                              onClick={() => removeRow(row)}
                              disabled={saving === row.id}
                              className="p-1 text-red-600 hover:text-red-800 touch-manipulation"
                              title="Remove"
                              data-testid={`bom-delete-${row.id}`}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* ── MOBILE CARDS (<md) ── */}
              <div className="md:hidden space-y-3">
                {rows.map((row) => {
                  const dirty = !!dirtyById[row.id];
                  const stock = componentStock(row.component_id);
                  const stockLabel = !stock ? "—" :
                    stock.avail <= 0 ? "Out of stock" :
                    `${stock.avail.toLocaleString()} avail`;
                  const stockColor = !stock ? "text-slate-400" :
                    stock.avail <= 0 ? "text-red-700" :
                    stock.avail < 10 ? "text-amber-700" :
                    "text-emerald-700";
                  return (
                    <div
                      key={row.id}
                      className={`border-2 ${dirty ? "border-amber-300 bg-amber-50" : "border-slate-200"} ${!row.active ? "opacity-60" : ""} p-3 space-y-3`}
                      data-testid={`bom-row-${row.id}`}
                    >
                      {/* Component name + stock */}
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-mono font-bold text-sm leading-tight">{componentLabel(row.component_id)}</div>
                          <div className={`text-xs font-bold mt-0.5 ${stockColor}`}>{stockLabel}</div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {/* Active toggle */}
                          <button
                            onClick={() => toggleActive(row)}
                            disabled={saving === row.id}
                            className="p-2 touch-manipulation"
                            data-testid={`bom-toggle-${row.id}`}
                            aria-label={row.active ? "Deactivate" : "Reactivate"}
                          >
                            {row.active
                              ? <ToggleRight className="w-6 h-6 text-emerald-600" />
                              : <ToggleLeft  className="w-6 h-6 text-slate-400" />}
                          </button>
                        </div>
                      </div>

                      {/* Editable fields */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Qty / pair</label>
                          <input
                            type="number" step="0.01"
                            value={rowValue(row, "quantity_per_pair")}
                            onChange={(e) => setRowDirty(row, "quantity_per_pair", e.target.value)}
                            className="w-full border-2 border-slate-300 px-3 py-2.5 text-right font-mono text-sm focus:border-[#C27842] focus:outline-none min-h-[44px]"
                            inputMode="decimal"
                            disabled={!row.active}
                          />
                        </div>
                        <div>
                          <label className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Waste %</label>
                          <input
                            type="number" step="0.1"
                            value={rowValue(row, "wastage_percent")}
                            onChange={(e) => setRowDirty(row, "wastage_percent", e.target.value)}
                            className="w-full border-2 border-slate-300 px-3 py-2.5 text-right font-mono text-sm focus:border-[#C27842] focus:outline-none min-h-[44px]"
                            inputMode="decimal"
                            disabled={!row.active}
                          />
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex gap-2 pt-1 border-t border-slate-200">
                        {dirty && (
                          <button
                            onClick={() => saveRow(row)}
                            disabled={saving === row.id}
                            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 min-h-[44px] bg-emerald-700 text-white text-xs font-bold uppercase tracking-wider touch-manipulation"
                            data-testid={`bom-save-${row.id}`}
                          >
                            {saving === row.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                            Save
                          </button>
                        )}
                        <button
                          onClick={() => removeRow(row)}
                          disabled={saving === row.id}
                          className="flex items-center justify-center gap-1.5 px-4 py-2.5 min-h-[44px] border-2 border-red-300 text-red-700 text-xs font-bold uppercase tracking-wider hover:bg-red-50 touch-manipulation"
                          data-testid={`bom-delete-${row.id}`}
                        >
                          <Trash2 className="w-4 h-4" /> Remove
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Add new row */}
          <div className="border-2 border-slate-200 p-3 sm:p-4 bg-slate-50">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-3">Add component</div>
            <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-end">
              {/* Searchable component picker */}
              <div className="flex-1 min-w-0">
                <label className="text-[10px] uppercase text-slate-500 block mb-1">Component</label>
                <SearchableSelect
                  options={pickable}
                  value={newPick.component_id}
                  onChange={(id) => setNewPick((p) => ({ ...p, component_id: id }))}
                  getKey={getComponentKey}
                  getLabel={getComponentLabel}
                  renderOption={renderComponentOption}
                  placeholder="— search component —"
                  testId="bom-add-component-select"
                />
                {pickable.length === 0 && (
                  <div className="text-[10px] text-slate-500 mt-1">All components are already mapped to this style.</div>
                )}
              </div>
              <div className="flex gap-3 sm:gap-2">
                <div className="flex-1 sm:w-28">
                  <label className="text-[10px] uppercase text-slate-500 block mb-1">Qty / pair</label>
                  <input
                    type="number" step="0.01"
                    value={newPick.quantity_per_pair}
                    onChange={(e) => setNewPick((p) => ({ ...p, quantity_per_pair: e.target.value }))}
                    className="w-full border-2 border-slate-300 px-3 py-2.5 text-right font-mono text-sm focus:border-[#C27842] focus:outline-none min-h-[44px]"
                    inputMode="decimal"
                    data-testid="bom-add-qpp"
                  />
                </div>
                <div className="flex-1 sm:w-24">
                  <label className="text-[10px] uppercase text-slate-500 block mb-1">Waste %</label>
                  <input
                    type="number" step="0.1"
                    value={newPick.wastage_percent}
                    onChange={(e) => setNewPick((p) => ({ ...p, wastage_percent: e.target.value }))}
                    className="w-full border-2 border-slate-300 px-3 py-2.5 text-right font-mono text-sm focus:border-[#C27842] focus:outline-none min-h-[44px]"
                    inputMode="decimal"
                  />
                </div>
                <div className="flex items-end">
                  <BtnPrimary
                    onClick={addNewRow}
                    disabled={adding || !newPick.component_id}
                    className="min-h-[44px] !px-4"
                    data-testid="bom-add-submit"
                  >
                    {adding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  </BtnPrimary>
                </div>
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-1">
            <BtnSecondary onClick={onClose} data-testid="bom-done" className="min-h-[44px]">Done</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}
