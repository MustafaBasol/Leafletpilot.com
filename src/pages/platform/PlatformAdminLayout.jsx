import { getStoredPlatformAdmin } from "../../api/platformSession.js";
import { t } from "./platformI18n.js";

export function PlatformAdminLayout({ children, onLogout }) {
  const admin = getStoredPlatformAdmin();
  return (
    <div className="platform-shell">
      <aside className="platform-sidebar">
        <a className="brand" href="#/platform">
          <img className="brand-mark" src="/brand/mark-white.png" alt="LeafletPilot" width="40" height="40" />
          <span>
            <strong>Platform</strong>
            <small>{admin?.full_name || "Admin"}</small>
          </span>
        </a>
        <nav>
          <a href="#/platform">{t("overview")}</a>
          <a href="#/platform/signup-requests">{t("signupRequests")}</a>
          <a href="#/platform/markets">{t("markets")}</a>
          <a href="#/platform/catalog">Global catalog</a>
          <a href="#/platform/templates">Templates</a>
        </nav>
        <button className="sidebar-logout" onClick={onLogout}>{t("logout")}</button>
      </aside>
      <main className="platform-main">{children}</main>
    </div>
  );
}
