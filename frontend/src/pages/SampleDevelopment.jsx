import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { http, inr, formatApiError, friendlyAxiosError } from "../lib/api";
import { SafeImage, resolveImageUrl } from "../components/ImageUploader";
import SearchableSelect from "../components/SearchableSelect";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
  StatTile,
} from "../components/ui-kit";

const getErrorMessage = (err, fallback = "An error occurred") => {
  if (err?.response?.data?.detail) {
    return formatApiError(err.response.data.detail);
  }
  return friendlyAxiosError(err) || fallback;
};
import {
  Sparkles, Plus, Search, Filter, Camera, Trash2, CheckCircle2,
  AlertCircle, ArrowRight, Layers, Hammer, ShieldAlert,
  ChevronRight, RefreshCw, X, Upload, Palette, Scissors,
  Tag, Clock, UserCheck, ExternalLink, SlidersHorizontal, Check, Eye,
  ChevronLeft, Star, ImagePlus, Images, Printer, Scan, Ruler, Lock
} from "lucide-react";
import PatternYieldModal from "../components/PatternYieldModal";

const STATUS_CONFIG = {
  draft: { label: "Draft Spec", badgeColor: "slate", accent: "#94A3B8" },
  in_sampling: { label: "In Sampling", badgeColor: "yellow", accent: "#F59E0B" },
  sample_ready: { label: "Sample Ready", badgeColor: "blue", accent: "#2563EB" },
  approved: { label: "Approved for Prod", badgeColor: "green", accent: "#16A34A" },
  rejected: { label: "Rejected / Discarded", badgeColor: "red", accent: "#DC2626" },
  transferred_to_style: { label: "Style Master Created", badgeColor: "purple", accent: "#7C3AED" },
};

export default function SampleDevelopment() {
  const navigate = useNavigate();
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("active");
  const [profileFilter, setProfileFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [statusCounts, setStatusCounts] = useState({});

  // Helpers (materials & karigars)
  const [materials, setMaterials] = useState([]);
  const [workers, setWorkers] = useState([]);

  // Active Modals
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingSample, setEditingSample] = useState(null);
  const [photoModalSample, setPhotoModalSample] = useState(null);
  const [transferModalSample, setTransferModalSample] = useState(null);
  const [detailSample, setDetailSample] = useState(null);
  const [detailPrintMode, setDetailPrintMode] = useState(false);
  const [patternYieldModalSample, setPatternYieldModalSample] = useState(null);
  const [approvalPromptSample, setApprovalPromptSample] = useState(null);

  // Status transition state
  const [statusUpdateLoading, setStatusUpdateLoading] = useState(false);

  // Fetch samples
  const fetchSamples = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (profileFilter !== "all") params.profile = profileFilter;
      if (searchTerm.trim()) params.q = searchTerm.trim();

      const res = await http.get("/samples", { params });
      setSamples(res.data.items || []);
      setStatusCounts(res.data.status_counts || {});
    } catch (err) {
      console.error("Error fetching samples:", err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, profileFilter, searchTerm]);

  // Fetch helpers
  const fetchHelpers = useCallback(async () => {
    try {
      const res = await http.get("/samples/helpers/materials-and-karigars");
      setMaterials(res.data.materials || []);
      setWorkers(res.data.workers || []);
    } catch (err) {
      console.error("Error fetching helpers:", err);
    }
  }, []);

  useEffect(() => {
    fetchSamples();
    fetchHelpers();
  }, [fetchSamples, fetchHelpers]);

  // Open Create Modal
  const handleOpenCreate = () => {
    setEditingSample({
      sample_name: "",
      profile: "flat",
      category: "Footwear",
      season: "SS26",
      target_gender: "women",
      target_cost: 0,
      target_date: "",
      assigned_karigar_id: "",
      assigned_karigar_name: "",
      notes: "",
      inspiration_photos: [],
      upper_spec: {
        materials: [
          {
            material_id: "",
            material_name: "",
            material_code: "",
            color_to_develop: "",
            placement: "Primary",
            photo_url: ""
          }
        ],
        upper_top_material_id: "",
        upper_top_material_name: "",
        upper_top_material_code: "",
        upper_color_to_develop: "",
        canvas_backing: "",
        lining_material_id: "",
        lining_material_name: "",
        lining_material_code: "",
        cutting_operation: "die_cut",
        stitching_operation: "stitching",
        edge_treatment: "none",
        has_buckle: false,
        buckle_spec: "",
        buckle_photo_url: "",
        other_hardware: "",
      },
      insole_spec: {
        profile_type: "flat",
        heeled_category: "platforms",
        insole_style_code_shape: "",
        flat_mould_name_shape: "",
        base_board: "paper_board",
        shank_reinforced: false,
        cushioning_type: "eva",
        cushioning_thickness_mm: "3mm",
        socks_covering_type: "matching",
        socks_material_id: "",
        socks_material_name: "",
        socks_color: "",
        surface_detailing: "none",
        embossing: "none",
        embossing_details: "",
        printing: "none",
        printing_details: "",
      },
      sole_spec: {
        sole_material: "TPR",
        sole_type: "ready_made",
        mould_name: "",
        sole_shape: "Round",
        velting: false,
        grinding: false,
        gripping: false,
        attaching_top_piece: false,
        other_processing: "",
        heel_type: "none",
        heel_mould_name: "",
        heel_height: "",
        heel_finish: "none",
        heel_covering_type: "matching",
        heel_covering_material_id: "",
        heel_covering_material_name: "",
      },
    });
    setEditorOpen(true);
  };

  const handleOpenEdit = (sample) => {
    setEditingSample(JSON.parse(JSON.stringify(sample)));
    setEditorOpen(true);
  };

  const handleStatusChange = async (sampleId, newStatus, rejectionReason = "") => {
    if (newStatus === "approved") {
      const target = samples.find(s => (s.id || s._id) === sampleId);
      if (target) {
        setApprovalPromptSample(target);
        return;
      }
    }
    await executeStatusChange(sampleId, newStatus, rejectionReason);
  };

  const executeStatusChange = async (sampleId, newStatus, rejectionReason = "") => {
    setStatusUpdateLoading(true);
    try {
      await http.post(`/samples/${sampleId}/status`, null, {
        params: { status: newStatus, rejection_reason: rejectionReason }
      });
      fetchSamples();
    } catch (err) {
      alert(getErrorMessage(err, "Failed to update status"));
    } finally {
      setStatusUpdateLoading(false);
    }
  };

  const handleDeleteSample = async (sample) => {
    if (!window.confirm(`Are you sure you want to discard / delete sample ${sample.temp_code} (${sample.sample_name})?`)) return;
    try {
      await http.delete(`/samples/${sample.id || sample._id}`);
      fetchSamples();
    } catch (err) {
      alert(getErrorMessage(err, "Failed to delete sample"));
    }
  };

  const handlePrintTechPack = (sample) => {
    setDetailPrintMode(true);
    setDetailSample(sample);
    setTimeout(() => {
      window.print();
    }, 200);
  };

  return (
    <div className="bg-[#F7F7F5] min-h-screen print:bg-white print:min-h-0 print:h-auto print:p-0 print:m-0">
      <div className="print:hidden">
        {/* ── TOP HEADER (SSK ERP PageHeader) ── */}
        <PageHeader
          title="Sample Development & Tracking"
          subtitle="Master / Footwear Sampling Pipeline (R&D & PD Specs)"
          testId="samples-header"
          action={
            <div className="flex items-center gap-2">
              <BtnSecondary onClick={() => fetchSamples()} disabled={loading} title="Refresh sample list">
                <RefreshCw className={`w-3.5 h-3.5 inline mr-1 -mt-0.5 ${loading ? "animate-spin" : ""}`} />
                <span>Refresh</span>
              </BtnSecondary>
              <BtnPrimary onClick={handleOpenCreate} data-testid="new-sample-btn">
                <Plus className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
                <span>New Sample Spec</span>
              </BtnPrimary>
            </div>
          }
        />

        <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1880px] mx-auto">
        {/* ── METRIC / STAT TILES ── */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 sm:gap-4">
          <Card
            onClick={() => setStatusFilter("active")}
            className={`p-3 sm:p-4 relative overflow-hidden cursor-pointer hover:border-slate-900 transition-all ${
              statusFilter === "active" ? "border-slate-900 shadow-ind ring-2 ring-slate-900" : "hover:shadow-sm"
            }`}
          >
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate">Active Pipeline</div>
            <div className="font-mono text-xl sm:text-2xl font-black mt-1.5 text-slate-900">
              {(statusCounts.draft || 0) + (statusCounts.in_sampling || 0) + (statusCounts.sample_ready || 0) + (statusCounts.approved || 0)}
            </div>
            <div className="text-[11px] text-slate-400 font-mono mt-0.5">In Development</div>
            <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#C27842]" />
          </Card>

          {Object.entries(STATUS_CONFIG).map(([key, cfg]) => {
            const count = statusCounts[key] || 0;
            return (
              <Card
                key={key}
                onClick={() => setStatusFilter(key)}
                className={`p-3 sm:p-4 relative overflow-hidden cursor-pointer hover:border-slate-900 transition-all ${
                  statusFilter === key ? "border-slate-900 shadow-ind ring-2 ring-slate-900" : "hover:shadow-sm"
                }`}
              >
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate" title={cfg.label}>
                  {cfg.label}
                </div>
                <div className="font-mono text-xl sm:text-2xl font-black mt-1.5 text-slate-900">
                  {count}
                </div>
                <div className="text-[11px] text-slate-400 font-mono mt-0.5 truncate">
                  {key === "draft" ? "Pending spec" : key === "in_sampling" ? "On workshop floor" : key === "sample_ready" ? "Awaiting review" : key === "approved" ? "Ready for BOM" : key === "transferred_to_style" ? "In Style Master" : "Archived"}
                </div>
                <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: cfg.accent }} />
              </Card>
            );
          })}
        </div>

        {/* ── FILTER & SEARCH BAR ── */}
        <Card className="p-3 sm:p-4 flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative w-full sm:w-96">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by SMP code, name, season..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs font-mono border-2 border-slate-300 bg-white focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto justify-end">
            {/* Pipeline vs Archives Toggle */}
            <div className="inline-flex border-2 border-slate-900 bg-white mr-1">
              <button
                onClick={() => setStatusFilter("active")}
                className={`px-3 py-1 text-xs font-bold uppercase tracking-wider transition-colors ${
                  statusFilter !== "archived" && statusFilter !== "transferred_to_style" && statusFilter !== "rejected"
                    ? "bg-[#0F172A] text-white"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                Active Pipeline ({(statusCounts.draft || 0) + (statusCounts.in_sampling || 0) + (statusCounts.sample_ready || 0) + (statusCounts.approved || 0)})
              </button>
              <button
                onClick={() => setStatusFilter("archived")}
                className={`px-3 py-1 text-xs font-bold uppercase tracking-wider border-l-2 border-slate-900 transition-colors ${
                  statusFilter === "archived" || statusFilter === "transferred_to_style" || statusFilter === "rejected"
                    ? "bg-purple-800 text-white"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                Archives ({(statusCounts.transferred_to_style || 0) + (statusCounts.rejected || 0)})
              </button>
            </div>

            <span className="text-[10px] uppercase tracking-wider font-bold text-slate-500 hidden sm:inline">Profile:</span>
            <div className="inline-flex border-2 border-slate-300 bg-white">
              <button
                onClick={() => setProfileFilter("all")}
                className={`px-3 py-1 text-xs font-bold uppercase tracking-wider transition-colors ${
                  profileFilter === "all" ? "bg-[#0F172A] text-white" : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                All
              </button>
              <button
                onClick={() => setProfileFilter("flat")}
                className={`px-3 py-1 text-xs font-bold uppercase tracking-wider border-l-2 border-slate-300 transition-colors ${
                  profileFilter === "flat" ? "bg-[#0F172A] text-white" : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                🥿 Flats
              </button>
              <button
                onClick={() => setProfileFilter("heeled")}
                className={`px-3 py-1 text-xs font-bold uppercase tracking-wider border-l-2 border-slate-300 transition-colors ${
                  profileFilter === "heeled" ? "bg-[#0F172A] text-white" : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                👠 Heels
              </button>
            </div>

            <BtnSecondary onClick={() => fetchSamples()} className="py-1 px-2.5 text-xs">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </BtnSecondary>
          </div>
        </Card>

        {/* ── SAMPLES GRID ── */}
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-500 font-mono text-sm">
            <RefreshCw className="w-5 h-5 animate-spin mr-2 text-[#C27842]" />
            <span>Loading sample development pipeline...</span>
          </div>
        ) : samples.length === 0 ? (
          <Card className="text-center py-16 p-6 border-2 border-dashed border-slate-300 bg-white">
            <Sparkles className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-base font-bold text-slate-900 uppercase tracking-wide">No sample development records found</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 mb-5">
              Upload reference inspiration photos and capture footwear upper, insole, and sole technical specifications.
            </p>
            <BtnPrimary onClick={handleOpenCreate}>
              <Plus className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
              <span>Create First Sample Spec</span>
            </BtnPrimary>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {samples.map((sample) => (
              <SampleCard
                key={sample.id || sample._id}
                sample={sample}
                onOpenPhotos={() => setPhotoModalSample(sample)}
                onOpenEdit={() => handleOpenEdit(sample)}
                onOpenTransfer={() => setTransferModalSample(sample)}
                onOpenDetail={() => setDetailSample(sample)}
                onPrintTechPack={() => handlePrintTechPack(sample)}
                onOpenPatternYield={() => setPatternYieldModalSample(sample)}
                onStatusChange={handleStatusChange}
                onDelete={handleDeleteSample}
              />
            ))}
          </div>
        )}
        </div>
      </div>

      {/* ── SPEC EDITOR MODAL ── */}
      {editorOpen && editingSample && (
        <SpecEditorModal
          sample={editingSample}
          materials={materials}
          workers={workers}
          onClose={() => {
            setEditorOpen(false);
            setEditingSample(null);
          }}
          onSaved={() => {
            setEditorOpen(false);
            setEditingSample(null);
            fetchSamples();
          }}
        />
      )}

      {/* ── PHOTO GALLERY & UPLOADER MODAL ── */}
      {photoModalSample && (
        <PhotoGalleryModal
          sample={photoModalSample}
          onClose={() => setPhotoModalSample(null)}
          onUpdated={() => {
            fetchSamples();
            http.get(`/samples/${photoModalSample.id || photoModalSample._id}`).then(res => {
              setPhotoModalSample(res.data);
            });
          }}
        />
      )}

      {/* ── TRANSFER TO STYLE MASTER MODAL ── */}
      {transferModalSample && (
        <TransferToStyleModal
          sample={transferModalSample}
          onClose={() => setTransferModalSample(null)}
          onSuccess={(styleCode) => {
            setTransferModalSample(null);
            fetchSamples();
            alert(`Sample successfully transferred to Style Master with code: ${styleCode}! You can now view and edit it in Styles Master.`);
          }}
        />
      )}

      {/* ── DETAIL VIEW & PRINT TECH PACK MODAL ── */}
      {detailSample && (
        <DetailViewModal
          sample={detailSample}
          initialViewMode={detailPrintMode ? "print_sheet" : "screen"}
          onClose={() => {
            setDetailSample(null);
            setDetailPrintMode(false);
          }}
          onOpenEdit={() => {
            const s = detailSample;
            setDetailSample(null);
            setDetailPrintMode(false);
            handleOpenEdit(s);
          }}
          onOpenTransfer={() => {
            const s = detailSample;
            setDetailSample(null);
            setDetailPrintMode(false);
            setTransferModalSample(s);
          }}
          onOpenPhotos={() => {
            const s = detailSample;
            setDetailSample(null);
            setDetailPrintMode(false);
            setPhotoModalSample(s);
          }}
          onOpenPatternYield={() => {
            const s = detailSample;
            setDetailSample(null);
            setDetailPrintMode(false);
            setPatternYieldModalSample(s);
          }}
        />
      )}

      {/* ── PATTERN SCANNER & 2D YIELD CALCULATION MODAL ── */}
      {patternYieldModalSample && (
        <PatternYieldModal
          sample={patternYieldModalSample}
          materials={materials}
          onClose={() => setPatternYieldModalSample(null)}
          onSaved={() => {
            fetchSamples();
          }}
          onOpenTransfer={() => {
            const s = patternYieldModalSample;
            setPatternYieldModalSample(null);
            setTransferModalSample(s);
          }}
        />
      )}

      {/* ── SAMPLE APPROVAL & YIELD CALCULATION PROMPT MODAL ── */}
      {approvalPromptSample && (
        <div className="fixed inset-0 z-50 bg-slate-900/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-[#F7F7F5] border-2 border-slate-900 shadow-ind-xl max-w-lg w-full p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 bg-emerald-100 border border-emerald-400 flex items-center justify-center text-emerald-800 shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-base uppercase text-slate-900">
                  Sample Approved for Production!
                </h3>
                <p className="text-xs text-slate-600 mt-1">
                  <strong>{approvalPromptSample.temp_code}</strong> ({approvalPromptSample.sample_name}) will be updated to <strong>Approved</strong>.
                </p>
              </div>
            </div>

            <div className="bg-amber-50 border border-amber-300 p-3.5 text-xs text-amber-900 space-y-1.5">
              <p className="font-bold uppercase tracking-wide flex items-center gap-1.5">
                <Scan className="w-4 h-4 text-[#C27842]" />
                <span>Calculate Precise BOM Yields with A4 Scanner?</span>
              </p>
              <p className="text-amber-800">
                You can now scan upper patterns on an A4 scanner to extract true 1:1 scale surface area and run 2D roll nesting to determine exact raw material consumption (meters/pair) before generating the Style Master BOM.
              </p>
            </div>

            <div className="space-y-2 pt-2">
              <button
                onClick={async () => {
                  const s = approvalPromptSample;
                  await executeStatusChange(s.id || s._id, "approved");
                  setApprovalPromptSample(null);
                  setPatternYieldModalSample(s);
                }}
                className="w-full bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase tracking-wider text-xs py-2.5 px-4 border-2 border-[#C27842] shadow-ind flex items-center justify-center gap-2"
              >
                <Scan className="w-4 h-4" />
                <span>Scan Pattern & Calculate Yield (Recommended)</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={async () => {
                    const s = approvalPromptSample;
                    await executeStatusChange(s.id || s._id, "approved");
                    setApprovalPromptSample(null);
                  }}
                  className="flex-1 bg-white hover:bg-slate-100 text-slate-700 font-bold uppercase tracking-wider text-xs py-2 px-3 border-2 border-slate-300"
                >
                  Approve with Standard Estimates
                </button>

                <button
                  onClick={() => setApprovalPromptSample(null)}
                  className="px-3 py-2 text-xs font-bold uppercase text-slate-500 hover:text-slate-900"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────────
   SAMPLE CARD (With Interactive Multi-Photo Carousel)
   ───────────────────────────────────────────────────────────────────────────── */
function SampleCard({ sample, onOpenPhotos, onOpenEdit, onOpenTransfer, onOpenDetail, onPrintTechPack, onOpenPatternYield, onStatusChange, onDelete }) {
  const sid = sample.id || sample._id;
  const cfg = STATUS_CONFIG[sample.status] || STATUS_CONFIG.draft;
  const upper = sample.upper_spec || {};
  const insole = sample.insole_spec || {};
  const sole = sample.sole_spec || {};

  const photos = sample.inspiration_photos || [];
  const [photoIdx, setPhotoIdx] = useState(0);

  // Default to primary photo if available
  useEffect(() => {
    if (photos.length > 0) {
      const pIdx = photos.findIndex(p => p.is_primary);
      setPhotoIdx(pIdx >= 0 ? pIdx : 0);
    }
  }, [photos]);

  const currentPhoto = photos[photoIdx] || photos[0];

  const handlePrevPhoto = (e) => {
    e.stopPropagation();
    setPhotoIdx(prev => (prev === 0 ? photos.length - 1 : prev - 1));
  };

  const handleNextPhoto = (e) => {
    e.stopPropagation();
    setPhotoIdx(prev => (prev === photos.length - 1 ? 0 : prev + 1));
  };

  return (
    <Card className="flex flex-col relative hover:border-slate-900 hover:shadow-ind transition-all overflow-hidden group">
      {/* PHOTO HEADER: Side-by-Side Comparison when Archived with Actual Photo, else Carousel */}
      <div className="relative h-52 bg-slate-100 border-b-2 border-slate-200 flex items-center justify-center overflow-hidden">
        {sample.actual_developed_photo_url ? (
          <div className="w-full h-full grid grid-cols-2 divide-x-2 divide-slate-900">
            <div className="relative h-full overflow-hidden bg-slate-50">
              {currentPhoto?.url ? (
                <SafeImage src={currentPhoto.url} alt="Inspiration" className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-[10px] text-slate-400 font-mono">No Insp. Photo</div>
              )}
              <span className="absolute bottom-1.5 left-1.5 bg-slate-900/80 text-white text-[9px] font-mono uppercase px-1.5 py-0.5 font-bold">
                Inspiration
              </span>
            </div>
            <div className="relative h-full overflow-hidden bg-emerald-50/30">
              <SafeImage src={sample.actual_developed_photo_url} alt="Actual Developed" className="w-full h-full object-cover" />
              <span className="absolute bottom-1.5 right-1.5 bg-emerald-700/90 text-white text-[9px] font-mono uppercase px-1.5 py-0.5 font-bold">
                Actual Approved
              </span>
            </div>
          </div>
        ) : currentPhoto?.url ? (
          <SafeImage
            src={currentPhoto.url}
            alt={sample.sample_name}
            className="w-full h-full object-cover transition duration-300 group-hover:scale-[1.02]"
          />
        ) : (
          <div
            onClick={onOpenPhotos}
            className="flex flex-col items-center justify-center text-slate-400 cursor-pointer hover:text-slate-800 transition p-4 text-center"
          >
            <Camera className="w-10 h-10 opacity-30 mb-1" />
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">No photos uploaded</span>
            <span className="text-[11px] text-[#C27842] font-semibold underline mt-0.5">+ Click to upload photos</span>
          </div>
        )}

        {/* Carousel Navigation Arrows */}
        {photos.length > 1 && (
          <>
            <button
              onClick={handlePrevPhoto}
              className="absolute left-2 top-1/2 -translate-y-1/2 p-1.5 bg-[#0F172A]/80 hover:bg-[#0F172A] text-white border border-slate-700 shadow-sm transition z-10"
              title="Previous photo"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <button
              onClick={handleNextPhoto}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 bg-[#0F172A]/80 hover:bg-[#0F172A] text-white border border-slate-700 shadow-sm transition z-10"
              title="Next photo"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </>
        )}

        {/* Temporary Code Badge */}
        <div className="absolute top-2.5 left-2.5 bg-[#0F172A] text-white px-2 py-0.5 text-xs font-mono font-bold tracking-wider border border-[#0F172A] shadow-ind flex items-center gap-1.5 z-10">
          <span className="w-1.5 h-1.5 bg-amber-400" />
          <span>{sample.temp_code}</span>
        </div>

        {/* Status Badge */}
        <div className="absolute top-2.5 right-2.5 z-10">
          <Badge color={cfg.badgeColor}>{cfg.label}</Badge>
        </div>

        {/* Profile Indicator */}
        <div className="absolute bottom-2.5 left-2.5 z-10">
          <Badge color={sample.profile === "heeled" ? "purple" : "slate"}>
            {sample.profile === "heeled" ? "👠 Heeled" : "🥿 Flat"}
          </Badge>
        </div>

        {/* Photos Count & Quick Upload Button */}
        <button
          onClick={onOpenPhotos}
          className="absolute bottom-2.5 right-2.5 bg-white text-slate-900 text-xs px-2.5 py-1 border-2 border-slate-300 hover:border-slate-900 flex items-center gap-1.5 font-bold uppercase tracking-wider shadow-sm transition z-10"
          title="Upload or view inspiration photos"
        >
          <Camera className="w-3.5 h-3.5 text-[#C27842]" />
          <span className="font-mono">{photos.length}</span>
          <span className="text-[10px] text-slate-500 font-semibold">+ Add</span>
        </button>

        {/* Thumbnail Carousel Dots */}
        {photos.length > 1 && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-black/60 px-2 py-0.5 z-10">
            {photos.map((p, idx) => (
              <span
                key={p.photo_id || idx}
                onClick={(e) => {
                  e.stopPropagation();
                  setPhotoIdx(idx);
                }}
                className={`w-1.5 h-1.5 cursor-pointer transition ${idx === photoIdx ? "bg-amber-400 scale-125" : "bg-white/40"}`}
              />
            ))}
          </div>
        )}
      </div>

      {/* CARD BODY */}
      <div className="p-4 flex-1 flex flex-col justify-between space-y-3 bg-white">
        <div>
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-bold text-base text-slate-900 leading-tight truncate" title={sample.sample_name}>
              {sample.sample_name}
            </h3>
            {sample.season && (
              <span className="text-[10px] font-mono uppercase bg-slate-100 border border-slate-300 px-1.5 py-0.5 text-slate-700 font-bold shrink-0">
                {sample.season}
              </span>
            )}
          </div>

          {sample.transferred_style_code && (
            <div className="mt-1.5 inline-flex items-center gap-1.5 px-2 py-0.5 bg-purple-50 border border-purple-300 text-purple-800 text-[11px] font-mono font-bold uppercase">
              <span>ERP Style:</span>
              <span className="underline font-black">{sample.transferred_style_code}</span>
            </div>
          )}

          {/* Development Timeline (shown for Archived / Transferred samples) */}
          {(sample.status === "transferred_to_style" || sample.status === "rejected" || (Array.isArray(sample.timeline) && sample.timeline.length > 0)) && (
            <div className="mt-2 p-2 bg-slate-50 border border-slate-200 rounded space-y-1">
              <span className="text-[9px] font-mono font-bold uppercase tracking-wider text-slate-500 block">
                Development Timeline
              </span>
              <div className="space-y-0.5">
                {(Array.isArray(sample.timeline) && sample.timeline.length > 0
                  ? sample.timeline
                  : [
                      ...(sample.created_at ? [{ label: "Draft Created", timestamp: sample.created_at }] : []),
                      ...(sample.transferred_at ? [{ label: `Transferred (${sample.transferred_style_code || "Style"})`, timestamp: sample.transferred_at }] : []),
                    ]
                ).map((ev, eIdx) => (
                  <div key={eIdx} className="flex items-center justify-between text-[10px] font-mono text-slate-700">
                    <span className="truncate pr-2 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-purple-600 shrink-0" />
                      <span>{ev.label}</span>
                    </span>
                    <span className="text-slate-500 shrink-0">
                      {ev.timestamp ? new Date(ev.timestamp).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" }) : ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {sample.yield_spec && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-50 border border-emerald-300 text-emerald-800 text-[11px] font-mono font-bold">
                <Scan className="w-3.5 h-3.5 text-emerald-600" />
                <span>Yield: {sample.yield_spec.yield_per_unit} prs/{sample.yield_spec.consumption_unit === "sheet" ? "sht" : "m"}</span>
                <span className="text-emerald-700 font-semibold">({sample.yield_spec.consumption_per_pair} {sample.yield_spec.consumption_unit}/pr)</span>
              </span>
            </div>
          )}

          {/* 3 Foundation Specifications */}
          <div className="mt-3 space-y-2 text-xs border-t-2 border-slate-100 pt-2.5">
            {/* Upper Pillar */}
            <div className="flex items-start gap-1.5 text-xs">
              <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider shrink-0 w-16">Upper:</span>
              <div className="flex-1 min-w-0">
                <span className="text-slate-800 truncate font-mono text-[11px] block">
                  {Array.isArray(upper.materials) && upper.materials.length > 0 ? (
                    upper.materials.map(m => `${m.material_name || "Material"} (${m.placement || "Primary"}${m.color_to_develop ? `: ${m.color_to_develop}` : ""})`).join(" · ")
                  ) : (
                    <>
                      {upper.upper_top_material_name || "Material not chosen"}
                      {upper.upper_color_to_develop ? ` (${upper.upper_color_to_develop})` : ""}
                    </>
                  )}
                  {" · "}
                  <span className="capitalize">{upper.cutting_operation?.replace("_", " ")}</span>
                  {upper.has_buckle ? " · Buckle" : ""}
                </span>
                {/* Swatches preview if any upper material or buckle has photo */}
                {((Array.isArray(upper.materials) && upper.materials.some(m => m.photo_url)) || upper.buckle_photo_url) && (
                  <div className="flex items-center gap-1 mt-1">
                    {upper.materials?.filter(m => m.photo_url).map((m, mIdx) => (
                      <div key={mIdx} className="w-5 h-5 rounded border border-slate-300 overflow-hidden shrink-0 shadow-xs" title={`${m.placement || "Upper"}: ${m.material_name || ""}`}>
                        <SafeImage src={m.photo_url} alt="Swatch" className="w-full h-full object-cover" />
                      </div>
                    ))}
                    {upper.buckle_photo_url && (
                      <div className="w-5 h-5 rounded border border-amber-300 overflow-hidden shrink-0 shadow-xs" title={`Buckle: ${upper.buckle_spec || ""}`}>
                        <SafeImage src={upper.buckle_photo_url} alt="Buckle" className="w-full h-full object-cover" />
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Insole Pillar */}
            <div className="flex items-start gap-1.5 text-xs">
              <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider shrink-0 w-16">Insole:</span>
              <span className="text-slate-800 truncate font-mono text-[11px]">
                {insole.base_board === "cellulose_board" ? "Cellulose" : "Paper Board"}
                {" + "}
                {insole.cushioning_type?.toUpperCase()} {insole.cushioning_thickness_mm}
                {" · "}
                {insole.socks_covering_type === "matching" ? "Matching Socks" : (insole.socks_material_name || "Custom Socks")}
                {insole.socks_color ? ` (${insole.socks_color})` : ""}
                {insole.embossing && insole.embossing !== "none" ? ` · ${insole.embossing}` : ""}
              </span>
            </div>

            {/* Sole Pillar */}
            <div className="flex items-start gap-1.5 text-xs">
              <span className="font-bold text-[10px] uppercase text-slate-500 tracking-wider shrink-0 w-16">Sole:</span>
              <span className="text-slate-800 truncate font-mono text-[11px]">
                {sole.sole_material || "TPR"}
                {sole.mould_name ? ` (${sole.mould_name})` : ""}
                {sample.profile === "heeled" && sole.heel_type !== "none" ? ` · Heel: ${sole.heel_type} (${sole.heel_finish})` : ""}
                {sole.velting ? " · Welting" : ""}
              </span>
            </div>
          </div>
        </div>

        {/* CARD ACTIONS */}
        <div className="border-t-2 border-slate-100 pt-3 space-y-2">
          {/* Primary Workflow Button */}
          {sample.status !== "transferred_to_style" && sample.status !== "rejected" ? (
            <button
              onClick={onOpenTransfer}
              className="w-full bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase tracking-wider text-xs py-2 px-3 border-2 border-[#C27842] shadow-ind hover:shadow-ind-lg transition-all flex items-center justify-center gap-1.5 active:shadow-none"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Transfer to Style Master (Generate BOM)</span>
              <ArrowRight className="w-3.5 h-3.5 ml-0.5" />
            </button>
          ) : sample.status === "transferred_to_style" ? (
            <div className="w-full bg-purple-50 border-2 border-purple-300 text-purple-800 font-bold uppercase tracking-wider text-xs py-1.5 px-3 text-center flex items-center justify-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-purple-700" />
              <span>Style Master Active ({sample.transferred_style_code})</span>
            </div>
          ) : (
            <div className="w-full bg-rose-50 border-2 border-rose-300 text-rose-800 font-bold uppercase tracking-wider text-xs py-1.5 px-3 text-center">
              Discarded / Rejected
            </div>
          )}

          {/* Secondary Actions */}
          <div className="flex items-center justify-between text-xs pt-1">
            <div className="flex items-center gap-2">
              <button
                onClick={onOpenEdit}
                className="text-xs font-bold uppercase tracking-wider text-slate-800 hover:text-[#C27842] hover:underline"
              >
                Edit Specs
              </button>
              <span className="text-slate-300">|</span>
              <button
                onClick={onOpenDetail}
                className="text-xs font-bold uppercase tracking-wider text-slate-500 hover:text-slate-900 hover:underline"
              >
                Tech Pack
              </button>
              <span className="text-slate-300">|</span>
              <button
                onClick={onPrintTechPack}
                className="text-xs font-bold uppercase tracking-wider text-[#C27842] hover:underline flex items-center gap-1"
                title="Print Tech Pack for Designer (80% Image Sheet)"
              >
                <Printer className="w-3 h-3" />
                <span>Print</span>
              </button>
              <span className="text-slate-300">|</span>
              {(() => {
                const isYieldActive = ["sample_ready", "approved", "transferred_to_style"].includes(sample.status);
                const hasCalculatedYield = Boolean(sample.yield_spec?.consumption_per_pair);
                if (isYieldActive) {
                  return (
                    <button
                      onClick={onOpenPatternYield}
                      className={`text-xs font-bold uppercase tracking-wider flex items-center gap-1 transition ${
                        hasCalculatedYield
                          ? "text-emerald-700 hover:text-emerald-900 font-extrabold"
                          : "text-indigo-700 hover:text-indigo-900 hover:underline"
                      }`}
                      title="A4 Pattern Scanner & 2D Yield Engine (Active - Sample Ready)"
                    >
                      <Scan className="w-3 h-3" />
                      <span>Yield {hasCalculatedYield ? "✓" : ""}</span>
                    </button>
                  );
                }
                return (
                  <button
                    disabled
                    className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1 cursor-not-allowed opacity-50"
                    title={`Yield calculation unlocks after sample is marked as 'Sample Ready' (current status: ${sample.status || 'draft'})`}
                  >
                    <Lock className="w-3 h-3" />
                    <span>Yield</span>
                  </button>
                );
              })()}
            </div>

            {sample.status !== "transferred_to_style" && (
              <div className="flex items-center gap-1">
                {sample.status === "draft" && (
                  <button
                    onClick={() => onStatusChange(sid, "in_sampling")}
                    className="px-2 py-0.5 border border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100 text-[10px] font-bold uppercase tracking-wider transition"
                  >
                    Start Sampling
                  </button>
                )}
                {sample.status === "in_sampling" && (
                  <button
                    onClick={() => onStatusChange(sid, "sample_ready")}
                    className="px-2 py-0.5 border border-blue-400 bg-blue-50 text-blue-800 hover:bg-blue-100 text-[10px] font-bold uppercase tracking-wider transition"
                  >
                    Sample Ready
                  </button>
                )}
                {sample.status === "sample_ready" && (
                  <button
                    onClick={() => onStatusChange(sid, "approved")}
                    className="px-2 py-0.5 border border-emerald-400 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 text-[10px] font-bold uppercase tracking-wider transition"
                  >
                    Approve
                  </button>
                )}
                <button
                  onClick={() => onDelete(sample)}
                  className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 transition border border-transparent hover:border-red-200"
                  title="Discard / Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}


/* ─────────────────────────────────────────────────────────────────────────────
   MODAL 1: SPECIFICATION EDITOR (WITH DIRECT MULTI-PHOTO UPLOAD ZONE)
   ───────────────────────────────────────────────────────────────────────────── */
function SpecEditorModal({ sample, materials, workers, onClose, onSaved }) {
  const isNew = !sample.id && !sample._id;
  const sid = sample.id || sample._id;
  const [formData, setFormData] = useState(() => {
    const copy = JSON.parse(JSON.stringify(sample));
    if (!copy.upper_spec) copy.upper_spec = {};
    if (!Array.isArray(copy.upper_spec.materials) || copy.upper_spec.materials.length === 0) {
      const topId = copy.upper_spec.upper_top_material_id || "";
      const matchedMat = materials.find(m => (m.id || m._id) === topId);
      copy.upper_spec.materials = [
        {
          material_id: topId,
          material_name: copy.upper_spec.upper_top_material_name || (matchedMat ? matchedMat.name : ""),
          material_code: copy.upper_spec.upper_top_material_code || (matchedMat ? matchedMat.code : ""),
          color_to_develop: copy.upper_spec.upper_color_to_develop || "",
          placement: "Primary",
          photo_url: matchedMat ? (matchedMat.image_url || matchedMat.image_thumbnail_url || "") : ""
        }
      ];
    }
    return copy;
  });
  const [activeTab, setActiveTab] = useState("upper");
  const [saving, setSaving] = useState(false);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const multiFileInputRef = useRef(null);

  const addUpperMaterial = () => {
    setFormData(prev => {
      const currentList = prev.upper_spec?.materials || [];
      const nextPlacement = currentList.length === 1 ? "Secondary" : currentList.length === 2 ? "Strap" : "Trim / Accent";
      const updated = [
        ...currentList,
        {
          material_id: "",
          material_name: "",
          material_code: "",
          color_to_develop: "",
          placement: nextPlacement,
          photo_url: ""
        }
      ];
      return {
        ...prev,
        upper_spec: {
          ...prev.upper_spec,
          materials: updated
        }
      };
    });
  };

  const removeUpperMaterial = (indexToRemove) => {
    setFormData(prev => {
      const currentList = prev.upper_spec?.materials || [];
      const updated = currentList.filter((_, idx) => idx !== indexToRemove);
      const first = updated[0] || {};
      return {
        ...prev,
        upper_spec: {
          ...prev.upper_spec,
          materials: updated,
          upper_top_material_id: first.material_id || "",
          upper_top_material_name: first.material_name || "",
          upper_top_material_code: first.material_code || "",
          upper_color_to_develop: first.color_to_develop || ""
        }
      };
    });
  };

  const updateUpperMaterialItem = (index, field, value) => {
    setFormData(prev => {
      const currentList = [...(prev.upper_spec?.materials || [])];
      if (!currentList[index]) return prev;
      currentList[index] = { ...currentList[index], [field]: value };
      const first = currentList[0] || {};
      return {
        ...prev,
        upper_spec: {
          ...prev.upper_spec,
          materials: currentList,
          upper_top_material_id: first.material_id || "",
          upper_top_material_name: first.material_name || "",
          upper_top_material_code: first.material_code || "",
          upper_color_to_develop: first.color_to_develop || ""
        }
      };
    });
  };

  const uploadCustomPhoto = async (file, onUploaded) => {
    if (!file) return;
    try {
      const upData = new FormData();
      upData.append("files", file);
      const res = await http.post("/samples/upload-photos", upData);
      const url = res.data?.photos?.[0]?.url;
      if (url) {
        onUploaded(url);
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to upload photo"));
    }
  };

  const updateUpper = (field, val) => {
    setFormData(prev => ({
      ...prev,
      upper_spec: { ...prev.upper_spec, [field]: val }
    }));
  };

  const updateInsole = (field, val) => {
    setFormData(prev => ({
      ...prev,
      insole_spec: { ...prev.insole_spec, [field]: val }
    }));
  };

  const updateSole = (field, val) => {
    setFormData(prev => ({
      ...prev,
      sole_spec: { ...prev.sole_spec, [field]: val }
    }));
  };

  // MULTI-PHOTO UPLOAD HANDLER
  const handleMultiPhotoUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setUploadingPhotos(true);
    const uploadData = new FormData();
    files.forEach(f => {
      uploadData.append("files", f);
    });

    try {
      if (sid) {
        // Upload directly to existing sample
        const res = await http.post(`/samples/${sid}/photos`, uploadData);
        setFormData(prev => ({
          ...prev,
          inspiration_photos: res.data.sample?.inspiration_photos || [...(prev.inspiration_photos || []), ...(res.data.photos || [])]
        }));
      } else {
        // Staging upload for new sample
        const res = await http.post("/samples/upload-photos", uploadData);
        const newPhotos = res.data.photos || [];
        setFormData(prev => {
          const existing = prev.inspiration_photos || [];
          if (!existing.some(p => p.is_primary) && newPhotos.length > 0) {
            newPhotos[0].is_primary = true;
          }
          return {
            ...prev,
            inspiration_photos: [...existing, ...newPhotos]
          };
        });
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to upload inspiration photos"));
    } finally {
      setUploadingPhotos(false);
      if (multiFileInputRef.current) multiFileInputRef.current.value = "";
    }
  };

  const handleSetPrimaryPhoto = (photoId) => {
    setFormData(prev => ({
      ...prev,
      inspiration_photos: (prev.inspiration_photos || []).map(p => ({
        ...p,
        is_primary: p.photo_id === photoId
      }))
    }));
  };

  const handleRemovePhoto = (photoId) => {
    setFormData(prev => {
      const remaining = (prev.inspiration_photos || []).filter(p => p.photo_id !== photoId);
      if (remaining.length > 0 && !remaining.some(p => p.is_primary)) {
        remaining[0].is_primary = true;
      }
      return { ...prev, inspiration_photos: remaining };
    });
  };

  const handleUpdateCaption = (photoId, newCaption) => {
    setFormData(prev => ({
      ...prev,
      inspiration_photos: (prev.inspiration_photos || []).map(p =>
        p.photo_id === photoId ? { ...p, caption: newCaption } : p
      )
    }));
  };

  const handleSave = async () => {
    if (!formData.sample_name || !formData.sample_name.trim()) {
      alert("Please enter a Sample Name");
      return;
    }
    setSaving(true);
    try {
      if (isNew) {
        await http.post("/samples", formData);
      } else {
        await http.patch(`/samples/${sid}`, formData);
      }
      onSaved();
    } catch (err) {
      alert(getErrorMessage(err, "Failed to save sample specification"));
    } finally {
      setSaving(false);
    }
  };

  const photos = formData.inspiration_photos || [];

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-2 sm:p-4 md:p-6 overflow-y-auto">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-5xl xl:max-w-6xl h-[94vh] max-h-[94vh] flex flex-col overflow-hidden">
        {/* MODAL HEADER */}
        <div className="px-5 py-4 border-b-2 border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">SSK / Sample R&D Technical Specification</div>
            <h2 className="text-lg font-black tracking-tight text-slate-900">
              {isNew ? "Create Sample Development Spec" : `Edit Sample Spec — ${sample.temp_code}`}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 text-slate-500 hover:text-slate-900">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* BASIC ATTRIBUTES STRIP */}
        <div className="px-5 py-4 border-b-2 border-slate-200 bg-slate-50 grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Sample Name *</label>
            <input
              type="text"
              placeholder="e.g. Strappy Block Heel Sandal"
              value={formData.sample_name}
              onChange={(e) => setFormData(prev => ({ ...prev, sample_name: e.target.value }))}
              className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Footwear Profile</label>
            <select
              value={formData.profile}
              onChange={(e) => {
                const val = e.target.value;
                setFormData(prev => ({
                  ...prev,
                  profile: val,
                  insole_spec: { ...prev.insole_spec, profile_type: val }
                }));
              }}
              className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-bold focus:border-[#2563EB] focus:outline-none"
            >
              <option value="flat">🥿 Flat Footwear</option>
              <option value="heeled">👠 Heeled Footwear</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Season / Collection</label>
            <input
              type="text"
              placeholder="e.g. SS26, Festive 2026"
              value={formData.season || ""}
              onChange={(e) => setFormData(prev => ({ ...prev, season: e.target.value }))}
              className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Assigned Karigar / Tech</label>
            <SearchableSelect
              options={[{ id: "", name: "-- Unassigned --", role: "" }, ...workers]}
              value={formData.assigned_karigar_id || ""}
              getKey={(w) => w.id || w._id || ""}
              getLabel={(w) => (w.id || w._id) ? `${w.name} (${w.role || "Karigar"})` : "-- Unassigned --"}
              placeholder="Search or pick karigar..."
              inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
              onChange={(wid) => {
                const worker = workers.find(w => (w.id || w._id) === wid);
                setFormData(prev => ({
                  ...prev,
                  assigned_karigar_id: wid,
                  assigned_karigar_name: worker ? worker.name : ""
                }));
              }}
            />
          </div>
        </div>

        {/* ── DEDICATED MULTI-PHOTO UPLOAD SECTION ── */}
        <div className="px-5 py-2.5 border-b-2 border-slate-200 bg-white space-y-2 shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-700">Sample Inspiration Photos</span>
              <span className="font-mono text-[10px] font-bold bg-[#0F172A] text-white px-2 py-0.5">
                {photos.length} UPLOADED
              </span>
              <span className="text-[10px] text-slate-400 font-mono hidden md:inline">
                &bull; uploads/samples_inspiration/
              </span>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="file"
                ref={multiFileInputRef}
                onChange={handleMultiPhotoUpload}
                multiple
                accept="image/*"
                className="hidden"
              />
              <BtnSecondary
                type="button"
                onClick={() => multiFileInputRef.current?.click()}
                disabled={uploadingPhotos}
                className="text-xs py-1 px-3"
              >
                {uploadingPhotos ? <RefreshCw className="w-3.5 h-3.5 inline mr-1 animate-spin" /> : <ImagePlus className="w-3.5 h-3.5 inline mr-1" />}
                <span>{uploadingPhotos ? "Uploading..." : "+ Upload Photos"}</span>
              </BtnSecondary>
            </div>
          </div>

          {/* PHOTO THUMBNAILS GALLERY */}
          {photos.length === 0 ? (
            <div
              onClick={() => multiFileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-300 hover:border-slate-900 rounded py-2 px-3 flex items-center justify-between cursor-pointer bg-slate-50/70 hover:bg-slate-100 transition group"
            >
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 bg-white border border-slate-300 rounded group-hover:border-slate-900">
                  <Camera className="w-4 h-4 text-slate-500 group-hover:text-slate-900" />
                </div>
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-800 group-hover:text-slate-900 block">
                    Click to browse or drop inspiration photos (Front, Side, Heel, Sole, Buckle)
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    PNG, JPG, WEBP &bull; Select multiple files at once
                  </span>
                </div>
              </div>
              <span className="text-[11px] font-bold text-blue-600 bg-blue-50 border border-blue-200 px-2.5 py-1 rounded">
                + Browse Files
              </span>
            </div>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-6 md:grid-cols-8 gap-2 pt-0.5">
              {photos.map((photo, pIdx) => (
                <div
                  key={photo.photo_id || pIdx}
                  className={`group relative border-2 overflow-hidden bg-white shadow-xs flex flex-col ${
                    photo.is_primary ? "border-amber-500 shadow-ind ring-1 ring-amber-400" : "border-slate-200"
                  }`}
                >
                  <div className="h-16 bg-slate-100 flex items-center justify-center overflow-hidden relative">
                    <SafeImage src={photo.url} alt="Inspiration" className="w-full h-full object-cover" />
                    {photo.is_primary && (
                      <span className="absolute top-0.5 left-0.5 z-10">
                        <Badge color="yellow">COVER</Badge>
                      </span>
                    )}
                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition flex items-center justify-center gap-1 p-1 z-10">
                      {!photo.is_primary && (
                        <button
                          type="button"
                          onClick={() => handleSetPrimaryPhoto(photo.photo_id)}
                          className="p-1 bg-amber-500 hover:bg-amber-600 text-white text-[9px] font-bold uppercase"
                          title="Make Primary Cover Photo"
                        >
                          <Star className="w-2.5 h-2.5" />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleRemovePhoto(photo.photo_id)}
                        className="p-1 bg-red-600 hover:bg-red-700 text-white text-[9px]"
                        title="Delete photo"
                      >
                        <Trash2 className="w-2.5 h-2.5" />
                      </button>
                    </div>
                  </div>
                  <input
                    type="text"
                    placeholder="Caption..."
                    value={photo.caption || ""}
                    onChange={(e) => handleUpdateCaption(photo.photo_id, e.target.value)}
                    className="p-0.5 text-[9px] font-mono border-t border-slate-200 bg-white focus:outline-none truncate"
                  />
                </div>
              ))}
              <button
                type="button"
                onClick={() => multiFileInputRef.current?.click()}
                disabled={uploadingPhotos}
                className="h-full min-h-[64px] border-2 border-dashed border-slate-300 hover:border-slate-900 flex flex-col items-center justify-center text-slate-500 hover:text-slate-900 text-[9px] font-bold uppercase tracking-wider transition bg-slate-50"
              >
                <Plus className="w-4 h-4 mb-0.5 opacity-60" />
                <span>+ More</span>
              </button>
            </div>
          )}
        </div>

        {/* PILLAR TABS */}
        <div className="flex items-center gap-1 border-b-2 border-slate-200 bg-slate-100 px-5 pt-2">
          {[
            { id: "upper", label: "1. Upper Component", icon: Scissors },
            { id: "insole", label: "2. Insole / Socks", icon: Layers },
            { id: "sole", label: "3. Sole & Heel", icon: Hammer },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider flex items-center gap-2 transition-all ${
                activeTab === tab.id
                  ? "bg-white border-t-2 border-l-2 border-r-2 border-slate-900 text-slate-900 -mb-[2px] z-10"
                  : "text-slate-600 hover:text-slate-900 border-b-2 border-transparent hover:border-slate-300"
              }`}
            >
              <tab.icon className="w-3.5 h-3.5 text-[#C27842]" />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* TAB CONTENTS (SCROLLABLE) */}
        <div className="p-4 md:p-6 overflow-y-auto flex-1 space-y-4 text-xs bg-white">
          {/* ──────────────── TAB 1: UPPER SPEC ──────────────── */}
          {activeTab === "upper" && (
            <div className="space-y-4">
              {/* Dynamic Upper Top Materials (Full Width - Generous space for 1, 2, 3+ materials) */}
              <div className="border-2 border-slate-200 p-4 bg-slate-50/70 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                  <div className="flex items-center gap-2">
                    <Palette className="w-4 h-4 text-[#C27842]" />
                    <span className="font-bold text-xs uppercase tracking-wider text-slate-900">
                      Upper Top Materials ({formData.upper_spec?.materials?.length || 1} Types)
                    </span>
                    <span className="text-[11px] text-slate-500 hidden sm:inline">
                      &bull; Multi-material footwear (Primary, Straps, Accents, Trims)
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={addUpperMaterial}
                    className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 shadow-sm transition"
                    title="Add another upper material (Secondary, Strap, Accent, Trim)"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Upper Material</span>
                  </button>
                </div>

                <div className="space-y-3">
                  {(formData.upper_spec?.materials || []).map((mat, idx) => (
                    <div key={idx} className="p-3.5 bg-white border-2 border-slate-200 rounded shadow-xs space-y-2.5">
                      {/* Material Card Top Bar */}
                      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] font-bold uppercase bg-slate-900 text-white px-2 py-0.5">
                            Material #{idx + 1}
                          </span>
                          <span className="text-slate-400 text-xs">&bull;</span>
                          <span className="text-[10px] font-bold uppercase text-slate-500 tracking-wider">Placement / Role:</span>
                          <input
                            type="text"
                            value={mat.placement || (idx === 0 ? "Primary" : "Secondary")}
                            onChange={(e) => updateUpperMaterialItem(idx, "placement", e.target.value)}
                            placeholder="e.g. Primary, Secondary, Strap, Vamp, Trim, Accent"
                            className="text-xs font-bold text-slate-900 border-b-2 border-dashed border-slate-400 hover:border-slate-900 focus:border-[#2563EB] outline-none px-1.5 py-0.5 w-48 bg-slate-50"
                            title="Click to edit placement label (e.g. Primary, Strap, Trim, Vamp)"
                          />
                        </div>

                        {formData.upper_spec?.materials?.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeUpperMaterial(idx)}
                            className="inline-flex items-center gap-1 text-[11px] text-red-600 hover:text-red-800 font-bold px-2 py-0.5 hover:bg-red-50 border border-transparent hover:border-red-200 transition"
                            title="Remove this upper material"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Remove</span>
                          </button>
                        )}
                      </div>

                      {/* Material Selection and Color Fields - Generous 12-Column Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-12 gap-3.5 items-start">
                        <div className="md:col-span-7">
                          <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 block mb-1">
                            Select from Material Master:
                          </label>
                          <SearchableSelect
                            options={[{ id: "", name: "-- Select Material --", code: "" }, ...materials]}
                            value={mat.material_id || ""}
                            getKey={(m) => m.id || m._id || ""}
                            getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}] - ₹${m.rate || 0}/${m.unit || ""} (${m.category || ""})` : "-- Select Material --"}
                            placeholder="Search material by name or code..."
                            inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                            renderOption={(m) => (
                              <div className="flex items-center gap-2 py-0.5">
                                {(m.image_url || m.image_thumbnail_url) && (
                                  <img
                                    src={resolveImageUrl(m.image_thumbnail_url || m.image_url)}
                                    alt="mat"
                                    className="w-6 h-6 rounded border border-slate-300 object-cover shrink-0"
                                  />
                                )}
                                <div className="truncate">
                                  <span className="font-bold text-slate-900">{m.name}</span>
                                  <span className="text-[10px] font-mono text-slate-500 ml-1.5">[{m.code}]</span>
                                </div>
                              </div>
                            )}
                            onChange={(mid) => {
                              const selectedMat = materials.find(m => (m.id || m._id) === mid);
                              if (selectedMat) {
                                updateUpperMaterialItem(idx, "material_id", mid);
                                updateUpperMaterialItem(idx, "material_name", selectedMat.name);
                                updateUpperMaterialItem(idx, "material_code", selectedMat.code);
                                if (selectedMat.image_url || selectedMat.image_thumbnail_url) {
                                  updateUpperMaterialItem(idx, "photo_url", selectedMat.image_url || selectedMat.image_thumbnail_url);
                                }
                              } else {
                                updateUpperMaterialItem(idx, "material_id", "");
                                updateUpperMaterialItem(idx, "material_name", "");
                                updateUpperMaterialItem(idx, "material_code", "");
                              }
                            }}
                          />
                        </div>

                        <div className="md:col-span-5">
                          <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 block mb-1">
                            Color to be Developed *
                          </label>
                          <input
                            type="text"
                            placeholder="e.g. Metallic Rose Gold, Tan Crust, Black Gloss"
                            value={mat.color_to_develop || ""}
                            onChange={(e) => updateUpperMaterialItem(idx, "color_to_develop", e.target.value)}
                            className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                          />
                        </div>
                      </div>

                      {/* Swatch Photo Preview - Strictly conditional: If no photo, REMOVE SPACE */}
                      {mat.photo_url ? (
                        <div className="flex items-center gap-2.5 p-2 bg-slate-50 border border-slate-200 rounded">
                          <div className="w-10 h-10 rounded border border-slate-300 overflow-hidden shrink-0 bg-white shadow-xs">
                            <SafeImage src={mat.photo_url} alt={mat.material_name || "Material"} className="w-full h-full object-cover" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-[10px] font-bold text-slate-800 block truncate">
                              {mat.material_name ? `${mat.material_name} Swatch Attached` : "Attached Swatch Photo"}
                            </span>
                            <div className="flex items-center gap-3 mt-0.5">
                              <label className="text-[10px] text-blue-600 hover:text-blue-800 font-bold cursor-pointer underline">
                                Change Swatch Photo
                                <input
                                  type="file"
                                  accept="image/*"
                                  className="hidden"
                                  onChange={(e) => {
                                    if (e.target.files?.[0]) {
                                      uploadCustomPhoto(e.target.files[0], (url) => updateUpperMaterialItem(idx, "photo_url", url));
                                    }
                                  }}
                                />
                              </label>
                              <button
                                type="button"
                                onClick={() => updateUpperMaterialItem(idx, "photo_url", "")}
                                className="text-[10px] text-red-600 hover:text-red-800 font-bold cursor-pointer underline"
                              >
                                Remove Photo
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="pt-0.5">
                          <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-600 hover:text-slate-900 font-semibold cursor-pointer">
                            <Camera className="w-3.5 h-3.5 text-slate-400" />
                            <span>+ Attach custom swatch photo</span>
                            <input
                              type="file"
                              accept="image/*"
                              className="hidden"
                              onChange={(e) => {
                                if (e.target.files?.[0]) {
                                  uploadCustomPhoto(e.target.files[0], (url) => updateUpperMaterialItem(idx, "photo_url", url));
                                }
                              }}
                            />
                          </label>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Lower Upper Details: Balanced 2 Columns */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Backing & Lining */}
                <div className="border-2 border-slate-200 p-4 bg-slate-50/70 space-y-3">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                    <Layers className="w-4 h-4 text-[#C27842]" />
                    Canvas Backing & Lining
                  </span>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Canvas / Interlining Backing:</label>
                    <SearchableSelect
                      options={[{ id: "", name: "-- None / No Canvas Backing --", code: "" }, ...materials]}
                      value={formData.upper_spec?.canvas_material_id || ""}
                      getKey={(m) => m.id || m._id || ""}
                      getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}] - ₹${m.rate || 0}/${m.unit || ""}` : "-- None / No Canvas Backing --"}
                      placeholder="Search canvas / backing material..."
                      inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      onChange={(mid) => {
                        const mat = materials.find(m => (m.id || m._id) === mid);
                        if (mat) {
                          updateUpper("canvas_material_id", mid);
                          updateUpper("canvas_material_name", mat.name);
                          updateUpper("canvas_material_code", mat.code);
                          updateUpper("canvas_backing", mat.name);
                        } else {
                          updateUpper("canvas_material_id", "");
                          updateUpper("canvas_material_name", "");
                          updateUpper("canvas_material_code", "");
                          updateUpper("canvas_backing", "");
                        }
                      }}
                    />
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Lining Material:</label>
                    <SearchableSelect
                      options={[{ id: "", name: "-- Select Lining Material --", code: "" }, ...materials]}
                      value={formData.upper_spec?.lining_material_id || ""}
                      getKey={(m) => m.id || m._id || ""}
                      getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}]` : "-- Select Lining Material --"}
                      placeholder="Search lining material..."
                      inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      onChange={(mid) => {
                        const mat = materials.find(m => (m.id || m._id) === mid);
                        if (mat) {
                          updateUpper("lining_material_id", mid);
                          updateUpper("lining_material_name", mat.name);
                          updateUpper("lining_material_code", mat.code);
                        } else {
                          updateUpper("lining_material_id", "");
                          updateUpper("lining_material_name", "");
                          updateUpper("lining_material_code", "");
                        }
                      }}
                    />
                  </div>
                </div>

                {/* Upper Manufacturing Operations */}
                <div className="border-2 border-slate-200 p-4 bg-slate-50/70 space-y-3">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                    <Scissors className="w-4 h-4 text-[#C27842]" />
                    Upper Manufacturing Operations
                  </span>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Cutting / Pattern Operation:</label>
                    <select
                      value={formData.upper_spec?.cutting_operation || "die_cut"}
                      onChange={(e) => updateUpper("cutting_operation", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="die_cut">Dye Cut (Die Cutting Press)</option>
                      <option value="folding">Folding / Skiving Pattern</option>
                      <option value="both">Both Die Cut + Folding</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Stitching Operation:</label>
                      <select
                        value={formData.upper_spec?.stitching_operation || "stitching"}
                        onChange={(e) => updateUpper("stitching_operation", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                      >
                        <option value="stitching">Stitching (Machine / Karigar)</option>
                        <option value="no_stitching">No Stitching (Seamless)</option>
                      </select>
                    </div>

                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Edge Treatment:</label>
                      <select
                        value={formData.upper_spec?.edge_treatment || "none"}
                        onChange={(e) => updateUpper("edge_treatment", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                      >
                        <option value="none">Raw Edge / Standard</option>
                        <option value="edge_coloring">Edge Coloring (Ink)</option>
                        <option value="folded_edge">Folded & Cemented</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>

              {/* Hardware & Buckle (Full Width) */}
              <div className="border-2 border-slate-200 p-4 bg-slate-50/70 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5">
                    <Tag className="w-4 h-4 text-[#C27842]" />
                    Buckles & Hardware Detailing
                  </span>
                  <label className="flex items-center gap-2 cursor-pointer font-bold uppercase text-[10px] tracking-wider text-slate-700">
                    <input
                      type="checkbox"
                      checked={formData.upper_spec?.has_buckle || false}
                      onChange={(e) => updateUpper("has_buckle", e.target.checked)}
                      className="w-4 h-4 text-slate-900"
                    />
                    <span>Has Buckle / Metal Trim</span>
                  </label>
                </div>

                {formData.upper_spec?.has_buckle && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                    <div className="space-y-2">
                      <div>
                        <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Buckle Specification (Size & Finish):</label>
                        <input
                          type="text"
                          placeholder="e.g. 15mm Oval Buckle, Antique Brass Finish"
                          value={formData.upper_spec?.buckle_spec || ""}
                          onChange={(e) => updateUpper("buckle_spec", e.target.value)}
                          className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                        />
                      </div>

                      {/* Buckle Photo Preview - Strictly conditional: If no photo, REMOVE SPACE */}
                      {formData.upper_spec?.buckle_photo_url ? (
                        <div className="flex items-center gap-2.5 p-2 bg-amber-50/60 border border-amber-200 rounded">
                          <div className="w-10 h-10 rounded border border-amber-300 overflow-hidden shrink-0 bg-white shadow-xs">
                            <SafeImage src={formData.upper_spec.buckle_photo_url} alt="Buckle" className="w-full h-full object-cover" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-[10px] font-bold text-amber-900 block truncate">Buckle Photo Attached</span>
                            <div className="flex items-center gap-3 mt-0.5">
                              <label className="text-[10px] text-blue-600 hover:text-blue-800 font-bold cursor-pointer underline">
                                Change Photo
                                <input
                                  type="file"
                                  accept="image/*"
                                  className="hidden"
                                  onChange={(e) => {
                                    if (e.target.files?.[0]) {
                                      uploadCustomPhoto(e.target.files[0], (url) => updateUpper("buckle_photo_url", url));
                                    }
                                  }}
                                />
                              </label>
                              <button
                                type="button"
                                onClick={() => updateUpper("buckle_photo_url", "")}
                                className="text-[10px] text-red-600 hover:text-red-800 font-bold cursor-pointer underline"
                              >
                                Remove Photo
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-600 hover:text-slate-900 font-semibold cursor-pointer">
                            <Camera className="w-3.5 h-3.5 text-slate-400" />
                            <span>+ Attach Buckle Photo</span>
                            <input
                              type="file"
                              accept="image/*"
                              className="hidden"
                              onChange={(e) => {
                                if (e.target.files?.[0]) {
                                  uploadCustomPhoto(e.target.files[0], (url) => updateUpper("buckle_photo_url", url));
                                }
                              }}
                            />
                          </label>
                        </div>
                      )}
                    </div>

                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Other Hardware / Rivets / D-rings:</label>
                      <input
                        type="text"
                        placeholder="e.g. Eyelets, Rivets, Elastic Goring"
                        value={formData.upper_spec?.other_hardware || ""}
                        onChange={(e) => updateUpper("other_hardware", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ──────────────── TAB 2: INSOLE SPEC ──────────────── */}
          {activeTab === "insole" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Mould / Shape Spec based on Heeled vs Flat */}
                <div className="border-2 border-slate-200 p-4 bg-slate-50/60 space-y-3">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                    <Hammer className="w-4 h-4 text-[#C27842]" />
                    {formData.profile === "heeled" ? "Heeled Insole Profile & Shape" : "Flat Mould Name & Shape"}
                  </span>

                  {formData.profile === "heeled" ? (
                    <>
                      <div>
                        <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Heeled Insole Category:</label>
                        <select
                          value={formData.insole_spec?.heeled_category || "platforms"}
                          onChange={(e) => updateInsole("heeled_category", e.target.value)}
                          className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                        >
                          <option value="platforms">Platforms Insole</option>
                          <option value="pumps">Pumps Insole</option>
                          <option value="wedges">Wedge Insole</option>
                          <option value="block_heel">Block Heel Insole</option>
                          <option value="other">Other Heeled Profile</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Insole Style Code / Mould Shape:</label>
                        <input
                          type="text"
                          placeholder="e.g. PUMP-SHAPE-38-POINTED, PLAT-50-SQUARE"
                          value={formData.insole_spec?.insole_style_code_shape || ""}
                          onChange={(e) => updateInsole("insole_style_code_shape", e.target.value)}
                          className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                        />
                      </div>
                    </>
                  ) : (
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Flat Mould Name / Die Shape:</label>
                      <input
                        type="text"
                        placeholder="e.g. FLAT-ROUND-M01, SQUARE-SLIPPER-02"
                        value={formData.insole_spec?.flat_mould_name_shape || ""}
                        onChange={(e) => updateInsole("flat_mould_name_shape", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      />
                    </div>
                  )}
                </div>

                {/* Base Board & Shank */}
                <div className="border-2 border-slate-200 p-4 bg-slate-50/60 space-y-3">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                    <Layers className="w-4 h-4 text-[#C27842]" />
                    Base Board (Shank) & Reinforcement
                  </span>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Base Board Material (from Material Master):</label>
                    <SearchableSelect
                      options={[{ id: "", name: "-- Select Base Board Material --", code: "" }, ...materials]}
                      value={formData.insole_spec?.base_board_material_id || ""}
                      getKey={(m) => m.id || m._id || ""}
                      getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}] - ₹${m.rate || 0}/${m.unit || ""}` : "-- Select Base Board Material --"}
                      placeholder="Search base board material..."
                      inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      onChange={(mid) => {
                        const mat = materials.find(m => (m.id || m._id) === mid);
                        if (mat) {
                          updateInsole("base_board_material_id", mid);
                          updateInsole("base_board_material_name", mat.name);
                          updateInsole("base_board_material_code", mat.code);
                          updateInsole("base_board", mat.name.toLowerCase().includes("cellulose") ? "cellulose_board" : "paper_board");
                        } else {
                          updateInsole("base_board_material_id", "");
                          updateInsole("base_board_material_name", "");
                          updateInsole("base_board_material_code", "");
                        }
                      }}
                    />
                  </div>

                  <div className="pt-2">
                    <label className="flex items-center gap-2 cursor-pointer font-bold uppercase text-[10px] tracking-wider text-slate-700">
                      <input
                        type="checkbox"
                        checked={formData.insole_spec?.shank_reinforced || false}
                        onChange={(e) => updateInsole("shank_reinforced", e.target.checked)}
                        className="w-4 h-4 text-slate-900"
                      />
                      <span>Steel Shank Reinforced (Mandatory for heels &gt; 1.5 in)</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Cushioning (EVA / PU Foam) */}
              <div className="border-2 border-slate-200 p-4 bg-slate-50/60 space-y-3">
                <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                  <Sparkles className="w-4 h-4 text-[#C27842]" />
                  Cushioning & Padding (EVA / PU Foam)
                </span>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Cushioning Foam Material (from Material Master):</label>
                    <SearchableSelect
                      options={[{ id: "", name: "-- Select Cushioning Foam --", code: "" }, ...materials]}
                      value={formData.insole_spec?.cushioning_material_id || ""}
                      getKey={(m) => m.id || m._id || ""}
                      getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}] - ₹${m.rate || 0}/${m.unit || ""}` : "-- Select Cushioning Foam --"}
                      placeholder="Search EVA / PU foam material..."
                      inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      onChange={(mid) => {
                        const mat = materials.find(m => (m.id || m._id) === mid);
                        if (mat) {
                          updateInsole("cushioning_material_id", mid);
                          updateInsole("cushioning_material_name", mat.name);
                          updateInsole("cushioning_material_code", mat.code);
                          updateInsole("cushioning_type", mat.name.toLowerCase().includes("pu") ? "pu_foam" : "eva");
                        } else {
                          updateInsole("cushioning_material_id", "");
                          updateInsole("cushioning_material_name", "");
                          updateInsole("cushioning_material_code", "");
                        }
                      }}
                    />
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Thickness (mm):</label>
                    <input
                      type="text"
                      placeholder="e.g. 3mm, 5mm, 3mm EVA + 2mm PU"
                      value={formData.insole_spec?.cushioning_thickness_mm || "3mm"}
                      onChange={(e) => updateInsole("cushioning_thickness_mm", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Socks Covering & Detailing */}
              <div className="border-2 border-slate-200 p-4 bg-slate-50/70 space-y-3">
                <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                  <Palette className="w-4 h-4 text-[#C27842]" />
                  Insole Covering (Socks) & Detailing
                </span>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Socks Covering Material:</label>
                    <select
                      value={formData.insole_spec?.socks_covering_type || "matching"}
                      onChange={(e) => updateInsole("socks_covering_type", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="matching">Matching Upper Top Material</option>
                      <option value="custom">Select Custom Material from Master</option>
                    </select>

                    {formData.insole_spec?.socks_covering_type === "custom" && (
                      <div className="mt-2.5">
                        <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Custom Socks Material:</label>
                        <SearchableSelect
                          options={[{ id: "", name: "-- Select Material --", code: "" }, ...materials]}
                          value={formData.insole_spec?.socks_material_id || ""}
                          getKey={(m) => m.id || m._id || ""}
                          getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}]` : "-- Select Material --"}
                          placeholder="Search socks material..."
                          inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                          onChange={(mid) => {
                            const mat = materials.find(m => (m.id || m._id) === mid);
                            updateInsole("socks_material_id", mid);
                            updateInsole("socks_material_name", mat ? mat.name : "");
                          }}
                        />
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 block mb-1 flex items-center justify-between">
                      <span>Insole / Socks Color:</span>
                      <span className="text-[9px] font-normal text-slate-500 lowercase">(if different than Upper)</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Tan, Nude, Beige, Gold (Leave blank if matches upper)"
                      value={formData.insole_spec?.socks_color || ""}
                      onChange={(e) => updateInsole("socks_color", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                    />
                    <p className="text-[10px] text-slate-500 mt-1">
                      {formData.insole_spec?.socks_color ? (
                        <span className="font-semibold text-blue-900">Custom Socks Color: "{formData.insole_spec.socks_color}"</span>
                      ) : (
                        <span>Leave blank to match Upper Primary Color ({formData.upper_spec?.materials?.[0]?.color_to_develop || formData.upper_spec?.upper_color_to_develop || "Primary Upper"})</span>
                      )}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-200">
                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Surface Detailing:</label>
                    <select
                      value={formData.insole_spec?.surface_detailing || "none"}
                      onChange={(e) => updateInsole("surface_detailing", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="none">None (Plain)</option>
                      <option value="patchwork">Patchwork</option>
                      <option value="stitching">Stitching Rows / Quilting</option>
                      <option value="both">Both Patchwork + Stitching</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Embossing:</label>
                    <select
                      value={formData.insole_spec?.embossing || "none"}
                      onChange={(e) => updateInsole("embossing", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="none">None</option>
                      <option value="gold_foil">Gold Foil Stamp</option>
                      <option value="silver_foil">Silver Foil Stamp</option>
                      <option value="blind_deboss">Blind Debossing</option>
                      <option value="heat_emboss">Heat Embossing</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Printing:</label>
                    <select
                      value={formData.insole_spec?.printing || "none"}
                      onChange={(e) => updateInsole("printing", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="none">None</option>
                      <option value="screen_printing">Screen Printing</option>
                      <option value="heat_transfer">Heat Transfer Print</option>
                      <option value="digital_pad">Digital Pad Printing</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ──────────────── TAB 3: SOLE & HEEL SPEC ──────────────── */}
          {activeTab === "sole" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Sole Material & Mould */}
                <div className="border-2 border-slate-200 p-4 bg-slate-50/60 space-y-3">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                    <Layers className="w-4 h-4 text-[#C27842]" />
                    Sole Material & Mould
                  </span>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Sole Material (from Material Master):</label>
                    <SearchableSelect
                      options={[{ id: "", name: "-- Select Sole Material --", code: "" }, ...materials]}
                      value={formData.sole_spec?.sole_material_id || ""}
                      getKey={(m) => m.id || m._id || ""}
                      getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}] - ₹${m.rate || 0}/${m.unit || ""}` : "-- Select Sole Material --"}
                      placeholder="Search sole material (TPR, PVC, PU, Sheet)..."
                      inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      onChange={(mid) => {
                        const mat = materials.find(m => (m.id || m._id) === mid);
                        if (mat) {
                          updateSole("sole_material_id", mid);
                          updateSole("sole_material_name", mat.name);
                          updateSole("sole_material_code", mat.code);
                          updateSole("sole_material", mat.name);
                        } else {
                          updateSole("sole_material_id", "");
                          updateSole("sole_material_name", "");
                          updateSole("sole_material_code", "");
                        }
                      }}
                    />
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Construction Type:</label>
                    <select
                      value={formData.sole_spec?.sole_type || "ready_made"}
                      onChange={(e) => updateSole("sole_type", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="ready_made">Ready-Made Moulded Sole</option>
                      <option value="die_cut">Die-Cut Sheet Sole</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Mould Name / Code:</label>
                      <input
                        type="text"
                        placeholder="e.g. M-TPR-045"
                        value={formData.sole_spec?.mould_name || ""}
                        onChange={(e) => updateSole("mould_name", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Sole Shape:</label>
                      <select
                        value={formData.sole_spec?.sole_shape || "Round"}
                        onChange={(e) => updateSole("sole_shape", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                      >
                        <option value="Round">Round Toe</option>
                        <option value="Square">Square Toe</option>
                        <option value="Pointed">Pointed Toe</option>
                        <option value="Almond">Almond Toe</option>
                        <option value="Chisel">Chisel Toe</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Secondary Processing Operations */}
                <div className="border-2 border-slate-200 p-4 bg-slate-50/60 space-y-3">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                    <Scissors className="w-4 h-4 text-[#C27842]" />
                    Sole Secondary Processing
                  </span>

                  <div className="space-y-2.5 pt-1">
                    <label className="flex items-center gap-2 cursor-pointer font-bold uppercase text-[10px] tracking-wider text-slate-700">
                      <input
                        type="checkbox"
                        checked={formData.sole_spec?.velting || false}
                        onChange={(e) => updateSole("velting", e.target.checked)}
                        className="w-4 h-4 text-slate-900"
                      />
                      <span>Velting (Welting Stitch Strip / Welt Stitching)</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer font-bold uppercase text-[10px] tracking-wider text-slate-700">
                      <input
                        type="checkbox"
                        checked={formData.sole_spec?.grinding || false}
                        onChange={(e) => updateSole("grinding", e.target.checked)}
                        className="w-4 h-4 text-slate-900"
                      />
                      <span>Sole Edge Grinding & Buffing</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer font-bold uppercase text-[10px] tracking-wider text-slate-700">
                      <input
                        type="checkbox"
                        checked={formData.sole_spec?.gripping || false}
                        onChange={(e) => updateSole("gripping", e.target.checked)}
                        className="w-4 h-4 text-slate-900"
                      />
                      <span>Anti-Skid Gripping / Grooving</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer font-bold uppercase text-[10px] tracking-wider text-slate-700">
                      <input
                        type="checkbox"
                        checked={formData.sole_spec?.attaching_top_piece || false}
                        onChange={(e) => updateSole("attaching_top_piece", e.target.checked)}
                        className="w-4 h-4 text-slate-900"
                      />
                      <span>Attaching Top Piece (Heel Top Lift / Rubber Tip)</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Heel Specifications */}
              <div className="border-2 border-slate-200 p-4 bg-slate-50/60 space-y-3">
                <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
                  <Hammer className="w-4 h-4 text-[#C27842]" />
                  Heel & Platform Construction
                </span>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Heel Profile:</label>
                    <select
                      value={formData.sole_spec?.heel_type || "none"}
                      onChange={(e) => updateSole("heel_type", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                    >
                      <option value="none">No Heel (Flat)</option>
                      <option value="platform_gola">Platform Rubber / Plastic Gola</option>
                      <option value="block_heel">Block Heel</option>
                      <option value="flared">Flared Heel</option>
                      <option value="kitten">Kitten Heel</option>
                      <option value="stiletto">Stiletto Heel</option>
                      <option value="wedge">Wedge</option>
                      <option value="just_heel">Just Heel (Standard Mould)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Heel Mould Name / Code:</label>
                    <input
                      type="text"
                      placeholder="e.g. M-HEEL-65MM"
                      value={formData.sole_spec?.heel_mould_name || ""}
                      onChange={(e) => updateSole("heel_mould_name", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Heel Height:</label>
                    <input
                      type="text"
                      placeholder="e.g. 50mm / 2 inch"
                      value={formData.sole_spec?.heel_height || ""}
                      onChange={(e) => updateSole("heel_height", e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                    />
                  </div>
                </div>

                {formData.sole_spec?.heel_type !== "none" && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-200 mt-2">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Heel Finish Type:</label>
                      <select
                        value={formData.sole_spec?.heel_finish || "colored"}
                        onChange={(e) => updateSole("heel_finish", e.target.value)}
                        className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                      >
                        <option value="colored">Colored (Spray Painted / Stained)</option>
                        <option value="covered">Covered (Wrapped with Material)</option>
                      </select>
                    </div>

                    {formData.sole_spec?.heel_finish === "covered" && (
                      <div className="space-y-2">
                        <div>
                          <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Covering Type:</label>
                          <select
                            value={formData.sole_spec?.heel_covering_type || "matching"}
                            onChange={(e) => updateSole("heel_covering_type", e.target.value)}
                            className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
                          >
                            <option value="matching">Matching Upper Material</option>
                            <option value="custom">Select from Materials Master</option>
                          </select>
                        </div>

                        {formData.sole_spec?.heel_covering_type === "custom" && (
                          <div>
                            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">Select Material:</label>
                            <SearchableSelect
                              options={[{ id: "", name: "-- Select Material --", code: "" }, ...materials]}
                              value={formData.sole_spec?.heel_covering_material_id || ""}
                              getKey={(m) => m.id || m._id || ""}
                              getLabel={(m) => (m.id || m._id) ? `${m.name} [${m.code || ""}]` : "-- Select Material --"}
                              placeholder="Search heel covering material..."
                              inputClassName="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
                              onChange={(mid) => {
                                const mat = materials.find(m => (m.id || m._id) === mid);
                                updateSole("heel_covering_material_id", mid);
                                updateSole("heel_covering_material_name", mat ? mat.name : "");
                              }}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* MODAL FOOTER */}
        <div className="px-5 py-4 bg-slate-50 border-t-2 border-slate-200 flex items-center justify-between flex-shrink-0">
          <BtnSecondary onClick={onClose} disabled={saving}>
            Cancel
          </BtnSecondary>

          <BtnPrimary
            onClick={handleSave}
            disabled={saving}
            data-testid="save-sample-spec-btn"
          >
            {saving ? <RefreshCw className="w-3.5 h-3.5 inline mr-1 animate-spin" /> : <Check className="w-3.5 h-3.5 inline mr-1" />}
            <span>{isNew ? "Create Sample Spec" : "Save Changes"}</span>
          </BtnPrimary>
        </div>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────────
   MODAL 2: INSPIRATION PHOTO GALLERY & ISOLATED MULTI-UPLOADER
   ───────────────────────────────────────────────────────────────────────────── */
function PhotoGalleryModal({ sample, onClose, onUpdated }) {
  const [uploading, setUploading] = useState(false);
  const [caption, setCaption] = useState("");
  const fileInputRef = useRef(null);
  const sid = sample.id || sample._id;

  const handleMultiFileUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setUploading(true);
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));

    try {
      await http.post(`/samples/${sid}/photos`, formData, {
        params: { caption: caption.trim() }
      });
      setCaption("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUpdated();
    } catch (err) {
      alert(getErrorMessage(err, "Failed to upload photos"));
    } finally {
      setUploading(false);
    }
  };

  const handleSetPrimary = async (photoId) => {
    try {
      await http.patch(`/samples/${sid}/photos/${photoId}/primary`);
      onUpdated();
    } catch (err) {
      alert(getErrorMessage(err, "Failed to set primary cover photo"));
    }
  };

  const handleDeletePhoto = async (photoId) => {
    if (!window.confirm("Delete this inspiration photo?")) return;
    try {
      await http.delete(`/samples/${sid}/photos/${photoId}`);
      onUpdated();
    } catch (err) {
      alert(getErrorMessage(err, "Failed to delete photo"));
    }
  };

  const photos = sample.inspiration_photos || [];

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3 md:p-6 overflow-y-auto">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-3xl flex flex-col max-h-[90vh] overflow-hidden">
        <div className="px-5 py-4 border-b-2 border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">SSK / Inspiration Photo Gallery</div>
            <h3 className="font-black text-base text-slate-900 flex items-center gap-2">
              <Camera className="w-4 h-4 text-[#C27842]" />
              <span>Mood Board & Multi-Angle Photos &mdash;</span>
              <span className="font-mono text-[#C27842]">{sample.temp_code}</span>
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Multi-angle inspiration pictures stored separately in <code className="font-mono text-slate-700 bg-slate-100 px-1 py-0.5">uploads/samples_inspiration/</code>.
            </p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 text-slate-500 hover:text-slate-900">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* MULTI-FILE UPLOADER STRIP */}
        <div className="px-5 py-3 bg-slate-50 border-b-2 border-slate-200 flex flex-col sm:flex-row gap-3 items-center">
          <input
            type="text"
            placeholder="Optional caption for these photos (e.g. Front upper angle, Heel finish)..."
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            className="w-full sm:flex-1 border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
          />

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleMultiFileUpload}
            multiple
            accept="image/*"
            className="hidden"
          />

          <BtnPrimary
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="text-xs"
          >
            {uploading ? <RefreshCw className="w-3.5 h-3.5 inline mr-1 animate-spin" /> : <Upload className="w-3.5 h-3.5 inline mr-1" />}
            <span>{uploading ? "Uploading..." : "+ Upload Photos"}</span>
          </BtnPrimary>
        </div>

        {/* PHOTO GALLERY GRID */}
        <div className="p-5 overflow-y-auto flex-1 bg-white">
          {photos.length === 0 ? (
            <div
              onClick={() => fileInputRef.current?.click()}
              className="text-center py-12 border-2 border-dashed border-slate-300 hover:border-slate-900 rounded p-6 cursor-pointer bg-slate-50/60 transition group"
            >
              <Camera className="w-10 h-10 opacity-30 mx-auto mb-2 text-slate-400 group-hover:scale-105 transition" />
              <p className="text-xs font-bold uppercase tracking-wider text-slate-800">No photos uploaded yet</p>
              <p className="text-[11px] text-slate-500 font-mono mt-1">Click here to select and upload multiple reference photos.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {photos.map((photo) => (
                <div key={photo.photo_id} className={`group relative border-2 overflow-hidden bg-white shadow-xs ${photo.is_primary ? "border-amber-500 shadow-ind ring-1 ring-amber-400" : "border-slate-200"}`}>
                  <div className="h-44 bg-slate-100 flex items-center justify-center overflow-hidden relative">
                    <SafeImage src={photo.url} alt="Inspiration" className="w-full h-full object-cover" />

                    {photo.is_primary && (
                      <span className="absolute top-2 left-2 z-10">
                        <Badge color="yellow">PRIMARY COVER</Badge>
                      </span>
                    )}

                    <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition z-10">
                      {!photo.is_primary && (
                        <button
                          onClick={() => handleSetPrimary(photo.photo_id)}
                          className="px-2 py-1 bg-amber-500 hover:bg-amber-600 text-white shadow-xs text-[10px] font-bold uppercase flex items-center gap-1"
                          title="Make Primary Cover"
                        >
                          <Star className="w-3 h-3" />
                          <span>Set Cover</span>
                        </button>
                      )}
                      <button
                        onClick={() => handleDeletePhoto(photo.photo_id)}
                        className="p-1.5 bg-[#0F172A] hover:bg-red-600 text-white transition shadow-xs text-[10px]"
                        title="Delete photo"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {photo.caption && (
                    <div className="p-2 text-[10px] font-mono text-slate-700 truncate border-t border-slate-200 bg-slate-50 font-bold">
                      {photo.caption}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t-2 border-slate-200 flex justify-end bg-slate-50 flex-shrink-0">
          <BtnSecondary onClick={onClose}>
            Done
          </BtnSecondary>
        </div>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────────
   MODAL 3: 1-CLICK TRANSFER TO STYLE MASTER (WITH BOM & LABOR GENERATION)
   ───────────────────────────────────────────────────────────────────────────── */
function TransferToStyleModal({ sample, onClose, onSuccess }) {
  const sid = sample.id || sample._id;
  const yieldSpec = sample.yield_spec || {};
  const stdPresets = yieldSpec.standard_presets || [];
  const insolePreset = stdPresets.find((p) => (p.component_key || "").includes("insole"));
  const socksPreset = stdPresets.find((p) => (p.component_key || "").includes("socks") || (p.component_key || "").includes("bottom"));

  const [styleCode, setStyleCode] = useState("");
  const [loadingCode, setLoadingCode] = useState(true);
  const [styleName, setStyleName] = useState(sample.sample_name || "");
  const [baseSize, setBaseSize] = useState("7");
  const [marginPct, setMarginPct] = useState(25);
  const [submitting, setSubmitting] = useState(false);

  // Actual Developed Sample Photo (uploaded at transfer; inspiration photo stays in Sample Archive)
  const [actualPhoto, setActualPhoto] = useState(sample.actual_developed_photo || null);
  const [actualPhotoUrl, setActualPhotoUrl] = useState(sample.actual_developed_photo_url || "");
  const [uploadingActualPhoto, setUploadingActualPhoto] = useState(false);

  const handleUploadActualPhoto = async (file) => {
    if (!file) return;
    setUploadingActualPhoto(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await http.post(`/samples/${sid}/actual-photo`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (res?.data?.actual_photo_url) {
        setActualPhotoUrl(res.data.actual_photo_url);
        setActualPhoto(res.data.actual_photo || null);
      }
    } catch (err) {
      alert(getErrorMessage(err, "Failed to upload actual developed sample photo"));
    } finally {
      setUploadingActualPhoto(false);
    }
  };

  useEffect(() => {
    let active = true;
    setLoadingCode(true);
    http.get(`/samples/${sid}/next-style-code`)
      .then((res) => {
        if (active && res?.data?.style_code) {
          setStyleCode(res.data.style_code);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoadingCode(false);
      });
    return () => { active = false; };
  }, [sid]);

  const upper = sample.upper_spec || {};
  const insole = sample.insole_spec || {};
  const sole = sample.sole_spec || {};
  const matBreakdowns = yieldSpec.material_breakdown || [];
  const upperTopBreakdowns = matBreakdowns.filter(
    (mb) => !mb.is_lining && !mb.is_canvas && !(mb.placement || "").toLowerCase().includes("canvas")
  );
  const upperMaterialsList = Array.isArray(upper.materials) && upper.materials.length > 0
    ? upper.materials
    : [{
        material_id: upper.upper_top_material_id || "",
        material_name: upper.upper_top_material_name || "Upper Material",
        material_code: upper.upper_top_material_code || "",
        placement: "Primary",
      }];

  const resolveUpperMatYield = (um, idx) => {
    const matched = upperTopBreakdowns.find(
      (mb) =>
        (um.material_id && mb.material_id === um.material_id) ||
        (um.material_name && mb.material_name === um.material_name) ||
        (um.placement && mb.placement === um.placement)
    ) || upperTopBreakdowns[idx];
    return Number(matched?.yield_per_unit || yieldSpec?.component_breakdown?.upper?.yield_per_unit || yieldSpec?.yield_per_unit || 15.0);
  };

  // Material Yields in Pairs / Meter (pair/mtr) or Pairs / Sheet
  const [yields, setYields] = useState(() => {
    const base = {
      upper_top: resolveUpperMatYield(upperMaterialsList[0], 0),
      canvas: Number(yieldSpec?.component_breakdown?.canvas_reinforcement?.yield_per_unit || 16.0),
      lining: Number(yieldSpec?.component_breakdown?.lining?.yield_per_unit || 17.0),
      base_board: Number(insolePreset?.yield_per_unit || 26.0),
      cushioning: 1.0,
      socks_covering: Number(socksPreset?.yield_per_unit || 8.0),
      sole: 1.0,
      heel: 1.0,
      buckle: 1.0,
    };
    upperMaterialsList.forEach((um, idx) => {
      base[`upper_mat_${idx}`] = resolveUpperMatYield(um, idx);
    });
    return base;
  });

  const handleTransfer = async () => {
    if (!actualPhotoUrl) {
      alert("Please upload the actual developed & approved sample photo before transferring to Style Master.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        style_code: styleCode ? styleCode.trim().toUpperCase() : null,
        name: styleName.trim(),
        base_size: baseSize,
        margin_pct: Number(marginPct),
        material_yields: yields,
        labor_rates: {},
        use_sample_photo_as_primary: false,
        actual_photo_url: actualPhotoUrl,
        actual_photo: actualPhoto,
      };

      const res = await http.post(`/samples/${sid}/transfer-to-style`, payload);
      onSuccess(res.data.style?.code || styleCode);
    } catch (err) {
      alert(getErrorMessage(err, "Failed to transfer sample to Style Master"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3 md:p-6 overflow-y-auto">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-4xl max-h-[92vh] flex flex-col overflow-hidden">
        {/* HEADER */}
        <div className="px-5 py-4 border-b-2 border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">SSK / Style Master Handover</div>
            <h2 className="text-lg font-black tracking-tight text-slate-900 flex items-center gap-2">
              <Layers className="w-5 h-5 text-[#C27842]" />
              <span>Transfer Sample to Style Master</span>
            </h2>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Promotes temporary sample <code className="font-mono text-slate-900 font-bold bg-slate-100 px-1 py-0.5">{sample.temp_code}</code> to official ERP production style with calibrated BOM yields (pair/mtr). Labor &amp; karigar wages are calculated at Planning.
            </p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 text-slate-500 hover:text-slate-900">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* BODY */}
        <div className="p-4 md:p-6 overflow-y-auto flex-1 space-y-4 text-xs bg-white">
          {/* PRIMARY ERP STYLE DETAILS */}
          <div className="border-2 border-slate-900 p-4 bg-slate-50 space-y-3">
            <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5 border-b border-slate-200 pb-2">
              <Tag className="w-4 h-4 text-[#C27842]" />
              Official Style Master Assignment
            </span>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 flex items-center justify-between mb-1">
                  <span>Official ERP Style Code</span>
                  <span className="text-[9px] px-1.5 py-0.2 bg-emerald-100 text-emerald-800 border border-emerald-300 font-mono">AUTO-ALLOTTED</span>
                </label>
                <input
                  type="text"
                  readOnly
                  value={loadingCode ? "Allotting..." : styleCode}
                  className="w-full border-2 border-slate-900 bg-slate-100 px-3 py-1.5 font-mono font-black text-sm tracking-wider text-slate-900 focus:outline-none cursor-not-allowed"
                />
                <span className="text-[10px] text-slate-500 mt-0.5 block font-mono">Automatically allotted unique ERP Style Code.</span>
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 block mb-1">Official Style Name</label>
                <input
                  type="text"
                  value={styleName}
                  onChange={(e) => setStyleName(e.target.value)}
                  className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-bold focus:border-[#2563EB] focus:outline-none"
                />
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 block mb-1">Base Production Size</label>
                <select
                  value={baseSize}
                  onChange={(e) => setBaseSize(e.target.value)}
                  className="w-full border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-mono font-bold focus:border-[#2563EB] focus:outline-none"
                >
                  {["4", "5", "6", "7", "8", "9", "10", "11"].map(s => (
                    <option key={s} value={s}>Size UK/India {s}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* ACTUAL DEVELOPED SAMPLE PHOTO UPLOAD */}
          <div className="border-2 border-emerald-700 p-4 bg-emerald-50/40 space-y-2.5">
            <div className="flex items-center justify-between border-b border-emerald-200 pb-2">
              <span className="font-bold text-xs uppercase tracking-wider text-emerald-950 flex items-center gap-1.5">
                <Camera className="w-4 h-4 text-emerald-700" />
                <span>Actual Developed &amp; Approved Sample Photo *</span>
              </span>
              <span className="text-[10px] font-mono text-emerald-800 font-bold">
                Shown in Style Master (Inspiration stays in Sample Archive)
              </span>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-4">
              {actualPhotoUrl ? (
                <div className="w-28 h-24 border-2 border-emerald-600 bg-white overflow-hidden shrink-0">
                  <SafeImage src={actualPhotoUrl} alt="Actual Developed Sample" className="w-full h-full object-cover" />
                </div>
              ) : (
                <div className="w-28 h-24 border-2 border-dashed border-emerald-400 bg-white flex flex-col items-center justify-center text-emerald-600 shrink-0">
                  <Camera className="w-6 h-6 opacity-50" />
                  <span className="text-[9px] font-mono mt-1">Required</span>
                </div>
              )}
              <div className="flex-1 space-y-1.5">
                <p className="text-[11px] text-slate-700">
                  Upload the photo of the <strong>actual developed &amp; approved physical sample</strong>. The original inspiration photo will remain archived in Sample Development for side-by-side comparison, while Style Master will display only this actual developed photo.
                </p>
                <label className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white font-bold uppercase text-[11px] tracking-wider cursor-pointer shadow-ind">
                  <Upload className="w-3.5 h-3.5" />
                  <span>{uploadingActualPhoto ? "Uploading..." : (actualPhotoUrl ? "Change Actual Sample Photo" : "Upload Actual Sample Photo")}</span>
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled={uploadingActualPhoto}
                    onChange={(e) => {
                      if (e.target.files?.[0]) handleUploadActualPhoto(e.target.files[0]);
                    }}
                  />
                </label>
              </div>
            </div>
          </div>

          {/* MATERIAL YIELDS PREVIEW & ADJUSTMENT */}
          <div className="border-2 border-slate-200 p-4 bg-white space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <span className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-1.5">
                <Palette className="w-4 h-4 text-[#C27842]" />
                Pre-Populated Bill of Materials (BOM) & Yield per Pair
              </span>
              <span className="text-[10px] font-mono uppercase text-slate-500">
                Material consumption allowance
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Upper Materials (each Primary / Secondary material with its exact calibrated yield) */}
              {upperMaterialsList.map((um, idx) => {
                const key = `upper_mat_${idx}`;
                const matchedMb = upperTopBreakdowns.find(
                  (mb) =>
                    (um.material_id && mb.material_id === um.material_id) ||
                    (um.material_name && mb.material_name === um.material_name) ||
                    (um.placement && mb.placement === um.placement)
                ) || upperTopBreakdowns[idx];
                const unitLabel = (matchedMb?.consumption_unit === "sheet" || yieldSpec?.material_type === "sheet")
                  ? "pair / sheet"
                  : "pair / mtr";
                const matLabel = `${um.placement || (idx === 0 ? "Primary" : "Secondary")}: ${um.material_name || "Upper Material"}${um.material_code ? ` [${um.material_code}]` : ""}`;
                return (
                  <div key={key} className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                    <span className="text-xs font-bold text-slate-900 truncate block" title={matLabel}>
                      {matLabel}
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.01"
                        value={yields[key] ?? yields.upper_top}
                        onChange={(e) => {
                          const val = Number(e.target.value);
                          setYields(p => ({ ...p, [key]: val, ...(idx === 0 ? { upper_top: val } : {}) }));
                        }}
                        className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                      />
                      <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">{unitLabel}</span>
                    </div>
                  </div>
                );
              })}

              {/* Canvas */}
              {(upper.canvas_material_name || upper.canvas_backing) && (
                <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                  <span className="text-xs font-bold text-slate-900 truncate block" title={`Canvas: ${upper.canvas_material_name || upper.canvas_backing}`}>
                    Canvas: {upper.canvas_material_name || upper.canvas_backing}{upper.canvas_material_code ? ` [${upper.canvas_material_code}]` : ""}
                  </span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="0.01"
                      value={yields.canvas}
                      onChange={(e) => setYields(p => ({ ...p, canvas: Number(e.target.value) }))}
                      className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                    />
                    <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / mtr</span>
                  </div>
                </div>
              )}

              {/* Lining */}
              {(upper.lining_material_name || upper.lining_material_id) && (
                <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                  <span className="text-xs font-bold text-slate-900 truncate block" title={`Lining: ${upper.lining_material_name}`}>
                    Lining: {upper.lining_material_name || "Standard Lining"}{upper.lining_material_code ? ` [${upper.lining_material_code}]` : ""}
                  </span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="0.01"
                      value={yields.lining}
                      onChange={(e) => setYields(p => ({ ...p, lining: Number(e.target.value) }))}
                      className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                    />
                    <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / mtr</span>
                  </div>
                </div>
              )}

              {/* Base Board */}
              <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                <span className="text-xs font-bold text-slate-900 truncate block">
                  Insole Base: {insole.base_board_material_name || (insole.base_board === "cellulose_board" ? "Cellulose Board" : "Paper Board")}
                </span>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step="1"
                    value={yields.base_board}
                    onChange={(e) => setYields(p => ({ ...p, base_board: Number(e.target.value) }))}
                    className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                  />
                  <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / sheet</span>
                </div>
              </div>

              {/* Cushioning Foam */}
              <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                <span className="text-xs font-bold text-slate-900 truncate block">
                  Cushion: {insole.cushioning_material_name || `${insole.cushioning_type?.toUpperCase() || "EVA"} ${insole.cushioning_thickness_mm || "3mm"}`}
                </span>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step="1"
                    value={yields.cushioning}
                    onChange={(e) => setYields(p => ({ ...p, cushioning: Number(e.target.value) }))}
                    className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                  />
                  <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / pair</span>
                </div>
              </div>

              {/* Socks Covering */}
              <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                <span className="text-xs font-bold text-slate-900 truncate block">
                  Socks: {insole.socks_covering_type === "matching" ? "Matching Upper" : (insole.socks_material_name || "Socks Material")}
                </span>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step="0.05"
                    value={yields.socks_covering}
                    onChange={(e) => setYields(p => ({ ...p, socks_covering: Number(e.target.value) }))}
                    className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                  />
                  <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / mtr</span>
                </div>
              </div>

              {/* Sole */}
              <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                <span className="text-xs font-bold text-slate-900 truncate block">
                  Sole: {sole.sole_material_name || sole.sole_material || "TPR"} {sole.mould_name ? `(${sole.mould_name})` : ""}
                </span>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step="1"
                    value={yields.sole}
                    onChange={(e) => setYields(p => ({ ...p, sole: Number(e.target.value) }))}
                    className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                  />
                  <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / pair</span>
                </div>
              </div>

              {/* Heel (if heeled) */}
              {(sample.profile === "heeled" || sole.heel_type !== "none") && (
                <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                  <span className="text-xs font-bold text-slate-900 truncate block">
                    Heel: {sole.heel_type} {sole.heel_mould_name} ({sole.heel_finish})
                  </span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="1"
                      value={yields.heel}
                      onChange={(e) => setYields(p => ({ ...p, heel: Number(e.target.value) }))}
                      className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                    />
                    <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / pair</span>
                  </div>
                </div>
              )}

              {/* Buckle */}
              {upper.has_buckle && (
                <div className="p-2.5 border-2 border-slate-200 bg-slate-50/60 space-y-1">
                  <span className="text-xs font-bold text-slate-900 truncate block">
                    Buckle: {upper.buckle_spec || "Standard"}
                  </span>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="1"
                      value={yields.buckle}
                      onChange={(e) => setYields(p => ({ ...p, buckle: Number(e.target.value) }))}
                      className="w-20 p-1 border-2 border-slate-300 font-mono text-xs text-right font-bold bg-white focus:border-[#2563EB] focus:outline-none"
                    />
                    <span className="text-[10px] uppercase font-bold text-slate-500 font-mono">pair / pair</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* FOOTER */}
        <div className="px-5 py-4 bg-slate-50 border-t-2 border-slate-200 flex items-center justify-between flex-shrink-0">
          <BtnSecondary onClick={onClose} disabled={submitting}>
            Cancel
          </BtnSecondary>

          <button
            onClick={handleTransfer}
            disabled={submitting || loadingCode || uploadingActualPhoto || !actualPhotoUrl}
            className="bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase tracking-wider text-xs px-6 py-2.5 border-2 border-[#C27842] shadow-ind hover:shadow-ind-lg transition-all active:shadow-none disabled:opacity-50 flex items-center gap-2"
            title={!actualPhotoUrl ? "Please upload the actual developed sample photo first" : "Confirm and transfer to Style Master"}
          >
            {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Layers className="w-3.5 h-3.5" />}
            <span>Confirm & Transfer to Style Master</span>
          </button>
        </div>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────────
   MODAL 4: DETAIL VIEW & DESIGNER TECH PACK PRINT SHEET (80% IMAGE COVERAGE)
   ───────────────────────────────────────────────────────────────────────────── */
function DetailViewModal({ sample, onClose, onOpenEdit, onOpenTransfer, onOpenPhotos, onOpenPatternYield, initialViewMode = "screen" }) {
  const [viewMode, setViewMode] = useState(initialViewMode); // "screen" or "print_sheet"
  const upper = sample.upper_spec || {};
  const insole = sample.insole_spec || {};
  const sole = sample.sole_spec || {};
  const photos = sample.inspiration_photos || [];
  const [selectedPhotoIdx, setSelectedPhotoIdx] = useState(0);

  const activePhoto = photos[selectedPhotoIdx] || photos[0];

  // Smart Footwear Tech Pack Pagination:
  // If there are an odd number of pictures, place the last picture on the final Tech Pack data page
  // (with technical specs below it), which saves 1 full printed page!
  // All other pictures are placed 2 per page on preceding visual sheets.
  // If there are an even number of pictures, all pictures are paired 2 per page,
  // and the final page is a dedicated full-page Technical Specifications sheet.
  const photoCount = photos.length;
  const isOdd = photoCount % 2 === 1;
  const pairedPhotos = isOdd ? photos.slice(0, photoCount - 1) : photos;
  const lastOddPhoto = isOdd ? photos[photoCount - 1] : null;

  const photoPages = [];
  for (let i = 0; i < pairedPhotos.length; i += 2) {
    photoPages.push(pairedPhotos.slice(i, i + 2));
  }

  // Total Pages:
  // 0 photos: 1 page (placeholder + data)
  // Even photos (>0): photoPages.length + 1 (all paired photo pages + 1 dedicated data page)
  // Odd photos: photoPages.length + 1 (all paired photo pages + 1 combined last-photo-and-data page)
  const totalPages = photoCount === 0 ? 1 : (photoPages.length + 1);

  const handlePrint = () => {
    setViewMode("print_sheet");
    setTimeout(() => {
      window.print();
    }, 150);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="techpack-overlay techpack-printable-dialog fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-2 sm:p-4 md:p-6 overflow-y-auto print:static print:p-0 print:m-0 print:bg-white print:overflow-visible print:block"
    >
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-4xl flex flex-col max-h-[92vh] overflow-hidden print:max-w-none print:max-h-none print:shadow-none print:border-none print:overflow-visible print:bg-white print:p-0 print:m-0">
        
        {/* ── MODAL SCREEN HEADER (Hidden in Print) ── */}
        <div className="px-5 py-3.5 border-b-2 border-slate-200 bg-white flex items-center justify-between flex-shrink-0 print:hidden">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">SSK / Tech Pack Specification</div>
            <h3 className="font-black text-base text-slate-900 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#C27842]" />
              <span>{sample.sample_name} &mdash; </span>
              <span className="font-mono text-[#C27842]">{sample.temp_code}</span>
            </h3>
            <div className="flex items-center gap-2 mt-0.5">
              <Badge color={sample.profile === "heeled" ? "purple" : "slate"}>
                {sample.profile === "heeled" ? "👠 Heeled" : "🥿 Flat"}
              </Badge>
              {sample.season && (
                <span className="font-mono text-[10px] font-bold uppercase bg-slate-100 border border-slate-300 px-1.5 py-0.5 text-slate-700">
                  {sample.season}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setViewMode(viewMode === "screen" ? "print_sheet" : "screen")}
              className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider border-2 transition flex items-center gap-1.5 ${
                viewMode === "print_sheet"
                  ? "bg-[#0F172A] text-white border-[#0F172A]"
                  : "bg-white text-slate-800 border-slate-300 hover:border-slate-900"
              }`}
              title="Toggle between Interactive Specs and Designer Tech Pack Print Preview"
            >
              {viewMode === "print_sheet" ? <Eye className="w-3.5 h-3.5" /> : <Layers className="w-3.5 h-3.5" />}
              <span>{viewMode === "print_sheet" ? "Standard Specs" : `Designer Sheet Preview (${totalPages} Page${totalPages > 1 ? "s" : ""})`}</span>
            </button>

            <BtnPrimary onClick={handlePrint} title="Print Tech Pack for Designer">
              <Printer className="w-3.5 h-3.5 inline mr-1" />
              <span>Print Tech Pack</span>
            </BtnPrimary>

            <button onClick={onClose} className="p-1 hover:bg-slate-100 text-slate-500 hover:text-slate-900 ml-1" title="Close">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ── VIEW 1: INTERACTIVE SCREEN SPECIFICATION (Print: Hidden) ── */}
        <div className={`${viewMode === "screen" ? "block" : "hidden"} print:hidden p-5 overflow-y-auto flex-1 space-y-4 text-xs bg-white`}>
          {/* PHOTO SHOWCASE */}
          {photos.length > 0 ? (
            <div className="space-y-2">
              <div className="h-64 overflow-hidden bg-slate-100 border-2 border-slate-200 flex items-center justify-center relative">
                <SafeImage src={activePhoto.url} alt="Sample Active" className="w-full h-full object-contain" />
                {activePhoto.caption && (
                  <div className="absolute bottom-2 left-2 right-2 bg-[#0F172A]/90 text-white font-mono px-3 py-1 text-xs border border-slate-700">
                    {activePhoto.caption}
                  </div>
                )}
                {activePhoto.is_primary && (
                  <div className="absolute top-2 left-2 z-10">
                    <Badge color="yellow">PRIMARY COVER</Badge>
                  </div>
                )}
              </div>

              {/* Thumbnails row */}
              {photos.length > 1 && (
                <div className="flex items-center gap-2 overflow-x-auto pb-1">
                  {photos.map((p, idx) => (
                    <div
                      key={p.photo_id || idx}
                      onClick={() => setSelectedPhotoIdx(idx)}
                      className={`h-16 w-16 shrink-0 overflow-hidden border-2 cursor-pointer transition ${
                        idx === selectedPhotoIdx ? "border-slate-900 shadow-ind ring-1 ring-slate-900" : "border-slate-200 opacity-70 hover:opacity-100"
                      }`}
                    >
                      <SafeImage src={p.url} alt="Thumb" className="w-full h-full object-cover" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div
              onClick={onOpenPhotos}
              className="h-32 border-2 border-dashed border-slate-300 hover:border-slate-900 flex flex-col items-center justify-center cursor-pointer text-slate-400 hover:text-slate-700 transition bg-slate-50"
            >
              <Camera className="w-8 h-8 opacity-30 mb-1" />
              <span className="font-bold text-xs uppercase tracking-wider text-slate-600">No photos uploaded yet &bull; Click to add reference photos</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="border-2 border-slate-200 p-3.5 bg-slate-50/60 space-y-2">
              <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 border-b border-slate-200 pb-1 flex items-center justify-between">
                <span>👟 Upper Component</span>
                {Array.isArray(upper.materials) && upper.materials.length > 1 && (
                  <span className="font-mono text-[9px] bg-slate-200 text-slate-800 px-1.5 py-0.5 rounded font-bold">
                    {upper.materials.length} Materials
                  </span>
                )}
              </h4>

              {Array.isArray(upper.materials) && upper.materials.length > 0 ? (
                <div className="space-y-1.5">
                  {upper.materials.map((m, mIdx) => (
                    <div key={mIdx} className="bg-white p-2 border border-slate-200 rounded">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[10px] uppercase text-slate-700 bg-slate-100 px-1 border border-slate-200">
                          {m.placement || `Material #${mIdx + 1}`}
                        </span>
                        {m.color_to_develop && (
                          <span className="font-mono text-[10px] font-bold text-blue-900">
                            Color: {m.color_to_develop}
                          </span>
                        )}
                      </div>
                      <p className="font-mono text-slate-900 text-xs font-bold mt-0.5 truncate">
                        {m.material_name || "Pending Selection"} {m.material_code ? `[${m.material_code}]` : ""}
                      </p>
                      {/* Attached swatch thumbnail - conditional */}
                      {m.photo_url && (
                        <div className="flex items-center gap-2 mt-1 pt-1 border-t border-slate-100">
                          <div className="w-8 h-8 rounded border border-slate-300 overflow-hidden shrink-0 shadow-xs">
                            <SafeImage src={m.photo_url} alt="Swatch" className="w-full h-full object-cover" />
                          </div>
                          <span className="text-[10px] text-slate-500 font-mono">Swatch Attached</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <p><span className="text-[10px] uppercase font-bold text-slate-500">Material:</span> <span className="font-mono text-slate-900">{upper.upper_top_material_name || "N/A"}</span></p>
                  <p><span className="text-[10px] uppercase font-bold text-slate-500">Color:</span> <span className="font-mono text-slate-900">{upper.upper_color_to_develop || "N/A"}</span></p>
                </>
              )}

              <p><span className="text-[10px] uppercase font-bold text-slate-500">Canvas:</span> <span className="font-mono text-slate-900">{upper.canvas_backing || "None"}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Lining:</span> <span className="font-mono text-slate-900">{upper.lining_material_name || "Standard"}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Operations:</span> <span className="font-mono text-slate-900">{upper.cutting_operation}, {upper.stitching_operation}, {upper.edge_treatment}</span></p>
              {upper.has_buckle && (
                <div className="pt-1 border-t border-slate-200">
                  <p><span className="text-[10px] uppercase font-bold text-slate-500">Buckle:</span> <span className="font-mono text-slate-900">{upper.buckle_spec}</span></p>
                  {upper.buckle_photo_url && (
                    <div className="flex items-center gap-2 mt-1">
                      <div className="w-8 h-8 rounded border border-amber-300 overflow-hidden shrink-0 shadow-xs">
                        <SafeImage src={upper.buckle_photo_url} alt="Buckle" className="w-full h-full object-cover" />
                      </div>
                      <span className="text-[10px] text-amber-800 font-mono">Buckle Photo Attached</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="border-2 border-slate-200 p-3.5 bg-slate-50/60 space-y-1.5">
              <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 border-b border-slate-200 pb-1">🩴 Insole / Socks</h4>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Base:</span> <span className="font-mono text-slate-900">{insole.base_board === "cellulose_board" ? "Cellulose" : "Paper Board"}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Cushion:</span> <span className="font-mono text-slate-900">{insole.cushioning_type} {insole.cushioning_thickness_mm}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Covering:</span> <span className="font-mono text-slate-900">{insole.socks_covering_type === "matching" ? "Matching Upper Top Material" : (insole.socks_material_name || "Custom Socks Material")}</span></p>
              <p>
                <span className="text-[10px] uppercase font-bold text-slate-500">Socks Color:</span>{" "}
                <span className="font-mono text-slate-900">
                  {insole.socks_color ? (
                    <span className="font-bold text-blue-900">{insole.socks_color}</span>
                  ) : (
                    <span className="text-slate-500 italic">Matches Upper ({upper.upper_color_to_develop || upper.materials?.[0]?.color_to_develop || "Standard"})</span>
                  )}
                </span>
              </p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Detailing:</span> <span className="font-mono text-slate-900">{insole.surface_detailing}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Embossing:</span> <span className="font-mono text-slate-900">{insole.embossing}</span></p>
            </div>

            <div className="border-2 border-slate-200 p-3.5 bg-slate-50/60 space-y-1.5">
              <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 border-b border-slate-200 pb-1">👞 Sole & Heel</h4>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Material:</span> <span className="font-mono text-slate-900">{sole.sole_material}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Type:</span> <span className="font-mono text-slate-900">{sole.sole_type}</span></p>
              <p><span className="text-[10px] uppercase font-bold text-slate-500">Mould:</span> <span className="font-mono text-slate-900">{sole.mould_name || "N/A"}</span></p>
              {sole.heel_type !== "none" && (
                <>
                  <p><span className="text-[10px] uppercase font-bold text-slate-500">Heel:</span> <span className="font-mono text-slate-900">{sole.heel_type} ({sole.heel_finish})</span></p>
                  <p><span className="text-[10px] uppercase font-bold text-slate-500">Height:</span> <span className="font-mono text-slate-900">{sole.heel_height || "N/A"}</span></p>
                </>
              )}
            </div>
          </div>
        </div>

        {/* ── VIEW 2: DESIGNER TECH PACK PRINT SHEET(S) ── */}
        <div className={`${viewMode === "print_sheet" ? "block" : "hidden"} print:block p-2 sm:p-4 print:p-0 print:m-0 w-full overflow-y-auto print:overflow-visible bg-slate-100 print:bg-white text-slate-900 font-sans space-y-6 print:space-y-0`}>
          
          {/* 1. PRECEDING 2-PHOTO PAGES (Pairs of 2 photos) */}
          {photoPages.map((pair, pIdx) => {
            const pageNumber = pIdx + 1;
            return (
              <div
                key={`photo-page-${pIdx}`}
                className="techpack-page w-full max-w-[190mm] mx-auto bg-white border border-slate-300 print:border flex flex-col justify-between p-2 print:p-1.5 box-border shadow-sm print:shadow-none"
              >
                {/* Header */}
                <div className="border-b border-slate-300 pb-1 mb-1 shrink-0">
                  <div className="flex items-baseline justify-between">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-slate-500">
                        SSK FOOTCARE &bull; TECH PACK (INSPIRATION ANGLES)
                      </span>
                      <h1 className="text-lg font-black text-slate-900 uppercase tracking-tight leading-tight truncate max-w-[90mm]">
                        {sample.sample_name}
                      </h1>
                    </div>

                    <div className="flex items-center gap-1.5 text-[11px] font-mono">
                      <span className="font-bold text-slate-900 bg-slate-100 px-1.5 py-0.5 border border-slate-300">
                        {sample.temp_code}
                      </span>
                      <span className="text-slate-700 font-semibold uppercase">
                        {sample.profile === "heeled" ? "👠 Heeled" : "🥿 Flat"}
                      </span>
                      {sample.season && (
                        <span className="text-slate-700 font-semibold">
                          {sample.season}
                        </span>
                      )}
                      <span className="bg-slate-900 text-white font-bold px-1.5 py-0.5 text-[10px]">
                        PAGE {pageNumber} OF {totalPages}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 2 Photos Stacked (Filling ~90% of page height) */}
                <div className="flex-1 min-h-0 w-full flex flex-col gap-2 my-1 overflow-hidden">
                  {pair.map((p, idxInPair) => {
                    const globalPhotoIdx = pIdx * 2 + idxInPair + 1;
                    return (
                      <div
                        key={p.photo_id || idxInPair}
                        className="flex-1 min-h-0 w-full flex flex-col items-center justify-center border border-slate-200 bg-slate-50/40 p-1 relative overflow-hidden"
                      >
                        <img
                          src={resolveImageUrl(p.url)}
                          alt={p.caption || `Angle ${globalPhotoIdx}`}
                          className="w-full h-full object-contain"
                          style={{ maxHeight: "96mm", maxWidth: "100%" }}
                        />
                        <div className="absolute top-1.5 left-1.5 flex items-center gap-1">
                          <span className="bg-slate-900/85 text-white font-mono text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider">
                            Angle #{globalPhotoIdx}
                          </span>
                          {p.is_primary && (
                            <span className="bg-[#C27842] text-white font-mono text-[9px] font-bold px-1.5 py-0.5 uppercase">
                              Primary Cover
                            </span>
                          )}
                        </div>
                        {p.caption && (
                          <div className="absolute bottom-1.5 left-1.5 right-1.5 bg-slate-900/85 text-white font-mono text-[10px] px-2 py-0.5 text-center truncate">
                            {p.caption}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Footer on Photo Page */}
                <div className="border-t border-slate-300 pt-1 mt-auto shrink-0 flex items-center justify-between text-[9px] font-mono text-slate-500">
                  <span>SSK Footwear R&D &bull; Visual Reference Sheet</span>
                  <span>Style: {sample.temp_code} &bull; Page {pageNumber} of {totalPages}</span>
                  <span>Karigar / Tech: {sample.assigned_worker_name || "Unassigned"}</span>
                </div>
              </div>
            );
          })}

          {/* 2. FINAL PAGE:
              - If odd number of pictures (or 0 pictures): Tech Pack data sits directly below the last picture (saves 1 page)!
              - If even number of pictures (>0): Full-page dedicated Technical Specifications sheet */}
          {isOdd || photoCount === 0 ? (
            /* COMBINED FINAL PAGE: LAST PICTURE ON TOP + TECH PACK DATA BELOW IT */
            <div
              id="techpack-printable-sheet"
              className="techpack-page techpack-page-last w-full max-w-[190mm] mx-auto bg-white border border-slate-300 print:border flex flex-col justify-between p-2 print:p-1.5 box-border shadow-sm print:shadow-none"
            >
              {/* Header */}
              <div className="border-b border-slate-300 pb-1 mb-1 shrink-0">
                <div className="flex items-baseline justify-between">
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-slate-500">
                      SSK FOOTCARE &bull; TECH PACK SPECIFICATION
                    </span>
                    <h1 className="text-lg font-black text-slate-900 uppercase tracking-tight leading-tight">
                      {sample.sample_name}
                    </h1>
                  </div>

                  <div className="flex items-center gap-2 text-[11px] font-mono">
                    <span className="font-bold text-slate-900 bg-slate-100 px-1.5 py-0.5 border border-slate-300">
                      {sample.temp_code}
                    </span>
                    <span className="text-slate-700 font-semibold uppercase">
                      {sample.profile === "heeled" ? "👠 Heeled" : "🥿 Flat"}
                    </span>
                    {sample.season && (
                      <span className="text-slate-700 font-semibold">
                        {sample.season}
                      </span>
                    )}
                    <span className="bg-[#C27842] text-white font-bold px-1.5 py-0.5 text-[10px]">
                      PAGE {totalPages} OF {totalPages}
                    </span>
                  </div>
                </div>
              </div>

              {/* Visual Zone: Final / Odd Picture (fills ~75% space above the data box) */}
              <div className="techpack-image-zone flex-1 min-h-0 w-full my-1 flex items-center justify-center overflow-hidden bg-white relative border border-slate-100">
                {photoCount === 0 ? (
                  <div className="w-full h-full border border-dashed border-slate-300 flex flex-col items-center justify-center text-slate-400 p-4 text-center">
                    <Camera className="w-10 h-10 opacity-30 mb-1" />
                    <p className="font-bold text-xs uppercase tracking-wider text-slate-600">No Sample Inspiration Photos Uploaded</p>
                  </div>
                ) : (
                  <div className="w-full h-full flex items-center justify-center overflow-hidden relative">
                    <img
                      src={resolveImageUrl(lastOddPhoto.url)}
                      alt={lastOddPhoto.caption || sample.sample_name}
                      className="w-full h-full object-contain"
                      style={{ maxHeight: "120mm", maxWidth: "100%" }}
                    />
                    <div className="absolute top-1 left-1 flex items-center gap-1">
                      <span className="bg-slate-900/85 text-white font-mono text-[9px] font-bold px-1.5 py-0.5 uppercase tracking-wider">
                        {photoPages.length > 0 ? `Angle #${photoCount} (Final Angle)` : "Hero Cover"}
                      </span>
                      {lastOddPhoto.is_primary && (
                        <span className="bg-[#C27842] text-white font-mono text-[9px] font-bold px-1.5 py-0.5 uppercase">
                          Primary
                        </span>
                      )}
                    </div>
                    {lastOddPhoto.caption && (
                      <div className="absolute bottom-1 left-1 right-1 bg-slate-900/85 text-white font-mono text-[9px] px-2 py-0.5 text-center truncate">
                        {lastOddPhoto.caption}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Technical Specifications Strip (Fixed directly below the last picture) */}
              <div className="techpack-bottom-data shrink-0 w-full mt-auto border border-slate-300 bg-white">
                <div className="grid grid-cols-3 divide-x divide-slate-300">
                  
                  {/* Pillar 1: Upper Component */}
                  <div className="px-1.5 py-1 space-y-0.5 text-slate-900">
                    <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200 pb-0.5 mb-0.5 flex items-center justify-between">
                      <span>1. Upper Component</span>
                      {Array.isArray(upper.materials) && upper.materials.length > 1 && (
                        <span className="font-mono text-[8px] bg-slate-100 px-1 border border-slate-300">
                          {upper.materials.length} MATERIALS
                        </span>
                      )}
                    </div>

                    {Array.isArray(upper.materials) && upper.materials.length > 0 ? (
                      upper.materials.map((m, mIdx) => (
                        <div key={mIdx} className="text-[9px] leading-tight flex items-baseline justify-between gap-1">
                          <span className="font-semibold text-slate-600 truncate">{m.placement || `Mat #${mIdx + 1}`}: </span>
                          <span className="font-mono font-bold text-slate-900 truncate flex-1 ml-1">{m.material_name || "Pending"}</span>
                          {m.color_to_develop && (
                            <span className="font-mono text-[8px] font-bold text-blue-900 shrink-0">[{m.color_to_develop}]</span>
                          )}
                        </div>
                      ))
                    ) : (
                      <>
                        <div className="text-[10px] leading-tight">
                          <span className="font-semibold text-slate-500">Material: </span>
                          <span className="font-mono font-bold text-slate-900">{upper.upper_top_material_name || "Pending Selection"}</span>
                        </div>
                        <div className="text-[10px] leading-tight">
                          <span className="font-semibold text-slate-500">Color to Dev: </span>
                          <span className="font-mono font-bold text-blue-900">{upper.upper_color_to_develop || "N/A"}</span>
                        </div>
                      </>
                    )}

                    <div className="text-[9px] leading-tight">
                      <span className="font-semibold text-slate-500">Canvas / Lining: </span>
                      <span className="font-mono text-slate-800">{upper.canvas_backing || "None"} &bull; {upper.lining_material_name || "Std"}</span>
                    </div>
                    <div className="text-[9px] leading-tight">
                      <span className="font-semibold text-slate-500">Operations: </span>
                      <span className="font-mono text-slate-800 capitalize">
                        {[upper.cutting_operation?.replace("_", " "), upper.stitching_operation?.replace("_", " "), upper.edge_treatment?.replace("_", " ")].filter(Boolean).join(", ")}
                      </span>
                    </div>
                    {upper.has_buckle && (
                      <div className="text-[9px] leading-tight">
                        <span className="font-semibold text-slate-500">Buckle / Spec: </span>
                        <span className="font-mono font-bold text-amber-900">{upper.buckle_spec}</span>
                      </div>
                    )}

                    {/* Attached Swatch / Buckle Photo Thumbnails Row (Strictly conditional: 0px if no photos) */}
                    {((Array.isArray(upper.materials) && upper.materials.some(m => m.photo_url)) || upper.buckle_photo_url) && (
                      <div className="pt-1 mt-0.5 border-t border-slate-200 flex items-center gap-1.5 overflow-hidden">
                        {upper.materials?.filter(m => m.photo_url).map((m, mIdx) => (
                          <div key={mIdx} className="flex items-center gap-1 bg-slate-50 border border-slate-300 px-1 py-0.5 rounded">
                            <div className="w-6 h-6 rounded border border-slate-300 overflow-hidden shrink-0 bg-white">
                              <img src={resolveImageUrl(m.photo_url)} alt="swatch" className="w-full h-full object-cover" />
                            </div>
                            <span className="font-mono text-[7px] font-bold text-slate-700 uppercase tracking-tighter truncate max-w-[14mm]">
                              {m.placement || `Mat #${mIdx+1}`}
                            </span>
                          </div>
                        ))}
                        {upper.buckle_photo_url && (
                          <div className="flex items-center gap-1 bg-amber-50 border border-amber-300 px-1 py-0.5 rounded">
                            <div className="w-6 h-6 rounded border border-amber-400 overflow-hidden shrink-0 bg-white">
                              <img src={resolveImageUrl(upper.buckle_photo_url)} alt="buckle" className="w-full h-full object-cover" />
                            </div>
                            <span className="font-mono text-[7px] font-bold text-amber-900 uppercase tracking-tighter">
                              Buckle
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Pillar 2: Insole & Socks */}
                  <div className="px-1.5 py-1 space-y-0.5 text-slate-900">
                    <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200 pb-0.5 mb-0.5">
                      2. Insole / Socks
                    </div>
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Base Board: </span>
                      <span className="font-mono font-bold text-slate-900">{insole.base_board === "cellulose_board" ? "Cellulose" : "Paper Board"}</span>
                    </div>
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Cushioning: </span>
                      <span className="font-mono font-bold text-slate-900">{insole.cushioning_type?.toUpperCase()} &bull; {insole.cushioning_thickness_mm}</span>
                    </div>
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Socks Covering: </span>
                      <span className="font-mono text-slate-800 capitalize">
                        {insole.socks_covering_type === "matching" ? "Matching Upper" : (insole.socks_material_name || "Custom")}
                        {insole.socks_color ? ` · Color: ${insole.socks_color}` : " (Matching Upper)"}
                      </span>
                    </div>
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Detailing: </span>
                      <span className="font-mono text-slate-800 capitalize">{insole.surface_detailing || "None"} &bull; {insole.embossing || "None"}</span>
                    </div>
                  </div>

                  {/* Pillar 3: Sole & Heel */}
                  <div className="px-1.5 py-1 space-y-0.5 text-slate-900">
                    <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200 pb-0.5 mb-0.5">
                      3. Sole & Heel
                    </div>
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Sole Material: </span>
                      <span className="font-mono font-bold text-slate-900">{sole.sole_material || "TPR"} ({sole.sole_type || "Ready Made"})</span>
                    </div>
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Mould / Shape: </span>
                      <span className="font-mono font-bold text-slate-900">{sole.mould_name || "Standard"} ({sole.sole_shape || "Standard"})</span>
                    </div>
                    {sample.profile === "heeled" ? (
                      <div className="text-[10px] leading-tight">
                        <span className="font-semibold text-slate-500">Heel Spec: </span>
                        <span className="font-mono font-bold text-purple-900">{sole.heel_type} &bull; {sole.heel_finish} ({sole.heel_height || "Height TBD"})</span>
                      </div>
                    ) : (
                      <div className="text-[10px] leading-tight">
                        <span className="font-semibold text-slate-500">Profile: </span>
                        <span className="font-mono text-slate-800">Flat Footwear Mould</span>
                      </div>
                    )}
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500">Processes: </span>
                      <span className="font-mono text-slate-800">
                        {[sole.velting ? "Welting" : null, sole.grinding_gripping ? "Grinding" : null, sole.attach_top_piece ? "Top Piece" : null].filter(Boolean).join(", ") || "Standard"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sign-Off Footer Bar */}
                <div className="border-t border-slate-300 bg-slate-50/60 px-2 py-0.5 flex items-center justify-between text-[9px] font-mono text-slate-700">
                  <div><span className="font-semibold text-slate-600">Sample Master: </span> <span className="border-b border-slate-400 inline-block w-24">&nbsp;</span></div>
                  <div><span className="font-semibold text-slate-600">Footwear Designer: </span> <span className="border-b border-slate-400 inline-block w-24">&nbsp;</span></div>
                  <div><span className="font-semibold text-slate-600">Date / Approval: </span> <span className="border-b border-slate-400 inline-block w-16">&nbsp;</span></div>
                </div>
              </div>
            </div>
          ) : (
            /* DEDICATED FULL-PAGE TECHNICAL SPECIFICATIONS SHEET (FOR EVEN PHOTO COUNTS: 2, 4, 6) */
            <div
              className="techpack-page techpack-page-last w-full max-w-[190mm] mx-auto bg-white border border-slate-300 print:border flex flex-col justify-between p-2.5 print:p-2 box-border shadow-sm print:shadow-none"
            >
              {/* Header */}
              <div className="border-b-2 border-slate-900 pb-1 mb-1.5 shrink-0">
                <div className="flex items-baseline justify-between">
                  <div>
                    <span className="font-mono text-[9px] font-bold uppercase tracking-wider text-slate-500">
                      SSK FOOTCARE ERP &bull; TECHNICAL SPECIFICATIONS & WORK ORDER
                    </span>
                    <h1 className="text-lg font-black text-slate-900 uppercase tracking-tight leading-tight">
                      {sample.sample_name}
                    </h1>
                  </div>

                  <div className="flex items-center gap-1.5 text-xs font-mono">
                    <span className="font-bold text-white bg-slate-900 px-2 py-0.5 text-[11px]">
                      {sample.temp_code}
                    </span>
                    <span className="text-slate-800 font-bold uppercase text-[11px]">
                      {sample.profile === "heeled" ? "👠 Heeled" : "🥿 Flat"}
                    </span>
                    {sample.season && (
                      <span className="text-slate-700 font-semibold border border-slate-300 px-1.5 py-0.5 bg-slate-50 text-[11px]">
                        {sample.season}
                      </span>
                    )}
                    <span className="bg-[#C27842] text-white font-bold px-1.5 py-0.5 text-[10px]">
                      PAGE {totalPages} OF {totalPages}
                    </span>
                  </div>
                </div>
              </div>

              {/* Photo Thumbnail Reference Bar */}
              <div className="border border-slate-300 bg-slate-50 p-1 mb-1.5 shrink-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-slate-600">
                    Visual Reference Index ({photoCount} Photos across Sheets 1&ndash;{photoPages.length})
                  </span>
                  <span className="text-[8px] font-mono text-slate-500">
                    See preceding visual sheets for full-scale angles
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  {photos.map((p, idx) => (
                    <div key={p.photo_id || idx} className="h-8 w-10 border border-slate-300 bg-white shrink-0 overflow-hidden relative">
                      <img src={resolveImageUrl(p.url)} alt="thumb" className="w-full h-full object-cover" />
                      <span className="absolute bottom-0 right-0 bg-slate-900 text-white text-[7px] font-mono px-0.5 leading-none">
                        #{idx + 1}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 3 Pillars Technical Specifications */}
              <div className="grid grid-cols-3 gap-2 border border-slate-300 bg-white p-2 mb-1.5 shrink-0">
                
                {/* Pillar 1: Upper Component */}
                <div className="space-y-1 border-r border-slate-200 pr-2">
                  <div className="text-[9px] font-black uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-0.5 mb-1 flex items-center justify-between">
                    <span>1. Upper Component</span>
                    {Array.isArray(upper.materials) && upper.materials.length > 1 && (
                      <span className="font-mono text-[8px] bg-slate-100 px-1 border border-slate-300">
                        {upper.materials.length} MATERIALS
                      </span>
                    )}
                  </div>

                  {Array.isArray(upper.materials) && upper.materials.length > 0 ? (
                    upper.materials.map((m, mIdx) => (
                      <div key={mIdx} className="text-[10px] leading-tight pb-0.5">
                        <span className="font-semibold text-slate-500 block text-[8px] uppercase">
                          {m.placement || `Material #${mIdx + 1}`}
                        </span>
                        <span className="font-mono font-bold text-slate-900">
                          {m.material_name || "Pending Selection"}
                        </span>
                        {m.color_to_develop && (
                          <span className="font-mono font-bold text-blue-900 ml-1 text-[9px]">
                            [{m.color_to_develop}]
                          </span>
                        )}
                      </div>
                    ))
                  ) : (
                    <>
                      <div className="text-[10px] leading-tight">
                        <span className="font-semibold text-slate-500 block text-[8px] uppercase">Upper Material</span>
                        <span className="font-mono font-bold text-slate-900">{upper.upper_top_material_name || "Pending Selection"}</span>
                      </div>
                      <div className="text-[10px] leading-tight">
                        <span className="font-semibold text-slate-500 block text-[8px] uppercase">Color to Develop</span>
                        <span className="font-mono font-bold text-blue-900">{upper.upper_color_to_develop || "N/A"}</span>
                      </div>
                    </>
                  )}

                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Canvas Backing</span>
                    <span className="font-mono text-slate-800">{upper.canvas_backing || "None"}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Lining Material</span>
                    <span className="font-mono text-slate-800">{upper.lining_material_name || "Standard"}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Operations</span>
                    <span className="font-mono text-slate-800 capitalize">
                      {[upper.cutting_operation?.replace("_", " "), upper.stitching_operation?.replace("_", " "), upper.edge_treatment?.replace("_", " ")].filter(Boolean).join(", ") || "Standard"}
                    </span>
                  </div>
                  {upper.has_buckle && (
                    <div className="text-[10px] leading-tight bg-amber-50 border border-amber-200 p-1">
                      <span className="font-semibold text-amber-800 block text-[8px] uppercase">Buckle / Hardware</span>
                      <span className="font-mono font-bold text-amber-900">{upper.buckle_spec}</span>
                    </div>
                  )}

                  {/* Attached Swatch / Buckle Photo Gallery Row (Strictly conditional: 0px if no photos) */}
                  {((Array.isArray(upper.materials) && upper.materials.some(m => m.photo_url)) || upper.buckle_photo_url) && (
                    <div className="pt-1.5 mt-1 border-t border-slate-200 flex flex-wrap gap-1.5 items-center">
                      {upper.materials?.filter(m => m.photo_url).map((m, mIdx) => (
                        <div key={mIdx} className="flex items-center gap-1 bg-slate-50 border border-slate-300 px-1 py-0.5 rounded">
                          <div className="w-6 h-6 rounded border border-slate-300 overflow-hidden shrink-0 bg-white">
                            <img src={resolveImageUrl(m.photo_url)} alt="swatch" className="w-full h-full object-cover" />
                          </div>
                          <span className="font-mono text-[7px] font-bold text-slate-700 uppercase tracking-tighter truncate max-w-[16mm]">
                            {m.placement || `Mat #${mIdx+1}`}
                          </span>
                        </div>
                      ))}
                      {upper.buckle_photo_url && (
                        <div className="flex items-center gap-1 bg-amber-50 border border-amber-300 px-1 py-0.5 rounded">
                          <div className="w-6 h-6 rounded border border-amber-400 overflow-hidden shrink-0 bg-white">
                            <img src={resolveImageUrl(upper.buckle_photo_url)} alt="buckle" className="w-full h-full object-cover" />
                          </div>
                          <span className="font-mono text-[7px] font-bold text-amber-900 uppercase tracking-tighter">
                            Buckle
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Pillar 2: Insole & Socks */}
                <div className="space-y-1 border-r border-slate-200 pr-2">
                  <div className="text-[9px] font-black uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-0.5 mb-1">
                    2. Insole / Socks
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Base Board</span>
                    <span className="font-mono font-bold text-slate-900">{insole.base_board === "cellulose_board" ? "Cellulose Board" : "Paper Board"}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Cushioning Spec</span>
                    <span className="font-mono font-bold text-slate-900">{insole.cushioning_type?.toUpperCase()} &bull; {insole.cushioning_thickness_mm}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Socks Covering</span>
                    <span className="font-mono text-slate-800 capitalize">{insole.socks_covering_type === "matching" ? "Matching Upper" : (insole.socks_material_name || "Custom")}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Socks Color</span>
                    <span className="font-mono font-bold text-blue-900">{insole.socks_color ? insole.socks_color : "Matches Upper"}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Surface Detailing</span>
                    <span className="font-mono text-slate-800 capitalize">{insole.surface_detailing || "None"}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Embossing / Foil</span>
                    <span className="font-mono text-slate-800 capitalize">{insole.embossing || "None"}</span>
                  </div>
                </div>

                {/* Pillar 3: Sole & Heel */}
                <div className="space-y-1">
                  <div className="text-[9px] font-black uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-0.5 mb-1">
                    3. Sole & Heel
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Sole Material & Type</span>
                    <span className="font-mono font-bold text-slate-900">{sole.sole_material || "TPR"} &bull; {sole.sole_type || "Ready Made"}</span>
                  </div>
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Mould & Shape</span>
                    <span className="font-mono font-bold text-slate-900">{sole.mould_name || "Standard Mould"} &bull; {sole.sole_shape || "Standard"}</span>
                  </div>
                  {sample.profile === "heeled" ? (
                    <div className="text-[10px] leading-tight bg-purple-50 border border-purple-200 p-1">
                      <span className="font-semibold text-purple-800 block text-[8px] uppercase">Heel Specification</span>
                      <span className="font-mono font-bold text-purple-900">{sole.heel_type} &bull; {sole.heel_finish} ({sole.heel_height || "Height TBD"})</span>
                    </div>
                  ) : (
                    <div className="text-[10px] leading-tight">
                      <span className="font-semibold text-slate-500 block text-[8px] uppercase">Profile</span>
                      <span className="font-mono text-slate-800">Flat Footwear Standard</span>
                    </div>
                  )}
                  <div className="text-[10px] leading-tight">
                    <span className="font-semibold text-slate-500 block text-[8px] uppercase">Processes</span>
                    <span className="font-mono text-slate-800">
                      {[sole.velting ? "Welting" : null, sole.grinding_gripping ? "Grinding" : null, sole.attach_top_piece ? "Top Piece" : null].filter(Boolean).join(", ") || "Standard"}
                    </span>
                  </div>
                </div>

              </div>

              {/* Designer / Karigar Production Notes */}
              <div className="border border-slate-300 bg-slate-50 p-1.5 mb-1.5 shrink-0">
                <div className="text-[8px] font-bold uppercase tracking-wider text-slate-600 mb-0.5">
                  Designer & Karigar Instructions:
                </div>
                <div className="text-[9px] font-mono text-slate-800 leading-snug">
                  {sample.notes || "Develop sample strictly conforming to the reference photos. Maintain critical tolerances on cushion thickness, edge bevel, and sole bonding strength. Prioritize upper finishing accuracy."}
                </div>
              </div>

              {/* Approval & Sign-Off Bar (Anchored at Bottom) */}
              <div className="techpack-bottom-data shrink-0 w-full mt-auto border border-slate-400 bg-white p-2">
                <div className="text-[8px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-300 pb-0.5 mb-1.5">
                  Production Handover & Quality Sign-Off
                </div>
                <div className="grid grid-cols-3 gap-3 text-[9px] font-mono text-slate-800">
                  <div>
                    <div className="font-semibold text-slate-600 mb-3">Sample Master / Karigar:</div>
                    <div className="border-b border-slate-400">&nbsp;</div>
                    <div className="text-[7px] text-slate-400 mt-0.5">Signature & Date</div>
                  </div>
                  <div>
                    <div className="font-semibold text-slate-600 mb-3">Footwear Designer:</div>
                    <div className="border-b border-slate-400">&nbsp;</div>
                    <div className="text-[7px] text-slate-400 mt-0.5">Signature & Date</div>
                  </div>
                  <div>
                    <div className="font-semibold text-slate-600 mb-3">Quality / Production Approval:</div>
                    <div className="border-b border-slate-400">&nbsp;</div>
                    <div className="text-[7px] text-slate-400 mt-0.5">Signature & Date</div>
                  </div>
                </div>
              </div>

            </div>
          )}

        </div>

        {/* ── MODAL SCREEN FOOTER (Hidden in Print) ── */}
        <div className="px-5 py-3 border-t-2 border-slate-200 flex justify-between bg-slate-50 flex-shrink-0 print:hidden">
          <div className="flex items-center gap-3">
            <button onClick={onOpenEdit} className="text-xs font-bold uppercase tracking-wider text-slate-800 hover:text-[#C27842] hover:underline">
              Edit Full Spec
            </button>
            <span className="text-slate-300">|</span>
            <button onClick={onOpenPhotos} className="text-xs font-bold uppercase tracking-wider text-[#C27842] hover:underline">
              Manage Photos ({photos.length})
            </button>
          </div>
          <div className="flex items-center gap-2.5">
            {(() => {
              const isYieldActive = ["sample_ready", "approved", "transferred_to_style"].includes(sample.status);
              if (isYieldActive) {
                return (
                  <button
                    onClick={onOpenPatternYield}
                    className="h-9 px-4 bg-slate-900 hover:bg-slate-800 text-white font-bold uppercase tracking-wider text-xs border-2 border-slate-900 shadow-ind hover:shadow-ind-lg flex items-center justify-center gap-2 transition-all cursor-pointer"
                    title="A4 Pattern Scanner & 2D Yield Engine (Active - Sample Ready)"
                  >
                    <Scan className="w-3.5 h-3.5 text-amber-400" />
                    <span>Pattern & Yield</span>
                  </button>
                );
              }
              return (
                <button
                  disabled
                  className="h-9 px-4 bg-slate-100 text-slate-400 border-2 border-slate-300 font-bold uppercase tracking-wider text-xs flex items-center justify-center gap-2 cursor-not-allowed opacity-60"
                  title={`Yield calculation unlocks after sample is marked as 'Sample Ready' (current status: ${sample.status || 'draft'})`}
                >
                  <Lock className="w-3.5 h-3.5 text-slate-400" />
                  <span>Pattern & Yield (Locked)</span>
                </button>
              );
            })()}
            {sample.status !== "transferred_to_style" && (
              <button
                onClick={onOpenTransfer}
                className="h-9 px-4 bg-[#C27842] hover:bg-[#A65D24] text-white font-bold uppercase tracking-wider text-xs border-2 border-[#C27842] shadow-ind hover:shadow-ind-lg flex items-center justify-center gap-2 transition-all cursor-pointer"
              >
                Transfer to Style Master
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
