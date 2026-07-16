import { canMutateCampaigns, canMutateCatalog } from "../../api/authSession.js";
import { Button, Icon } from "../ui/index.js";

export function Header({ pageTitle, onLogout, sessionVersion }) {
  void sessionVersion;
  const showCatalogAction = canMutateCatalog();
  const showCampaignAction = canMutateCampaigns();

  return (
    <header className="top-header">
      <div>
        <p className="header-kicker">Operasyon Paneli</p>
        <h1>{pageTitle}</h1>
      </div>
      <div className="header-actions">
        <div className="search-box">
          <Icon name="search" />
          <input aria-label="Ara" placeholder="Kampanya, ürün veya market ara" />
        </div>
        {showCatalogAction && (
          <Button variant="secondary" href="#/products?action=create-private" onClick={() => {
            if (window.location.hash === "#/products?action=create-private") window.dispatchEvent(new Event("leafletpilot:catalog-create"));
          }}>
            Ürün Ekle
          </Button>
        )}
        {showCampaignAction && (
          <Button variant="primary" href="#/campaigns/new">
            Yeni Kampanya
          </Button>
        )}
        <Button className="icon-button" aria-label="Çıkış yap" onClick={onLogout}>
          <Icon name="logout" />
        </Button>
      </div>
    </header>
  );
}
