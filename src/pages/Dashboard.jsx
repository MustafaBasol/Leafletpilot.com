import { useEffect, useMemo, useState } from "react";
import { canMutateCatalog, getSelectedMarket } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import {
  activities,
  campaigns as mockCampaigns,
  metrics,
  missingProducts,
  products,
  waitingApprovals,
} from "../data/mockData.js";
import { getCampaigns, getTelegramStatus } from "../data/dataSource.js";
import { Badge, Button, Card, Icon, StatusBadge, Table } from "../components/ui/index.js";

function metricIconName(tone) {
  if (tone === "danger") return "alert";
  if (tone === "success") return "check";
  return "file";
}

function MetricCards({ items }) {
  return (
    <div className="metric-grid">
      {items.map((metric) => (
        <section className={`metric-card metric-${metric.tone}`} key={metric.label}>
          <div className="metric-top">
            <span className="metric-icon">
              <Icon name={metricIconName(metric.tone)} />
            </span>
            <Badge tone={metric.tone}>{metric.badge || "Güncel"}</Badge>
          </div>
          <p>{metric.label}</p>
          <strong>{metric.value}</strong>
          <small>{metric.helper}</small>
          {metric.trend ? <span className="metric-trend">{metric.trend}</span> : null}
        </section>
      ))}
    </div>
  );
}

function RecentCampaigns({ items, isLoading }) {
  return (
    <Card
      title="Son Kampanyalar"
      action={
        <a className="subtle-link" href="#/campaigns">
          Tümünü gör
        </a>
      }
      className="span-8"
    >
      {isLoading ? <p className="inline-result">Kampanyalar yükleniyor...</p> : null}
      {!isLoading && items.length === 0 ? <p className="catalog-empty">Bu markette kampanya yok.</p> : null}
      {!isLoading && items.length > 0 ? (
        <Table columns={["Kampanya", "Market", "Durum", "Ürün", "Tarih", "Aksiyon"]}>
          {items.slice(0, 5).map((campaign) => (
            <tr key={campaign.id || `${campaign.name}-${campaign.date}`}>
              <td>
                <strong>{campaign.name}</strong>
                <small>{campaign.channel} üzerinden alındı</small>
              </td>
              <td>{campaign.market}</td>
              <td>
                <StatusBadge status={campaign.status} />
              </td>
              <td>{campaign.productCount} ürün</td>
              <td>{campaign.date || campaign.createdAt}</td>
              <td>
                <a className="table-action" href={`#/campaigns/${campaign.id}`}>
                  Detay
                </a>
              </td>
            </tr>
          ))}
        </Table>
      ) : null}
    </Card>
  );
}

function BotStatus({ selectedMarket }) {
  const [botStatus, setBotStatus] = useState(null);
  const [botStatusError, setBotStatusError] = useState("");

  useEffect(() => {
    let isMounted = true;
    setBotStatusError("");
    getTelegramStatus()
      .then((result) => {
        if (isMounted) setBotStatus(result);
      })
      .catch((error) => {
        if (isMounted) setBotStatusError(error.message || "Bot bağlantı durumu yüklenemedi.");
      });
    return () => {
      isMounted = false;
    };
  }, [selectedMarket?.id]);

  const connected = Boolean(botStatus?.connected);

  return (
    <Card title="Bot Bağlantı Durumu" className="span-4">
      <div className={`bot-status ${connected ? "" : "bot-status-muted"}`}>
        <div className="bot-orb">
          <Icon name="bot" />
        </div>
        <div>
          <Badge tone={connected ? "success" : undefined}>{connected ? "Bağlı" : "Yapılandırılmadı"}</Badge>
          <h3>{connected ? "Telegram bağlantısı aktif" : "Bot bağlantısı henüz yapılandırılmadı."}</h3>
          <p>
            {connected
              ? `${botStatus.username ? `@${botStatus.username}` : "Bir ekip üyesi"} Telegram hesabını bağladı.`
              : "Ekip üyelerinizden biri Telegram botunu bağladığında bağlantı durumu burada görünür."}
          </p>
        </div>
      </div>
      {botStatusError ? <p className="inline-result inline-result-warning">{botStatusError}</p> : null}
      <dl className="detail-list">
        <div>
          <dt>Market</dt>
          <dd>{selectedMarket?.name || "-"}</dd>
        </div>
        <div>
          <dt>Durum</dt>
          <dd>{connected ? "Aktif" : "Beklemede"}</dd>
        </div>
        {connected ? (
          <div>
            <dt>Bağlı hesap sayısı</dt>
            <dd>{botStatus.connected_member_count}</dd>
          </div>
        ) : null}
      </dl>
    </Card>
  );
}

function WaitingList({ items }) {
  return (
    <Card title="Onay Bekleyenler" className="span-6">
      <div className="stack-list">
        {items.length === 0 ? <p className="catalog-empty">Onay bekleyen kampanya yok.</p> : null}
        {items.map((item, index) => (
          <article className="approval-row" key={item.id || item.name}>
            <div className="preview-thumb">P{index + 1}</div>
            <div>
              <strong>{item.name}</strong>
              <small>{item.market} · {item.waiting || item.status}</small>
            </div>
            <a href={item.id ? `#/campaigns/${item.id}` : "#/campaigns"}>Aç</a>
          </article>
        ))}
      </div>
    </Card>
  );
}

function MissingList({ items }) {
  return (
    <Card
      title="Eksik Ürünler"
      action={
        <a className="subtle-link" href="#/products">
          Kataloğa git
        </a>
      }
      className="span-6"
    >
      <div className="stack-list">
        {items.length === 0 ? <p className="catalog-empty">Eksik ürün görünmüyor.</p> : null}
        {items.map((product) => (
          <article className="missing-row" key={`${product.incoming}-${product.campaign}`}>
            <div>
              <strong>{product.incoming}</strong>
              <small>{product.campaign}</small>
            </div>
            <div>
              <small>Öneri</small>
              <span>{product.suggestion || "-"}</span>
            </div>
            <a href="#/products">Eşleştir</a>
          </article>
        ))}
      </div>
    </Card>
  );
}

function ActivityHistory() {
  return (
    <Card title="Son İşlem Geçmişi" className="span-6">
      {isRealApiEnabled ? (
        <p className="catalog-empty">İşlem geçmişi için gerçek veri bu fazda hazır değil.</p>
      ) : (
        <>
          <ol className="activity-list">
            {activities.map((activity) => (
              <li key={activity}>{activity}</li>
            ))}
          </ol>
          <div className="product-strip">
            {products.slice(0, 4).map((product) => (
              <span key={product.name}>
                <strong>{product.name}</strong>
                {product.price}
              </span>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function buildRealMetrics(campaignItems) {
  const missingCount = campaignItems.reduce((total, campaign) => total + Number(campaign.missingCount || 0), 0);
  const approvalCount = campaignItems.filter((campaign) => ["Onay bekliyor", "Revizyon istendi"].includes(campaign.status)).length;
  return [
    {
      label: "Toplam Kampanya",
      value: campaignItems.length,
      helper: "Seçili marketteki kampanya sayısı",
      trend: "",
      tone: "success",
    },
    {
      label: "Onay Bekleyen",
      value: approvalCount,
      helper: "Onay veya revizyon durumundaki kampanyalar",
      trend: "",
      tone: approvalCount ? "warning" : "success",
      badge: approvalCount ? "Aksiyon gerekli" : "Güncel",
    },
    {
      label: "Eksik Ürün",
      value: missingCount,
      helper: "Kampanyalardaki eksik ürün toplamı",
      trend: "",
      tone: missingCount ? "danger" : "success",
      badge: missingCount ? "Aksiyon gerekli" : "Güncel",
    },
    {
      label: "Üretilen Dosya",
      value: "-",
      helper: "Kampanyalarınız için henüz üretilmiş dosya yok",
      trend: "",
      tone: "neutral",
      badge: "Hazır değil",
    },
  ];
}

export function Dashboard() {
  const [campaignItems, setCampaignItems] = useState(() => (isRealApiEnabled ? [] : mockCampaigns));
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const selectedMarket = getSelectedMarket();

  useEffect(() => {
    let isMounted = true;

    async function loadDashboard() {
      if (!isRealApiEnabled) return;
      setIsLoading(true);
      setCampaignItems([]);
      setApiError("");
      try {
        const items = await getCampaigns();
        if (isMounted) setCampaignItems(items);
      } catch (error) {
        if (isMounted) setApiError(error.message || "Dashboard verisi yüklenemedi.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadDashboard();

    return () => {
      isMounted = false;
    };
  }, [selectedMarket?.id]);

  const dashboardMetrics = useMemo(
    () => (isRealApiEnabled ? buildRealMetrics(campaignItems) : metrics),
    [campaignItems],
  );
  const waitingItems = isRealApiEnabled
    ? campaignItems.filter((campaign) => ["Onay bekliyor", "Revizyon istendi"].includes(campaign.status)).slice(0, 4)
    : waitingApprovals;
  const missingItems = isRealApiEnabled
    ? campaignItems
        .filter((campaign) => Number(campaign.missingCount || 0) > 0)
        .slice(0, 4)
        .map((campaign) => ({ incoming: `${campaign.missingCount} eksik ürün`, campaign: campaign.name, suggestion: "Katalog kontrolü" }))
    : missingProducts;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Dashboard</h2>
          <p>Kampanyalarınızı, ürün eşleşmelerini ve çıktı durumlarını tek ekrandan takip edin.</p>
        </div>
        <div className="page-actions">
          {!isRealApiEnabled ? (
            <Button variant="secondary" href="#/bot-connections">
              Bot Testi
            </Button>
          ) : null}
          {canMutateCatalog() ? (
            <Button variant="secondary" href="#/products?action=create-private">
              <Icon name="box" /> Ürün Ekle
            </Button>
          ) : null}
          {canMutateCatalog() ? (
            <Button variant="secondary" href="#/products">
              <Icon name="alert" /> Eksik Ürünleri Çöz
            </Button>
          ) : null}
          <Button variant="secondary" href="#/campaigns">
            <Icon name="file" /> Kampanyaları Gör
          </Button>
        </div>
      </section>
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      <MetricCards items={dashboardMetrics} />
      <section className="dashboard-grid">
        <RecentCampaigns items={campaignItems} isLoading={isLoading} />
        <BotStatus selectedMarket={selectedMarket} />
        <WaitingList items={waitingItems} />
        <MissingList items={missingItems} />
        <ActivityHistory />
      </section>
    </>
  );
}
