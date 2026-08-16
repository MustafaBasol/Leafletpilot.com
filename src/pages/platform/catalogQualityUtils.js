export const catalogQualityStateLabels = {
  exact_duplicate: "Kesin yinelenen",
  strong_candidate: "Güçlü aday",
  barcode_conflict: "Barkod çakışması",
  identity_conflict: "Kimlik çakışması",
  alias_conflict: "Alternatif ad çakışması",
  ignored: "Yok sayıldı",
  resolved: "Çözüldü",
};

export const catalogQualitySeverityLabels = {
  critical: "Kritik",
  high: "Yüksek",
  medium: "Orta",
  low: "Düşük",
};

export function catalogQualityStateLabel(value) {
  return catalogQualityStateLabels[value] || "Bilinmeyen durum";
}

export function catalogQualitySeverityLabel(value) {
  return catalogQualitySeverityLabels[value] || "İnceleme gerekli";
}

export function candidateProducts(candidate) {
  return {
    productA: candidate?.product_a || candidate?.left_product || candidate?.left || {},
    productB: candidate?.product_b || candidate?.right_product || candidate?.right || {},
  };
}

export function mergeSelection(candidate, winnerId) {
  const { productA, productB } = candidateProducts(candidate);
  const targetId = winnerId || productB.id || productA.id || null;
  const sourceId = targetId === productA.id ? productB.id : productA.id;
  return { sourceId, targetId };
}

export function readableQualityItems(values) {
  if (!values) return [];
  if (Array.isArray(values)) return values.filter(Boolean).map(String);
  if (typeof values === "object") return Object.entries(values).filter(([, value]) => value).map(([key, value]) => `${key}: ${value}`);
  return [String(values)];
}
