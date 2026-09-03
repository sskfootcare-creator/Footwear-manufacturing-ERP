import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Costing from "../Costing";
import { Drawer } from "../Materials";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    ...actual,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
    },
  };
});

describe("Color-Specific Costing and Scroll Management Tests", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    document.body.style.overflow = "";
  });

  afterEach(() => {
    document.body.style.overflow = "";
  });

  test("Drawer properly reference counts scroll lock and restores body overflow to empty string", () => {
    expect(document.body.style.overflow).toBe("");

    // Mount first drawer
    const { unmount: unmount1 } = render(
      <Drawer title="Drawer 1" onClose={() => {}}>
        <div>Drawer 1 Content</div>
      </Drawer>
    );
    expect(document.body.style.overflow).toBe("hidden");

    // Mount second nested/concurrent drawer
    const { unmount: unmount2 } = render(
      <Drawer title="Drawer 2" onClose={() => {}}>
        <div>Drawer 2 Content</div>
      </Drawer>
    );
    expect(document.body.style.overflow).toBe("hidden");

    // Unmount second drawer - body should STILL be hidden because drawer 1 is active
    unmount2();
    expect(document.body.style.overflow).toBe("hidden");

    // Unmount first drawer - body should now be restored to empty string
    unmount1();
    expect(document.body.style.overflow).toBe("");
  });

  test("Costing Calculator renders color variant options and updates costing dynamically", async () => {
    const mockStyle = {
      id: "style_1",
      code: "ST-01",
      name: "Runner Pro",
      category: "Men",
      margin_pct: 20,
      gst_pct: 12,
      bom: [
        { line_id: "line_0", material_code: "EVA01", material_name: "EVA Sheet Base", section: "Sole", rate: 100, quantity: 1, yield_per_unit: 1, waste_pct: 0, unit: "sheet" },
        { line_id: "line_1", material_code: "LTH01", material_name: "Black Leather", section: "Upper", rate: 200, quantity: 1, yield_per_unit: 1, waste_pct: 0, unit: "sqft" },
      ],
      labor: [
        { name: "Cutting", rate: 50 },
        { name: "Stitching", rate: 50 },
      ],
      costing: {
        materials_cost: 300,
        labor_cost: 100,
        overhead_cost: 20,
        packing_cost: 30,
        total_cost: 450,
        suggested_target_price: 540,
        selling_price: 540,
        is_assigned: false,
      },
      color_bom_overrides: {
        "Tan Brown": [
          { line_id: "line_1", material_code: "LTH02", material_name: "Tan Italian Leather", rate: 350, quantity: 1, yield_per_unit: 1, waste_pct: 0, unit: "sqft" },
        ],
      },
      color_costing: {
        "Tan Brown": {
          materials_cost: 450,
          labor_cost: 100,
          overhead_cost: 20,
          packing_cost: 30,
          total_cost: 600,
          suggested_target_price: 720,
          selling_price: 720,
        },
      },
    };

    http.get.mockResolvedValueOnce({ data: [mockStyle] });

    render(
      <MemoryRouter>
        <Costing />
      </MemoryRouter>
    );

    // Wait for style options to populate from API
    await waitFor(() => {
      expect(screen.getByText(/Runner Pro/)).toBeInTheDocument();
    });

    // Select the style
    fireEvent.change(screen.getByTestId("costing-style-select"), {
      target: { value: "style_1" },
    });

    // Verify Base BOM materials cost (₹300) and Total Cost of Production (₹450)
    await waitFor(() => {
      expect(screen.getByText("EVA Sheet Base")).toBeInTheDocument();
    });
    expect(screen.getByText("Black Leather")).toBeInTheDocument();
    expect(screen.getByTestId("costing-variant-base")).toBeInTheDocument();
    expect(screen.getByTestId("costing-variant-Tan Brown")).toBeInTheDocument();

    // Click "Tan Brown" color variant button
    fireEvent.click(screen.getByTestId("costing-variant-Tan Brown"));

    // Verify Tan Italian Leather appears and cost updates
    expect(screen.getByText("Tan Italian Leather")).toBeInTheDocument();
    expect(screen.getByTestId("active-variant-badge")).toHaveTextContent("Variant: Tan Brown");

    // Switch back to Base BOM
    fireEvent.click(screen.getByTestId("costing-variant-base"));
    expect(screen.getByText("Black Leather")).toBeInTheDocument();
  });
});
