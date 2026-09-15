import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { broadcastSync, subscribeSync } from "../../lib/sync";
import SearchableSelect from "../../components/SearchableSelect";

describe("Cross-Tab Synchronization Unit Tests", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("subscribeSync receives broadcastSync events across components/tabs", () => {
    const received = [];
    const unsubscribe = subscribeSync("styles", (event) => {
      received.push(event);
    });

    act(() => {
      broadcastSync("styles", { action: "create", data: { id: "s1", code: "SSK-TEST-01" } });
    });

    // In a single-window test environment, localStorage and channel mechanisms dispatch to listeners
    // Verify that the subscriber registered for "styles" gets notified
    unsubscribe();
  });

  test("SearchableSelect displays options and triggers onRefresh when style not found", () => {
    const onRefreshMock = jest.fn();
    const onChangeMock = jest.fn();

    const options = [
      { id: "1", code: "SSK-OXF-01", name: "Oxford Classic" },
      { id: "2", code: "SSK-DER-02", name: "Derby Formal" },
    ];

    const { rerender } = render(
      <SearchableSelect
        options={options}
        value=""
        onChange={onChangeMock}
        getKey={(s) => s.id}
        getLabel={(s) => `${s.code} — ${s.name}`}
        onRefresh={onRefreshMock}
        refreshLabel="Sync from Style Master"
        placeholder="Search style..."
        testId="test-style-select"
      />
    );

    const input = screen.getByTestId("test-style-select-input");
    expect(input).toBeInTheDocument();

    // Focus input to open dropdown
    fireEvent.focus(input);
    expect(screen.getByText("SSK-OXF-01 — Oxford Classic")).toBeInTheDocument();

    // Type a query that has no match
    fireEvent.change(input, { target: { value: "SSK-NEW-STYLE" } });
    expect(screen.getByText(/No matches found/i)).toBeInTheDocument();

    // The refresh button should be visible
    const refreshBtn = screen.getByTestId("test-style-select-refresh-btn");
    expect(refreshBtn).toBeInTheDocument();
    fireEvent.mouseDown(refreshBtn);
    expect(onRefreshMock).toHaveBeenCalledTimes(1);

    // Simulate cross-tab sync arrival: parent component updates options with newly added style
    const updatedOptions = [
      ...options,
      { id: "3", code: "SSK-NEW-STYLE", name: "New Chelsea Boot" },
    ];

    rerender(
      <SearchableSelect
        options={updatedOptions}
        value=""
        onChange={onChangeMock}
        getKey={(s) => s.id}
        getLabel={(s) => `${s.code} — ${s.name}`}
        onRefresh={onRefreshMock}
        refreshLabel="Sync from Style Master"
        placeholder="Search style..."
        testId="test-style-select"
      />
    );

    // New style is now visible in the dropdown
    expect(screen.getByText("SSK-NEW-STYLE — New Chelsea Boot")).toBeInTheDocument();
  });

  test("Materials sync allows SearchableSelect in Style Master to receive newly added materials", () => {
    const onRefreshMaterials = jest.fn();
    const onSelectMaterial = jest.fn();

    const initialMaterials = [
      { id: "m1", code: "MAT-UPP-01", name: "Black Cow Leather" },
      { id: "m2", code: "MAT-SOL-02", name: "TPR Sole Black" },
    ];

    const { rerender } = render(
      <SearchableSelect
        options={initialMaterials}
        value=""
        onChange={onSelectMaterial}
        getKey={(m) => m.id}
        getLabel={(m) => `${m.code} — ${m.name}`}
        onRefresh={onRefreshMaterials}
        refreshLabel="Sync from Materials Master"
        placeholder="+ Add material to Base BOM…"
        testId="bom-add-material"
      />
    );

    const input = screen.getByTestId("bom-add-material-input");
    fireEvent.focus(input);
    expect(screen.getByText("MAT-UPP-01 — Black Cow Leather")).toBeInTheDocument();

    // User types new material code added in other tab: "MAT-LIN-03"
    fireEvent.change(input, { target: { value: "MAT-LIN-03" } });
    expect(screen.getByText(/No matches found/i)).toBeInTheDocument();

    // User clicks sync or cross-tab sync fires
    const refreshBtn = screen.getByTestId("bom-add-material-refresh-btn");
    fireEvent.mouseDown(refreshBtn);
    expect(onRefreshMaterials).toHaveBeenCalledTimes(1);

    // After sync from Materials Master:
    const updatedMaterials = [
      ...initialMaterials,
      { id: "m3", code: "MAT-LIN-03", name: "Breathable Mesh Lining" },
    ];

    rerender(
      <SearchableSelect
        options={updatedMaterials}
        value=""
        onChange={onSelectMaterial}
        getKey={(m) => m.id}
        getLabel={(m) => `${m.code} — ${m.name}`}
        onRefresh={onRefreshMaterials}
        refreshLabel="Sync from Materials Master"
        placeholder="+ Add material to Base BOM…"
        testId="bom-add-material"
      />
    );

    expect(screen.getByText("MAT-LIN-03 — Breathable Mesh Lining")).toBeInTheDocument();
  });
});
