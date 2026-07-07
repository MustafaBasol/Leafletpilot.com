import { apiClient } from "./client.js";

export function listMarketMembers() {
  return apiClient.get("/market-members");
}

export function updateMarketMember(membershipId, payload) {
  return apiClient.patch(`/market-members/${membershipId}`, payload);
}

export function listMarketInvitations() {
  return apiClient.get("/market-invitations");
}

export function createMarketInvitation(payload) {
  return apiClient.post("/market-invitations", payload);
}

export function revokeMarketInvitation(invitationId) {
  return apiClient.post(`/market-invitations/${invitationId}/revoke`, {});
}

export function acceptInvitation(payload) {
  return apiClient.post("/auth/accept-invitation", payload, { skipAuth: true, skipMarket: true });
}

export function acceptInvitationAuthenticated(payload) {
  return apiClient.post("/auth/accept-invitation-authenticated", payload, { skipMarket: true });
}
