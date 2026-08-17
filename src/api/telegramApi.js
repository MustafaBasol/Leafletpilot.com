import { apiClient } from "./client.js";

export function getTelegramStatus(marketId) {
  return apiClient.get("/integrations/telegram/status", { marketId });
}
