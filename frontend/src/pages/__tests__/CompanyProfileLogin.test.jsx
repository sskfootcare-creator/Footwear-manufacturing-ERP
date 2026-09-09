import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import Login from "../Login";

// Mock useAuth
const mockLogin = jest.fn();
jest.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: null,
    login: mockLogin,
    error: null,
    setError: jest.fn(),
  }),
}));

// Mock api
jest.mock("@/lib/api", () => ({
  http: {
    post: jest.fn().mockResolvedValue({ data: { message: "Reset link sent" } }),
  },
}));

describe("Company Profile & Login Page", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const renderComponent = () =>
    render(
      <BrowserRouter>
        <Login />
      </BrowserRouter>
    );

  test("renders executive company profile header and hero content", () => {
    renderComponent();

    // Check brand & hero title
    expect(screen.getAllByText(/SSK FOOTCARE/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Engineering India's Footwear Supply Chain/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Startup India/i).length).toBeGreaterThan(0);
    // Section 80-IAC must not be present
    expect(screen.queryByText(/Section 80-IAC/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Pitch Deck Portfolio/i)).not.toBeInTheDocument();
  });

  test("renders core sections from the company profile", () => {
    renderComponent();

    // Slide 2: What We Do
    expect(screen.getByText(/What We Do/i)).toBeInTheDocument();
    expect(screen.getByText(/Raw Material to Finished Product/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Direct Online Retail/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/B2B Contract Manufacturing/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Direct-to-Consumer \(D2C\) Focus/i)).toBeInTheDocument();
    expect(screen.getByText(/Enterprise B2B Manufacturing/i)).toBeInTheDocument();

    // Slide 3: Tech USP
    expect(screen.getByText(/A Manufacturer Built Like a Tech Company/i)).toBeInTheDocument();
    expect(screen.getByText(/Real-Time Cost Engineering/i)).toBeInTheDocument();
    expect(screen.getByText(/Stage-Level Production Tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/Data-Driven Trend Forecasting/i)).toBeInTheDocument();
    expect(screen.getByText(/Dual-Channel Reconciliation/i)).toBeInTheDocument();

    // Slide 4: Products
    expect(screen.getByText(/From Our Manufacturing Line/i)).toBeInTheDocument();

    // Slide 7: Revenue Model - Replaced "How We Earn", no percentages disclosed
    expect(screen.getByText(/Revenue Model/i)).toBeInTheDocument();
    expect(screen.queryByText(/How We Earn/i)).not.toBeInTheDocument();
    expect(screen.queryByText("60%")).not.toBeInTheDocument();
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
    expect(screen.queryByText(/60 \/ 40/i)).not.toBeInTheDocument();

    // Slide 9: Traction & Clients
    expect(screen.getByText(/Who We Work With/i)).toBeInTheDocument();
    expect(screen.getByText(/Myntra Designs Pvt Ltd/i)).toBeInTheDocument();
    expect(screen.getByText(/Nexgen Fashion Pvt Ltd/i)).toBeInTheDocument();
    expect(screen.getByText(/Siyaram Silk Mills/i)).toBeInTheDocument();
    expect(screen.getByText(/Metro Brands Ltd/i)).toBeInTheDocument();
    expect(screen.getByText(/Flipkart Pvt Ltd/i)).toBeInTheDocument();

    // Slides 5 & 6: Leadership & Ownership - Equity split must not be disclosed
    expect(screen.getAllByText(/Umesh Suwasiya/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Naresh Kurdiya/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/B.E., Computer Science/i)).toBeInTheDocument();
    expect(screen.getByText(/B.Com, IPCC/i)).toBeInTheDocument();
    expect(screen.queryByText(/Equity: 50%/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/50%/i)).not.toBeInTheDocument();

    // Authorized Personnel section must be removed
    expect(screen.queryByText(/Authorized Personnel & Client Sign-In/i)).not.toBeInTheDocument();
  });

  test("preserves all login form testids and authentication flow via modal", async () => {
    renderComponent();

    // Open portal login modal
    const loginBtn = screen.getByRole("button", { name: /^login$/i });
    fireEvent.click(loginBtn);

    const emailInput = screen.getByTestId("login-email");
    const passwordInput = screen.getByTestId("login-password");
    const submitBtn = screen.getByTestId("login-submit");

    expect(emailInput).toBeInTheDocument();
    expect(passwordInput).toBeInTheDocument();
    expect(submitBtn).toBeInTheDocument();

    fireEvent.change(emailInput, { target: { value: "test@sskfootcare.com" } });
    fireEvent.change(passwordInput, { target: { value: "secret123" } });
    await React.act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(mockLogin).toHaveBeenCalledWith("test@sskfootcare.com", "secret123");
  });

  test("opens forgot password modal and karigar portal triggers correctly", () => {
    renderComponent();

    // Open portal modal first to access forgot password link
    const loginBtn = screen.getByRole("button", { name: /^login$/i });
    fireEvent.click(loginBtn);

    // Forgot password modal
    const forgotBtn = screen.getByTestId("forgot-password-link");
    fireEvent.click(forgotBtn);

    expect(screen.getByTestId("forgot-password-modal")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-email-input")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-submit")).toBeInTheDocument();

    // Karigar portal button in sticky header
    expect(screen.getByTestId("karigar-portal-btn")).toBeInTheDocument();
  });

  test("toggles mobile slide-out navigation menu on hamburger click", () => {
    renderComponent();

    const hamburgerBtn = screen.getByLabelText(/Toggle navigation menu/i);
    expect(hamburgerBtn).toBeInTheDocument();

    // Open mobile menu
    fireEvent.click(hamburgerBtn);
    expect(screen.getByText(/Company Sections/i)).toBeInTheDocument();
    expect(screen.getByText(/Capabilities & Operations/i)).toBeInTheDocument();
    expect(screen.getByText(/Tech \/ Proprietary ERP/i)).toBeInTheDocument();

    // Close mobile menu
    fireEvent.click(hamburgerBtn);
    expect(screen.queryByText(/Company Sections/i)).not.toBeInTheDocument();
  });

  test("opens and closes product specification sheet modal on mobile touch", () => {
    renderComponent();

    const viewSpecsBtns = screen.getAllByText(/View Specifications/i);
    expect(viewSpecsBtns.length).toBeGreaterThan(0);

    // Click to open spec modal
    fireEvent.click(viewSpecsBtns[0]);
    expect(screen.getByText(/SSK Product Specification Sheet/i)).toBeInTheDocument();
    expect(screen.getByText(/Materials Used/i)).toBeInTheDocument();

    // Close modal
    const closeBtn = screen.getByRole("button", { name: /^close$/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByText(/SSK Product Specification Sheet/i)).not.toBeInTheDocument();
  });
});
