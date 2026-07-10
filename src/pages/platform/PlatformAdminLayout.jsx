import { getStoredPlatformAdmin } from "../../api/platformSession.js";
import { t } from "./platformI18n.js";

export function PlatformAdminLayout({ children, onLogout }) {
  const admin = getStoredPlatformAdmin();
  return (
    <div className="platform-shell">
      <aside className="platform-sidebar">
        <a className="brand" href="#/platform/signup-requests">
          <span className="brand-mark">LP</span>
          <span>
            <strong>Platform</strong>
            <small>{admin?.full_name || "Admin"}</small>
          </span>
        </a>
        <nav>
          <a href="#/platform/signup-requests">{t("signupRequests")}</a>
          <a href="#/platform/markets">{t("markets")}</a>
        </nav>
        <button className="sidebar-logout" onClick={onLogout}>Çıkış</button>
      </aside>
      <main className="platform-main">{children}</main>
    </div>
  );
}
