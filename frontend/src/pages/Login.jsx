import { useState } from "react";
import { useAuth } from "../lib/auth";
import { Loader2 } from "lucide-react";

export default function Login() {
  const { login, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    await login(email, password);
    setBusy(false);
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

            <div className="mt-6 border-t border-slate-200 pt-4">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold mb-2">Seeded Admin (Dev)</div>
              <div className="flex items-center justify-between gap-2 text-xs text-slate-600 font-mono bg-slate-50 border border-slate-200 px-3 py-2">
                <div>
                  <div><span className="text-slate-400">email:</span> admin@example.com</div>
                  <div><span className="text-slate-400">pass&nbsp;:</span> admin123</div>
                </div>
                <button
                  type="button"
                  data-testid="login-autofill"
                  onClick={() => { setEmail("admin@example.com"); setPassword("admin123"); }}
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
    </div>
  );
}
