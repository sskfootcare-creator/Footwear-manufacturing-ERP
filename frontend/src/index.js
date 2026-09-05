import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";

if (typeof window !== "undefined") {
  window.addEventListener(
    "error",
    (e) => {
      const isExt =
        (e.filename && e.filename.includes("chrome-extension://")) ||
        (e.message && (e.message.includes("chrome-extension://") || e.message.includes("M_ID"))) ||
        (e.error && e.error.stack && (e.error.stack.includes("chrome-extension://") || e.error.stack.includes("M_ID")));
      if (isExt) {
        e.stopImmediatePropagation();
        e.preventDefault();
        return true;
      }
    },
    true
  );

  window.addEventListener(
    "unhandledrejection",
    (e) => {
      const reason = e.reason;
      const isExt =
        (reason && reason.stack && (reason.stack.includes("chrome-extension://") || reason.stack.includes("M_ID"))) ||
        (reason && String(reason).includes("chrome-extension://")) ||
        (reason && String(reason).includes("M_ID"));
      if (isExt) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    },
    true
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
