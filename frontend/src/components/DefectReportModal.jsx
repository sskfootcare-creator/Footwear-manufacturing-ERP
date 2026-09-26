import React, { useState } from "react";
import { Camera, Upload, X, AlertOctagon, CheckCircle2, Loader2, Image as ImageIcon } from "lucide-react";

/**
 * DefectReportModal (U-005)
 * Defect reporting with photo attachment for quality disputes and root-cause review.
 */
export default function DefectReportModal({
  isOpen,
  onClose,
  initialStyle = null,
  onSuccess,
}) {
  const [styleId, setStyleId] = useState(initialStyle?.style_id || "");
  const [color, setColor] = useState(initialStyle?.color || "");
  const [size, setSize] = useState(initialStyle?.size || "");
  const [quantity, setQuantity] = useState(1);
  const [defectCategory, setDefectCategory] = useState("sole_separation");
  const [defectReason, setDefectReason] = useState("");
  const [notes, setNotes] = useState("");
  const [photoUrls, setPhotoUrls] = useState([]);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploadingPhoto(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", files[0]);

      const res = await fetch("/api/upload/image", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Image upload failed");
      }
      const data = await res.json();
      const url = data.url || data.key;
      if (url) {
        setPhotoUrls([...photoUrls, url]);
      }
    } catch (err) {
      setError("Failed to upload defect photo. Please ensure it is a valid JPEG/PNG image.");
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!styleId || !color || !size || !defectReason) {
      setError("Please complete all required fields");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/inventory/defect-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          style_id: styleId,
          color,
          size,
          quantity: parseInt(quantity, 10),
          defect_category: defectCategory,
          defect_reason: defectReason,
          photo_urls: photoUrls,
          notes,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to record defect report");
      }

      const result = await res.json();
      if (onSuccess) onSuccess(result);
      onClose();
    } catch (err) {
      setError(err.message || "Failed to submit defect report");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-lg w-full p-6 shadow-2xl text-white">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <AlertOctagon className="w-6 h-6 text-rose-500" />
            <h3 className="font-bold text-lg">Log Quality Defect & Evidence</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-xl hover:bg-slate-800 text-slate-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="py-4 space-y-4">
          {error && (
            <div className="bg-rose-950/60 border border-rose-800 p-3 rounded-xl text-xs text-rose-300">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-300">Style ID / Code *</label>
              <input
                type="text"
                required
                value={styleId}
                onChange={(e) => setStyleId(e.target.value)}
                placeholder="Style code or ID"
                className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-300">Defect Quantity (Pairs) *</label>
              <input
                type="number"
                min="1"
                required
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-300">Color *</label>
              <input
                type="text"
                required
                value={color}
                onChange={(e) => setColor(e.target.value)}
                placeholder="e.g. Tan"
                className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-300">Size *</label>
              <input
                type="text"
                required
                value={size}
                onChange={(e) => setSize(e.target.value)}
                placeholder="e.g. 8"
                className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-300">Defect Category *</label>
            <select
              value={defectCategory}
              onChange={(e) => setDefectCategory(e.target.value)}
              className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              <option value="sole_separation">Sole Separation / Bonding Failure</option>
              <option value="stitching_fault">Stitching Tear / Loose Thread</option>
              <option value="upper_tear">Upper Material Scratch / Tear</option>
              <option value="color_bleed">Color Shading / Bleed</option>
              <option value="sizing_mismatch">Sizing / Last Asymmetry</option>
              <option value="other">Other Quality Discrepancy</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-300">Defect Reason / Root Cause *</label>
            <input
              type="text"
              required
              value={defectReason}
              onChange={(e) => setDefectReason(e.target.value)}
              placeholder="e.g. Inadequate adhesive temperature on toe wrap"
              className="mt-1 w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Photo Upload Zone */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Photographic Evidence
            </label>
            <div className="flex flex-wrap gap-2 items-center">
              {photoUrls.map((url, idx) => (
                <div key={idx} className="relative w-16 h-16 rounded-xl border border-slate-700 overflow-hidden bg-slate-800">
                  <img src={url} alt="Evidence" className="w-full h-full object-cover" />
                  <button
                    type="button"
                    onClick={() => setPhotoUrls(photoUrls.filter((_, i) => i !== idx))}
                    className="absolute top-1 right-1 p-0.5 rounded-full bg-black/70 text-white hover:bg-rose-600"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}

              <label className="w-16 h-16 rounded-xl border-2 border-dashed border-slate-700 hover:border-slate-500 bg-slate-800/50 flex flex-col items-center justify-center cursor-pointer text-slate-400 hover:text-white transition-colors">
                {uploadingPhoto ? (
                  <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                ) : (
                  <>
                    <Camera className="w-5 h-5" />
                    <span className="text-[9px] mt-0.5 font-bold">Add</span>
                  </>
                )}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handleFileUpload}
                  disabled={uploadingPhoto}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-sm font-bold flex items-center gap-1.5 transition-colors"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <AlertOctagon className="w-4 h-4" />}
              Submit Defect Report
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
