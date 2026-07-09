import { ApiError } from "./client.js";
import { apiBaseUrl } from "./config.js";
import { clearPlatformSession, getPlatformAccessToken } from "./platformSession.js";

function readPlatformErrorMessage(response, responseBody) {
  const detail = responseBody?.detail || responseBody?.message;
  return detail ? String(detail) : `Platform isteği başarısız oldu (${response.status})`;
}

export function isInvalidPlatformSession(response, responseBody) {
  if (response.status === 401) return true;
  if (response.status !== 403) return false;
  const detail = responseBody?.detail;
  const code = typeof detail === "object" && detail !== null ? detail.code : responseBody?.code;
  if (typeof code === "string" && code.includes("platform") && code.includes("auth")) return true;
  const message = String(typeof detail === "string" ? detail : responseBody?.message || "").toLowerCase();
  return (
    message.includes("platform") &&
    (message.includes("oturum") || message.includes("session") || message.includes("auth"))
  );
}

export function redirectToPlatformLoginIfNeeded() {
  clearPlatformSession();
  if (window.location.hash !== "#/platform/login") {
    window.location.hash = "#/platform/login";
  }
}

async function request(path, { method = "GET", params, body, skipAuth = false } = {}) {
  const url = new URL(`${apiBaseUrl}${path}`);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  const headers = { Accept: "application/json" };
  const token = skipAuth ? "" : getPlatformAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const options = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url.toString(), options);
  const text = await response.text();
  const responseBody = text ? JSON.parse(text) : null;
  if (!response.ok) {
    if (isInvalidPlatformSession(response, responseBody)) {
      redirectToPlatformLoginIfNeeded();
    }
    throw new ApiError(readPlatformErrorMessage(response, responseBody), {
      status: response.status,
      body: responseBody,
    });
  }
  return responseBody;
}

export const platformApi = {
  login: (email, password) => request("/platform/auth/login", { method: "POST", skipAuth: true, body: { email, password } }),
  me: () => request("/platform/auth/me"),
  listSignupRequests: (params) => request("/platform/signup-requests", { params }),
  getSignupRequest: (id) => request(`/platform/signup-requests/${id}`),
  updateSignupRequest: (id, body) => request(`/platform/signup-requests/${id}`, { method: "PATCH", body }),
  provisionSignupRequest: (id, body) => request(`/platform/signup-requests/${id}/provision`, { method: "POST", body }),
  listMarkets: (params) => request("/platform/markets", { params }),
  getMarket: (id) => request(`/platform/markets/${id}`),
  updateMarketLifecycle: (id, body) => request(`/platform/markets/${id}/lifecycle`, { method: "PATCH", body }),
};
