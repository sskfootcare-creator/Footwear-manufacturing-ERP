import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom";
import Production from "../Production";
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

describe("Parallel Component Production & Karigar Assignment on Kanban Card", () => {
  const mockJobs = [
    {
      id: "job-flat-101",
      po_id: "po-101",
      po_number: "PO-2026-901",
      client_name: "SIYARAM SILK MILLS LTD.",
      style_id: "style-101",
      style_code: "SSK_00196",
      po_style_code: "5ZE1026WFFLT-0-0603",
      created_at: "2026-09-10T10:00:00Z",
      color: "CREAM",
      size: "6",
      quantity: 528,
      completed_qty: 0,
      stage: "cutting",
      archived: false,
      footwear_type: "flat",
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
        bottom: { status: "ready", current_stage: "ready", completed_qty: 528 },
        sole: { status: "ready", current_stage: "ready", completed_qty: 528 },
      },
      components: {
        upper_done: false,
        bottom_done: true,
        sole_done: true,
      },
      assignments: {
        upper: {
          worker_id: "w-1",
          worker_name: "Ramesh Kumar",
          rate_per_pair: 15.0,
        },
        bottom: {
          worker_id: "w-2",
          worker_name: "Suresh Insole Specialist",
          rate_per_pair: 12.0,
        },
        lasting: {
          worker_id: "w-3",
          worker_name: "Mohan Master",
          rate_per_pair: 20.0,
        },
      },
    },
  ];

  const mockWorkers = [
    { id: "w-1", name: "Ramesh Kumar", skill: "cutting", rate_per_pair: 15.0, active: true },
    { id: "w-2", name: "Suresh Insole Specialist", skill: "cutting", rate_per_pair: 12.0, active: true },
    { id: "w-3", name: "Mohan Master", skill: "lasting", rate_per_pair: 20.0, active: true },
    { id: "w-4", name: "Sole Prep Tech", skill: "finishing", rate_per_pair: 8.0, active: true },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) return Promise.resolve({ data: mockJobs });
      if (url.startsWith("/workers")) return Promise.resolve({ data: mockWorkers });
      if (url.startsWith("/styles")) {
        return Promise.resolve({
          data: [{ code: "SSK_00196", name: "Flat Loafer Sandal", footwear_type: "flat" }],
        });
      }
      if (url.startsWith("/production/archive")) return Promise.resolve({ data: [] });
      if (url.startsWith("/packing-lists")) return Promise.resolve({ data: [] });
      if (url.startsWith("/dispatch-records")) return Promise.resolve({ data: [] });
      if (url.startsWith("/invoices")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });
  });

  test("renders unified Parallel Components section on Kanban card with gate indicators and direct karigar assignments", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Wait for the Kanban card to render
    const styleElem = await screen.findByTestId("style-code-PO-2026-901::SSK_00196::CREAM");
    expect(styleElem).toBeInTheDocument();


    // Verify Upper track card has Ramesh Kumar assigned
    expect(screen.getByText("Upper")).toBeInTheDocument();
    expect(screen.getByText("Ramesh Kumar")).toBeInTheDocument();

    // Verify Bottom track card has Suresh assigned
    expect(screen.getByText("Bottom")).toBeInTheDocument();
    expect(screen.getByText("Suresh Insole Specialist")).toBeInTheDocument();

    // Verify Sole track card shows + Assign Karigar
    expect(screen.getByTestId("component-card-sole")).toBeInTheDocument();
    expect(screen.getByTestId("assign-PO-2026-901::SSK_00196::CREAM-sole")).toBeInTheDocument();

    // Verify Assembly Karigars row
    expect(screen.getByText("Assembly Karigars")).toBeInTheDocument();
    const lastingBtn = screen.getByTestId("assign-PO-2026-901::SSK_00196::CREAM-lasting");
    expect(lastingBtn).toHaveTextContent("Mohan Master");
    expect(lastingBtn).toHaveTextContent("₹20");
  });

  test("clicking component status button toggles readiness via PATCH /production/jobs/{jid}/components", async () => {
    http.patch.mockResolvedValueOnce({ data: { message: "Updated" } });

    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    const toggleUpperBtn = await screen.findByTestId("toggle-comp-PO-2026-901::SSK_00196::CREAM-upper");
    expect(toggleUpperBtn).toBeInTheDocument();
    expect(toggleUpperBtn).toHaveTextContent("Pending");

    // Click to mark Upper ready
    fireEvent.click(toggleUpperBtn);

    await waitFor(() => {
      expect(http.patch).toHaveBeenCalledWith(
        "/production/jobs/job-flat-101/components",
        { upper_done: true }
      );
    });
  });

  test("clicking Karigar slot opens Assign Karigar modal pre-scoped to that component role", async () => {
    http.post.mockResolvedValueOnce({ data: { message: "Updated" } });

    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Click assign button on Sole track
    const assignSoleBtn = await screen.findByTestId("assign-PO-2026-901::SSK_00196::CREAM-sole");
    fireEvent.click(assignSoleBtn);

    // Modal dialog appears with header indicating Sole Track
    const assignDialog = await screen.findByTestId("assign-dialog");
    expect(assignDialog).toBeInTheDocument();
    expect(screen.getByText(/Sole Track/i)).toBeInTheDocument();

    // Pick Sole Prep Tech
    const pickBtn = screen.getByText("Sole Prep Tech");
    fireEvent.click(pickBtn);

    // Save assignment
    const saveBtn = screen.getByTestId("assign-save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/production/jobs/job-flat-101/components/sole/bulk-assign",
        expect.objectContaining({
          worker_id: "w-4",
          rate_per_pair: 8,
          overwrite: false,
        })
      );
    });
  });
});
