import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { http, inr } from "../lib/api";
import { triggerApiExport, downloadCatalogueXlsx, downloadCsv } from "../lib/exportUtils";
import { ImageThumb } from "../components/ImageUploader";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
  ConfirmDialog,
  PaginationControls,
  usePagination,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Plus,
  Upload,
  Trash2,
  Eye,
  Save,
  FileText,
  Loader2,
  Sparkles,
  FileDown,
  Truck,
  Package,
  Barcode,
  ReceiptIndianRupee,
  ExternalLink,
  ArrowRight,
  Calculator,
  AlertCircle,
  CheckCircle2,
  HardHat,
  UserCheck,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
  CheckSquare,
  Square,
  Check,
  X,
  Layers,
} from "lucide-react";
import SearchableSelect from "../components/SearchableSelect";
import PackingListPreviewModal from "../components/PackingListPreviewModal";
import PoEanCodesModal from "../components/PoEanCodesModal";

import { API } from "../lib/api";

const emptyLine = {
  style_code: "",       // Internal SSK style code (SSK_XXXXX). MUST be filled before save.
  external_sku: "",     // Client's / marketplace's raw code from PO (preserved for sku_map)
  resolution_warning: "", // Warning message if auto-resolution failed
  description: "",
  color: "",
  size: "",
  hsn_code: "",
  quantity: 0,
  unit_price: 0,
  amount: 0,
};

const emptyPO = {
  po_number: "",
  po_date: "",
  client_name: "",
  client_address: "",
  billing_address: "",
  shipping_address: "",
  client_gstin: "",
  client_state: "",
  client_state_code: "",
  delivery_date: "",
  payment_terms: "",
  currency: "INR",
  line_items: [{ ...emptyLine }],
  cgst_rate: 0,
  sgst_rate: 0,
  igst_rate: 0,
  notes: "",
};

export default function POs() {
  const [pos, setPos] = useState([]);
  const [styles, setStyles] = useState([]);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyPO);
  const [uploading, setUploading] = useState(false);
  const [view, setView] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const navigate = useNavigate();
  const [formError, setFormError] = useState("");
  const [statusFilter, setStatusFilter] = useState("active"); // "active" | "completed"

  const [selectedPoForInvoices, setSelectedPoForInvoices] = useState(null);
  const [poInvoicesList, setPoInvoicesList] = useState([]);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [previewPo, setPreviewPo] = useState(null);
  const [invoiceModalOpen, setInvoiceModalOpen] = useState(false);
  const [selectedPoForEan, setSelectedPoForEan] = useState(null);
  const [poEanModalOpen, setPoEanModalOpen] = useState(false);
  const [poDocumentsData, setPoDocumentsData] = useState(null);
  const [docActiveTab, setDocActiveTab] = useState("all");
  const [viewDocuments, setViewDocuments] = useState(null);
  const [loadingViewDocs, setLoadingViewDocs] = useState(false);
  const [planningData, setPlanningData] = useState(null);
  const [loadingPlanning, setLoadingPlanning] = useState(false);
  const [showPlanningSection, setShowPlanningSection] = useState(true);
  const [assignModal, setAssignModal] = useState(null);
  const [allocatingKarigar, setAllocatingKarigar] = useState(false);

  // Style photo & detail lookup map
  const stylesMap = useMemo(() => {
    const m = new Map();
    styles.forEach((s) => {
      if (s.code) m.set(s.code.trim().toUpperCase(), s);
      if (s.id || s._id) m.set(String(s.id || s._id), s);
    });
    return m;
  }, [styles]);

  const getStyleImage = (styleCode, lineItem = null) => {
    if (lineItem?.image_thumbnail_url) return lineItem.image_thumbnail_url;
    if (lineItem?.image_url) return lineItem.image_url;
    const s = stylesMap.get(String(styleCode || "").trim().toUpperCase());
    return s?.image_thumbnail_url || s?.image_url || s?.image_display_url || "";
  };

  // Single PO View Drawer: Filter styles included in budget calculation
  const [poViewSelectedLines, setPoViewSelectedLines] = useState([]);

  // Multi-PO and Multi-Style Production Budget Calculator state
  const [selectedPoIds, setSelectedPoIds] = useState([]);
  const [multiBudgetOpen, setMultiBudgetOpen] = useState(false);
  const [multiBudgetPoIds, setMultiBudgetPoIds] = useState([]);
  const [selectedMultiStyleKeys, setSelectedMultiStyleKeys] = useState(new Set());
  const [aligningBudget, setAligningBudget] = useState(false);
  const [alignmentSuccess, setAlignmentSuccess] = useState(null);

  const togglePoSelect = (poId) => {
    setSelectedPoIds((prev) =>
      prev.includes(poId) ? prev.filter((id) => id !== poId) : [...prev, poId]
    );
  };

  const toggleSelectAllPos = () => {
    if (selectedPoIds.length === displayedPos.length && displayedPos.length > 0) {
      setSelectedPoIds([]);
    } else {
      setSelectedPoIds(displayedPos.map((p) => p.id));
    }
  };

  const openMultiBudget = (initialPoIds = []) => {
    let ids = initialPoIds.length > 0 ? initialPoIds : selectedPoIds;
    if (ids.length === 0) {
      ids = activePos.length > 0 ? activePos.slice(0, 5).map((p) => p.id) : pos.slice(0, 5).map((p) => p.id);
    }
    setMultiBudgetPoIds(ids);

    const keys = new Set();
    pos.filter((p) => ids.includes(p.id)).forEach((p) => {
      (p.line_items || []).forEach((_, idx) => {
        keys.add(`${p.id}_${idx}`);
      });
    });
    setSelectedMultiStyleKeys(keys);
    setAlignmentSuccess(null);
    setMultiBudgetOpen(true);
  };

  const toggleMultiBudgetPo = (poId) => {
    setMultiBudgetPoIds((prev) => {
      const isIncluded = prev.includes(poId);
      const next = isIncluded ? prev.filter((id) => id !== poId) : [...prev, poId];
      // When adding, select all styles; when removing, remove style keys
      const updatedKeys = new Set(selectedMultiStyleKeys);
      const targetPo = pos.find((p) => p.id === poId);
      if (targetPo && targetPo.line_items) {
        targetPo.line_items.forEach((_, idx) => {
          const k = `${poId}_${idx}`;
          if (isIncluded) {
            updatedKeys.delete(k);
          } else {
            updatedKeys.add(k);
          }
        });
      }
      setSelectedMultiStyleKeys(updatedKeys);
      return next;
    });
  };

  const toggleMultiBudgetStyleKey = (key) => {
    setSelectedMultiStyleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const selectAllStylesForPo = (poId) => {
    const targetPo = pos.find((p) => p.id === poId);
    if (!targetPo || !targetPo.line_items) return;
    setSelectedMultiStyleKeys((prev) => {
      const next = new Set(prev);
      targetPo.line_items.forEach((_, idx) => next.add(`${poId}_${idx}`));
      return next;
    });
  };

  const deselectAllStylesForPo = (poId) => {
    const targetPo = pos.find((p) => p.id === poId);
    if (!targetPo || !targetPo.line_items) return;
    setSelectedMultiStyleKeys((prev) => {
      const next = new Set(prev);
      targetPo.line_items.forEach((_, idx) => next.delete(`${poId}_${idx}`));
      return next;
    });
  };

  const multiBudgetSelectedPOs = useMemo(() => {
    return pos.filter((p) => multiBudgetPoIds.includes(p.id));
  }, [pos, multiBudgetPoIds]);

  const multiBudgetCalculated = useMemo(() => {
    let totalQty = 0;
    let totalRevenue = 0;
    let totalBom = 0;
    let totalLabor = 0;
    let totalPacking = 0;
    let totalOutside = 0;
    let hasEstimated = false;
    let hasActual = false;
    const selectedLineRows = [];

    multiBudgetSelectedPOs.forEach((p) => {
      (p.line_items || []).forEach((li, idx) => {
        const key = `${p.id}_${idx}`;
        if (selectedMultiStyleKeys.has(key)) {
          const q = Number(li.quantity || 0);
          const price = Number(li.unit_price || 0);
          const rev = q * price;
          const pr = li.profitability || {};
          const bom = Number(pr.bom_cost || 0) * q;
          const labor = Number(pr.labor_cost || 0) * q;
          const packing = Number(pr.packing_cost || 0) * q;
          const outside = Number(pr.outside_cost || 0) * q;
          const lineCost = bom + labor + packing + outside;

          if (pr.is_estimated) hasEstimated = true;
          else if (Number(pr.labor_cost || 0) > 0) hasActual = true;

          totalQty += q;
          totalRevenue += rev;
          totalBom += bom;
          totalLabor += labor;
          totalPacking += packing;
          totalOutside += outside;

          selectedLineRows.push({
            po: p,
            lineIndex: idx,
            lineItem: li,
            quantity: q,
            unitPrice: price,
            revenue: rev,
            bomCost: bom,
            laborCost: labor,
            packingCost: packing,
            outsideCost: outside,
            totalCost: lineCost,
            profit: rev - lineCost,
            profitPct: rev > 0 ? (((rev - lineCost) / rev) * 100).toFixed(1) : "0.0",
            isLaborEstimated: pr.is_estimated ?? true,
          });
        }
      });
    });

    const totalCost = totalBom + totalLabor + totalPacking + totalOutside;
    const profit = totalRevenue - totalCost;
    const profitPct = totalRevenue > 0 ? ((profit / totalRevenue) * 100).toFixed(1) : "0.0";

    return {
      totalQty,
      totalRevenue,
      totalBom,
      totalLabor,
      totalPacking,
      totalOutside,
      totalCost,
      profit,
      profitPct,
      isLaborEstimated: hasEstimated || !hasActual,
      isActual: hasActual && !hasEstimated,
      selectedLineRows,
      selectedCount: selectedLineRows.length,
    };
  }, [multiBudgetSelectedPOs, selectedMultiStyleKeys]);

  const handleAlignMultiBudget = async () => {
    setAligningBudget(true);
    try {
      const itemsPayload = multiBudgetCalculated.selectedLineRows.map((r) => ({
        po_id: r.po.id,
        po_number: r.po.po_number,
        client_name: r.po.client_name,
        style_code: r.lineItem.style_code,
        description: r.lineItem.description,
        color: r.lineItem.color,
        size: String(r.lineItem.size || ""),
        quantity: r.quantity,
        unit_price: r.unitPrice,
        line_index: r.lineIndex,
      }));

      const { data } = await http.post("/pos/multi-budget/align", {
        items: itemsPayload,
        po_ids: multiBudgetPoIds,
        notes: `Production Budget Aligned across ${multiBudgetPoIds.length} POs (${multiBudgetCalculated.selectedCount} styles, ${multiBudgetCalculated.totalQty} pairs)`,
      });

      setAlignmentSuccess({
        id: data.id,
        timestamp: new Date().toLocaleTimeString(),
        totalBudget: multiBudgetCalculated.totalCost,
        totalQty: multiBudgetCalculated.totalQty,
      });
    } catch (err) {
      console.error("Failed to align budget:", err);
      alert("Failed to align production budget: " + (err.response?.data?.detail || err.message));
    } finally {
      setAligningBudget(false);
    }
  };

  const handleDownloadPoCatalogue = async () => {
    let codes = [];
    if (selectedPoIds.length > 0) {
      pos.filter((p) => selectedPoIds.includes(p.id)).forEach((p) => {
        (p.line_items || []).forEach((li) => {
          if (li.style_code) codes.push(li.style_code);
        });
      });
    }
    codes = Array.from(new Set(codes));
    await downloadCatalogueXlsx({
      style_codes: codes.length > 0 ? codes : undefined,
      brand: "ZECODE",
      defaultFilename: codes.length > 0 ? `Catalogue_Selected_POs.xlsx` : "SSK_Footwear_Catalogue.xlsx",
    });
  };


  const openPoDocuments = async (po, defaultTab = "all") => {
    setSelectedPoForInvoices(po);
    setDocActiveTab(defaultTab);
    setLoadingInvoices(true);
    setInvoiceModalOpen(true);
    try {
      const res = await http.get(`/pos/${po.id}/documents`);
      const data = res.data || {};
      setPoDocumentsData(data);
      setPoInvoicesList(data.invoices || []);
    } catch {
      try {
        const r2 = await http.get(`/pos/${po.id}/invoices`);
        setPoDocumentsData({ invoices: r2.data || [], dispatch_records: [] });
        setPoInvoicesList(r2.data || []);
      } catch {
        setPoDocumentsData(null);
        setPoInvoicesList([]);
      }
    } finally {
      setLoadingInvoices(false);
    }
  };

  const handleInvoiceClick = (po) => openPoDocuments(po, "all");

  const load = async () => {
    try {
      const [posRes, stylesRes] = await Promise.all([
        http.get("/pos"),
        http.get("/styles"),
      ]);
      setPos(posRes.data);
      setStyles(stylesRes.data);
    } catch (e) {
      alert("Failed to load PO data: " + e.message);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const activePos = useMemo(() => {
    return pos.filter((p) => !p.is_completed && p.status !== "completed");
  }, [pos]);

  const completedPos = useMemo(() => {
    return pos.filter((p) => p.is_completed || p.status === "completed");
  }, [pos]);

  const displayedPos = useMemo(() => {
    if (statusFilter === "completed") return completedPos;
    return activePos;
  }, [statusFilter, activePos, completedPos]);

  const {
    paginatedItems: paginatedPos,
    paginationProps: poPaginationProps,
  } = usePagination(displayedPos, {
    initialPageSize: 25,
    pageSizeOptions: [10, 25, 50, 100],
    testIdPrefix: "pos-pagination",
  });

  const validStyleCodes = useMemo(() => {
    return new Set(styles.map((s) => s.code.trim().toUpperCase()));
  }, [styles]);

  const loadPlanningData = async (poId) => {
    if (!poId) return;
    setLoadingPlanning(true);
    try {
      const { data } = await http.get(`/pos/${poId}/planning-jobs`);
      setPlanningData(data);
    } catch (err) {
      console.error("Failed to load PO planning jobs:", err);
    } finally {
      setLoadingPlanning(false);
    }
  };

  const openView = async (p) => {
    setView(p);
    setLoadingViewDocs(true);
    setViewDocuments(null);
    setPlanningData(null);
    loadPlanningData(p.id);
    try {
      const [res, docRes] = await Promise.all([
        http.get(`/pos/${p.id}`).catch(() => ({ data: p })),
        http.get(`/pos/${p.id}/documents`).catch(() => ({ data: null })),
      ]);
      setView(res.data || p);
      setViewDocuments(docRes.data || null);
    } catch {
      setView(p);
    } finally {
      setLoadingViewDocs(false);
    }
  };

  const handleAllocateWorker = async (role, workerId, rate) => {
    if (!view?.id || !role) return;
    setAllocatingKarigar(true);
    try {
      const { data: updatedPo } = await http.post(`/pos/${view.id}/allocate-karigar`, {
        role,
        worker_id: workerId || null,
        rate_per_pair: rate !== "" && rate != null ? Number(rate) : null,
      });
      setView(updatedPo);
      await loadPlanningData(view.id);
      setAssignModal(null);
      load(); // refresh main PO list
    } catch (err) {
      console.error("Failed to allocate worker:", err);
      alert("Failed to allocate karigar: " + (err.response?.data?.detail || err.message));
    } finally {
      setAllocatingKarigar(false);
    }
  };

  const poBudget = useMemo(() => {
    if (!view || !view.line_items) return null;
    const selectedLines = view.line_items.filter((_, idx) =>
      poViewSelectedLines.length === 0 || poViewSelectedLines.includes(idx)
    );
    let totalBom = 0;
    let totalLabor = 0;
    let totalPacking = 0;
    let totalOutside = 0;
    let totalSubtotal = 0;
    let totalQty = 0;
    let hasActual = false;
    let hasEstimated = false;

    selectedLines.forEach((li) => {
      const q = Number(li.quantity || 0);
      const pr = li.profitability || {};
      const rate = Number(li.unit_price || 0);
      totalQty += q;
      totalSubtotal += rate * q;
      totalBom += Number(pr.bom_cost || 0) * q;
      totalLabor += Number(pr.labor_cost || 0) * q;
      totalPacking += Number(pr.packing_cost || 0) * q;
      totalOutside += Number(pr.outside_cost || 0) * q;
      if (pr.is_estimated) hasEstimated = true;
      else if (Number(pr.labor_cost || 0) > 0) hasActual = true;
    });

    const totalCost = Number(totalBom + totalLabor + totalPacking + totalOutside);
    const profit = totalSubtotal - totalCost;
    const profitPct = totalSubtotal > 0 ? ((profit / totalSubtotal) * 100).toFixed(1) : "0.0";

    return {
      totalBom,
      totalLabor,
      totalPacking,
      totalOutside,
      totalCost,
      subtotal: totalSubtotal,
      profit,
      profitPct,
      totalQuantity: totalQty,
      selectedCount: selectedLines.length,
      totalLines: view.line_items.length,
      isLaborEstimated: hasEstimated || !hasActual,
      isActual: hasActual && !hasEstimated,
      isFullyAllocated: !hasEstimated && hasActual,
    };
  }, [view, poViewSelectedLines]);

  const startNew = () => {
    setEditId(null);
    setForm(emptyPO);
    setFormError("");
    setOpen(true);
  };
  const onExtractFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await http.post("/pos/extract", fd);
      const clientName = data.client_name || data.vendor_name || "";
      const validCodes = new Set(styles.map((s) => s.code.trim().toUpperCase()));

      // Pre-resolve each external code via sku_map so already-mapped items land pre-picked
      const rawLines =
        data.line_items && data.line_items.length
          ? data.line_items
          : [{ ...emptyLine }];
      const resolved = await Promise.all(
        rawLines.map(async (li) => {
          const ext = String(li.style_code || li.item_code || "").trim();
          let mappedStyle = "";
          let resolutionWarning = "";
          // If the external code is itself already an SSK code, use it directly.
          if (ext && validCodes.has(ext.toUpperCase())) {
            mappedStyle = ext;
          } else if (ext && clientName) {
            try {
              const r = await http.get(
                `/sku-map/resolve?source_type=b2b_client&source_name=${encodeURIComponent(
                  clientName,
                )}&external_sku=${encodeURIComponent(ext)}`,
              );
              if (r.data?.matched && r.data.style_code) {
                mappedStyle = r.data.style_code;
              }
            } catch {
              resolutionWarning = "Could not auto-resolve SKU mapping — check manually";
            }
          }
          return {
            style_code: mappedStyle,
            external_sku: ext,
            resolution_warning: resolutionWarning,
            description: li.description || "",
            color: li.color || "",
            size: String(li.size || ""),
            hsn_code: li.hsn_code || "",
            quantity: Number(li.quantity || 0),
            unit_price: Number(li.unit_price || 0),
            amount: Number(
              li.amount ||
              Number(li.quantity || 0) * Number(li.unit_price || 0),
            ),
          };
        }),

      );

      setForm({
        po_number: data.po_number || "",
        po_date: data.po_date || "",
        client_name: clientName,
        client_address: data.client_address || "",
        billing_address: data.billing_address || "",
        shipping_address: data.shipping_address || "",
        client_gstin: data.client_gstin || "",
        client_state: data.client_state || "",
        client_state_code: data.client_state_code || "",
        delivery_date: data.delivery_date || "",
        payment_terms: data.payment_terms || "",
        currency: data.currency || "INR",
        line_items: resolved,
        cgst_rate: Number(data.cgst_rate || 0),
        sgst_rate: Number(data.sgst_rate || 0),
        igst_rate: Number(data.igst_rate || 0),
        notes: data.notes || "",
      });
      setEditId(null);
      setOpen(true);
    } catch (err) {
      alert(
        "Extraction failed: " + (err.response?.data?.detail || err.message),
      );
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const updateLine = (i, key, val) =>
    setForm((f) => {
      const li = f.line_items.map((r, idx) =>
        idx === i ? { ...r, [key]: val } : r,
      );
      if (key === "quantity" || key === "unit_price") {
        const row = li[i];
        row.amount = Number(row.quantity || 0) * Number(row.unit_price || 0);
      }
      return { ...f, line_items: li };
    });
  const addLine = () =>
    setForm((f) => ({ ...f, line_items: [...f.line_items, { ...emptyLine }] }));
  const removeLine = (i) =>
    setForm((f) => ({
      ...f,
      line_items: f.line_items.filter((_, idx) => idx !== i),
    }));

  const totals = useMemo(() => {
    const subtotal = form.line_items.reduce(
      (s, li) => s + Number(li.amount || 0),
      0,
    );
    const cgst_amount = (subtotal * Number(form.cgst_rate || 0)) / 100;
    const sgst_amount = (subtotal * Number(form.sgst_rate || 0)) / 100;
    const igst_amount = (subtotal * Number(form.igst_rate || 0)) / 100;
    const grand_total = subtotal + cgst_amount + sgst_amount + igst_amount;
    const total_quantity = form.line_items.reduce(
      (s, li) => s + Number(li.quantity || 0),
      0,
    );
    return {
      subtotal,
      cgst_amount,
      sgst_amount,
      igst_amount,
      grand_total,
      total_quantity,
    };
  }, [form]);

  const save = async () => {
    setFormError("");

    // Guard: every line must have an internal SSK style picked.
    const unresolved = form.line_items
      .map((li, i) => ({ li, i }))
      .filter(
        ({ li }) =>
          !li.style_code ||
          !validStyleCodes.has(li.style_code.trim().toUpperCase()),
      );
    if (unresolved.length > 0) {
      setFormError(
        `${unresolved.length} line item(s) still need an SSK style mapped. Pick one from the "SSK Style" dropdown for each red row before saving.`,
      );
      return;
    }

    try {
      const body = {
        ...form,
        line_items: form.line_items.map((li) => ({
          ...li,
          quantity: Number(li.quantity),
          unit_price: Number(li.unit_price),
          amount: Number(li.amount),
        })),

        cgst_rate: Number(form.cgst_rate),
        sgst_rate: Number(form.sgst_rate),
        igst_rate: Number(form.igst_rate),
        cgst_amount: totals.cgst_amount,
        sgst_amount: totals.sgst_amount,
        igst_amount: totals.igst_amount,
        subtotal: totals.subtotal,
        grand_total: totals.grand_total,
        total_quantity: totals.total_quantity,
      };
      if (editId) await http.patch(`/pos/${editId}`, body);
      else await http.post("/pos", body);
      setOpen(false);
      load();
    } catch (err) {
      setFormError(err.response?.data?.detail || err.message);
    }
  };

  const remove = (id) => {
    setConfirm({
      title: "Delete Purchase Order",
      message:
        "Are you sure you want to delete this Purchase Order? All associated production jobs will also be deleted from the system.",
      onConfirm: async () => {
        await http.delete(`/pos/${id}`);
        setConfirm(null);
        load();
      },
    });
  };

  const downloadPacking = (po) => {
    setPreviewPo(po);
  };

  return (
    <div>
      <PageHeader
        title="Purchase Orders"
        subtitle="Orders / Purchase Orders"
        testId="pos-header"
        action={
          <div className="flex gap-2 items-center flex-wrap">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => openMultiBudget(selectedPoIds)}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wider bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-700 hover:to-amber-800 text-white rounded shadow-sm transition-all"
                data-testid="header-multi-po-budget-btn"
                title="Calculate production budget from planning stage across multiple POs & styles"
              >
                <Calculator className="w-4 h-4 text-white" />
                <span>
                  Budget Calculator {selectedPoIds.length ? `(${selectedPoIds.length} POs)` : "(Multi-PO)"}
                </span>
              </button>
              <button
                type="button"
                onClick={handleDownloadPoCatalogue}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wider bg-emerald-50 hover:bg-emerald-600 hover:text-white text-emerald-800 border-2 border-emerald-600 rounded shadow-sm transition-all"
                data-testid="header-po-catalogue-download-btn"
                title="Download Excel catalogue with photos for PO styles (matching catalogue.xlsx)"
              >
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                <span>Catalogue Download</span>
              </button>
              <button
                data-testid="pos-export-btn"
                onClick={() =>
                  triggerApiExport(
                    "/pos/export",
                    { format: "xlsx" },
                    "SSK_Customer_POs.xlsx"
                  )
                }
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wider bg-white border-2 border-slate-300 hover:border-slate-900 transition-colors shadow-sm text-slate-700"
                title="Export Customer POs to Excel (.xlsx)"
              >
                <FileDown className="w-3.5 h-3.5 text-emerald-600" />
                <span>Export (Excel)</span>
              </button>
              <button
                data-testid="pos-export-csv-btn"
                onClick={() =>
                  triggerApiExport(
                    "/pos/export",
                    { format: "csv" },
                    "SSK_Customer_POs.csv"
                  )
                }
                className="px-2.5 py-2 text-xs font-bold uppercase tracking-wider bg-white border-2 border-slate-300 hover:border-slate-900 transition-colors shadow-sm text-slate-700"
                title="Export Customer POs to CSV"
              >
                CSV
              </button>
            </div>
            <label
              className="bg-[#C27842] text-white font-bold uppercase tracking-wider text-xs px-3 sm:px-5 py-2.5 border-2 border-[#C27842] shadow-ind hover:bg-[#A65D24] cursor-pointer flex items-center gap-2"
              data-testid="upload-po-label"
            >
              {uploading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              <span className="hidden sm:inline">
                {uploading ? "Extracting..." : "Upload PO (AI)"}
              </span>
              {uploading && <span className="inline sm:hidden">...</span>}
              <input
                type="file"
                accept=".pdf,.xlsx,.xls"
                className="hidden"
                onChange={onExtractFile}
                disabled={uploading}
                data-testid="upload-po-input"
              />
            </label>
            <BtnPrimary
              onClick={startNew}
              data-testid="new-po-btn"
              className="px-3 sm:px-5"
            >
              <Plus className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">New PO</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        <div
          className="bg-[#1E3A8A] text-white p-4 flex items-center gap-3 border-2 border-[#1E3A8A]"
          data-testid="po-ai-banner"
        >
          <Sparkles className="w-5 h-5 text-[#C27842]" />
          <div>
            <div className="font-bold text-sm uppercase tracking-wider">
              AI-Powered PO Intake
            </div>
            <div className="text-xs text-slate-300 mt-0.5">
              Upload any PDF or Excel purchase order — we'll auto-extract line
              items, sizes, tax breakdown and create production jobs
              automatically.
            </div>
          </div>
        </div>

        {/* Tabs Bar: Active vs Completed */}
        <div className="flex items-center justify-between border-b border-slate-200">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setStatusFilter("active")}
              data-testid="tab-active-pos"
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                statusFilter === "active"
                  ? "border-[#1E3A8A] text-[#1E3A8A]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Active
              <span
                className={`px-2 py-0.5 text-[10px] rounded-full font-mono font-bold ${
                  statusFilter === "active"
                    ? "bg-[#1E3A8A] text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {activePos.length}
              </span>
            </button>
            <button
              onClick={() => setStatusFilter("completed")}
              data-testid="tab-completed-pos"
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                statusFilter === "completed"
                  ? "border-[#16A34A] text-[#16A34A]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              Completed
              <span
                className={`px-2 py-0.5 text-[10px] rounded-full font-mono font-bold ${
                  statusFilter === "completed"
                    ? "bg-[#16A34A] text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {completedPos.length}
              </span>
            </button>
          </div>
        </div>

        {/* Multi-PO Selection & Batch Production Planning Banner */}
        {selectedPoIds.length > 0 && (
          <div className="bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-slate-50 border-2 border-amber-500/30 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 text-xs" data-testid="multi-po-selection-banner">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-amber-600 text-white font-bold">
                <Calculator className="w-4 h-4" />
              </span>
              <div>
                <span className="font-bold text-slate-900">
                  {selectedPoIds.length} Purchase Order(s) Selected
                </span>
                <span className="text-slate-500 text-[11px] block sm:inline sm:ml-2">
                  Total {pos.filter(p => selectedPoIds.includes(p.id)).reduce((acc, p) => acc + (p.total_quantity || 0), 0)} pairs across selected POs
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => openMultiBudget(selectedPoIds)}
                className="px-3.5 py-1.5 bg-[#C27842] hover:bg-[#A65D24] text-white rounded font-bold text-xs uppercase tracking-wider inline-flex items-center gap-1.5 shadow-sm transition-colors"
                data-testid="calculate-selected-pos-budget-btn"
              >
                <Calculator className="w-3.5 h-3.5" />
                <span>Calculate Production Budget</span>
              </button>
              <button
                type="button"
                onClick={handleDownloadPoCatalogue}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-bold text-xs inline-flex items-center gap-1 shadow-sm transition-colors"
                data-testid="download-selected-pos-catalogue-btn"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" />
                <span>Download Catalogue (.xlsx)</span>
              </button>
              <button
                type="button"
                onClick={() => setSelectedPoIds([])}
                className="px-2.5 py-1.5 bg-white border border-slate-300 text-slate-600 hover:bg-slate-50 rounded font-semibold text-xs"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="pos-table">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-3 font-bold w-10 text-center bg-slate-50">
                    <input
                      type="checkbox"
                      checked={selectedPoIds.length === displayedPos.length && displayedPos.length > 0}
                      onChange={toggleSelectAllPos}
                      title="Select all POs for batch budget planning"
                      className="w-4 h-4 text-[#C27842] rounded border-slate-300"
                      data-testid="select-all-pos-checkbox"
                    />
                  </th>
                  <th className="px-4 py-3 font-bold sticky left-0 z-10 bg-slate-50">PO # &amp; Styles</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3 font-bold">Date</th>
                  <th className="px-4 py-3 font-bold">Client</th>
                  <th className="px-4 py-3 font-bold text-right">Lines</th>
                  <th className="px-4 py-3 font-bold text-right">Qty</th>
                  <th className="px-4 py-3 font-bold text-right">
                    Grand Total
                  </th>
                  <th className="px-4 py-3 font-bold">Delivery</th>
                  <th className="px-4 py-3 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {displayedPos.length === 0 ? (
                  <tr>
                    <td
                      colSpan="9"
                      className="px-6 py-10 text-center text-slate-400"
                    >
                      {statusFilter === "completed"
                        ? "No completed POs yet. POs with all jobs dispatched and invoiced will appear here."
                        : "No active POs. Click \"New PO\" or \"Upload PO (AI)\" to import one."}
                    </td>
                  </tr>
                ) : (
                  paginatedPos.map((p) => (
                    <tr
                      key={p.id}
                      className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${
                        selectedPoIds.includes(p.id) ? "bg-amber-50/40" : ""
                      }`}
                    >
                      <td className="px-3 py-3 text-center">
                        <input
                          type="checkbox"
                          checked={selectedPoIds.includes(p.id)}
                          onChange={() => togglePoSelect(p.id)}
                          title="Select this PO for budget calculation"
                          className="w-4 h-4 text-[#C27842] rounded border-slate-300"
                          data-testid={`select-po-${p.po_number}`}
                        />
                      </td>
                      <td className="px-4 py-3 font-mono font-bold sticky left-0 z-10 bg-white">
                        <div className="flex items-center gap-2">
                          <span className="text-slate-900">{p.po_number}</span>
                        </div>
                        {/* Style preview photos for this PO */}
                        <div className="flex items-center -space-x-1.5 mt-1" title="Styles in this PO">
                          {(p.line_items || []).slice(0, 3).map((li, i) => (
                            <ImageThumb
                              key={i}
                              image={getStyleImage(li.style_code, li)}
                              size={22}
                              className="rounded-full border-2 border-white shadow-xs inline-block"
                              alt={li.style_code}
                              title={`${li.style_code} (${li.quantity} prs)`}
                            />
                          ))}
                          {(p.line_items || []).length > 3 && (
                            <span className="text-[9px] font-bold text-slate-500 bg-slate-100 rounded-full px-1 border border-slate-300">
                              +{p.line_items.length - 3}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {p.is_completed || p.status === "completed" ? (
                          <Badge tone="success" className="text-[10px] uppercase font-bold tracking-wider">
                            Completed
                          </Badge>
                        ) : (
                          <Badge tone="amber" className="text-[10px] uppercase font-bold tracking-wider">
                            Active
                          </Badge>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs">{p.po_date}</td>
                      <td className="px-4 py-3">{p.client_name}</td>
                      <td className="px-4 py-3 text-right font-mono">
                        {p.line_items?.length || 0}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {p.total_quantity}
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-bold">
                        {inr(p.grand_total)}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {p.delivery_date || "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => openPoDocuments(p, "all")}
                          className="text-slate-600 hover:text-[#C27842] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation"
                          title="Invoices & Packing Lists"
                          data-testid={`invoice-${p.po_number}`}
                          disabled={loadingInvoices && selectedPoForInvoices?.id === p.id}
                        >
                          {loadingInvoices && selectedPoForInvoices?.id === p.id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-[#C27842]" />
                          ) : (
                            <ReceiptIndianRupee className="w-4 h-4" />
                          )}
                        </button>
                        <button
                          onClick={() => {
                            setSelectedPoForEan(p);
                            setPoEanModalOpen(true);
                          }}
                          className="text-slate-600 hover:text-[#0D9488] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          title="Client Barcodes / EAN Import"
                          data-testid={`ean-${p.po_number}`}
                        >
                          <Barcode className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openMultiBudget([p.id])}
                          className="text-slate-600 hover:text-amber-600 p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          title="Calculate Production Budget for this PO"
                          data-testid={`calc-budget-${p.po_number}`}
                        >
                          <Calculator className="w-4 h-4 text-amber-600" />
                        </button>
                        <button
                          onClick={() => openView(p)}
                          className="text-slate-600 hover:text-[#2563EB] p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                          data-testid={`view-po-${p.po_number}`}
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => remove(p.id)}
                          className="text-slate-600 hover:text-red-600 p-2 min-h-[44px] min-w-[44px] inline-flex items-center justify-center touch-manipulation ml-1"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="px-5 py-3 bg-white border-t border-slate-200">
            <PaginationControls {...poPaginationProps} />
          </div>
        </Card>
      </div>

      {open && (
        <Drawer
          onClose={() => {
            setOpen(false);
            setFormError("");
          }}
          title={editId ? "Edit Purchase Order" : "New Purchase Order"}
          width="max-w-5xl"
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="col-span-2 sm:col-span-1">
                <Input
                  label="PO Number"
                  value={form.po_number}
                  onChange={(e) => {
                    setFormError("");
                    setForm({ ...form, po_number: e.target.value });
                  }}
                  testId="form-po-number"
                />
                {formError && (
                  <p
                    className="mt-1 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2"
                    data-testid="form-po-error"
                  >
                    {formError}
                  </p>
                )}
              </div>
              <Input
                label="PO Date"
                type="date"
                value={form.po_date}
                onChange={(e) => setForm({ ...form, po_date: e.target.value })}
              />
              <Input
                label="Delivery Date"
                type="date"
                value={form.delivery_date}
                onChange={(e) =>
                  setForm({ ...form, delivery_date: e.target.value })
                }
              />
            </div>
            <Input
              label="Client Name"
              value={form.client_name}
              onChange={(e) =>
                setForm({ ...form, client_name: e.target.value })
              }
              testId="form-po-client"
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Billing Address"
                value={form.billing_address}
                onChange={(e) =>
                  setForm({ ...form, billing_address: e.target.value })
                }
              />
              <Input
                label="Shipping Address"
                value={form.shipping_address}
                onChange={(e) =>
                  setForm({ ...form, shipping_address: e.target.value })
                }
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Input
                label="Client GSTIN"
                value={form.client_gstin}
                onChange={(e) => {
                  const gstin = e.target.value.toUpperCase();
                  let sc = form.client_state_code;
                  if (
                    gstin.length >= 2 &&
                    /^\d{2}$/.test(gstin.substring(0, 2))
                  ) {
                    sc = gstin.substring(0, 2);
                  }
                  setForm({
                    ...form,
                    client_gstin: gstin,
                    client_state_code: sc,
                  });
                }}
                testId="form-po-client-gstin"
              />
              <Input
                label="Client State"
                value={form.client_state}
                onChange={(e) =>
                  setForm({ ...form, client_state: e.target.value })
                }
              />
              <Input
                label="Client State Code"
                value={form.client_state_code}
                onChange={(e) =>
                  setForm({ ...form, client_state_code: e.target.value })
                }
              />
            </div>
            <Input
              label="Payment Terms"
              value={form.payment_terms}
              onChange={(e) =>
                setForm({ ...form, payment_terms: e.target.value })
              }
            />

            <div className="flex items-baseline justify-between pt-3">
              <h3 className="text-sm font-bold uppercase tracking-wider">
                Line Items
              </h3>
              <button
                type="button"
                onClick={addLine}
                className="text-xs font-bold uppercase tracking-wider text-[#2563EB] py-2 px-3 min-h-[44px] touch-manipulation"
                data-testid="add-line-btn"
              >
                + Add line
              </button>
            </div>
            <div className="bg-blue-50 border-2 border-blue-200 px-3 py-2 text-[11px] text-blue-900">
              <strong>SKU mapping is compulsory.</strong> Each PO line must be tied to an internal SSK style. If the client&apos;s external code hasn&apos;t been mapped yet, pick the matching style from the dropdown — we&apos;ll remember it for future POs from this client.
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-2 border-slate-200">
                <thead className="bg-slate-50">
                  <tr className="text-left">
                    <th className="px-2 py-2 font-bold sticky left-0 z-10 bg-slate-50">External SKU</th>
                    <th className="px-2 py-2 font-bold text-center w-12">Photo</th>
                    <th className="px-2 py-2 font-bold">SSK Style *</th>
                    <th className="px-2 py-2 font-bold">Description</th>
                    <th className="px-2 py-2 font-bold">Color</th>
                    <th className="px-2 py-2 font-bold">Size</th>
                    <th className="px-2 py-2 font-bold">HSN</th>
                    <th className="px-2 py-2 font-bold text-right">Qty</th>
                    <th className="px-2 py-2 font-bold text-right">Rate</th>
                    <th className="px-2 py-2 font-bold text-right">Amount</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {form.line_items.map((li, i) => {
                    const isStyleValid =
                      li.style_code &&
                      validStyleCodes.has(li.style_code.trim().toUpperCase());
                    const isNewMapping =
                      isStyleValid &&
                      li.external_sku &&
                      li.external_sku.trim().toUpperCase() !==
                      li.style_code.trim().toUpperCase();
                    return (
                      <tr
                        key={i}
                        className={`border-t border-slate-200 ${!isStyleValid ? "bg-red-50/40" : ""
                          }`}
                        data-testid={`po-line-${i}`}
                      >
                        <td className="px-1 py-1 sticky left-0 z-10 bg-white">
                          <input
                            value={li.external_sku || ""}
                            onChange={(e) =>
                              updateLine(i, "external_sku", e.target.value)
                            }
                            className="w-32 border border-slate-300 px-1 py-0.5 font-mono bg-slate-50"
                            placeholder="Client code"
                            title="External SKU from the client's PO / marketplace"
                            data-testid={`po-line-${i}-ext-sku`}
                          />
                        </td>
                        <td className="px-1 py-1 min-w-[160px] relative">
                          <SearchableSelect
                            options={styles}
                            value={li.style_code || ""}
                            onChange={(code) => updateLine(i, "style_code", code)}
                            getKey={(s) => s.code}
                            getLabel={(s) => `${s.code} · ${s.name}`}
                            placeholder="— pick SSK style —"
                            testId={`po-line-${i}-style-select`}
                          />
                          {!isStyleValid && (
                            <div
                              className="text-[9px] text-red-600 font-bold mt-0.5"
                              data-testid={`po-line-${i}-resolution-warning`}
                            >
                              {li.resolution_warning || "Mapping required"}
                            </div>
                          )}

                          {isNewMapping && (
                            <div
                              className="text-[9px] text-blue-700 font-bold mt-0.5"
                              title={`On save we'll remember: ${li.external_sku} → ${li.style_code} for ${form.client_name || "this client"}`}
                            >
                              New mapping will be saved
                            </div>
                          )}
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.description}
                            onChange={(e) =>
                              updateLine(i, "description", e.target.value)
                            }
                            className="w-44 border border-slate-300 px-1 py-0.5"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.color}
                            onChange={(e) =>
                              updateLine(i, "color", e.target.value)
                            }
                            className="w-20 border border-slate-300 px-1 py-0.5"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.size}
                            onChange={(e) =>
                              updateLine(i, "size", e.target.value)
                            }
                            className="w-12 border border-slate-300 px-1 py-0.5 text-center font-mono"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            value={li.hsn_code}
                            onChange={(e) =>
                              updateLine(i, "hsn_code", e.target.value)
                            }
                            className="w-20 border border-slate-300 px-1 py-0.5 font-mono"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            type="number"
                            value={li.quantity}
                            onChange={(e) =>
                              updateLine(i, "quantity", e.target.value)
                            }
                            inputMode="numeric"
                            className="w-16 border border-slate-300 px-1 py-2 text-right font-mono text-xs min-h-[44px]"
                          />
                        </td>
                        <td className="px-1 py-1">
                          <input
                            type="number"
                            step="0.01"
                            value={li.unit_price}
                            onChange={(e) =>
                              updateLine(i, "unit_price", e.target.value)
                            }
                            inputMode="decimal"
                            className="w-20 border border-slate-300 px-1 py-2 text-right font-mono text-xs min-h-[44px]"
                          />
                        </td>
                        <td className="px-2 py-1 text-right font-mono font-bold">
                          {inr(li.amount)}
                        </td>
                        <td className="px-1 py-1">
                          <button
                            onClick={() => removeLine(i)}
                            className="text-slate-500 hover:text-red-600"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-6 pt-3">
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Input
                    label="CGST %"
                    type="number"
                    step="0.01"
                    value={form.cgst_rate}
                    onChange={(e) =>
                      setForm({ ...form, cgst_rate: e.target.value })
                    }
                  />
                  <Input
                    label="SGST %"
                    type="number"
                    step="0.01"
                    value={form.sgst_rate}
                    onChange={(e) =>
                      setForm({ ...form, sgst_rate: e.target.value })
                    }
                  />
                  <Input
                    label="IGST %"
                    type="number"
                    step="0.01"
                    value={form.igst_rate}
                    onChange={(e) =>
                      setForm({ ...form, igst_rate: e.target.value })
                    }
                  />
                </div>
                <Input
                  label="Notes"
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </div>
              <div className="bg-[#0F172A] text-white p-5 border-2 border-[#0F172A]">
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold mb-3">
                  Summary
                </div>
                <Total label="Subtotal" value={inr(totals.subtotal)} />
                <Total label="CGST" value={inr(totals.cgst_amount)} />
                <Total label="SGST" value={inr(totals.sgst_amount)} />
                <Total label="IGST" value={inr(totals.igst_amount)} />
                <div className="border-t border-dashed border-slate-600 my-2" />
                <Total label="Total Qty" value={totals.total_quantity} />
                <Total
                  label="Grand Total"
                  value={inr(totals.grand_total)}
                  big
                />
              </div>
            </div>

            <div className="flex gap-2 pt-3 border-t border-slate-200">
              <BtnPrimary onClick={save} data-testid="save-po-btn">
                <Save className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
                Purchase Order
              </BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}

      {view && (
        <Drawer
          onClose={() => setView(null)}
          title={`PO ${view.po_number}`}
          width="max-w-4xl"
        >
          <div className="space-y-4 text-sm">
            {/* PO-level Document & Barcode Actions Toolbar */}
            <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-wrap items-center justify-between gap-2.5">
              <div className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                PO Operations &amp; Documents
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => openPoDocuments(view, "all")}
                  className="px-3 py-1.5 text-xs font-bold text-white bg-[#C27842] hover:bg-[#a86535] border border-[#C27842] rounded shadow-sm inline-flex items-center gap-1.5 min-h-[34px] transition-colors"
                  data-testid="detail-invoices-packing-btn"
                  title="View list of invoices and packing lists produced for this PO"
                >
                  <ReceiptIndianRupee className="w-3.5 h-3.5" />
                  <span>
                    Invoices &amp; Packing Lists
                    {viewDocuments ? ` (${(viewDocuments.invoices?.length || 0) + (viewDocuments.dispatch_records?.length || 0)})` : ""}
                  </span>
                </button>
                <button
                  onClick={() => {
                    setSelectedPoForEan(view);
                    setPoEanModalOpen(true);
                  }}
                  className="px-3 py-1.5 text-xs font-bold text-teal-800 bg-teal-50 hover:bg-teal-100 border border-teal-300 rounded shadow-sm inline-flex items-center gap-1.5 min-h-[34px] transition-colors"
                  data-testid="detail-upload-barcode-btn"
                  title="Upload and manage client barcode EAN mappings for this PO"
                >
                  <Barcode className="w-3.5 h-3.5 text-teal-600" />
                  <span>Upload Barcode File</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Client" value={view.client_name} />
              <Field label="Client GSTIN" value={view.client_gstin || "—"} />
              <Field
                label="Client State"
                value={
                  view.client_state
                    ? `${view.client_state} (Code: ${view.client_state_code})`
                    : "—"
                }
              />
              <Field label="PO Date" value={view.po_date} />
              <Field label="Delivery" value={view.delivery_date} />
              <Field label="Payment Terms" value={view.payment_terms} />
              <div>
                <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500 mb-1">
                  Status
                </div>
                <div>
                  {view.is_completed || view.status === "completed" ? (
                    <Badge tone="success" className="text-[10px] uppercase font-bold tracking-wider">
                      Completed
                    </Badge>
                  ) : (
                    <Badge tone="amber" className="text-[10px] uppercase font-bold tracking-wider">
                      Active
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <div>
              <Field label="Billing" value={view.billing_address} />
              <Field label="Shipping" value={view.shipping_address} />
            </div>

            {/* ── PLANNING STAGE: KARIGAR & WORKER ALLOCATION SECTION ── */}
            <div className="border-2 border-violet-200 bg-gradient-to-br from-violet-50/80 to-indigo-50/80 rounded-xl p-3.5 space-y-3" data-testid="po-planning-stage-section">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-violet-600 text-white">
                    <HardHat className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-violet-950">
                        Planning Stage · Karigar Allocation
                      </h3>
                      {planningData && (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                          planningData.is_fully_allocated
                            ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                            : "bg-amber-100 text-amber-900 border-amber-300"
                        }`} data-testid="po-allocation-progress-badge">
                          {planningData.allocated_count} / {planningData.total_roles} Allocated
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-violet-700">
                      Allocate karigars to determine actual labour cost &amp; manufacturing budget
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => navigate("/production")}
                    className="text-xs font-bold text-violet-700 hover:text-violet-900 hover:underline inline-flex items-center gap-1"
                    title="Open in Kanban Production board"
                  >
                    Kanban Planning <ArrowRight className="w-3 h-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowPlanningSection(!showPlanningSection)}
                    className="p-1 rounded text-violet-600 hover:bg-violet-100 transition-colors"
                    title={showPlanningSection ? "Collapse Karigar Allocation" : "Expand Karigar Allocation"}
                  >
                    {showPlanningSection ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {showPlanningSection && (
                <div>
                  {loadingPlanning ? (
                    <div className="py-4 text-center text-xs text-violet-600 flex items-center justify-center gap-1.5">
                      <Loader2 className="w-4 h-4 animate-spin" /> Loading planning roles &amp; karigars...
                    </div>
                  ) : planningData?.roles?.length ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1">
                      {planningData.roles.map((r) => (
                        <div
                          key={r.key}
                          className={`p-2.5 rounded-lg border text-xs transition-all ${
                            r.is_allocated
                              ? "bg-white border-violet-200 shadow-xs"
                              : "bg-violet-100/40 border-dashed border-violet-300 hover:border-violet-400"
                          }`}
                          data-testid={`karigar-role-${r.key}`}
                        >
                          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                            <span className="truncate">{r.label}</span>
                            <span className="text-[9px] px-1 py-0.2 rounded bg-slate-100 text-slate-600 font-mono">
                              {r.category}
                            </span>
                          </div>
                          {r.is_allocated ? (
                            <div className="flex items-center justify-between gap-1 pt-0.5">
                              <div className="min-w-0">
                                <div className="font-bold text-slate-900 truncate flex items-center gap-1">
                                  <UserCheck className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                                  <span className="truncate">{r.worker_name}</span>
                                </div>
                                <div className="text-[11px] font-mono font-semibold text-[#C27842]">
                                  {inr(r.rate_per_pair)} <span className="text-[9px] text-slate-400 font-normal">/ pair</span>
                                </div>
                              </div>
                              <button
                                type="button"
                                onClick={() =>
                                  setAssignModal({
                                    role: r.key,
                                    roleLabel: r.label,
                                    workerId: r.worker_id,
                                    rate: r.rate_per_pair,
                                    currentWorkerId: r.worker_id,
                                  })
                                }
                                className="px-2 py-1 text-[10px] font-bold text-violet-700 hover:bg-violet-50 rounded border border-violet-200 flex-shrink-0"
                                data-testid={`edit-role-${r.key}`}
                              >
                                Change
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() =>
                                setAssignModal({
                                  role: r.key,
                                  roleLabel: r.label,
                                  workerId: "",
                                  rate: "",
                                  currentWorkerId: null,
                                })
                              }
                              className="w-full mt-1 py-1.5 px-2 text-[11px] font-bold text-violet-700 bg-white hover:bg-violet-50 border border-violet-300 rounded shadow-xs flex items-center justify-center gap-1 transition-colors"
                              data-testid={`allocate-btn-${r.key}`}
                            >
                              <Plus className="w-3 h-3 text-violet-600" /> Allocate Karigar
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-2 text-xs text-slate-500">
                      No manufacturing roles available for allocation.
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="pt-2">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Line Items &amp; PO Profitability
                </h3>
                <span className="text-[11px] text-slate-500 italic">
                  Profit = PO Rate − (BOM + Labor + Outside + Packing)
                </span>
              </div>
              <div className="overflow-x-auto border-2 border-slate-200">
                <table className="w-full text-xs">
                  <thead className="bg-slate-100 border-b border-slate-200">
                    <tr className="text-left font-bold text-slate-700 text-[11px]">
                      <th className="px-2.5 py-2">Style / Desc</th>
                      <th className="px-2 py-2 text-right">Qty</th>
                      <th className="px-2 py-2 text-right">PO Rate</th>
                      <th className="px-2.5 py-2">Cost Breakdown / Pair</th>
                      <th className="px-2.5 py-2 text-right">Profit / Pair</th>
                      <th className="px-2.5 py-2 text-right">Line Profit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {view.line_items.map((li, i) => {
                      const prof = li.profitability;
                      const isIncluded = poViewSelectedLines.includes(i);
                      const lineProfit =
                        prof && prof.profit != null
                          ? prof.profit * Number(li.quantity || 0)
                          : null;
                      return (
                        <tr
                          key={i}
                          className={`hover:bg-slate-50/80 transition-colors ${
                            !isIncluded ? "opacity-40 bg-slate-100/50" : ""
                          }`}
                        >
                          <td className="px-2 py-2 text-center">
                            <input
                              type="checkbox"
                              checked={isIncluded}
                              onChange={() => {
                                setPoViewSelectedLines((prev) =>
                                  prev.includes(i) ? prev.filter((idx) => idx !== i) : [...prev, i]
                                );
                              }}
                              className="w-3.5 h-3.5 text-[#C27842] rounded border-slate-300 cursor-pointer"
                              title="Include / exclude this style from production budget"
                            />
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <ImageThumb
                              image={getStyleImage(li.style_code, li)}
                              size={40}
                              alt={li.style_code}
                              clickable
                              className="rounded border shadow-xs inline-block"
                            />
                          </td>
                          <td className="px-2.5 py-2">
                            <div className="font-mono font-bold text-slate-900">
                              {li.style_code}
                            </div>
                            <div className="text-[11px] text-slate-500">
                              {li.description ||
                                `${li.color || ""} ${li.size ? "Sz " + li.size : ""}`}
                            </div>
                          </td>
                          <td className="px-2 py-2 text-right font-mono font-semibold">
                            {li.quantity}
                          </td>
                          <td className="px-2 py-2 text-right font-mono font-bold text-slate-800">
                            {inr(li.unit_price)}
                          </td>
                          <td className="px-2.5 py-2 text-[11px]">
                            {prof ? (
                              <div className="space-y-0.5">
                                <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-slate-600">
                                  <span>BOM: <strong className="font-mono">{inr(prof.bom_cost)}</strong></span>
                                  <span>Pack: <strong className="font-mono">{inr(prof.packing_cost)}</strong></span>
                                  {Number(prof.outside_cost || 0) > 0 && (
                                    <span>Outside: <strong className="font-mono text-purple-700">{inr(prof.outside_cost)}</strong></span>
                                  )}
                                </div>
                                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                                  <span>Labor: <strong className="font-mono">{inr(prof.labor_cost)}</strong></span>
                                  {prof.is_estimated ? (
                                    <span
                                      className="px-1.5 py-0.2 bg-amber-100 text-amber-900 border border-amber-300 text-[9px] font-bold uppercase rounded"
                                      title="No production job data yet; using planned style labor cost."
                                    >
                                      Estimated Labor
                                    </span>
                                  ) : (
                                    <span
                                      className="px-1.5 py-0.2 bg-emerald-100 text-emerald-900 border border-emerald-300 text-[9px] font-bold uppercase rounded"
                                      title="Computed from real production job assignments for this style."
                                    >
                                      Actual Labor
                                    </span>
                                  )}
                                  {Number(prof.outside_cost || 0) > 0 && (
                                    prof.outside_source === "actual" ? (
                                      <span
                                        className="px-1.5 py-0.2 bg-purple-100 text-purple-900 border border-purple-300 text-[9px] font-bold uppercase rounded"
                                        title="Computed from production job outside labour / subcontract work."
                                      >
                                        Actual Outside
                                      </span>
                                    ) : (
                                      <span
                                        className="px-1.5 py-0.2 bg-violet-100 text-violet-900 border border-violet-300 text-[9px] font-bold uppercase rounded"
                                        title="Planned outside labour / subcontract from style master."
                                      >
                                        Est Outside
                                      </span>
                                    )
                                  )}
                                </div>
                              </div>
                            ) : (
                              <span className="text-slate-400 italic">—</span>
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right font-mono">
                            {prof && prof.profit != null ? (
                              <div>
                                <div
                                  className={`font-bold ${prof.profit >= 0 ? "text-emerald-700" : "text-red-600"
                                    }`}
                                >
                                  {prof.profit >= 0 ? "+" : ""}
                                  {inr(prof.profit)}
                                </div>
                                {prof.profit_pct != null && (
                                  <div
                                    className={`text-[10px] font-semibold ${prof.profit >= 0 ? "text-emerald-600" : "text-red-500"
                                      }`}
                                  >
                                    ({prof.profit_pct}%)
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span className="text-slate-400 italic">—</span>
                            )}
                          </td>
                          <td className="px-2.5 py-2 text-right font-mono font-bold">
                            {lineProfit != null ? (
                              <span
                                className={
                                  lineProfit >= 0 ? "text-emerald-700" : "text-red-600"
                                }
                              >
                                {lineProfit >= 0 ? "+" : ""}
                                {inr(lineProfit)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bg-slate-50 p-4 grid grid-cols-2 gap-2 text-xs">
              <div>
                Subtotal:{" "}
                <span className="font-mono font-bold ml-2">
                  {inr(view.subtotal)}
                </span>
              </div>
              <div>
                CGST:{" "}
                <span className="font-mono ml-2">{inr(view.cgst_amount)}</span>
              </div>
              <div>
                SGST:{" "}
                <span className="font-mono ml-2">{inr(view.sgst_amount)}</span>
              </div>
              <div>
                IGST:{" "}
                <span className="font-mono ml-2">{inr(view.igst_amount)}</span>
              </div>
              <div className="col-span-2 text-lg font-black border-t pt-2 flex justify-between items-baseline">
                <span>
                  Grand Total:{" "}
                  <span className="font-mono text-[#C27842] ml-2">
                    {inr(view.grand_total)}
                  </span>
                </span>
              </div>
            </div>

            {/* ── PRODUCTION BUDGET & COST TO COMPLETE SECTION ── */}
            <div className="rounded-xl border-2 border-amber-500/30 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white p-4 shadow-lg space-y-3" data-testid="po-production-budget-card">
              <div className="flex items-center justify-between pb-2.5 border-b border-slate-700">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-[#C27842]/20 border border-[#C27842]/40 text-[#C27842]">
                    <Calculator className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                      Production Budget (Cost to Complete)
                    </h4>
                    <p className="text-[10px] text-slate-400">
                      Estimated funds required to complete manufacturing for {view.total_quantity || 0} pairs
                    </p>
                  </div>
                </div>
                <div>
                  {poBudget?.isLaborEstimated ? (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40" title="One or more karigar roles not yet allocated; using estimated style planned labor.">
                      <AlertCircle className="w-3 h-3 text-amber-400" />
                      Estimated Labor Rates
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" title="Computed from real allocated karigar piece rates.">
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                      Actual Allocated Karigar Rates
                    </span>
                  )}
                </div>
              </div>

              {/* 4 Cost Breakdown KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                {/* Total BOM */}
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-lg p-2.5" data-testid="budget-total-bom">
                  <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total BOM Cost
                  </div>
                  <div className="text-base font-black font-mono text-white mt-0.5">
                    {inr(poBudget?.totalBom)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    Raw materials &amp; soles
                  </div>
                </div>

                {/* Total Labour */}
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-lg p-2.5" data-testid="budget-total-labor">
                  <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total Labour Cost
                  </div>
                  <div className="text-base font-black font-mono text-amber-400 mt-0.5">
                    {inr(poBudget?.totalLabor)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5 flex items-center justify-between">
                    <span>Karigar piece wages</span>
                    {!poBudget?.isLaborEstimated ? (
                      <span className="text-[9px] text-emerald-400 font-bold">Allocated</span>
                    ) : (
                      <span className="text-[9px] text-amber-400 font-bold">Planned</span>
                    )}
                  </div>
                </div>

                {/* Total Packing */}
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-lg p-2.5" data-testid="budget-total-packing">
                  <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total Packing Cost
                  </div>
                  <div className="text-base font-black font-mono text-cyan-400 mt-0.5">
                    {inr(poBudget?.totalPacking)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    Cartons, boxes &amp; labels
                  </div>
                </div>

                {/* Total Production Budget */}
                <div className="bg-[#C27842]/20 border border-[#C27842]/50 rounded-lg p-2.5" data-testid="budget-total-production">
                  <div className="text-[10px] uppercase font-bold text-amber-200 tracking-wider">
                    Production Budget
                  </div>
                  <div className="text-base font-black font-mono text-[#F59E0B] mt-0.5">
                    {inr(poBudget?.totalCost)}
                  </div>
                  <div className="text-[10px] text-amber-200/80 mt-0.5 font-semibold">
                    Cost to Complete
                  </div>
                </div>
              </div>

              {/* Commercial Comparison: Revenue vs Budget vs Expected Profit */}
              <div className="pt-2.5 border-t border-slate-700/80 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex flex-wrap items-center gap-3">
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 font-semibold block">PO Subtotal (Revenue)</span>
                    <span className="font-mono font-bold text-white text-sm">{inr(view.subtotal)}</span>
                  </div>
                  <span className="text-slate-500 font-mono text-base hidden sm:inline">−</span>
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 font-semibold block">Total Budget (Cost)</span>
                    <span className="font-mono font-bold text-amber-400 text-sm">{inr(poBudget?.totalCost)}</span>
                  </div>
                  <span className="text-slate-500 font-mono text-base hidden sm:inline">=</span>
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 font-semibold block">Projected Margin</span>
                    <span className={`font-mono font-bold text-sm ${poBudget?.profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {poBudget?.profit >= 0 ? "+" : ""}{inr(poBudget?.profit)} ({poBudget?.profitPct}%)
                    </span>
                  </div>
                </div>
                {Number(poBudget?.totalOutside || 0) > 0 && (
                  <div className="text-[11px] text-purple-300 font-mono">
                    Outside Labour: <b>{inr(poBudget.totalOutside)}</b>
                  </div>
                )}
              </div>
            </div>

            {/* Invoices & Packing Lists Section in PO View */}
            <div className="pt-3 border-t-2 border-slate-200" data-testid="po-view-invoices-and-packing">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ReceiptIndianRupee className="w-4 h-4 text-[#C27842]" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Invoices &amp; Packing Lists Produced
                  </h3>
                </div>
                {viewDocuments && (
                  <span className="text-[11px] font-semibold text-slate-500">
                    Dispatched: <b className="text-[#C27842]">{viewDocuments.total_dispatched_pairs ?? 0}</b> / {view.total_quantity} pairs
                  </span>
                )}
              </div>

              {loadingViewDocs ? (
                <div className="py-6 text-center text-xs text-slate-500 bg-slate-50 rounded-lg border border-slate-200">
                  <Loader2 className="w-4 h-4 animate-spin inline mr-1.5 text-[#C27842]" />
                  Loading invoices &amp; packing lists...
                </div>
              ) : !viewDocuments?.invoices?.length && !viewDocuments?.dispatch_records?.length ? (
                <div className="p-4 bg-slate-50 border border-dashed border-slate-200 rounded-lg text-center space-y-1.5">
                  <div className="text-xs font-semibold text-slate-700">No Invoices or Packing Lists Produced Yet</div>
                  <p className="text-[11px] text-slate-500 max-w-md mx-auto">
                    Invoices and packing lists are generated when packed cartons are dispatched from the Kanban board.
                  </p>
                  <div className="pt-1 flex items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={() => navigate("/production")}
                      className="text-xs font-bold text-[#C27842] hover:underline inline-flex items-center gap-1"
                    >
                      Go to Kanban Production <ArrowRight className="w-3 h-3" />
                    </button>
                    <span className="text-slate-300">|</span>
                    <a
                      href={`${API}/pos/${view.id}/invoice.pdf`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-slate-500 hover:text-slate-700 underline"
                    >
                      Download PO draft invoice
                    </a>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Invoices List */}
                  {viewDocuments?.invoices && viewDocuments.invoices.length > 0 && (
                    <div>
                      <div className="text-[11px] uppercase font-bold text-slate-600 tracking-wider mb-1.5 flex items-center justify-between">
                        <span>Invoices Produced ({viewDocuments.invoices.length})</span>
                        <button
                          type="button"
                          onClick={() => navigate("/invoices")}
                          className="text-[11px] text-slate-500 hover:text-[#C27842] inline-flex items-center gap-1"
                        >
                          View Invoices Ledger <ExternalLink className="w-2.5 h-2.5" />
                        </button>
                      </div>
                      <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-white">
                        {viewDocuments.invoices.map((inv) => (
                          <div key={inv.id} className="p-3 hover:bg-slate-50 flex items-center justify-between gap-3">
                            <div>
                              <div className="font-mono font-bold text-slate-900 text-xs flex items-center gap-2">
                                <span>{inv.invoice_no}</span>
                                {inv.status && <Badge tone="success">{inv.status.toUpperCase()}</Badge>}
                              </div>
                              <div className="text-[11px] text-slate-500 mt-0.5">
                                Date: {inv.invoice_date} | Pairs: <b>{inv.pairs_count || "—"}</b> | Total: <span className="font-mono font-bold text-slate-800">{inr(inv.grand_total)}</span>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <a
                                href={`${API}/invoices/${inv.id}/file?token=${localStorage.getItem('token') || ''}`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2.5 py-1 text-xs font-bold text-white bg-[#C27842] hover:bg-[#a86535] rounded shadow-sm inline-flex items-center gap-1"
                              >
                                <FileDown className="w-3 h-3" /> Invoice PDF
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Packing Lists & Dispatches */}
                  {viewDocuments?.dispatch_records && viewDocuments.dispatch_records.length > 0 && (
                    <div>
                      <div className="text-[11px] uppercase font-bold text-slate-600 tracking-wider mb-1.5">
                        Packing Lists &amp; Dispatches ({viewDocuments.dispatch_records.length})
                      </div>
                      <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-white">
                        {viewDocuments.dispatch_records.map((dr) => (
                          <div key={dr.id} className="p-3 hover:bg-slate-50 flex items-center justify-between gap-3">
                            <div>
                              <div className="font-mono font-bold text-slate-900 text-xs">
                                Dispatch: {dr.invoice_no || dr.id}
                              </div>
                              <div className="text-[11px] text-slate-500 mt-0.5">
                                Date: {dr.dispatched_at ? new Date(dr.dispatched_at).toLocaleDateString() : "—"} | Cartons: <b>{dr.carton_count || 0}</b> | Pairs: <b>{dr.pairs || dr.total_quantity || "—"}</b>
                              </div>
                              {(dr.transporter || dr.vehicle) && (
                                <div className="text-[10px] text-slate-400">
                                  Transport: {dr.transporter || "—"} {dr.vehicle ? `(${dr.vehicle})` : ""}
                                </div>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-1.5">
                              <a
                                href={`${API}/dispatch-records/${dr.id}/packing-list`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2 py-1 text-[11px] font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded inline-flex items-center gap-1"
                              >
                                <Package className="w-3 h-3 text-[#16A34A]" /> Packing List (XLSX)
                              </a>
                              <a
                                href={`${API}/dispatch-records/${dr.id}/carton-labels`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2 py-1 text-[11px] font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded inline-flex items-center gap-1"
                              >
                                <FileText className="w-3 h-3 text-[#F97316]" /> Carton Labels
                              </a>
                              <a
                                href={`${API}/dispatch-records/${dr.id}/ewaybill`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2 py-1 text-[11px] font-bold text-sky-700 bg-sky-50 hover:bg-sky-100 border border-sky-300 rounded inline-flex items-center gap-1"
                                data-testid={`dr-ewaybill-btn-${dr.id}`}
                              >
                                <FileText className="w-3 h-3 text-sky-600" /> E-Way Bill
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </Drawer>
      )}
      {invoiceModalOpen && (
        <Drawer
          title={`Invoices & Packing Lists — ${selectedPoForInvoices?.po_number || ""}`}
          open={invoiceModalOpen}
          onClose={() => setInvoiceModalOpen(false)}
          width="max-w-3xl"
        >
          <div className="space-y-4 p-2">
            {/* Direct 1-Click Action Card if single invoice */}
            {poInvoicesList.length === 1 && (
              <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-bold text-amber-900 flex items-center gap-1.5">
                    <ReceiptIndianRupee className="w-3.5 h-3.5 text-[#C27842]" />
                    <span>Production Invoice: {poInvoicesList[0].invoice_no}</span>
                  </div>
                  <div className="text-[11px] text-amber-800 mt-0.5">
                    Date: {poInvoicesList[0].invoice_date} | Pairs: <b>{poInvoicesList[0].pairs_count || "—"}</b> | Total: <span className="font-mono font-bold">{inr(poInvoicesList[0].grand_total)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={`${API}/invoices/${poInvoicesList[0].id}/file?token=${localStorage.getItem('token') || ''}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 text-xs font-bold text-white bg-[#C27842] hover:bg-[#a86535] rounded shadow-sm inline-flex items-center gap-1.5"
                  >
                    <FileDown className="w-3.5 h-3.5" /> Download Invoice PDF
                  </a>
                  <button
                    type="button"
                    onClick={() => {
                      setInvoiceModalOpen(false);
                      navigate("/invoices");
                    }}
                    className="px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded inline-flex items-center gap-1"
                  >
                    View in Invoices <ExternalLink className="w-3 h-3" />
                  </button>
                </div>
              </div>
            )}

            {/* Header info */}
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div>
                  <span className="text-slate-500">Client: </span>
                  <span className="font-semibold text-slate-800">{selectedPoForInvoices?.client_name}</span>
                </div>
                <div>
                  <span className="text-slate-500">PO Total: </span>
                  <span className="font-mono font-semibold text-slate-800">{inr(selectedPoForInvoices?.grand_total)}</span>
                </div>
                <div>
                  <span className="text-slate-500">Dispatched: </span>
                  <span className="font-semibold text-[#C27842]">
                    {poDocumentsData?.total_dispatched_pairs ?? 0} / {poDocumentsData?.total_po_quantity ?? selectedPoForInvoices?.total_quantity ?? 0} pairs
                  </span>
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-slate-200 gap-4 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setDocActiveTab("all")}
                className={`pb-2 transition-colors border-b-2 ${
                  docActiveTab === "all"
                    ? "border-[#C27842] text-[#C27842]"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                All Documents ({poInvoicesList.length + (poDocumentsData?.dispatch_records || []).length})
              </button>
              <button
                type="button"
                onClick={() => setDocActiveTab("invoices")}
                className={`pb-2 transition-colors border-b-2 ${
                  docActiveTab === "invoices"
                    ? "border-[#C27842] text-[#C27842]"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Invoices ({poInvoicesList.length})
              </button>
              <button
                type="button"
                onClick={() => setDocActiveTab("dispatches")}
                className={`pb-2 transition-colors border-b-2 ${
                  docActiveTab === "dispatches"
                    ? "border-[#C27842] text-[#C27842]"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Packing Lists ({(poDocumentsData?.dispatch_records || []).length})
              </button>
            </div>

            {loadingInvoices ? (
              <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-2">
                <Loader2 className="w-6 h-6 animate-spin text-[#C27842]" />
                <span className="text-xs">Loading production documents...</span>
              </div>
            ) : poInvoicesList.length === 0 && (poDocumentsData?.dispatch_records || []).length === 0 ? (
              <div className="py-8 px-4 text-center bg-slate-50 rounded-lg border border-dashed border-slate-200">
                <ReceiptIndianRupee className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm font-medium text-slate-700">No Invoices or Packing Lists Produced Yet</p>
                <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                  Invoices, packing lists, and carton labels are produced automatically upon completing and dispatching production jobs in the Kanban board.
                </p>
                <div className="mt-4 pt-3 border-t border-slate-200 flex flex-wrap items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setInvoiceModalOpen(false);
                      navigate("/production");
                    }}
                    className="text-xs font-bold text-[#C27842] hover:underline inline-flex items-center gap-1"
                  >
                    Go to Kanban Production <ArrowRight className="w-3 h-3" />
                  </button>
                  <span className="text-slate-300">|</span>
                  <a
                    href={`${API}/pos/${selectedPoForInvoices?.id}/invoice.pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-slate-500 hover:text-[#C27842] underline"
                  >
                    Generate draft PO invoice
                  </a>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Invoices */}
                {(docActiveTab === "all" || docActiveTab === "invoices") && (
                  <div>
                    <div className="text-[11px] uppercase font-bold text-slate-600 tracking-wider mb-2 flex items-center justify-between">
                      <span>Invoices Produced ({poInvoicesList.length})</span>
                      <button
                        type="button"
                        onClick={() => {
                          setInvoiceModalOpen(false);
                          navigate("/invoices");
                        }}
                        className="text-[11px] text-slate-500 hover:text-[#C27842] inline-flex items-center gap-1"
                      >
                        Invoices Ledger <ExternalLink className="w-2.5 h-2.5" />
                      </button>
                    </div>
                    {poInvoicesList.length === 0 ? (
                      <div className="py-4 text-center text-xs text-slate-400 bg-slate-50 rounded border border-dashed border-slate-200">
                        No invoices produced yet.
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-white">
                        {poInvoicesList.map((inv) => (
                          <div key={inv.id} className="p-3.5 hover:bg-slate-50 flex items-center justify-between gap-4">
                            <div>
                              <div className="font-mono font-bold text-slate-900 text-sm flex items-center gap-2">
                                <span>{inv.invoice_no}</span>
                                {inv.status && <Badge tone="success">{inv.status.toUpperCase()}</Badge>}
                              </div>
                              <div className="text-xs text-slate-500 mt-1">
                                Date: {inv.invoice_date} | Pairs: <span className="font-semibold text-slate-700">{inv.pairs_count || "—"}</span> | Amount: <span className="font-mono font-semibold text-slate-700">{inr(inv.grand_total)}</span>
                              </div>
                              {inv.job_ids && inv.job_ids.length > 0 && (
                                <div className="text-[11px] text-slate-400 mt-0.5">
                                  Production Jobs: {inv.job_ids.length} job(s)
                                </div>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              <a
                                href={`${API}/invoices/${inv.id}/file?token=${localStorage.getItem('token') || ''}`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-3 py-1.5 text-xs font-medium text-white bg-[#C27842] hover:bg-[#a86535] rounded-md inline-flex items-center gap-1.5 shadow-sm"
                              >
                                <FileDown className="w-3.5 h-3.5" /> Invoice PDF
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Packing Lists & Dispatches */}
                {(docActiveTab === "all" || docActiveTab === "dispatches") && (
                  <div>
                    <div className="text-[11px] uppercase font-bold text-slate-600 tracking-wider mb-2">
                      Packing Lists &amp; Dispatches ({(poDocumentsData?.dispatch_records || []).length})
                    </div>
                    {(poDocumentsData?.dispatch_records || []).length === 0 ? (
                      <div className="py-4 text-center text-xs text-slate-400 bg-slate-50 rounded border border-dashed border-slate-200">
                        No dispatch packing lists produced yet.
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-white">
                        {(poDocumentsData?.dispatch_records || []).map((dr) => (
                          <div key={dr.id} className="p-3.5 hover:bg-slate-50 flex items-center justify-between gap-4">
                            <div>
                              <div className="font-mono font-bold text-slate-900 text-sm">
                                Dispatch: {dr.invoice_no || dr.id}
                              </div>
                              <div className="text-xs text-slate-500 mt-1">
                                Date: {dr.dispatched_at ? new Date(dr.dispatched_at).toLocaleDateString() : "—"} | Cartons: <span className="font-semibold text-slate-700">{dr.carton_count || 0}</span> | Pairs: <span className="font-semibold text-slate-700">{dr.pairs || dr.total_quantity || "—"}</span>
                              </div>
                              {(dr.transporter || dr.vehicle) && (
                                <div className="text-[11px] text-slate-400 mt-0.5">
                                  Transport: {dr.transporter || "—"} {dr.vehicle ? `(${dr.vehicle})` : ""}
                                </div>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <a
                                href={`${API}/dispatch-records/${dr.id}/packing-list`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2.5 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded inline-flex items-center gap-1"
                                title="Download Packing List XLSX"
                              >
                                <Package className="w-3.5 h-3.5 text-[#16A34A]" /> Packing List (XLSX)
                              </a>
                              <a
                                href={`${API}/dispatch-records/${dr.id}/carton-labels`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2.5 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded inline-flex items-center gap-1"
                                title="Download Carton Labels PDF"
                              >
                                <FileText className="w-3.5 h-3.5 text-[#F97316]" /> Carton Labels
                              </a>
                              <a
                                href={`${API}/dispatch-records/${dr.id}/invoice`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2.5 py-1.5 text-xs font-medium text-white bg-[#C27842] hover:bg-[#a86535] rounded inline-flex items-center gap-1 shadow-sm"
                                title="Download Dispatch Invoice PDF"
                              >
                                <FileDown className="w-3.5 h-3.5" /> Invoice PDF
                              </a>
                              <a
                                href={`${API}/dispatch-records/${dr.id}/ewaybill`}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2.5 py-1.5 text-xs font-medium text-sky-700 bg-sky-50 hover:bg-sky-100 border border-sky-300 rounded inline-flex items-center gap-1 shadow-sm"
                                title="Download E-Way Bill JSON"
                                data-testid={`dr-detail-ewaybill-btn-${dr.id}`}
                              >
                                <FileText className="w-3.5 h-3.5 text-sky-600" /> E-Way Bill
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="pt-4 border-t border-slate-200 flex justify-end items-center">
              <BtnSecondary onClick={() => setInvoiceModalOpen(false)}>
                Close
              </BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}

      {/* ── ALLOCATE KARIGAR MODAL DIALOG IN PO TAB ── */}
      {assignModal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" data-testid="po-assign-karigar-modal">
          <div className="bg-white rounded-xl border border-slate-200 shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-5 py-4 bg-slate-900 text-white flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[#C27842] font-bold">Planning Stage · Allocate Karigar</div>
                <div className="font-bold text-base text-white">{assignModal.roleLabel}</div>
              </div>
              <button
                onClick={() => setAssignModal(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg"
              >
                ✕
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="text-xs font-bold text-slate-700 block mb-1.5">
                  Select Worker / Karigar <span className="text-red-500">*</span>
                </label>
                <select
                  value={assignModal.workerId || ""}
                  onChange={(e) => {
                    const wid = e.target.value;
                    const wObj = (planningData?.workers || []).find((w) => String(w.id) === String(wid));
                    setAssignModal({
                      ...assignModal,
                      workerId: wid,
                      rate: wObj?.rate_per_pair != null ? wObj.rate_per_pair : assignModal.rate,
                    });
                  }}
                  className="w-full text-xs border border-slate-300 rounded-lg p-2.5 bg-white focus:ring-2 focus:ring-[#C27842] focus:border-[#C27842] outline-none"
                  data-testid="select-karigar-dropdown"
                >
                  <option value="">-- Choose Karigar from Master List --</option>
                  {(planningData?.workers || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} {w.skill ? `(${w.skill})` : ""} {w.rate_per_pair ? `— ₹${w.rate_per_pair}/pr` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-700 block mb-1.5">
                  Karigar Wage Rate / Pair (₹) <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={assignModal.rate}
                  onChange={(e) => setAssignModal({ ...assignModal, rate: e.target.value })}
                  placeholder="e.g. 15.00"
                  className="w-full text-xs font-mono font-bold border border-slate-300 rounded-lg p-2.5 focus:ring-2 focus:ring-[#C27842] focus:border-[#C27842] outline-none"
                  data-testid="input-karigar-rate"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  This piece rate directly determines the actual labour budget to complete this PO.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                {assignModal.currentWorkerId && (
                  <button
                    type="button"
                    disabled={allocatingKarigar}
                    onClick={() => handleAllocateWorker(assignModal.role, null, null)}
                    className="px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-lg mr-auto border border-rose-200"
                    data-testid="unassign-karigar-btn"
                  >
                    Unassign
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setAssignModal(null)}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-lg border border-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={allocatingKarigar || !assignModal.workerId}
                  onClick={() => handleAllocateWorker(assignModal.role, assignModal.workerId, assignModal.rate)}
                  className="px-4 py-2 text-xs font-bold text-white bg-[#C27842] hover:bg-[#a86535] rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-50"
                  data-testid="save-allocated-karigar-btn"
                >
                  {allocatingKarigar ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  Confirm Allocation
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title}
        message={confirm?.message}
        onConfirm={confirm?.onConfirm}
        onCancel={() => setConfirm(null)}
      />
      <PackingListPreviewModal
        po={previewPo}
        isOpen={!!previewPo}
        onClose={() => setPreviewPo(null)}
      />
      <PoEanCodesModal
        po={selectedPoForEan}
        isOpen={poEanModalOpen}
        onClose={() => setPoEanModalOpen(false)}
        onUpdated={load}
      />

      {/* ── MULTI-PO & MULTI-STYLE PRODUCTION BUDGET PLANNING DRAWER ── */}
      {multiBudgetOpen && (
        <Drawer
          onClose={() => setMultiBudgetOpen(false)}
          title="Multi-PO Production Budget & Planning Alignment"
          width="w-full max-w-[96vw] xl:max-w-7xl 2xl:max-w-[1600px]"
        >
          <div className="p-4 sm:p-6 space-y-5 text-xs">
            {/* Header Banner */}
            <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white p-4 sm:p-5 rounded-xl border border-indigo-900/50 shadow-lg flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="p-2.5 rounded-xl bg-amber-500/20 border border-amber-500/40 text-amber-400 shrink-0">
                  <Calculator className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-[10px] uppercase font-bold tracking-widest text-amber-400">
                    Planning Stage · Multi-PO Manufacturing Budget
                  </div>
                  <h2 className="text-base font-bold text-white mt-0.5">
                    Production Budget Alignment ({multiBudgetSelectedPOs.length} POs Selected)
                  </h2>
                  <p className="text-slate-300 text-xs mt-1 max-w-2xl leading-relaxed">
                    Select multiple POs and pick any combination of styles to align manufacturing funds, evaluate BOM &amp; Karigar labor piece wages, and verify production budgets before scheduling batches.
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={async () => {
                    const distinctCodes = Array.from(new Set(multiBudgetCalculated.selectedLineRows.map(r => r.lineItem.style_code).filter(Boolean)));
                    await downloadCatalogueXlsx({
                      style_codes: distinctCodes,
                      brand: "ZECODE",
                      defaultFilename: `Aligned_Budget_Catalogue_${new Date().toISOString().slice(0, 10)}.xlsx`,
                    });
                  }}
                  disabled={multiBudgetCalculated.selectedCount === 0}
                  className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white rounded-lg font-bold text-xs uppercase tracking-wider inline-flex items-center gap-1.5 shadow-md transition-colors"
                  title="Download catalogue file with pictures for selected styles across POs"
                  data-testid="multi-budget-catalogue-download-btn"
                >
                  <FileSpreadsheet className="w-4 h-4" />
                  <span>Download Catalogue (.xlsx)</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const headers = ["PO #", "Client", "Style Code", "Description", "Color", "Size", "Qty", "Rate", "Revenue", "BOM Cost", "Labor Cost", "Packing Cost", "Total Cost", "Profit"];
                    const rows = multiBudgetCalculated.selectedLineRows.map(r => [
                      r.po.po_number,
                      r.po.client_name,
                      r.lineItem.style_code,
                      r.lineItem.description,
                      r.lineItem.color,
                      r.lineItem.size,
                      r.quantity,
                      r.unitPrice,
                      r.revenue,
                      r.bomCost,
                      r.laborCost,
                      r.packingCost,
                      r.totalCost,
                      r.profit,
                    ]);
                    downloadCsv(`Production_Budget_Breakdown_${new Date().toISOString().slice(0, 10)}.csv`, headers, rows);
                  }}
                  disabled={multiBudgetCalculated.selectedCount === 0}
                  className="px-3 py-2 bg-white/10 hover:bg-white/20 text-white border border-white/20 rounded-lg font-bold text-xs uppercase tracking-wider inline-flex items-center gap-1.5 transition-colors"
                  title="Export itemized budget spreadsheet"
                >
                  <FileDown className="w-4 h-4" />
                  <span>CSV Breakdown</span>
                </button>
                <button
                  type="button"
                  onClick={handleAlignMultiBudget}
                  disabled={aligningBudget || multiBudgetCalculated.selectedCount === 0}
                  className="px-4 py-2 bg-[#C27842] hover:bg-[#A65D24] disabled:opacity-40 text-white rounded-lg font-bold text-xs uppercase tracking-wider inline-flex items-center gap-2 shadow-lg transition-colors"
                  data-testid="confirm-align-budget-btn"
                >
                  {aligningBudget ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  <span>{aligningBudget ? "Aligning..." : "Align Budget Snapshot"}</span>
                </button>
              </div>
            </div>

            {/* Alignment Success Alert */}
            {alignmentSuccess && (
              <div className="p-3.5 bg-emerald-50 border-2 border-emerald-300 rounded-xl flex items-center justify-between gap-3 text-emerald-900 shadow-xs" data-testid="budget-alignment-success-alert">
                <div className="flex items-center gap-2.5">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                  <div>
                    <div className="font-bold text-xs">Production Budget Successfully Aligned &amp; Recorded!</div>
                    <div className="text-[11px] text-emerald-700 mt-0.5">
                      Snapshot ID: <code className="font-mono font-bold">{alignmentSuccess.id}</code> · Recorded at {alignmentSuccess.timestamp} for {alignmentSuccess.totalQty} pairs ({inr(alignmentSuccess.totalBudget)} budget).
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setAlignmentSuccess(null)}
                  className="p-1 rounded text-emerald-700 hover:bg-emerald-100"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Step 1: PO Multi-Select Chips Bar */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="font-bold uppercase tracking-wider text-slate-700 text-[11px] flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-[#C27842]" />
                  <span>Step 1: Choose Purchase Orders to Combine ({multiBudgetSelectedPOs.length} of {pos.length} selected)</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const allIds = pos.map(p => p.id);
                      setMultiBudgetPoIds(allIds);
                      const k = new Set();
                      pos.forEach(p => (p.line_items || []).forEach((_, idx) => k.add(`${p.id}_${idx}`)));
                      setSelectedMultiStyleKeys(k);
                    }}
                    className="text-xs font-bold text-[#C27842] hover:underline"
                  >
                    Select All POs ({pos.length})
                  </button>
                  <span className="text-slate-300">|</span>
                  <button
                    type="button"
                    onClick={() => {
                      setMultiBudgetPoIds([]);
                      setSelectedMultiStyleKeys(new Set());
                    }}
                    className="text-xs font-semibold text-slate-500 hover:text-slate-800"
                  >
                    Clear All
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {pos.map((p) => {
                  const isChecked = multiBudgetPoIds.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => toggleMultiBudgetPo(p.id)}
                      className={`px-3 py-1.5 rounded-lg border text-xs font-medium inline-flex items-center gap-2 transition-all ${
                        isChecked
                          ? "bg-amber-100 text-amber-900 border-amber-400 font-bold shadow-xs"
                          : "bg-white text-slate-600 border-slate-300 hover:border-slate-400"
                      }`}
                      data-testid={`multi-budget-po-chip-${p.po_number}`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        className="w-3.5 h-3.5 text-[#C27842] rounded border-slate-300 cursor-pointer pointer-events-none"
                      />
                      <span>{p.po_number}</span>
                      <span className="text-[10px] text-slate-500 font-normal">
                        ({p.client_name} · {p.total_quantity || 0} prs)
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Aggregated Budget KPI Summary Card */}
            <div className="rounded-xl border-2 border-amber-500/40 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white p-4 sm:p-5 shadow-xl space-y-4" data-testid="multi-po-budget-kpi-card">
              <div className="flex items-center justify-between pb-3 border-b border-slate-700 flex-wrap gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-[#C27842]/20 border border-[#C27842]/50 text-[#C27842]">
                    <Calculator className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-white">
                      Combined Production Budget (Cost to Complete)
                    </h4>
                    <p className="text-[11px] text-slate-400">
                      Calculated for {multiBudgetCalculated.totalQty} pairs across {multiBudgetCalculated.selectedCount} selected styles
                    </p>
                  </div>
                </div>
                <div>
                  {multiBudgetCalculated.isLaborEstimated ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40">
                      <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                      Estimated Style Labor (Some Karigars Not Yet Allocated)
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-bold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      Actual Allocated Karigar Wages
                    </span>
                  )}
                </div>
              </div>

              {/* 4 KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total BOM Cost
                  </div>
                  <div className="text-lg font-black font-mono text-white mt-1">
                    {inr(multiBudgetCalculated.totalBom)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">Raw materials &amp; soles</div>
                </div>

                <div className="bg-slate-800/80 border border-slate-700/80 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total Labour Cost
                  </div>
                  <div className="text-lg font-black font-mono text-amber-400 mt-1">
                    {inr(multiBudgetCalculated.totalLabor)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5 flex items-center justify-between">
                    <span>Karigar piece wages</span>
                    <span className={`text-[9px] font-bold ${multiBudgetCalculated.isLaborEstimated ? "text-amber-400" : "text-emerald-400"}`}>
                      {multiBudgetCalculated.isLaborEstimated ? "Estimated" : "Allocated"}
                    </span>
                  </div>
                </div>

                <div className="bg-slate-800/80 border border-slate-700/80 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total Packing Cost
                  </div>
                  <div className="text-lg font-black font-mono text-cyan-400 mt-1">
                    {inr(multiBudgetCalculated.totalPacking)}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">Boxes, cartons &amp; labels</div>
                </div>

                <div className="bg-[#C27842]/20 border border-[#C27842]/60 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-bold text-amber-200 tracking-wider">
                    Total Production Budget
                  </div>
                  <div className="text-lg font-black font-mono text-[#F59E0B] mt-1">
                    {inr(multiBudgetCalculated.totalCost)}
                  </div>
                  <div className="text-[10px] text-amber-200/80 mt-0.5 font-semibold">Cost to complete</div>
                </div>
              </div>

              {/* Commercial Comparison */}
              <div className="pt-3 border-t border-slate-700/80 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex flex-wrap items-center gap-3">
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 font-semibold block">Combined Revenue</span>
                    <span className="font-mono font-bold text-white text-base">{inr(multiBudgetCalculated.totalRevenue)}</span>
                  </div>
                  <span className="text-slate-500 font-mono text-lg hidden sm:inline">−</span>
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 font-semibold block">Total Budget (Cost)</span>
                    <span className="font-mono font-bold text-amber-400 text-base">{inr(multiBudgetCalculated.totalCost)}</span>
                  </div>
                  <span className="text-slate-500 font-mono text-lg hidden sm:inline">=</span>
                  <div>
                    <span className="text-[10px] uppercase text-slate-400 font-semibold block">Projected Margin</span>
                    <span className={`font-mono font-bold text-base ${multiBudgetCalculated.profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {multiBudgetCalculated.profit >= 0 ? "+" : ""}{inr(multiBudgetCalculated.profit)} ({multiBudgetCalculated.profitPct}%)
                    </span>
                  </div>
                </div>
                {Number(multiBudgetCalculated.totalOutside || 0) > 0 && (
                  <div className="text-xs text-purple-300 font-mono">
                    Outside Labour: <b>{inr(multiBudgetCalculated.totalOutside)}</b>
                  </div>
                )}
              </div>
            </div>

            {/* Step 2: PO Line Items Selection Table */}
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="font-bold uppercase tracking-wider text-slate-700 text-[11px] flex items-center gap-1.5">
                  <CheckSquare className="w-4 h-4 text-emerald-600" />
                  <span>Step 2: Pick Styles from each PO for Budget Alignment ({multiBudgetCalculated.selectedCount} styles selected)</span>
                </div>
                <div className="text-slate-500 text-xs">
                  Tip: Check/uncheck individual styles to tailor the exact production run.
                </div>
              </div>

              {multiBudgetSelectedPOs.length === 0 ? (
                <div className="p-8 text-center bg-slate-50 rounded-xl border border-dashed border-slate-300 text-slate-500">
                  No Purchase Orders selected above. Click any PO chip in Step 1 to load styles.
                </div>
              ) : (
                multiBudgetSelectedPOs.map((p) => {
                  const poStylesCount = (p.line_items || []).length;
                  const poSelectedCount = (p.line_items || []).filter((_, idx) => selectedMultiStyleKeys.has(`${p.id}_${idx}`)).length;
                  return (
                    <div key={p.id} className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-xs">
                      {/* PO Header Bar */}
                      <div className="bg-slate-50 border-b border-slate-200 px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <span className="font-mono font-bold text-sm text-slate-900">{p.po_number}</span>
                          <span className="text-slate-600 font-medium">{p.client_name}</span>
                          <span className="text-slate-400">·</span>
                          <span className="text-slate-500 text-[11px]">{p.po_date}</span>
                          <span className="text-[10px] bg-slate-200 text-slate-700 font-bold px-2 py-0.5 rounded-full">
                            {p.total_quantity || 0} pairs total
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-semibold text-slate-600">
                            {poSelectedCount} of {poStylesCount} styles selected
                          </span>
                          <button
                            type="button"
                            onClick={() => selectAllStylesForPo(p.id)}
                            className="px-2 py-0.5 bg-white border border-slate-300 hover:bg-slate-100 rounded text-[11px] font-bold text-[#C27842]"
                          >
                            Select All
                          </button>
                          <button
                            type="button"
                            onClick={() => deselectAllStylesForPo(p.id)}
                            className="px-2 py-0.5 bg-white border border-slate-300 hover:bg-slate-100 rounded text-[11px] text-slate-600"
                          >
                            Deselect All
                          </button>
                        </div>
                      </div>

                      {/* Styles Table */}
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead className="bg-slate-100/70 border-b border-slate-200 text-slate-600 font-bold text-[11px]">
                            <tr>
                              <th className="px-3 py-2 text-center w-10">Select</th>
                              <th className="px-2 py-2 text-center w-12">Photo</th>
                              <th className="px-3 py-2">Style / Desc</th>
                              <th className="px-2 py-2 text-center">Color / Sz</th>
                              <th className="px-2.5 py-2 text-right">Qty</th>
                              <th className="px-2.5 py-2 text-right">PO Rate</th>
                              <th className="px-3 py-2">Cost Breakdown / Pair</th>
                              <th className="px-2.5 py-2 text-right">Unit Cost</th>
                              <th className="px-2.5 py-2 text-right">Line Budget</th>
                              <th className="px-2.5 py-2 text-right">Line Margin</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {(p.line_items || []).map((li, idx) => {
                              const key = `${p.id}_${idx}`;
                              const isChecked = selectedMultiStyleKeys.has(key);
                              const prof = li.profitability || {};
                              const qty = Number(li.quantity || 0);
                              const rate = Number(li.unit_price || 0);
                              const lineRev = qty * rate;
                              const bom = Number(prof.bom_cost || 0);
                              const labor = Number(prof.labor_cost || 0);
                              const packing = Number(prof.packing_cost || 0);
                              const outside = Number(prof.outside_cost || 0);
                              const uCost = bom + labor + packing + outside;
                              const totCost = uCost * qty;
                              const margin = lineRev - totCost;

                              return (
                                <tr
                                  key={idx}
                                  className={`hover:bg-slate-50 transition-colors ${
                                    !isChecked ? "opacity-35 bg-slate-50/50" : ""
                                  }`}
                                >
                                  <td className="px-3 py-2 text-center">
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={() => toggleMultiBudgetStyleKey(key)}
                                      className="w-4 h-4 text-[#C27842] rounded border-slate-300 cursor-pointer"
                                      title="Include/exclude this style from budget"
                                      data-testid={`multi-style-checkbox-${p.po_number}-${idx}`}
                                    />
                                  </td>
                                  <td className="px-2 py-1.5 text-center">
                                    <ImageThumb
                                      image={getStyleImage(li.style_code, li)}
                                      size={40}
                                      alt={li.style_code}
                                      clickable
                                      className="rounded border shadow-xs inline-block"
                                    />
                                  </td>
                                  <td className="px-3 py-2">
                                    <div className="font-mono font-bold text-slate-900">{li.style_code}</div>
                                    <div className="text-[11px] text-slate-500 truncate max-w-xs">{li.description || "—"}</div>
                                  </td>
                                  <td className="px-2 py-2 text-center text-slate-600 font-mono">
                                    {li.color || "—"} {li.size ? `· ${li.size}` : ""}
                                  </td>
                                  <td className="px-2.5 py-2 text-right font-mono font-bold">{qty}</td>
                                  <td className="px-2.5 py-2 text-right font-mono">{inr(rate)}</td>
                                  <td className="px-3 py-2 text-[11px]">
                                    <div className="flex flex-wrap gap-x-2 text-slate-600">
                                      <span>BOM: <b>{inr(bom)}</b></span>
                                      <span>Pack: <b>{inr(packing)}</b></span>
                                      {outside > 0 && <span>Out: <b className="text-purple-700">{inr(outside)}</b></span>}
                                    </div>
                                    <div className="flex items-center gap-1.5 mt-0.5">
                                      <span>Labor: <b className="font-mono">{inr(labor)}</b></span>
                                      <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                                        prof.is_estimated ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-900"
                                      }`}>
                                        {prof.is_estimated ? "Estimated" : "Allocated"}
                                      </span>
                                    </div>
                                  </td>
                                  <td className="px-2.5 py-2 text-right font-mono font-semibold text-slate-800">{inr(uCost)}</td>
                                  <td className="px-2.5 py-2 text-right font-mono font-bold text-amber-700">{inr(totCost)}</td>
                                  <td className="px-2.5 py-2 text-right font-mono font-bold">
                                    <span className={margin >= 0 ? "text-emerald-700" : "text-rose-600"}>
                                      {margin >= 0 ? "+" : ""}{inr(margin)}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </Drawer>
      )}

    </div>
  );
}

function Total({ label, value, big }) {
  return (
    <div
      className={`flex justify-between items-baseline ${big ? "py-1" : "py-0.5"}`}
    >
      <span className="text-xs uppercase tracking-wider text-slate-400">
        {label}
      </span>
      <span
        className={`font-mono ${big ? "text-xl font-bold text-[#C27842]" : "text-sm"}`}
      >
        {value}
      </span>
    </div>
  );
}
function Field({ label, value }) {
  return (
    <div className="border-b border-dashed border-slate-200 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
        {label}
      </div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
}
