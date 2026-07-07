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
import { getMe, login as loginWithApi } from "./api/authApi.js";
import { clearAuthSession, hasStoredAuthSession, saveAuthSession } from "./api/authSession.js";
import { isRealApiEnabled } from "./api/config.js";

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
  const [isAuthenticated, setAuthenticated] = useState(() =>
    isRealApiEnabled ? hasStoredAuthSession() : localStorage.getItem(AUTH_KEY) === "true",
  );
  const [isCheckingSession, setCheckingSession] = useState(() => isRealApiEnabled && hasStoredAuthSession());
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function validateSession() {
      if (!isRealApiEnabled || !hasStoredAuthSession()) {
        setCheckingSession(false);
        return;
      }

      try {
        const session = await getMe();
        if (isMounted) {
          saveAuthSession(session);
          setAuthenticated(true);
          setAuthError("");
        }
      } catch {
        clearAuthSession();
        if (isMounted) {
          setAuthenticated(false);
          setAuthError("Oturum süresi doldu. Lütfen tekrar giriş yapın.");
          window.location.hash = "#/login";
        }
      } finally {
        if (isMounted) setCheckingSession(false);
      }
    }

    validateSession();

    return () => {
      isMounted = false;
    };
  }, []);

  async function login({ email, password, remember }) {
    if (!isRealApiEnabled) {
      if (remember) {
        localStorage.setItem(AUTH_KEY, "true");
      }
      setAuthenticated(true);
      window.location.hash = "#/";
      return;
    }

    const session = await loginWithApi(email, password);
    saveAuthSession(session);
    setAuthenticated(true);
    setAuthError("");
    window.location.hash = "#/";
  }

  function logout() {
    if (!isRealApiEnabled) {
      localStorage.removeItem(AUTH_KEY);
    } else {
      clearAuthSession();
    }
    setAuthenticated(false);
    window.location.hash = "#/login";
  }

  if (isCheckingSession) {
    return <Landing />;
  }

  if (path === "/login") {
    return <Login onLogin={login} initialError={authError} />;
  }

  if (!isAuthenticated) {
    if (!isRealApiEnabled && path !== "/login") {
      return <Landing />;
    }
    window.location.hash = "#/login";
    return <Login onLogin={login} initialError={authError} />;
  }

  return (
    <AppLayout currentPath={path} pageTitle={getPageTitle(path)} onLogout={logout}>
      <Page path={path} />
    </AppLayout>
  );
}
