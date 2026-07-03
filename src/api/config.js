const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api";

function normalizeBaseUrl(value) {
  return (value || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

function readBoolean(value) {
  return String(value || "").toLowerCase() === "true";
}

export const apiBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);
export const isRealApiEnabled = readBoolean(import.meta.env.VITE_USE_REAL_API);
export const demoMarketId = import.meta.env.VITE_DEMO_MARKET_ID || "";

