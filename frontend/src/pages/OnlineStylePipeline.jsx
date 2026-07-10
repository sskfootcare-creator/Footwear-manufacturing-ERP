import { useEffect, useState, useCallback, useMemo } from "react";
import { http, formatApiError, friendlyAxiosError } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import { SafeImage } from "../components/ImageUploader";
import {
  Layers, ChevronRight, RefreshCw, Search, Rocket, Archive, TrendingDown,
  ImageOff, ExternalLink, Save, X, Plus, AlertTriangle, CheckCircle2,
  Package, DollarSign, Palette, Ruler, Camera, BookOpen,
} from "lucide-react";

/* ────────────────────────────────────────────────────────────
   Pipeline stage definitions — keep visually aligned with the
   backend ONLINE_STATUS_SEQUENCE + side branches.
   ──────────────────────────────────────────────────────────── */
const STAGES = [
  { key: "draft",                 label: "Draft",                 accent: "#64748B" },
  { key: "sample_approved",       label: "Sample Approved",       accent: "#0EA5E9" },
  { key: "photoshoot_completed",  label: "Photoshoot Done",       accent: "#8B5CF6" },
  { key: "catalog_completed",     label: "Catalog Done",          accent: "#A855F7" },
  { key: "price_finalized",       label: "Price Finalized",       accent: "#F59E0B" },
  { key: "ready_for_launch",      label: "Ready For Launch",      accent: "#F97316" },
  { key: "live",                  label: "Live",                  accent: "#16A34A" },
];
const SIDE_STAGES = [
  { key: "liquidation_candidate", label: "Liquidation Candidate", accent: "#DC2626" },
  { key: "archived",              label: "Archived",              accent: "#111827" },
];
const ALL_STAGES = [...STAGES, ...SIDE_STAGES];
const STAGE_BY_KEY = Object.fromEntries(ALL_STAGES.map((s) => [s.key, s]));

const CHANNELS = ["myntra", "flipkart", "nykaa", "website"];
const COMPONENTS = ["upper", "bottom", "sole", "insole", "lace", "box"];

const inr0 = (n) => (n == null || n === "" ? "—" : `₹${new Intl.NumberFormat("en-IN").format(Number(n))}`);

// Return the next stage key (or null if already at end / on a side branch)
function nextStageKey(current) {
  const idx = STAGES.findIndex((s) => s.key === current);
  if (idx === -1) return null;                         // side-branch: no forward
  if (idx === STAGES.length - 1) return null;          // already live
  return STAGES[idx + 1].key;
}

/* ────────────────────────────────────────────────────────────
   Advance-stage drawer — captures notes and confirms the transition,
   with a special "Go Live" mode that shows the seed-plan preview.
   ──────────────────────────────────────────────────────────── */
function AdvanceStageDrawer({ card, onClose, onDone }) {
  const [notes, setNotes]     = useState("");
  const [target, setTarget]   = useState(nextStageKey(card.online_status) || "");
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState("");
  const [result, setResult]   = useState(null);

  const isGoLive = target === "live";
  const isSideBranch = SIDE_STAGES.some((s) => s.key === target);

  const seedPreview = useMemo(() => {
    if (!isGoLive) return null;
    const colors = (card.planned_colors || []).filter(Boolean);
    const sizes  = (card.planned_sizes  || []).filter(Boolean);
    return {
      colors, sizes,
      pairs: colors.length * sizes.length,
      min:   card.planned_min_stock || 25,
    };
  }, [isGoLive, card]);

  async function submit() {
    setError(""); setSaving(true); setResult(null);
    try {
      const r = await http.patch(`/styles/${card.style_id}/online-status`, {
        to_status: target,
        notes:     notes.trim(),
      });
      setResult(r.data);
      onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Transition failed.");
    } finally { setSaving(false); }
  }

  const nextForwardKey = nextStageKey(card.online_status);
  return (
    <Drawer onClose={onClose} title={`Advance — ${card.style_code}`} testId="advance-drawer">
      <div className="space-y-4 p-4">
        <div className="flex items-center gap-3 text-xs">
          <Badge color="slate">{STAGE_BY_KEY[card.online_status]?.label || card.online_status}</Badge>
          <ChevronRight className="w-4 h-4 text-slate-400" />
          {target ? (
            <Badge color={isGoLive ? "green" : isSideBranch ? "red" : "blue"}>
              {STAGE_BY_KEY[target]?.label || target}
            </Badge>
          ) : (
            <span className="text-slate-400 italic">Pick a target stage below</span>
          )}
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5">
            Move To
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            {nextForwardKey && (
              <button
                onClick={() => setTarget(nextForwardKey)}
                className={`flex items-center justify-between text-left px-3 py-2 border-2 text-xs font-bold ${
                  target === nextForwardKey ? "border-[#0F172A] bg-[#0F172A] text-white" : "border-slate-300 hover:border-slate-500"
                }`}
              >
                <span className="flex items-center gap-2">
                  <ChevronRight className="w-4 h-4" />
                  {STAGE_BY_KEY[nextForwardKey].label}
                </span>
                <span className="text-[10px] uppercase tracking-wider opacity-70">Next Stage</span>
              </button>
            )}
            {SIDE_STAGES.map((s) => (
              <button
                key={s.key}
                onClick={() => setTarget(s.key)}
                className={`flex items-center justify-between text-left px-3 py-2 border-2 text-xs font-bold ${
                  target === s.key ? "border-[#0F172A] bg-[#0F172A] text-white" : "border-slate-300 hover:border-slate-500"
                }`}
              >
                <span className="flex items-center gap-2">
                  {s.key === "archived" ? <Archive className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  {s.label}
                </span>
                <span className="text-[10px] uppercase tracking-wider opacity-70">Side branch</span>
              </button>
            ))}
          </div>
        </div>

        {isGoLive && seedPreview && (
          <div className="border-2 border-green-500 bg-green-50 p-3 text-xs">
            <div className="flex items-center gap-1.5 font-bold text-green-800 uppercase tracking-wider text-[10px] mb-2">
              <Rocket className="w-3.5 h-3.5" /> Go-Live Side Effects
            </div>
            <ul className="space-y-1 text-green-900 font-mono">
              <li>• Generate <span className="font-bold">back_track_number</span> (auto)</li>
              <li>• Set <span className="font-bold">went_live_at</span> to now</li>
              <li>
                • Seed <span className="font-bold">{seedPreview.pairs}</span> FG inventory cells
                {" "}({seedPreview.colors.length} colors × {seedPreview.sizes.length} sizes),
                {" "}ready=0, min={seedPreview.min}
              </li>
            </ul>
            {seedPreview.pairs === 0 && (
              <div className="mt-2 flex items-center gap-1.5 text-red-700 font-bold">
                <AlertTriangle className="w-3.5 h-3.5" /> No planned colors/sizes — FG rows will NOT be seeded.
              </div>
            )}
          </div>
        )}

        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5">Notes (optional)</div>
          <textarea
            className="w-full border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-[#0F172A] focus:outline-none"
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. sample approved by ops on 12 Oct."
          />
        </div>

        {error && (
          <div className="border-2 border-red-500 bg-red-50 text-red-800 px-3 py-2 text-xs font-bold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}
        {result && (
          <div className="border-2 border-green-500 bg-green-50 text-green-900 px-3 py-2 text-xs font-mono">
            <div className="font-bold uppercase tracking-wider text-[10px] mb-1 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> Updated
            </div>
            <div>Status: <span className="font-bold">{result.online_status}</span></div>
            {result.back_track_number && (
              <div>back_track_number: <span className="font-bold">{result.back_track_number}</span></div>
            )}
            {result.seed_result && (
              <div>FG seeded: created {result.seed_result.created}, updated {result.seed_result.updated} (pairs: {result.seed_result.pairs})</div>
            )}
          </div>
        )}

        <div className="flex gap-2 pt-2 sticky bottom-0 bg-white py-2 border-t border-slate-200">
          <BtnPrimary onClick={submit} disabled={!target || saving} className="flex-1">
            {saving ? "Saving…" : <span className="flex items-center gap-2 justify-center"><Save className="w-4 h-4" /> Confirm Transition</span>}
          </BtnPrimary>
          <BtnSecondary onClick={onClose}><X className="w-4 h-4" /></BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

/* ────────────────────────────────────────────────────────────
   Edit-Details drawer — capture MRP, sale channels, planned
   colors/sizes/components, sole info, and photoshoot/catalog links.
   ──────────────────────────────────────────────────────────── */
function EditDetailsDrawer({ card, onClose, onDone }) {
  const [form, setForm] = useState({
    sale_channels:            card.sale_channels || [],
    mrp:                      card.mrp ?? "",
    online_selling_price:     card.online_selling_price ?? "",
    platform_commission_pct:  card.platform_commission_pct || {},
    planned_min_stock:        card.planned_min_stock ?? 25,
    planned_colors:           (card.planned_colors || []).join(", "),
    planned_sizes:            (card.planned_sizes  || []).join(", "),
    planned_components:       Object.fromEntries(
      COMPONENTS.map((c) => [c, (card.planned_components || []).find((x) => x.component === c)?.planned_qty || 0])
    ),
    sole_mould_name:  card.sole_mould_name  || "",
    sole_shape:       card.sole_shape       || "",
    pattern_number:   card.pattern_number   || "",
    photoshoot_link:  card.photoshoot_link  || "",
    catalogue_link:   card.catalogue_link   || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");

  const toggleChannel = (ch) => {
    setForm((f) => ({
      ...f,
      sale_channels: f.sale_channels.includes(ch)
        ? f.sale_channels.filter((c) => c !== ch)
        : [...f.sale_channels, ch],
    }));
  };

  async function save() {
    setError(""); setSaving(true);
    try {
      const payload = {
        sale_channels: form.sale_channels,
        mrp: form.mrp === "" ? null : Number(form.mrp),
        online_selling_price: form.online_selling_price === "" ? null : Number(form.online_selling_price),
        platform_commission_pct: Object.fromEntries(
          Object.entries(form.platform_commission_pct).filter(([, v]) => v !== "" && v != null).map(([k, v]) => [k, Number(v)])
        ),
        planned_min_stock: Number(form.planned_min_stock) || 25,
        planned_colors: form.planned_colors.split(",").map((s) => s.trim()).filter(Boolean),
        planned_sizes:  form.planned_sizes.split(",").map((s) => s.trim()).filter(Boolean),
        planned_components: COMPONENTS.map((c) => ({ component: c, planned_qty: Number(form.planned_components[c]) || 0 })),
        sole_mould_name: form.sole_mould_name,
        sole_shape:      form.sole_shape,
        pattern_number:  form.pattern_number,
        photoshoot_link: form.photoshoot_link,
        catalogue_link:  form.catalogue_link,
      };
      await http.put(`/style-lifecycle/${card.style_id}`, payload);
      onDone();
      onClose();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Save failed.");
    } finally { setSaving(false); }
  }

  return (
    <Drawer onClose={onClose} title={`Edit — ${card.style_code}`} testId="edit-details-drawer">
      <div className="p-4 space-y-5 pb-24">
        {/* Sale channels */}
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5 flex items-center gap-1.5">
            <Palette className="w-3.5 h-3.5" /> Sale Channels
          </div>
          <div className="flex flex-wrap gap-1.5">
            {CHANNELS.map((ch) => {
              const on = form.sale_channels.includes(ch);
              return (
                <button
                  key={ch}
                  onClick={() => toggleChannel(ch)}
                  className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold border-2 ${
                    on ? "bg-[#0F172A] text-white border-[#0F172A]" : "bg-white text-slate-700 border-slate-300 hover:border-slate-500"
                  }`}
                >
                  {ch}
                </button>
              );
            })}
          </div>
        </div>

        {/* Pricing */}
        <div className="grid grid-cols-2 gap-3">
          <Input label="MRP (₹)" type="number" step="0.01"
            value={form.mrp} onChange={(e) => setForm((f) => ({ ...f, mrp: e.target.value }))} />
          <Input label="Online Selling Price (₹)" type="number" step="0.01"
            value={form.online_selling_price} onChange={(e) => setForm((f) => ({ ...f, online_selling_price: e.target.value }))} />
        </div>

        {form.sale_channels.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5 flex items-center gap-1.5">
              <DollarSign className="w-3.5 h-3.5" /> Platform Commission % (per channel)
            </div>
            <div className="grid grid-cols-2 gap-2">
              {form.sale_channels.map((ch) => (
                <div key={ch}>
                  <label className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{ch}</label>
                  <input
                    type="number" step="0.01"
                    className="w-full border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-[#0F172A] focus:outline-none"
                    value={form.platform_commission_pct[ch] ?? ""}
                    onChange={(e) => setForm((f) => ({
                      ...f, platform_commission_pct: { ...f.platform_commission_pct, [ch]: e.target.value }
                    }))}
                    placeholder="e.g. 32.5"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Planned Colors / Sizes / Min stock */}
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5 flex items-center gap-1.5">
            <Ruler className="w-3.5 h-3.5" /> Planned Colors & Sizes (used to seed FG on Go-Live)
          </div>
          <div className="space-y-2">
            <Input label="Planned Colors (comma separated)"
              value={form.planned_colors} onChange={(e) => setForm((f) => ({ ...f, planned_colors: e.target.value }))}
              placeholder="e.g. Silver, Gold" />
            <Input label="Planned Sizes (comma separated)"
              value={form.planned_sizes} onChange={(e) => setForm((f) => ({ ...f, planned_sizes: e.target.value }))}
              placeholder="e.g. 36, 37, 38, 39, 40, 41" />
            <Input label="Planned min-stock per cell" type="number"
              value={form.planned_min_stock} onChange={(e) => setForm((f) => ({ ...f, planned_min_stock: e.target.value }))} />
          </div>
        </div>

        {/* Planned components */}
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5 flex items-center gap-1.5">
            <Package className="w-3.5 h-3.5" /> Planned Components per Style
          </div>
          <div className="grid grid-cols-3 gap-2">
            {COMPONENTS.map((c) => (
              <div key={c}>
                <label className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{c}</label>
                <input
                  type="number"
                  className="w-full border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-[#0F172A] focus:outline-none"
                  value={form.planned_components[c]}
                  onChange={(e) => setForm((f) => ({ ...f, planned_components: { ...f.planned_components, [c]: e.target.value } }))}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Sole / Pattern */}
        <div className="grid grid-cols-2 gap-3">
          <Input label="Sole Mould Name"
            value={form.sole_mould_name} onChange={(e) => setForm((f) => ({ ...f, sole_mould_name: e.target.value }))} />
          <Input label="Sole Shape"
            value={form.sole_shape} onChange={(e) => setForm((f) => ({ ...f, sole_shape: e.target.value }))} />
          <Input label="Pattern Number"
            value={form.pattern_number} onChange={(e) => setForm((f) => ({ ...f, pattern_number: e.target.value }))} />
        </div>

        {/* Content links */}
        <div className="space-y-2">
          <Input label="Photoshoot Link"
            value={form.photoshoot_link} onChange={(e) => setForm((f) => ({ ...f, photoshoot_link: e.target.value }))}
            placeholder="Drive / Dropbox URL to photoshoot assets" />
          <Input label="Catalogue Link"
            value={form.catalogue_link} onChange={(e) => setForm((f) => ({ ...f, catalogue_link: e.target.value }))}
            placeholder="Google Doc / Notion catalogue" />
        </div>

        {error && (
          <div className="border-2 border-red-500 bg-red-50 text-red-800 px-3 py-2 text-xs font-bold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}

        <div className="flex gap-2 pt-2 sticky bottom-0 bg-white py-2 border-t border-slate-200">
          <BtnPrimary onClick={save} disabled={saving} className="flex-1">
            {saving ? "Saving…" : <span className="flex items-center gap-2 justify-center"><Save className="w-4 h-4" /> Save Details</span>}
          </BtnPrimary>
          <BtnSecondary onClick={onClose}><X className="w-4 h-4" /></BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

/* ────────────────────────────────────────────────────────────
   Compact card in a kanban column.
   ──────────────────────────────────────────────────────────── */
function StyleCard({ card, onAdvance, onEdit }) {
  const stage = STAGE_BY_KEY[card.online_status] || STAGES[0];
  const nextKey = nextStageKey(card.online_status);
  const nextLabel = nextKey ? STAGE_BY_KEY[nextKey].label : null;
  return (
    <div
      className="bg-white border border-slate-200 hover:border-[#C27842] transition-colors flex flex-col"
      style={{ borderLeft: `4px solid ${stage.accent}` }}
      data-testid={`pipeline-card-${card.style_code}`}
    >
      {/* Image / photo slot */}
      {card.image_url || card.image_display_url || card.image_thumbnail_url ? (
        <SafeImage
          image={{
            url: card.image_url,
            display_url: card.image_display_url,
            thumbnail_url: card.image_thumbnail_url,
          }}
          alt={card.style_name}
          aspectRatio="16/8"
          testId={`pipeline-img-${card.style_code}`}
        />
      ) : (
        <div className="h-14 bg-slate-50 border-b border-slate-100 flex items-center justify-center">
          <ImageOff className="w-5 h-5 text-slate-300" />
        </div>
      )}

      <div className="p-2.5 flex-1 flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <div className="font-mono font-bold text-xs truncate">{card.style_code}</div>
          {card.back_track_number && (
            <span className="text-[9px] font-mono text-slate-500 uppercase tracking-wider" title="Back-track code">
              {card.back_track_number}
            </span>
          )}
        </div>
        <div className="text-[11px] text-slate-600 truncate">{card.style_name || "—"}</div>

        {/* Channel SKUs from sku_map */}
        {card.channel_skus?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.channel_skus.slice(0, 3).map((m) => (
              <span
                key={m.id}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 border border-slate-300 bg-slate-50 text-[9px] font-mono font-bold uppercase"
                title={`${m.source_type} / ${m.source_name} → ${m.external_sku}`}
              >
                <span className="text-slate-500">{m.source_name}</span>
                <ExternalLink className="w-2.5 h-2.5 text-slate-400" />
                <span className="text-slate-800">{m.external_sku}</span>
              </span>
            ))}
            {card.channel_skus.length > 3 && (
              <span className="text-[9px] font-bold text-slate-500 self-center">+{card.channel_skus.length - 3}</span>
            )}
          </div>
        )}

        {/* Selected chips: MRP, colors, sizes */}
        <div className="flex flex-wrap gap-1 text-[9px] font-mono text-slate-500 mt-0.5">
          {card.mrp != null && <span className="px-1 border border-slate-200">MRP {inr0(card.mrp)}</span>}
          {card.online_selling_price != null && (
            <span className="px-1 border border-slate-200 text-green-700">SP {inr0(card.online_selling_price)}</span>
          )}
          {(card.planned_colors?.length || 0) > 0 && (
            <span className="px-1 border border-slate-200">{card.planned_colors.length} colors</span>
          )}
          {(card.planned_sizes?.length || 0) > 0 && (
            <span className="px-1 border border-slate-200">{card.planned_sizes.length} sizes</span>
          )}
          {card.sale_channels?.length > 0 && (
            <span className="px-1 border border-slate-200 text-blue-700">{card.sale_channels.join(", ")}</span>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-1 mt-1.5">
          <button
            onClick={() => onEdit(card)}
            className="flex-1 text-[9px] uppercase tracking-wider font-bold text-slate-700 hover:text-white hover:bg-[#0F172A] border border-slate-300 px-1.5 py-1 flex items-center gap-1 justify-center"
            data-testid={`edit-${card.style_code}`}
          >
            Edit
          </button>
          <button
            onClick={() => onAdvance(card)}
            className={`flex-1 text-[9px] uppercase tracking-wider font-bold border px-1.5 py-1 flex items-center gap-1 justify-center ${
              nextKey
                ? "text-white bg-[#C27842] hover:bg-[#0F172A] border-[#C27842] hover:border-[#0F172A]"
                : "text-slate-400 border-slate-200 cursor-not-allowed"
            }`}
            title={nextLabel ? `Advance → ${nextLabel}` : "Already at the last main stage"}
            data-testid={`advance-${card.style_code}`}
          >
            <ChevronRight className="w-3 h-3" /> {nextLabel || "Advance"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Main page.
   ──────────────────────────────────────────────────────────── */
export default function OnlineStylePipeline() {
  const [rows, setRows]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [channel, setChannel]   = useState("");
  const [advanceCard, setAdvanceCard] = useState(null);
  const [editCard, setEditCard]       = useState(null);
  const [showAddPicker, setShowAddPicker] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (search)  p.append("search", search);
      if (channel) p.append("sale_channel", channel);
      const qs = p.toString() ? `?${p}` : "";
      const r = await http.get(`/styles/online${qs}`);
      setRows(r.data);
    } finally { setLoading(false); }
  }, [search, channel]);

  useEffect(() => { load(); }, [load]);

  // Group cards by online_status
  const byStage = useMemo(() => {
    const g = Object.fromEntries(ALL_STAGES.map((s) => [s.key, []]));
    for (const r of rows) {
      if (g[r.online_status]) g[r.online_status].push(r);
    }
    return g;
  }, [rows]);

  const counts = useMemo(() => {
    return Object.fromEntries(ALL_STAGES.map((s) => [s.key, byStage[s.key]?.length || 0]));
  }, [byStage]);

  return (
    <div className="min-h-screen bg-[#F7F7F5]">
      <PageHeader
        title="Online Style Pipeline"
        subtitle="Draft → Live lifecycle for online-branch styles. Cards advance one stage at a time."
        testId="online-pipeline-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={load} data-testid="pipeline-refresh-btn">
              <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
            </BtnSecondary>
            <BtnPrimary
              onClick={() => setShowAddPicker(true)}
              data-testid="pipeline-add-style-btn"
            >
              <span className="flex items-center gap-1.5"><Plus className="w-4 h-4" /> Add Style</span>
            </BtnPrimary>
          </div>
        }
      />

      {showAddPicker && (
        <AddStyleToPipelineDrawer
          onClose={() => setShowAddPicker(false)}
          onAdded={() => { setShowAddPicker(false); load(); }}
        />
      )}

      {/* Stage counts strip */}
      <div className="px-4 sm:px-8 py-4 grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-2">
        {ALL_STAGES.map((s) => (
          <div
            key={s.key}
            className="bg-white border-l-4 border-slate-200 px-2.5 py-2"
            style={{ borderLeftColor: s.accent }}
            data-testid={`stage-count-${s.key}`}
          >
            <div className="text-[9px] uppercase tracking-wider font-bold text-slate-500">{s.label}</div>
            <div className="font-mono font-bold text-lg" style={{ color: s.accent }}>{counts[s.key]}</div>
          </div>
        ))}
      </div>

      {/* Filter bar */}
      <div className="px-4 sm:px-8 py-3 bg-white border-y-2 border-slate-200 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]">
          <Input label="Search"
            placeholder="Style code or name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            testId="search-online" />
        </div>
        <div className="w-56">
          <Select label="Sale Channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="">All channels</option>
            {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
        </div>
        <BtnSecondary onClick={load}>Apply</BtnSecondary>
        <button
          className="text-xs text-slate-400 hover:text-slate-700 underline pb-1.5"
          onClick={() => { setSearch(""); setChannel(""); }}
        >Clear</button>
      </div>

      {/* Kanban */}
      <div className="px-4 sm:px-8 py-5 overflow-x-auto">
        {loading ? (
          <div className="text-center py-20 text-slate-400">Loading pipeline…</div>
        ) : rows.length === 0 ? (
          <Card className="p-10 text-center">
            <Layers className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <div className="text-slate-500 font-semibold mb-1">No styles in the online pipeline yet.</div>
            <div className="text-xs text-slate-400">Only styles you explicitly opt-in appear here. Use &quot;Add Style&quot; above, or the globe icon on a style card in the Styles master.</div>
          </Card>
        ) : (
          <div className="flex gap-3 min-w-max pb-4">
            {STAGES.map((s) => (
              <div key={s.key} className="w-64 flex-shrink-0" data-testid={`col-${s.key}`}>
                <div
                  className="px-2.5 py-2 flex items-baseline justify-between text-white"
                  style={{ background: s.accent }}
                >
                  <div className="text-[10px] uppercase tracking-wider font-bold">{s.label}</div>
                  <div className="font-mono font-bold text-sm">{counts[s.key]}</div>
                </div>
                <div className="bg-slate-100/60 p-1.5 space-y-1.5 min-h-[100px]">
                  {byStage[s.key]?.map((c) => (
                    <StyleCard
                      key={c.style_id}
                      card={c}
                      onAdvance={setAdvanceCard}
                      onEdit={setEditCard}
                    />
                  ))}
                </div>
              </div>
            ))}
            {/* Side branches */}
            {SIDE_STAGES.map((s) => (
              <div key={s.key} className="w-64 flex-shrink-0" data-testid={`col-${s.key}`}>
                <div
                  className="px-2.5 py-2 flex items-baseline justify-between text-white"
                  style={{ background: s.accent }}
                >
                  <div className="text-[10px] uppercase tracking-wider font-bold flex items-center gap-1">
                    {s.key === "archived" ? <Archive className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {s.label}
                  </div>
                  <div className="font-mono font-bold text-sm">{counts[s.key]}</div>
                </div>
                <div className="bg-slate-100/60 p-1.5 space-y-1.5 min-h-[100px]">
                  {byStage[s.key]?.map((c) => (
                    <StyleCard
                      key={c.style_id}
                      card={c}
                      onAdvance={setAdvanceCard}
                      onEdit={setEditCard}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {advanceCard && (
        <AdvanceStageDrawer
          card={advanceCard}
          onClose={() => setAdvanceCard(null)}
          onDone={() => { load(); setAdvanceCard(null); }}
        />
      )}
      {editCard && (
        <EditDetailsDrawer
          card={editCard}
          onClose={() => setEditCard(null)}
          onDone={() => load()}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Add-Style-to-Pipeline picker drawer.
   Lists styles that are NOT yet in the pipeline; user picks one,
   backend adds a "draft" lifecycle doc via POST /styles/{id}/pipeline.
   ──────────────────────────────────────────────────────────── */
function AddStyleToPipelineDrawer({ onClose, onAdded }) {
  const [styles, setStyles]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState("");
  const [adding, setAdding]   = useState(null);
  const [err, setErr]         = useState("");

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const qs = search ? `?search=${encodeURIComponent(search)}` : "";
      const r = await http.get(`/styles/not-in-pipeline${qs}`);
      setStyles(r.data || []);
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { load(); }, [load]);

  const addOne = async (sid, code) => {
    setAdding(sid); setErr("");
    try {
      await http.post(`/styles/${sid}/pipeline`);
      onAdded && onAdded();
    } catch (e) {
      setErr(friendlyAxiosError(e));
    } finally { setAdding(null); }
  };

  return (
    <Drawer onClose={onClose} title="Add Style to Online Pipeline" width="max-w-2xl">
      <div className="space-y-4">
        <div className="text-xs text-slate-500">
          Only styles NOT yet in the pipeline are shown. Adding creates a Draft lifecycle entry — you can then advance it through Sample → Live in the pipeline board.
        </div>

        <Input
          label="Search"
          placeholder="Style code or name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          testId="add-pipeline-search"
        />

        {err && (
          <div className="p-2 bg-red-50 border-2 border-red-300 text-red-800 text-xs">{err}</div>
        )}

        {loading ? (
          <div className="text-center py-10 text-slate-400 text-sm">Loading…</div>
        ) : styles.length === 0 ? (
          <div className="text-center py-10 text-slate-400 text-sm">
            {search ? "No matching styles outside the pipeline." : "Every style is already in the pipeline."}
          </div>
        ) : (
          <div className="border-2 border-slate-200 divide-y divide-slate-200 max-h-[60vh] overflow-y-auto">
            {styles.map((s) => (
              <div
                key={s.id}
                className="flex items-center gap-3 p-3 hover:bg-slate-50"
                data-testid={`add-pipeline-row-${s.code}`}
              >
                <SafeImage
                  image={{
                    url: s.image_url,
                    display_url: s.image_display_url,
                    thumbnail_url: s.image_thumbnail_url,
                  }}
                  alt={s.name}
                  aspectRatio="1/1"
                  className="w-14 h-14 flex-shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="font-mono font-bold text-sm">{s.code}</div>
                  <div className="text-xs text-slate-500 truncate">{s.name || "—"}</div>
                </div>
                <BtnPrimary
                  onClick={() => addOne(s.id, s.code)}
                  disabled={adding === s.id}
                  data-testid={`add-pipeline-btn-${s.code}`}
                >
                  {adding === s.id ? "Adding…" : "Add"}
                </BtnPrimary>
              </div>
            ))}
          </div>
        )}
      </div>
    </Drawer>
  );
}
