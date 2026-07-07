export const navGroups = [
  {
    label: "Operasyon",
    items: [
      { label: "Dashboard", path: "/", icon: "chart" },
      { label: "Kampanyalar", path: "/campaigns", icon: "file" },
      { label: "Yeni Kampanya", path: "/campaigns/new", icon: "plus", mutationOnly: true },
    ],
  },
  {
    label: "Katalog",
    items: [
      { label: "Ürün Kataloğu", path: "/products", icon: "box" },
      { label: "Kategoriler", path: "/categories", icon: "file" },
      { label: "Markalar", path: "/brands", icon: "check" },
    ],
  },
  {
    label: "Tasarım",
    items: [
      { label: "Şablonlar", path: "/templates", icon: "file" },
      { label: "Dosyalar", path: "/files", icon: "file" },
    ],
  },
  {
    label: "Yönetim",
    items: [
      { label: "Marketler", path: "/markets", icon: "store" },
      { label: "Ekip", path: "/team", icon: "settings", adminOnly: true },
      { label: "Bot Bağlantıları", path: "/bot-connections", icon: "bot" },
      { label: "Raporlar", path: "/reports", icon: "chart" },
      { label: "Ayarlar", path: "/settings", icon: "settings" },
    ],
  },
];

export const pageMeta = {
  "/campaigns": {
    title: "Kampanyalar",
    description: "Kampanya listesi, filtreler ve çıktı aksiyonları.",
    action: "Yeni Kampanya Oluştur",
    actionHref: "#/campaigns/new",
  },
  "/campaigns/new": {
    title: "Yeni Kampanya",
    description: "Bilgiler, ürün listesi, eşleştirme, şablon, önizleme ve çıktı adımları.",
    action: "Taslak Oluştur",
    actionHref: "#/campaigns/new",
  },
  "/products": {
    title: "Ürün Kataloğu",
    description: "Onaylı ürün veritabanı, arama, filtreleme ve ürün görsel yönetimi.",
    action: "Ürün Ekle",
    actionHref: "#/products",
  },
  "/categories": {
    title: "Kategoriler",
    description: "Ürün kategori ağacı ve katalog düzeni.",
    action: "Kategori Ekle",
    actionHref: "#/categories",
  },
  "/brands": {
    title: "Markalar",
    description: "Marka kayıtları, alternatif yazımlar ve katalog ilişkileri.",
    action: "Marka Ekle",
    actionHref: "#/brands",
  },
  "/templates": {
    title: "Şablonlar",
    description: "Broşür şablonları, desteklenen formatlar ve varsayılan seçimler.",
    action: "Şablon Ekle",
    actionHref: "#/templates",
  },
  "/markets": {
    title: "Marketler",
    description: "Market profilleri, şube bilgileri, varsayılan şablon ve marka ayarları.",
    action: "Market Ekle",
    actionHref: "#/markets",
  },
  "/team": {
    title: "Ekip",
    description: "Market üyeleri, roller ve davet bağlantıları.",
    action: "Davet Oluştur",
    actionHref: "#/team",
  },
  "/bot-connections": {
    title: "Bot Bağlantıları",
    description: "Telegram ve WhatsApp bağlantı durumu, webhook sağlığı ve test mesajları.",
    action: "Test Mesajı Gönder",
    actionHref: "#/bot-connections",
  },
  "/files": {
    title: "Dosyalar",
    description: "PDF, PNG ve sosyal medya çıktıları için dosya merkezi.",
    action: "Dosyaları Gör",
    actionHref: "#/files",
  },
  "/reports": {
    title: "Raporlar",
    description: "Kampanya performansı, eşleşme oranları ve çıktı üretim istatistikleri.",
    action: "Rapor Oluştur",
    actionHref: "#/reports",
  },
  "/settings": {
    title: "Ayarlar",
    description: "Market, dil, para birimi ve çıktı tercihleri.",
    action: "Kaydet",
    actionHref: "#/settings",
  },
};

export function getPageTitle(path) {
  if (path === "/login") return "Giriş";
  if (path.startsWith("/campaigns/") && path !== "/campaigns/new") return "Kampanya Detayı";
  if (path.startsWith("/templates/")) return "Şablon Detayı";
  return path === "/" ? "Dashboard" : (pageMeta[path] || pageMeta["/campaigns"]).title;
}
