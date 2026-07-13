import { demoMarketId, isRealApiEnabled } from "../api/config.js";
import * as catalogApi from "../api/catalogApi.js";
import { getSelectedMarketId } from "../api/authSession.js";
import * as campaignApi from "../api/campaignApi.js";
import * as templateApi from "../api/templateApi.js";
import {
  activities,
  campaigns,
  findCampaignById,
  metrics,
  missingProducts,
  parsedWizardProducts,
  products,
  templates,
  waitingApprovals,
} from "./mockData.js";

const statusLabels = {
  draft: "Taslak",
  parsing: "Ürünler analiz ediliyor",
  matching: "Ürünler eşleştiriliyor",
  missing_products: "Eksik ürün var",
  preview_ready: "Önizleme hazır",
  waiting_approval: "Onay bekliyor",
  revision_requested: "Revizyon istendi",
  approved: "Onaylandı",
  generating_files: "Dosyalar oluşturuluyor",
  completed: "Tamamlandı",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

const channelLabels = {
  panel: "Panel",
  telegram: "Telegram",
  whatsapp: "WhatsApp",
  import: "İçe Aktarım",
};

const sourceTypeLabels = {
  text: "Metin",
  excel: "Excel",
  pdf: "PDF",
  barcode_list: "Barkod listesi",
  manual: "Manuel",
};

const matchStatusLabels = {
  matched: "Eşleşti",
  low_confidence: "Kontrol gerekli",
  not_found: "Bulunamadı",
  manual_selected: "Manuel seçildi",
  new_product_needed: "Yeni ürün gerekli",
  use_without_image: "Görselsiz devam",
  excluded: "Kampanyadan çıkarıldı",
};

const resolutionByStatus = {
  "Eşleşti": "manual_selected",
  "Yeni ürün gerekli": "new_product_needed",
  "Görselsiz devam": "use_without_image",
  "Kampanyadan çıkarıldı": "excluded",
  "Bulunamadı": "not_found",
};

function requireSelectedMarketId() {
  const marketId = getSelectedMarketId();
  if (!marketId) throw new Error("Real API modu için oturumdaki market seçimi gerekli.");
  return marketId;
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

function formatUpdatedAt(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatMoney(value, currency = "EUR") {
  if (value === undefined || value === null || value === "") return "-";
  const numberValue = Number(value);
  if (Number.isNaN(numberValue)) return String(value);
  return `${numberValue.toFixed(2)} ${currency}`;
}

function unwrapList(response) {
  return Array.isArray(response) ? response : response?.items || [];
}

function uniqueByName(items, fallbackLabel) {
  const seen = new Set();
  return items
    .map((item) => item || fallbackLabel)
    .filter((name) => {
      if (!name || seen.has(name)) return false;
      seen.add(name);
      return true;
    })
    .map((name) => ({ id: name, name }));
}

function mapCampaign(campaign) {
  return {
    id: campaign.id,
    name: campaign.title,
    market: "Demo Market",
    marketId: campaign.market_id,
    status: statusLabels[campaign.status] || campaign.status,
    productCount: campaign.product_count ?? 0,
    missingCount: campaign.missing_count ?? 0,
    channel: channelLabels[campaign.channel] || campaign.channel || "Panel",
    templateId: campaign.template_id || "",
    template: campaign.template_name || (campaign.template_id ? "Şablon adı yok" : "Şablon yok"),
    frozenAt: campaign.frozen_at || null,
    finalizedAt: campaign.finalized_at || null,
    campaignStartDate: campaign.campaign_start_date || "",
    campaignEndDate: campaign.campaign_end_date || "",
    createdAt: formatDate(campaign.created_at),
    updatedAt: formatUpdatedAt(campaign.updated_at),
    date: formatDate(campaign.campaign_start_date || campaign.created_at),
    files: [],
  };
}

function mapCampaignItem(item, suggestions = []) {
  const score =
    item.match_confidence === null || item.match_confidence === undefined ? 0 : Math.round(Number(item.match_confidence));

  return {
    id: item.id,
    productId: item.product_id || "",
    rawLine: item.raw_line,
    incomingName: item.incoming_name,
    matchedProduct: item.display_name || "Eşleşme yok",
    price: formatMoney(item.price, item.currency),
    oldPrice: formatMoney(item.old_price, item.currency),
    currency: item.currency,
    category: item.category_hint || "-",
    score,
    status: matchStatusLabels[item.match_status] || item.match_status,
    matchStatus: item.match_status,
    image: Boolean(item.product_id),
    warnings: Array.isArray(item.parsed_payload?.warnings) ? item.parsed_payload.warnings : [],
    suggestions,
  };
}

function mapCampaignDetail(campaign) {
  const suggestionsByItem = new Map();
  (campaign.matching_suggestions || []).forEach((suggestion) => {
    const current = suggestionsByItem.get(suggestion.campaign_item_id) || [];
    current.push(suggestion);
    suggestionsByItem.set(suggestion.campaign_item_id, current);
  });

  const base = mapCampaign(campaign);
  return {
    ...base,
    title: campaign.title,
    slug: campaign.slug || "",
    sourceType: sourceTypeLabels[campaign.source_type] || campaign.source_type || "-",
    sourceTypeRaw: campaign.source_type || "",
    channelRaw: campaign.channel || "",
    currency: campaign.currency,
    language: campaign.language,
    rawInputText: campaign.raw_input_text || "",
    matchedCount: campaign.matched_count ?? 0,
    lowConfidenceCount: campaign.low_confidence_count ?? 0,
    createdAtFull: formatDateTime(campaign.created_at),
    updatedAtFull: formatDateTime(campaign.updated_at),
    items: (campaign.items || []).map((item) => mapCampaignItem(item, suggestionsByItem.get(item.id) || [])),
    files: campaign.files || [],
    exportJobs: campaign.export_jobs || [],
    matchingSuggestions: campaign.matching_suggestions || [],
  };
}

function mapProduct(product, { brandsById = new Map(), categoriesById = new Map() } = {}) {
  const brandName = product.brand_id ? brandsById.get(product.brand_id)?.name || "Marka yok" : "Marka yok";
  const categoryName = product.category_id
    ? categoriesById.get(product.category_id)?.name || "Kategori yok"
    : "Kategori yok";

  return {
    id: product.id,
    name: product.name,
    shortName: product.short_name || product.name,
    price: "",
    brandId: product.brand_id || "",
    categoryId: product.category_id || "",
    brand: brandName,
    category: categoryName,
    barcode: product.barcode || "-",
    packageSize: product.package_size || "",
    packageType: product.package_type || "",
    regularPrice: product.regular_price ?? "",
    promoPrice: product.promo_price ?? "",
    currency: product.currency || "EUR",
    badgeText: product.badge_text || "",
    sortOrder: product.sort_order ?? 0,
    alternativeNames: (product.aliases || []).map((alias) => (typeof alias === "string" ? alias : alias.alias)).filter(Boolean),
    alternativeNameItems: (product.aliases || []).filter((alias) => typeof alias !== "string"),
    status: product.is_active ? "Aktif" : "Pasif",
    imageStatus: product.images?.length ? "Var" : "Görsel yok",
    usageCount: product.usage_count || 0,
  };
}

function mapMockProduct(product) {
  return {
    ...product,
    brandId: product.brand,
    categoryId: product.category,
  };
}

function mapTemplate(template) {
  const config = template.config_json || {};
  const formats = Array.isArray(config.formats) && config.formats.length ? config.formats : ["A4 PNG"];
  const maxProductsPerPage = Number(config.max_products_per_page || 0);

  return {
    id: template.id,
    name: template.name,
    slug: template.slug,
    type: template.template_type || "market",
    templateType: template.template_type || "market",
    formats,
    capacity: maxProductsPerPage ? `${maxProductsPerPage} ürün / sayfa` : "Kapasite belirtilmedi",
    maxProductsPerPage,
    status: template.is_active ? "Aktif" : "Pasif",
    isDefault: template.slug === "premium-market",
    isGlobal: Boolean(template.is_global),
    recommendation: template.description || "Bu şablon için açıklama henüz girilmedi.",
    bestFor: template.is_global ? "Tüm marketler" : "Bu market",
    previewTone: config.preview_tone || "classic",
    createdAt: formatDateTime(template.created_at),
    updatedAt: formatDateTime(template.updated_at),
    raw: template,
  };
}

export function getDashboardData() {
  return {
    metrics,
    waitingApprovals,
    missingProducts,
    activities,
  };
}

export async function getCampaigns() {
  if (!isRealApiEnabled) return campaigns;
  const marketId = requireSelectedMarketId();

  const response = await campaignApi.listCampaigns({ limit: 50, offset: 0 }, marketId);
  return unwrapList(response).map(mapCampaign);
}

export async function getCampaignDetail(id) {
  if (!isRealApiEnabled) return findCampaignById(id);
  const marketId = requireSelectedMarketId();

  return mapCampaignDetail(await campaignApi.getCampaign(id, marketId));
}

export async function updateCampaignDetail(id, form) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return mapCampaignDetail(
    await campaignApi.updateCampaign(
      id,
      {
        title: cleanText(form.title),
        template_id: cleanOptionalId(form.templateId),
        campaign_start_date: form.campaignStartDate || null,
        campaign_end_date: form.campaignEndDate || null,
      },
      marketId,
    ),
  );
}

export async function getCampaignPreviewHtml(campaignId) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return campaignApi.getCampaignPreviewHtml(campaignId, marketId);
}

export async function finalizeCampaign(id) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return mapCampaignDetail((await campaignApi.finalizeCampaign(id, marketId)).campaign);
}

export async function reorderCampaignItems(id, items) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return mapCampaignDetail(await campaignApi.reorderCampaignItems(id, items.map((item) => item.id), marketId));
}

export async function getProducts() {
  if (!isRealApiEnabled) return products;
  requireSelectedMarketId();

  const { products: catalogProducts } = await getProductCatalogData();
  return catalogProducts;
}

export async function getProductCatalogData() {
  if (!isRealApiEnabled) {
    const mockProducts = products.map(mapMockProduct);
    return {
      products: mockProducts,
      brands: uniqueByName(mockProducts.map((product) => product.brand), "Marka yok"),
      categories: uniqueByName(mockProducts.map((product) => product.category), "Kategori yok"),
    };
  }
  const marketId = requireSelectedMarketId();

  const [productsResponse, brandsResponse, categoriesResponse] = await Promise.all([
    catalogApi.listProducts({ limit: 100, offset: 0, include_global: true }, marketId),
    catalogApi.listBrands({ limit: 100, offset: 0, include_global: true }, marketId),
    catalogApi.listCategories({ limit: 100, offset: 0, include_global: true }, marketId),
  ]);
  const brands = unwrapList(brandsResponse);
  const categories = unwrapList(categoriesResponse);
  const brandsById = new Map(brands.map((brand) => [brand.id, brand]));
  const categoriesById = new Map(categories.map((category) => [category.id, category]));

  return {
    products: unwrapList(productsResponse).map((product) => mapProduct(product, { brandsById, categoriesById })),
    brands,
    categories,
  };
}

export async function getCatalogBrands() {
  if (!isRealApiEnabled) {
    return uniqueByName(products.map((product) => product.brand), "Marka yok").map((brand) => ({
      ...brand,
      slug: brand.name.toLocaleLowerCase("tr-TR").replace(/\s+/g, "-"),
      is_active: true,
      is_global: false,
    }));
  }
  const marketId = requireSelectedMarketId();
  return unwrapList(await catalogApi.listBrands({ limit: 100, offset: 0, include_global: true }, marketId));
}

export async function createCatalogBrand(form) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return catalogApi.createBrand(
    {
      name: cleanText(form.name),
      slug: cleanText(form.slug),
      is_global: Boolean(form.isGlobal),
      is_active: true,
    },
    marketId,
  );
}

export async function getCatalogCategories() {
  if (!isRealApiEnabled) {
    return uniqueByName(products.map((product) => product.category), "Kategori yok").map((category) => ({
      ...category,
      slug: category.name.toLocaleLowerCase("tr-TR").replace(/\s+/g, "-"),
      parent_id: null,
      is_active: true,
      is_global: false,
    }));
  }
  const marketId = requireSelectedMarketId();
  return unwrapList(await catalogApi.listCategories({ limit: 100, offset: 0, include_global: true }, marketId));
}

export async function createCatalogCategory(form) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return catalogApi.createCategory(
    {
      name: cleanText(form.name),
      slug: cleanText(form.slug),
      parent_id: cleanOptionalId(form.parentId),
      is_global: Boolean(form.isGlobal),
      is_active: true,
    },
    marketId,
  );
}

export async function parseCampaignTextPreview({ rawText, currency = "EUR", language = "tr" }) {
  if (!isRealApiEnabled) return parsedWizardProducts;
  return campaignApi.parseCampaignText({ raw_text: rawText, default_currency: currency, language }, requireSelectedMarketId());
}

export async function createCampaignFromText({ title, rawText, templateId, currency = "EUR", language = "tr" }) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return campaignApi.createCampaignFromText(
    {
      title: cleanText(title),
      raw_text: rawText,
      channel: "panel",
      source_type: "text",
      template_id: cleanOptionalId(templateId),
      currency,
      language,
      generate_suggestions: true,
      suggestion_limit: 5,
    },
    marketId,
  );
}

export async function generateCampaignDetailSuggestions(campaignId) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return campaignApi.generateCampaignSuggestions(campaignId, { limit_per_item: 5 }, marketId);
}

export async function generateCampaignItemSuggestions(campaignId, itemId) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return campaignApi.generateItemSuggestions(campaignId, itemId, { limit: 5 }, marketId);
}

export async function resolveCampaignItem(campaignId, item, resolutionStatus, suggestion) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  const resolution = resolutionByStatus[resolutionStatus] || resolutionStatus || "manual_selected";
  return campaignApi.resolveCampaignItemMatch(
    campaignId,
    item.id,
    {
      resolution,
      product_id: suggestion?.product_id || item.productId || null,
      display_name: suggestion?.suggested_name || item.matchedProduct || item.incomingName,
      notes: suggestion ? "Öneri üzerinden eşleştirildi." : "Panel üzerinden güncellendi.",
    },
    marketId,
  );
}

export async function createCampaignExportJob(campaignId, requestedFormats = ["pdf", "png"]) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return campaignApi.createExportJob(
    campaignId,
    { job_type: "final_export", requested_formats: requestedFormats, status: "queued" },
    marketId,
  );
}

export async function downloadCampaignFile(campaignId, file) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  const blob = await campaignApi.downloadCampaignFile(campaignId, file.id, marketId);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.downloadName || file.name || `${file.id}.${file.format || "bin"}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return null;
}

function cleanText(value) {
  const text = String(value || "").trim();
  return text || null;
}

function cleanOptionalId(value) {
  return value ? value : null;
}

function parseAliasText(value) {
  const seen = new Set();
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => {
      const normalized = item.toLocaleLowerCase("tr-TR");
      if (!item || seen.has(normalized)) return false;
      seen.add(normalized);
      return true;
    });
}

function buildProductPayload(form, { includeAliases = false } = {}) {
  const payload = {
    name: cleanText(form.name),
    short_name: cleanText(form.shortName),
    barcode: cleanText(form.barcode),
    brand_id: cleanOptionalId(form.brandId),
    category_id: cleanOptionalId(form.categoryId),
    package_size: cleanText(form.packageSize),
    package_type: cleanText(form.packageType),
    regular_price: form.regularPrice === "" || form.regularPrice === null ? null : Number(form.regularPrice),
    promo_price: form.promoPrice === "" || form.promoPrice === null ? null : Number(form.promoPrice),
    currency: cleanText(form.currency || "EUR")?.toUpperCase(),
    badge_text: cleanText(form.badgeText),
    sort_order: Number(form.sortOrder || 0),
    is_active: form.status ? form.status === "Aktif" : undefined,
  };

  Object.keys(payload).forEach((key) => {
    if (payload[key] === undefined) {
      delete payload[key];
    }
  });

  if (includeAliases) {
    payload.aliases = parseAliasText(form.alternativeNamesText);
  }

  return payload;
}

async function syncProductAliases(productId, form) {
  const desiredAliases = parseAliasText(form.alternativeNamesText);
  const desiredByName = new Map(desiredAliases.map((alias) => [alias.toLocaleLowerCase("tr-TR"), alias]));
  const existingAliases = form.alternativeNameItems || [];
  const existingKeys = new Set();

  await Promise.all(
    existingAliases
      .filter((item) => item?.id && !desiredByName.has(String(item.alias || "").toLocaleLowerCase("tr-TR")))
      .map((item) => catalogApi.deleteProductAlias(productId, item.id, requireSelectedMarketId())),
  );

  existingAliases.forEach((item) => {
    if (item?.alias) {
      existingKeys.add(item.alias.toLocaleLowerCase("tr-TR"));
    }
  });

  await Promise.all(
    desiredAliases
      .filter((alias) => !existingKeys.has(alias.toLocaleLowerCase("tr-TR")))
      .map((alias) => catalogApi.createProductAlias(productId, { alias }, requireSelectedMarketId())),
  );
}

export async function createCatalogProduct(form) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();

  return catalogApi.createProduct(buildProductPayload(form, { includeAliases: true }), marketId);
}

export async function updateCatalogProduct(productId, form) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();

  const product = await catalogApi.updateProduct(productId, buildProductPayload(form), marketId);
  await syncProductAliases(productId, form);
  return product;
}

export async function updateCatalogProductStatus(productId, isActive) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();

  return catalogApi.updateProduct(productId, { is_active: isActive }, marketId);
}

export async function getTemplates() {
  if (!isRealApiEnabled) return templates;
  const marketId = requireSelectedMarketId();
  const response = await templateApi.listTemplates({ limit: 100, offset: 0, include_global: true }, marketId);
  return unwrapList(response).map(mapTemplate);
}

export async function getTemplateDetail(templateId) {
  if (!isRealApiEnabled) return templates.find((template) => template.id === templateId) || templates[0];
  const marketId = requireSelectedMarketId();
  return mapTemplate(await templateApi.getTemplate(templateId, marketId));
}

export async function updateTemplateStatus(templateId, isActive) {
  if (!isRealApiEnabled) return null;
  const marketId = requireSelectedMarketId();
  return templateApi.updateTemplate(templateId, { is_active: isActive }, marketId);
}

export const dataSourceInfo = {
  isRealApiEnabled,
  demoMarketId,
};
