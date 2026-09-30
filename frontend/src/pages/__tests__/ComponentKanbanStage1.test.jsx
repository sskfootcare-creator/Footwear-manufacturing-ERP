import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import Materials, { getStagePresets } from "../Materials";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  http: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
  inr: (v) => `₹${v}`,
}));

jest.mock("../../lib/sync", () => ({
  broadcastSync: jest.fn(),
  useCrossTabSync: jest.fn(),
}));

describe("Component Kanban Stage 1: Materials and Styles Master", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("getStagePresets returns appropriate stage suggestions based on category", () => {
    expect(getStagePresets("sole")).toEqual(["cutting", "finishing", "splitting", "beveling"]);
    expect(getStagePresets("heel")).toEqual(["cover_cutting", "folding", "pasting", "finishing"]);
    expect(getStagePresets("upper")).toEqual(["cutting", "folding", "attachment", "stitching"]);
    expect(getStagePresets("other")).toEqual(["cutting", "finishing", "cover_cutting", "folding"]);
  });

  test("Materials page renders stage_requirements badges for configured materials and ready-to-use for empty sole", async () => {
    const mockMaterials = [
      {
        id: "mat-1",
        code: "PVC-001",
        name: "PVC Sole Classic",
        category: "sole",
        rate: 80,
        unit: "pcs",
        stage_requirements: [],
      },
      {
        id: "mat-2",
        code: "RUBBER-001",
        name: "Rubber Sole Sheet",
        category: "sole",
        rate: 220,
        unit: "sqft",
        stage_requirements: ["cutting", "finishing"],
      },
    ];

    http.get.mockImplementation((url) => {
      if (url === "/materials") return Promise.resolve({ data: mockMaterials });
      if (url.startsWith("/vendors")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    render(<Materials />);

    await waitFor(() => {
      expect(screen.getByTestId("material-ready-PVC-001")).toBeInTheDocument();
      expect(screen.getByTestId("material-stages-RUBBER-001")).toHaveTextContent("Stages: cutting, finishing");
    });
  });

  test("Adding a stage requirement in Material drawer works via preset and manual input", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/materials") return Promise.resolve({ data: [] });
      if (url.startsWith("/vendors")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    render(<Materials />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByTestId("add-material-btn")).toBeInTheDocument();
    });

    // Open add material drawer
    fireEvent.click(screen.getByTestId("add-material-btn"));

    // Check default state of stage requirements section
    expect(screen.getByTestId("no-stage-reqs-indicator")).toBeInTheDocument();

    // Click quick preset for "cutting"
    const cuttingPreset = screen.getByTestId("preset-stage-cutting");
    fireEvent.click(cuttingPreset);

    // Verify cutting chip is added
    expect(screen.getByTestId("stage-req-chip-cutting")).toBeInTheDocument();

    // Type a custom stage and add it
    const stageInput = screen.getByTestId("input-stage-req");
    fireEvent.change(stageInput, { target: { value: "beveling" } });
    fireEvent.click(screen.getByTestId("add-stage-req-btn"));

    expect(screen.getByTestId("stage-req-chip-beveling")).toBeInTheDocument();

    // Remove the cutting chip
    fireEvent.click(screen.getByTestId("remove-stage-req-cutting"));
    expect(screen.queryByTestId("stage-req-chip-cutting")).not.toBeInTheDocument();
    expect(screen.getByTestId("stage-req-chip-beveling")).toBeInTheDocument();
  });
});
