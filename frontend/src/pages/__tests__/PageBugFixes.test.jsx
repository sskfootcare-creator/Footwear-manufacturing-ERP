import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { useWorkspace } from "../../components/AppShell";
import OnlineOrders from "../OnlineOrders";

function WorkspaceConsumer() {
  const [ws] = useWorkspace();
  return <div data-testid="resolved-workspace">{ws}</div>;
}

describe("Page Bug Fixes Verification", () => {
  afterEach(() => {
    localStorage.clear();
  });

  test("Fix 8: useWorkspace sanitizes invalid workspace string to safe default 'management'", () => {
    localStorage.setItem("workspace", "invalid_corrupted_ws_value");
    render(<WorkspaceConsumer />);
    expect(screen.getByTestId("resolved-workspace")).toHaveTextContent("management");
    expect(localStorage.getItem("workspace")).toBe("management");
  });

  test("Fix 7: OnlineOrders uses searchParams ?tab= for active tab state", () => {
    render(
      <MemoryRouter initialEntries={["/online-orders?tab=reconciliation"]}>
        <Routes>
          <Route path="/online-orders" element={<OnlineOrders />} />
        </Routes>
      </MemoryRouter>
    );

    // Verify Monthly Reconciliation tab is active
    const reconTab = screen.getByTestId("oo-tab-reconciliation");
    expect(reconTab).toHaveClass("border-slate-900 text-slate-900");
    expect(screen.getByText("Monthly Reconciliation")).toBeInTheDocument();
  });

});
