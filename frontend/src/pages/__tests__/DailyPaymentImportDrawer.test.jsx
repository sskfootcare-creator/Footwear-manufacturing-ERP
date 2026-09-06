import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import OnlineOrders, { DailyPaymentImportDrawer } from "../OnlineOrders";
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
  };
});

describe("DailyPaymentImportDrawer & Daily Habit Trigger", () => {
  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url.includes("/online-reconciliation/daily-payments/progress")) {
        return Promise.resolve({
          data: {
            month: "2026-09",
            total_business_days_in_month: 22,
            expected_business_days_mtd: 5,
            uploaded_business_days_count: 2,
            uploaded_business_days: ["2026-09-01", "2026-09-02"],
            missing_business_days_mtd: ["2026-09-03", "2026-09-04", "2026-09-05"],
            progress_pct: 40.0,
            total_rows_this_month: 64,
            distinct_payment_dates: ["2026-09-01", "2026-09-02"],
          },
        });
      }
      if (url.includes("/order-import-format-configs")) return Promise.resolve({ data: [] });
      if (url.includes("/online-orders/jobs")) return Promise.resolve({ data: [] });
      if (url.includes("/online-orders/stats")) return Promise.resolve({ data: {} });
      if (url.includes("/online-reconciliation/summary")) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: [] });
    });
  });

  test("trigger button is prominently placed right alongside 'Import orders' in Orders tab", async () => {
    render(
      <MemoryRouter>
        <OnlineOrders />
      </MemoryRouter>
    );

    // Confirm both daily buttons exist together
    await waitFor(() => {
      expect(screen.getByTestId("btn-daily-payment-upload")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /import orders/i })).toBeInTheDocument();
    });

    const dailyBtn = screen.getByTestId("btn-daily-payment-upload");
    expect(dailyBtn).toHaveTextContent("Upload Daily Payment");
    // Wait for cadence badge to load asynchronously
    await waitFor(() => {
      expect(dailyBtn).toHaveTextContent("2/5d");
    });

    // Click daily button opens drawer directly without navigating through monthly reconciliation
    fireEvent.click(dailyBtn);

    await waitFor(() => {
      expect(screen.getByText(/2 of 5 business days uploaded MTD/i)).toBeInTheDocument();
    });
  });

  test("drawer single-purpose upload shows Stage 1 summary and Done action", async () => {
    const handleDone = jest.fn();
    const handleClose = jest.fn();

    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        filename: "myntra_daily_prepaid.csv",
        total_in_file: 39,
        inserted: 39,
        skipped_duplicates: 0,
        message: "Successfully imported 39 daily payment rows (0 duplicates skipped)",
      },
    });

    render(
      <MemoryRouter>
        <DailyPaymentImportDrawer onClose={handleClose} onDone={handleDone} />
      </MemoryRouter>
    );

    // Verify file input and upload button
    const fileInput = document.getElementById("daily-payment-file-input");
    expect(fileInput).toBeInTheDocument();

    const dummyFile = new File(["dummy content"], "myntra_daily_prepaid.csv", { type: "text/csv" });
    fireEvent.change(fileInput, { target: { files: [dummyFile] } });

    const uploadBtn = screen.getByRole("button", { name: /Upload & Process/i });
    expect(uploadBtn).not.toBeDisabled();

    fireEvent.click(uploadBtn);

    // Wait for Stage 1 summary card
    await waitFor(() => {
      expect(screen.getByTestId("daily-payment-result-card")).toBeInTheDocument();
    });

    expect(screen.getByText("Daily Payment File Processed")).toBeInTheDocument();
    expect(screen.getByText("myntra_daily_prepaid.csv")).toBeInTheDocument();
    expect(screen.getByTestId("stat-total-in-file")).toHaveTextContent("39");
    expect(screen.getByTestId("stat-new-inserted")).toHaveTextContent("39");
    expect(screen.getByTestId("stat-duplicates-skipped")).toHaveTextContent("0");

    // Click Done calls onClose
    const doneBtn = screen.getByRole("button", { name: /Done/i });
    fireEvent.click(doneBtn);
    expect(handleClose).toHaveBeenCalled();
  });

  test("duplicate protection summary clearly warns when rows are skipped", async () => {
    const handleDone = jest.fn();
    const handleClose = jest.fn();

    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        filename: "myntra_daily_duplicate.csv",
        total_in_file: 39,
        inserted: 0,
        skipped_duplicates: 39,
        message: "0 new rows inserted (39 duplicates already present skipped)",
      },
    });

    render(
      <MemoryRouter>
        <DailyPaymentImportDrawer onClose={handleClose} onDone={handleDone} />
      </MemoryRouter>
    );

    const fileInput = document.getElementById("daily-payment-file-input");
    const dummyFile = new File(["dummy content"], "myntra_daily_duplicate.csv", { type: "text/csv" });
    fireEvent.change(fileInput, { target: { files: [dummyFile] } });

    const uploadBtn = screen.getByRole("button", { name: /Upload & Process/i });
    fireEvent.click(uploadBtn);

    await waitFor(() => {
      expect(screen.getByTestId("daily-payment-result-card")).toBeInTheDocument();
    });

    expect(screen.getByTestId("stat-new-inserted")).toHaveTextContent("0");
    expect(screen.getByTestId("stat-duplicates-skipped")).toHaveTextContent("39");
    expect(screen.getByText(/skipped to avoid duplicate payouts/i)).toBeInTheDocument();
  });
});
