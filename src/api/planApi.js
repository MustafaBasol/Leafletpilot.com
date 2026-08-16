import { apiClient } from "./client.js";

export function getMyMarketPlan(marketId) {
  return apiClient.get("/market/plan", { marketId });
}
