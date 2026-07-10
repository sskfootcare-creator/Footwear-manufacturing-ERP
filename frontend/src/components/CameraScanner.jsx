import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { Camera, X, RotateCw, AlertTriangle } from "lucide-react";

/**
 * CameraScanner — mobile-first barcode/QR scanner overlay.
 * Uses the phone's rear camera by default; falls back to any available camera.
 * Continuously reads until either `onScan(text)` returns truthy (success) or
 * the user closes the modal. Supports both QR codes and standard 1D barcodes.
 *
 * Props:
 *   onScan(text)  — required. Called with the decoded string. Return `true` to
 *                   stop scanning (single-shot), or `false`/nothing to keep
 *                   scanning (multi-shot mode for consecutive picks).
 *   onClose()     — required.
 *   expected      — optional. If provided, the overlay highlights the
 *                   expected code so pickers know what they're looking for.
 *
 * Under the hood we drive `Html5Qrcode` directly (not the wrapper `Html5QrcodeScanner`)
 * because we want a custom UI. `fps: 10` keeps CPU usage low; `qrbox` is
 * responsive.
 */
export default function CameraScanner({ onScan, onClose, expected }) {
  const containerRef = useRef(null);
  const scannerRef   = useRef(null);
  const onScanRef    = useRef(onScan);
  useEffect(() => { onScanRef.current = onScan; }, [onScan]);
  const [cameraId, setCameraId]   = useState(null);
  const [cameras, setCameras]     = useState([]);
  const [error, setError]         = useState("");
  const [scanning, setScanning]   = useState(false);
  const [lastHit, setLastHit]     = useState("");

  // Enumerate cameras once — prefer rear-facing.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const devices = await Html5Qrcode.getCameras();
        if (cancelled) return;
        if (!devices || devices.length === 0) {
          setError("No camera found on this device.");
          return;
        }
        setCameras(devices);
        // Try to auto-select the rear camera (contains "back" or "environment")
        const rear = devices.find((d) =>
          /back|rear|environment/i.test(d.label || "")
        ) || devices[devices.length - 1];
        setCameraId(rear.id);
      } catch (e) {
        setError(
          e?.message?.includes("Permission") || e?.name === "NotAllowedError"
            ? "Camera permission denied. Enable it in your browser settings and reload."
            : `Camera error: ${e?.message || e}`
        );
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Start / restart scanning whenever the chosen camera changes.
  // We create a dedicated child div for Html5Qrcode inside the wrapper ref so
  // React never owns the DOM Html5Qrcode mutates — this avoids the classic
  // "removeChild ... not a child of this node" crash when React unmounts.
  useEffect(() => {
    if (!cameraId || !containerRef.current) return;
    let cancelled = false;
    const wrapper = containerRef.current;
    // Dedicated div React does NOT own. Html5Qrcode is free to inject children.
    const targetId = `ssk-cam-target-${Math.random().toString(36).slice(2)}`;
    const target   = document.createElement("div");
    target.id      = targetId;
    target.style.width  = "100%";
    target.style.height = "100%";
    wrapper.appendChild(target);

    let html5 = null;
    const startTimer = setTimeout(startScanner, 60);

    async function startScanner() {
      if (cancelled) return;
      try {
        html5 = new Html5Qrcode(targetId);
        scannerRef.current = html5;
        setScanning(true);
        setError("");
        await html5.start(
          cameraId,
          {
            fps: 10,
            qrbox: (viewfinderWidth, viewfinderHeight) => {
              const w = viewfinderWidth  || 300;
              const h = viewfinderHeight || 300;
              const side = Math.max(160, Math.min(w, h) * 0.75);
              return { width: side, height: side };
            },
          },
          (decodedText) => {
            if (cancelled) return;
            setLastHit(decodedText);
            Promise.resolve(onScanRef.current(decodedText)).then((stop) => {
              if (stop && scannerRef.current) {
                scannerRef.current.stop().catch(() => {});
              }
            });
          },
          () => { /* per-frame decode failures — noisy, ignore */ },
        );
      } catch (e) {
        if (cancelled) return;
        setError(
          e?.message?.includes("Permission") || e?.name === "NotAllowedError"
            ? "Camera permission denied. Please allow camera access and try again."
            : `Could not start camera: ${e?.message || e}`
        );
        setScanning(false);
      }
    }

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      const sc = html5;
      scannerRef.current = null;
      const cleanup = () => {
        // Remove our dedicated div (with all Html5Qrcode's injected children)
        // from the wrapper — safe because it's OUR node, not React's.
        try {
          if (target.parentNode === wrapper) wrapper.removeChild(target);
        } catch { /* ignore */ }
      };
      if (sc) {
        // getState() === 2 means SCANNING; anything else means we shouldn't stop.
        try {
          const state = typeof sc.getState === "function" ? sc.getState() : null;
          if (state === 2) {
            sc.stop().catch(() => {}).finally(cleanup);
          } else {
            cleanup();
          }
        } catch { cleanup(); }
      } else {
        cleanup();
      }
    };
  }, [cameraId]);

  const switchCamera = () => {
    if (cameras.length < 2) return;
    const idx = cameras.findIndex((c) => c.id === cameraId);
    setCameraId(cameras[(idx + 1) % cameras.length].id);
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/90 flex items-center justify-center p-2 sm:p-6" data-testid="camera-scanner">
      <div className="w-full max-w-md bg-black border-2 border-slate-700 overflow-hidden">
        <div className="px-3 py-2 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <Camera className="w-4 h-4 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Camera Scan</div>
              {expected && (
                <div className="text-xs font-mono truncate">Expecting: <strong>{expected}</strong></div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            {cameras.length > 1 && (
              <button
                onClick={switchCamera}
                className="p-1.5 text-white hover:bg-slate-800"
                title="Switch camera"
                data-testid="cam-switch"
              >
                <RotateCw className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-white hover:bg-slate-800"
              title="Close"
              data-testid="cam-close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Wrapper is React-owned. Html5Qrcode's target div is injected
            dynamically inside it so React never touches the scanner's DOM. */}
        <div ref={containerRef} className="w-full aspect-square bg-black relative">
          {!scanning && !error && (
            <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-xs">
              Starting camera…
            </div>
          )}
        </div>

        {/* Status strip */}
        <div className="px-3 py-2 bg-slate-900 text-xs text-slate-300">
          {error ? (
            <div className="flex items-start gap-2 text-red-300" data-testid="cam-error">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          ) : lastHit ? (
            <div>Last scan: <span className="font-mono text-emerald-300">{lastHit}</span></div>
          ) : (
            <div>Align the code inside the frame. QR + 1D barcodes both supported.</div>
          )}
        </div>
      </div>
    </div>
  );
}
