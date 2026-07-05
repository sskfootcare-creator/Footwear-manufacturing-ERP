import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { LayoutDashboard, Boxes, Layers, Calculator, FileText, Hammer, Users, LogOut, Factory, AlertOctagon, BarChart3, HardHat, Warehouse, IndianRupee, Settings as SettingsIcon, Receipt, BookOpen, Truck } from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, roles: ["admin", "manager", "production", "sales"] },
  { to: "/styles", label: "Styles", icon: Layers, roles: ["admin", "manager", "sales"] },
  { to: "/materials", label: "Materials", icon: Boxes, roles: ["admin", "manager"] },
  { to: "/inventory", label: "Inventory", icon: Warehouse, roles: ["admin", "manager", "production"] },
  { to: "/workers", label: "Karigars", icon: HardHat, roles: ["admin", "manager", "production"] },
  { to: "/costing", label: "Costing", icon: Calculator, roles: ["admin", "manager"] },
  { to: "/pos", label: "Purchase Orders", icon: FileText, roles: ["admin", "manager", "sales"] },
  { to: "/production", label: "Production", icon: Hammer, roles: ["admin", "manager", "production"] },
  { to: "/defects", label: "Defects & QC", icon: AlertOctagon, roles: ["admin", "manager", "production"] },
  { to: "/payroll", label: "Payroll", icon: IndianRupee, roles: ["admin", "manager"] },
  { to: "/invoices", label: "Invoices", icon: Receipt, roles: ["admin", "manager", "sales"] },
  { to: "/clients", label: "Clients", icon: BookOpen, roles: ["admin", "manager", "sales"] },
  { to: "/vendors", label: "Vendors", icon: Truck, roles: ["admin", "manager"] },
  { to: "/vendor-pos", label: "Vendor POs", icon: FileText, roles: ["admin", "manager"] },
  { to: "/reports", label: "Reports", icon: BarChart3, roles: ["admin", "manager"] },
  { to: "/settings", label: "Settings", icon: SettingsIcon, roles: ["admin", "manager"] },
  { to: "/users", label: "Users", icon: Users, roles: ["admin"] },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  const doLogout = async () => {
    await logout();
    nav("/login");
  };

  return (
    <div className="min-h-screen flex bg-[#F7F7F5]">
      <aside className="w-64 bg-[#0F172A] text-slate-300 flex flex-col sticky top-0 h-screen" data-testid="sidebar">
        <div className="px-5 py-5 border-b border-slate-800 flex items-center gap-3">
          <div className="w-10 h-10 bg-[#C27842] text-white grid place-items-center font-black">
            <Factory className="w-5 h-5" />
          </div>
          <div>
            <div className="font-black text-white tracking-tight">SSK FOOTCARE</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">ERP v1.0</div>
          </div>
        </div>

        <nav className="flex-1 py-3 overflow-y-auto">
          {navItems
            .filter((n) => !user?.role || n.roles.includes(user.role))
            .map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                data-testid={`nav-${n.label.toLowerCase().replace(/\s+/g, "-")}`}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-5 py-3 text-sm border-l-4 transition-colors ${
                    isActive
                      ? "bg-slate-800 text-white border-[#C27842]"
                      : "border-transparent hover:bg-slate-800 hover:text-white hover:border-[#C27842]/50"
                  }`
                }
              >
                <n.icon className="w-4 h-4" />
                <span className="font-medium">{n.label}</span>
              </NavLink>
            ))}
        </nav>

        <div className="border-t border-slate-800 p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 bg-[#C27842] text-white grid place-items-center font-bold">
              {user?.name?.[0]?.toUpperCase() || "U"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-white truncate">{user?.name}</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{user?.role}</div>
            </div>
          </div>
          <button
            onClick={doLogout}
            data-testid="logout-btn"
            className="w-full flex items-center justify-center gap-2 text-xs uppercase tracking-wider font-bold py-2 border border-slate-700 hover:border-[#C27842] hover:text-white transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" /> Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 min-w-0" data-testid="main-content">
        <Outlet />
      </main>
    </div>
  );
}
