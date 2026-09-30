import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import ComponentProductionBoard from "../../components/ComponentProductionBoard";
import { http } from "../../lib/api";
import { broadcastSync } from "../../lib/sync";

jest.mock("../../lib/api", () => ({
  http: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
  inr: (v) => `₹${v}`,
}));

jest.mock("../../lib/sync", () => ({
  broadcastSync: jest.fn(),
  useCrossTabSync: jest.fn(),
}));

describe("Component Production Board (Stage 5)", () => {
  const mockWorkers = [
    { id: "w-1", name: "Ramesh Kumar", roles: ["cutting"] },
    { id: "w-2", name: "Suresh Sole Specialist", roles: ["finishing"] },
  ];

  const mockGroups = [
    {
      key: "grp-flat-1",
      id: "grp-flat-1",
      po_number: "PO-2026-001",
      style_code: "FLAT-LOAFER",
      color: "Tan",
      stage: "cutting",
      quantity: 120,
      rows: [
        {
          id: "job-flat-1",
          po_number: "PO-2026-001",
          style_code: "FLAT-LOAFER",
          color: "Tan",
          stage: "cutting",
          quantity: 120,
          component_specs: {
            footwear_type: "flat",
            components: {
              upper: { stages: ["cutting", "stitching"], is_inhouse: true },
              bottom: { stages: ["cutting"], is_inhouse: true },
              sole: { stages: [], is_inhouse: false },
            },
          },
          component_tracks: {
            upper: { status: "in_progress", current_stage: "cutting", completed_qty: 0 },
            bottom: { status: "ready", current_stage: "ready", completed_qty: 120 },
            sole: { status: "ready", current_stage: "ready", completed_qty: 120 },
          },
          assignments: {},
        },
      ],
    },
    {
      key: "grp-heel-1",
      id: "grp-heel-1",
      po_number: "PO-2026-002",
      style_code: "HEEL-STILETTO",
      color: "Black",
      stage: "cutting",
      quantity: 80,
      rows: [
        {
          id: "job-heel-1",
          po_number: "PO-2026-002",
          style_code: "HEEL-STILETTO",
          color: "Black",
          stage: "cutting",
          quantity: 80,
          component_specs: {
            footwear_type: "heel",
            components: {
              upper: { stages: ["cutting", "stitching"], is_inhouse: true },
              bottom: { stages: ["cutting"], is_inhouse: true },
              sole: { stages: ["cutting", "finishing"], is_inhouse: true },
              heel_gola: { stages: ["cover_cutting", "pasting"], is_inhouse: true },
            },
          },
          component_tracks: {
            upper: { status: "ready", current_stage: "ready", completed_qty: 80 },
            bottom: { status: "ready", current_stage: "ready", completed_qty: 80 },
            sole: { status: "in_progress", current_stage: "cutting", completed_qty: 0 },
            heel_gola: { status: "in_progress", current_stage: "cover_cutting", completed_qty: 0 },
          },
          assignments: {},
        },
      ],
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders component board with flat and heel cards and displays gate statuses", () => {
    render(
      <ComponentProductionBoard
        groups={mockGroups}
        workers={mockWorkers}
        styleByCode={{}}
        canEdit={true}
        onRefresh={jest.fn()}
      />
    );

    expect(screen.getByTestId("component-production-board")).toBeInTheDocument();
    expect(screen.getByText("FLAT-LOAFER")).toBeInTheDocument();
    expect(screen.getByText("HEEL-STILETTO")).toBeInTheDocument();

    // FLAT style Khokha gate is waiting (upper not ready), Sole gate is ready (PVC sole)
    const flatLastingGate = screen.getByTestId("gate-lasting-grp-flat-1");
    expect(flatLastingGate).toHaveTextContent("Khokha Gate (Lasting): Waiting");

    const flatSoleGate = screen.getByTestId("gate-sole-grp-flat-1");
    expect(flatSoleGate).toHaveTextContent("Sole Pasting Gate: Ready");

    // HEEL style Khokha gate is ready, Sole gate is waiting
    const heelLastingGate = screen.getByTestId("gate-lasting-grp-heel-1");
    expect(heelLastingGate).toHaveTextContent("Khokha Gate (Lasting): Ready");

    const heelSoleGate = screen.getByTestId("gate-sole-grp-heel-1");
    expect(heelSoleGate).toHaveTextContent("Sole Pasting Gate: Waiting");
  });

  test("filtering by footwear type works correctly", () => {
    render(
      <ComponentProductionBoard
        groups={mockGroups}
        workers={mockWorkers}
        styleByCode={{}}
        canEdit={true}
        onRefresh={jest.fn()}
      />
    );

    // Filter to heel only
    const heelFilterBtn = screen.getByTestId("filter-type-heel");
    fireEvent.click(heelFilterBtn);

    expect(screen.queryByText("FLAT-LOAFER")).not.toBeInTheDocument();
    expect(screen.getByText("HEEL-STILETTO")).toBeInTheDocument();

    // Filter to flat only
    const flatFilterBtn = screen.getByTestId("filter-type-flat");
    fireEvent.click(flatFilterBtn);

    expect(screen.getByText("FLAT-LOAFER")).toBeInTheDocument();
    expect(screen.queryByText("HEEL-STILETTO")).not.toBeInTheDocument();
  });

  test("heel style card renders 4 swimlanes including Heel / Platform / Gola", () => {
    render(
      <ComponentProductionBoard
        groups={[mockGroups[1]]} // heel only
        workers={mockWorkers}
        styleByCode={{}}
        canEdit={true}
        onRefresh={jest.fn()}
      />
    );

    expect(screen.getByText("Upper Track")).toBeInTheDocument();
    expect(screen.getByText("Bottom / Insole Track")).toBeInTheDocument();
    expect(screen.getByText("Sole Track")).toBeInTheDocument();
    expect(screen.getByText("Heel / Platform / Gola")).toBeInTheDocument();
  });

  test("advancing a component stage opens modal and calls PATCH /production/jobs/{jid}/component-stage", async () => {
    const onRefresh = jest.fn();
    http.patch.mockResolvedValueOnce({ data: { message: "Updated" } });

    render(
      <ComponentProductionBoard
        groups={[mockGroups[0]]} // flat
        workers={mockWorkers}
        styleByCode={{}}
        canEdit={true}
        onRefresh={onRefresh}
      />
    );

    // Upper track is at 'cutting'
    const advanceBtn = screen.getByTestId("advance-btn-upper-grp-flat-1");
    expect(advanceBtn).toBeInTheDocument();
    fireEvent.click(advanceBtn);

    // Modal should appear
    expect(screen.getByTestId("advance-modal")).toBeInTheDocument();
    expect(screen.getByTestId("advance-worker-select")).toBeInTheDocument();

    // Select worker
    fireEvent.change(screen.getByTestId("advance-worker-select"), {
      target: { value: "w-1" },
    });

    // Submit advance
    const submitBtn = screen.getByTestId("confirm-advance-stage-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.patch).toHaveBeenCalledWith(
        "/production/jobs/job-flat-1/component-stage",
        expect.objectContaining({
          component: "upper",
          stage: "cutting",
          completed_qty: 120,
          worker_id: "w-1",
        })
      );
    });

    expect(broadcastSync).toHaveBeenCalledWith("production", { action: "component_advance" });
    expect(onRefresh).toHaveBeenCalled();
  });
});
