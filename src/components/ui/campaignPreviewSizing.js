const DEFAULT_DIMENSIONS = { width: 1240, height: 1754 };
const FORMAT_DIMENSIONS = {
  pdf: DEFAULT_DIMENSIONS,
  png: DEFAULT_DIMENSIONS,
  instagram_post: { width: 1080, height: 1080 },
  instagram_story: { width: 1080, height: 1920 },
  whatsapp: { width: 1080, height: 1920 },
};

function readDimension(html, attribute) {
  const match = String(html || "").match(new RegExp(`${attribute}=["'](\\d+(?:\\.\\d+)?)["']`, "i"));
  const value = Number(match?.[1]);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function getCampaignPreviewDimensions(html, fallbackFormat = "pdf") {
  const width = readDimension(html, "data-preview-width");
  const height = readDimension(html, "data-preview-height");
  if (width && height) return { width, height };

  return FORMAT_DIMENSIONS[fallbackFormat] || DEFAULT_DIMENSIONS;
}
