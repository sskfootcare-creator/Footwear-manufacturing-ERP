import { useState, useEffect, useRef, useCallback } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import {
  LayoutDashboard, Boxes, Layers, Calculator, FileText, Hammer,
  Users, LogOut, Factory, AlertOctagon, BarChart3, HardHat,
  Warehouse, IndianRupee, Settings as SettingsIcon, Receipt,
  BookOpen, Truck, ArrowLeftRight, ShoppingBag, Package,
  ClipboardList, PackageOpen, ChevronLeft, MoreHorizontal, X,
  Check,
} from "lucide-react";

/* ─────────────────────────────────────────────────────────────────────────────
   NAV GROUPS — single source of truth
   ───────────────────────────────────────────────────────────────────────────── */
const NAV_GROUPS = [
  {
    key: "core",
    title: "Core Operations",
    workspaces: ["b2b", "online", "management"],
    items: [
      { to: "/",                    label: "Dashboard",            icon: LayoutDashboard, end: true, roles: ["admin","manager","production","sales"] },
      { to: "/styles",              label: "Styles",               icon: Layers,          roles: ["admin","manager","sales"] },
      { to: "/materials",           label: "Materials",            icon: Boxes,           roles: ["admin","manager"] },
      { to: "/inventory",           label: "Raw Material Inventory",icon: Warehouse,       roles: ["admin","manager","production"] },
      { to: "/components",          label: "Component Inventory",  icon: Package,         roles: ["admin","manager","production"] },
      { to: "/workers",             label: "Workers",              icon: HardHat,         roles: ["admin","manager","production"] },
      { to: "/payroll",             label: "Payroll",              icon: IndianRupee,     roles: ["admin","manager"] },
      { to: "/listing-formats",     label: "Listing Formats",      icon: FileText,        roles: ["admin"] },
      { to: "/order-import-formats",label: "Order Import Formats", icon: FileText,        roles: ["admin"] },
      { to: "/settings",            label: "Settings",             icon: SettingsIcon,    roles: ["admin","manager"] },
      { to: "/users",               label: "Users",                icon: Users,           roles: ["admin"] },
    ],
  },
  {
    key: "b2b",
    title: "B2B Manufacturing",
    workspaces: ["b2b", "management"],
    items: [
      { to: "/pos",        label: "POs",          icon: FileText,    roles: ["admin","manager","sales"] },
      { to: "/production", label: "Production",   icon: Hammer,      roles: ["admin","manager","production"] },
      { to: "/vendors",    label: "Vendors",      icon: Truck,       roles: ["admin","manager"] },
      { to: "/vendor-pos", label: "Vendor POs",   icon: FileText,    roles: ["admin","manager"] },
      { to: "/invoices",   label: "Invoices",     icon: Receipt,     roles: ["admin","manager","sales"] },
      { to: "/expenses",   label: "Expenses & P&L",icon: IndianRupee, roles: ["admin","manager"] },
      { to: "/clients",    label: "Clients",      icon: BookOpen,    roles: ["admin","manager","sales"] },
      { to: "/costing",    label: "Costing",      icon: Calculator,  roles: ["admin","manager"] },
      { to: "/defects",    label: "Defects",      icon: AlertOctagon,roles: ["admin","manager","production"] },
      { to: "/reports",    label: "Reports",      icon: BarChart3,   roles: ["admin","manager"] },
    ],
  },
  {
    key: "online",
    title: "Online Commerce",
    workspaces: ["online", "management"],
    items: [
      { to: "/online-pipeline",      label: "Online Style Pipeline", icon: Layers,       roles: ["admin","manager"] },
      { to: "/sku-map",              label: "SKU Mapping",           icon: ArrowLeftRight,roles: ["admin","manager"] },
      { to: "/ready-stock",          label: "Ready Stock",           icon: Boxes,         roles: ["admin","manager"] },
      { to: "/online-orders",        label: "Online Orders",         icon: ShoppingBag,   roles: ["admin","manager","sales"] },
      { to: "/online-profitability", label: "Profitability",         icon: BarChart3,     roles: ["admin","manager"] },
      { to: "/warehouse",            label: "Warehouse",             icon: Warehouse,     roles: ["admin","manager","production"] },
      { to: "/picklists",            label: "Picklists",             icon: ClipboardList, roles: ["admin","manager","production"] },
      { to: "/warehouse/reports",    label: "Warehouse Reports",     icon: BarChart3,     roles: ["admin","manager"] },
      { to: "/pending-list",         label: "Pending Product List",  icon: PackageOpen,   roles: ["admin","manager","production"] },
    ],
  },
];

/* Route → page title map for mobile top bar */
const PAGE_TITLES = {
  "/":                     "Dashboard",
  "/styles":               "Styles",
  "/materials":            "Materials",
  "/inventory":            "Raw Material Inventory",
  "/components":           "Component Inventory",
  "/workers":              "Workers",
  "/payroll":              "Payroll",
  "/listing-formats":      "Listing Formats",
  "/order-import-formats": "Order Import Formats",
  "/settings":             "Settings",
  "/users":                "Users",
  "/pos":                  "Purchase Orders",
  "/production":           "Production",
  "/vendors":              "Vendors",
  "/vendor-pos":           "Vendor POs",
  "/invoices":             "Invoices",
  "/expenses":             "Expenses & P&L",
  "/clients":              "Clients",
  "/costing":              "Costing",
  "/defects":              "Defects",
  "/reports":              "Reports",
  "/online-pipeline":      "Online Style Pipeline",
  "/sku-map":              "SKU Mapping",
  "/ready-stock":          "Ready Stock",
  "/online-orders":        "Online Orders",
  "/online-profitability": "Profitability",
  "/warehouse":            "Warehouse",
  "/picklists":            "Picklists",
  "/warehouse/reports":    "Warehouse Reports",
  "/pending-list":         "Pending Product List",
};

/* Bottom tabs per workspace — first 4 items; 5th is always "More" */
const WORKSPACE_TABS = {
  b2b: [
    { to: "/",           label: "Dashboard",  icon: LayoutDashboard, end: true },
    { to: "/production", label: "Production", icon: Hammer },
    { to: "/pos",        label: "POs",        icon: FileText },
    { to: "/invoices",   label: "Invoices",   icon: Receipt },
  ],
  online: [
    { to: "/",              label: "Dashboard",     icon: LayoutDashboard, end: true },
    { to: "/online-orders", label: "Orders",        icon: ShoppingBag },
    { to: "/warehouse",     label: "Warehouse",     icon: Warehouse },
    { to: "/picklists",     label: "Picklists",     icon: ClipboardList },
  ],
  management: [
    { to: "/",        label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/reports", label: "Reports",   icon: BarChart3 },
    { to: "/invoices",label: "Invoices",  icon: Receipt },
    { to: "/styles",  label: "Styles",    icon: Layers },
  ],
};

const WORKSPACE_LABELS = {
  b2b:        "B2B Manufacturing",
  online:     "Online Commerce",
  management: "Management Dashboard",
};

/* ─────────────────────────────────────────────────────────────────────────────
   HELPERS
   ───────────────────────────────────────────────────────────────────────────── */
function useWorkspace() {
  const [workspace, setWorkspace] = useState(
    () => localStorage.getItem("workspace") || "management"
  );
  useEffect(() => {
    const handler = () =>
      setWorkspace(localStorage.getItem("workspace") || "management");
    window.addEventListener("workspaceChanged", handler);
    return () => window.removeEventListener("workspaceChanged", handler);
  }, []);
  return [workspace, setWorkspace];
}

function visibleGroups(workspace, userRole) {
  return NAV_GROUPS.map((g) => {
    if (!g.workspaces.includes(workspace)) return null;
    const items = g.items.filter(
      (n) => !userRole || n.roles.includes(userRole)
    );
    return items.length ? { ...g, items } : null;
  }).filter(Boolean);
}

/* ─────────────────────────────────────────────────────────────────────────────
   SIDEBAR CONTENT (shared between mobile drawer + desktop sidebar)
   ───────────────────────────────────────────────────────────────────────────── */
function SidebarContent({ workspace, onSwitch, onClose, user, onLogout }) {
  const groups = visibleGroups(workspace, user?.role);

  return (
    <>
      {/* Logo + close (mobile only) */}
      <div className="px-5 py-5 border-b border-slate-800 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#C27842] text-white grid place-items-center font-black">
            <Factory className="w-5 h-5" />
          </div>
          <div>
            <div className="font-black text-white tracking-tight">SSK FOOTCARE</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">ERP v1.0</div>
          </div>
        </div>
        {onClose && (
          <button
            className="lg:hidden text-slate-400 hover:text-white p-1 -mr-1"
            onClick={onClose}
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Workspace Switcher */}
      <div
        className="px-5 py-3 bg-slate-950/65 border-b border-slate-800 flex flex-col gap-1.5"
        data-testid="workspace-switcher-panel"
      >
        <span className="text-[9px] uppercase font-bold text-slate-500 tracking-wider">
          Active Workspace
        </span>
        <select
          value={workspace}
          onChange={(e) => onSwitch(e.target.value)}
          className="bg-slate-800 text-white text-xs font-semibold px-2 py-1.5 border border-slate-700 focus:outline-none w-full cursor-pointer hover:border-slate-500 transition-colors"
          data-testid="workspace-select-dropdown"
        >
          <option value="b2b">B2B Manufacturing</option>
          <option value="online">Online Commerce</option>
          <option value="management">Management Dashboard</option>
        </select>
      </div>

      {/* Nav links */}
      <nav className="flex-1 py-3 overflow-y-auto space-y-4">
        {groups.map((group) => (
          <div key={group.key} className="space-y-1">
            <div className="px-5 py-1 text-[9px] uppercase tracking-wider font-black text-slate-500">
              {group.title}
            </div>
            {group.items.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                onClick={onClose}
                data-testid={`nav-${n.label.toLowerCase().replace(/\s+/g, "-")}`}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-5 py-2 text-xs border-l-4 transition-colors ${
                    isActive
                      ? "bg-slate-800 text-white border-[#C27842]"
                      : "border-transparent text-slate-400 hover:bg-slate-800 hover:text-white hover:border-[#C27842]/50"
                  }`
                }
              >
                <n.icon className="w-3.5 h-3.5" />
                <span className="font-semibold">{n.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* User footer */}
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
          onClick={onLogout}
          data-testid="logout-btn"
          className="w-full flex items-center justify-center gap-2 text-xs uppercase tracking-wider font-bold py-2 border border-slate-700 hover:border-[#C27842] hover:text-white transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" /> Sign out
        </button>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   MOBILE: MORE DRAWER (slide-up panel with all nav groups)
   ───────────────────────────────────────────────────────────────────────────── */
function MoreDrawer({ open, onClose, workspace, user }) {
  const drawerRef = useRef(null);
  const groups = visibleGroups(workspace, user?.role);

  // Lock body scroll while open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  return (
    <div
      className={`fixed inset-0 z-50 lg:hidden transition-all duration-300 ${
        open ? "visible" : "invisible pointer-events-none"
      }`}
      role="dialog"
      aria-modal="true"
      aria-label="More navigation"
    >
      {/* Scrim */}
      <div
        className={`absolute inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity duration-300 ${
          open ? "opacity-100" : "opacity-0"
        }`}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        ref={drawerRef}
        className={`absolute bottom-0 left-0 right-0 bg-[#0F172A] text-slate-300 rounded-t-2xl overflow-hidden flex flex-col transition-transform duration-300 ease-out ${
          open ? "translate-y-0" : "translate-y-full"
        }`}
        style={{ maxHeight: "75vh" }}
      >
        {/* Handle + header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-1 h-4 bg-[#C27842] rounded" />
            <span className="text-sm font-black text-white tracking-tight">All Sections</span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-2 -mr-2 transition-colors"
            aria-label="Close"
            style={{ minHeight: 44, minWidth: 44, display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drag indicator */}
        <div className="absolute top-2 left-1/2 -translate-x-1/2 w-10 h-1 bg-slate-700 rounded-full" />

        {/* Scrollable groups */}
        <div className="overflow-y-auto flex-1 py-3 space-y-4 pb-safe">
          {groups.map((group) => (
            <div key={group.key} className="space-y-0.5">
              <div className="px-5 py-1.5 text-[9px] uppercase tracking-[0.2em] font-black text-slate-500">
                {group.title}
              </div>
              {group.items.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.end}
                  onClick={onClose}
                  data-testid={`mobile-nav-${n.label.toLowerCase().replace(/\s+/g, "-")}`}
                  className={({ isActive }) =>
                    `flex items-center gap-4 px-5 transition-colors ${
                      isActive
                        ? "bg-slate-800 text-white border-l-4 border-[#C27842]"
                        : "border-l-4 border-transparent text-slate-400 hover:bg-slate-800/60 hover:text-white"
                    }`
                  }
                  style={{ minHeight: 48 }}
                >
                  <n.icon className="w-4 h-4 flex-shrink-0" />
                  <span className="text-sm font-semibold">{n.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
          {/* Bottom safe area padding */}
          <div style={{ height: "env(safe-area-inset-bottom, 0px)" }} />
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   MOBILE: USER MENU POPOVER (top-right of top bar)
   ───────────────────────────────────────────────────────────────────────────── */
function UserMenuPopover({ user, workspace, onSwitch, onLogout, open, onToggle }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onToggle();
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [open, onToggle]);

  const workspaceOptions = [
    { key: "b2b",        label: "B2B Manufacturing" },
    { key: "online",     label: "Online Commerce" },
    { key: "management", label: "Management Dashboard" },
  ];

  return (
    <div className="relative" ref={ref}>
      {/* Avatar button */}
      <button
        onClick={onToggle}
        data-testid="user-menu-btn"
        aria-label="User menu"
        className="w-9 h-9 bg-[#C27842] text-white grid place-items-center font-bold text-sm rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C27842] active:scale-95 transition-transform"
      >
        {user?.name?.[0]?.toUpperCase() || "U"}
      </button>

      {/* Dropdown */}
      <div
        className={`absolute right-0 top-full mt-2 w-72 bg-[#0F172A] border border-slate-700 rounded-lg shadow-2xl z-50 overflow-hidden transition-all duration-200 origin-top-right ${
          open ? "opacity-100 scale-100 pointer-events-auto" : "opacity-0 scale-95 pointer-events-none"
        }`}
      >
        {/* User info */}
        <div className="px-4 py-3 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#C27842] text-white grid place-items-center font-bold flex-shrink-0">
              {user?.name?.[0]?.toUpperCase() || "U"}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white truncate">{user?.name}</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{user?.role}</div>
            </div>
          </div>
        </div>

        {/* Workspace selector */}
        <div className="px-4 py-3 border-b border-slate-800">
          <div className="text-[9px] uppercase font-bold text-slate-500 tracking-wider mb-2">
            Active Workspace
          </div>
          <div className="space-y-1">
            {workspaceOptions.map((opt) => (
              <button
                key={opt.key}
                onClick={() => { onSwitch(opt.key); onToggle(); }}
                data-testid={`ws-switch-${opt.key}`}
                className={`w-full flex items-center justify-between px-3 transition-colors rounded ${
                  workspace === opt.key
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-white"
                }`}
                style={{ minHeight: 44 }}
              >
                <span className="text-sm font-semibold">{opt.label}</span>
                {workspace === opt.key && (
                  <Check className="w-4 h-4 text-[#C27842] flex-shrink-0" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Logout */}
        <div className="p-3">
          <button
            onClick={onLogout}
            data-testid="logout-btn-mobile"
            className="w-full flex items-center gap-3 px-3 text-slate-400 hover:text-red-400 transition-colors rounded hover:bg-slate-800/60"
            style={{ minHeight: 44 }}
          >
            <LogOut className="w-4 h-4 flex-shrink-0" />
            <span className="text-sm font-semibold">Sign out</span>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   MOBILE: BOTTOM TAB BAR
   ───────────────────────────────────────────────────────────────────────────── */
function BottomTabBar({ workspace, onMoreOpen, userRole }) {
  const tabs = (WORKSPACE_TABS[workspace] || WORKSPACE_TABS.management).filter(
    (t) => {
      // Find the nav item and check role
      if (!userRole) return true;
      const allItems = NAV_GROUPS.flatMap((g) => g.items);
      const navItem = allItems.find((n) => n.to === t.to);
      return !navItem || navItem.roles.includes(userRole);
    }
  );

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-[#0F172A] border-t border-slate-800 flex items-stretch no-print"
      data-testid="mobile-bottom-tab-bar"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          data-testid={`tab-${tab.label.toLowerCase().replace(/\s+/g, "-")}`}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center justify-center gap-0.5 transition-colors ${
              isActive ? "text-[#C27842]" : "text-slate-500 hover:text-slate-300"
            }`
          }
          style={{ minHeight: 60 }}
        >
          {({ isActive }) => (
            <>
              <tab.icon
                className={`w-5 h-5 transition-transform ${isActive ? "scale-110" : ""}`}
              />
              <span
                className={`text-[10px] font-semibold tracking-tight ${
                  isActive ? "text-[#C27842]" : ""
                }`}
              >
                {tab.label}
              </span>
            </>
          )}
        </NavLink>
      ))}

      {/* More tab */}
      <button
        onClick={onMoreOpen}
        data-testid="tab-more"
        className="flex-1 flex flex-col items-center justify-center gap-0.5 text-slate-500 hover:text-slate-300 transition-colors"
        style={{ minHeight: 60 }}
        aria-label="More navigation options"
      >
        <MoreHorizontal className="w-5 h-5" />
        <span className="text-[10px] font-semibold tracking-tight">More</span>
      </button>
    </nav>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   MOBILE: TOP BAR
   ───────────────────────────────────────────────────────────────────────────── */
function MobileTopBar({ user, workspace, onSwitch, onLogout }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const pageTitle = PAGE_TITLES[location.pathname] || "SSK Footcare";
  const isRoot = location.pathname === "/";

  const toggleUserMenu = useCallback(
    () => setUserMenuOpen((v) => !v),
    []
  );

  return (
    <header
      className="lg:hidden sticky top-0 z-40 bg-[#0F172A] border-b border-slate-800 no-print"
      data-testid="mobile-top-bar"
      style={{ minHeight: 56 }}
    >
      <div className="flex items-center justify-between px-3 h-14">
        {/* Left: back or logo */}
        <div className="flex items-center gap-1" style={{ minWidth: 44 }}>
          {!isRoot ? (
            <button
              onClick={() => navigate(-1)}
              aria-label="Go back"
              data-testid="back-btn"
              className="p-2 -ml-2 text-slate-400 hover:text-white transition-colors rounded active:bg-slate-800"
              style={{ minHeight: 44, minWidth: 44, display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <ChevronLeft className="w-6 h-6" />
            </button>
          ) : (
            <div className="w-8 h-8 bg-[#C27842] text-white grid place-items-center font-black ml-1">
              <Factory className="w-4 h-4" />
            </div>
          )}
        </div>

        {/* Center: page title */}
        <div className="flex-1 text-center px-2">
          <span className="text-sm font-black text-white tracking-tight truncate block">
            {isRoot ? "SSK FOOTCARE" : pageTitle}
          </span>
          {isRoot && (
            <span className="text-[9px] uppercase tracking-[0.2em] text-slate-500 block">
              {WORKSPACE_LABELS[workspace] || "ERP"}
            </span>
          )}
        </div>

        {/* Right: user menu */}
        <div style={{ minWidth: 44 }} className="flex justify-end">
          <UserMenuPopover
            user={user}
            workspace={workspace}
            onSwitch={onSwitch}
            onLogout={onLogout}
            open={userMenuOpen}
            onToggle={toggleUserMenu}
          />
        </div>
      </div>
    </header>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   DESKTOP: SIDEBAR (overlay drawer on mobile, static on desktop)
   ───────────────────────────────────────────────────────────────────────────── */

/* ─────────────────────────────────────────────────────────────────────────────
   ROOT COMPONENT
   ───────────────────────────────────────────────────────────────────────────── */
export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [workspace, setWorkspaceState] = useWorkspace();
  const [moreOpen, setMoreOpen] = useState(false);

  const switchWorkspace = useCallback((ws) => {
    localStorage.setItem("workspace", ws);
    window.dispatchEvent(new Event("workspaceChanged"));
    setWorkspaceState(ws);
    navigate("/");
  }, [navigate, setWorkspaceState]);

  const doLogout = useCallback(async () => {
    await logout();
    localStorage.removeItem("workspace");
    navigate("/login");
  }, [logout, navigate]);

  const openMore = useCallback(() => setMoreOpen(true), []);
  const closeMore = useCallback(() => setMoreOpen(false), []);

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-[#F7F7F5]">

      {/* ── MOBILE TOP BAR ─────────────────────────────────────────── */}
      <MobileTopBar
        user={user}
        workspace={workspace}
        onSwitch={switchWorkspace}
        onLogout={doLogout}
      />

      {/* ── DESKTOP STATIC SIDEBAR ─────────────────────────────────── */}
      <aside
        className="hidden lg:flex w-64 bg-[#0F172A] text-slate-300 flex-col sticky top-0 h-screen"
        data-testid="sidebar"
      >
        <SidebarContent
          workspace={workspace}
          onSwitch={switchWorkspace}
          onClose={null}
          user={user}
          onLogout={doLogout}
        />
      </aside>

      {/* ── MAIN CONTENT ───────────────────────────────────────────── */}
      <main
        className="flex-1 min-w-0 mobile-main-content"
        data-testid="main-content"
      >
        <Outlet />
      </main>

      {/* ── MOBILE: MORE DRAWER ────────────────────────────────────── */}
      <MoreDrawer
        open={moreOpen}
        onClose={closeMore}
        workspace={workspace}
        user={user}
      />

      {/* ── MOBILE: BOTTOM TAB BAR ─────────────────────────────────── */}
      <BottomTabBar
        workspace={workspace}
        onMoreOpen={openMore}
        userRole={user?.role}
      />
    </div>
  );
}
