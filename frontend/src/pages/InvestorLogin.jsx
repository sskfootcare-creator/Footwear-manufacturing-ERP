import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { http, friendlyAxiosError } from "@/lib/api";
import { Loader2, Landmark, ShieldCheck, ArrowRight } from "lucide-react";

export default function InvestorLogin() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("ident"); // "ident" | "pin"
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pinInputRef = useRef(null);

  const handleIdentNext = (e) => {
    if (e) e.preventDefault();
    if (!identifier.trim()) {
      setError("Please enter your registered phone or email");
      return;
    }
    setError("");
    setStep("pin");
    setTimeout(() => pinInputRef.current?.focus(), 100);
  };

  const handleLogin = useCallback(async (e) => {
    if (e) e.preventDefault();
    if (pin.length < 4) {
      setError("PIN must be 4–6 digits");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const { data } = await http.post("/auth/investor-login", {
        identifier: identifier.trim(),
        pin: pin.trim(),
      });
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("investor_token", data.access_token);
        localStorage.setItem("investor_user", JSON.stringify({
          investor_id: data.investor_id,
          name: data.name,
          role: "investor",
        }));
      }
      navigate("/investor", { replace: true });
    } catch (err) {
      setError(friendlyAxiosError(err));
      setPin("");
    } finally {
      setLoading(false);
    }
  }, [identifier, pin, navigate]);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center px-4 relative overflow-hidden font-sans">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-600/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 left-1/3 w-80 h-80 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        {/* Header Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-tr from-emerald-500/20 to-blue-500/20 border border-emerald-500/30 text-emerald-400 mb-4 shadow-lg shadow-emerald-950/50">
            <Landmark className="w-8 h-8" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">SSK Capital Partner Portal</h1>
          <p className="text-sm text-slate-400 mt-1">Secured, read-only investor dashboard</p>
        </div>

        {/* Card */}
        <div className="bg-slate-900/80 backdrop-blur-xl border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl">
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs sm:text-sm font-medium">
              {error}
            </div>
          )}

          {step === "ident" ? (
            <form onSubmit={handleIdentNext} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                  Phone Number or Email
                </label>
                <input
                  type="text"
                  autoFocus
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="e.g. 9876543210 or investor@domain.com"
                  className="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 text-sm transition"
                />
              </div>

              <button
                type="submit"
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-medium rounded-xl text-sm transition shadow-lg shadow-emerald-900/30 flex items-center justify-center gap-2"
              >
                <span>Continue</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
                  Enter 4–6 Digit PIN
                </label>
                <button
                  type="button"
                  onClick={() => { setStep("ident"); setPin(""); setError(""); }}
                  className="text-xs text-emerald-400 hover:underline"
                >
                  Change Account
                </button>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-400 truncate">
                Logging in as: <span className="text-white font-mono">{identifier}</span>
              </div>

              <input
                ref={pinInputRef}
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                placeholder="••••"
                className="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-white text-center tracking-[0.5em] text-2xl font-mono focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
              />

              <button
                type="submit"
                disabled={loading || pin.length < 4}
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white font-medium rounded-xl text-sm transition shadow-lg shadow-emerald-900/30 flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                <span>Authorize & Sign In</span>
              </button>
            </form>
          )}

          <div className="mt-6 pt-5 border-t border-slate-800/80 text-center">
            <span className="text-xs text-slate-500">
              Internal Manufacturing ERP • Strictly Confidential
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
