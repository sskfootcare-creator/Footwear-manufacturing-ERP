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

describe("Simple Per-Color Material Overrides UI in Styles.jsx", () => {
  const mockMaterials = [
    { id: "mat-1", code: "MAT-BLK-UP", name: "Black Box Leather", category: "upper", rate: 100, unit: "sqft" },
    { id: "mat-2", code: "MAT-TAN-UP", name: "Tan Suede Leather", category: "upper", rate: 160, unit: "sqft" },
    { id: "mat-3", code: "MAT-INS-01", name: "Standard Insole Board", category: "insole", rate: 35, unit: "sheet" },
    { id: "mat-4", code: "MAT-COV-01", name: "Insole PU Cover", category: "cover", rate: 20, unit: "sqft" },
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
    color_material_overrides: {
      "Tan": {
        "upper": {
          "material_id": "mat-2",
          "material_name": "Tan Suede Leather",
          "material_code": "MAT-TAN-UP",
          "rate": 160.0,
        },
      },
    },
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

  test("Renders style with dynamic section overrides based on style's base BOM", async () => {
    render(
      <MemoryRouter>
        <Styles />
      </MemoryRouter>
    );

    // Wait for table to load style
    await waitFor(() => {
      expect(screen.getByText("Classic Derby")).toBeInTheDocument();
    });

    // Click the Edit button on the style card to open edit drawer
    const editBtn = screen.getByRole("button", { name: /^edit$/i });
    fireEvent.click(editBtn);

    // Wait for drawer to open
    await waitFor(() => {
      expect(screen.getByTestId("color-bom-overrides-section")).toBeInTheDocument();
    });

    // 1. Confirm the BOM table headers do NOT contain "Color"
    const bomTableHeaders = screen.getAllByRole("columnheader").map((th) => th.textContent.trim());
    expect(bomTableHeaders).not.toContain("Color");
    expect(bomTableHeaders).toContain("Material");
    expect(bomTableHeaders).toContain("Section");
    expect(bomTableHeaders).toContain("Rate");
    expect(bomTableHeaders).toContain("Qty");

    // 2. Confirm no per-line color text input in BOM table
    expect(screen.queryByTestId("bom-color-0")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/line color/i)).not.toBeInTheDocument();

    // 3. Confirm color selector pills: "Tan" has "Custom" badge and "Black" shows "Using base BOM"
    expect(screen.getByTestId("color-tab-Tan")).toBeInTheDocument();
    expect(screen.getByTestId("custom-bom-badge-Tan")).toBeInTheDocument();
    expect(screen.getByTestId("custom-bom-badge-Tan").textContent).toBe("Custom");

    expect(screen.getByTestId("color-tab-Black")).toBeInTheDocument();
    expect(screen.getByTestId("base-bom-text-Black")).toBeInTheDocument();
    expect(screen.getByTestId("base-bom-text-Black").textContent).toBe("Using base BOM");

    // 4. Confirm dynamic override sections match the style's base BOM sections ("upper", "insole", "sole")
    expect(screen.getByTestId("override-section-upper")).toBeInTheDocument();
    expect(screen.getByTestId("override-section-insole")).toBeInTheDocument();
    expect(screen.getByTestId("override-section-sole")).toBeInTheDocument();
    // Sections NOT in this style's base BOM (like "cover") are not arbitrarily shown
    expect(screen.queryByTestId("override-section-cover")).not.toBeInTheDocument();

    // Upper override is set to Tan Suede Leather (₹160)
    expect(screen.getByTestId("rate-upper-input")).toHaveValue(160);
    expect(screen.getByTestId("reset-upper-btn")).toBeInTheDocument();

    // Insole and Sole overrides are not set -> show "+ Pick ... Override"
    expect(screen.getByTestId("add-insole-override")).toBeInTheDocument();
    expect(screen.getByTestId("add-sole-override")).toBeInTheDocument();

    // 5. Switch to Black tab -> shows Using base BOM everywhere
    fireEvent.click(screen.getByTestId("color-tab-Black"));

    await waitFor(() => {
      expect(screen.getByTestId("base-bom-indicator-Black")).toBeInTheDocument();
    });
    expect(screen.getByTestId("add-upper-override")).toBeInTheDocument();
    expect(screen.getByTestId("add-insole-override")).toBeInTheDocument();
    expect(screen.getByTestId("add-sole-override")).toBeInTheDocument();
  });

  test("Allows user to override more than one material (multi-material override in a section & dropdown)", async () => {
    const multiMatStyle = {
      ...mockStyle,
      id: "style-multi",
      code: "STY-MULTI",
      name: "Multi Material Sneaker",
      bom: [
        {
          line_id: "line-vamp",
          material_id: "mat-1",
          material_code: "MAT-BLK-UP",
          material_name: "Black Box Leather",
          rate: 100,
          quantity: 1.2,
          yield_per_unit: 1.0,
          waste_pct: 0,
          section: "upper",
          component: "Vamp",
        },
        {
          line_id: "line-collar",
          material_id: "mat-2",
          material_code: "MAT-TAN-UP",
          material_name: "Tan Suede Leather",
          rate: 80,
          quantity: 0.5,
          yield_per_unit: 1.0,
          waste_pct: 0,
          section: "upper",
          component: "Collar",
        },
        {
          line_id: "line-ins",
          material_id: "mat-3",
          material_code: "MAT-INS-01",
          material_name: "Standard Insole Board",
          rate: 35,
          quantity: 1.0,
          yield_per_unit: 1.0,
          waste_pct: 0,
          section: "insole",
        },
      ],
      color_material_overrides: {
        "Tan": {
          "line-vamp": {
            material_id: "mat-2",
            material_name: "Tan Suede Leather",
            material_code: "MAT-TAN-UP",
            rate: 160.0,
          },
        },
      },
    };

    http.get.mockImplementation((url) => {
      if (url.includes("/styles/summary")) {
        return Promise.resolve({ data: [multiMatStyle] });
      }
      if (url === "/materials") {
        return Promise.resolve({ data: mockMaterials });
      }
      if (url.includes("/color-master")) {
        return Promise.resolve({ data: [{ color_name: "Black" }, { color_name: "Tan" }] });
      }
      if (url === "/styles/style-multi") {
        return Promise.resolve({ data: multiMatStyle });
      }
      if (url.includes("/catalogue-codes")) {
        return Promise.resolve({
          data: { colors: ["Black", "Tan"], sizes: ["6", "7", "8"], rows: [] },
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <Styles />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Multi Material Sneaker")).toBeInTheDocument();
    });

    const editBtn = screen.getByRole("button", { name: /^edit$/i });
    fireEvent.click(editBtn);

    await waitFor(() => {
      expect(screen.getByTestId("color-bom-overrides-section")).toBeInTheDocument();
    });

    // Switch to Tan tab where overrides are configured
    fireEvent.click(screen.getByTestId("color-tab-Tan"));

    await waitFor(() => {
      expect(screen.getByTestId("custom-bom-indicator-Tan")).toBeInTheDocument();
    });

    // 1. Confirm + Add Material Override selector is present
    expect(screen.getByTestId("add-extra-material-override-select")).toBeInTheDocument();

    // 2. Both materials in the 'upper' section are rendered so the user can override more than one material
    expect(screen.getByTestId("materials-count-upper")).toHaveTextContent(/2 Materials in this Section:/i);
    expect(screen.getByText(/Vamp: Black Box Leather/i)).toBeInTheDocument();
    expect(screen.getByText(/Collar: Tan Suede Leather/i)).toBeInTheDocument();

    // Vamp has the override (₹160)
    expect(screen.getByTestId("rate-upper-input")).toHaveValue(160);

    // Collar has its own override button to allow overriding a second material
    expect(screen.getByTestId("add-upper-1-override")).toBeInTheDocument();
  });
});
