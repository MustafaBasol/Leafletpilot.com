import {
  activities,
  campaigns,
  market,
  metrics,
  missingProducts,
  products,
  waitingApprovals,
} from "../data/mockData.js";
import { Badge, Button, Card, Icon, StatusBadge, Table } from "../components/ui/index.js";

function metricIconName(tone) {
  if (tone === "danger") return "alert";
  if (tone === "success") return "check";
  return "file";
}

function MetricCards() {
  return (
    <div className="metric-grid">
      {metrics.map((metric) => (
        <section className={`metric-card metric-${metric.tone}`} key={metric.label}>
          <div className="metric-top">
            <span>
              <Icon name={metricIconName(metric.tone)} />
            </span>
            <Badge tone={metric.tone}>{metric.tone === "warning" ? "Aksiyon gerekli" : "Güncel"}</Badge>
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

function RecentCampaigns() {
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
      <Table columns={["Kampanya", "Market", "Durum", "Ürün", "Tarih", "Aksiyon"]}>
        {campaigns.map((campaign) => (
          <tr key={`${campaign.name}-${campaign.date}`}>
            <td>
              <strong>{campaign.name}</strong>
              <small>{campaign.channel} üzerinden alındı</small>
            </td>
            <td>{campaign.market}</td>
            <td>
              <StatusBadge status={campaign.status} />
            </td>
            <td>{campaign.productCount} ürün</td>
            <td>{campaign.date}</td>
            <td>
              <a className="table-action" href={`#/campaigns/${campaign.id}`}>
                Detay
              </a>
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function BotStatus() {
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
      <div className="card-actions">
        <Button variant="primary" href="#/bot-connections">
          Test mesajı gönder
        </Button>
        <Button variant="secondary" href="#/bot-connections">
          Bağlantıyı görüntüle
        </Button>
      </div>
    </Card>
  );
}

function WaitingList() {
  return (
    <Card title="Onay Bekleyenler" className="span-6">
      <div className="stack-list">
        {waitingApprovals.map((item, index) => (
          <article className="approval-row" key={item.name}>
            <div className="preview-thumb">P{index + 1}</div>
            <div>
              <strong>{item.name}</strong>
              <small>
                {item.market} · {item.waiting}
              </small>
            </div>
            <a href="#/campaigns">Aç</a>
          </article>
        ))}
      </div>
    </Card>
  );
}

function MissingList() {
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
        {missingProducts.map((product) => (
          <article className="missing-row" key={`${product.incoming}-${product.campaign}`}>
            <div>
              <strong>{product.incoming}</strong>
              <small>{product.campaign}</small>
            </div>
            <div>
              <small>Öneri</small>
              <span>{product.suggestion}</span>
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
    ["Yeni Kampanya Oluştur", "#/campaigns/new", "plus"],
    ["Ürün Kataloğuna Git", "#/products", "box"],
    ["Excel İçe Aktar", "#/products", "file"],
    ["Yeni Şablon Ekle", "#/templates", "file"],
    ["Bot Bağlantısını Kontrol Et", "#/bot-connections", "bot"],
    ["Market Ayarları", "#/markets", "store"],
  ];

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
    </Card>
  );
}

export function Dashboard() {
  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Dashboard</h2>
          <p>Kampanyalarınızı, ürün eşleşmelerini ve çıktı durumlarını tek ekrandan takip edin.</p>
        </div>
        <div className="page-actions">
          <Button variant="secondary" href="#/bot-connections">
            Bot Testi
          </Button>
          <Button variant="primary" href="#/campaigns/new">
            Yeni Kampanya
          </Button>
        </div>
      </section>
      <MetricCards />
      <section className="dashboard-grid">
        <RecentCampaigns />
        <BotStatus />
        <WaitingList />
        <MissingList />
        <QuickActions />
        <ActivityHistory />
      </section>
    </>
  );
}
