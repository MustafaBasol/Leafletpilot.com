import { canManageTeam, canMutateCampaigns, getSelectedMarket, getStoredMarkets, setSelectedMarketId } from "../../api/authSession.js";
import { isRealApiEnabled } from "../../api/config.js";
import { market } from "../../data/mockData.js";
import { navGroups } from "../../routes/routes.js";
import { Badge, Icon } from "../ui/index.js";

const roleLabels = {
  market_admin: "Yönetici",
  market_staff: "Personel",
  viewer: "Görüntüleyici",
};

function isActivePath(currentPath, itemPath) {
  return currentPath === itemPath || (itemPath !== "/" && currentPath.startsWith(itemPath));
}

function roleLabel(role) {
  return roleLabels[role] || role || "Market";
}

export function Sidebar({ currentPath, sessionVersion }) {
  void sessionVersion;
  const selectedMarket = getSelectedMarket();
  const markets = getStoredMarkets();
  const displayMarket = isRealApiEnabled && selectedMarket ? selectedMarket : market;
  const visibleGroups = navGroups.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.adminOnly && !canManageTeam()) return false;
      if (item.mutationOnly && !canMutateCampaigns()) return false;
      return true;
    }),
  }));

  function handleMarketChange(event) {
    setSelectedMarketId(event.target.value);
  }

  return (
    <aside className="sidebar">
      <a className="brand" href="#/">
        <span className="brand-mark">LP</span>
        <span>
          <strong>LeafletPilot</strong>
          <small>AI Brochure Automation</small>
        </span>
      </a>
      <nav>
        {visibleGroups.map((group) => (
          <div className="nav-group" key={group.label}>
            <p>{group.label}</p>
            {group.items.map((item) => (
              <a
                className={`nav-link ${isActivePath(currentPath, item.path) ? "is-active" : ""}`.trim()}
                href={`#${item.path}`}
                key={item.path}
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </a>
            ))}
          </div>
        ))}
      </nav>
      <div className="market-switcher" aria-label="Seçili market">
        <div className="market-switcher-top">
          <span className="market-avatar">{displayMarket.name.slice(0, 1)}</span>
          <span>
            <strong>{displayMarket.name}</strong>
            <small>{isRealApiEnabled ? "Seçili market" : market.location}</small>
          </span>
        </div>
        <Badge tone="primary">{roleLabel(selectedMarket?.role)}</Badge>
        {isRealApiEnabled && markets.length > 1 ? (
          <label className="market-select-label">
            <span>Market değiştir</span>
            <select value={displayMarket.id} onChange={handleMarketChange} aria-label="Market seç">
              {markets.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name} - {roleLabel(item.role)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
    </aside>
  );
}
