import { useState, useEffect } from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useOutletContext } from "react-router-dom";
import AppShell from "../AppShell";

jest.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { name: "Admin User", role: "admin", email: "admin@sskfootcare.com" },
    logout: jest.fn(),
  }),
}));

let mountCount = 0;
function TestPage() {
  const { workspace } = useOutletContext() || {};
  const [renders, setRenders] = useState(0);

  useEffect(() => {
    mountCount += 1;
    setRenders((r) => r + 1);
  }, []);

  return (
    <div>
      <h1 data-testid="page-title">Test Child Page</h1>
      <div data-testid="workspace-indicator">Active: {workspace || "none"}</div>
      <div data-testid="mount-count">Mounts: {mountCount}</div>
    </div>
  );
}

describe("Workspace Switching Lifecycle", () => {
  beforeEach(() => {
    mountCount = 0;
    localStorage.setItem("workspace", "b2b");
  });

  test("switching workspace remounts the active page with fresh workspace context and re-fetches cleanly", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<TestPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    // Initial render under B2B workspace
    expect(screen.getByTestId("workspace-indicator")).toHaveTextContent("Active: b2b");
    expect(screen.getByTestId("mount-count")).toHaveTextContent("Mounts: 1");

    // Open User menu and switch to Online Commerce workspace
    const userMenuBtn = screen.getByTestId("user-menu-btn");
    fireEvent.click(userMenuBtn);

    const onlineSwitchBtn = screen.getByTestId("ws-switch-online");
    expect(onlineSwitchBtn).toBeInTheDocument();
    fireEvent.click(onlineSwitchBtn);

    // Verify workspace state transitioned and child component remounted afresh
    await waitFor(() => {
      expect(screen.getByTestId("workspace-indicator")).toHaveTextContent("Active: online");
    });
    expect(screen.getByTestId("mount-count")).toHaveTextContent("Mounts: 2");
    expect(localStorage.getItem("workspace")).toBe("online");
  });
});

