import React, { useState, useEffect } from "react";
import { http } from "../lib/api";
import { BtnPrimary, BtnSecondary, Badge, ConfirmDialog } from "./ui-kit";
import { Drawer } from "../pages/Materials";
import {
  Barcode,
  Upload,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  FileSpreadsheet,
  Loader2,
  RefreshCw,
  Info,
  Check,
  X,
} from "lucide-react";

export default function PoEanCodesModal({ po, isOpen, onClose, onUpdated }) {
  const [activeTab, setActiveTab] = useState("current"); // "current" | "upload"
  const [loading, setLoading] = useState(false);
  const [existingEans, setExistingEans] = useState([]);
  
  // Format configs
  const [formatConfigs, setFormatConfigs] = useState([]);
  const [selectedFormatId, setSelectedFormatId] = useState("");
  
  // Upload & Preview state
  const [uploadFile, setUploadFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);

  // Load existing EANs and formats when opened
  useEffect(() => {
    if (isOpen && po?.id) {
      loadExistingEans();
      loadFormatConfigs();
      setPreviewData(null);
      setUploadFile(null);
      setImportResult(null);
      setErrorMsg("");
      setActiveTab("current");
    }
  }, [isOpen, po?.id]);

  const loadExistingEans = async () => {
    if (!po?.id) return;
    setLoading(true);
    try {
      const res = await http.get(`/pos/${po.id}/ean-codes`);
      setExistingEans(res.data?.items || []);
    } catch (err) {
      console.error("Failed to load PO EAN codes:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadFormatConfigs = async () => {
    try {
      const res = await http.get("/po-ean-formats?active=true");
      const list = res.data || [];
      setFormatConfigs(list);
      
      // Try to auto-select matching client format
      if (po?.client_name) {
        const clientLower = po.client_name.toLowerCase();
        const matched = list.find(
          (c) => c.client_name && clientLower.includes(c.client_name.toLowerCase())
        );
        if (matched) {
          setSelectedFormatId(matched.id);
          return;
        }
      }
      if (list.length > 0) {
        setSelectedFormatId(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load PO EAN format configs:", err);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadFile(file);
    setErrorMsg("");
    setImportResult(null);
    await triggerPreview(file, selectedFormatId);
  };

  const handleFormatChange = async (e) => {
    const fmtId = e.target.value;
    setSelectedFormatId(fmtId);
    if (uploadFile) {
      await triggerPreview(uploadFile, fmtId);
    }
  };

  const triggerPreview = async (file, fmtId) => {
    if (!file || !po?.id) return;
    setPreviewLoading(true);
    setErrorMsg("");
    try {
      const selectedCfg = formatConfigs.find((c) => c.id === fmtId);
      const formData = new FormData();
      formData.append("file", file);
      if (selectedCfg) {
        formData.append("config_json", JSON.stringify(selectedCfg));
      }
      const res = await http.post(`/pos/${po.id}/ean-codes/preview-upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreviewData(res.data);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || err.message || "Failed to preview barcode file");
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleImport = async () => {
    setImporting(true);
    setErrorMsg("");
    try {
      let res;
      if (uploadFile) {
        const selectedCfg = formatConfigs.find((c) => c.id === selectedFormatId);
        const formData = new FormData();
        formData.append("file", uploadFile);
        formData.append("overwrite_existing", String(overwrite));
        if (selectedCfg) {
          formData.append("config_json", JSON.stringify(selectedCfg));
        } else if (selectedFormatId) {
          formData.append("config_id", selectedFormatId);
        }
        res = await http.post(`/pos/${po.id}/ean-codes/import`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } else if (previewData?.extracted_items && previewData.extracted_items.length > 0) {
        const payload = {
          po_id: po.id,
          po_number: po.po_number,
          overwrite_existing: overwrite,
          items: previewData.extracted_items.map((item) => ({
            style_code: item.style_code,
            color: item.color,
            size: String(item.size),
            ean_code: item.ean_code,
            po_number: item.po_number || po.po_number,
          })),
        };
        res = await http.post(`/pos/${po.id}/ean-codes/import`, payload);
      } else {
        return;
      }
      setImportResult(res.data);
      await loadExistingEans();
      if (onUpdated) onUpdated();
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || err.message || "Failed to import barcodes");
    } finally {
      setImporting(false);
    }
  };

  const handleClearAll = async () => {
    if (!po?.id) return;
    try {
      await http.delete(`/pos/${po.id}/ean-codes`);
      setConfirmClear(false);
      await loadExistingEans();
      if (onUpdated) onUpdated();
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || err.message || "Failed to delete EAN codes");
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <Drawer
        title={
          <div className="flex items-center gap-2">
            <Barcode className="w-5 h-5 text-[#0D9488]" />
            <span>PO Barcodes & EAN Import — {po?.po_number}</span>
          </div>
        }
        open={isOpen}
        onClose={onClose}
      >
        <div className="space-y-4 p-2 text-slate-800" data-testid="po-ean-modal">
          {/* Header summary banner */}
          <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-wrap items-center justify-between gap-3 text-xs">
            <div>
              <span className="text-slate-500">Client:</span>{" "}
              <span className="font-bold text-slate-800">{po?.client_name || "—"}</span>
            </div>
            <div>
              <span className="text-slate-500">PO Date:</span>{" "}
              <span className="font-mono font-medium">{po?.po_date || "—"}</span>
            </div>
            <div>
              <span className="text-slate-500">PO Lines:</span>{" "}
              <span className="font-mono font-bold text-slate-800">
                {po?.line_items?.length || 0}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Mapped Barcodes:</span>{" "}
              <span className="font-mono font-bold text-[#0D9488]">
                {existingEans.length}
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex border-b border-slate-200">
            <button
              onClick={() => setActiveTab("current")}
              data-testid="tab-current-eans"
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                activeTab === "current"
                  ? "border-[#0D9488] text-[#0D9488]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Barcode className="w-3.5 h-3.5" />
              Stored Barcodes ({existingEans.length})
            </button>
            <button
              onClick={() => setActiveTab("upload")}
              data-testid="tab-upload-eans"
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px ${
                activeTab === "upload"
                  ? "border-[#0D9488] text-[#0D9488]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              Upload & Import Sheet
            </button>
          </div>

          {errorMsg && (
            <div
              className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded flex items-start gap-2"
              data-testid="ean-error-banner"
            >
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>{errorMsg}</div>
            </div>
          )}

          {/* TAB 1: CURRENT STORED EANS */}
          {activeTab === "current" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs text-slate-500">
                  {existingEans.length === 0
                    ? "No barcodes imported yet for this PO."
                    : `${existingEans.length} EAN barcode(s) saved for packing lists and carton labels.`}
                </div>
                {existingEans.length > 0 && (
                  <button
                    onClick={() => setConfirmClear(true)}
                    className="text-xs text-red-600 hover:text-red-800 flex items-center gap-1 font-semibold"
                    data-testid="clear-po-eans-btn"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Clear All
                  </button>
                )}
              </div>

              {loading ? (
                <div className="py-12 text-center text-slate-400">
                  <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0D9488]" />
                  Loading barcodes...
                </div>
              ) : existingEans.length === 0 ? (
                <div className="border border-dashed border-slate-200 rounded-lg p-8 text-center text-slate-400 space-y-3">
                  <Barcode className="w-10 h-10 mx-auto text-slate-300 stroke-1" />
                  <p className="text-xs">
                    Client barcode sheet has not been imported for PO {po?.po_number}.
                  </p>
                  <BtnPrimary
                    onClick={() => setActiveTab("upload")}
                    data-testid="goto-upload-btn"
                    className="text-xs"
                  >
                    <Upload className="w-3.5 h-3.5 mr-1 inline" /> Import Barcodes Now
                  </BtnPrimary>
                </div>
              ) : (
                <div className="border border-slate-200 rounded-lg overflow-hidden max-h-[480px] overflow-y-auto">
                  <table className="w-full text-xs" data-testid="po-eans-table">
                    <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                      <tr className="text-left font-bold text-slate-600 uppercase tracking-wider text-[10px]">
                        <th className="px-3 py-2">Style Code</th>
                        <th className="px-3 py-2">Color</th>
                        <th className="px-3 py-2">Size</th>
                        <th className="px-3 py-2">EAN / Barcode</th>
                        <th className="px-3 py-2">Imported At</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {existingEans.map((ean, idx) => (
                        <tr key={ean.id || idx} className="hover:bg-slate-50">
                          <td className="px-3 py-2 font-bold text-slate-900">
                            {ean.style_code}
                          </td>
                          <td className="px-3 py-2 text-slate-600">
                            {ean.color || "—"}
                          </td>
                          <td className="px-3 py-2 font-bold text-[#0D9488]">
                            {ean.size}
                          </td>
                          <td className="px-3 py-2 font-bold text-slate-800">
                            <span className="bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                              {ean.ean_code}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-slate-400 text-[11px]">
                            {ean.imported_at ? ean.imported_at.slice(0, 10) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: UPLOAD & IMPORT */}
          {activeTab === "upload" && (
            <div className="space-y-4">
              {/* Configuration selector */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200">
                <div>
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Barcode Format Template
                  </label>
                  <select
                    value={selectedFormatId}
                    onChange={handleFormatChange}
                    className="w-full text-xs border border-slate-300 rounded px-2.5 py-1.5 bg-white font-medium focus:ring-1 focus:ring-[#0D9488] focus:border-[#0D9488]"
                    data-testid="select-po-ean-format"
                  >
                    {formatConfigs.map((fmt) => (
                      <option key={fmt.id} value={fmt.id}>
                        {fmt.name} {fmt.client_name ? `(${fmt.client_name})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Target Purchase Order
                  </label>
                  <div className="text-xs font-mono font-bold py-1.5 px-2 bg-white border border-slate-200 rounded text-slate-700">
                    {po?.po_number} ({po?.client_name || "Client"})
                  </div>
                </div>
              </div>

              {/* Upload Dropzone */}
              <div className="border-2 border-dashed border-[#0D9488]/40 hover:border-[#0D9488] bg-teal-50/20 rounded-lg p-6 text-center transition-colors">
                <FileSpreadsheet className="w-8 h-8 mx-auto text-[#0D9488] mb-2" />
                <div className="text-xs font-bold text-slate-700">
                  {uploadFile ? uploadFile.name : "Select Client Barcode File"}
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  Accepts Excel (.xlsx, .xls) and CSV barcode mapping files
                </div>
                <label className="mt-3 inline-block cursor-pointer">
                  <span className="px-4 py-2 bg-[#0D9488] hover:bg-[#0f766e] text-white text-xs font-bold rounded shadow-sm inline-flex items-center gap-1.5">
                    <Upload className="w-3.5 h-3.5" />
                    {uploadFile ? "Choose Different File" : "Browse Barcode File"}
                  </span>
                  <input
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    className="hidden"
                    onChange={handleFileChange}
                    data-testid="po-ean-file-input"
                  />
                </label>
              </div>

              {previewLoading && (
                <div className="py-8 text-center text-slate-400 text-xs">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-[#0D9488]" />
                  Parsing sheet and matching PO style codes...
                </div>
              )}

              {/* Preview extracted items */}
              {previewData && !previewLoading && (
                <div className="space-y-3" data-testid="po-ean-preview-container">
                  {/* Summary Metric Counters */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="bg-slate-50 border border-slate-200 p-2.5 rounded text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">
                        Total Extracted
                      </div>
                      <div className="font-mono text-base font-bold text-slate-800" data-testid="metric-total-rows">
                        {previewData.extracted_items?.length || 0}
                      </div>
                    </div>
                    <div className="bg-emerald-50 border border-emerald-200 p-2.5 rounded text-center">
                      <div className="text-[10px] uppercase font-bold text-emerald-700">
                        PO Line Matches
                      </div>
                      <div className="font-mono text-base font-bold text-emerald-800" data-testid="metric-matched-rows">
                        {previewData.po_matched_count || 0}
                      </div>
                    </div>
                    <div className="bg-amber-50 border border-amber-200 p-2.5 rounded text-center">
                      <div className="text-[10px] uppercase font-bold text-amber-700">
                        Duplicates
                      </div>
                      <div className="font-mono text-base font-bold text-amber-800" data-testid="metric-duplicate-rows">
                        {previewData.duplicate_keys?.length || 0}
                      </div>
                    </div>
                    <div className="bg-blue-50 border border-blue-200 p-2.5 rounded text-center">
                      <div className="text-[10px] uppercase font-bold text-blue-700">
                        Existing in DB
                      </div>
                      <div className="font-mono text-base font-bold text-blue-800" data-testid="metric-existing-rows">
                        {previewData.extracted_items?.filter((i) => i.exists_in_db).length || 0}
                      </div>
                    </div>
                  </div>

                  {/* Duplicate warning alert if duplicate keys exist */}
                  {previewData.duplicate_keys && previewData.duplicate_keys.length > 0 && (
                    <div className="bg-amber-50 border border-amber-300 p-3 rounded text-xs text-amber-800 space-y-1">
                      <div className="font-bold flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4 text-amber-600" />
                        Warning: {previewData.duplicate_keys.length} duplicate SKU rows found in sheet
                      </div>
                      <div className="text-[11px] text-amber-700">
                        Duplicate occurrences within the sheet will be skipped automatically to maintain 1:1 mapping.
                      </div>
                    </div>
                  )}

                  {/* Table of extracted barcodes */}
                  <div className="border border-slate-200 rounded-lg overflow-hidden max-h-[320px] overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                        <tr className="text-left font-bold text-slate-600 uppercase tracking-wider text-[10px]">
                          <th className="px-3 py-2">Row</th>
                          <th className="px-3 py-2">Style Code</th>
                          <th className="px-3 py-2">Color</th>
                          <th className="px-3 py-2">Size</th>
                          <th className="px-3 py-2">EAN / Barcode</th>
                          <th className="px-3 py-2">Match Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono">
                        {previewData.extracted_items?.map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-50">
                            <td className="px-3 py-1.5 text-slate-400 text-[11px]">
                              #{row.row_number}
                            </td>
                            <td className="px-3 py-1.5 font-bold text-slate-900">
                              {row.style_code}
                            </td>
                            <td className="px-3 py-1.5 text-slate-600">
                              {row.color || "—"}
                            </td>
                            <td className="px-3 py-1.5 font-bold text-[#0D9488]">
                              {row.size}
                            </td>
                            <td className="px-3 py-1.5 font-bold text-slate-800">
                              {row.ean_code}
                            </td>
                            <td className="px-3 py-1.5">
                              {row.is_po_match ? (
                                <Badge tone="success" className="text-[10px] font-sans">
                                  PO Match
                                </Badge>
                              ) : (
                                <Badge tone="neutral" className="text-[10px] font-sans">
                                  General
                                </Badge>
                              )}
                              {row.exists_in_db && (
                                <span className="ml-1 text-[10px] text-blue-600 font-sans font-semibold">
                                  (In DB)
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Overwrite toggle & Confirm Import Bar */}
                  <div className="pt-3 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3">
                    <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={overwrite}
                        onChange={(e) => setOverwrite(e.target.checked)}
                        className="rounded border-slate-300 text-[#0D9488] focus:ring-[#0D9488]"
                        data-testid="checkbox-overwrite-ean"
                      />
                      <span>Overwrite existing EAN codes in database</span>
                    </label>

                    <div className="flex items-center gap-2">
                      <BtnSecondary onClick={() => setPreviewData(null)} className="text-xs">
                        Cancel
                      </BtnSecondary>
                      <BtnPrimary
                        onClick={handleImport}
                        disabled={importing || !previewData.extracted_items?.length}
                        className="text-xs bg-[#0D9488] hover:bg-[#0f766e] border-[#0D9488]"
                        data-testid="confirm-import-ean-btn"
                      >
                        {importing ? (
                          <>
                            <Loader2 className="w-3.5 h-3.5 animate-spin mr-1 inline" />
                            Importing...
                          </>
                        ) : (
                          <>
                            <Check className="w-3.5 h-3.5 mr-1 inline" />
                            Import {previewData.extracted_items?.length} Barcodes
                          </>
                        )}
                      </BtnPrimary>
                    </div>
                  </div>
                </div>
              )}

              {/* Import Result Banner with Detailed Match / Unmatched Summary */}
              {importResult && (
                <div
                  className="p-4 bg-white border-2 border-slate-200 rounded-lg text-xs space-y-3 shadow-sm"
                  data-testid="ean-import-success-banner"
                >
                  <div className="flex items-center gap-2 text-emerald-800 font-bold text-sm bg-emerald-50 p-2.5 rounded border border-emerald-200">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                    <span>Successfully imported {importResult.imported} EAN barcode(s) for PO {po?.po_number}!</span>
                  </div>

                  {importResult.skipped_duplicates > 0 && (
                    <div className="text-slate-600 px-1">
                      Skipped <strong className="font-mono text-slate-800">{importResult.skipped_duplicates}</strong> duplicate or existing record(s).
                    </div>
                  )}

                  {/* Flagged Unmatched Rows (Invalid Style/Color/Size for this PO) */}
                  {importResult.unmatched_rows && importResult.unmatched_rows.length > 0 && (
                    <div
                      className="p-3 bg-amber-50 border border-amber-300 rounded-lg text-amber-900 space-y-2"
                      data-testid="unmatched-rows-alert"
                    >
                      <div className="font-bold flex items-center gap-1.5 text-xs text-amber-800">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                        <span>
                          {importResult.unmatched_rows.length} row(s) failed to match a valid style/color/size for this PO (flagged below):
                        </span>
                      </div>
                      <div className="text-[11px] text-amber-700">
                        These items were skipped from saving into PO barcodes because they do not correspond to any line item in PO #{po?.po_number}.
                      </div>

                      <div className="border border-amber-200 rounded overflow-hidden max-h-[180px] overflow-y-auto bg-white font-mono">
                        <table className="w-full text-[11px]">
                          <thead className="bg-amber-100/60 border-b border-amber-200 text-left font-bold text-amber-900">
                            <tr>
                              <th className="px-2.5 py-1.5">Row</th>
                              <th className="px-2.5 py-1.5">Raw Style</th>
                              <th className="px-2.5 py-1.5">Color</th>
                              <th className="px-2.5 py-1.5">Size</th>
                              <th className="px-2.5 py-1.5">EAN Code</th>
                              <th className="px-2.5 py-1.5">Reason</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-amber-100">
                            {importResult.unmatched_rows.map((unm, i) => (
                              <tr key={i} className="hover:bg-amber-50/50">
                                <td className="px-2.5 py-1 text-slate-500">#{unm.row_number}</td>
                                <td className="px-2.5 py-1 font-bold text-slate-800">{unm.raw_style || unm.style_code}</td>
                                <td className="px-2.5 py-1 text-slate-600">{unm.raw_color || unm.color || "—"}</td>
                                <td className="px-2.5 py-1 font-bold text-amber-800">{unm.raw_size || unm.size}</td>
                                <td className="px-2.5 py-1 text-slate-700">{unm.ean_code}</td>
                                <td className="px-2.5 py-1 font-sans text-amber-700 text-[10px]">{unm.reason}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                    <button
                      onClick={() => setActiveTab("current")}
                      className="underline font-bold text-[#0D9488] hover:text-teal-800"
                    >
                      &larr; View stored barcodes
                    </button>
                    <span className="text-[11px] text-slate-400 font-mono">
                      PO {po?.po_number}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </Drawer>

      <ConfirmDialog
        open={confirmClear}
        title="Clear PO Barcodes"
        message={`Are you sure you want to remove all ${existingEans.length} stored EAN barcodes for PO ${po?.po_number}?`}
        onConfirm={handleClearAll}
        onCancel={() => setConfirmClear(false)}
      />
    </>
  );
}
