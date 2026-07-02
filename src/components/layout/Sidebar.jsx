import { market } from "../../data/mockData.js";
import { Icon } from "../ui/index.js";
import { navGroups } from "../../routes/routes.js";

function isActivePath(currentPath, itemPath) {
  return currentPath === itemPath || (itemPath !== "/" && currentPath.startsWith(itemPath));
}

export function Sidebar({ currentPath }) {
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
        {navGroups.map((group) => (
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
      <div className="market-switcher">
        <span className="market-avatar">{market.name.slice(0, 1)}</span>
        <span>
          <strong>{market.name}</strong>
          <small>{market.location}</small>
        </span>
      </div>
    </aside>
  );
}
