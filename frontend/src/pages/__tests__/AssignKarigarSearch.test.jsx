import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
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

describe("Assign Karigar Modal Search Feature", () => {
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
      },
    },
  ];

  const mockWorkers = [
    { id: "w-1", name: "Ramesh Kumar", skill: "cutting", rate_per_pair: 15.0, phone: "9876543210", active: true },
    { id: "w-2", name: "Kamlesh Dabariya", skill: "general", rate_per_pair: 10.0, phone: "9002220469", active: true },
    { id: "w-3", name: "Kalim Khan", skill: "stitching", rate_per_pair: 25.0, phone: "7800156499", active: true },
    { id: "w-4", name: "Prem Jatoliya", skill: "stitching", rate_per_pair: 25.0, phone: "9829000000", active: true },
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
      return Promise.resolve({ data: [] });
    });
  });

  test("search input filters karigars by name, skill, and phone, and allows instant selection", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Open Assign dialog on Upper track
    const assignUpperBtn = await screen.findByTestId("assign-PO-2026-901::SSK_00196::CREAM-upper");
    fireEvent.click(assignUpperBtn);

    const assignDialog = await screen.findByTestId("assign-dialog");
    expect(assignDialog).toBeInTheDocument();

    const { within } = require("@testing-library/react");
    const dialogScope = within(assignDialog);

    // Verify search input is rendered
    const searchInput = dialogScope.getByTestId("assign-worker-search");
    expect(searchInput).toBeInTheDocument();
    expect(searchInput).toHaveAttribute("placeholder", "Search karigar by name, skill, or phone...");

    // All workers visible initially
    expect(dialogScope.getByTestId("assign-worker-w-1")).toBeInTheDocument();
    expect(dialogScope.getByText("Kamlesh Dabariya")).toBeInTheDocument();
    expect(dialogScope.getByText("Kalim Khan")).toBeInTheDocument();
    expect(dialogScope.getByText("Prem Jatoliya")).toBeInTheDocument();

    // Filter by name "Kamlesh"
    fireEvent.change(searchInput, { target: { value: "Kamlesh" } });
    expect(dialogScope.getByText("Kamlesh Dabariya")).toBeInTheDocument();
    expect(dialogScope.queryByText("Kalim Khan")).not.toBeInTheDocument();
    expect(dialogScope.queryByText("Prem Jatoliya")).not.toBeInTheDocument();

    // Filter by phone "7800"
    fireEvent.change(searchInput, { target: { value: "7800" } });
    expect(dialogScope.getByText("Kalim Khan")).toBeInTheDocument();
    expect(dialogScope.queryByText("Kamlesh Dabariya")).not.toBeInTheDocument();

    // Filter by non-existent term
    fireEvent.change(searchInput, { target: { value: "NonExistentName" } });
    expect(dialogScope.getByText("No karigar found")).toBeInTheDocument();
    expect(dialogScope.getByText(/No worker matches/i)).toBeInTheDocument();

    // Click Clear Search button
    const clearBtn = dialogScope.getByText("Clear Search");
    fireEvent.click(clearBtn);
    expect(searchInput.value).toBe("");
    expect(dialogScope.getByText("Kamlesh Dabariya")).toBeInTheDocument();
    expect(dialogScope.getByText("Kalim Khan")).toBeInTheDocument();

    // Press Enter to pick first matching worker
    fireEvent.change(searchInput, { target: { value: "Kalim" } });
    fireEvent.keyDown(searchInput, { key: "Enter", code: "Enter" });

    // Kalim Khan should now be the selected worker
    const kalimBtn = dialogScope.getByTestId("assign-worker-w-3");
    expect(kalimBtn.className).toContain("bg-orange-50");
  });
});
