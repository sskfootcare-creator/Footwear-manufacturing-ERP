import React, { useState, useEffect } from "react";
import http from "../api/http";
import { Download, FileSpreadsheet, FileText, X, CheckCircle, AlertCircle, Eye } from "lucide-react";

export default function PackingListPreviewModal({ po, isOpen, onClose }) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cartonDim, setCartonDim] = useState("60x50x30 CMS");

  useEffect(() => {
    if (isOpen && po) {
      fetchPreview();
    }
  }, [isOpen, po]);

  const fetchPreview = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await http.post("/packing-list/preview", {
        po_id: po.id,
        carton_dim: cartonDim,
      });
      setPreview(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load packing list preview");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !po) return null;

  const downloadXlsx = () => {
    const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
    window.open(`${API}/pos/${po.id}/packing-list.xlsx`, "_blank");
  };

  const downloadPdf = () => {
    const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
    window.open(`${API}/pos/${po.id}/packing-list.pdf`, "_blank");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col overflow-hidden border border-slate-200">
        
        {/* Header */}
        <div className="px-6 py-4 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Eye className="w-6 h-6 text-amber-400" />
            <div>
              <h2 className="text-lg font-bold tracking-tight">PACKING LIST PREVIEW</h2>
              <p className="text-xs text-slate-400">Master PDF Visual Reference Verification</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50">
          
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3 text-red-700 text-sm">
              <AlertCircle className="w-5 h-5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="py-16 text-center space-y-3">
              <div className="w-10 h-10 border-4 border-slate-900 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm font-medium text-slate-600">Generating Packing List Preview...</p>
            </div>
          ) : preview ? (
            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200 space-y-6 text-xs text-slate-800 font-sans">
              
              {/* Document Title Banner */}
              <div className="bg-slate-200 py-2.5 text-center font-bold text-base tracking-wider text-slate-900 border border-slate-400">
                PACKING LIST
              </div>

              {/* Vendor & Destination Blocks */}
              <div className="grid grid-cols-2 gap-4">
                <div className="border border-slate-400 p-3 space-y-1 bg-slate-50/50">
                  <div className="font-bold text-slate-900">VENDOR NAME : {preview.vendor.name}</div>
                  <div className="text-slate-600 leading-tight whitespace-pre-line">{preview.vendor.address}</div>
                  <div className="font-bold text-slate-900 mt-1">GSTIN:- {preview.vendor.gstin}</div>
                </div>

                <div className="border border-slate-400 p-3 space-y-1 bg-slate-50/50">
                  <div className="font-bold text-slate-900 text-center">DESTINATION HUB</div>
                  <div className="font-semibold text-center text-slate-800">{preview.destination.name}</div>
                  <div className="text-slate-600 text-center leading-tight">{preview.destination.address}</div>
                  <div className="font-bold text-center text-slate-900">GSTIN:- {preview.destination.gstin}</div>
                  <div className="text-center font-medium text-slate-500">EACHES</div>
                </div>
              </div>

              {/* PO Meta Section */}
              <div className="border border-slate-400 p-3 bg-white grid grid-cols-12 gap-2 text-center items-center">
                <div className="col-span-2 font-bold text-left">PO NO</div>
                <div className="col-span-3 font-semibold text-left">{preview.po.po_number}</div>
                <div className="col-span-1 font-bold bg-slate-100 py-1">{preview.po.total_pcs}</div>
                <div className="col-span-1 font-bold">PCS</div>
                <div className="col-span-1 font-bold">BOX</div>
                <div className="col-span-1 font-bold bg-slate-100 py-1">{preview.po.total_cartons}</div>
                <div className="col-span-3 font-bold text-slate-500 text-right">EACHES</div>

                <div className="col-span-2 font-bold text-left border-t pt-2">PO DATE</div>
                <div className="col-span-3 font-semibold text-left border-t pt-2">{preview.po.po_date}</div>
                <div className="col-span-3 border-t pt-2 font-bold text-right">CARTON DIMENTION</div>
                <div className="col-span-4 border-t pt-2 font-bold bg-slate-100 py-1 text-center">{preview.po.carton_dimension}</div>
              </div>

              {/* Main Packing Table */}
              <div className="overflow-x-auto border border-slate-400">
                <table className="w-full text-center border-collapse text-[11px]">
                  <thead>
                    <tr className="bg-slate-200 font-bold border-b border-slate-400 text-slate-900">
                      <th className="p-1.5 border-r border-slate-400">SITE CODE</th>
                      <th className="p-1.5 border-r border-slate-400 text-left">Style</th>
                      <th className="p-1.5 border-r border-slate-400 text-left">Colour</th>
                      <th className="p-1.5 border-r border-slate-400">CTN .NO</th>
                      {preview.sizes.map((sz) => (
                        <th key={sz} className="p-1.5 border-r border-slate-400 w-8">{sz}</th>
                      ))}
                      <th className="p-1.5 border-r border-slate-400">PCS/CTN</th>
                      <th className="p-1.5 border-r border-slate-400">Per Carton</th>
                      <th className="p-1.5 border-r border-slate-400">TTL CTN</th>
                      <th className="p-1.5 border-r border-slate-400">Total PCS</th>
                      <th className="p-1.5 border-r border-slate-400">NET WEIGHT</th>
                      <th className="p-1.5">GROSS WEIGHT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} className="border-b border-slate-300 hover:bg-slate-50">
                        <td className="p-1.5 border-r border-slate-300 font-medium">{row.site_code}</td>
                        <td className="p-1.5 border-r border-slate-300 font-bold text-left">{row.style}</td>
                        <td className="p-1.5 border-r border-slate-300 text-left">{row.color}</td>
                        <td className="p-1.5 border-r border-slate-300">{row.carton_no}</td>
                        {preview.sizes.map((sz) => (
                          <td key={sz} className="p-1.5 border-r border-slate-300">
                            {row.by_size[sz] || ""}
                          </td>
                        ))}
                        <td className="p-1.5 border-r border-slate-300 font-medium">{row.pcs_per_carton}</td>
                        <td className="p-1.5 border-r border-slate-300">{row.per_carton}</td>
                        <td className="p-1.5 border-r border-slate-300 font-semibold">{row.total_cartons}</td>
                        <td className="p-1.5 border-r border-slate-300 font-bold">{row.total_pcs}</td>
                        <td className="p-1.5 border-r border-slate-300 text-right">{row.net_weight.toFixed(3)}</td>
                        <td className="p-1.5 text-right">{row.gross_weight.toFixed(3)}</td>
                      </tr>
                    ))}

                    {/* Grand Total Row */}
                    <tr className="bg-slate-200 font-bold border-t-2 border-slate-400 text-slate-900">
                      <td colSpan={4} className="p-2 border-r border-slate-400 text-center">GRAND TOTAL</td>
                      {preview.sizes.map((sz) => (
                        <td key={sz} className="p-2 border-r border-slate-400">
                          {preview.grand_total.size_totals[sz]}
                        </td>
                      ))}
                      <td className="p-2 border-r border-slate-400"></td>
                      <td className="p-2 border-r border-slate-400"></td>
                      <td className="p-2 border-r border-slate-400">{preview.grand_total.total_cartons}</td>
                      <td className="p-2 border-r border-slate-400">{preview.grand_total.total_pcs}</td>
                      <td className="p-2 border-r border-slate-400 text-right">{preview.grand_total.net_weight.toFixed(3)}</td>
                      <td className="p-2 text-right">{preview.grand_total.gross_weight.toFixed(3)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Order Summary & Authorised Signatory */}
              <div className="grid grid-cols-12 gap-4 pt-2">
                
                {/* Order Summary Table (Left) */}
                <div className="col-span-8 border border-slate-400 overflow-hidden">
                  <table className="w-full text-center border-collapse text-[11px]">
                    <thead>
                      <tr className="bg-slate-200 font-bold border-b border-slate-400">
                        <th rowSpan={5} className="p-2 border-r border-slate-400 bg-slate-300 text-center font-bold w-28">
                          ORDER SUMMERY
                        </th>
                        <th className="p-1 border-r border-slate-400 font-bold">Size</th>
                        {preview.sizes.map((sz) => (
                          <th key={sz} className="p-1 border-r border-slate-400 font-bold">{sz}</th>
                        ))}
                        <th className="p-1 font-bold">TOTAL</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-slate-300">
                        <td className="p-1 font-semibold border-r border-slate-300 text-left pl-2">Order Qty</td>
                        {preview.sizes.map((sz) => (
                          <td key={sz} className="p-1 border-r border-slate-300">{preview.order_summary.order_qty[sz]}</td>
                        ))}
                        <td className="p-1 font-bold">{preview.order_summary.total_order_qty}</td>
                      </tr>
                      <tr className="border-b border-slate-300">
                        <td className="p-1 font-semibold border-r border-slate-300 text-left pl-2">Pack Qty</td>
                        {preview.sizes.map((sz) => (
                          <td key={sz} className="p-1 border-r border-slate-300">{preview.order_summary.pack_qty[sz]}</td>
                        ))}
                        <td className="p-1 font-bold">{preview.order_summary.total_pack_qty}</td>
                      </tr>
                      <tr className="border-b border-slate-300">
                        <td className="p-1 font-semibold border-r border-slate-300 text-left pl-2">Excss/Short</td>
                        {preview.sizes.map((sz) => (
                          <td key={sz} className="p-1 border-r border-slate-300">{preview.order_summary.excess_short[sz]}</td>
                        ))}
                        <td className="p-1 font-bold">{preview.order_summary.total_excess_short}</td>
                      </tr>
                      <tr>
                        <td className="p-1 font-semibold border-r border-slate-300 text-left pl-2">Excss/Short %</td>
                        {preview.sizes.map((sz) => (
                          <td key={sz} className="p-1 border-r border-slate-300">{preview.order_summary.excess_short_pct[sz]}</td>
                        ))}
                        <td className="p-1 font-bold">{preview.order_summary.total_excess_short_pct}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Authorised Signatory Box (Right) */}
                <div className="col-span-4 border border-slate-400 p-3 flex flex-col justify-between h-32 bg-slate-50">
                  <div className="font-bold text-center text-slate-800 text-[11px]">AUTHORISED SIGNATORY</div>
                  <div className="text-center text-[10px] text-slate-400 italic">Stamp / Signature</div>
                </div>

              </div>

            </div>
          ) : null}

        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 bg-slate-100 border-t border-slate-200 flex items-center justify-between">
          <div className="text-xs text-slate-500 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-500" />
            <span>Master PDF Visual Reference Verified</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition"
            >
              Close
            </button>

            <button
              onClick={downloadXlsx}
              className="px-4 py-2 text-xs font-semibold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition flex items-center gap-2 shadow-sm"
            >
              <FileSpreadsheet className="w-4 h-4" />
              Download Excel (.xlsx)
            </button>

            <button
              onClick={downloadPdf}
              className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition flex items-center gap-2 shadow-sm"
            >
              <FileText className="w-4 h-4" />
              Download PDF (.pdf)
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
