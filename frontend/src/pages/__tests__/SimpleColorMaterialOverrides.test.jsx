import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Styles from "../Styles";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    ...actual,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    },
  };
});

describe("Flexible Color BOM Overrides UI in Styles.jsx", () => {
  const mockMaterials = [
    { id: "mat-1", code: "MAT-BLK-UP", name: "Black Box Leather", category: "upper", rate: 100, unit: "sqft" },
    { id: "mat-2", code: "MAT-TAN-UP", name: "Tan Suede Leather", category: "upper", rate: 160, unit: "sqft" },
    { id: "mat-3", code: "MAT-INS-01", name: "Standard Insole Board", category: "insole", rate: 35, unit: "sheet" },
    { id: "mat-4", code: "MAT-COV-01", name: "Insole PU Cover", category: "cover", rate: 20, unit: "sqft" },
    { id: "mat-5", code: "MAT-SOL-01", name: "TPR Unit Sole", category: "sole", rate: 55, unit: "pair" },
  ];

  const mockStyle = {
    id: "style-101",
    code: "STY-101",
    name: "Classic Derby",
    category: "Footwear",
    base_size: "7",
    overhead_pct: 0,
    packing_cost: 0,
    margin_pct: 20,
    gst_pct: 5,
    bom: [
      {
        line_id: "line-up-1",
        material_id: "mat-1",
        material_code: "MAT-BLK-UP",
        material_name: "Black Box Leather",
        rate: 100,
        quantity: 1.5,
        yield_per_unit: 1.0,
        waste_pct: 0,
        section: "upper",
      },
      {
        line_id: "line-ins-1",
        material_id: "mat-3",
        material_code: "MAT-INS-01",
        material_name: "Standard Insole Board",
        rate: 35,
        quantity: 1.0,
        yield_per_unit: 1.0,
        waste_pct: 0,
        section: "insole",
      },
      {
        line_id: "line-sol-1",
        material_id: "mat-5",
        material_code: "MAT-SOL-01",
        material_name: "TPR Unit Sole",
        rate: 55,
        quantity: 1.0,
        yield_per_unit: 1.0,
        waste_pct: 0,
        section: "sole",
      },
    ],
    color_bom_overrides: {},
    catalogue_codes: {
      colors: ["Black", "Tan"],
      sizes: ["6", "7", "8", "9"],
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.includes("/styles/summary")) {
        return Promise.resolve({ data: [mockStyle] });
      }
      if (url === "/materials") {
        return Promise.resolve({ data: mockMaterials });
      }
      if (url.includes("/color-master")) {
        return Promise.resolve({ data: [{ color_name: "Black" }, { color_name: "Tan" }, { color_name: "Cherry" }] });
      }
      if (url === "/styles/style-101") {
        return Promise.resolve({ data: mockStyle });
      }
      if (url.includes("/sku-map")) {
        return Promise.resolve({ data: [] });
      }
      if (url.includes("/catalogue-codes")) {
        return Promise.resolve({
          data: {
            colors: ["Black", "Tan"],
            sizes: ["6", "7", "8", "9"],
            rows: [],
            unmapped_colors: [],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });
  });

  test("Full flow: select color, override 2 lines, check indicators, check other colors unchanged, reset override", async () => {
    render(
      <MemoryRouter>
        <Styles />
      </MemoryRouter>
    );

    // 1. Wait for table to load style
    await waitFor(() => {
      expect(screen.getByText("Classic Derby")).toBeInTheDocument();
    });

    // 2. Open edit drawer
    const editBtn = screen.getByRole("button", { name: /^edit$/i });
    fireEvent.click(editBtn);

    // 3. Confirm color selector tabs are visible above BOM table
    await waitFor(() => {
      expect(screen.getByTestId("color-tab-base")).toBeInTheDocument();
      expect(screen.getByTestId("color-tab-Tan")).toBeInTheDocument();
    });

    // By default, Base BOM is active
    expect(screen.getByTestId("bom-rate-line-up-1")).toHaveValue(100);
    expect(screen.getByTestId("bom-qty-line-ins-1")).toHaveValue(1);

    // 4. Select "Tan" color tab
    fireEvent.click(screen.getByTestId("color-tab-Tan"));

    await waitFor(() => {
      expect(screen.getByText(/Editing effective BOM for/i)).toBeInTheDocument();
    });

    // Initially, lines show "Using base" indicator for Tan
    expect(screen.getByTestId("base-bom-indicator-Tan-line-up-1")).toHaveTextContent("Using base");
    expect(screen.getByTestId("base-bom-indicator-Tan-line-ins-1")).toHaveTextContent("Using base");

    // 5. Override line 1 (upper): change rate from 100 to 175 and color to Tan Suede
    const rateInput = screen.getByTestId("bom-rate-line-up-1");
    fireEvent.change(rateInput, { target: { value: "175" } });
    const colorInput = screen.getByTestId("bom-color-line-up-1");
    fireEvent.change(colorInput, { target: { value: "Tan Suede" } });
    expect(colorInput).toHaveValue("Tan Suede");

    // 6. Override line 2 (insole): change qty from 1.0 to 2.5
    const qtyInput = screen.getByTestId("bom-qty-line-ins-1");
    fireEvent.change(qtyInput, { target: { value: "2.5" } });

    // 7. Confirm both show "Custom for Tan" indicator
    await waitFor(() => {
      expect(screen.getByTestId("custom-bom-indicator-Tan-line-up-1")).toHaveTextContent("Custom for Tan");
      expect(screen.getByTestId("custom-bom-indicator-Tan-line-ins-1")).toHaveTextContent("Custom for Tan");
    });

    // Line 3 (sole) was untouched and still shows "Using base"
    expect(screen.getByTestId("base-bom-indicator-Tan-line-sol-1")).toHaveTextContent("Using base");

    // 8. Confirm other color (Black) still shows the base values
    fireEvent.click(screen.getByTestId("color-tab-Black"));

    await waitFor(() => {
      expect(screen.getByTestId("base-bom-indicator-Black-line-up-1")).toHaveTextContent("Using base");
      expect(screen.getByTestId("base-bom-indicator-Black-line-ins-1")).toHaveTextContent("Using base");
    });

    expect(screen.getByTestId("bom-rate-line-up-1")).toHaveValue(100);
    expect(screen.getByTestId("bom-qty-line-ins-1")).toHaveValue(1);

    // 9. Confirm Base BOM still shows original base values
    fireEvent.click(screen.getByTestId("color-tab-base"));
    expect(screen.getByTestId("bom-rate-line-up-1")).toHaveValue(100);
    expect(screen.getByTestId("bom-qty-line-ins-1")).toHaveValue(1);

    // 10. Switch back to Tan and test "Reset to base" on line 1
    fireEvent.click(screen.getByTestId("color-tab-Tan"));

    await waitFor(() => {
      expect(screen.getByTestId("reset-override-line-up-1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("reset-override-line-up-1"));

    // Line 1 should now revert to "Using base" and rate should be 100 again!
    await waitFor(() => {
      expect(screen.getByTestId("base-bom-indicator-Tan-line-up-1")).toHaveTextContent("Using base");
      expect(screen.getByTestId("bom-rate-line-up-1")).toHaveValue(100);
    });

    // Line 2 is still custom for Tan
    expect(screen.getByTestId("custom-bom-indicator-Tan-line-ins-1")).toHaveTextContent("Custom for Tan");
    expect(screen.getByTestId("bom-qty-line-ins-1")).toHaveValue(2.5);
  });
});
