import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { Camera, X, RotateCw, AlertTriangle, Keyboard } from "lucide-react";

/**
 * CameraScanner — mobile-first barcode/QR scanner overlay.
 * Uses the phone's rear camera (`facingMode: "environment"`) by default.
 * Continuously reads until either `onScan(text)` returns truthy (success) or
 * the user closes the modal. Supports both QR codes and standard 1D barcodes.
 * Includes a manual input fallback if camera permission is denied or camera fails.
 *
 * Props:
 *   onScan(text)  — required. Called with the decoded string. Return `true` to
 *                   stop scanning (single-shot), or `false`/nothing to keep
 *                   scanning (multi-shot mode for consecutive picks).
 *   onClose()     — required.
 *   expected      — optional. If provided, the overlay highlights the
 *                   expected code so pickers know what they're looking for.
 */
export default function CameraScanner({ onScan, onClose, expected }) {
  const containerRef = useRef(null);
  const scannerRef   = useRef(null);
  const onScanRef    = useRef(onScan);
  useEffect(() => { onScanRef.current = onScan; }, [onScan]);

  // cameraTarget can be a device ID string OR constraint object { facingMode: "environment" }
  const [cameraTarget, setCameraTarget] = useState({ facingMode: "environment" });
  const [cameras, setCameras]           = useState([]);
  const [error, setError]               = useState("");
  const [scanning, setScanning]         = useState(false);
  const [lastHit, setLastHit]           = useState("");
  const [manualInput, setManualInput]   = useState(expected || "");

  // Enumerate cameras if permitted to support explicit switching between front/rear.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const devices = await Html5Qrcode.getCameras();
        if (cancelled) return;
        if (devices && devices.length > 0) {
          setCameras(devices);
          const rear = devices.find((d) =>
            /back|rear|environment/i.test(d.label || "")
          );
          if (rear) {
            setCameraTarget(rear.id);
          }
        }
      } catch (e) {
        // Ignored here — startScanner will capture and surface any camera initialization error
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Start / restart scanning whenever the chosen camera target changes.
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;
    const wrapper = containerRef.current;
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
          cameraTarget,
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
            ? "Camera permission denied. Allow camera access in your browser or type the code manually below."
            : `Could not start camera (${e?.message || e}). Type code manually below.`
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
        try {
          if (target.parentNode === wrapper) wrapper.removeChild(target);
        } catch { /* ignore */ }
      };
      if (sc) {
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
  }, [cameraTarget]);

  const switchCamera = () => {
    if (cameras.length < 2) return;
    const currentId = typeof cameraTarget === "string" ? cameraTarget : "";
    const idx = cameras.findIndex((c) => c.id === currentId);
    const nextCam = cameras[(idx + 1) % cameras.length];
    setCameraTarget(nextCam.id);
  };

  const handleManualSubmit = (e) => {
    e.preventDefault();
    const val = manualInput.trim();
    if (!val) return;
    setLastHit(val);
    Promise.resolve(onScanRef.current(val)).then((stop) => {
      if (stop) onClose();
    });
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-2 sm:p-6 max-h-[100dvh] overflow-y-auto" data-testid="camera-scanner">
      <div className="w-full max-w-md bg-black border-2 border-slate-700 overflow-hidden shadow-2xl my-auto">
        {/* Header */}
        <div className="px-3 py-2.5 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <Camera className="w-4 h-4 flex-shrink-0 text-amber-400" />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Barcode / QR Scanner</div>
              {expected && (
                <div className="text-xs font-mono truncate text-amber-300">Expecting: <strong>{expected}</strong></div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            {cameras.length > 1 && (
              <button
                onClick={switchCamera}
                className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center text-white hover:bg-slate-800 touch-manipulation"
                title="Switch camera"
                data-testid="cam-switch"
              >
                <RotateCw className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center text-white hover:bg-slate-800 touch-manipulation"
              title="Close"
              data-testid="cam-close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Camera Feed Container */}
        <div ref={containerRef} className="w-full aspect-square bg-black relative">
          {!scanning && !error && (
            <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-xs">
              Starting rear camera…
            </div>
          )}
        </div>

        {/* Status Strip */}
        <div className="px-3 py-2 bg-slate-900 text-xs text-slate-300 border-t border-slate-800">
          {error ? (
            <div className="flex items-start gap-2 text-amber-300" data-testid="cam-error">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5 text-amber-400" />
              <span>{error}</span>
            </div>
          ) : lastHit ? (
            <div>Last scan: <span className="font-mono font-bold text-emerald-400">{lastHit}</span></div>
          ) : (
            <div>Point camera at barcode or QR code. Rear camera active by default.</div>
          )}
        </div>

        {/* Manual Fallback Entry Form */}
        <form onSubmit={handleManualSubmit} className="p-3 bg-slate-950 border-t border-slate-800 space-y-1.5" data-testid="cam-manual-form">
          <div className="text-[10px] uppercase font-bold text-slate-400 flex items-center gap-1">
            <Keyboard className="w-3 h-3 text-slate-400" /> Manual Code Entry
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={manualInput}
              onChange={(e) => setManualInput(e.target.value)}
              placeholder={expected || "Type or paste barcode"}
              className="flex-1 bg-slate-900 border border-slate-700 px-3 py-2 text-xs text-white font-mono min-h-[44px] focus:outline-none focus:border-amber-500"
              data-testid="cam-manual-input"
            />
            <button
              type="submit"
              disabled={!manualInput.trim()}
              className="px-4 py-2 bg-[#C27842] hover:bg-[#A65D24] text-white font-bold text-xs uppercase tracking-wider min-h-[44px] disabled:opacity-50 touch-manipulation"
              data-testid="cam-manual-submit"
            >
              Submit
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
