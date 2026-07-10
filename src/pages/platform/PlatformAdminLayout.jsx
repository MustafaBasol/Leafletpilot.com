import { getStoredPlatformAdmin } from "../../api/platformSession.js";

export function PlatformAdminLayout({ children, onLogout }) {
  const admin = getStoredPlatformAdmin();
  return (
    <div className="platform-shell">
      <aside className="platform-sidebar">
        <a className="brand" href="#/platform">
          <span className="brand-mark">LP</span>
          <span>
            <strong>Platform</strong>
            <small>{admin?.full_name || "Admin"}</small>
          </span>
        </a>
        <nav>
          <a href="#/platform">Genel Bakış</a>
          <a href="#/platform/signup-requests">Başvurular</a>
          <a href="#/platform/markets">Marketler</a>
        </nav>
        <button className="sidebar-logout" onClick={onLogout}>Çıkış</button>
      </aside>
      <main className="platform-main">{children}</main>
    </div>
  );
}
