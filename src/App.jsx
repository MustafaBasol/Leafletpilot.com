import { useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout.jsx";
import { BotConnections } from "./pages/BotConnections.jsx";
import { AcceptInvitation } from "./pages/AcceptInvitation.jsx";
import { CampaignDetail } from "./pages/CampaignDetail.jsx";
import { Categories } from "./pages/Categories.jsx";
import { Campaigns } from "./pages/Campaigns.jsx";
import { Dashboard } from "./pages/Dashboard.jsx";
import { Landing } from "./pages/Landing.jsx";
import { Login } from "./pages/Login.jsx";
import { NewCampaign } from "./pages/NewCampaign.jsx";
import { Onboarding } from "./pages/Onboarding.jsx";
import { PlaceholderPage } from "./pages/PlaceholderPage.jsx";
import { ProductCatalog } from "./pages/ProductCatalog.jsx";
import { MarketCatalog } from "./pages/MarketCatalog.jsx";
import { Settings } from "./pages/Settings.jsx";
import { Start } from "./pages/Start.jsx";
import { TemplateDetail } from "./pages/TemplateDetail.jsx";
import { Templates } from "./pages/Templates.jsx";
import { Team } from "./pages/Team.jsx";
import { PlatformAdminLayout } from "./pages/platform/PlatformAdminLayout.jsx";
import { PlatformLogin } from "./pages/platform/PlatformLogin.jsx";
import { PlatformMarketDetail } from "./pages/platform/PlatformMarketDetail.jsx";
import { PlatformMarketList } from "./pages/platform/PlatformMarketList.jsx";
import { PlatformOverview } from "./pages/platform/PlatformOverview.jsx";
import { SignupRequestDetail } from "./pages/platform/SignupRequestDetail.jsx";
import { SignupRequestList } from "./pages/platform/SignupRequestList.jsx";
import { PlatformCatalog } from "./pages/platform/PlatformCatalog.jsx";
import { PlatformTemplates } from "./pages/platform/PlatformTemplates.jsx";
import { getPageTitle, pageMeta } from "./routes/routes.js";
import { canAccessPilotPath } from "./routes/capabilities.js";
import { getMe, login as loginWithApi } from "./api/authApi.js";
import { clearAuthSession, hasStoredAuthSession, saveAuthSession, selectedMarketNeedsOnboarding } from "./api/authSession.js";
import { isRealApiEnabled } from "./api/config.js";
import { clearPlatformSession, hasPlatformSession } from "./api/platformSession.js";

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

function Page({ path, sessionVersion }) {
  void sessionVersion;
  const [pathname, search = ""] = path.split("?");
  const action = new URLSearchParams(search).get("action") || "";
  if (!canAccessPilotPath(pathname)) return <Dashboard />;
  if (pathname === "/dashboard") return <Dashboard />;
  if (pathname === "/campaigns") return <Campaigns />;
  if (pathname === "/campaigns/new") return <NewCampaign />;
  if (pathname.startsWith("/campaigns/")) return <CampaignDetail campaignId={pathname.replace("/campaigns/", "")} />;
  if (pathname === "/products") return <MarketCatalog action={action} />;
  if (path === "/categories") return <Categories />;
  if (path === "/templates") return <Templates />;
  if (path.startsWith("/templates/")) return <TemplateDetail templateId={path.replace("/templates/", "")} />;
  if (path === "/bot-connections") return <BotConnections />;
  if (path === "/settings") return <Settings />;
  if (path === "/team") return <Team />;
  if (path === "/onboarding") return <Onboarding />;
  if (pageMeta[pathname]) return <PlaceholderPage path={pathname} />;
  return <PlaceholderPage path="/campaigns" />;
}

export function App() {
  const path = useHashPath();
  const [isAuthenticated, setAuthenticated] = useState(() =>
    isRealApiEnabled ? hasStoredAuthSession() : localStorage.getItem(AUTH_KEY) === "true",
  );
  const [isCheckingSession, setCheckingSession] = useState(() => isRealApiEnabled && hasStoredAuthSession());
  const [authError, setAuthError] = useState("");
  const [sessionVersion, setSessionVersion] = useState(0);
  const [isPlatformAuthenticated, setPlatformAuthenticated] = useState(() => hasPlatformSession());

  useEffect(() => {
    const handleMarketChanged = () => setSessionVersion((version) => version + 1);
    window.addEventListener("leafletpilot:market-changed", handleMarketChanged);
    return () => window.removeEventListener("leafletpilot:market-changed", handleMarketChanged);
  }, []);

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
          setSessionVersion((version) => version + 1);
          setAuthenticated(true);
          setAuthError("");
        }
      } catch {
        clearAuthSession();
        if (isMounted) {
          setAuthenticated(false);
          setAuthError("Oturum süresi doldu. Lütfen tekrar giriş yapın.");
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
      window.location.hash = "#/dashboard";
      return;
    }

    const session = await loginWithApi(email, password);
    saveAuthSession(session);
    setSessionVersion((version) => version + 1);
    setAuthenticated(true);
    setAuthError("");
    window.location.hash = "#/dashboard";
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

  function platformLogout() {
    clearPlatformSession();
    setPlatformAuthenticated(false);
    window.location.hash = "#/platform/login";
  }

  function handleSessionUpdated() {
    setSessionVersion((version) => version + 1);
    setAuthenticated(
      isRealApiEnabled ? hasStoredAuthSession() : localStorage.getItem(AUTH_KEY) === "true",
    );
    setAuthError("");
  }

  if (isCheckingSession) {
    return <Landing />;
  }

  if (path === "/") {
    return <Landing />;
  }

  if (path === "/start") {
    return <Start />;
  }

  if (path.startsWith("/platform")) {
    if (path === "/platform/login") {
      return <PlatformLogin onLogin={() => setPlatformAuthenticated(true)} />;
    }
    if (!isPlatformAuthenticated) {
      window.location.hash = "#/platform/login";
      return <PlatformLogin onLogin={() => setPlatformAuthenticated(true)} />;
    }
    let platformPage = <PlatformOverview />;
    if (path === "/platform") platformPage = <PlatformOverview />;
    else if (path === "/platform/signup-requests") platformPage = <SignupRequestList />;
    else if (path.startsWith("/platform/signup-requests/")) platformPage = <SignupRequestDetail id={path.replace("/platform/signup-requests/", "")} />;
    else if (path === "/platform/markets") platformPage = <PlatformMarketList />;
    else if (path === "/platform/catalog") platformPage = <PlatformCatalog />;
    else if (path === "/platform/templates") platformPage = <PlatformTemplates />;
    else if (path.startsWith("/platform/markets/")) platformPage = <PlatformMarketDetail id={path.replace("/platform/markets/", "")} />;
    return <PlatformAdminLayout onLogout={platformLogout}>{platformPage}</PlatformAdminLayout>;
  }

  if (path === "/login") {
    return <Login onLogin={login} initialError={authError} />;
  }

  if (path.startsWith("/accept-invitation") || path.startsWith("/invite/")) {
    return (
      <AcceptInvitation
        path={path}
        isAuthenticated={isAuthenticated}
        onSessionUpdated={handleSessionUpdated}
      />
    );
  }

  if (!isAuthenticated) {
    window.location.hash = "#/login";
    return <Login onLogin={login} initialError={authError} />;
  }

  if (selectedMarketNeedsOnboarding() && path !== "/onboarding") {
    window.location.hash = "#/onboarding";
    return null;
  }

  return (
    <AppLayout currentPath={path} pageTitle={getPageTitle(path.split("?")[0])} onLogout={logout} sessionVersion={sessionVersion}>
      <Page path={path} sessionVersion={sessionVersion} key={`${path}:${sessionVersion}`} />
    </AppLayout>
  );
}
