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

async function request(path, { method = "GET", params, body, headers: extraHeaders, skipAuth = false } = {}) {
  const url = new URL(`${apiBaseUrl}${path}`);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  const headers = { Accept: "application/json", ...(extraHeaders || {}) };
  const token = skipAuth ? "" : getPlatformAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const options = { method, headers };
  if (body !== undefined) {
    if (body instanceof Blob || body instanceof ArrayBuffer || body instanceof FormData) {
      options.body = body;
    } else {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
  }
  let response;
  try {
    response = await fetch(url.toString(), options);
  } catch {
    throw new ApiError("Sunucuya ulaşılamadı. Lütfen tekrar deneyin.", { status: 0 });
  }
  const text = await response.text();
  let responseBody = null;
  try { responseBody = text ? JSON.parse(text) : null; } catch { responseBody = null; }
  if (!response.ok) {
    throwPlatformErrorIfNeeded(response, responseBody);
  }
  return responseBody;
}

function throwPlatformErrorIfNeeded(response, responseBody) {
  if (isInvalidPlatformSession(response, responseBody)) redirectToPlatformLoginIfNeeded();
  throw new ApiError(readPlatformErrorMessage(response, responseBody), { status: response.status, body: responseBody });
}

async function requestImage(path) {
  const headers = { Authorization: `Bearer ${getPlatformAccessToken()}` };
  const response = await fetch(`${apiBaseUrl}${path}`, { headers });
  if (!response.ok) {
    const responseBody = await response.clone().json().catch(() => null);
    throwPlatformErrorIfNeeded(response, responseBody);
  }
  return URL.createObjectURL(await response.blob());
}

async function downloadPlatformFile(path, filename) {
  const response = await fetch(`${apiBaseUrl}${path}`, { headers: { Authorization: `Bearer ${getPlatformAccessToken()}` } });
  if (!response.ok) throwPlatformErrorIfNeeded(response, await response.clone().json().catch(() => null));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
}

export const platformApi = {
  login: (email, password) => request("/platform/auth/login", { method: "POST", skipAuth: true, body: { email, password } }),
  me: () => request("/platform/auth/me"),
  overview: () => request("/platform/overview"),
  listAudit: (params) => request("/platform/audit", { params }),
  listSignupRequests: (params) => request("/platform/signup-requests", { params }),
  getSignupRequest: (id) => request(`/platform/signup-requests/${id}`),
  updateSignupRequest: (id, body) => request(`/platform/signup-requests/${id}`, { method: "PATCH", body }),
  provisionSignupRequest: (id, body) => request(`/platform/signup-requests/${id}/provision`, { method: "POST", body }),
  listMarkets: (params) => request("/platform/markets", { params }),
  getMarket: (id) => request(`/platform/markets/${id}`),
  updateMarketLifecycle: (id, body) => request(`/platform/markets/${id}/lifecycle`, { method: "PATCH", body }),
  updateMarketPlan: (id, body) => request(`/platform/markets/${id}/plan`, { method: "PATCH", body }),
  createOwnerInvitation: (id, body) => request(`/platform/markets/${id}/owner-invitation`, { method: "POST", body }),
  rotateOwnerInvitation: (id, body) => request(`/platform/markets/${id}/owner-invitation/rotate`, { method: "POST", body }),
  revokeOwnerInvitation: (id) => request(`/platform/markets/${id}/owner-invitation/revoke`, { method: "POST" }),
  createManualOwnerInvitationLink: (id) => request(`/platform/markets/${id}/owner-invitation/manual-link`, { method: "POST" }),
  listGlobalCategories: (params) => request("/platform/catalog/categories", { params }),
  createGlobalCategory: (body) => request("/platform/catalog/categories", { method: "POST", body }),
  updateGlobalCategory: (id, body) => request(`/platform/catalog/categories/${id}`, { method: "PATCH", body }),
  deactivateGlobalCategory: (id) => request(`/platform/catalog/categories/${id}`, { method: "DELETE" }),
  listGlobalBrands: (params) => request("/platform/catalog/brands", { params }),
  createGlobalBrand: (body) => request("/platform/catalog/brands", { method: "POST", body }),
  updateGlobalBrand: (id, body) => request(`/platform/catalog/brands/${id}`, { method: "PATCH", body }),
  deactivateGlobalBrand: (id) => request(`/platform/catalog/brands/${id}`, { method: "DELETE" }),
  listGlobalProducts: (params) => request("/platform/catalog/products", { params }),
  listCatalogQualityCandidates: (params) => request("/platform/catalog/quality/candidates", { params }),
  previewCatalogProductMerge: (body) => request("/platform/catalog/quality/merge-preview", { method: "POST", body }),
  mergeCatalogProducts: (body) => request("/platform/catalog/quality/merge", { method: "POST", body }),
  ignoreCatalogQualityCandidate: (body) => request("/platform/catalog/quality/ignore", { method: "POST", body }),
  downloadGlobalProductImportTemplate: () => downloadPlatformFile("/platform/catalog/products/import-template", "leafletpilot-global-products-template.xlsx"),
  previewGlobalProductImport: (file, imagesZip) => { const body = new FormData(); body.append("workbook", file); if (imagesZip) body.append("images_zip", imagesZip); return request("/platform/catalog/products/import/preview", { method: "POST", body }); },
  importGlobalProducts: (file, imagesZip) => { const body = new FormData(); body.append("workbook", file); if (imagesZip) body.append("images_zip", imagesZip); return request("/platform/catalog/products/import", { method: "POST", body }); },
  createGlobalProduct: (body) => request("/platform/catalog/products", { method: "POST", body }),
  updateGlobalProduct: (id, body) => request(`/platform/catalog/products/${id}`, { method: "PATCH", body }),
  deactivateGlobalProduct: (id) => request(`/platform/catalog/products/${id}`, { method: "DELETE" }),
  uploadGlobalProductImage: (id, blob, { mimeType, primary = false } = {}) => request(`/platform/catalog/products/${id}/images`, { method: "POST", params: { primary }, body: blob, headers: { "Content-Type": mimeType } }),
  setGlobalProductPrimaryImage: (productId, imageId) => request(`/platform/catalog/products/${productId}/images/${imageId}/primary`, { method: "PATCH" }),
  removeGlobalProductImage: (productId, imageId) => request(`/platform/catalog/products/${productId}/images/${imageId}`, { method: "DELETE" }),
  getGlobalProductImageUrl: (productId, imageId) => requestImage(`/platform/catalog/products/${productId}/images/${imageId}/content`),
  approveGlobalProductImage: (productId, imageId) => request(`/platform/catalog/products/${productId}/images/${imageId}/approve`, { method: "PATCH" }),
  rejectGlobalProductImage: (productId, imageId) => request(`/platform/catalog/products/${productId}/images/${imageId}/reject`, { method: "PATCH" }),
  bulkApproveGlobalProductImages: (imageIds) => request("/platform/catalog/products/images/bulk-approve", { method: "POST", body: { image_ids: imageIds } }),
  bulkRejectGlobalProductImages: (imageIds) => request("/platform/catalog/products/images/bulk-reject", { method: "POST", body: { image_ids: imageIds } }),
  previewGlobalProductImageBulkImport: (zipBlob) => request("/platform/catalog/products/bulk-images/preview", { method: "POST", body: zipBlob, headers: { "Content-Type": "application/zip" } }),
  importGlobalProductImageBulkImport: (zipBlob, resolutions) => request("/platform/catalog/products/bulk-images/import", { method: "POST", params: resolutions?.length ? { resolutions: JSON.stringify(resolutions) } : undefined, body: zipBlob, headers: { "Content-Type": "application/zip" } }),
  listTemplates: (params) => request("/platform/templates", { params }),
  createTemplate: (body) => request("/platform/templates", { method: "POST", body }),
  updateTemplate: (id, body) => request(`/platform/templates/${id}`, { method: "PATCH", body }),
  publishTemplate: (id) => request(`/platform/templates/${id}/publish`, { method: "POST" }),
  duplicateTemplate: (id) => request(`/platform/templates/${id}/duplicate`, { method: "POST" }),
  archiveTemplate: (id) => request(`/platform/templates/${id}/archive`, { method: "POST" }),
  restoreTemplate: (id) => request(`/platform/templates/${id}/restore`, { method: "POST" }),
};
