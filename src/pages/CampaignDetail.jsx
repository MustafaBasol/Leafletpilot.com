import { useState } from "react";
import {
  campaignActivities,
  campaignProducts,
  findCampaignById,
  generatedFiles,
  messages,
} from "../data/mockData.js";
import {
  Badge,
  Button,
  Card,
  ExportPanel,
  MissingProductModal,
  PageHeader,
  PreviewFrame,
  ProductThumbnail,
  StatusBadge,
  Table,
} from "../components/ui/index.js";

function scoreTone(score) {
  if (score >= 90) return "success";
  if (score >= 75) return "warning";
  return "danger";
}

function needsAttention(status) {
  return ["Kontrol gerekli", "Bulunamadı", "BulunamadÄ±"].includes(status);
}

export function CampaignDetail({ campaignId }) {
  const campaign = findCampaignById(campaignId);
  const [rows, setRows] = useState(campaignProducts);
  const [selectedMissing, setSelectedMissing] = useState(null);
  const [notice, setNotice] = useState("");

  function resolveProduct(status) {
    setRows((currentRows) =>
      currentRows.map((row) => (row.id === selectedMissing?.id ? { ...row, status, score: Math.max(row.score, 82) } : row)),
    );
    setSelectedMissing(null);
    setNotice("Eksik ürün eşleştirmesi yerel olarak güncellendi.");
  }

  const missingRows = rows.filter((row) => needsAttention(row.status));

  return (
    <>
      <PageHeader
        title={campaign.name}
        description={`${campaign.market} · ${campaign.template} · ${campaign.channel} · ${campaign.createdAt}`}
        actions={
          <>
            <Button onClick={() => setNotice("Önizleme yeniden oluşturma simüle edildi.")}>Önizlemeyi Yeniden Oluştur</Button>
            <Button onClick={() => setNotice("Final dosyaları üretim için hazırlandı.")}>Final Dosyaları Üret</Button>
            <Button variant="primary" onClick={() => setNotice("Dosyalar kullanıcıya gönderildi olarak işaretlendi.")}>
              Kullanıcıya Gönder
            </Button>
          </>
        }
      />
      {notice ? <p className="inline-result">{notice}</p> : null}

      <section className="detail-hero card">
        <div>
          <StatusBadge status={campaign.status} />
          <h2>{campaign.name}</h2>
          <p>Market, şablon, kanal ve dosya üretim durumu bu kampanya üzerinden takip ediliyor.</p>
        </div>
        <dl className="summary-grid">
          <div>
            <dt>Market</dt>
            <dd>{campaign.market}</dd>
          </div>
          <div>
            <dt>Şablon</dt>
            <dd>{campaign.template}</dd>
          </div>
          <div>
            <dt>Kanal</dt>
            <dd>{campaign.channel}</dd>
          </div>
          <div>
            <dt>Ürün</dt>
            <dd>{campaign.productCount}</dd>
          </div>
        </dl>
      </section>

      <section className="dashboard-grid">
        <Card title="Broşür Önizleme" className="span-8">
          <PreviewFrame title={campaign.name} status="Önizleme hazır" />
        </Card>

        <Card title="Eksik Ürünler" className="span-4">
          <div className="stack-list">
            {missingRows.map((product) => (
              <article className="missing-action-row" key={product.id}>
                <div>
                  <strong>{product.incomingName}</strong>
                  <small>{product.matchedProduct}</small>
                </div>
                <StatusBadge status={product.status} />
                <div className="row-actions">
                  <Button onClick={() => setSelectedMissing(product)}>Eşleştir</Button>
                  <Button onClick={() => setRows(rows.filter((row) => row.id !== product.id))}>Kampanyadan Çıkar</Button>
                </div>
              </article>
            ))}
          </div>
        </Card>

        <Card title="Ürün Eşleştirme Tablosu" className="span-12">
          <Table columns={["Görsel", "Gelen Ürün Adı", "Eşleşen Ürün", "Fiyat", "Eski Fiyat", "Kategori", "Eşleşme Skoru", "Durum", "Aksiyon"]}>
            {rows.map((product) => (
              <tr key={product.id}>
                <td>
                  <ProductThumbnail label={product.matchedProduct} hasImage={product.image} />
                </td>
                <td>{product.incomingName}</td>
                <td>
                  <strong>{product.matchedProduct}</strong>
                </td>
                <td>{product.price}</td>
                <td>{product.oldPrice}</td>
                <td>{product.category}</td>
                <td>
                  <Badge tone={scoreTone(product.score)}>%{product.score}</Badge>
                </td>
                <td>
                  <StatusBadge status={product.status} />
                </td>
                <td>
                  <button className="table-action" type="button" onClick={() => setSelectedMissing(product)}>
                    Eşleştir
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        </Card>

        <Card title="Çıktılar" className="span-12">
          <ExportPanel files={generatedFiles} onAction={setNotice} />
        </Card>

        <Card title="Mesaj Geçmişi" className="span-6">
          <div className="message-list">
            {messages.map((message) => (
              <article key={`${message.sender}-${message.time}`}>
                <strong>{message.sender}</strong>
                <p>{message.text}</p>
                <small>{message.time}</small>
              </article>
            ))}
          </div>
        </Card>

        <Card title="İşlem Geçmişi" className="span-6">
          <ol className="activity-timeline">
            {campaignActivities.map((activity) => (
              <li key={activity.label}>
                <Badge tone={activity.tone}>{activity.time}</Badge>
                <span>{activity.label}</span>
              </li>
            ))}
          </ol>
        </Card>
      </section>

      <MissingProductModal product={selectedMissing} onClose={() => setSelectedMissing(null)} onResolve={resolveProduct} />
    </>
  );
}
