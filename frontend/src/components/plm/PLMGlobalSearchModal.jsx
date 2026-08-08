import React, { useState, useEffect } from "react";
import { Search, X, Folder, FileText, Wrench, Layers, ArrowRight } from "lucide-react";
import { http } from "@/lib/api";

export default function PLMGlobalSearchModal({ isOpen, onClose, onSelectStyle, onSelectTool }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults(null);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await http.get(`/plm/search?q=${encodeURIComponent(query)}`);
        setResults(res.data);
      } catch (e) {
        console.error("PLM search failed:", e);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 bg-black/70 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-3xl rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh] text-slate-100">
        {/* Search Header */}
        <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center gap-3">
          <Search className="w-5 h-5 text-amber-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Global Search PLM (Style Code, Pattern, Mould Name, Tool Code, Vendor, Document...)"
            className="flex-1 bg-transparent text-white placeholder-slate-500 outline-none text-base font-medium"
            autoFocus
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-slate-400 hover:text-white p-1">
              <X className="w-4 h-4" />
            </button>
          )}
          <button onClick={onClose} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-lg ml-2">
            ESC
          </button>
        </div>

        {/* Results Container */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading && (
            <div className="text-center py-8 text-slate-400 text-sm animate-pulse">
              Searching PLM Digital Style Folders, Tooling & Patterns...
            </div>
          )}

          {!loading && !results && query.length < 2 && (
            <div className="text-center py-12 text-slate-500">
              <Search className="w-12 h-12 text-slate-700 mx-auto mb-3" />
              <p className="text-sm">Type a style code, pattern name, mould code, or tag to search globally.</p>
            </div>
          )}

          {!loading && results && (
            <div className="space-y-6">
              {/* Styles */}
              {results.styles?.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 mb-3 flex items-center gap-1.5">
                    <Folder className="w-4 h-4" /> Styles ({results.styles.length})
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {results.styles.map((s) => (
                      <div
                        key={s.id}
                        onClick={() => { onSelectStyle && onSelectStyle(s); onClose(); }}
                        className="p-3 bg-slate-950 border border-slate-800 hover:border-amber-500/50 rounded-xl cursor-pointer transition flex items-center justify-between group"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-slate-800 rounded-lg flex items-center justify-center font-mono font-bold text-amber-400 text-xs">
                            {s.code}
                          </div>
                          <div>
                            <div className="font-bold text-sm text-white group-hover:text-amber-300 transition">{s.name}</div>
                            <div className="text-xs text-slate-400">{s.category || "Footwear Style"}</div>
                          </div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-amber-400 transition" />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Documents & Engineering Assets */}
              {results.documents?.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-teal-400 mb-3 flex items-center gap-1.5">
                    <FileText className="w-4 h-4" /> Documents & CAD Patterns ({results.documents.length})
                  </h4>
                  <div className="space-y-2">
                    {results.documents.map((d) => (
                      <div
                        key={d.id}
                        className="p-3 bg-slate-950 border border-slate-800 hover:border-teal-500/50 rounded-xl flex items-center justify-between"
                      >
                        <div>
                          <div className="font-bold text-sm text-white flex items-center gap-2">
                            {d.document_name}
                            <span className="bg-teal-500/20 text-teal-300 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded">
                              v{d.current_version}
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 mt-0.5">
                            Style: <span className="font-mono text-slate-200">{d.style_code}</span> • Folder: {d.folder_name}
                          </div>
                        </div>
                        <a
                          href={d.url}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg text-teal-300 transition"
                        >
                          View File
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tooling & Moulds */}
              {results.tooling?.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-400 mb-3 flex items-center gap-1.5">
                    <Wrench className="w-4 h-4" /> Tooling & Sole Moulds ({results.tooling.length})
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {results.tooling.map((t) => (
                      <div
                        key={t.id}
                        onClick={() => { onSelectTool && onSelectTool(t); onClose(); }}
                        className="p-3 bg-slate-950 border border-slate-800 hover:border-indigo-500/50 rounded-xl cursor-pointer transition"
                      >
                        <div className="flex items-center justify-between">
                          <div className="font-mono font-bold text-xs text-indigo-300">{t.tool_code}</div>
                          <span className="text-[10px] uppercase font-bold px-2 py-0.5 bg-indigo-500/10 text-indigo-400 rounded border border-indigo-500/20">
                            {t.tool_category}
                          </span>
                        </div>
                        <div className="font-bold text-sm text-white mt-1">{t.tool_name}</div>
                        <div className="text-xs text-slate-400 mt-1">Vendor: {t.vendor || "Internal"} • Location: {t.storage_location}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
