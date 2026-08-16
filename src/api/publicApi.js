import { apiClient } from "./client.js";

export function submitSignupRequest(payload) {
  return apiClient.post("/public/signup-requests", payload, { skipAuth: true, skipMarket: true });
}

export function getPublicPlans() {
  return apiClient.get("/public/plans", { skipAuth: true, skipMarket: true });
}
