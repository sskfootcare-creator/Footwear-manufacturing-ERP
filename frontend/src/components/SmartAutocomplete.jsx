import React, { useState, useEffect, useRef } from "react";
import { Search, Check, Loader2, Sparkles } from "lucide-react";

/**
 * SmartAutocomplete (U-007)
 * Intelligent data-entry aid with instant fuzzy matching, keyboard navigation,
 * and secondary attribute indicators for components, styles, materials, and clients.
 */
export default function SmartAutocomplete({
  value = "",
  onChange,
  onSelect,
  placeholder = "Search style, component, or client...",
  fetchUrl = "/api/styles",
  labelField = "name",
  codeField = "code",
  subField = "category",
  disabled = false,
  className = "",
}) {
  const [query, setQuery] = useState(value);
  const [options, setOptions] = useState([]);
  const [filtered, setFiltered] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    setQuery(value || "");
  }, [value]);

  useEffect(() => {
    fetchOptions();
  }, [fetchUrl]);

  const fetchOptions = async () => {
    if (!fetchUrl) return;
    try {
      setLoading(true);
      const res = await fetch(fetchUrl);
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : data.items || data.styles || data.clients || [];
        setOptions(list);
      }
    } catch (e) {
      console.warn("SmartAutocomplete fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!query) {
      setFiltered(options.slice(0, 8));
      return;
    }
    const q = query.toLowerCase();
    const matches = options.filter((item) => {
      const label = String(item[labelField] || "").toLowerCase();
      const code = String(item[codeField] || "").toLowerCase();
      const sub = String(item[subField] || "").toLowerCase();
      return label.includes(q) || code.includes(q) || sub.includes(q);
    });
    setFiltered(matches.slice(0, 10));
    setActiveIndex(0);
  }, [query, options, labelField, codeField, subField]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelectOption = (item) => {
    const displayVal = item[codeField] || item[labelField] || "";
    setQuery(displayVal);
    setIsOpen(false);
    if (onChange) onChange(displayVal);
    if (onSelect) onSelect(item);
  };

  const handleKeyDown = (e) => {
    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % Math.max(1, filtered.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + filtered.length) % Math.max(1, filtered.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[activeIndex]) {
        handleSelectOption(filtered[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  return (
    <div ref={containerRef} className={`relative w-full ${className}`}>
      <div className="relative">
        <input
          type="text"
          disabled={disabled}
          value={query}
          placeholder={placeholder}
          onFocus={() => setIsOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            if (onChange) onChange(e.target.value);
          }}
          onKeyDown={handleKeyDown}
          className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors pr-9"
        />
        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
          ) : (
            <Search className="w-4 h-4" />
          )}
        </div>
      </div>

      {/* Autocomplete Dropdown List */}
      {isOpen && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl max-h-60 overflow-y-auto p-1.5 animate-in fade-in-50 zoom-in-95 duration-100">
          {filtered.map((item, idx) => {
            const isSelected = activeIndex === idx;
            const code = item[codeField];
            const label = item[labelField];
            const sub = item[subField];

            return (
              <div
                key={idx}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => handleSelectOption(item)}
                className={`px-3 py-2 rounded-xl text-xs flex items-center justify-between cursor-pointer transition-colors ${
                  isSelected ? "bg-blue-600 text-white" : "hover:bg-slate-800 text-slate-200"
                }`}
              >
                <div>
                  <div className="font-bold flex items-center gap-1.5">
                    {code && <span>{code}</span>}
                    {label && code !== label && (
                      <span className={isSelected ? "text-blue-100 font-normal" : "text-slate-400 font-normal"}>
                        — {label}
                      </span>
                    )}
                  </div>
                  {sub && (
                    <div className={`text-[10px] mt-0.5 ${isSelected ? "text-blue-200" : "text-slate-500"}`}>
                      {sub}
                    </div>
                  )}
                </div>

                {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
