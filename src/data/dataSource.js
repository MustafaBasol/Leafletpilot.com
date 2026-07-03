import { demoMarketId, isRealApiEnabled } from "../api/config.js";
import * as catalogApi from "../api/catalogApi.js";
import * as campaignApi from "../api/campaignApi.js";
import {
  activities,
  campaigns,
  findCampaignById,
  metrics,
  missingProducts,
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
    productCount: campaign.product_count || 0,
    missingCount: campaign.missing_count || 0,
    channel: channelLabels[campaign.channel] || campaign.channel || "Panel",
    template: campaign.template_id ? "API Şablonu" : "Şablon yok",
    createdAt: formatDate(campaign.created_at),
    updatedAt: formatUpdatedAt(campaign.updated_at),
    date: formatDate(campaign.campaign_start_date || campaign.created_at),
    files: [],
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
    alternativeNames: (product.aliases || []).map((alias) => (typeof alias === "string" ? alias : alias.alias)).filter(Boolean),
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
  if (!demoMarketId) throw new Error("Real API modu için VITE_DEMO_MARKET_ID gerekli.");

  const response = await campaignApi.listCampaigns({ limit: 50, offset: 0 }, demoMarketId);
  return unwrapList(response).map(mapCampaign);
}

export async function getCampaignDetail(id) {
  // TODO Phase 14: wire CampaignDetail once item and file panels are mapped to backend fields.
  if (!isRealApiEnabled) return findCampaignById(id);
  if (!demoMarketId) throw new Error("Real API modu için VITE_DEMO_MARKET_ID gerekli.");

  return campaignApi.getCampaign(id, demoMarketId);
}

export async function getProducts() {
  if (!isRealApiEnabled) return products;
  if (!demoMarketId) throw new Error("Real API modu için VITE_DEMO_MARKET_ID gerekli.");

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
  if (!demoMarketId) throw new Error("Real API modu için VITE_DEMO_MARKET_ID gerekli.");

  const [productsResponse, brandsResponse, categoriesResponse] = await Promise.all([
    catalogApi.listProducts({ limit: 100, offset: 0, include_global: true }, demoMarketId),
    catalogApi.listBrands({ limit: 100, offset: 0, include_global: true }, demoMarketId),
    catalogApi.listCategories({ limit: 100, offset: 0, include_global: true }, demoMarketId),
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

export function getTemplates() {
  // TODO Phase 14: replace with backend template API when template models/routes exist.
  return templates;
}

export const dataSourceInfo = {
  isRealApiEnabled,
  demoMarketId,
};
