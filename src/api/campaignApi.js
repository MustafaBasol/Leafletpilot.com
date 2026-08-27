import { apiBaseUrl } from "./config.js";
import { apiClient, ApiError } from "./client.js";
import { getAccessToken } from "./authSession.js";

export function listCampaigns(params, marketId) {
  return apiClient.get("/campaigns", { params, marketId });
}

export function getCampaign(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}`, { marketId });
}

export function getCampaignPreviewHtml(campaignId, marketId, params = {}) {
  return apiClient.get(`/campaigns/${campaignId}/preview-html`, { marketId, params });
}

export function getCampaignIntelligence(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}/intelligence`, { marketId });
}

export function analyzeCampaignIntelligence(campaignId, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/intelligence/analyze`, {}, { marketId });
}

export function applyCampaignIntelligence(campaignId, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/intelligence/apply`, {}, { marketId });
}
export function createCampaign(payload, marketId) {
  return apiClient.post("/campaigns", payload, { marketId });
}

export function getCampaignBuilderOptions(marketId) {
  return apiClient.get("/campaigns/builder/options", { marketId });
}

export function finalizeCampaign(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/finalize`, payload, { marketId });
}

export function reorderCampaignItems(campaignId, itemIds, marketId) {
  return apiClient.patch(`/campaigns/${campaignId}/items/order`, { item_ids: itemIds }, { marketId });
}

export function updateCampaign(campaignId, payload, marketId) {
  return apiClient.patch(`/campaigns/${campaignId}`, payload, { marketId });
}

export function cancelCampaign(campaignId, marketId) {
  return apiClient.delete(`/campaigns/${campaignId}`, { marketId });
}

export function parseCampaignText(payload, marketId) {
  return apiClient.post("/campaigns/parse-text", payload, { marketId });
}

export function createCampaignFromText(payload, marketId) {
  return apiClient.post("/campaigns/from-text", payload, { marketId });
}

export function generateCampaignSuggestions(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/generate-suggestions`, payload, { marketId });
}

export function generateItemSuggestions(campaignId, itemId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/items/${itemId}/generate-suggestions`, payload, { marketId });
}

export function resolveCampaignItemMatch(campaignId, itemId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/items/${itemId}/resolve-match`, payload, { marketId });
}

export function listCampaignFiles(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}/files`, { marketId });
}

export function createExportJob(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/export-jobs`, payload, { marketId });
}

export async function downloadCampaignFile(campaignId, fileId, marketId) {
  return fetchCampaignFile(campaignId, fileId, marketId);
}

export async function fetchCampaignFile(campaignId, fileId, marketId) {
  const token = getAccessToken();
  const response = await fetch(`${apiBaseUrl}/campaigns/${campaignId}/files/${fileId}/download`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "X-Market-Id": marketId,
    },
  });

  if (!response.ok) {
    throw new ApiError(`Dosya indirilemedi (${response.status} ${response.statusText})`, { status: response.status });
  }

  return response.blob();
}

export function applyCampaignRevision(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/revisions`, payload, { marketId });
}

export function undoCampaignRevision(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/revisions/undo`, payload, { marketId });
}

export function createAIRevisionProposal(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/revision-intent`, payload, { marketId });
}

export function applyAIRevisionProposal(campaignId, proposalId, marketId) {
  return apiClient.post(
    `/campaigns/${campaignId}/revision-intent/${proposalId}/apply`,
    undefined,
    { marketId },
  );
}

export function approveCampaign(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/approve`, payload, { marketId });
}

export function getCampaignItemImageOptions(campaignId, itemId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}/items/${itemId}/image-options`, { marketId });
}

export function getProfessionalizationHistory(campaignId, marketId) {
  return apiClient.get(`/campaigns/${campaignId}/professionalization`, { marketId });
}

export function createProfessionalizationRun(campaignId, payload, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/professionalization`, payload, { marketId });
}

export function applyProfessionalizationRun(campaignId, runId, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/professionalization/${runId}/apply`, undefined, { marketId });
}

export function restoreOriginalProfessionalization(campaignId, marketId) {
  return apiClient.post(`/campaigns/${campaignId}/professionalization/original`, undefined, { marketId });
}