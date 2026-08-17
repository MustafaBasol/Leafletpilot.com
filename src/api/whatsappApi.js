import { apiClient } from "./client.js";

export function getWhatsAppChannelStatus() {
  return apiClient.get("/integrations/whatsapp/status");
}

export function createWhatsAppVerification(payload) {
  return apiClient.post("/integrations/whatsapp/verifications", payload);
}

export function getWhatsAppVerification(verificationId) {
  return apiClient.get(`/integrations/whatsapp/verifications/${verificationId}`);
}

export function cancelWhatsAppVerification(verificationId) {
  return apiClient.post(`/integrations/whatsapp/verifications/${verificationId}/cancel`, {});
}

export function revokeMemberWhatsApp(membershipId, reason) {
  return apiClient.post(`/integrations/whatsapp/members/${membershipId}/revoke`, { reason: reason || null });
}
