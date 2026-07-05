import { useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout.jsx";
import { BotConnections } from "./pages/BotConnections.jsx";
import { CampaignDetail } from "./pages/CampaignDetail.jsx";
import { Campaigns } from "./pages/Campaigns.jsx";
import { Dashboard } from "./pages/Dashboard.jsx";
import { Landing } from "./pages/Landing.jsx";
import { Login } from "./pages/Login.jsx";
import { NewCampaign } from "./pages/NewCampaign.jsx";
import { PlaceholderPage } from "./pages/PlaceholderPage.jsx";
import { ProductCatalog } from "./pages/ProductCatalog.jsx";
import { Settings } from "./pages/Settings.jsx";
import { TemplateDetail } from "./pages/TemplateDetail.jsx";
import { Templates } from "./pages/Templates.jsx";
import { getPageTitle, pageMeta } from "./routes/routes.js";

const AUTH_KEY = "leafletpilot_mock_auth";

function currentPath() {
  const hashPath = window.location.hash.replace(/^#/, "");
  return hashPath || "/";
}

function useHashPath() {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const handleHashChange = () => setPath(currentPath());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  return path;
}

function Page({ path }) {
  if (path === "/") return <Dashboard />;
  if (path === "/campaigns") return <Campaigns />;
  if (path === "/campaigns/new") return <NewCampaign />;
  if (path.startsWith("/campaigns/")) return <CampaignDetail campaignId={path.replace("/campaigns/", "")} />;
  if (path === "/products") return <ProductCatalog />;
  if (path === "/templates") return <Templates />;
  if (path.startsWith("/templates/")) return <TemplateDetail templateId={path.replace("/templates/", "")} />;
  if (path === "/bot-connections") return <BotConnections />;
  if (path === "/settings") return <Settings />;
  if (pageMeta[path]) return <PlaceholderPage path={path} />;
  return <PlaceholderPage path="/campaigns" />;
}

export function App() {
  const path = useHashPath();
  const [isAuthenticated, setAuthenticated] = useState(() => localStorage.getItem(AUTH_KEY) === "true");

  function login({ remember }) {
    if (remember) {
      localStorage.setItem(AUTH_KEY, "true");
    }
    setAuthenticated(true);
    window.location.hash = "#/";
  }

  function logout() {
    localStorage.removeItem(AUTH_KEY);
    setAuthenticated(false);
    window.location.hash = "#/";
  }

  if (path === "/login") {
    return <Login onLogin={login} />;
  }

  if (!isAuthenticated) {
    return <Landing />;
  }

  return (
    <AppLayout currentPath={path} pageTitle={getPageTitle(path)} onLogout={logout}>
      <Page path={path} />
    </AppLayout>
  );
}
