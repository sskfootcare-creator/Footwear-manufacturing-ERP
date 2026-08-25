import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ResponsiveTable from "../ResponsiveTable";


describe("ResponsiveTable Virtualization", () => {
  const columns = [
    { key: "id", header: "ID", primary: true },
    { key: "name", header: "Product Name" },
    { key: "category", header: "Category" },
    { key: "price", header: "Price", render: (r) => `₹${r.price}` },
    { key: "stock", header: "Stock" },
  ];

  test("renders 5000 rows with virtualization enabled without rendering all 5000 into the DOM simultaneously", () => {
    const dataset = Array.from({ length: 5000 }, (_, i) => ({
      id: `ITEM-${i}`,
      name: `Synthetic Product ${i}`,
      category: i % 2 === 0 ? "Footwear" : "Accessory",
      price: 500 + (i % 100),
      stock: (i * 7) % 50,
    }));

    render(
      <ResponsiveTable
        columns={columns}
        rows={dataset}
        rowKey={(r) => r.id}
        testId="virtual-table-test"
        maxHeight="500px"
      />
    );

    const tableRoot = screen.getByTestId("virtual-table-test");
    expect(tableRoot).toBeInTheDocument();

    // Verify only a small window of rows exist in the DOM (not 5,000)
    const domRows = document.querySelectorAll("tr[data-index]");
    expect(domRows.length).toBeGreaterThan(0);
    expect(domRows.length).toBeLessThan(100);
  });

  test("renders normal dataset correctly with identical appearance and values", () => {
    const smallDataset = [
      { id: "S1", name: "Shoe A", category: "Formal", price: 1200, stock: 10 },
      { id: "S2", name: "Shoe B", category: "Casual", price: 800, stock: 25 },
    ];

    render(
      <ResponsiveTable
        columns={columns}
        rows={smallDataset}
        rowKey={(r) => r.id}
        testId="small-table-test"
      />
    );

    expect(screen.getAllByText("Shoe A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Shoe B").length).toBeGreaterThan(0);
    expect(screen.getAllByText("₹1200").length).toBeGreaterThan(0);
    expect(screen.getAllByText("₹800").length).toBeGreaterThan(0);
  });
});

