import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { useWorkspace } from "../../components/AppShell";
import OnlineOrders from "../OnlineOrders";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn().mockResolvedValue({ data: [] }),
      post: jest.fn().mockResolvedValue({ data: {} }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
      patch: jest.fn().mockResolvedValue({ data: {} }),
    },
  };
});

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

  test("Fix 7: OnlineOrders renders cleanly without tab errors", async () => {
    render(
      <MemoryRouter initialEntries={["/online-orders"]}>
        <Routes>
          <Route path="/online-orders" element={<OnlineOrders />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByTestId("online-orders-header")).toBeInTheDocument();
    expect(screen.getByText("Online Orders")).toBeInTheDocument();
  });

});
