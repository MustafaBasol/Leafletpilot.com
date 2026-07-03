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

function mapProduct(product) {
  return {
    id: product.id,
    name: product.name,
    shortName: product.short_name || product.name,
    price: "",
    brand: product.brand_id ? "API Marka" : "-",
    category: product.category_id ? "API Kategori" : "-",
    barcode: product.barcode || "-",
    packageSize: product.package_size || "",
    packageType: product.package_type || "",
    alternativeNames: (product.aliases || []).map((alias) => alias.alias),
    status: product.is_active ? "Aktif" : "Pasif",
    imageStatus: product.images?.length ? "Var" : "Görsel yok",
    usageCount: product.usage_count || 0,
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

  const response = await catalogApi.listProducts({ limit: 100, offset: 0, include_global: true }, demoMarketId);
  return unwrapList(response).map(mapProduct);
}

export function getTemplates() {
  // TODO Phase 14: replace with backend template API when template models/routes exist.
  return templates;
}

export const dataSourceInfo = {
  isRealApiEnabled,
  demoMarketId,
};
