import React, { useState, useEffect } from "react";
import {
  Wrench, Plus, Search, Layers, Scissors, ShieldAlert, CheckCircle,
  FileText, Activity, AlertCircle, RefreshCw, X
} from "lucide-react";
import { http } from "@/lib/api";

const TOOLING_CATEGORIES = [
  "Sole Mould",
  "Heel Mould",
  "Last",
  "Upper Die",
  "Insole Die",
  "Bottom Die",
  "Metal Cutting Die",
  "Embossing Plate",
  "Laser Tool",
  "Punch Tool",
  "Screen Printing Plate",
];

export default function ToolingLibrary() {
  const [tools, setTools] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({
    tool_code: "",
    tool_name: "",
    tool_category: "Sole Mould",
    vendor: "",
    material_code: "",
    drawing_url: "",
    image_url: "",
    life_cycle_status: "Active",
    max_usage: 100000,
    current_usage: 0,
    storage_location: "RACK-A-01",
    compatible_styles: "",
    remarks: "",
  });

  useEffect(() => {
    fetchTooling();
  }, []);

  const fetchTooling = async () => {
    setLoading(true);
    try {
      const res = await http.get("/plm/tooling");
      setTools(res.data);
    } catch (e) {
      console.error("Failed to load tooling library:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.tool_code || !form.tool_name) {
      alert("Tool Code and Tool Name are required.");
      return;
    }
    try {
      const payload = {
        ...form,
        compatible_styles: form.compatible_styles
          ? form.compatible_styles.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean)
          : [],
      };
      await http.post("/plm/tooling", payload);
      setModalOpen(false);
      setForm({
        tool_code: "",
        tool_name: "",
        tool_category: "Sole Mould",
        vendor: "",
        material_code: "",
        drawing_url: "",
        image_url: "",
        life_cycle_status: "Active",
        max_usage: 100000,
        current_usage: 0,
        storage_location: "RACK-A-01",
        compatible_styles: "",
        remarks: "",
      });
      fetchTooling();
    } catch (err) {
      alert("Failed to save tool: " + (err.response?.data?.detail || err.message));
    }
  };

  const filteredTools = tools.filter((t) => {
    const matchesCat = selectedCategory === "All" || t.tool_category === selectedCategory;
    const matchesSearch =
      !search ||
      t.tool_name.toLowerCase().includes(search.toLowerCase()) ||
      t.tool_code.toLowerCase().includes(search.toLowerCase()) ||
      (t.vendor || "").toLowerCase().includes(search.toLowerCase());
    return matchesCat && matchesSearch;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-8 space-y-6">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-400 rounded-xl">
            <Wrench className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-black tracking-tight text-white">Tooling & Sole Mould Library</h1>
              <span className="bg-amber-500/20 text-amber-300 text-xs font-mono font-bold px-2.5 py-1 rounded-full border border-amber-500/30">
                Mould & Die Registry
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">Lifecycle tracking, maintenance schedules & style compatibility</p>
          </div>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="px-5 py-2.5 bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs rounded-xl shadow-lg transition flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Add Tool / Mould Entry
        </button>
      </div>

      {/* Category Filter & Search */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-4 rounded-2xl">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setSelectedCategory("All")}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg transition ${
              selectedCategory === "All" ? "bg-amber-600 text-white" : "bg-slate-950 text-slate-400 hover:text-white"
            }`}
          >
            All Tooling ({tools.length})
          </button>
          {TOOLING_CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition ${
                selectedCategory === cat ? "bg-amber-600 text-white" : "bg-slate-950 text-slate-400 hover:text-white"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tool code, name, vendor..."
            className="bg-slate-950 border border-slate-700 text-white text-xs pl-9 pr-4 py-2 rounded-xl outline-none focus:border-amber-500"
          />
        </div>
      </div>

      {/* Tooling Grid */}
      {loading ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400 font-mono text-sm animate-pulse">
          Loading tooling and mould registry...
        </div>
      ) : filteredTools.length === 0 ? (
        <div className="bg-slate-900 border border-dashed border-slate-800 p-12 text-center rounded-2xl text-slate-500">
          <Wrench className="w-12 h-12 text-slate-700 mx-auto mb-3" />
          <p className="text-sm font-medium">No tooling records found in this category.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredTools.map((t) => {
            const usagePct = Math.min(Math.round(((t.current_usage || 0) / (t.max_usage || 100000)) * 100), 100);
            return (
              <div key={t.id} className="bg-slate-900 border border-slate-800 hover:border-amber-500/50 p-5 rounded-2xl shadow-xl transition space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-black text-xs text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded border border-amber-500/20">
                      {t.tool_code}
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300 bg-slate-950 px-2.5 py-1 rounded border border-slate-800">
                      {t.tool_category}
                    </span>
                  </div>

                  <h3 className="font-bold text-white text-base leading-snug mt-3">{t.tool_name}</h3>
                  <p className="text-xs text-slate-400 mt-1">Vendor: <span className="text-slate-200">{t.vendor || "N/A"}</span> • Location: <span className="font-mono text-slate-200">{t.storage_location}</span></p>
                </div>

                {/* Usage Bar */}
                <div className="space-y-1.5 p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-slate-400">Usage Life</span>
                    <span className={`font-bold ${usagePct > 80 ? "text-rose-400" : "text-emerald-400"}`}>
                      {t.current_usage || 0} / {t.max_usage || 100000} ({usagePct}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${usagePct > 80 ? "bg-rose-500" : "bg-emerald-500"}`}
                      style={{ width: `${usagePct}%` }}
                    />
                  </div>
                </div>

                {/* Compatible Styles */}
                {t.compatible_styles?.length > 0 && (
                  <div className="text-xs">
                    <span className="text-slate-400 font-medium">Compatible Styles: </span>
                    <span className="font-mono font-bold text-amber-300">{t.compatible_styles.join(", ")}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-lg rounded-2xl p-6 space-y-5 text-slate-100 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <h3 className="font-bold text-lg text-white flex items-center gap-2">
                <Wrench className="w-5 h-5 text-amber-400" /> Create Tool / Mould Entry
              </h3>
              <button onClick={() => setModalOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-bold mb-1">Tool / Mould Code</label>
                  <input
                    type="text"
                    value={form.tool_code}
                    onChange={(e) => setForm({ ...form, tool_code: e.target.value.toUpperCase() })}
                    placeholder="e.g. MLD-SOLE-001"
                    className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500 font-mono font-bold"
                    required
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-bold mb-1">Category</label>
                  <select
                    value={form.tool_category}
                    onChange={(e) => setForm({ ...form, tool_category: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500"
                  >
                    {TOOLING_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Tool / Mould Name</label>
                <input
                  type="text"
                  value={form.tool_name}
                  onChange={(e) => setForm({ ...form, tool_name: e.target.value })}
                  placeholder="e.g. TPR Sports Sole 6-Cavity Mould"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-bold mb-1">Vendor / Toolmaker</label>
                  <input
                    type="text"
                    value={form.vendor}
                    onChange={(e) => setForm({ ...form, vendor: e.target.value })}
                    placeholder="e.g. Precision Dies Ltd"
                    className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 font-bold mb-1">Storage Location</label>
                  <input
                    type="text"
                    value={form.storage_location}
                    onChange={(e) => setForm({ ...form, storage_location: e.target.value })}
                    placeholder="e.g. RACK-B-04"
                    className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Compatible Style Codes (comma separated)</label>
                <input
                  type="text"
                  value={form.compatible_styles}
                  onChange={(e) => setForm({ ...form, compatible_styles: e.target.value })}
                  placeholder="e.g. SSK001, SSK002, SSK005"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500 font-mono"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-white font-bold rounded-xl shadow-lg"
                >
                  Save Tooling Entry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
