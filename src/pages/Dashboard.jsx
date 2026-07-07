import { useEffect, useMemo, useState } from "react";
import { canManageTemplates, canMutateCampaigns, canMutateCatalog, getSelectedMarket } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import {
  activities,
  campaigns as mockCampaigns,
  market,
  metrics,
  missingProducts,
  products,
  waitingApprovals,
} from "../data/mockData.js";
import { getCampaigns } from "../data/dataSource.js";
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
            <span>
              <Icon name={metricIconName(metric.tone)} />
            </span>
            <Badge tone={metric.tone}>{metric.badge || "Güncel"}</Badge>
          </div>
          <p>{metric.label}</p>
          <strong>{metric.value}</strong>
          <small>{metric.helper}</small>
          <span className="metric-trend">{metric.trend}</span>
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
  if (isRealApiEnabled) {
    return (
      <Card title="Bot Bağlantı Durumu" className="span-4">
        <div className="bot-status bot-status-muted">
          <div className="bot-orb">
            <Icon name="bot" />
          </div>
          <div>
            <Badge>Yapılandırılmadı</Badge>
            <h3>Bot bağlantısı henüz yapılandırılmadı.</h3>
            <p>Telegram ve WhatsApp entegrasyonları bu fazda aktif değildir.</p>
          </div>
        </div>
        <dl className="detail-list">
          <div>
            <dt>Market</dt>
            <dd>{selectedMarket?.name || "-"}</dd>
          </div>
          <div>
            <dt>Durum</dt>
            <dd>Beklemede</dd>
          </div>
        </dl>
      </Card>
    );
  }

  return (
    <Card title="Bot Bağlantı Durumu" className="span-4">
      <div className="bot-status">
        <div className="bot-orb">
          <Icon name="bot" />
        </div>
        <div>
          <Badge tone="success">Bot aktif</Badge>
          <h3>Telegram bağlantısı çalışıyor</h3>
          <p>Son mesaj: 3 dakika önce</p>
        </div>
      </div>
      <dl className="detail-list">
        <div>
          <dt>Kanal</dt>
          <dd>Telegram</dd>
        </div>
        <div>
          <dt>Bot</dt>
          <dd>@LeafletPilotBot</dd>
        </div>
        <div>
          <dt>Webhook</dt>
          <dd>
            <Badge tone="success">Sağlıklı</Badge>
          </dd>
        </div>
        <div>
          <dt>Market</dt>
          <dd>{market.name}</dd>
        </div>
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

function QuickActions() {
  const actions = [
    canMutateCampaigns() ? ["Yeni Kampanya Oluştur", "#/campaigns/new", "plus"] : null,
    ["Ürün Kataloğuna Git", "#/products", "box"],
    canMutateCatalog() ? ["Excel İçe Aktar", "#/products", "file"] : null,
    canManageTemplates() ? ["Yeni Şablon Ekle", "#/templates", "file"] : null,
    ["Bot Bağlantısını Kontrol Et", "#/bot-connections", "bot"],
    ["Market Ayarları", "#/markets", "store"],
  ].filter(Boolean);

  return (
    <Card title="Hızlı Aksiyonlar" className="span-6">
      <div className="quick-grid">
        {actions.map(([label, href, iconName]) => (
          <a className="quick-action" href={href} key={label}>
            <Icon name={iconName} />
            <span>{label}</span>
          </a>
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
      trend: "Gerçek API verisi",
      tone: "success",
    },
    {
      label: "Onay Bekleyen",
      value: approvalCount,
      helper: "Onay veya revizyon durumundaki kampanyalar",
      trend: "Seçili market",
      tone: approvalCount ? "warning" : "success",
      badge: approvalCount ? "Aksiyon gerekli" : "Güncel",
    },
    {
      label: "Eksik Ürün",
      value: missingCount,
      helper: "Kampanyalardaki eksik ürün toplamı",
      trend: "Seçili market",
      tone: missingCount ? "danger" : "success",
      badge: missingCount ? "Aksiyon gerekli" : "Güncel",
    },
    {
      label: "Üretilen Dosya",
      value: "-",
      helper: "Bu metrik için gerçek veri henüz yok",
      trend: "Sahte veri gösterilmiyor",
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
          {canMutateCampaigns() ? (
            <Button variant="primary" href="#/campaigns/new">
              Yeni Kampanya
            </Button>
          ) : null}
        </div>
      </section>
      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}
      <MetricCards items={dashboardMetrics} />
      <section className="dashboard-grid">
        <RecentCampaigns items={campaignItems} isLoading={isLoading} />
        <BotStatus selectedMarket={selectedMarket} />
        <WaitingList items={waitingItems} />
        <MissingList items={missingItems} />
        <QuickActions />
        <ActivityHistory />
      </section>
    </>
  );
}
