export function normalizeOptionalUuid(value) {
  return value || null;
}

export function revokeObjectUrls(urls) {
  for (const url of new Set(Object.values(urls || {}).filter(Boolean))) {
    URL.revokeObjectURL(url);
  }
}

export function selectEditorImage(images = []) {
  return images.find((image) => image.is_primary)
    || images.find((image) => ["good", "excellent"].includes(image.quality_status))
    || images[0]
    || null;
}
