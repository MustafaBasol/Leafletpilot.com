import { apiBaseUrl } from "./config.js";
import { apiClient, apiRequest, ApiError } from "./client.js";
import { getAccessToken } from "./authSession.js";

export const getMarketLogo = (marketId) => apiClient.get("/market/logo", { marketId });
export const uploadMarketLogo = (file, marketId) => apiRequest("/market/logo", { method: "PUT", body: file, headers: { "Content-Type": file.type }, marketId });
export const removeMarketLogo = (marketId) => apiRequest("/market/logo", { method: "DELETE", marketId });
export async function fetchMarketLogo(marketId) {
  const response = await fetch(`${apiBaseUrl}/market/logo/content`, { headers: { ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}), "X-Market-Id": marketId } });
  if (!response.ok) throw new ApiError("Market logosu indirilemedi.", { status: response.status });
  return response.blob();
}