import { useEffect, useState } from "react";
import { Upload, X, Loader2 } from "lucide-react";
import { http } from "../lib/api";

/**
 * Reusable image uploader that hits `/api/upload/image` (Phase 1 backend).
 *
 * value:   either the full { url, display_url, thumbnail_url } object
 *          returned by the endpoint, or a legacy plain URL string
 *          (older records that predate the Pillow rework store just a url).
 * onChange: called with the full object once upload succeeds — parent
 *           forms should merge it into their `form` state.
 * label:    text shown above the drop zone (default "Image").
 * maxSizeMB: client-side pre-check for fast user feedback (server enforces
 *            its own 8MB cap regardless).
 * testIdPrefix: allows two uploaders on the same page to have unique test ids.
 */
export default function ImageUploader({
  value,
  onChange,
  label = "Image",
  maxSizeMB = 8,
  testIdPrefix = "image",
}) {
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState("");
  const [fallbackToThumb, setFallbackToThumb] = useState(false);
  const [fallbackToPlaceholder, setFallbackToPlaceholder] = useState(false);

  // Normalise: `value` may be a string (legacy) or the full object
  const asObj =
    typeof value === "string"
      ? { url: value, display_url: value, thumbnail_url: value }
      : value || {};
  const hasImage = !!(asObj.url || asObj.display_url || asObj.thumbnail_url);

  const previewSrc = fallbackToThumb
    ? asObj.thumbnail_url || asObj.url || ""
    : asObj.display_url || asObj.url || asObj.thumbnail_url || "";

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setErr("");
    if (file.size > maxSizeMB * 1024 * 1024) {
      setErr(
        `Image too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Max ${maxSizeMB}MB.`
      );
      e.target.value = "";
      return;
    }
    if (!/^image\/(png|jpe?g|webp|gif)$/i.test(file.type)) {
      setErr("Only PNG, JPG, WEBP, or GIF allowed.");
      e.target.value = "";
      return;
    }

    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      const res = await http.post("/upload/image", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const { url, original_url, display_url, thumbnail_url, width, height } =
        res.data || {};
      onChange({
        url: url || original_url || "",
        original_url: original_url || url || "",
        display_url: display_url || url || "",
        thumbnail_url: thumbnail_url || display_url || url || "",
        width,
        height,
      });
      setFallbackToThumb(false);
      setFallbackToPlaceholder(false);
    } catch (er) {
      setErr(er?.response?.data?.detail || er?.message || "Upload failed.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const clear = () => {
    onChange({ url: "", original_url: "", display_url: "", thumbnail_url: "" });
    setFallbackToThumb(false);
    setFallbackToPlaceholder(false);
    setErr("");
  };

  /**
   * Normalize common share-link formats (Dropbox, OneDrive, Google Drive) to
   * direct-download URLs the browser's <img> tag can actually render.
   * - Dropbox share (www.dropbox.com/...?dl=0)
   *     → dl.dropboxusercontent.com/... (or dl=1); works for both /s/ and /scl/fi/ paths.
   * - OneDrive short (1drv.ms) + full share URLs
   *     → api.onedrive.com/v1.0/shares/u!<b64url>/root/content
   * - Google Drive share (/file/d/<id>/view or open?id=<id>)
   *     → drive.google.com/uc?export=view&id=<id>
   * Returns the original string if no rule matched.
   */
  const normalizeImageUrl = (raw) => {
    if (!raw || typeof raw !== "string") return raw;
    let val = raw.trim();
    // Strip anything wrapped in HTML like <img src="...">
    const srcMatch = val.match(/src=["'](.*?)["']/i);
    if (srcMatch && srcMatch[1]) val = srcMatch[1];

    try {
      const u = new URL(val);

      // ---- DROPBOX --------------------------------------------------------
      // www.dropbox.com/s/… or www.dropbox.com/scl/fi/… — swap host + drop dl=0.
      if (/(^|\.)dropbox\.com$/i.test(u.hostname) && u.hostname !== "dl.dropboxusercontent.com") {
        u.hostname = "dl.dropboxusercontent.com";
        // Some Dropbox links carry `dl=0`; the direct host ignores it but we
        // strip it for cleanliness. Also handle the (rarer) `raw=1` param.
        u.searchParams.delete("dl");
        return u.toString();
      }

      // ---- ONEDRIVE (1drv.ms shortlink OR onedrive.live.com share URL) ----
      // The public "shares API" trick: base64url-encode the FULL share URL
      // and open it at /shares/u!<b64>/root/content — returns the raw file
      // and works from <img> tags (no auth needed for anyone-with-link shares).
      if (
        u.hostname === "1drv.ms" ||
        /(^|\.)onedrive\.live\.com$/i.test(u.hostname)
      ) {
        const b64 = btoa(val)
          .replace(/=+$/g, "") // strip padding
          .replace(/\//g, "_")
          .replace(/\+/g, "-");
        return `https://api.onedrive.com/v1.0/shares/u!${b64}/root/content`;
      }

      // ---- GOOGLE DRIVE ---------------------------------------------------
      if (/(^|\.)drive\.google\.com$/i.test(u.hostname)) {
        // /file/d/<id>/view  or  /file/d/<id>/edit
        const m = u.pathname.match(/\/file\/d\/([^/]+)/);
        const id = m ? m[1] : u.searchParams.get("id");
        if (id) {
          return `https://drive.google.com/uc?export=view&id=${id}`;
        }
      }
    } catch {
      // Not a valid URL — return as-is so the user sees their own input.
    }
    return val;
  };

  const pasteUrl = (e) => {
    const val = normalizeImageUrl(e.target.value);
    onChange({
      url: val,
      original_url: val,
      display_url: val,
      thumbnail_url: val,
    });
    setFallbackToThumb(false);
    setFallbackToPlaceholder(false);
  };

  return (
    <div data-testid={`${testIdPrefix}-uploader`}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
        {label}{" "}
        <span className="text-slate-400 font-normal normal-case">
          (max {maxSizeMB}MB)
        </span>
      </div>
      <div className="flex gap-3 items-start">
        <div className="w-28 h-28 border-2 border-dashed border-slate-300 bg-slate-50 grid place-items-center overflow-hidden flex-shrink-0">
          {hasImage && !fallbackToPlaceholder ? (
            <img
              src={previewSrc}
              alt="preview"
              className="w-full h-full object-cover"
              data-testid={`${testIdPrefix}-preview`}
              onError={() => {
                if (!fallbackToThumb) setFallbackToThumb(true);
                else setFallbackToPlaceholder(true);
              }}
            />
          ) : (
            <div className="text-center">
              <div className="text-3xl mb-1">👟</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400 font-bold">
                No Image
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-col justify-center flex-1 min-w-[200px]">
          <div className="flex items-center gap-2 mb-2">
            <label
              className={`inline-block bg-white text-slate-900 font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-slate-300 hover:border-[#0F172A] transition-colors ${
                uploading ? "opacity-50 pointer-events-none" : "cursor-pointer"
              }`}
              data-testid={`${testIdPrefix}-upload-label`}
            >
              {uploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 inline -mt-0.5 mr-1 animate-spin" />{" "}
                  Uploading
                </>
              ) : (
                <>
                  <Upload className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Upload
                  File
                </>
              )}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                onChange={onFile}
                disabled={uploading}
                data-testid={`${testIdPrefix}-upload-input`}
              />
            </label>
            <span className="text-[10px] text-slate-400 font-bold">OR</span>
            <input
              type="text"
              placeholder="Paste image URL"
              className="flex-1 bg-white border-2 border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-slate-500"
              value={asObj.url || ""}
              onChange={pasteUrl}
              data-testid={`${testIdPrefix}-url-input`}
            />
          </div>
          {hasImage && (
            <button
              type="button"
              onClick={clear}
              className="text-xs uppercase tracking-wider text-slate-500 hover:text-red-600 font-bold self-start inline-flex items-center gap-1"
              data-testid={`${testIdPrefix}-clear`}
            >
              <X className="w-3 h-3" /> Clear Image
            </button>
          )}
          {err && (
            <div
              className="mt-1 text-[11px] font-medium text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1"
              data-testid={`${testIdPrefix}-error`}
            >
              {err}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Compact thumbnail component for table rows / BOM lists / picker menus.
 * Falls back gracefully: display_url → thumbnail_url → 👟 placeholder.
 *
 * `clickable`: when true, clicking the thumbnail opens a lightbox modal
 * showing the full-size display_url with backdrop dismissal (ESC key + click).
 */
export function ImageThumb({
  image,
  size = 36,
  alt = "",
  className = "",
  testId,
  clickable = false,
}) {
  const [broken, setBroken] = useState(false);
  const [open, setOpen] = useState(false);

  const asObj =
    typeof image === "string"
      ? { url: image, thumbnail_url: image, display_url: image }
      : image || {};
  const src = asObj.thumbnail_url || asObj.display_url || asObj.url || "";
  const lightboxSrc =
    asObj.display_url || asObj.url || asObj.thumbnail_url || "";

  // ESC to close
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!src || broken) {
    return (
      <div
        className={`bg-slate-100 border border-slate-200 grid place-items-center text-slate-400 text-base ${className}`}
        style={{ width: size, height: size }}
        data-testid={testId}
        title="No image"
      >
        👟
      </div>
    );
  }

  const imgEl = (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setBroken(true)}
      className={`object-cover border border-slate-200 ${className} ${
        clickable ? "cursor-zoom-in hover:opacity-80 transition-opacity" : ""
      }`}
      style={{ width: size, height: size }}
      data-testid={testId}
      onClick={clickable ? () => setOpen(true) : undefined}
    />
  );

  if (!clickable || !open) return imgEl;

  return (
    <>
      {imgEl}
      {/* Lightbox modal */}
      <div
        role="dialog"
        aria-modal="true"
        className="fixed inset-0 z-[200] bg-black/85 flex items-center justify-center p-6 cursor-zoom-out"
        onClick={() => setOpen(false)}
        data-testid={`${testId || "image-thumb"}-lightbox`}
      >
        <div
          className="relative max-w-[90vw] max-h-[90vh] bg-white shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="absolute -top-3 -right-3 bg-white border-2 border-slate-900 w-8 h-8 grid place-items-center hover:bg-red-50 hover:border-red-600 transition-colors"
            data-testid={`${testId || "image-thumb"}-lightbox-close`}
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
          <img
            src={lightboxSrc}
            alt={alt}
            className="max-w-[90vw] max-h-[90vh] object-contain block"
            onError={(e) => {
              // Prefer display_url; fall back to url; then to thumbnail_url
              const chain = [asObj.display_url, asObj.url, asObj.thumbnail_url].filter(
                Boolean
              );
              const nextIdx =
                chain.indexOf(e.currentTarget.src.replace(/\?.*$/, "")) + 1;
              if (nextIdx < chain.length) {
                e.currentTarget.src = chain[nextIdx];
              }
            }}
          />
          {alt && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-white text-xs px-3 py-2 font-mono tracking-wide">
              {alt}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/**
 * SafeImage — the definitive display component for style/material images in
 * grid cards, detail drawers, and any medium-sized container.
 *
 * Enforces:
 *   • fallback chain display_url → url → thumbnail_url → 👟 placeholder
 *   • fixed aspect ratio wrapper (prevents layout shift while loading)
 *   • loading="lazy" for grid/list contexts (dozens of thumbnails at once)
 *   • graceful placeholder — never a broken-image icon
 *
 * Props:
 *   image:       either a full {url, display_url, thumbnail_url} object OR a
 *                bare URL string (bulk-uploaded / CSV-imported styles carry
 *                only the raw URL — this component treats it as all three).
 *   alt, className, testId : standard passthrough.
 *   aspectRatio: e.g. "4/3", "1", "16/9" — tailwind arbitrary-value class
 *                (default "4/3", matches the current card grid height).
 *   fit:         object-fit variant, "cover" (default) or "contain".
 */
export function SafeImage({
  image,
  alt = "",
  className = "",
  testId,
  aspectRatio = "4/3",
  fit = "cover",
}) {
  const [errStep, setErrStep] = useState(0); // 0=try display, 1=thumb, 2=placeholder
  const asObj =
    typeof image === "string"
      ? { url: image, display_url: image, thumbnail_url: image }
      : image || {};

  const chain = Array.from(
    new Set(
      [
        asObj.display_url || asObj.url,
        asObj.thumbnail_url || asObj.url,
        asObj.url,
      ].filter(Boolean)
    )
  );
  const currentSrc = chain[errStep];
  const showPlaceholder = !currentSrc;

  const wrapperStyle = { aspectRatio };
  const wrapperClass = `relative overflow-hidden bg-slate-100 ${className}`;

  if (showPlaceholder) {
    return (
      <div
        className={`${wrapperClass} grid place-items-center`}
        style={wrapperStyle}
        data-testid={testId}
      >
        <div className="text-center">
          <div className="text-3xl mb-1">👟</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400 font-bold">
            No Image
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={wrapperClass} style={wrapperStyle} data-testid={testId}>
      <img
        src={currentSrc}
        alt={alt}
        loading="lazy"
        onError={() => {
          if (errStep < chain.length - 1) setErrStep(errStep + 1);
          else setErrStep(chain.length); // trigger placeholder branch on next render
        }}
        className={`w-full h-full ${fit === "contain" ? "object-contain" : "object-cover"}`}
      />
    </div>
  );
}
