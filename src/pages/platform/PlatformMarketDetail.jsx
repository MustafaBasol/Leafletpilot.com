import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card } from "../../components/ui/index.js";

export function PlatformMarketDetail({ id }) {
  const [market, setMarket] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setMarket(await platformApi.getMarket(id));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function setLifecycle(lifecycle_status) {
    const message = lifecycle_status === "archived" ? "Market arşivlensin mi?" : `Lifecycle ${lifecycle_status} yapılsın mı?`;
    if (!window.confirm(message)) return;
    await platformApi.updateMarketLifecycle(id, { lifecycle_status, confirm_archive: lifecycle_status === "archived" });
    await load();
  }

  if (!market) return <p className="inline-result">Yükleniyor...</p>;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{market.name}</h2>
          <p>{market.slug}</p>
        </div>
        <Badge>{market.lifecycle_status}</Badge>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="dashboard-grid">
        <Card title="Operasyon" className="span-6">
          <dl className="detail-list">
            <div><dt>Deneme bitişi</dt><dd>{market.trial_ends_at ? new Date(market.trial_ends_at).toLocaleDateString("tr-TR") : "-"}</dd></div>
            <div><dt>Onboarding</dt><dd>{market.onboarding_status} · adım {market.onboarding_step}</dd></div>
            <div><dt>Üye</dt><dd>{market.member_count}</dd></div>
            <div><dt>Ürün</dt><dd>{market.product_count}</dd></div>
            <div><dt>Kampanya</dt><dd>{market.campaign_count}</dd></div>
          </dl>
          <div className="page-actions">
            <Button onClick={() => setLifecycle("active")}>Aktifleştir</Button>
            <Button variant="danger" onClick={() => setLifecycle("suspended")}>Askıya Al</Button>
            <Button variant="danger" onClick={() => setLifecycle("archived")}>Arşivle</Button>
          </div>
        </Card>
        <Card title="Profil" className="span-6">
          <dl className="detail-list">
            <div><dt>Yasal ad</dt><dd>{market.legal_name || "-"}</dd></div>
            <div><dt>Konum</dt><dd>{[market.city, market.country_code].filter(Boolean).join(", ")}</dd></div>
            <div><dt>Dil / Para</dt><dd>{market.language} / {market.currency}</dd></div>
            <div><dt>Zaman dilimi</dt><dd>{market.timezone}</dd></div>
            <div><dt>İletişim</dt><dd>{market.contact_email || "-"} {market.contact_phone || ""}</dd></div>
          </dl>
        </Card>
      </section>
    </>
  );
}
