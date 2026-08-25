import { getBackendUrl, API } from "../api";

describe("Frontend API URL Resolution", () => {
  const originalEnv = process.env.REACT_APP_BACKEND_URL;

  afterEach(() => {
    process.env.REACT_APP_BACKEND_URL = originalEnv;
  });

  test("uses explicitly configured REACT_APP_BACKEND_URL when provided", () => {
    process.env.REACT_APP_BACKEND_URL = "https://custom-erp.api.sskfootcare.com";
    expect(getBackendUrl()).toBe("https://custom-erp.api.sskfootcare.com");
  });

  test("uses window.location.origin when REACT_APP_BACKEND_URL is unset without port heuristic breaks", () => {
    delete process.env.REACT_APP_BACKEND_URL;
    expect(getBackendUrl()).toBe(window.location.origin);
  });

  test("API constant contains valid /api prefix", () => {
    expect(API).toMatch(/\/api$/);
  });
});
