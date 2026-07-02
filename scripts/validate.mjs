import { access, readFile } from "node:fs/promises";

const requiredFiles = [
  "index.html",
  "vite.config.js",
  "src/main.jsx",
  "src/App.jsx",
  "src/styles.css",
  "src/components/layout/AppLayout.jsx",
  "src/components/layout/Sidebar.jsx",
  "src/components/layout/Header.jsx",
  "src/components/ui/Button.jsx",
  "src/components/ui/Card.jsx",
  "src/components/ui/Checkbox.jsx",
  "src/components/ui/Badge.jsx",
  "src/components/ui/StatusBadge.jsx",
  "src/components/ui/Table.jsx",
  "src/components/ui/Input.jsx",
  "src/components/ui/EmptyState.jsx",
  "src/components/ui/ExportPanel.jsx",
  "src/components/ui/Modal.jsx",
  "src/components/ui/Stepper.jsx",
  "src/components/ui/FilterBar.jsx",
  "src/components/ui/PageHeader.jsx",
  "src/components/ui/FileCard.jsx",
  "src/components/ui/PreviewFrame.jsx",
  "src/components/ui/ProviderConnectionCard.jsx",
  "src/components/ui/MessageFlowPreview.jsx",
  "src/components/ui/ProductThumbnail.jsx",
  "src/components/ui/MissingProductModal.jsx",
  "src/components/ui/TemplateCard.jsx",
  "src/data/mockData.js",
  "src/pages/Dashboard.jsx",
  "src/pages/Campaigns.jsx",
  "src/pages/CampaignDetail.jsx",
  "src/pages/NewCampaign.jsx",
  "src/pages/ProductCatalog.jsx",
  "src/pages/Templates.jsx",
  "src/pages/TemplateDetail.jsx",
  "src/pages/BotConnections.jsx",
  "src/pages/Settings.jsx",
  "src/pages/Login.jsx",
  "src/pages/PlaceholderPage.jsx",
  "src/routes/routes.js",
];

for (const file of requiredFiles) {
  await access(file);
}

const html = await readFile("index.html", "utf8");
const main = await readFile("src/main.jsx", "utf8");
const app = await readFile("src/App.jsx", "utf8");

if (!html.includes('id="app"')) {
  throw new Error("index.html must include #app root.");
}

if (!html.includes('src="/src/main.jsx"')) {
  throw new Error("index.html must load the React entry point.");
}

if (!main.includes("createRoot")) {
  throw new Error("src/main.jsx must initialize React.");
}

if (!app.includes("AppLayout") || !app.includes("Dashboard")) {
  throw new Error("src/App.jsx must compose the layout and dashboard route.");
}

if (!app.includes("Campaigns") || !app.includes("CampaignDetail") || !app.includes("ProductCatalog")) {
  throw new Error("src/App.jsx must route Phase 2 campaign and product screens.");
}

if (!app.includes("Templates") || !app.includes("TemplateDetail") || !app.includes("BotConnections") || !app.includes("Login")) {
  throw new Error("src/App.jsx must route Phase 3 template, bot connection and login screens.");
}

const data = await readFile("src/data/mockData.js", "utf8");
if (!data.includes("campaignProducts") || !data.includes("templates") || !data.includes("messages")) {
  throw new Error("src/data/mockData.js must include reusable Phase 2 mock data.");
}

if (!data.includes("botConnections") || !data.includes("outputFormats") || !data.includes("marketSettings")) {
  throw new Error("src/data/mockData.js must include reusable Phase 3 mock data.");
}

console.log("Vite React frontend validation passed.");
