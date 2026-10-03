import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom";
import Production from "../Production";
import ComponentProductionBoard from "../../components/ComponentProductionBoard";
import { http } from "../../lib/api";

jest.mock("../../lib/auth", () => ({
  useAuth: () => ({
    user: { email: "admin@sskfootwear.com", role: "admin", name: "Admin" },
  }),
}));

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
      patch: jest.fn(),
    },
    inr: (v) => `₹${v}`,
  };
});

describe("Bottom Component Sub-tasks & Ready-to-Use Sole Assignment Disabling", () => {
  const mockWorkers = [
    { id: "w-1", name: "Ramesh Sharma", skill: "cutting", rate_per_pair: 15.0, active: true },
    { id: "w-2", name: "Sunil Kumar", skill: "stitching", rate_per_pair: 12.0, active: true },
  ];

  const readySoleJob = {
    id: "job-ready-sole-1",
    po_id: "po-rs-1",
    po_number: "PO-2026-RS1",
    client_name: "METRO SHOES",
    style_id: "style-rs-1",
    style_code: "STYLE_RS_01",
    po_style_code: "STYLE_RS_01",
    created_at: "2026-10-01T10:00:00Z",
    color: "BLACK",
    size: "7",
    quantity: 300,
    completed_qty: 0,
    stage: "planning",
    archived: false,
    footwear_type: "flat",
    sole_ready_to_use: true,
    component_specs: {
      footwear_type: "flat",
      components: {
        upper: { stages: ["cutting", "stitching"], is_inhouse: true },
        bottom: { stages: ["cutting", "stitching", "stamping"], is_inhouse: true },
        sole: { stages: [], is_ready_to_use: true, is_inhouse: false },
      },
    },
    component_tracks: {
      upper: { status: "in_progress", current_stage: "cutting", completed_qty: 0 },
      bottom: { status: "in_progress", current_stage: "cutting", completed_qty: 0 },
      sole: { status: "ready", current_stage: "ready", completed_qty: 300 },
    },
    components: {
      upper_done: false,
      bottom_done: false,
      sole_done: true,
    },
    assignments: {},
  };

  const mockGroups = [
    {
      key: "grp-rs-1",
      id: "grp-rs-1",
      po_number: "PO-2026-RS1",
      style_code: "STYLE_RS_01",
      color: "BLACK",
      stage: "planning",
      quantity: 300,
      rows: [readySoleJob],
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) {
        return Promise.resolve({ data: [readySoleJob] });
      }
      if (url.startsWith("/workers")) {
        return Promise.resolve({ data: mockWorkers });
      }
      if (url.startsWith("/hr/workers")) {
        return Promise.resolve({ data: mockWorkers });
      }
      if (url.startsWith("/production/settings")) {
        return Promise.resolve({ data: {} });
      }
      if (url.startsWith("/styles")) {
        return Promise.resolve({
          data: [
            {
              id: "style-rs-1",
              code: "STYLE_RS_01",
              name: "Ready Sole Loafer",
              sole_ready_to_use: true,
              footwear_type: "flat",
              component_specs: readySoleJob.component_specs,
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
    http.post.mockResolvedValue({ status: "ok", data: {} });
    http.patch.mockResolvedValue({ data: readySoleJob });
  });

  test("ComponentProductionBoard displays cutting, stitching, and stamping / brand marking for bottom component", () => {
    render(
      <MemoryRouter>
        <ComponentProductionBoard groups={mockGroups} onRefresh={jest.fn()} />
      </MemoryRouter>
    );

    // Verify Bottom Component Swimlane displays the 3 stages: Cutting, Stitching, Stamping / Brand Marking
    expect(screen.getByText("Bottom / Insole Track")).toBeInTheDocument();
    const bottomTrack = screen.getByTestId("track-bottom-grp-rs-1");
    expect(within(bottomTrack).getByTestId("stage-step-bottom-cutting")).toHaveTextContent("Cutting");
    expect(within(bottomTrack).getByTestId("stage-step-bottom-stitching")).toHaveTextContent("Stitching");
    expect(within(bottomTrack).getByTestId("stage-step-bottom-stamping")).toHaveTextContent("Stamping / Brand Marking");

    // Verify ready-to-use sole swimlane displays vendor-supplied indicator
    expect(screen.getByText(/Ready-to-use \/ Vendor-supplied/i)).toBeInTheDocument();
  });

  test("Production Kanban disables subtask assignment when ready-to-use sole is used in style", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Wait for the job card to render
    await waitFor(() => {
      expect(screen.getByText("PO-2026-RS1")).toBeInTheDocument();
    });

    // Check sole component card shows Ready-to-use Sole indicator
    expect(screen.getByTestId("ready-sole-indicator-PO-2026-RS1::STYLE_RS_01::BLACK")).toBeInTheDocument();
    expect(screen.getByText("Ready-to-use Sole")).toBeInTheDocument();
    expect(screen.getByText("No Sub-tasks")).toBeInTheDocument();

    // Click on Bottom card to open Karigar panel and verify bottom subtasks cutting, stitching, stamping
    const bottomCard = screen.getByTestId("component-card-bottom");
    fireEvent.click(bottomCard);

    // Bottom panel should show all 3 sub-tasks
    const bottomPanel = await screen.findByTestId("comp-karigar-panel-bottom");
    expect(bottomPanel).toBeInTheDocument();
    expect(bottomPanel).toHaveTextContent(/Bottom \/ Insole Track Assignment/i);
    expect(within(bottomPanel).getByText("Cutting")).toBeInTheDocument();
    expect(within(bottomPanel).getByText("Stitching")).toBeInTheDocument();
    expect(within(bottomPanel).getByText("Stamping / Brand Marking")).toBeInTheDocument();

    // Click on Sole card to open its Karigar panel
    const soleCard = screen.getByTestId("component-card-sole");
    fireEvent.click(soleCard);

    // Sole panel should show Ready-to-Use Sole and disabled sub-tasks banner
    const solePanel = await screen.findByTestId("comp-karigar-panel-sole");
    expect(solePanel).toBeInTheDocument();
    expect(screen.getByTestId("sole-ready-to-use-disabled-banner")).toBeInTheDocument();
    expect(screen.getByText("Sub-tasks Disabled")).toBeInTheDocument();
    expect(screen.getByText("Assignment Disabled")).toBeInTheDocument();
  });
});
