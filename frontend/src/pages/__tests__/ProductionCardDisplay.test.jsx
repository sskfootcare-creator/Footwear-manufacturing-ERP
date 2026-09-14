import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Production from "../Production";
import { http } from "../../lib/api";

jest.mock("../../lib/auth", () => ({
  useAuth: () => ({
    user: { email: "admin@sskfootwear.com", role: "admin", name: "Admin" },
  }),
}));

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

describe("Production Card Display - Mapped Style Code and Creation Date", () => {
  const mockJobMapped = {
    id: "job_mapped_1",
    po_id: "po_mapped_123",
    po_number: "2220011455",
    client_name: "SIYARAM SILK MILLS LTD.",
    style_id: "style_ssk_34",
    style_code: "SSK_00034",
    po_style_code: "5ZE1026WFFLT-0-0602",
    created_at: "2026-09-05T10:38:44.624735+00:00",
    color: "CREAM",
    size: "6",
    quantity: 130,
    completed_qty: 0,
    stage: "procurement",
    archived: false,
    delivery_date: "2026-09-25",
  };

  const mockJobUnmapped = {
    id: "job_unmapped_1",
    po_id: "po_unmapped_123",
    po_number: "2220010098",
    client_name: "SIYARAM SILK MILLS LTD.",
    style_id: "style_ssk_10",
    style_code: "SSK_00010",
    po_style_code: null,
    created_at: "2026-09-02T14:20:00.000000+00:00",
    color: "TAUPE",
    size: "7",
    quantity: 120,
    completed_qty: 0,
    stage: "cutting",
    archived: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) {
        return Promise.resolve({ data: [mockJobMapped, mockJobUnmapped] });
      }
      if (url.startsWith("/workers")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) {
        return Promise.resolve({
          data: [
            { code: "SSK_00034", name: "Siyaram Loafer" },
            { code: "SSK_00010", name: "Siyaram Sandal" },
          ],
        });
      }
      if (url.startsWith("/production/archive")) return Promise.resolve({ data: [] });
      if (url.startsWith("/packing-lists")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });
  });

  test("renders SSK_stylecode/mapped_stylecode format when po_style_code is mapped and plain style_code when unmapped", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Verify card with mapped style code displays SSK_stylecode/mapped_stylecode
    const mappedKey = `2220011455::SSK_00034::CREAM`;
    const mappedStyleElement = await screen.findByTestId(`style-code-${mappedKey}`);
    expect(mappedStyleElement).toHaveTextContent("SSK_00034/5ZE1026WFFLT-0-0602");

    // Verify card without mapped style code displays plain style code
    const unmappedKey = `2220010098::SSK_00010::TAUPE`;
    const unmappedStyleElement = await screen.findByTestId(`style-code-${unmappedKey}`);
    expect(unmappedStyleElement).toHaveTextContent("SSK_00010");
  });

  test("renders card creation date on production cards", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    const mappedKey = `2220011455::SSK_00034::CREAM`;
    const createdDateElement = await screen.findByTestId(`created-date-${mappedKey}`);
    expect(createdDateElement).toBeInTheDocument();
    // 2026-09-05 formatted in en-IN is "05 Sep 2026"
    expect(createdDateElement).toHaveTextContent("Created: 05 Sep 2026");

    const unmappedKey = `2220010098::SSK_00010::TAUPE`;
    const unmappedCreatedDateElement = await screen.findByTestId(`created-date-${unmappedKey}`);
    expect(unmappedCreatedDateElement).toBeInTheDocument();
    expect(unmappedCreatedDateElement).toHaveTextContent("Created: 02 Sep 2026");
  });
});
