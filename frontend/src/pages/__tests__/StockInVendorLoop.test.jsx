import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Inventory from "../Inventory";
import Materials from "../Materials";
import { http } from "../../lib/api";

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
    inr: (val) => `₹${Number(val || 0).toLocaleString("en-IN")}`,
  };
});

jest.mock("../../lib/auth", () => ({
  useAuth: () => ({
    user: { id: "user_1", role: "admin", name: "Admin Test", email: "admin@ssk.com" },
  }),
}));

describe("Stock In Vendor Dropdown & Material Vendor Integration (Closed Loop)", () => {
  const mockVendors = [
    { id: "ven_1", name: "Apex Leather Supplies", phone: "9876543210" },
    { id: "ven_2", name: "Crown Soles & Rubber", phone: "9876543211" },
  ];

  const mockMaterials = [
    {
      id: "mat_1",
      code: "LEA-001",
      name: "Black Napa Leather",
      category: "upper",
      unit: "sqft",
      rate: 250,
      preferred_vendor_id: "ven_1",
      balance: 100,
    },
    {
      id: "mat_2",
      code: "SOL-002",
      name: "Sport Outsole Rubber",
      category: "sole",
      unit: "pair",
      rate: 180,
      preferred_vendor_id: "",
      balance: 50,
    },
  ];

  const mockInventory = [
    {
      material_id: "mat_1",
      code: "LEA-001",
      name: "Black Napa Leather",
      category: "upper",
      unit: "sqft",
      current_rate: 250,
      last_purchase_rate: 250,
      weighted_avg_rate: 250,
      stock_in: 100,
      stock_out: 0,
      adjustments: 0,
      balance: 100,
      value: 25000,
      preferred_vendor_id: "ven_1",
      vendor_name: "Apex Leather Supplies",
    },
    {
      material_id: "mat_2",
      code: "SOL-002",
      name: "Sport Outsole Rubber",
      category: "sole",
      unit: "pair",
      current_rate: 180,
      last_purchase_rate: 180,
      weighted_avg_rate: 180,
      stock_in: 50,
      stock_out: 0,
      adjustments: 0,
      balance: 50,
      value: 9000,
      preferred_vendor_id: "",
      vendor_name: "",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url === "/inventory") return Promise.resolve({ data: mockInventory });
      if (url.startsWith("/materials")) return Promise.resolve({ data: mockMaterials });
      if (url === "/inventory/alerts") return Promise.resolve({ data: [] });
      if (url.startsWith("/vendors")) return Promise.resolve({ data: mockVendors });
      return Promise.resolve({ data: [] });
    });
    http.post.mockResolvedValue({ data: { ok: true, id: "mov_new" } });
  });

  test("Inventory page renders Stock In with vendor dropdown and auto-selects preferred vendor", async () => {
    render(
      <MemoryRouter>
        <Inventory />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("LEA-001")).toBeInTheDocument();
    });

    // Verify vendor name appears in the inventory table
    expect(screen.getByText("Apex Leather Supplies")).toBeInTheDocument();

    // Click "Stock In" button
    const stockInBtn = screen.getByTestId("add-stock-in-btn");
    fireEvent.click(stockInBtn);

    // Expect drawer to open with title
    expect(screen.getByText("Stock In (Purchase)")).toBeInTheDocument();

    // Expect Vendor dropdown to be present
    const vendorSelect = screen.getByTestId("movement-vendor-select");
    expect(vendorSelect).toBeInTheDocument();
    expect(screen.getByText("— Select Vendor —")).toBeInTheDocument();
    expect(screen.getByText("Crown Soles & Rubber")).toBeInTheDocument();

    // Select material LEA-001 (which has preferred_vendor_id = 'ven_1')
    const materialSelect = screen.getByTestId("movement-material");
    fireEvent.change(materialSelect, { target: { value: "mat_1" } });

    // Expect vendorSelect to automatically select ven_1
    await waitFor(() => {
      expect(vendorSelect.value).toBe("ven_1");
    });

    // Check quantity and rate
    const qtyInput = screen.getByTestId("movement-qty");
    fireEvent.change(qtyInput, { target: { value: "25" } });

    // Submit movement
    const saveBtn = screen.getByTestId("movement-save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/inventory/movements",
        expect.objectContaining({
          type: "in",
          material_id: "mat_1",
          quantity: 25,
          party: "Apex Leather Supplies",
          vendor_id: "ven_1",
        })
      );
    });
  });

  test("Stock In opens QuickAddVendorModal, creates new vendor, and selects it", async () => {
    http.post.mockImplementation((url, body) => {
      if (url === "/vendors") {
        return Promise.resolve({
          data: { id: "ven_new_99", name: body.name, phone: body.phone },
        });
      }
      return Promise.resolve({ data: { ok: true } });
    });

    render(
      <MemoryRouter>
        <Inventory />
      </MemoryRouter>
    );

    await waitFor(() => screen.getByText("LEA-001"));

    // Open Stock In
    fireEvent.click(screen.getByTestId("add-stock-in-btn"));

    // Click "+ New Vendor" button
    const addVendorBtn = screen.getByTestId("stock-in-add-vendor-btn");
    fireEvent.click(addVendorBtn);

    // Modal opens
    expect(screen.getByTestId("quick-add-vendor-modal")).toBeInTheDocument();

    // Fill vendor name
    const vendorNameInput = screen.getByTestId("quick-vendor-name");
    fireEvent.change(vendorNameInput, { target: { value: "Supreme Leather Works" } });

    // Click Save Vendor
    const saveVendorBtn = screen.getByTestId("quick-vendor-save-btn");
    fireEvent.click(saveVendorBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/vendors",
        expect.objectContaining({ name: "Supreme Leather Works" })
      );
    });

    // Ensure the new vendor is selected in the movement drawer
    const vendorSelect = screen.getByTestId("movement-vendor-select");
    await waitFor(() => {
      expect(vendorSelect.value).toBe("ven_new_99");
    });
  });

  test("Materials page renders Vendor column and Vendor select with New Vendor option", async () => {
    render(
      <MemoryRouter>
        <Materials />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("LEA-001")).toBeInTheDocument();
    });

    // Check table headers include "Vendor"
    expect(screen.getByRole("columnheader", { name: "Vendor" })).toBeInTheDocument();

    // LEA-001 has preferred_vendor_id "ven_1" -> Apex Leather Supplies
    expect(screen.getByTestId("material-vendor-LEA-001")).toHaveTextContent("Apex Leather Supplies");

    // Click "Add Material"
    const addMatBtn = screen.getByRole("button", { name: /Add Material/i });
    fireEvent.click(addMatBtn);

    // Form has Vendor / Supplier selector and "+ New Vendor" button
    expect(screen.getByTestId("form-mat-vendor")).toBeInTheDocument();
    expect(screen.getByTestId("mat-add-vendor-btn")).toBeInTheDocument();
  });
});
