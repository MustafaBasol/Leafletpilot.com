export function campaignIdFromPersistedDraft(response) {
  const id = response?.id || response?.campaign_id || response?.campaign?.id;
  if (!id) throw new Error("Backend yanıtında kampanya kimliği bulunamadı.");
  return id;
}

export function finalizePayloadFromPersistedDraft(response) {
  const expectedRevision = response?.draft_revision ?? response?.campaign?.draft_revision;
  if (!Number.isInteger(expectedRevision) || expectedRevision < 0) {
    throw new Error("Backend yanıtında finalizasyon için geçerli taslak revizyonu bulunamadı.");
  }
  return { expected_revision: expectedRevision };
}

export async function finalizeCampaignAndCreateExports({
  persistDraft,
  finalize,
  createExport,
  navigate,
  selectedMarketId,
  selectedFormats,
  exportFormats,
}) {
  const persistedDraft = await persistDraft();
  const campaignId = campaignIdFromPersistedDraft(persistedDraft);
  const payload = finalizePayloadFromPersistedDraft(persistedDraft);

  await finalize(campaignId, payload, selectedMarketId);

  const formats = selectedFormats.filter((format) => exportFormats.some((item) => item.id === format));
  if (formats.length) {
    await createExport(campaignId, { job_type: "final_export", requested_formats: formats }, selectedMarketId);
  }

  navigate(campaignId);
  return campaignId;
}
