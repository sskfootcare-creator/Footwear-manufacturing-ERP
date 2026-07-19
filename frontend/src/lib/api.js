import axios from "axios";

export const getBackendUrl = () => {
  // 1. Explicitly configured REACT_APP_BACKEND_URL takes priority if present
  if (process.env.REACT_APP_BACKEND_URL && process.env.REACT_APP_BACKEND_URL.trim() !== "") {
    return process.env.REACT_APP_BACKEND_URL.trim();
  }
  // 2. Browser environment dynamic resolution
  if (typeof window !== "undefined" && window.location) {
    const { hostname, port, protocol, origin } = window.location;
    // Local dev server running on port 3000 (React dev server) -> target backend on port 8000
    if (port === "3000") {
      return `${protocol}//${hostname}:8000`;
    }
    // Live server / staging / cloud preview / production deployment -> target same origin
    return origin;
  }
  return "http://localhost:8000";
};

export const API = `${getBackendUrl()}/api`;

// NOTE: withCredentials is intentionally OFF. The Emergent ingress adds
// `Access-Control-Allow-Origin: *` to every response, and browsers reject any
// credentialed (`withCredentials: true`) response that has a wildcard origin —
// axios then sees no `response` object at all and every API call silently
// fails with "Network Error". We use Bearer tokens (localStorage) exclusively.
export const http = axios.create({
  baseURL: API,
  withCredentials: false,
});

http.interceptors.request.use(
  (config) => {
    // Dynamically set baseURL on every request so host changes / live deployments work seamlessly
    config.baseURL = `${getBackendUrl()}/api`;
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (
      error.response &&
      error.response.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url.includes("auth/refresh") &&
      !originalRequest.url.includes("auth/login")
    ) {
      originalRequest._retry = true;
      try {
        const refreshTok = localStorage.getItem("refresh_token");
        // Send refresh_token in body so cookies aren't required
        const { data } = await http.post("/auth/refresh", refreshTok ? { refresh_token: refreshTok } : {});
        if (data.access_token) {
          localStorage.setItem("token", data.access_token);
        }
        return http(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem("token");
        localStorage.removeItem("refresh_token");
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export function formatApiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

/**
 * Turn an axios error into a human-friendly, informative message.
 * Falls back cleanly when the browser blocked the response body (CORS) —
 * critical for diagnosing issues in preview environments.
 */
export function friendlyAxiosError(err) {
  if (!err) return "Something went wrong. Please try again.";
  // Real HTTP response with a body
  if (err.response) {
    const detail = err.response.data && err.response.data.detail;
    const status = err.response.status;
    if (detail) return `${formatApiError(detail)} (HTTP ${status})`;
    return `Request failed with status ${status}.`;
  }
  // Request was made but no response was received (network error, CORS block, timeout)
  if (err.request) {
    if (err.code === "ECONNABORTED") return "Request timed out. Please retry.";
    return "The server didn't respond (network error or blocked by the browser). Please retry.";
  }
  // Something happened while setting up the request
  return err.message || "Unknown request error.";
}

export const inr = (n) =>
  `₹${Number(n || 0).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  })}`;

export const num = (n, dec = 0) =>
  Number(n || 0).toLocaleString("en-IN", {
    maximumFractionDigits: dec,
    minimumFractionDigits: dec,
  });
