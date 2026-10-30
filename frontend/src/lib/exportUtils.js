import { http } from "./api";
import { toast } from "sonner";

/**
 * Downloads a binary or text Blob directly to the user's browser.
 */
export function downloadBlob(blob, filename) {
  if (typeof window === "undefined") return;
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    if (link.parentNode) {
      link.parentNode.removeChild(link);
    }
    window.URL.revokeObjectURL(url);
  }, 1000);
}

/**
 * Generates an RFC 4180 CSV with UTF-8 BOM so Excel opens it with proper encoding.
 */
export function downloadCsv(filename, headers, rows) {
  const BOM = "\uFEFF";
  const csvContent =
    BOM +
    [
      headers.map((h) => `"${String(h ?? "").replace(/"/g, '""')}"`).join(","),
      ...rows.map((r) => r.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")),
    ].join("\r\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  downloadBlob(blob, filename);
}

/**
 * Triggers a backend export endpoint for Excel (.xlsx) or CSV (.csv) with error handling.
 */
export async function triggerApiExport(endpoint, params = {}, defaultFilename = "export.xlsx") {
  const isXlsx = (params.format || "xlsx").toLowerCase() === "xlsx";
  const toastId = toast?.loading
    ? toast.loading(`Preparing ${isXlsx ? "Excel" : "CSV"} export...`)
    : null;

  try {
    const res = await http.get(endpoint, {
      params,
      responseType: "blob",
    });

    // Check if server returned an error JSON inside the blob
    if (res.data?.type === "application/json") {
      const text = await res.data.text();
      let errorMsg = "Export request failed";
      try {
        const parsed = JSON.parse(text);
        errorMsg = parsed.detail || errorMsg;
      } catch {}
      throw new Error(errorMsg);
    }

    let filename = defaultFilename;
    const disposition = res.headers?.["content-disposition"] || res.headers?.["Content-Disposition"];
    if (disposition && disposition.includes("filename=")) {
      const match = disposition.match(/filename=["']?([^"';]+)["']?/i);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const contentType =
      res.headers?.["content-type"] ||
      (isXlsx
        ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        : "text/csv;charset=utf-8;");

    const blob = new Blob([res.data], { type: contentType });
    downloadBlob(blob, filename);

    if (toastId && toast?.dismiss) {
      toast.dismiss(toastId);
    }
    toast?.success?.(`Downloaded ${filename}`);
    return true;
  } catch (err) {
    if (toastId && toast?.dismiss) {
      toast.dismiss(toastId);
    }
    const msg = err?.response?.data?.detail || err?.message || "Export failed";
    toast?.error?.(msg);
    console.error("Export error:", err);
    throw err;
  }
}

/**
 * Downloads Master Footwear Product Specification & Costing Sheet (.xlsx) with embedded style pictures.
 * Matches C:\Users\Dell\Downloads\catalogue.xlsx formatting and columns.
 */
export async function downloadCatalogueXlsx({
  style_ids,
  style_codes,
  brand = "ZECODE",
  category = "Women's Footwear (Flats, Wedges, Platform Slides & Kitten Heels)",
  defaultFilename = "SSK_Footwear_Catalogue.xlsx",
} = {}) {
  const toastId = toast?.loading
    ? toast.loading("Generating Excel catalogue with style pictures...")
    : null;

  try {
    const res = await http.post(
      "/styles/catalogue/download",
      {
        style_ids: style_ids && style_ids.length ? style_ids : undefined,
        style_codes: style_codes && style_codes.length ? style_codes : undefined,
        brand,
        category,
        include_images: true,
      },
      { responseType: "blob" }
    );

    let filename = defaultFilename;
    const disposition = res.headers?.["content-disposition"] || res.headers?.["Content-Disposition"];
    if (disposition && disposition.includes("filename=")) {
      const match = disposition.match(/filename=["']?([^"';]+)["']?/i);
      if (match && match[1]) {
        filename = match[1].trim();
      }
    }

    const blob = new Blob([res.data], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    downloadBlob(blob, filename);

    if (toastId && toast?.dismiss) {
      toast.dismiss(toastId);
    }
    toast?.success?.(`Downloaded ${filename} with style pictures!`);
    return true;
  } catch (err) {
    if (toastId && toast?.dismiss) {
      toast.dismiss(toastId);
    }
    const msg = err?.response?.data?.detail || err?.message || "Failed to download catalogue";
    toast?.error?.(msg);
    console.error("Catalogue download error:", err);
    throw err;
  }
}
