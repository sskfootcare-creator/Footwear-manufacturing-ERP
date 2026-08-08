import React, { useState } from "react";
import {
  X, ZoomIn, ZoomOut, RotateCw, Download, Printer, History,
  Maximize2, ChevronLeft, ChevronRight, Layers, FileText, CheckCircle2, RefreshCw
} from "lucide-react";

export default function DocumentViewerModal({ document, onClose, onRollback, onReplace }) {
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [activeTab, setActiveTab] = useState("preview"); // 'preview' | 'history' | 'compare'
  const [compareVersion, setCompareVersion] = useState(null);

  if (!document) return null;

  const currentVer = document.current_version || 1;
  const versions = document.versions || [];
  const currentVerDoc = versions.find(v => v.version === currentVer) || {
    url: document.url,
    file_name: document.file_name,
    file_size: document.file_size,
    uploaded_by: document.uploaded_by || "User",
    uploaded_at: document.updated_at || document.created_at,
    remarks: document.remarks || "Current Version",
  };

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 25, 250));
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 25, 50));
  const handleRotate = () => setRotation(prev => (prev + 90) % 360);

  const handlePrint = () => {
    const printWindow = window.open(document.url, "_blank");
    if (printWindow) {
      printWindow.focus();
      printWindow.print();
    }
  };

  const isImage = /\.(jpg|jpeg|png|webp|gif)$/i.test(currentVerDoc.file_name || document.url);
  const isPdf = /\.pdf$/i.test(currentVerDoc.file_name || document.url);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 sm:p-6 animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-6xl h-[90vh] rounded-xl flex flex-col overflow-hidden text-slate-100 shadow-2xl">
        {/* Top Control Bar */}
        <div className="bg-slate-950 px-6 py-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/10 text-amber-400 rounded-lg">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-white">{document.document_name}</h3>
                <span className="bg-amber-500/20 text-amber-300 text-xs px-2 py-0.5 rounded font-mono font-bold border border-amber-500/30">
                  v{currentVer}
                </span>
                <span className="text-xs text-slate-400 font-mono">({document.folder_name})</span>
              </div>
              <p className="text-xs text-slate-400">
                {currentVerDoc.file_name} • {((currentVerDoc.file_size || 0) / 1024).toFixed(1)} KB • Uploaded by {currentVerDoc.uploaded_by}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* View Tabs */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-1 flex gap-1">
              <button
                onClick={() => setActiveTab("preview")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition ${activeTab === "preview" ? "bg-amber-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                Document Viewer
              </button>
              <button
                onClick={() => setActiveTab("history")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition flex items-center gap-1.5 ${activeTab === "history" ? "bg-amber-600 text-white" : "text-slate-400 hover:text-white"}`}
              >
                <History className="w-3.5 h-3.5" />
                Version History ({versions.length})
              </button>
            </div>

            {/* Viewer Controls */}
            {activeTab === "preview" && (
              <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1">
                <button onClick={handleZoomOut} title="Zoom Out" className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded">
                  <ZoomOut className="w-4 h-4" />
                </button>
                <span className="text-xs font-mono text-slate-400 px-1">{zoom}%</span>
                <button onClick={handleZoomIn} title="Zoom In" className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded">
                  <ZoomIn className="w-4 h-4" />
                </button>
                <button onClick={handleRotate} title="Rotate 90°" className="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded ml-1 border-l border-slate-800">
                  <RotateCw className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Action Buttons */}
            <a
              href={document.url}
              download={document.file_name}
              target="_blank"
              rel="noreferrer"
              className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white rounded-lg border border-slate-700 transition"
              title="Download File"
            >
              <Download className="w-4 h-4" />
            </a>
            <button
              onClick={handlePrint}
              className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white rounded-lg border border-slate-700 transition"
              title="Print Document"
            >
              <Printer className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 rounded-lg transition ml-2 border border-rose-500/30"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Viewer Area */}
        <div className="flex-1 overflow-auto bg-slate-950 flex items-center justify-center p-6 relative">
          {activeTab === "preview" && (
            <div
              className="transition-all duration-200 flex items-center justify-center min-w-full min-h-full"
              style={{
                transform: `scale(${zoom / 100}) rotate(${rotation}deg)`,
                transformOrigin: "center center",
              }}
            >
              {isImage ? (
                <img
                  src={document.url}
                  alt={document.document_name}
                  className="max-h-[75vh] max-w-full object-contain rounded-lg shadow-2xl border border-slate-800"
                />
              ) : isPdf ? (
                <iframe
                  src={document.url}
                  title={document.document_name}
                  className="w-[80vw] max-w-5xl h-[75vh] rounded-lg border border-slate-800 bg-white"
                />
              ) : (
                <div className="text-center p-8 bg-slate-900 border border-slate-800 rounded-xl max-w-md">
                  <FileText className="w-16 h-16 text-amber-500 mx-auto mb-4" />
                  <h4 className="text-lg font-bold text-white mb-2">{document.file_name}</h4>
                  <p className="text-sm text-slate-400 mb-6">Preview not directly embedded for this file type.</p>
                  <a
                    href={document.url}
                    download={document.file_name}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg font-semibold text-sm transition"
                  >
                    <Download className="w-4 h-4" /> Download to View
                  </a>
                </div>
              )}
            </div>
          )}

          {activeTab === "history" && (
            <div className="w-full max-w-4xl max-h-[75vh] overflow-y-auto bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h4 className="font-bold text-lg text-white mb-4 flex items-center gap-2">
                <History className="w-5 h-5 text-amber-400" />
                Version Audit & Rollback History
              </h4>
              <div className="space-y-4">
                {versions.slice().reverse().map((ver) => {
                  const isCurrent = ver.version === currentVer;
                  return (
                    <div
                      key={ver.version}
                      className={`p-4 rounded-xl border transition ${
                        isCurrent
                          ? "bg-amber-950/30 border-amber-500/50"
                          : "bg-slate-950 border-slate-800 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <span className={`px-2.5 py-1 text-xs font-mono font-bold rounded-md ${
                            isCurrent ? "bg-amber-500 text-slate-950" : "bg-slate-800 text-slate-300"
                          }`}>
                            Version {ver.version}
                          </span>
                          <div>
                            <div className="font-semibold text-sm text-white flex items-center gap-2">
                              {ver.file_name}
                              {isCurrent && (
                                <span className="text-[10px] uppercase font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                                  Current Active Version
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 mt-0.5">
                              Uploaded by <span className="text-slate-200 font-medium">{ver.uploaded_by}</span> on {new Date(ver.uploaded_at).toLocaleString()}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <a
                            href={ver.url}
                            target="_blank"
                            rel="noreferrer"
                            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg text-slate-200 transition"
                          >
                            Preview
                          </a>
                          {!isCurrent && onRollback && (
                            <button
                              onClick={() => onRollback(ver.version)}
                              className="px-3 py-1.5 bg-amber-600/20 hover:bg-amber-600 text-amber-300 hover:text-white border border-amber-500/30 text-xs font-semibold rounded-lg transition flex items-center gap-1"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                              Rollback to v{ver.version}
                            </button>
                          )}
                        </div>
                      </div>
                      {ver.remarks && (
                        <p className="text-xs text-slate-400 mt-3 pt-3 border-t border-slate-800/80 italic">
                          Remarks: "{ver.remarks}"
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
