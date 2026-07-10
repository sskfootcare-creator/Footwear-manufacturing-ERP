import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { http } from "../lib/api";
import { Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

/**
 * /reset-password?token=xxx
 * Consumes a single-use reset token, prompts for a new password, then
 * bounces to /login on success.
 */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) setError("This reset link is missing its token. Please open the link from your email.");
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) return setError("Password must be at least 8 characters long.");
    if (password !== confirm) return setError("Passwords do not match.");
    setBusy(true);
    try {
      await http.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
      setTimeout(() => navigate("/login"), 2500);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Could not reset password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid md:grid-cols-2 min-h-screen">
      <div className="flex flex-col justify-between p-10 bg-white">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#0F172A] text-[#C27842] grid place-items-center font-black text-xl shadow-ind">SS</div>
            <div>
              <div className="font-black tracking-tight text-lg">SSK FOOTCARE</div>
              <div className="text-xs text-slate-500 uppercase tracking-[0.2em]">Manufacturing System</div>
            </div>
          </div>
        </div>

        <div className="max-w-sm w-full mx-auto">
          <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Password Reset</div>
          <h1 className="text-4xl font-black mb-1">Choose a new password.</h1>
          <p className="text-sm text-slate-600 mb-8">Your reset link expires in 1 hour and can only be used once.</p>

          {done ? (
            <div
              className="p-4 border-2 border-emerald-500 bg-emerald-50 text-emerald-900 flex items-start gap-3"
              data-testid="reset-success"
            >
              <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">Password updated.</div>
                <div className="text-xs mt-1">Redirecting to sign in…</div>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-600">New password</label>
                <input
                  data-testid="reset-password-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full mt-1 border-2 border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-[#2563EB] focus:outline-none font-mono text-sm"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-600">Confirm new password</label>
                <input
                  data-testid="reset-confirm-input"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={8}
                  className="w-full mt-1 border-2 border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-[#2563EB] focus:outline-none font-mono text-sm"
                />
              </div>

              {error && (
                <div
                  data-testid="reset-error"
                  className="text-sm text-red-800 bg-red-50 border-2 border-red-300 px-3 py-2 flex items-start gap-2"
                >
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              <button
                data-testid="reset-submit"
                disabled={busy || !token}
                className="w-full bg-[#0F172A] text-white font-bold uppercase tracking-wider text-sm py-3 border-2 border-[#0F172A] shadow-ind hover:shadow-ind-lg hover:-translate-x-0.5 hover:-translate-y-0.5 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                Set new password
              </button>

              <div className="text-right">
                <button
                  type="button"
                  onClick={() => navigate("/login")}
                  className="text-xs uppercase tracking-wider font-bold text-slate-500 hover:text-slate-900"
                >
                  Back to sign in
                </button>
              </div>
            </form>
          )}
        </div>

        <div className="text-xs text-slate-400 uppercase tracking-[0.2em]">© SSK Footcare Manufacturing LLP</div>
      </div>

      <div
        className="hidden md:block relative bg-cover bg-center"
        style={{ backgroundImage: "url('https://images.pexels.com/photos/33387259/pexels-photo-33387259.jpeg')" }}
      >
        <div className="absolute inset-0 bg-[#0F172A]/70" />
        <div className="relative h-full flex flex-col justify-end p-10 text-white">
          <div className="border-l-4 border-[#C27842] pl-4 max-w-md">
            <div className="text-xs uppercase tracking-[0.3em] text-[#C27842] mb-2 font-bold">Secure Reset</div>
            <h2 className="text-3xl font-black mb-3 leading-tight">One-time use. One-hour window.</h2>
            <p className="text-sm text-slate-300">
              Your reset link is single-use and expires quickly. If it stopped working, just request a new one.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
