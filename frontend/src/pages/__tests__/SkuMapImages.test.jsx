import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import SkuMap from "../SkuMap";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  http: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
  formatApiError: (err) => err || "Error",
}));

describe("SkuMap Table Image Fallback & Modal Preview Tests", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders larger thumbnail and opens image in modal on click", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/styles") {
        return Promise.resolve({
          data: [
            { id: "s1", code: "SSK_00034", name: "V sandal 3 buckle", image_url: "/company/classic_oxford.jpg" },
          ],
        });
      }
      if (url.startsWith("/sku-map")) {
        return Promise.resolve({
          data: [
            {
              id: "m1",
              style_code: "SSK_00034",
              style_id: "s1",
              external_sku: "EXT-100",
              source_type: "b2b_client",
              source_name: "SIYARAM",
              image_url: "https://ik.imagekit.io/test.jpg",
            },
            {
              id: "m2",
              style_code: "SSK_TEST_OXFORD",
              style_id: "s2",
              external_sku: "EXT-200",
              source_type: "b2b_client",
              source_name: "B2B Client",
              image_url: "",
              internal_image_thumbnail_url: "/company/classic_oxford.jpg",
            },
            {
              id: "m3",
              style_code: "SSK_NO_IMG",
              style_id: "s3",
              external_sku: "EXT-300",
              source_type: "b2b_client",
              source_name: "B2B Client",
              image_url: "",
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<SkuMap />);

    await waitFor(() => {
      expect(screen.getByText("SSK_00034")).toBeInTheDocument();
      expect(screen.getByText("SSK_TEST_OXFORD")).toBeInTheDocument();
      expect(screen.getByText("SSK_NO_IMG")).toBeInTheDocument();
    });

    // Verify m1 image rendered in bigger thumbnail button
    const m1Img = screen.getByAltText("SSK_00034");
    expect(m1Img).toBeInTheDocument();
    expect(m1Img.getAttribute("src")).toBe("https://ik.imagekit.io/test.jpg");
    const btn = m1Img.closest("button");
    expect(btn).toHaveClass("w-16");
    expect(btn).toHaveClass("h-16");

    // Click thumbnail to open image modal
    fireEvent.click(btn);

    // Verify modal is open with image and metadata
    const modalDialog = screen.getByRole("dialog");
    expect(modalDialog).toBeInTheDocument();
    expect(modalDialog).toHaveTextContent("SSK_00034");
    expect(modalDialog).toHaveTextContent("EXT-100");
    expect(modalDialog).toHaveTextContent("SIYARAM");

    // Close modal
    const closeBtn = document.getElementById("btn-close-image-modal");
    fireEvent.click(closeBtn);

    // Verify modal is closed
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
