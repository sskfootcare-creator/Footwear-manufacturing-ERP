import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { http, friendlyAxiosError, inr } from "@/lib/api";
import {
  HardHat, LogOut, CheckCircle2, Clock, Package, IndianRupee,
  RefreshCw, ChevronRight, Loader2, FileText, Download, X, Eye, Layers
} from "lucide-react";

// ── karigar-scoped HTTP helper ────────────────────────────────────────────────
function karigarHttp() {
  const token = localStorage.getItem("karigar_token") || localStorage.getItem("token");
  return {
    get: (url, cfg) => http.get(url, { ...cfg, headers: { ...(cfg?.headers || {}), Authorization: `Bearer ${token}` } }),
    post: (url, data, cfg) => http.post(url, data, { ...cfg, headers: { ...(cfg?.headers || {}), Authorization: `Bearer ${token}` } }),
    patch: (url, data, cfg) => http.patch(url, data, { ...cfg, headers: { ...(cfg?.headers || {}), Authorization: `Bearer ${token}` } }),
  };
}


const POLL_MS = 30_000;

// ── Stage display name mapping ────────────────────────────────────────────────
const STAGE_LABELS = {
  procurement: "Procurement", cutting: "Cutting", folding: "Folding",
  attachment: "Attachment", stitching: "Stitching", lasting: "Lasting",
  sole_pasting: "Sole Pasting", finishing: "Finishing", qc_pack: "QC & Pack",
  dispatched: "Dispatched",
};

// ── Production Card Modal / Drawer ────────────────────────────────────────────
function ProductionCardModal({ jobId, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pdfLoading, setPdfLoading] = useState(false);

  const api = karigarHttp();

  useEffect(() => {
    let unmounted = false;
    async function fetchDetails() {
      try {
        const { data } = await api.get(`/my/tasks/${jobId}/details`);
        if (!unmounted) setDetails(data);
      } catch (e) {
        if (!unmounted) setError(friendlyAxiosError(e));
      } finally {
        if (!unmounted) setLoading(false);
      }
    }
    fetchDetails();
    return () => { unmounted = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const downloadPdf = async () => {
    setPdfLoading(true);
    try {
      const res = await api.get(`/my/tasks/${jobId}/card.pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ProductionCard-${details?.style_code || "job"}-${details?.color || ""}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      alert("PDF download failed: " + friendlyAxiosError(e));
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 100,
      background: "rgba(15,23,42,0.85)", backdropFilter: "blur(12px)",
      display: "flex", alignItems: "center", justifyCenter: "center",
      padding: "1rem",
    }}>
      <div style={{
        background: "#1e293b", border: "1px solid rgba(255,255,255,0.12)",
        borderRadius: 20, width: "100%", maxWidth: 440, maxHeight: "90vh",
        overflowY: "auto", padding: "1.25rem", color: "#f1f5f9",
        boxShadow: "0 25px 50px -12px rgba(0,0,0,0.5)", margin: "auto",
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: "0.68rem", color: "#C27842", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.12em" }}>
              Production Card
            </div>
            <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "#f1f5f9", marginTop: 2 }}>
              {details?.style_code || "Loading..."}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "rgba(255,255,255,0.08)", border: "none", borderRadius: 8,
              color: "#94a3b8", width: 36, height: 36, display: "flex",
              alignItems: "center", justifyContent: "center", cursor: "pointer",
            }}
          >
            <X size={20} />
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "3rem 0", color: "#64748b" }}>
            <Loader2 size={28} style={{ animation: "spin 1s linear infinite" }} />
          </div>
        ) : error ? (
          <div style={{ color: "#fca5a5", fontSize: "0.85rem", padding: "1rem 0" }}>{error}</div>
        ) : (
          <div>
            {/* Style Image */}
            <div style={{ marginBottom: 14 }}>
              {details.image_url || details.image_thumbnail_url ? (
                <div style={{
                  borderRadius: 14, overflow: "hidden",
                  border: "1px solid rgba(255,255,255,0.12)", background: "#020617",
                  maxHeight: 220, display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center", position: "relative",
                  boxShadow: "0 10px 25px rgba(0,0,0,0.4)"
                }}>
                  <img
                    src={details.image_url || details.image_thumbnail_url}
                    alt={details.style_code}
                    style={{ width: "100%", maxHeight: 220, objectFit: "contain", background: "#020617" }}
                  />
                  <div style={{
                    position: "absolute", bottom: 8, right: 8,
                    background: "rgba(15,23,42,0.85)", backdropFilter: "blur(6px)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    padding: "3px 8px", borderRadius: 6, fontSize: "0.68rem", color: "#cbd5e1", fontWeight: 700
                  }}>
                    📷 Style Reference Image
                  </div>
                </div>
              ) : (
                <div style={{
                  borderRadius: 12, padding: "1.25rem 1rem",
                  border: "1px dashed rgba(255,255,255,0.15)", background: "rgba(15,23,42,0.4)",
                  textAlign: "center", color: "#64748b", fontSize: "0.8rem",
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
                }}>
                  <Package size={30} strokeWidth={1.5} color="#475569" />
                  <span style={{ fontWeight: 600 }}>No style reference image uploaded for {details.style_code}</span>
                </div>
              )}
            </div>

            {/* Info Grid */}
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8,
              background: "rgba(15,23,42,0.6)", padding: "0.85rem",
              borderRadius: 12, marginBottom: 12, border: "1px solid rgba(255,255,255,0.05)",
            }}>
              <div>
                <div style={{ fontSize: "0.65rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase" }}>PO Number</div>
                <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "#f1f5f9" }}>{details.po_number}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.65rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase" }}>Client</div>
                <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "#f1f5f9" }}>{details.client_name}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.65rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase" }}>Color</div>
                <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "#fbbf24" }}>{details.color || "—"}</div>
              </div>
              <div>
                <div style={{ fontSize: "0.65rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase" }}>Delivery Date</div>
                <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "#f1f5f9" }}>{details.delivery_date || "—"}</div>
              </div>
            </div>

            {/* Sizes & Quantities Table */}
            {details.sizes && details.sizes.length > 0 ? (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: "0.68rem", color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                  Size Breakdown ({details.total_qty} Pairs Total)
                </div>
                <div style={{
                  background: "rgba(15,23,42,0.6)", borderRadius: 10, overflow: "hidden",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}>
                  <div style={{
                    display: "grid", gridTemplateColumns: `repeat(${details.sizes.length + 1}, 1fr)`,
                    background: "rgba(51,65,85,0.5)", padding: "6px 8px",
                    fontSize: "0.72rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", textAlign: "center",
                  }}>
                    {details.sizes.map((s) => (
                      <div key={s.size}>Sz {s.size}</div>
                    ))}
                    <div style={{ color: "#C27842" }}>Total</div>
                  </div>
                  <div style={{
                    display: "grid", gridTemplateColumns: `repeat(${details.sizes.length + 1}, 1fr)`,
                    padding: "8px", fontSize: "0.95rem", fontWeight: 800, color: "#f1f5f9", textAlign: "center",
                  }}>
                    {details.sizes.map((s) => (
                      <div key={s.size}>
                        <div>{s.quantity}</div>
                        {s.completed_qty > 0 && (
                          <div style={{ fontSize: "0.68rem", color: "#4ade80", fontWeight: 700 }}>✓ {s.completed_qty}</div>
                        )}
                      </div>
                    ))}
                    <div>
                      <div style={{ color: "#6ee7b7" }}>{details.total_qty}</div>
                      {details.total_completed_qty > 0 && (
                        <div style={{ fontSize: "0.68rem", color: "#4ade80", fontWeight: 700 }}>✓ {details.total_completed_qty}</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Stage Progress & Worker Assignments */}
            {details.assignments && Object.keys(details.assignments).length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: "0.68rem", color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                  Stage Progress & Assignments
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {["upper", "stitching", "sole", "bottom", "packing"].map((stg) => {
                    const asgn = details.assignments[stg];
                    if (!asgn) return null;
                    const isDone = asgn.status === "completed" || details.components?.[`${stg}_done`];
                    const isCurrent = details.stage === stg;
                    return (
                      <div key={stg} style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        padding: "8px 12px", background: "rgba(15,23,42,0.5)",
                        borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)"
                      }}>
                        <div>
                          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#e2e8f0", textTransform: "capitalize" }}>
                            {STAGE_LABELS[stg] || stg}:
                          </span>
                          <span style={{ fontSize: "0.8rem", color: "#94a3b8", marginLeft: 6 }}>
                            {asgn.worker_name || "Assigned"}
                          </span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          {asgn.rate_per_pair != null && (
                            <span style={{ fontSize: "0.75rem", color: "#fbbf24", fontWeight: 700 }}>
                              ₹{asgn.rate_per_pair}/pr
                            </span>
                          )}
                          <span style={{
                            fontSize: "0.65rem", fontWeight: 800, padding: "2px 8px", borderRadius: 6,
                            textTransform: "uppercase",
                            background: isDone ? "rgba(34,197,94,0.2)" : isCurrent ? "rgba(234,179,8,0.2)" : "rgba(148,163,184,0.1)",
                            color: isDone ? "#4ade80" : isCurrent ? "#fde047" : "#94a3b8",
                            border: `1px solid ${isDone ? "rgba(34,197,94,0.4)" : isCurrent ? "rgba(234,179,8,0.4)" : "rgba(148,163,184,0.2)"}`
                          }}>
                            {isDone ? "✓ Completed" : isCurrent ? "In Progress" : "Pending"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Component / BOM Notes if present */}
            {details.bom_items && details.bom_items.length > 0 ? (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: "0.68rem", color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                  BOM Components
                </div>
                <div style={{
                  background: "rgba(15,23,42,0.4)", borderRadius: 10, padding: "8px 12px",
                  fontSize: "0.8rem", color: "#cbd5e1", maxHeight: 100, overflowY: "auto"
                }}>
                  {details.bom_items.map((b, idx) => (
                    <div key={idx} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                      <span>{b.material_name || b.name || b.category || `Item #${idx + 1}`}</span>
                      <span style={{ fontWeight: 700, color: "#94a3b8" }}>{b.qty || b.yield || ""}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* My Assignment Info */}
            {details.my_assignment?.role && (
              <div style={{
                background: "rgba(194,120,66,0.1)", border: "1px solid rgba(194,120,66,0.25)",
                borderRadius: 10, padding: "0.65rem 0.85rem", marginBottom: 14,
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <div>
                  <div style={{ fontSize: "0.65rem", color: "#C27842", fontWeight: 700, textTransform: "uppercase" }}>Your Assigned Role</div>
                  <div style={{ fontSize: "0.9rem", fontWeight: 800, color: "#f1f5f9", textTransform: "capitalize" }}>
                    {STAGE_LABELS[details.my_assignment.role] || details.my_assignment.role}
                  </div>
                </div>
                {details.my_assignment.rate_per_pair != null && (
                  <div style={{ fontSize: "0.95rem", fontWeight: 800, color: "#6ee7b7" }}>
                    {inr(details.my_assignment.rate_per_pair)} / pair
                  </div>
                )}
              </div>
            )}

            {/* PDF Download Button */}
            <button
              onClick={downloadPdf}
              disabled={pdfLoading}
              style={{
                width: "100%", background: "linear-gradient(135deg, #C27842, #a05a28)",
                border: "none", borderRadius: 12, color: "white",
                height: 48, fontSize: "0.9rem", fontWeight: 700, cursor: pdfLoading ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                opacity: pdfLoading ? 0.7 : 1,
              }}
            >
              {pdfLoading ? <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} /> : <Download size={18} />}
              Download A4 Production Card PDF
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Task Card ─────────────────────────────────────────────────────────────────
function TaskCard({ job, workerName, onMarkReady, onViewCard }) {
  const [expanded, setExpanded] = useState(false);
  const [sizeQtys, setSizeQtys] = useState({});
  const [qty, setQty] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState("");

  const rfp = job.ready_for_pickup;
  const isReady = !!rfp;
  const isDone = job.is_completed;

  // Initialize sizeQtys when sizes are available
  useEffect(() => {
    if (job.sizes && job.sizes.length > 0) {
      const initMap = {};
      job.sizes.forEach((sz) => {
        const k = sz.job_id || sz.size;
        initMap[k] = sz.ordered_qty;
      });
      setSizeQtys(initMap);
    }
  }, [job.sizes]);

  const calcTotalPairs = () => {
    if (job.sizes && job.sizes.length > 0) {
      return job.sizes.reduce((acc, sz) => {
        const k = sz.job_id || sz.size;
        const val = parseInt(sizeQtys[k] !== undefined ? sizeQtys[k] : sz.ordered_qty, 10) || 0;
        return acc + val;
      }, 0);
    }
    return parseInt(qty, 10) || 0;
  };

  const handleSubmit = async () => {
    const totalPairs = calcTotalPairs();
    if (totalPairs <= 0) {
      setLocalError("Please enter completed pairs for at least one size");
      return;
    }

    const breakdown = {};
    if (job.sizes && job.sizes.length > 0) {
      job.sizes.forEach((sz) => {
        const k = sz.job_id || sz.size;
        breakdown[k] = parseInt(sizeQtys[k] !== undefined ? sizeQtys[k] : sz.ordered_qty, 10) || 0;
      });
    }

    setLocalError("");
    setSubmitting(true);
    try {
      await onMarkReady(job.id, totalPairs, notes, breakdown);
      setExpanded(false);
      setNotes("");
    } catch (e) {
      setLocalError(friendlyAxiosError(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      background: "rgba(30,41,59,0.8)", backdropFilter: "blur(10px)",
      border: isDone
        ? "1px solid rgba(34,197,94,0.3)"
        : isReady
        ? "1.5px solid rgba(251,191,36,0.4)"
        : "1px solid rgba(255,255,255,0.07)",
      borderRadius: 16, padding: "1rem 1.1rem", marginBottom: 12,
      boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          {job.image_thumbnail_url ? (
            <img
              src={job.image_thumbnail_url}
              alt={job.style_code}
              style={{
                width: 52, height: 52, borderRadius: 8, objectFit: "cover",
                border: "1px solid rgba(255,255,255,0.1)", background: "#0f172a", flexShrink: 0
              }}
            />
          ) : null}
          <div>
            <div style={{ fontSize: "0.68rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>
              {job.po_number}
            </div>
            <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "#f1f5f9", marginTop: 2 }}>
              {job.style_code}
            </div>
            <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: 2 }}>
              {[job.color, `${job.total_quantity || job.quantity || 0} pairs total`].filter(Boolean).join(" · ")}
            </div>

            {/* Size Breakdown Tags */}
            {job.sizes && job.sizes.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                {job.sizes.map((sz) => (
                  <span
                    key={sz.size}
                    style={{
                      background: "rgba(15,23,42,0.7)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      borderRadius: 6, padding: "2px 6px",
                      fontSize: "0.72rem", color: "#cbd5e1", fontWeight: 600,
                    }}
                  >
                    Size {sz.size}: <strong style={{ color: "#f59e0b" }}>{sz.ordered_qty}</strong>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ textAlign: "right" }}>
          <span style={{
            display: "inline-block", fontSize: "0.68rem", fontWeight: 700,
            padding: "3px 10px", borderRadius: 20,
            background: isDone ? "rgba(34,197,94,0.15)" : "rgba(194,120,66,0.15)",
            color: isDone ? "#86efac" : "#C27842",
            border: isDone ? "1px solid rgba(34,197,94,0.3)" : "1px solid rgba(194,120,66,0.3)",
            textTransform: "uppercase", letterSpacing: "0.05em",
          }}>
            {isDone ? "Completed" : STAGE_LABELS[job.stage] || job.stage}
          </span>
          {job.my_assignment?.rate_per_pair != null && (
            <div style={{ fontSize: "0.8rem", color: "#6ee7b7", fontWeight: 700, marginTop: 6 }}>
              {inr(job.my_assignment.rate_per_pair)} / pair
            </div>
          )}
        </div>
      </div>

      {/* Status or action */}
      {isDone ? (
        <div style={{
          marginTop: 12, background: "rgba(34,197,94,0.08)",
          border: "1px solid rgba(34,197,94,0.25)", borderRadius: 10,
          padding: "0.6rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <CheckCircle2 size={16} color="#4ade80" />
            <div>
              <div style={{ color: "#86efac", fontSize: "0.8rem", fontWeight: 700 }}>Work Completed</div>
              <div style={{ color: "#94a3b8", fontSize: "0.72rem" }}>
                {job.completed_qty ? `${job.completed_qty} pairs recorded` : "Stage completed"}
              </div>
            </div>
          </div>
          <button
            onClick={() => onViewCard?.(job.id)}
            style={{
              background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 8, color: "#f1f5f9", padding: "0.35rem 0.65rem",
              fontSize: "0.75rem", fontWeight: 700, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 4,
            }}
          >
            <FileText size={13} />
            Card
          </button>
        </div>
      ) : isReady ? (
        <div style={{
          marginTop: 12, background: "rgba(251,191,36,0.08)",
          border: "1px solid rgba(251,191,36,0.25)", borderRadius: 10,
          padding: "0.6rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Clock size={15} color="#fbbf24" />
            <div>
              <div style={{ color: "#fbbf24", fontSize: "0.8rem", fontWeight: 700 }}>Waiting for pickup</div>
              <div style={{ color: "#94a3b8", fontSize: "0.72rem" }}>
                Marked {rfp.completed_qty} pairs complete
              </div>
            </div>
          </div>
          <button
            onClick={() => onViewCard?.(job.id)}
            style={{
              background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 8, color: "#f1f5f9", padding: "0.35rem 0.65rem",
              fontSize: "0.75rem", fontWeight: 700, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 4,
            }}
          >
            <FileText size={13} />
            Card
          </button>
        </div>
      ) : expanded ? (
        <div style={{ marginTop: 14, background: "rgba(15,23,42,0.4)", borderRadius: 12, padding: "0.9rem", border: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Size-Wise Completed Pairs
            </div>
            {job.sizes && job.sizes.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  const m = {};
                  job.sizes.forEach((sz) => { m[sz.job_id || sz.size] = sz.ordered_qty; });
                  setSizeQtys(m);
                }}
                style={{
                  background: "rgba(34,197,94,0.15)", border: "1px solid rgba(34,197,94,0.3)",
                  color: "#86efac", borderRadius: 6, padding: "3px 9px", fontSize: "0.72rem", fontWeight: 700, cursor: "pointer",
                }}
              >
                Fill All (100%)
              </button>
            )}
          </div>

          {job.sizes && job.sizes.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
              {job.sizes.map((sz) => {
                const k = sz.job_id || sz.size;
                const curVal = sizeQtys[k] !== undefined ? sizeQtys[k] : sz.ordered_qty;
                return (
                  <div
                    key={k}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      background: "rgba(30,41,59,0.7)", padding: "6px 12px", borderRadius: 8,
                      border: "1px solid rgba(255,255,255,0.05)",
                    }}
                  >
                    <div>
                      <span style={{ color: "#f8fafc", fontWeight: 800, fontSize: "0.9rem" }}>Size {sz.size}</span>
                      <span style={{ color: "#64748b", fontSize: "0.75rem", marginLeft: 8 }}>Order: {sz.ordered_qty} prs</span>
                    </div>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={sz.ordered_qty}
                      value={curVal}
                      onChange={(e) => setSizeQtys({ ...sizeQtys, [k]: e.target.value })}
                      style={{
                        width: 72, background: "rgba(15,23,42,0.9)",
                        border: "1.5px solid rgba(34,197,94,0.4)", borderRadius: 8,
                        padding: "0.35rem 0.5rem", color: "#86efac", fontSize: "0.95rem",
                        fontWeight: 800, textAlign: "center", outline: "none",
                      }}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <input
              type="number"
              inputMode="numeric"
              min={1}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder="Enter pairs done"
              style={{
                width: "100%", background: "rgba(15,23,42,0.6)",
                border: "1.5px solid rgba(255,255,255,0.12)", borderRadius: 10,
                padding: "0.65rem 0.9rem", color: "#f1f5f9", fontSize: "1rem",
                fontWeight: 700, outline: "none", marginBottom: 8,
              }}
            />
          )}

          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes (optional)"
            style={{
              width: "100%", background: "rgba(15,23,42,0.6)",
              border: "1px solid rgba(255,255,255,0.12)", borderRadius: 10,
              padding: "0.55rem 0.8rem", color: "#94a3b8", fontSize: "0.82rem",
              outline: "none", resize: "none",
            }}
          />

          {localError && (
            <div style={{ color: "#fca5a5", fontSize: "0.75rem", marginTop: 6 }}>{localError}</div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button
              type="button"
              onClick={() => { setExpanded(false); setLocalError(""); }}
              style={{
                flex: 1, background: "rgba(51,65,85,0.7)", border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 10, color: "#94a3b8", height: 44, cursor: "pointer", fontWeight: 600,
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              style={{
                flex: 2, background: "linear-gradient(135deg, #22c55e, #16a34a)",
                border: "none", borderRadius: 10, color: "white",
                height: 44, cursor: submitting ? "not-allowed" : "pointer",
                fontWeight: 700, opacity: submitting ? 0.65 : 1,
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              }}
            >
              {submitting ? <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} /> : <CheckCircle2 size={16} />}
              Submit ({calcTotalPairs()} pairs)
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button
            onClick={() => onViewCard?.(job.id)}
            style={{
              flex: 1, background: "rgba(51,65,85,0.6)",
              border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10,
              color: "#e2e8f0", height: 42, cursor: "pointer",
              fontWeight: 700, fontSize: "0.82rem",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
            }}
          >
            <FileText size={15} color="#C27842" />
            Production Card
          </button>
          <button
            onClick={() => setExpanded(true)}
            style={{
              flex: 1.3,
              background: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(22,163,74,0.1))",
              border: "1px solid rgba(34,197,94,0.3)", borderRadius: 10,
              color: "#86efac", height: 42, cursor: "pointer",
              fontWeight: 700, fontSize: "0.82rem",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
            }}
          >
            <CheckCircle2 size={15} />
            Mark Ready
          </button>
        </div>
      )}
    </div>
  );
}


// ── Immutable Completed Card for Payroll ─────────────────────────────────────
function PayrollCompletedCard({ job, onViewCard }) {
  const poNum = job.po_number || "—";
  const styleCode = job.style_code || "—";
  const color = job.color || "";
  const totalPairs = job.completed_qty || job.total_quantity || job.quantity || job.pairs || 0;
  const rate = job.rate_per_pair || job.rate || 0;
  const earning = job.total_earning || job.earning || (totalPairs * rate);
  const imgUrl = job.image_thumbnail_url || job.image_url;
  const roleLabel = STAGE_LABELS[job.role] || job.role || "Completed";

  return (
    <div style={{
      background: "rgba(30,41,59,0.8)",
      backdropFilter: "blur(10px)",
      border: "1px solid rgba(34,197,94,0.3)",
      borderRadius: 16,
      padding: "1rem 1.1rem",
      marginBottom: 12,
      boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
    }}>
      {/* Top Header Row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          {imgUrl ? (
            <img
              src={imgUrl}
              alt={styleCode}
              style={{
                width: 56, height: 56, borderRadius: 10, objectFit: "cover",
                border: "1px solid rgba(255,255,255,0.12)", background: "#0f172a", flexShrink: 0
              }}
            />
          ) : (
            <div style={{
              width: 56, height: 56, borderRadius: 10, background: "#0f172a",
              border: "1px solid rgba(255,255,255,0.12)", display: "grid", placeItems: "center", flexShrink: 0
            }}>
              <Package size={24} color="#475569" />
            </div>
          )}
          <div>
            <div style={{ fontSize: "0.7rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>
              {poNum}
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "#f1f5f9", marginTop: 2 }}>
              {styleCode}
            </div>
            <div style={{ fontSize: "0.82rem", color: "#94a3b8", marginTop: 2, fontWeight: 600 }}>
              {[color, `${totalPairs} pairs total`].filter(Boolean).join(" · ")}
            </div>

            {/* Size Breakdown Badges */}
            {job.sizes && job.sizes.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                {job.sizes.map((sz) => (
                  <span
                    key={sz.size}
                    style={{
                      background: "rgba(15,23,42,0.7)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      borderRadius: 6, padding: "2px 8px",
                      fontSize: "0.72rem", color: "#cbd5e1", fontWeight: 600,
                    }}
                  >
                    Size {sz.size}: <strong style={{ color: "#f59e0b" }}>{sz.completed_qty || sz.ordered_qty || sz.pairs}</strong>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <span style={{
            display: "inline-block", fontSize: "0.68rem", fontWeight: 800,
            padding: "3px 10px", borderRadius: 20,
            background: "rgba(34,197,94,0.15)", color: "#86efac",
            border: "1px solid rgba(34,197,94,0.3)",
            textTransform: "uppercase", letterSpacing: "0.05em",
          }}>
            COMPLETED ({roleLabel})
          </span>
          <div style={{ fontSize: "0.85rem", color: "#6ee7b7", fontWeight: 800, marginTop: 6 }}>
            {inr(rate)} / pair
          </div>
          <div style={{ fontSize: "0.78rem", color: "#fbbf24", fontWeight: 800, marginTop: 2 }}>
            {inr(earning)}
          </div>
        </div>
      </div>

      {/* Immutable Footer Banner */}
      <div style={{
        marginTop: 12, background: "rgba(34,197,94,0.08)",
        border: "1px solid rgba(34,197,94,0.25)", borderRadius: 10,
        padding: "0.65rem 0.95rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <CheckCircle2 size={18} color="#4ade80" />
          <div>
            <div style={{ color: "#86efac", fontSize: "0.82rem", fontWeight: 700 }}>Work Completed</div>
            <div style={{ color: "#94a3b8", fontSize: "0.75rem" }}>
              {totalPairs} pairs recorded · <span style={{ color: "#6ee7b7", fontWeight: 700 }}>{inr(earning)}</span>
            </div>
          </div>
        </div>
        <button
          onClick={() => onViewCard?.(job.id || job.job_id)}
          style={{
            background: "rgba(51,65,85,0.7)",
            border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8,
            color: "#e2e8f0", padding: "6px 14px", cursor: "pointer",
            fontWeight: 700, fontSize: "0.78rem",
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <FileText size={14} color="#C27842" />
          Card
        </button>
      </div>
    </div>
  );
}


// ── Payroll Panel ─────────────────────────────────────────────────────────────
function PayrollPanel({ worker, onViewCard }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const api = karigarHttp();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get("/my/payroll");
      setData(d);
    } catch (e) {
      setError(friendlyAxiosError(e));
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ textAlign: "center", padding: "3rem 0", color: "#64748b" }}>
      <Loader2 size={28} style={{ animation: "spin 1s linear infinite" }} />
      <div style={{ marginTop: 8, fontSize: "0.85rem" }}>Loading payroll data...</div>
    </div>
  );
  if (error) return (
    <div style={{
      background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)",
      borderRadius: 12, padding: "1rem", color: "#fca5a5", fontSize: "0.85rem",
    }}>
      {error}
    </div>
  );
  if (!data) return null;

  const p = data.payroll || {};
  return (
    <div>
      <div style={{ fontSize: "0.68rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 4 }}>
        {data.from_date} to {data.to_date}
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 12 }}>
        {[
          { label: "Pairs Done", value: p.total_pairs, color: "#60a5fa" },
          { label: "Earnings", value: inr(p.total_earning), color: "#6ee7b7" },
          { label: "Bonus", value: inr(p.total_bonus || 0), color: "#fbbf24" },
          { label: "Net Payable", value: inr(p.net_payable), color: "#a78bfa" },
        ].map((s) => (
          <div key={s.label} style={{
            background: "rgba(30,41,59,0.8)", border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 14, padding: "1rem",
          }}>
            <div style={{ fontSize: "0.68rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>{s.label}</div>
            <div style={{ fontSize: "1.25rem", fontWeight: 800, color: s.color, marginTop: 4 }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* By-role breakdown */}
      {p.by_role && Object.keys(p.by_role).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: "0.68rem", color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>By Role</div>
          {Object.entries(p.by_role).map(([role, pairs]) => (
            <div key={role} style={{
              display: "flex", justifyContent: "space-between",
              padding: "0.5rem 0.75rem",
              background: "rgba(15,23,42,0.4)", borderRadius: 8, marginBottom: 4,
            }}>
              <span style={{ color: "#94a3b8", fontSize: "0.85rem", textTransform: "capitalize" }}>{STAGE_LABELS[role] || role}</span>
              <span style={{ color: "#e2e8f0", fontWeight: 700, fontSize: "0.85rem" }}>{pairs} pairs</span>
            </div>
          ))}
        </div>
      )}

      {/* Completed Production Cards & Earnings */}
      {p.jobs && p.jobs.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: "0.68rem", color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 10 }}>
            Completed Production Cards ({p.jobs.length})
          </div>
          <div>
            {p.jobs.map((job, idx) => (
              <PayrollCompletedCard
                key={job.id || idx}
                job={job}
                onViewCard={(jid) => onViewCard?.(jid || job.id || job.job_id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function KarigarDashboard() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("tasks");
  const [taskScope, setTaskScope] = useState("active"); // "active" | "completed"
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeCardJobId, setActiveCardJobId] = useState(null);
  const pollRef = useRef(null);

  const worker = (() => {
    try { return JSON.parse(localStorage.getItem("karigar_worker") || "{}"); }
    catch { return {}; }
  })();

  const token = localStorage.getItem("karigar_token") || localStorage.getItem("token");

  useEffect(() => {
    if (!token) navigate("/karigar-login", { replace: true });
  }, [token, navigate]);


  const api = karigarHttp();

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get(`/my/tasks?scope=${taskScope}`);
      setTasks(data);
    } catch (e) {
      if (e?.response?.status === 401) {
        navigate("/karigar-login", { replace: true });
      } else {
        setError(friendlyAxiosError(e));
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskScope]);

  useEffect(() => {
    if (tab === "tasks") {
      loadTasks();
      pollRef.current = setInterval(loadTasks, POLL_MS);
    }
    return () => clearInterval(pollRef.current);
  }, [tab, taskScope, loadTasks]);

  const handleMarkReady = async (jobId, completedQty, notes, sizeBreakdown) => {
    await api.patch(`/my/tasks/${jobId}/ready-for-pickup`, {
      completed_qty: completedQty,
      notes: notes,
      size_breakdown: sizeBreakdown,
    });
    await loadTasks();
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("karigar_token");
    localStorage.removeItem("karigar_worker");
    navigate("/karigar-login", { replace: true });
  };


  return (
    <div style={{
      minHeight: "100dvh",
      background: "linear-gradient(145deg, #0f172a 0%, #1e293b 60%, #172032 100%)",
      fontFamily: "'Inter', 'Segoe UI', sans-serif",
      maxWidth: 480, margin: "0 auto",
    }}>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>

      {/* Top bar */}
      <div style={{
        position: "sticky", top: 0, zIndex: 50,
        background: "rgba(15,23,42,0.92)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid rgba(255,255,255,0.07)",
        padding: "0.9rem 1rem",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 36, height: 36,
            background: "linear-gradient(135deg, #C27842, #a05a28)",
            borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <HardHat size={18} color="white" />
          </div>
          <div>
            <div style={{ color: "#f1f5f9", fontWeight: 800, fontSize: "0.95rem" }}>
              {worker.name || "Karigar"}
            </div>
            <div style={{ color: "#64748b", fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em" }}>
              {worker.skill || "worker"}
            </div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          style={{
            background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)",
            borderRadius: 8, color: "#f87171", padding: "0.4rem 0.75rem",
            cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
            fontSize: "0.78rem", fontWeight: 700,
          }}
          id="karigar-logout-btn"
        >
          <LogOut size={14} />
          Logout
        </button>
      </div>

      {/* Tab bar */}
      <div style={{
        display: "flex", borderBottom: "1px solid rgba(255,255,255,0.07)",
        background: "rgba(15,23,42,0.5)",
      }}>
        {[
          { id: "tasks", label: "My Tasks", icon: Package },
          { id: "payroll", label: "My Payroll", icon: IndianRupee },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              flex: 1, padding: "0.85rem 0",
              background: "none", border: "none",
              borderBottom: tab === id ? "2.5px solid #C27842" : "2.5px solid transparent",
              color: tab === id ? "#C27842" : "#64748b",
              fontWeight: 700, fontSize: "0.85rem", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              transition: "all 0.15s ease",
            }}
            id={`karigar-tab-${id}`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: "1rem", paddingBottom: "2rem" }}>
        {tab === "tasks" && (
          <>
            {/* Task Scope Filter Pills */}
            <div style={{
              display: "flex", background: "rgba(15,23,42,0.6)",
              borderRadius: 12, padding: 3, marginBottom: 16,
              border: "1px solid rgba(255,255,255,0.08)",
            }}>
              <button
                onClick={() => setTaskScope("active")}
                style={{
                  flex: 1, padding: "0.45rem 0", borderRadius: 9,
                  border: "none", background: taskScope === "active" ? "#C27842" : "transparent",
                  color: taskScope === "active" ? "white" : "#94a3b8",
                  fontWeight: 700, fontSize: "0.78rem", cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                Ongoing Tasks
              </button>
              <button
                onClick={() => setTaskScope("completed")}
                style={{
                  flex: 1, padding: "0.45rem 0", borderRadius: 9,
                  border: "none", background: taskScope === "completed" ? "#C27842" : "transparent",
                  color: taskScope === "completed" ? "white" : "#94a3b8",
                  fontWeight: 700, fontSize: "0.78rem", cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                Completed Tasks
              </button>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div style={{ color: "#f1f5f9", fontWeight: 700, fontSize: "0.9rem" }}>
                {tasks.length} {taskScope} job{tasks.length !== 1 ? "s" : ""}
              </div>
              <button
                onClick={loadTasks}
                disabled={loading}
                style={{
                  background: "none", border: "none", color: "#64748b",
                  cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
                  fontSize: "0.75rem", fontWeight: 600,
                }}
                id="karigar-refresh-btn"
              >
                <RefreshCw size={14} style={loading ? { animation: "spin 1s linear infinite" } : {}} />
                Refresh
              </button>
            </div>

            {loading && tasks.length === 0 && (
              <div style={{ textAlign: "center", padding: "3rem 0", color: "#64748b" }}>
                <Loader2 size={24} style={{ animation: "spin 1s linear infinite" }} />
              </div>
            )}

            {error && (
              <div style={{
                background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)",
                borderRadius: 10, padding: "0.75rem 1rem", color: "#fca5a5", fontSize: "0.85rem",
              }}>
                {error}
              </div>
            )}

            {!loading && !error && tasks.length === 0 && (
              <div style={{ textAlign: "center", padding: "4rem 0", color: "#475569" }}>
                <Package size={40} strokeWidth={1.2} />
                <div style={{ marginTop: 12, fontWeight: 600 }}>No {taskScope} tasks</div>
                <div style={{ fontSize: "0.8rem", marginTop: 4 }}>
                  {taskScope === "active" ? "Your manager will assign you to a job" : "Tasks you complete will appear here"}
                </div>
              </div>
            )}

            {tasks.map((job) => (
              <TaskCard
                key={job.id}
                job={job}
                workerName={worker.name}
                onMarkReady={handleMarkReady}
                onViewCard={(jid) => setActiveCardJobId(jid)}
              />
            ))}
          </>
        )}

        {tab === "payroll" && (
          <PayrollPanel
            worker={worker}
            onViewCard={(jid) => setActiveCardJobId(jid)}
          />
        )}
      </div>

      {/* Production Card Modal */}
      {activeCardJobId && (
        <ProductionCardModal
          jobId={activeCardJobId}
          onClose={() => setActiveCardJobId(null)}
        />
      )}
    </div>
  );
}
