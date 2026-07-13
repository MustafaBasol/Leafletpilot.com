export function normalizeOptionalUuid(value) {
  return value || null;
}

export function revokeObjectUrls(urls) {
  for (const url of new Set(Object.values(urls || {}).filter(Boolean))) {
    URL.revokeObjectURL(url);
  }
}
