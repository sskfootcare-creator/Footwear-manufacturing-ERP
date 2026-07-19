import { useState, useRef, useEffect, useId } from "react";

/**
 * SearchableSelect — drop-in replacement for long raw <select> lists.
 *
 * Props
 * ─────
 * options      {Array}    All options.
 * value        {any}      Currently selected option's key (from getKey).
 * onChange     {Function} (key) => void  — called when user picks an option.
 * getKey       {Function} (opt) => string|number  — unique key.
 * getLabel     {Function} (opt) => string  — displayed in the text box + dropdown.
 * renderOption {Function} (opt) => ReactNode  — optional richer row in dropdown.
 * placeholder  {string}   Placeholder text when nothing is selected.
 * disabled     {bool}
 * testId       {string}
 * className    {string}   Extra class on the root wrapper.
 */
export default function SearchableSelect({
  options = [],
  value,
  onChange,
  getKey    = (o) => o.id,
  getLabel  = (o) => String(o),
  renderOption,
  placeholder = "— search & pick —",
  disabled = false,
  testId,
  className = "",
}) {
  const [query, setQuery]       = useState("");
  const [open, setOpen]         = useState(false);
  const inputRef  = useRef(null);
  const listRef   = useRef(null);
  const wrapRef   = useRef(null);
  const listId    = useId();

  const selected = options.find((o) => getKey(o) === value);

  // When the dropdown opens, reset the query so all options show
  const handleFocus = () => {
    if (!disabled) {
      setQuery("");
      setOpen(true);
    }
  };

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [open]);

  // Filter options
  const filtered = query.trim()
    ? options.filter((o) =>
        getLabel(o).toLowerCase().includes(query.trim().toLowerCase())
      )
    : options;

  const pick = (opt) => {
    onChange(getKey(opt));
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
  };

  const displayValue = open ? query : (selected ? getLabel(selected) : "");

  return (
    <div ref={wrapRef} className={`relative ${className}`} data-testid={testId}>
      {/* Text input acting as the combobox trigger */}
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        autoComplete="off"
        disabled={disabled}
        placeholder={selected ? getLabel(selected) : placeholder}
        value={displayValue}
        onFocus={handleFocus}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "Escape") { setOpen(false); setQuery(""); }
          if (e.key === "Enter" && filtered.length === 1) { e.preventDefault(); pick(filtered[0]); }
        }}
        className={`w-full border-2 border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-[#2563EB] focus:outline-none font-mono min-h-[44px] ${
          disabled ? "opacity-50 cursor-not-allowed bg-slate-50" : ""
        }`}
        data-testid={testId ? `${testId}-input` : undefined}
      />

      {/* Dropdown list */}
      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="absolute z-[200] w-full bg-white border-2 border-slate-300 shadow-xl max-h-60 overflow-y-auto"
          style={{ top: "calc(100% + 2px)" }}
        >
          {filtered.length === 0 ? (
            <li className="px-3 py-3 text-xs text-slate-400 italic">No matches.</li>
          ) : (
            filtered.map((opt) => {
              const key = getKey(opt);
              const isSelected = key === value;
              return (
                <li
                  key={key}
                  role="option"
                  aria-selected={isSelected}
                  onMouseDown={(e) => { e.preventDefault(); pick(opt); }}
                  onTouchEnd={(e) => { e.preventDefault(); pick(opt); }}
                  className={`px-3 py-2.5 text-xs cursor-pointer select-none flex items-center justify-between gap-2 min-h-[44px] ${
                    isSelected
                      ? "bg-[#0F172A] text-white"
                      : "hover:bg-slate-100 active:bg-slate-200 text-slate-800"
                  }`}
                  data-testid={testId ? `${testId}-opt-${key}` : undefined}
                >
                  {renderOption ? renderOption(opt) : (
                    <span className="font-mono">{getLabel(opt)}</span>
                  )}
                  {isSelected && (
                    <span className="text-[10px] font-bold shrink-0">✓</span>
                  )}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
