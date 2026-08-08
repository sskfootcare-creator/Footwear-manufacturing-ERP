import React, { useState, useEffect } from "react";
import {
  Folder, FileText, Layers, Wrench, ShieldCheck, History,
  Upload, Eye, Download, Printer, RefreshCw, Search, Plus, Filter,
  CheckCircle, ArrowLeft, Image as ImageIcon, Sparkles, AlertCircle, X
} from "lucide-react";
import { http } from "@/lib/api";
import DocumentViewerModal from "../components/plm/DocumentViewerModal";
import PLMGlobalSearchModal from "../components/plm/PLMGlobalSearchModal";

const DEFAULT_PLM_FOLDERS = [
  { code: "01", name: "01 Reference Images" },
  { code: "02", name: "02 Tech Pack" },
  { code: "03", name: "03 Upper Patterns" },
  { code: "04", name: "04 Lining Patterns" },
  { code: "05", name: "05 Insole Patterns" },
  { code: "06", name: "06 Bottom Patterns" },
  { code: "07", name: "07 Sole Drawings" },
  { code: "08", name: "08 Sole Mould" },
  { code: "09", name: "09 Last Details" },
  { code: "10", name: "10 Cutting Dies" },
  { code: "11", name: "11 Embossing Dies" },
  { code: "12", name: "12 Printing Screens" },
  { code: "13", name: "13 CAD Files" },
  { code: "14", name: "14 BOM" },
  { code: "15", name: "15 Cost Sheet" },
  { code: "16", name: "16 Sample Images" },
  { code: "17", name: "17 Customer Artwork" },
  { code: "18", name: "18 Packaging Artwork" },
  { code: "19", name: "19 QC Documents" },
  { code: "20", name: "20 Production Notes" },
  { code: "21", name: "21 Vendor Documents" },
  { code: "22", name: "22 Compliance Documents" },
  { code: "23", name: "23 Revision History" },
];

export default function StylePLM({ initialStyleCode, onBack }) {
  const [styles, setStyles] = useState([]);
  const [selectedStyleCode, setSelectedStyleCode] = useState(initialStyleCode || "");
  const [selectedStyle, setSelectedStyle] = useState(null);
  const [activeTab, setActiveTab] = useState("engineering"); // overview | images | engineering | patterns | tooling | production | documents | revision | activity

  const [folderData, setFolderData] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [selectedFolder, setSelectedFolder] = useState(null); // null = all 23 folders view

  const [loading, setLoading] = useState(false);
  const [viewerDoc, setViewerDoc] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);

  // Upload state
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadForm, setUploadForm] = useState({
    folder_code: "01",
    folder_name: "01 Reference Images",
    document_name: "",
    document_type: "other",
    url: "",
    file_name: "",
    file_size: 1048576,
    pattern_category: "",
    remarks: "",
  });

  // Load Styles List
  useEffect(() => {
    fetchStyles();
  }, []);

  // When selected style changes, fetch PLM folders & documents
  useEffect(() => {
    if (selectedStyleCode) {
      loadStylePLM(selectedStyleCode);
    }
  }, [selectedStyleCode]);

  const fetchStyles = async () => {
    try {
      const res = await http.get("/styles");
      setStyles(res.data);
      if (!selectedStyleCode && res.data.length > 0) {
        setSelectedStyleCode(res.data[0].code);
      }
    } catch (e) {
      console.error("Failed to fetch styles:", e);
    }
  };

  const loadStylePLM = async (code) => {
    setLoading(true);
    try {
      const s = styles.find(x => x.code === code);
      if (s) setSelectedStyle(s);

      const fRes = await http.get(`/plm/styles/${code}/folders`);
      setFolderData(fRes.data);

      const dRes = await http.get(`/plm/styles/${code}/documents`);
      setDocuments(dRes.data);

      const aRes = await http.get(`/plm/audit-log?style_code=${code}`);
      setAuditLogs(aRes.data);
    } catch (e) {
      console.error("Failed to load style PLM data:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadSubmit = async (e) => {
    e.preventDefault();
    if (!uploadForm.document_name || !uploadForm.url) {
      alert("Document Name and File URL are required.");
      return;
    }
    try {
      await http.post(`/plm/styles/${selectedStyleCode}/documents/upload`, {
        style_id: folderData?.style_id || selectedStyleCode,
        style_code: selectedStyleCode,
        folder_code: uploadForm.folder_code,
        folder_name: uploadForm.folder_name,
        document_name: uploadForm.document_name,
        document_type: uploadForm.document_type,
        pattern_category: uploadForm.pattern_category || undefined,
        file_name: uploadForm.file_name || `${uploadForm.document_name}.pdf`,
        file_size: uploadForm.file_size || 1048576,
        url: uploadForm.url,
        thumbnail_url: uploadForm.url,
        remarks: uploadForm.remarks,
      });

      setUploadModalOpen(false);
      setUploadForm({
        folder_code: "01",
        folder_name: "01 Reference Images",
        document_name: "",
        document_type: "other",
        url: "",
        file_name: "",
        file_size: 1048576,
        pattern_category: "",
        remarks: "",
      });
      loadStylePLM(selectedStyleCode);
    } catch (err) {
      alert("Upload failed: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleRollback = async (docId, targetVersion) => {
    if (!window.confirm(`Are you sure you want to rollback to Version v${targetVersion}?`)) return;
    try {
      await http.post(`/plm/styles/${selectedStyleCode}/documents/${docId}/rollback?target_version=${targetVersion}`);
      setViewerDoc(null);
      loadStylePLM(selectedStyleCode);
    } catch (err) {
      alert("Rollback failed: " + (err.response?.data?.detail || err.message));
    }
  };

  const filteredDocs = selectedFolder
    ? documents.filter(d => d.folder_code === selectedFolder.code)
    : documents;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-8 space-y-6">
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
        <div className="flex items-center gap-4">
          {onBack && (
            <button
              onClick={onBack}
              className="p-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition border border-slate-700"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-400 rounded-xl">
            <Layers className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-black tracking-tight text-white">Digital Style Folder</h1>
              <span className="bg-amber-500/20 text-amber-300 text-xs font-mono font-bold px-2.5 py-1 rounded-full border border-amber-500/30">
                PLM Lifecycle Module
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">Single Source of Truth for Product Engineering & Documentation</p>
          </div>
        </div>

        {/* Style Picker & Global Search */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setSearchOpen(true)}
            className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-xl text-xs font-bold transition flex items-center gap-2"
          >
            <Search className="w-4 h-4 text-amber-400" />
            Global Search
          </button>

          <select
            value={selectedStyleCode}
            onChange={(e) => setSelectedStyleCode(e.target.value)}
            className="bg-slate-950 border border-slate-700 text-white font-mono font-bold text-sm px-4 py-2.5 rounded-xl outline-none focus:border-amber-500 transition"
          >
            {styles.map((s) => (
              <option key={s.id} value={s.code}>
                {s.code} — {s.name}
              </option>
            ))}
          </select>

          <button
            onClick={() => setUploadModalOpen(true)}
            className="px-4 py-2.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold rounded-xl shadow-lg transition flex items-center gap-2"
          >
            <Upload className="w-4 h-4" />
            Upload Document
          </button>
        </div>
      </div>

      {/* Style Details Summary Banner */}
      {selectedStyle && (
        <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {selectedStyle.image_url ? (
              <img src={selectedStyle.image_url} alt={selectedStyle.name} className="w-14 h-14 object-cover rounded-xl border border-slate-700 bg-slate-950" />
            ) : (
              <div className="w-14 h-14 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-center text-slate-600 font-mono text-xs">No Image</div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-black text-amber-400 text-lg">{selectedStyle.code}</span>
                <span className="text-white font-bold text-base">• {selectedStyle.name}</span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Category: <span className="text-slate-200 font-medium">{selectedStyle.category || "Footwear"}</span> • Upper Material: <span className="text-slate-200 font-medium">{selectedStyle.upper_material || "N/A"}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-6 font-mono text-xs">
            <div className="text-right">
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Base Cost</span>
              <span className="text-emerald-400 font-bold text-sm">Rs.{selectedStyle.costing?.total_cost || "0.00"}</span>
            </div>
            <div className="text-right border-l border-slate-800 pl-6">
              <span className="text-slate-400 block text-[10px] uppercase font-bold">PLM Documents</span>
              <span className="text-amber-400 font-bold text-sm">{documents.length} Files</span>
            </div>
          </div>
        </div>
      )}

      {/* Engineering Tabs Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-2 flex flex-wrap gap-1">
        {[
          { key: "engineering", label: "03. Engineering (23 Folders)", icon: Folder },
          { key: "overview", label: "01. Overview", icon: Sparkles },
          { key: "images", label: "02. Product Images", icon: ImageIcon },
          { key: "patterns", label: "04. Patterns", icon: Layers },
          { key: "tooling", label: "05. Tooling & Moulds", icon: Wrench },
          { key: "documents", label: "06. All Documents", icon: FileText },
          { key: "revision", label: "07. Revision History", icon: RefreshCw },
          { key: "activity", label: "08. Activity Log", icon: History },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => { setActiveTab(tab.key); setSelectedFolder(null); }}
              className={`px-4 py-2.5 text-xs font-bold rounded-xl transition flex items-center gap-2 ${
                isActive
                  ? "bg-amber-600 text-white shadow-md"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Main Tab Content */}
      {loading ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400 font-mono text-sm animate-pulse">
          Loading PLM Engineering Assets for {selectedStyleCode}...
        </div>
      ) : (
        <>
          {/* TAB: 23-FOLDER DIGITAL STYLE FOLDER TREE */}
          {activeTab === "engineering" && (
            <div className="space-y-6">
              {/* Folder Selector Breadcrumb */}
              {selectedFolder && (
                <div className="flex items-center justify-between bg-amber-950/30 border border-amber-500/30 p-4 rounded-xl">
                  <div className="flex items-center gap-2">
                    <Folder className="w-5 h-5 text-amber-400" />
                    <span className="font-bold text-white text-sm">Filtered by Folder:</span>
                    <span className="font-mono text-amber-300 font-bold">{selectedFolder.name}</span>
                  </div>
                  <button
                    onClick={() => setSelectedFolder(null)}
                    className="text-xs font-bold text-amber-400 hover:text-amber-300 underline"
                  >
                    View All 23 Folders
                  </button>
                </div>
              )}

              {/* 23 Folders Grid */}
              {!selectedFolder && (
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
                    <Folder className="w-4 h-4 text-amber-400" /> Standardized 23 PLM Sub-Folders
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {folderData?.folders?.map((f) => (
                      <div
                        key={f.code}
                        onClick={() => setSelectedFolder(f)}
                        className="bg-slate-900 border border-slate-800 hover:border-amber-500/50 p-4 rounded-2xl cursor-pointer transition group flex flex-col justify-between"
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-mono font-bold text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                              {f.code}
                            </span>
                            <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded-full ${
                              f.file_count > 0 ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" : "bg-slate-800 text-slate-500"
                            }`}>
                              {f.file_count || 0} Files
                            </span>
                          </div>
                          <h4 className="font-bold text-sm text-white group-hover:text-amber-300 transition">{f.name}</h4>
                          <p className="text-xs text-slate-400 mt-1 line-clamp-2">{f.description}</p>
                        </div>
                        <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-500 font-medium">
                          <span>Browse Assets</span>
                          <Folder className="w-4 h-4 text-slate-600 group-hover:text-amber-400 transition" />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Asset Documents Cards */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-teal-400" />
                    Engineering Asset Cards ({filteredDocs.length})
                  </h3>
                  <button
                    onClick={() => {
                      setUploadForm(prev => ({
                        ...prev,
                        folder_code: selectedFolder ? selectedFolder.code : "01",
                        folder_name: selectedFolder ? selectedFolder.name : "01 Reference Images"
                      }));
                      setUploadModalOpen(true);
                    }}
                    className="text-xs font-bold text-amber-400 hover:text-amber-300 flex items-center gap-1"
                  >
                    <Plus className="w-4 h-4" /> Add File to {selectedFolder ? selectedFolder.name : "Style"}
                  </button>
                </div>

                {filteredDocs.length === 0 ? (
                  <div className="bg-slate-900 border border-dashed border-slate-800 p-12 text-center rounded-2xl text-slate-500">
                    <FileText className="w-12 h-12 text-slate-700 mx-auto mb-3" />
                    <p className="text-sm font-medium">No engineering documents uploaded in this folder yet.</p>
                    <button
                      onClick={() => setUploadModalOpen(true)}
                      className="mt-4 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs rounded-xl transition inline-flex items-center gap-2"
                    >
                      <Upload className="w-4 h-4" /> Upload First Document
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                    {filteredDocs.map((doc) => {
                      const isImg = /\.(jpg|jpeg|png|webp|gif)$/i.test(doc.file_name || doc.url);
                      return (
                        <div key={doc.id} className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-2xl overflow-hidden shadow-xl flex flex-col justify-between group">
                          {/* Card Preview Header */}
                          <div className="h-40 bg-slate-950 relative overflow-hidden flex items-center justify-center p-3 border-b border-slate-800">
                            {isImg ? (
                              <img src={doc.url} alt={doc.document_name} className="max-h-full max-w-full object-contain rounded-lg group-hover:scale-105 transition duration-300" />
                            ) : (
                              <div className="text-center p-4">
                                <FileText className="w-12 h-12 text-amber-500 mx-auto mb-2" />
                                <span className="font-mono text-xs text-slate-400 uppercase font-bold">{doc.file_name}</span>
                              </div>
                            )}
                            <span className="absolute top-3 left-3 bg-amber-500 text-slate-950 text-[10px] font-mono font-black px-2 py-0.5 rounded shadow">
                              v{doc.current_version}
                            </span>
                            <span className="absolute top-3 right-3 bg-slate-900/90 text-slate-300 text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700">
                              {doc.folder_code}
                            </span>
                          </div>

                          {/* Card Body */}
                          <div className="p-5 space-y-3 flex-1 flex flex-col justify-between">
                            <div>
                              <h4 className="font-bold text-white text-base leading-snug line-clamp-1">{doc.document_name}</h4>
                              <p className="text-xs text-slate-400 mt-1 font-mono">{doc.folder_name}</p>
                              {doc.remarks && <p className="text-xs text-slate-400 italic mt-2 line-clamp-2">"{doc.remarks}"</p>}
                            </div>

                            {/* Card Actions */}
                            <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between gap-2">
                              <button
                                onClick={() => setViewerDoc(doc)}
                                className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold rounded-xl transition flex items-center justify-center gap-1.5"
                              >
                                <Eye className="w-3.5 h-3.5 text-amber-400" /> Preview
                              </button>
                              <a
                                href={doc.url}
                                download={doc.file_name}
                                className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-xl transition border border-slate-700"
                                title="Download"
                              >
                                <Download className="w-4 h-4" />
                              </a>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB: REVISION HISTORY / AUDIT LOG */}
          {(activeTab === "revision" || activeTab === "activity") && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
              <h3 className="font-bold text-lg text-white flex items-center gap-2">
                <History className="w-5 h-5 text-amber-400" />
                ECO / ECN Audit Log for {selectedStyleCode}
              </h3>
              <div className="space-y-3">
                {auditLogs.length === 0 ? (
                  <p className="text-sm text-slate-500 italic">No audit records logged for this style yet.</p>
                ) : (
                  auditLogs.map((log) => (
                    <div key={log.id} className="p-4 bg-slate-950 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs">
                      <div>
                        <div className="flex items-center gap-2 font-bold text-white">
                          <span className="uppercase text-[10px] px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded font-mono border border-amber-500/20">
                            {log.action}
                          </span>
                          {log.details}
                        </div>
                        <p className="text-slate-400 mt-1 font-mono">
                          User: {log.user} • Time: {new Date(log.timestamp).toLocaleString()}
                        </p>
                      </div>
                      {log.current_version && (
                        <span className="font-mono text-amber-300 font-bold bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800">
                          v{log.previous_version || "1"} → v{log.current_version}
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Upload Modal */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="bg-slate-900 border border-slate-700 w-full max-w-lg rounded-2xl p-6 space-y-5 text-slate-100 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <h3 className="font-bold text-lg text-white flex items-center gap-2">
                <Upload className="w-5 h-5 text-amber-400" /> Upload PLM Asset
              </h3>
              <button onClick={() => setUploadModalOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleUploadSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-bold mb-1">Target Sub-Folder</label>
                <select
                  value={uploadForm.folder_code}
                  onChange={(e) => {
                    const found = DEFAULT_PLM_FOLDERS.find(f => f.code === e.target.value);
                    setUploadForm({ ...uploadForm, folder_code: e.target.value, folder_name: found?.name || "" });
                  }}
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500"
                >
                  {DEFAULT_PLM_FOLDERS.map((f) => (
                    <option key={f.code} value={f.code}>
                      {f.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Document Title</label>
                <input
                  type="text"
                  value={uploadForm.document_name}
                  onChange={(e) => setUploadForm({ ...uploadForm, document_name: e.target.value })}
                  placeholder="e.g. Upper Pattern DXF Specification"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">File URL / ImageKit Storage Link</label>
                <input
                  type="text"
                  value={uploadForm.url}
                  onChange={(e) => setUploadForm({ ...uploadForm, url: e.target.value, file_name: e.target.value.split("/").pop() || "asset.pdf" })}
                  placeholder="https://ik.imagekit.io/ssk/... or file link"
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1">Engineering Remarks / ECO Notes</label>
                <textarea
                  value={uploadForm.remarks}
                  onChange={(e) => setUploadForm({ ...uploadForm, remarks: e.target.value })}
                  placeholder="Initial release / pattern revision notes..."
                  className="w-full bg-slate-950 border border-slate-700 text-white p-2.5 rounded-xl outline-none focus:border-amber-500 h-20"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setUploadModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-white font-bold rounded-xl shadow-lg"
                >
                  Upload & Save Metadata
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Document Viewer Modal */}
      {viewerDoc && (
        <DocumentViewerModal
          document={viewerDoc}
          onClose={() => setViewerDoc(null)}
          onRollback={(ver) => handleRollback(viewerDoc.id, ver)}
        />
      )}

      {/* Global Search Modal */}
      <PLMGlobalSearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSelectStyle={(s) => setSelectedStyleCode(s.code)}
      />
    </div>
  );
}
