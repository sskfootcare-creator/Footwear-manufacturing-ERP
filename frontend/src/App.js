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
import Invoices from "@/pages/Invoices";
import Clients from "@/pages/Clients";
import Vendors from "@/pages/Vendors";
import VendorPOs from "@/pages/VendorPOs";
import SkuMap from "@/pages/SkuMap";
import OnlineStylePipeline from "@/pages/OnlineStylePipeline";
import ComponentInventory from "@/pages/ComponentInventory";
import OnlineOrders from "@/pages/OnlineOrders";
import OnlineProfitability from "@/pages/OnlineProfitability";
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
import { Loader2 } from "lucide-react";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen grid place-items-center text-slate-500"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  if (user === false) return <Navigate to="/login" replace />;

  const workspace = localStorage.getItem("workspace");
  const isSelectPage = window.location.pathname === "/select-workspace";
  if (!workspace && !isSelectPage) {
    return <Navigate to="/select-workspace" replace />;
  }
  return children;
}

function PublicOnly({ children }) {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen grid place-items-center text-slate-500"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  if (user && user !== false) return <Navigate to="/" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/select-workspace" element={<Protected><SelectWorkspace /></Protected>} />
          <Route path="/" element={<Protected><AppShell /></Protected>}>

            <Route index element={<Dashboard />} />
            <Route path="materials" element={<Materials />} />
            <Route path="workers" element={<Workers />} />
            <Route path="inventory" element={<Inventory />} />
            <Route path="payroll" element={<Payroll />} />
            <Route path="styles" element={<Styles />} />
            <Route path="costing" element={<Costing />} />
            <Route path="pos" element={<POs />} />
            <Route path="production" element={<Production />} />
            <Route path="defects" element={<Defects />} />
            <Route path="reports" element={<Reports />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="clients" element={<Clients />} />
            <Route path="vendors" element={<Vendors />} />
            <Route path="vendor-pos" element={<VendorPOs />} />
            <Route path="sku-map" element={<SkuMap />} />
            <Route path="online-pipeline" element={<OnlineStylePipeline />} />
            <Route path="components" element={<ComponentInventory />} />
            <Route path="ready-stock" element={<ReadyStock />} />
            <Route path="online-orders" element={<OnlineOrders />} />
            <Route path="online-profitability" element={<OnlineProfitability />} />
            <Route path="warehouse" element={<WarehouseDashboard />} />
            <Route path="picklists" element={<Picklists />} />
            <Route path="warehouse/reports" element={<WarehouseReports />} />
            <Route path="warehouse/qr" element={<WarehouseQRSheet />} />
            <Route path="pending-list" element={<PendingProductList />} />
            <Route path="listing-formats" element={<ListingFormats />} />
            <Route path="order-import-formats" element={<OrderImportFormats />} />
            <Route path="settings" element={<Settings />} />
            <Route path="users" element={<Users />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
