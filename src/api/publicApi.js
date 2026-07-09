import { apiClient } from "./client.js";

export function submitSignupRequest(payload) {
  return apiClient.post("/public/signup-requests", payload, { skipAuth: true, skipMarket: true });
}
