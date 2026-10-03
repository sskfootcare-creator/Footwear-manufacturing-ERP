import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom";
import Production from "../Production";
import Styles from "../Styles";
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

describe("Component Karigar Delegation & Outside Labour Work", () => {
  const mockJobs = [
    {
      id: "job-101",
      po_id: "po-101",
      po_number: "PO-2026-888",
      client_name: "METRO BRANDS LTD",
      style_id: "style-101",
      style_code: "SSK_TEST_STYLE",
      created_at: "2026-09-15T10:00:00Z",
      color: "BLACK",
      size: "7",
      quantity: 300,
      completed_qty: 0,
      stage: "planning",
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
        upper: { status: "ready", current_stage: "ready", completed_qty: 300 },
        bottom: { status: "ready", current_stage: "ready", completed_qty: 300 },
        sole: { status: "ready", current_stage: "ready", completed_qty: 300 },
      },
      components: {
        upper_done: true,
        bottom_done: true,
        sole_done: true,
      },
      assignments: {
        upper: {
          worker_id: "w-1",
          worker_name: "Ramesh Lead",
          rate_per_pair: 20.0,
        },
        "upper.stitching": {
          worker_id: "w-5",
          worker_name: "Pooja Stitcher",
          rate_per_pair: 14.0,
        },
        bottom: {
          worker_id: "w-2",
          worker_name: "Suresh Bottom Lead",
          rate_per_pair: 15.0,
        },
        sole: {
          worker_id: "w-4",
          worker_name: "Dinesh Sole Lead",
          rate_per_pair: 10.0,
        },
      },
      outside_labour: [
        {
          name: "Gold Foil Embossing",
          component: "upper",
          vendor: "Royal Prints",
          rate: 6.5,
          is_outside: true,
        },
      ],
    },
  ];

  const mockWorkers = [
    { id: "w-1", name: "Ramesh Lead", skill: "cutting", rate_per_pair: 20.0, active: true },
    { id: "w-2", name: "Suresh Bottom Lead", skill: "cutting", rate_per_pair: 15.0, active: true },
    { id: "w-4", name: "Dinesh Sole Lead", skill: "finishing", rate_per_pair: 10.0, active: true },
    { id: "w-5", name: "Pooja Stitcher", skill: "stitching", rate_per_pair: 14.0, active: true },
  ];

  const mockStyles = [
    {
      id: "style-101",
      code: "SSK_TEST_STYLE",
      name: "Classic Loafer",
      footwear_type: "flat",
      status: "active",
      bom: [],
      labor: [],
      outside_labour: [
        {
          name: "Gold Foil Embossing",
          component: "upper",
          vendor: "Royal Prints",
          rate: 6.5,
          is_outside: true,
        },
      ],
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) return Promise.resolve({ data: mockJobs });
      if (url.startsWith("/workers")) return Promise.resolve({ data: mockWorkers });
      if (url.startsWith("/styles")) return Promise.resolve({ data: mockStyles });
      if (url.startsWith("/materials")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });
    http.post.mockResolvedValue({ status: "ok", data: {} });
    http.patch.mockResolvedValue({ data: mockJobs[0] });
  });

  test("Production Kanban displays main assigned person and expands subtasks + outside work for that component", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Main assigned person on Upper
    expect(await screen.findByText("Ramesh Lead")).toBeInTheDocument();

    // Upper has outside labour badge indicator
    expect(screen.getByText(/1 Outside/i)).toBeInTheDocument();

    // Click Upper component card to expand its detailed panel
    const upperCard = screen.getByTestId("component-card-upper");
    fireEvent.click(upperCard);

    // Check panel has appeared
    expect(await screen.findByTestId("comp-karigar-panel-upper")).toBeInTheDocument();

    // Section 1: Main Component Assigned Person
    expect(screen.getByText(/1\. Component Assigned Person/i)).toBeInTheDocument();

    // Section 2: Sub-tasks delegatable to other workers (e.g. Stitching to Pooja Stitcher) with rate displayed on chip
    expect(screen.getByText(/2\. Process Sub-tasks/i)).toBeInTheDocument();
    const poojaEl = screen.getByText("Pooja Stitcher");
    expect(poojaEl).toBeInTheDocument();
    expect(poojaEl.closest("button")).toHaveTextContent("₹14/pr");

    // Inlined PO number, Style code in JobCard header
    expect(screen.getByTestId("po-number-PO-2026-888::SSK_TEST_STYLE::BLACK")).toHaveTextContent("PO-2026-888");
    expect(screen.getByTestId("style-code-PO-2026-888::SSK_TEST_STYLE::BLACK")).toHaveTextContent("SSK_TEST_STYLE");

    // Section 3: Outside Labour Work part of Upper (no longer duplicate 'Extra')
    expect(screen.getByText(/3\. Outside Labour Work/i)).toBeInTheDocument();
    expect(screen.getByText("Gold Foil Embossing")).toBeInTheDocument();
    expect(screen.getByText(/Vendor:/i)).toBeInTheDocument();
    expect(screen.getByText("Royal Prints")).toBeInTheDocument();
  });

  test("Outside Labour is managed in Component Karigar panel without duplicate planning section", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Verify duplicate Outside Labour Work (Planning) is removed from top of planning stage
    expect(screen.queryByText(/Outside Labour Work \(Planning\)/i)).not.toBeInTheDocument();

    // Expand Upper card to access Outside Labour
    const upperCard = await screen.findByTestId("component-card-upper");
    fireEvent.click(upperCard);

    // Section 3 is present in component panel
    expect(await screen.findByText(/3\. Outside Labour Work/i)).toBeInTheDocument();
    expect(screen.getByText("Gold Foil Embossing")).toBeInTheDocument();
  });

  test("Style Master includes Extra Outside Labour Work section restricted to upper, bottom, or sole", async () => {
    render(
      <MemoryRouter>
        <Styles />
      </MemoryRouter>
    );

    // Open style create drawer
    const createBtn = await screen.findByTestId("add-style-btn");
    fireEvent.click(createBtn);

    // Go to Costing / Labor tab
    const costingTab = await screen.findByTestId("tab-labor-overheads");
    fireEvent.click(costingTab);

    // Check Extra Outside Labour Work section exists
    expect(await screen.findByText("Extra Outside Labour Work")).toBeInTheDocument();
    const addOutsideBtn = screen.getByTestId("outside-labour-add");
    expect(addOutsideBtn).toBeInTheDocument();

    // Click Add Outside Labour
    fireEvent.click(addOutsideBtn);

    // Verify newly added row has component select with ONLY upper, bottom, sole
    const selects = screen.getAllByRole("combobox");
    const compSelect = selects.find((s) => s.innerHTML.includes("Upper") && s.innerHTML.includes("Sole"));
    expect(compSelect).toBeInTheDocument();
    const availableOptions = Array.from(compSelect.options).map((o) => o.value);
    expect(availableOptions).toEqual(["upper", "bottom", "sole"]);
  });
});
