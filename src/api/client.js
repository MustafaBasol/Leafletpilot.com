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

function getErrorMessage(response, body) {
  const detail = typeof body === "object" && body !== null ? body.detail || body.message : body;
  const formattedDetail = Array.isArray(detail)
    ? detail
        .map((item) => {
          const path = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
          return [path, item.msg].filter(Boolean).join(": ");
        })
        .join("; ")
    : detail;
  const suffix = formattedDetail
    ? `: ${typeof formattedDetail === "string" ? formattedDetail : JSON.stringify(formattedDetail)}`
    : "";
  return `API isteği başarısız oldu (${response.status} ${response.statusText})${suffix}`;
}

export async function apiRequest(path, { method = "GET", params, body, marketId, headers } = {}) {
  const requestHeaders = {
    Accept: "application/json",
    ...headers,
  };

  const options = {
    method,
    headers: requestHeaders,
  };

  if (marketId) {
    requestHeaders["X-Market-Id"] = marketId;
  }

  if (body !== undefined && body !== null) {
    requestHeaders["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
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

export const apiClient = {
  get: (path, options) => apiRequest(path, { ...options, method: "GET" }),
  post: (path, body, options) => apiRequest(path, { ...options, method: "POST", body }),
  patch: (path, body, options) => apiRequest(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => apiRequest(path, { ...options, method: "DELETE" }),
};
