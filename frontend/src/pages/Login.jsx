import { useState } from "react";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Loader2 } from "lucide-react";

export default function Login() {
  const { login, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotBusy, setForgotBusy] = useState(false);
  const [forgotResult, setForgotResult] = useState(null); // {message, dev_reset_url?}

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    await login(email, password);
    setBusy(false);
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    setForgotBusy(true);
    setForgotResult(null);
    try {
      const { data } = await http.post("/auth/forgot-password", { email: forgotEmail });
      setForgotResult({
        message: data?.message || "If that email matches an account, a reset link has been sent.",
        dev_reset_url: data?.dev_reset_url || null,
        email_status: data?.email_status || null,
      });
    } catch (err) {
      setForgotResult({
        message:
          err.response?.data?.detail ||
          err.message ||
          "Could not send reset link. Please try again.",
      });
    } finally {
      setForgotBusy(false);
    }
  };

  return (
    <div className="grid md:grid-cols-2 min-h-screen">
      <div className="flex flex-col justify-between p-10 bg-white">
        <div>
          <div className="flex items-center gap-3" data-testid="login-logo">
            <div className="w-10 h-10 bg-[#0F172A] text-[#C27842] grid place-items-center font-black text-xl shadow-ind">SS</div>
            <div>
              <div className="font-black tracking-tight text-lg">SSK FOOTCARE</div>
              <div className="text-xs text-slate-500 uppercase tracking-[0.2em]">Manufacturing System</div>
            </div>
          </div>
        </div>

        <div className="max-w-sm w-full mx-auto">
          <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">Sign In</div>
          <h1 className="text-4xl font-black mb-1">Welcome back.</h1>
          <p className="text-sm text-slate-600 mb-8">Operations console for the production floor.</p>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="text-xs uppercase tracking-wider font-bold text-slate-600">Email</label>
              <input
                data-testid="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full mt-1 border-2 border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-[#2563EB] focus:outline-none font-mono text-sm"
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider font-bold text-slate-600">Password</label>
              <input
                data-testid="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full mt-1 border-2 border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-[#2563EB] focus:outline-none font-mono text-sm"
              />
            </div>

            {error && (
              <div data-testid="login-error" className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2">
                {error}
              </div>
            )}

            <button
              data-testid="login-submit"
              disabled={busy}
              className="w-full bg-[#0F172A] text-white font-bold uppercase tracking-wider text-sm py-3 border-2 border-[#0F172A] shadow-ind hover:shadow-ind-lg hover:-translate-x-0.5 hover:-translate-y-0.5 transition-all active:shadow-none active:translate-x-0.5 active:translate-y-0.5 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Sign in
            </button>

            <div className="text-right">
              <button
                type="button"
                data-testid="forgot-password-link"
                onClick={() => { setForgotOpen(true); setForgotEmail(email); setForgotResult(null); }}
                className="text-xs uppercase tracking-wider font-bold text-[#2563EB] hover:text-[#1D4ED8]"
              >
                Forgot password?
              </button>
            </div>

            <div className="mt-6 border-t border-slate-200 pt-4">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold mb-2">Seeded Admin (Dev)</div>
              <div className="flex items-center justify-between gap-2 text-xs text-slate-600 font-mono bg-slate-50 border border-slate-200 px-3 py-2">
                <div>
                  <div><span className="text-slate-400">email:</span> admin@ssk.com</div>
                  <div><span className="text-slate-400">pass&nbsp;:</span> admin1234</div>
                </div>
                <button
                  type="button"
                  data-testid="login-autofill"
                  onClick={() => { setEmail("admin@ssk.com"); setPassword("admin1234"); }}
                  className="text-[10px] uppercase font-bold text-[#2563EB] hover:text-[#1D4ED8] tracking-wider"
                >
                  Autofill
                </button>
              </div>
            </div>


          </form>
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
            <div className="text-xs uppercase tracking-[0.3em] text-[#C27842] mb-2 font-bold">Workshop Console</div>
            <h2 className="text-3xl font-black mb-3 leading-tight">From cut to dispatch — one tight system.</h2>
            <p className="text-sm text-slate-300">
              Track every pair from BOM to packed box. Replace your master sheet. Run your floor.
            </p>
          </div>
        </div>
      </div>

      {forgotOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setForgotOpen(false)}
          data-testid="forgot-password-modal"
        >
          <div
            className="bg-white w-full max-w-md border-2 border-[#0F172A] shadow-ind-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b-2 border-[#0F172A] flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Password Reset</div>
                <h3 className="text-xl font-black">Forgot your password?</h3>
              </div>
              <button
                type="button"
                onClick={() => setForgotOpen(false)}
                className="text-slate-500 hover:text-slate-900 text-lg font-bold"
              >×</button>
            </div>
            <form onSubmit={submitForgot} className="p-6 space-y-4">
              <p className="text-sm text-slate-600">
                Enter your account email — we&apos;ll email a single-use reset link that expires in 1 hour.
              </p>
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-600">Email</label>
                <input
                  data-testid="forgot-email-input"
                  type="email"
                  required
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  className="w-full mt-1 border-2 border-slate-300 bg-white px-4 py-2.5 text-slate-900 focus:border-[#2563EB] focus:outline-none font-mono text-sm"
                />
              </div>

              {forgotResult && (
                <div
                  className="text-sm bg-slate-50 border-2 border-slate-300 px-3 py-2 space-y-1"
                  data-testid="forgot-result"
                >
                  <div className="font-semibold">{forgotResult.message}</div>
                  {forgotResult.email_status === "email_not_configured" && forgotResult.dev_reset_url && (
                    <div className="text-xs text-amber-900 bg-amber-50 border border-amber-300 px-2 py-1.5">
                      <strong>Email service isn&apos;t configured</strong> — set <code>GMAIL_USER</code> +
                      {" "}<code>GMAIL_APP_PASSWORD</code> in <code>backend/.env</code>. Meanwhile
                      the admin can hand-deliver this reset link:
                      <div className="mt-1 break-all font-mono text-[11px] text-slate-800 bg-white border border-slate-300 px-2 py-1">
                        <a href={forgotResult.dev_reset_url} target="_blank" rel="noreferrer" className="underline">
                          {forgotResult.dev_reset_url}
                        </a>
                      </div>
                    </div>
                  )}
                  {forgotResult.email_status && forgotResult.email_status !== "email_not_configured" && (
                    <div className="text-xs text-red-800">
                      Email delivery failed ({forgotResult.email_status}). Please try again or contact your admin.
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setForgotOpen(false)}
                  className="flex-1 border-2 border-slate-300 text-slate-700 font-bold uppercase tracking-wider text-xs py-2.5 hover:border-slate-500"
                >
                  Close
                </button>
                <button
                  type="submit"
                  data-testid="forgot-submit"
                  disabled={forgotBusy}
                  className="flex-1 bg-[#0F172A] text-white font-bold uppercase tracking-wider text-xs py-2.5 border-2 border-[#0F172A] hover:shadow-ind disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {forgotBusy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Send reset link
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
