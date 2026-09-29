import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import KarigarLogin from "../KarigarLogin";

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      post: jest.fn().mockResolvedValue({
        data: {
          access_token: "mock-worker-jwt",
          worker_id: "w-1",
          name: "Ramesh Karigar",
          skill: "Stitching",
        },
      }),
    },
  };
});

describe("KarigarLogin Touch and Keypad Responsiveness", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("renders Karigar keypad and registers pointerdown touch events instantly", () => {
    render(
      <MemoryRouter>
        <KarigarLogin />
      </MemoryRouter>
    );

    expect(screen.getByText("SSK Karigar App")).toBeInTheDocument();
    expect(screen.getByText("Enter your phone number")).toBeInTheDocument();

    const key9 = screen.getByRole("button", { name: "Digit 9" });
    const key8 = screen.getByRole("button", { name: "Digit 8" });

    // Simulate instant pointerdown touch
    fireEvent.pointerDown(key9);
    fireEvent.pointerDown(key8);

    // Should display digits formatted in phone-display
    const display = screen.getByTestId("phone-display");
    expect(display).toHaveTextContent("98");
  });

  test("handles consecutive rapid taps without dropping digits (pointerdown debounce protects duplicates)", () => {
    render(
      <MemoryRouter>
        <KarigarLogin />
      </MemoryRouter>
    );

    const key5 = screen.getByRole("button", { name: "Digit 5" });
    const display = screen.getByTestId("phone-display");

    // Touch down followed by click (normal browser touch cycle)
    fireEvent.pointerDown(key5);
    fireEvent.click(key5);

    // Only one digit 5 registered because click was synthesized within 400ms
    expect(display).toHaveTextContent("5");

    // Rapid second tap on 5 with pointerDown (e.g. typing double 5)
    fireEvent.pointerDown(key5);
    expect(display).toHaveTextContent("55");

    // Now backspace works
    const delKey = screen.getByRole("button", { name: "Delete" });
    fireEvent.pointerDown(delKey);
    expect(display).toHaveTextContent("5");
  });

  test("supports physical keyboard input for fast numpad entry", () => {
    render(
      <MemoryRouter>
        <KarigarLogin />
      </MemoryRouter>
    );

    const display = screen.getByTestId("phone-display");

    fireEvent.keyDown(window, { key: "1" });
    fireEvent.keyDown(window, { key: "2" });
    fireEvent.keyDown(window, { key: "3" });

    expect(display).toHaveTextContent("123");

    fireEvent.keyDown(window, { key: "Backspace" });
    expect(display).toHaveTextContent("12");
  });

  test("full flow: entering 10 digits advances to PIN step", async () => {
    render(
      <MemoryRouter>
        <KarigarLogin />
      </MemoryRouter>
    );

    for (let i = 0; i < 10; i++) {
      fireEvent.keyDown(window, { key: "9" });
    }

    const continueBtn = screen.getByRole("button", { name: "Continue →" });
    fireEvent.click(continueBtn);

    await waitFor(() => {
      expect(screen.getByText("Enter your PIN")).toBeInTheDocument();
      expect(screen.getByText("PIN")).toBeInTheDocument();
    });
  });
});
