import React, { useState, useEffect } from "react";
import {
  Layers, Upload, Scan, FileText, CheckCircle2, Wrench, RefreshCw,
  Search, Plus, Filter, Scissors, ExternalLink, Sliders, X
} from "lucide-react";
import { http } from "@/lib/api";

const PATTERN_CATEGORIES = [
  "Upper Pattern",
  "Lining Pattern",
  "Insole Pattern",
  "Bottom Pattern",
  "Sock Pattern",
  "Toe Puff Pattern",
  "Counter Pattern",
  "Reinforcement Pattern",
  "Size Grading Sheet",
  "Pattern Nesting",
  "Pattern Marker",
];

export default function PatternManager() {
  const [patterns, setPatterns] = useState([]);
  const [tools, setTools] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  // Scan modal state
  const [scanModalOpen, setScanModalOpen] = useState(false);
  const [scanForm, setScanForm] = useState({
    style_code: "",
    pattern_name: "",
    category: "Upper Pattern",
    dpi: 300,
    auto_crop: true,
    deskew: true,
    background_cleaned: true,
    url: "",
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [pRes, tRes] = await Promise.all([
        http.get("/plm/patterns"),
        http.get("/plm/tooling")
      ]);
      setPatterns(pRes.data);
      setTools(tRes.data);
    } catch (e) {
      console.error("Failed to load pattern data:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleScanSubmit = async (e) => {
    e.preventDefault();
    if (!scanForm.style_code || !scanForm.pattern_name) {
      alert("Style Code and Pattern Name are required.");
      return;
    }
    try {
      await http.post("/plm/patterns/scan", scanForm);
      setScanModalOpen(false);
      setScanForm({
        style_code: "",
        pattern_name: "",
        category: "Upper Pattern",
        dpi: 300,
        auto_crop: true,
        deskew: true,
        background_cleaned: true,
        url: "",
      });
      fetchData();
    } catch (err) {
      alert("Digitizing scan failed: " + (err.response?.data?.detail || err.message));
    }
  };

  const filteredPatterns = patterns.filter((p) => {
    const matchesCat = selectedCategory === "All" || p.category === selectedCategory;
    const matchesSearch = !search || p.pattern_name.toLowerCase().includes(search.toLowerCase()) || p.style_code.toLowerCase().includes(search.toLowerCase());
    return matchesCat && matchesSearch;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-8 space-y-6">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 rounded-xl">
            <Layers className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-black tracking-tight text-white">Pattern Management Hub</h1>
              <span className="bg-indigo-500/20 text-indigo-300 text-xs font-mono font-bold px-2.5 py-1 rounded-full border border-indigo-500/30">
                2D/3D CAD & Grading
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">Digitize physical patterns, manage nesting markers & cutting die links</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setScanModalOpen(true)}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-xl shadow-lg transition flex items-center gap-2"
          >
            <Scan className="w-4 h-4" />
            Digitize & Scan Paper Pattern
          </button>
        </div>
      </div>

      {/* Category Pills & Search */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-4 rounded-2xl">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setSelectedCategory("All")}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg transition ${
              selectedCategory === "All" ? "bg-indigo-600 text-white" : "bg-slate-950 text-slate-400 hover:text-white"
            }`}
          >
            All Categories ({patterns.length})
          </button>
          {PATTERN_CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition ${
                selectedCategory === cat ? "bg-indigo-600 text-white" : "bg-slate-950 text-slate-400 hover:text-white"
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
            placeholder="Search pattern name or style..."
            className="bg-slate-950 border border-slate-700 text-white text-xs pl-9 pr-4 py-2 rounded-xl outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Patterns Grid */}
      {loading ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400 font-mono text-sm animate-pulse">
          Loading pattern registry...
        </div>
      ) : filteredPatterns.length === 0 ? (
        <div className="bg-slate-900 border border-dashed border-slate-800 p-12 text-center rounded-2xl text-slate-500">
          <Layers className="w-12 h-12 text-slate-700 mx-auto mb-3" />
          <p className="text-sm font-medium">No pattern records found in this category.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredPatterns.map((pat) => (
            <div key={pat.id} className="bg-slate-900 border border-slate-800 hover:border-indigo-500/50 p-5 rounded-2xl shadow-xl transition space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-xs text-indigo-400 bg-indigo-500/10 px-2.5 py-1 rounded border border-indigo-500/20">
                  {pat.style_code}
                </span>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 bg-slate-950 px-2.5 py-1 rounded border border-slate-800">
                  {pat.category}
                </span>
              </div>

              <div>
                <h3 className="font-bold text-white text-base leading-snug">{pat.pattern_name}</h3>
                <p className="text-xs text-slate-400 mt-1">Version v{pat.version || 1} • Linked to Digital Style Folder</p>
              </div>

              {/* Linked Die / Tool Info */}
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-xs space-y-1">
                <div className="flex items-center justify-between text-slate-300 font-medium">
                  <span className="flex items-center gap-1.5 text-slate-400">
                    <Scissors className="w-3.5 h-3.5 text-amber-400" /> Linked Cutting Die:
                  </span>
                  <span className="font-mono font-bold text-amber-300">{pat.linked_die_code || "Unlinked"}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Digitize & Scan Modal */}
      {scanModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-lg rounded-2xl p-6 space-y-5 text-slate-100 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <h3 className="font-bold text-lg text-white flex items-center gap-2">
                <Scan className="w-5 h-5 text-indigo-400" /> Digitize & Scan Physical Pattern
              </h3>
              <button onClick={() => setScanModalOpen(false)} className="text-slate-400 hover:text-white">
                ✕
              </button>
            </div>

            <form onSubmit={handleScanSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-bold mb-1">Style Code</label>
                <input
                  type="text"
                  value={scanForm.style_code}
                  onChange={(e) => setScanForm({ ...scanForm, style_code: e.target.value.toUpperCase() })}
                  placeholder="e.g. SSK001"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-indigo-500 font-mono font-bold"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Pattern Name / Part Title</label>
                <input
                  type="text"
                  value={scanForm.pattern_name}
                  onChange={(e) => setScanForm({ ...scanForm, pattern_name: e.target.value })}
                  placeholder="e.g. Vamp Upper Shell Pattern"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-indigo-500"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Pattern Category</label>
                <select
                  value={scanForm.category}
                  onChange={(e) => setScanForm({ ...scanForm, category: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-indigo-500"
                >
                  {PATTERN_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>

              {/* Resolution & Digitizing Options */}
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                <span className="font-bold text-indigo-400 block border-b border-slate-800 pb-1">Scanning & Pre-Processing Options</span>
                <div className="flex items-center justify-between">
                  <span className="text-slate-300">Resolution (DPI):</span>
                  <div className="flex gap-2 font-mono">
                    {[300, 600].map((d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setScanForm({ ...scanForm, dpi: d })}
                        className={`px-3 py-1 text-xs rounded-lg font-bold border transition ${
                          scanForm.dpi === d
                            ? "bg-indigo-600 text-white border-indigo-500"
                            : "bg-slate-900 text-slate-400 border-slate-800"
                        }`}
                      >
                        {d} DPI
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                    <input
                      type="checkbox"
                      checked={scanForm.deskew}
                      onChange={(e) => setScanForm({ ...scanForm, deskew: e.target.checked })}
                      className="accent-indigo-500"
                    />
                    Auto-Deskew
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                    <input
                      type="checkbox"
                      checked={scanForm.background_cleaned}
                      onChange={(e) => setScanForm({ ...scanForm, background_cleaned: e.target.checked })}
                      className="accent-indigo-500"
                    />
                    Background Cleaning
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Digitized File / ImageKit Link</label>
                <input
                  type="text"
                  value={scanForm.url}
                  onChange={(e) => setScanForm({ ...scanForm, url: e.target.value })}
                  placeholder="https://ik.imagekit.io/ssk/... or uploaded scan URL"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setScanModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-lg"
                >
                  Process & Digitize
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
