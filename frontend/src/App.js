import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth";
import Login from "@/pages/Login";
import AppShell from "@/components/AppShell";
import Dashboard from "@/pages/Dashboard";
import Materials from "@/pages/Materials";
import Workers from "@/pages/Workers";
import Inventory from "@/pages/Inventory";
import Payroll from "@/pages/Payroll";
import Styles from "@/pages/Styles";
import Costing from "@/pages/Costing";
import POs from "@/pages/POs";
import Production from "@/pages/Production";
import Defects from "@/pages/Defects";
import Reports from "@/pages/Reports";
import Users from "@/pages/Users";
import Settings from "@/pages/Settings";
import Expenses from "@/pages/Expenses";
import Invoices from "@/pages/Invoices";
import Clients from "@/pages/Clients";
import Vendors from "@/pages/Vendors";
import VendorPOs from "@/pages/VendorPOs";
import SkuMap from "@/pages/SkuMap";
import OnlineStylePipeline from "@/pages/OnlineStylePipeline";
import ComponentInventory from "@/pages/ComponentInventory";
import OnlineOrders from "@/pages/OnlineOrders";
import OnlineProfitability from "@/pages/OnlineProfitability";
import B2BProfitability from "@/pages/B2BProfitability";
import ReadyStock from "@/pages/ReadyStock";
import WarehouseDashboard from "@/pages/WarehouseDashboard";
import Picklists from "@/pages/Picklists";
import WarehouseReports from "@/pages/WarehouseReports";
import WarehouseQRSheet from "@/pages/WarehouseQRSheet";
import PendingProductList from "@/pages/PendingProductList";
import ListingFormats from "@/pages/ListingFormats";
import OrderImportFormats from "@/pages/OrderImportFormats";
import SelectWorkspace from "@/pages/SelectWorkspace";
import ResetPassword from "@/pages/ResetPassword";
import KarigarLogin from "@/pages/KarigarLogin";
import KarigarDashboard from "@/pages/KarigarDashboard";
import StylePLM from "@/pages/StylePLM";
import PatternManager from "@/pages/PatternManager";
import ToolingLibrary from "@/pages/ToolingLibrary";
import BankReconciliation from "@/pages/BankReconciliation";
import { Loader2 } from "lucide-react";

// F-037: Route-to-module & role authorization matrix for frontend navigation guard
const ROUTE_PERMISSIONS = {
  "styles": { roles: ["admin", "manager", "production", "sales"], modules: ["production", "orders_sales"] },
  "plm": { roles: ["admin", "manager", "production"], modules: ["production"] },
  "patterns": { roles: ["admin", "manager", "production"], modules: ["production"] },
  "tooling": { roles: ["admin", "manager", "production"], modules: ["production"] },
  "materials": { roles: ["admin", "manager", "production"], modules: ["inventory", "procurement"] },
  "workers": { roles: ["admin", "manager", "production"], modules: ["workers"] },
  "inventory": { roles: ["admin", "manager", "production"], modules: ["inventory"] },
  "components": { roles: ["admin", "manager", "production"], modules: ["inventory", "production"] },
  "payroll": { roles: ["admin", "manager"], modules: ["workers", "settings_admin"] },
  "expenses": { roles: ["admin", "manager"], modules: ["reports", "settings_admin"] },
  "bank-reconciliation": { roles: ["admin", "manager"], modules: ["reports", "settings_admin"] },
  "pos": { roles: ["admin", "manager", "sales"], modules: ["orders_sales"] },
  "production": { roles: ["admin", "manager", "production"], modules: ["production"] },
  "defects": { roles: ["admin", "manager", "production"], modules: ["production"] },
  "costing": { roles: ["admin", "manager"], modules: ["orders_sales", "production"] },
  "b2b-profitability": { roles: ["admin", "manager"], modules: ["reports", "orders_sales"] },
  "reports": { roles: ["admin", "manager"], modules: ["reports"] },
  "invoices": { roles: ["admin", "manager", "sales"], modules: ["orders_sales"] },
  "clients": { roles: ["admin", "manager", "sales"], modules: ["orders_sales"] },
  "vendors": { roles: ["admin", "manager"], modules: ["procurement"] },
  "vendor-pos": { roles: ["admin", "manager"], modules: ["procurement"] },
  "sku-map": { roles: ["admin", "manager"], modules: ["online"] },
  "online-pipeline": { roles: ["admin", "manager"], modules: ["online", "production"] },
  "ready-stock": { roles: ["admin", "manager"], modules: ["online", "inventory"] },
  "online-orders": { roles: ["admin", "manager", "sales"], modules: ["online"] },
  "online-profitability": { roles: ["admin", "manager"], modules: ["online", "reports"] },
  "warehouse": { roles: ["admin", "manager", "production"], modules: ["online", "inventory"] },
  "picklists": { roles: ["admin", "manager", "production"], modules: ["online", "inventory"] },
  "warehouse/reports": { roles: ["admin", "manager"], modules: ["online", "reports"] },
  "warehouse/qr": { roles: ["admin", "manager", "production"], modules: ["online", "inventory"] },
  "pending-list": { roles: ["admin", "manager", "production"], modules: ["online", "inventory"] },
  "listing-formats": { roles: ["admin"], modules: ["settings_admin"] },
  "order-import-formats": { roles: ["admin"], modules: ["settings_admin"] },
  "settings": { roles: ["admin", "manager"], modules: ["settings_admin"] },
  "users": { roles: ["admin"], modules: ["settings_admin"] },
};

function RouteGuard({ path, children }) {
  const { user } = useAuth();
  if (!user || user.role === "admin") return children;

  const rule = ROUTE_PERMISSIONS[path];
  if (!rule) return children;

  if (rule.roles && !rule.roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  const userModules = Array.isArray(user.modules) ? user.modules : [];
  if (rule.modules && userModules.length > 0) {
    const hasModule = rule.modules.some((m) => userModules.includes(m));
    if (!hasModule) {
      return <Navigate to="/" replace />;
    }
  }

  return children;
}

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen grid place-items-center text-slate-500"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  if (user === false) return <Navigate to="/login" replace />;

  // Workers (karigars) must never access the main ERP console — redirect to karigar dashboard
  if (user.role === "worker") return <Navigate to="/karigar" replace />;

  // F-038: localStorage workspace is treated as a UI display preference, never an authorization boundary.
  // All tenant/company data access is strictly enforced server-side.
  const workspace = localStorage.getItem("workspace") || "management";
  const isSelectPage = window.location.pathname === "/select-workspace";
  if (!localStorage.getItem("workspace") && !isSelectPage) {
    localStorage.setItem("workspace", "management");
  }
  return children;
}

function PublicOnly({ children }) {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen grid place-items-center text-slate-500"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  // Workers should not be redirected to the ERP — send them to the karigar app instead
  if (user && user !== false) {
    if (user.role === "worker") return <Navigate to="/karigar" replace />;
    return <Navigate to="/" replace />;
  }
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/karigar-login" element={<KarigarLogin />} />
          <Route path="/karigar" element={<KarigarDashboard />} />
          <Route path="/select-workspace" element={<Protected><SelectWorkspace /></Protected>} />
          <Route path="/" element={<Protected><AppShell /></Protected>}>

            <Route index element={<Dashboard />} />
            <Route path="styles" element={<RouteGuard path="styles"><Styles /></RouteGuard>} />
            <Route path="plm" element={<RouteGuard path="plm"><StylePLM /></RouteGuard>} />
            <Route path="patterns" element={<RouteGuard path="patterns"><PatternManager /></RouteGuard>} />
            <Route path="tooling" element={<RouteGuard path="tooling"><ToolingLibrary /></RouteGuard>} />
            <Route path="materials" element={<RouteGuard path="materials"><Materials /></RouteGuard>} />
            <Route path="workers" element={<RouteGuard path="workers"><Workers /></RouteGuard>} />
            <Route path="inventory" element={<RouteGuard path="inventory"><Inventory /></RouteGuard>} />
            <Route path="payroll" element={<RouteGuard path="payroll"><Payroll /></RouteGuard>} />
            <Route path="costing" element={<RouteGuard path="costing"><Costing /></RouteGuard>} />
            <Route path="pos" element={<RouteGuard path="pos"><POs /></RouteGuard>} />

            <Route path="production" element={<RouteGuard path="production"><Production /></RouteGuard>} />
            <Route path="defects" element={<RouteGuard path="defects"><Defects /></RouteGuard>} />
            <Route path="reports" element={<RouteGuard path="reports"><Reports /></RouteGuard>} />
            <Route path="invoices" element={<RouteGuard path="invoices"><Invoices /></RouteGuard>} />
            <Route path="expenses" element={<RouteGuard path="expenses"><Expenses /></RouteGuard>} />
            <Route path="bank-reconciliation" element={<RouteGuard path="bank-reconciliation"><BankReconciliation /></RouteGuard>} />
            <Route path="clients" element={<RouteGuard path="clients"><Clients /></RouteGuard>} />
            <Route path="vendors" element={<RouteGuard path="vendors"><Vendors /></RouteGuard>} />
            <Route path="vendor-pos" element={<RouteGuard path="vendor-pos"><VendorPOs /></RouteGuard>} />
            <Route path="sku-map" element={<RouteGuard path="sku-map"><SkuMap /></RouteGuard>} />
            <Route path="online-pipeline" element={<RouteGuard path="online-pipeline"><OnlineStylePipeline /></RouteGuard>} />
            <Route path="components" element={<RouteGuard path="components"><ComponentInventory /></RouteGuard>} />
            <Route path="ready-stock" element={<RouteGuard path="ready-stock"><ReadyStock /></RouteGuard>} />
            <Route path="online-orders" element={<RouteGuard path="online-orders"><OnlineOrders /></RouteGuard>} />
            <Route path="online-profitability" element={<RouteGuard path="online-profitability"><OnlineProfitability /></RouteGuard>} />
            <Route path="b2b-profitability" element={<RouteGuard path="b2b-profitability"><B2BProfitability /></RouteGuard>} />
            <Route path="warehouse" element={<RouteGuard path="warehouse"><WarehouseDashboard /></RouteGuard>} />
            <Route path="picklists" element={<RouteGuard path="picklists"><Picklists /></RouteGuard>} />
            <Route path="warehouse/reports" element={<RouteGuard path="warehouse/reports"><WarehouseReports /></RouteGuard>} />
            <Route path="warehouse/qr" element={<RouteGuard path="warehouse/qr"><WarehouseQRSheet /></RouteGuard>} />
            <Route path="pending-list" element={<RouteGuard path="pending-list"><PendingProductList /></RouteGuard>} />
            <Route path="listing-formats" element={<RouteGuard path="listing-formats"><ListingFormats /></RouteGuard>} />
            <Route path="order-import-formats" element={<RouteGuard path="order-import-formats"><OrderImportFormats /></RouteGuard>} />
            <Route path="settings" element={<RouteGuard path="settings"><Settings /></RouteGuard>} />
            <Route path="users" element={<RouteGuard path="users"><Users /></RouteGuard>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
