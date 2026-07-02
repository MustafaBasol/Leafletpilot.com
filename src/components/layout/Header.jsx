import { Button, Icon } from "../ui/index.js";

export function Header({ pageTitle, onLogout }) {
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
        <Button variant="secondary" href="#/products">
          Ürün Ekle
        </Button>
        <Button variant="primary" href="#/campaigns/new">
          Yeni Kampanya
        </Button>
        <Button className="icon-button" aria-label="Çıkış yap" onClick={onLogout}>
          <Icon name="logout" />
        </Button>
      </div>
    </header>
  );
}
