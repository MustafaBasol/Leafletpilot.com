import { apiClient } from "./client.js";

export function listProducts(params, marketId) {
  return apiClient.get("/catalog/products", { params, marketId });
}

export function createProduct(payload, marketId) {
  return apiClient.post("/catalog/products", payload, { marketId });
}

export function updateProduct(productId, payload, marketId) {
  return apiClient.patch(`/catalog/products/${productId}`, payload, { marketId });
}

export function createProductAlias(productId, payload, marketId) {
  return apiClient.post(`/catalog/products/${productId}/aliases`, payload, { marketId });
}

export function deleteProductAlias(productId, aliasId, marketId) {
  return apiClient.delete(`/catalog/products/${productId}/aliases/${aliasId}`, { marketId });
}

export function listBrands(params, marketId) {
  return apiClient.get("/catalog/brands", { params, marketId });
}

export function createBrand(payload, marketId) {
  return apiClient.post("/catalog/brands", payload, { marketId });
}

export function listCategories(params, marketId) {
  return apiClient.get("/catalog/categories", { params, marketId });
}

export function createCategory(payload, marketId) {
  return apiClient.post("/catalog/categories", payload, { marketId });
}
