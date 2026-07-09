import { apiClient } from "./client.js";

export const onboardingApi = {
  get: () => apiClient.get("/onboarding"),
  updateProfile: (payload) => apiClient.patch("/onboarding/profile", payload),
  updateBrand: (payload) => apiClient.patch("/onboarding/brand", payload),
  updateTemplate: (payload) => apiClient.patch("/onboarding/template", payload),
  complete: () => apiClient.post("/onboarding/complete", {}),
};
