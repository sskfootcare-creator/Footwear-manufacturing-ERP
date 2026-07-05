import { useNavigate } from "react-router-dom";
import { Factory, ShoppingBag, BarChart3, ArrowRight } from "lucide-react";
import { Card } from "../components/ui-kit";

export default function SelectWorkspace() {
  const nav = useNavigate();

  const handleSelect = (workspace) => {
    localStorage.setItem("workspace", workspace);
    // Send event to let AppShell know workspace changed if it's currently loaded
    window.dispatchEvent(new Event("workspaceChanged"));
    nav("/");
  };

  const options = [
    {
      key: "b2b",
      title: "B2B Manufacturing",
      desc: "Track purchase orders, bills of materials (BOM), karigar (worker) operations, and bulk production floor tasks.",
      icon: Factory,
      color: "border-blue-500 text-blue-500 bg-blue-50/50 hover:bg-blue-50 hover:border-blue-600",
    },
    {
      key: "online",
      title: "Online Commerce",
      desc: "Manage online marketplace orders (Myntra, Flipkart, Nykaa, Website), SKU maps, and direct order fulfillment.",
      icon: ShoppingBag,
      color: "border-pink-500 text-pink-500 bg-pink-50/50 hover:bg-pink-50 hover:border-pink-600",
    },
    {
      key: "management",
      title: "Management Dashboard",
      desc: "Complete operational overview including live financial reports, client tally ledgers, invoices, settings, and users.",
      icon: BarChart3,
      color: "border-amber-500 text-amber-500 bg-amber-50/50 hover:bg-amber-50 hover:border-amber-600",
    },
  ];

  return (
    <div className="min-h-screen bg-[#F7F7F5] flex flex-col justify-between p-6 sm:p-12">
      {/* Top logo */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-[#0F172A] text-[#C27842] grid place-items-center font-black text-xl shadow-ind">SS</div>
        <div>
          <div className="font-black tracking-tight text-lg text-slate-900">SSK FOOTCARE</div>
          <div className="text-xs text-slate-500 uppercase tracking-[0.2em]">Management ERP</div>
        </div>
      </div>

      {/* Main choice area */}
      <div className="max-w-5xl w-full mx-auto my-12">
        <div className="text-center mb-10">
          <div className="text-xs uppercase tracking-[0.25em] text-slate-500 font-bold mb-2">Workspace Entry</div>
          <h1 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">Select your active workspace.</h1>
          <p className="text-sm text-slate-600 mt-2">You can easily switch workspace again later from the sidebar.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {options.map((opt) => {
            const Icon = opt.icon;
            return (
              <Card
                key={opt.key}
                onClick={() => handleSelect(opt.key)}
                className={`p-6 sm:p-8 cursor-pointer border-2 transition-all duration-300 transform hover:-translate-y-1 hover:shadow-lg flex flex-col justify-between h-80 ${opt.color}`}
                data-testid={`workspace-select-${opt.key}`}
              >
                <div>
                  <div className="w-12 h-12 bg-white rounded-xl shadow-sm border border-slate-100 flex items-center justify-center mb-5">
                    <Icon className="w-6 h-6" />
                  </div>
                  <h2 className="text-xl font-bold text-slate-900 mb-3">{opt.title}</h2>
                  <p className="text-xs text-slate-600 leading-relaxed">{opt.desc}</p>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider mt-4">
                  Enter workspace <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-xs text-slate-400 uppercase tracking-[0.2em]">
        © SSK Footcare Manufacturing LLP
      </div>
    </div>
  );
}
