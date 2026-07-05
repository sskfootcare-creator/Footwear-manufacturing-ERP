export function PageHeader({ title, subtitle, action, testId }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b-2 border-slate-200 px-4 sm:px-8 py-4 sm:py-6 bg-white" data-testid={testId}>
      <div>
        <div className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-slate-500 font-bold mb-1">SSK / {subtitle || title}</div>
        <h1 className="text-xl sm:text-3xl font-black tracking-tight">{title}</h1>
      </div>
      <div>{action}</div>
    </div>
  );
}

export function BtnPrimary({ children, className = "", ...rest }) {
  return (
    <button
      className={`bg-[#0F172A] text-white font-bold uppercase tracking-wider text-xs px-5 py-2.5 border-2 border-[#0F172A] shadow-ind hover:shadow-ind-lg hover:-translate-x-0.5 hover:-translate-y-0.5 transition-all active:shadow-none active:translate-x-0.5 active:translate-y-0.5 disabled:opacity-50 ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function BtnSecondary({ children, className = "", ...rest }) {
  return (
    <button
      className={`bg-white text-slate-900 font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-slate-300 hover:border-[#0F172A] transition-colors ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "", style, ...rest }) {
  return (
    <div className={`bg-white border-2 border-slate-200 ${className}`} style={style} {...rest}>{children}</div>
  );
}

export function StatTile({ label, value, sub, accent = "#C27842", testId }) {
  return (
    <Card className="p-3 sm:p-5 relative overflow-hidden" >
      <div data-testid={testId}>
        <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate">{label}</div>
        <div className="font-mono text-lg sm:text-2xl lg:text-3xl font-bold mt-2 truncate" title={String(value)}>{value}</div>
        {sub && <div className="text-xs text-slate-500 mt-1 truncate" title={String(sub)}>{sub}</div>}
      </div>
      <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: accent }} />
    </Card>
  );
}

export function Input({ label, testId, className = "", ...rest }) {
  return (
    <div className="space-y-1">
      {label && <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">{label}</div>}
      <input
        data-testid={testId}
        className={`w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none font-mono ${className}`}
        {...rest}
      />
    </div>
  );
}

export function Select({ label, testId, children, className = "", ...rest }) {
  return (
    <div className="space-y-1">
      {label && <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">{label}</div>}
      <select
        data-testid={testId}
        className={`w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none ${className}`}
        {...rest}
      >
        {children}
      </select>
    </div>
  );
}

export function Badge({ children, color = "slate" }) {
  const map = {
    slate: "bg-slate-100 text-slate-800 border-slate-300",
    green: "bg-green-100 text-green-800 border-green-300",
    yellow: "bg-yellow-100 text-yellow-800 border-yellow-300",
    red: "bg-red-100 text-red-800 border-red-300",
    blue: "bg-blue-100 text-blue-800 border-blue-300",
    orange: "bg-orange-100 text-orange-800 border-orange-300",
  };
  return <span className={`inline-block px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${map[color]}`}>{children}</span>;
}

export function ConfirmDialog({ open, title = "Confirm Action", message, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-black/40 p-4" data-testid="confirm-dialog">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-sm">
        <div className="px-5 py-4 border-b-2 border-slate-200">
          <div className="text-[10px] uppercase tracking-[0.2em] text-[#DC2626] font-bold">Confirmation Required</div>
          <div className="font-bold text-base mt-1">{title}</div>
        </div>
        <div className="p-5 text-sm text-slate-600 leading-relaxed">
          {message}
        </div>
        <div className="px-5 py-4 bg-slate-50 border-t border-slate-200 flex gap-2 justify-end">
          <BtnSecondary onClick={onCancel}>Cancel</BtnSecondary>
          <button
            onClick={onConfirm}
            className="bg-[#DC2626] text-white font-bold uppercase tracking-wider text-xs px-5 py-2.5 border-2 border-[#DC2626] shadow-ind hover:bg-[#B91C1C] hover:border-[#B91C1C] transition-all"
            data-testid="confirm-dialog-yes"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
