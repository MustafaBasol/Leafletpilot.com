import { getAccessToken, getSelectedMarketId } from "./authSession.js";
import { apiBaseUrl } from "./config.js";

export class ApiError extends Error {
  constructor(message, { status, body } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function buildUrl(path, params) {
  const url = new URL(`${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`);

  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });

  return url.toString();
}

async function readResponseBody(response) {
  if (response.status === 204) return null;

  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function formatValidationDetail(detail) {
  if (!Array.isArray(detail)) return detail;

  return detail
    .map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const path = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
      return [path, item.msg || item.message || JSON.stringify(item)].filter(Boolean).join(": ");
    })
    .join("; ");
}

function getErrorMessage(response, body) {
  const detail = typeof body === "object" && body !== null ? body.detail || body.message : body;
  if (typeof detail === "object" && detail?.code === "invitation_email_mismatch") {
    return "Bu davet başka bir e-posta adresi için oluşturulmuş. Davet edilen hesapla giriş yapın veya mevcut oturumdan çıkın.";
  }
  const formattedDetail = formatValidationDetail(detail);
  if (response.status === 403 && formattedDetail) return formattedDetail;
  if (response.status === 403) return "Bu işlem için yetkiniz bulunmuyor.";
  const suffix = formattedDetail
    ? `: ${typeof formattedDetail === "string" ? formattedDetail : JSON.stringify(formattedDetail)}`
    : "";
  return `API isteği başarısız oldu (${response.status} ${response.statusText})${suffix}`;
}

export async function apiRequest(
  path,
  { method = "GET", params, body, marketId, headers, skipAuth = false, skipMarket = false } = {},
) {
  const requestHeaders = {
    Accept: "application/json",
    ...headers,
  };

  const token = skipAuth ? "" : getAccessToken();
  if (token) {
    requestHeaders.Authorization = `Bearer ${token}`;
  }

  const selectedMarketId = marketId || (!skipMarket ? getSelectedMarketId() : "");
  if (selectedMarketId) {
    requestHeaders["X-Market-Id"] = selectedMarketId;
  }

  const options = {
    method,
    headers: requestHeaders,
  };

  if (body !== undefined && body !== null) {
    const isRawBody = body instanceof Blob || body instanceof ArrayBuffer || body instanceof FormData;
    if (!isRawBody) {
      requestHeaders["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    } else {
      options.body = body;
      if (body instanceof Blob && body.type && !requestHeaders["Content-Type"]) {
        requestHeaders["Content-Type"] = body.type;
      }
    }
  }

  let response;
  try {
    response = await fetch(buildUrl(path, params), options);
  } catch (error) {
    throw new ApiError(`API bağlantısı kurulamadı: ${error.message}`, { status: 0 });
  }

  const responseBody = await readResponseBody(response);
  if (!response.ok) {
    throw new ApiError(getErrorMessage(response, responseBody), {
      status: response.status,
      body: responseBody,
    });
  }

  return responseBody;
}

export function resolveImageUrl(imageUrl) {
  if (!imageUrl) return "";

  try {
    return new URL(imageUrl, `${apiBaseUrl}/`).toString();
  } catch {
    return "";
  }
}

function isApiImageUrl(imageUrl, resolvedUrl) {
  if (imageUrl.startsWith("/api/")) return true;

  try {
    const apiOrigin = new URL(apiBaseUrl).origin;
    const parsed = new URL(resolvedUrl);
    return parsed.origin === apiOrigin && parsed.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

export async function fetchImageSource(imageUrl, { signal, marketId } = {}) {
  const resolvedUrl = resolveImageUrl(imageUrl);
  if (!resolvedUrl) throw new Error("Görsel URL'si geçersiz.");

  if (!isApiImageUrl(imageUrl, resolvedUrl)) {
    return { src: resolvedUrl, revoke: false };
  }

  const selectedMarketId = marketId || getSelectedMarketId();
  if (!selectedMarketId) throw new Error("Görsel için seçili market gerekli.");

  const headers = { Accept: "image/*", "X-Market-Id": selectedMarketId };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(resolvedUrl, { headers, signal, cache: "no-store" });
  if (!response.ok) throw new Error(`Görsel yüklenemedi (${response.status}).`);

  return { src: URL.createObjectURL(await response.blob()), revoke: true };
}

export const apiClient = {
  get: (path, options) => apiRequest(path, { ...options, method: "GET" }),
  post: (path, body, options) => apiRequest(path, { ...options, method: "POST", body }),
  patch: (path, body, options) => apiRequest(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => apiRequest(path, { ...options, method: "DELETE" }),
};
