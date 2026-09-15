import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
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

describe("SkuMap Table Image Fallback Tests", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders mapping with direct image_url, internal style fallback, or placeholder icon", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/styles") {
        return Promise.resolve({
          data: [
            { id: "s1", code: "SSK_00034", name: "V sandal", image_url: "/company/classic_oxford.jpg" },
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

    // Verify m1 image rendered
    const m1Img = screen.getByAltText("SSK_00034");
    expect(m1Img).toBeInTheDocument();
    expect(m1Img.getAttribute("src")).toBe("https://ik.imagekit.io/test.jpg");

    // Verify m2 fallback to internal image rendered
    const m2Img = screen.getByAltText("SSK_TEST_OXFORD");
    expect(m2Img).toBeInTheDocument();
    expect(m2Img.getAttribute("src")).toBe("/company/classic_oxford.jpg");
  });
});
