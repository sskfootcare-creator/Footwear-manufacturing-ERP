import React, { useEffect, useState } from "react";
import { X, ExternalLink, Maximize2, AlertCircle, Loader2 } from "lucide-react";

/**
 * ImageViewModal
 * Reusable modal for full-size preview of footwear styles and item images.
 * Supports ESC to close, click-outside to close, high-res loading, and external view.
 */
export default function ImageViewModal({
  isOpen = true,
  src,
  alt = "Preview",
  title = "Image Preview",
  subtitle = null,
  onClose,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
  }, [src]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose?.();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !src) return null;

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-150"
      onClick={onClose}
      data-testid="image-view-modal"
    >
      <div
        className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-4xl max-h-[92vh] w-full overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-slate-950/80 border-b border-slate-800 text-white shrink-0">
          <div className="min-w-0 pr-3">
            <h3 className="text-sm sm:text-base font-bold text-slate-100 truncate flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-[#C27842]" />
              {title}
            </h3>
            {subtitle && (
              <p className="text-xs text-slate-400 truncate mt-0.5 font-medium">
                {subtitle}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <a
              href={src}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
              title="Open original image in new tab"
              data-testid="image-modal-external-link"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
              title="Close (Esc)"
              data-testid="image-modal-close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content / Image Area */}
        <div className="relative flex-1 bg-slate-950 flex items-center justify-center p-4 min-h-[300px] max-h-[calc(92vh-64px)] overflow-hidden">
          {loading && !error && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-2">
              <Loader2 className="w-7 h-7 animate-spin text-[#C27842]" />
              <span className="text-xs font-medium">Loading high-resolution image…</span>
            </div>
          )}

          {error ? (
            <div className="flex flex-col items-center justify-center text-slate-400 p-8 text-center">
              <AlertCircle className="w-10 h-10 text-amber-500 mb-2" />
              <p className="text-sm font-semibold text-slate-200">Unable to load image</p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm truncate">{src}</p>
            </div>
          ) : (
            <img
              src={src}
              alt={alt}
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false);
                setError(true);
              }}
              className={`max-w-full max-h-[75vh] w-auto h-auto object-contain rounded-lg transition-opacity duration-200 ${
                loading ? "opacity-0" : "opacity-100"
              }`}
              data-testid="image-modal-img"
            />
          )}
        </div>
      </div>
    </div>
  );
}
