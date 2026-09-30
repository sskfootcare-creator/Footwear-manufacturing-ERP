import React, { useState, useMemo } from "react";
import { http, inr } from "../lib/api";
import { broadcastSync } from "../lib/sync";
import { Card, Badge, BtnPrimary, BtnSecondary } from "./ui-kit";
import {
  CheckCircle2,
  Clock,
  ChevronRight,
  HardHat,
  AlertTriangle,
  Layers,
  Sparkles,
  ArrowRight,
  X,
} from "lucide-react";

export default function ComponentProductionBoard({
  jobs = [],
  groups = [],
  workers = [],
  styleByCode = {},
  canEdit = true,
  onRefresh,
}) {
  const [filterType, setFilterType] = useState("all");
  const [search, setSearch] = useState("");
  const [advanceModal, setAdvanceModal] = useState(null); // { job, component, stage, stagesList }
  const [selectedWorkerId, setSelectedWorkerId] = useState("");
  const [completedQty, setCompletedQty] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Filter groups in component production stages (prior to lasting)
  const componentGroups = useMemo(() => {
    return groups.filter((g) => {
      const stage = g.stage || g.rows?.[0]?.stage;
      // Stages before lasting: planning, procurement, cutting, folding, attachment, stitching
      const isPreLasting = [
        "planning",
        "procurement",
        "cutting",
        "folding",
        "attachment",
        "stitching",
      ].includes(stage);
      if (!isPreLasting) return false;

      const ft =
        g.rows?.[0]?.component_specs?.footwear_type ||
        styleByCode[g.style_code]?.footwear_type ||
        "flat";
      if (filterType !== "all" && ft !== filterType) return false;

      if (search) {
        const q = search.toLowerCase();
        const match =
          `${g.po_number || ""} ${g.style_code || ""} ${g.color || ""} ${g.client_name || ""}`
            .toLowerCase()
            .includes(q);
        if (!match) return false;
      }
      return true;
    });
  }, [groups, filterType, search, styleByCode]);

  const openAdvance = (job, component, stage, stagesList) => {
    setErrorMsg("");
    setAdvanceModal({ job, component, stage, stagesList });
    setCompletedQty(job.quantity || 100);
    // Find pre-assigned worker if any
    const asgnKey = `${component}.${stage}`;
    const preWorker =
      job.assignments?.[asgnKey]?.worker_id ||
      job.assignments?.[stage]?.worker_id ||
      "";
    setSelectedWorkerId(preWorker);
    setNotes("");
  };

  const submitAdvance = async () => {
    if (!advanceModal) return;
    setSubmitting(true);
    setErrorMsg("");
    try {
      const { job, component, stage } = advanceModal;
      const targetJobs = job.rows && job.rows.length > 0 ? job.rows : [job];

      await Promise.all(
        targetJobs.map((j) =>
          http.patch(`/production/jobs/${j.id}/component-stage`, {
            component,
            stage,
            completed_qty: Number(completedQty),
            worker_id: selectedWorkerId || undefined,
            notes,
          })
        )
      );

      broadcastSync("production", { action: "component_advance" });
      setAdvanceModal(null);
      if (onRefresh) onRefresh();
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="component-production-board">
      {/* Controls Bar */}
      <div className="bg-white border-2 border-slate-200 p-4 rounded-lg flex flex-wrap items-center justify-between gap-4 shadow-sm">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="text-xs uppercase font-bold tracking-wider text-slate-500">
            Footwear Type:
          </div>
          <div className="inline-flex rounded-md border border-slate-200 p-0.5 bg-slate-50">
            {["all", "flat", "heel"].map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={`px-3 py-1 text-xs font-bold rounded capitalize transition-all ${
                  filterType === t
                    ? "bg-[#0F172A] text-white shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                data-testid={`filter-type-${t}`}
              >
                {t === "all" ? "All Styles" : `${t} Styles`}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Search PO, style, color..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-xs border border-slate-300 rounded px-3 py-1.5 w-48 sm:w-64 focus:ring-2 focus:ring-[#C27842]/30 outline-none"
            data-testid="component-search-input"
          />
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
          <span className="font-bold text-slate-900 font-sans text-sm">
            {componentGroups.length}
          </span>{" "}
          cards in component production
        </div>
      </div>

      {componentGroups.length === 0 ? (
        <Card className="p-12 text-center text-slate-400">
          <Layers className="w-10 h-10 mx-auto mb-3 text-slate-300" />
          <div className="text-sm font-semibold text-slate-600">
            No production jobs currently in component preparation
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Jobs in planning, procurement, or component sub-stages appear here
            with independent swimlanes.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {componentGroups.map((g) => {
            const firstRow = g.rows?.[0] || {};
            const specs = firstRow.component_specs || {};
            const tracks = firstRow.component_tracks || {};
            const ft =
              specs.footwear_type ||
              styleByCode[g.style_code]?.footwear_type ||
              "flat";

            const upperTrack = tracks.upper || { status: "pending", current_stage: "cutting" };
            const bottomTrack = tracks.bottom || { status: "pending", current_stage: "cutting" };
            const soleTrack = tracks.sole || { status: "ready", current_stage: "ready" };
            const heelTrack = tracks.heel_gola || { status: "ready", current_stage: "ready" };

            const isKhokhaReady = upperTrack.status === "ready" && bottomTrack.status === "ready";
            const isSoleReady =
              soleTrack.status === "ready" &&
              (ft !== "heel" || heelTrack.status === "ready");

            const activeComps = [
              { key: "upper", label: "Upper Track", track: upperTrack, spec: specs.components?.upper },
              { key: "bottom", label: "Bottom / Insole Track", track: bottomTrack, spec: specs.components?.bottom },
              { key: "sole", label: "Sole Track", track: soleTrack, spec: specs.components?.sole },
            ];

            if (ft === "heel") {
              activeComps.push({
                key: "heel_gola",
                label: "Heel / Platform / Gola",
                track: heelTrack,
                spec: specs.components?.heel_gola,
              });
            }

            return (
              <div
                key={g.key || g.id}
                className="bg-white border-2 border-slate-200 rounded-lg overflow-hidden shadow-sm hover:border-slate-300 transition-all"
                data-testid={`component-card-${g.key || g.id}`}
              >
                {/* Header */}
                <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="font-mono font-bold text-sm text-slate-800">
                      {g.po_number || "—"}
                    </div>
                    <span className="text-slate-300">|</span>
                    <div className="font-semibold text-slate-900 text-sm">
                      {g.style_code}
                    </div>
                    {g.color && (
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-medium">
                        {g.color}
                      </span>
                    )}
                    <Badge color={ft === "heel" ? "purple" : "slate"}>
                      {ft === "heel" ? "Heel Style" : "Flat Style"}
                    </Badge>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* Merge Gates Status Indicators */}
                    <div
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold border ${
                        isKhokhaReady
                          ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                          : "bg-amber-50 text-amber-800 border-amber-300"
                      }`}
                      data-testid={`gate-lasting-${g.key || g.id}`}
                      title={isKhokhaReady ? "Lasting Gate Cleared" : "Blocked: Upper and Bottom must be ready"}
                    >
                      {isKhokhaReady ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-amber-600" />
                      )}
                      <span>Khokha Gate (Lasting): {isKhokhaReady ? "Ready" : "Waiting"}</span>
                    </div>

                    <div
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold border ${
                        isSoleReady
                          ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                          : "bg-amber-50 text-amber-800 border-amber-300"
                      }`}
                      data-testid={`gate-sole-${g.key || g.id}`}
                      title={isSoleReady ? "Sole Pasting Gate Cleared" : "Blocked: Sole components must be ready"}
                    >
                      {isSoleReady ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-amber-600" />
                      )}
                      <span>Sole Pasting Gate: {isSoleReady ? "Ready" : "Waiting"}</span>
                    </div>

                    <div className="font-mono text-xs font-bold text-slate-600 ml-2">
                      {g.totalQty || g.quantity} prs
                    </div>
                  </div>
                </div>

                {/* Component Tracks Swimlanes */}
                <div className="p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 bg-slate-50/40">
                  {activeComps.map(({ key, label, track, spec }) => {
                    const stagesList = spec?.stages || [];
                    const isReady = track.status === "ready";
                    const isVendorReady = stagesList.length === 0;

                    return (
                      <div
                        key={key}
                        className={`p-3.5 rounded-lg border flex flex-col justify-between transition-all ${
                          isReady
                            ? "bg-emerald-50/40 border-emerald-200"
                            : "bg-white border-slate-200 shadow-xs"
                        }`}
                        data-testid={`track-${key}-${g.key || g.id}`}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[11px] uppercase tracking-wider font-bold text-slate-600">
                              {label}
                            </span>
                            {isReady ? (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
                                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                                Ready
                              </span>
                            ) : (
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300">
                                In Progress
                              </span>
                            )}
                          </div>

                          {/* Sub-stages visualization */}
                          {isVendorReady ? (
                            <div className="text-xs text-slate-500 italic py-2">
                              Ready-to-use / Vendor-supplied (no stages required)
                            </div>
                          ) : (
                            <div className="space-y-1.5 my-2">
                              <div className="flex items-center gap-1 overflow-x-auto py-1">
                                {stagesList.map((st, idx) => {
                                  const completed =
                                    isReady ||
                                    (track.stages_completed || []).includes(st);
                                  const current =
                                    !isReady && track.current_stage === st;

                                  return (
                                    <React.Fragment key={st}>
                                      <div
                                        className={`px-2 py-1 rounded text-[11px] font-medium flex items-center gap-1 whitespace-nowrap border ${
                                          completed
                                            ? "bg-emerald-100 text-emerald-900 border-emerald-300 font-semibold"
                                            : current
                                            ? "bg-[#C27842] text-white border-[#C27842] font-bold shadow-xs"
                                            : "bg-slate-100 text-slate-500 border-slate-200"
                                        }`}
                                        data-testid={`stage-step-${key}-${st}`}
                                      >
                                        {completed && <CheckCircle2 className="w-2.5 h-2.5 text-emerald-700" />}
                                        {st}
                                      </div>
                                      {idx < stagesList.length - 1 && (
                                        <ChevronRight className="w-3 h-3 text-slate-400 flex-shrink-0" />
                                      )}
                                    </React.Fragment>
                                  );
                                })}
                              </div>

                              {/* Karigar assignment for current stage */}
                              {!isReady && (
                                <div className="text-[11px] text-slate-500 flex items-center justify-between pt-1">
                                  <span className="flex items-center gap-1 text-slate-600">
                                    <HardHat className="w-3 h-3 text-amber-600" />
                                    {firstRow.assignments?.[`${key}.${track.current_stage}`]?.worker_name ||
                                      firstRow.assignments?.[track.current_stage]?.worker_name ||
                                      "Unassigned"}
                                  </span>
                                  <span className="font-mono text-[10px]">
                                    Stage: <b className="text-slate-800">{track.current_stage}</b>
                                  </span>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Action: Advance stage button */}
                        {!isReady && canEdit && (
                          <div className="pt-2 border-t border-slate-100 mt-2">
                            <button
                              type="button"
                              onClick={() => openAdvance(firstRow, key, track.current_stage, stagesList)}
                              className="w-full py-1.5 px-2 rounded bg-slate-900 hover:bg-[#C27842] text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-xs"
                              data-testid={`advance-btn-${key}-${g.key || g.id}`}
                            >
                              <span>Complete {track.current_stage}</span>
                              <ArrowRight className="w-3 h-3" />
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Advance Component Stage Modal */}
      {advanceModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-lg border-2 border-slate-300 max-w-md w-full p-5 space-y-4 shadow-xl" data-testid="advance-modal">
            <div className="flex items-center justify-between border-b pb-3">
              <div>
                <h3 className="font-bold text-slate-900 text-sm uppercase tracking-wider">
                  {`Complete ${advanceModal.component} Sub-Stage`}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Advance <b className="text-slate-800">{advanceModal.stage}</b> to the next stage or Ready status.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAdvanceModal(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {errorMsg && (
              <div className="p-2.5 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                {errorMsg}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                  Assign Karigar (Worker)
                </label>
                <select
                  value={selectedWorkerId}
                  onChange={(e) => setSelectedWorkerId(e.target.value)}
                  className="w-full border-2 border-slate-300 rounded px-2.5 py-1.5 text-xs bg-white focus:border-[#C27842] outline-none"
                  data-testid="advance-worker-select"
                >
                  <option value="">-- No Karigar Assigned --</option>
                  {workers.map((w) => (
                    <option key={w.id} value={w.id}>
                      {`${w.name} ${w.rate_per_pair ? `(₹${w.rate_per_pair}/pr)` : ""} - ${w.skill || "general"}`}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                  Completed Quantity (Pairs)
                </label>
                <input
                  type="number"
                  value={completedQty}
                  onChange={(e) => setCompletedQty(e.target.value)}
                  className="w-full border-2 border-slate-300 rounded px-2.5 py-1.5 text-xs focus:border-[#C27842] outline-none"
                  data-testid="advance-qty-input"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-1">
                  Notes (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. inspected and passed batch"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full border-2 border-slate-300 rounded px-2.5 py-1.5 text-xs focus:border-[#C27842] outline-none"
                />
              </div>
            </div>

            <div className="flex gap-2 pt-2 border-t">
              <BtnPrimary
                onClick={submitAdvance}
                disabled={submitting}
                className="flex-1 bg-[#C27842] border-[#C27842] hover:bg-[#a55f2d] text-xs py-2"
                data-testid="confirm-advance-stage-btn"
              >
                {submitting ? "Advancing..." : `Confirm & Complete ${advanceModal.stage}`}
              </BtnPrimary>
              <BtnSecondary onClick={() => setAdvanceModal(null)} className="text-xs">
                Cancel
              </BtnSecondary>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
