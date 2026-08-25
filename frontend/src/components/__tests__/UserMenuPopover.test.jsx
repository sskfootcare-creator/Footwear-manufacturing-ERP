import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import AppShell from "../AppShell";

jest.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { name: "Admin User", role: "admin", email: "admin@sskfootcare.com" },
    logout: jest.fn(),
  }),
}));

describe("AppShell UserMenuPopover", () => {
  test("clicking Karigar App link invokes navigate to /karigar-login without throwing ReferenceError", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>Dashboard Page</div>} />
          </Route>
          <Route path="/karigar-login" element={<div>Karigar Login Page</div>} />
        </Routes>
      </MemoryRouter>
    );

    // Open User Menu Popover
    const userMenuBtn = screen.getByTestId("user-menu-btn");
    expect(userMenuBtn).toBeInTheDocument();
    fireEvent.click(userMenuBtn);

    // Click the Karigar App Link
    const karigarLink = screen.getByTestId("open-karigar-app-btn");
    expect(karigarLink).toBeInTheDocument();

    expect(() => {
      fireEvent.click(karigarLink);
    }).not.toThrow();

    // Verify successful navigation to Karigar Login Page
    expect(screen.getByText("Karigar Login Page")).toBeInTheDocument();
  });
});

