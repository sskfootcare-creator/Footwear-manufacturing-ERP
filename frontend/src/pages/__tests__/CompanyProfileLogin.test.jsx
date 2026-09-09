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

    // Check brand & pitch deck title
    expect(screen.getAllByText(/SSK FOOTCARE/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Engineering India's Footwear Supply Chain/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Startup India/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Section 80-IAC/i).length).toBeGreaterThan(0);
  });

  test("renders core sections from the 11-slide pitch deck", () => {
    renderComponent();

    // Slide 2: What We Do
    expect(screen.getByText(/What We Do/i)).toBeInTheDocument();
    expect(screen.getByText(/Raw Material to Finished Product/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Direct Online Retail/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/B2B Contract Manufacturing/i).length).toBeGreaterThan(0);

    // Slide 3: Tech USP
    expect(screen.getByText(/A Manufacturer Built Like a Tech Company/i)).toBeInTheDocument();
    expect(screen.getByText(/Real-Time Cost Engineering/i)).toBeInTheDocument();
    expect(screen.getByText(/Stage-Level Production Tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/Data-Driven Trend Forecasting/i)).toBeInTheDocument();
    expect(screen.getByText(/Dual-Channel Reconciliation/i)).toBeInTheDocument();

    // Slide 4: Products
    expect(screen.getByText(/From Our Manufacturing Line/i)).toBeInTheDocument();

    // Slide 7: Revenue Model
    expect(screen.getByText(/How We Earn/i)).toBeInTheDocument();
    expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("40%").length).toBeGreaterThan(0);

    // Slide 9: Traction & Clients
    expect(screen.getByText(/Who We Work With/i)).toBeInTheDocument();
    expect(screen.getByText(/Myntra Designs Pvt Ltd/i)).toBeInTheDocument();
    expect(screen.getByText(/Nexgen Fashion Pvt Ltd/i)).toBeInTheDocument();
    expect(screen.getByText(/Siyaram Silk Mills/i)).toBeInTheDocument();
    expect(screen.getByText(/Metro Brands Ltd/i)).toBeInTheDocument();
    expect(screen.getByText(/Flipkart Pvt Ltd/i)).toBeInTheDocument();

    // Slides 5 & 6: Leadership & Ownership
    expect(screen.getAllByText(/Umesh Suwasiya/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Naresh Kurdiya/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/B.E., Computer Science/i)).toBeInTheDocument();
    expect(screen.getByText(/B.Com, IPCC/i)).toBeInTheDocument();
  });

  test("preserves all login form testids and authentication flow", async () => {
    renderComponent();

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

    // Forgot password modal
    const forgotBtn = screen.getByTestId("forgot-password-link");
    fireEvent.click(forgotBtn);

    expect(screen.getByTestId("forgot-password-modal")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-email-input")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-submit")).toBeInTheDocument();

    // Karigar login links
    expect(screen.getByTestId("karigar-login-link")).toBeInTheDocument();
    expect(screen.getByTestId("karigar-portal-btn")).toBeInTheDocument();
  });
});
