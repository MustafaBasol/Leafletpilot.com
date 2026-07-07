import { apiClient } from "./client.js";

export function login(email, password) {
  return apiClient.post("/auth/login", { email, password }, { skipAuth: true, skipMarket: true });
}

export function getMe() {
  return apiClient.get("/auth/me", { skipMarket: true });
}
