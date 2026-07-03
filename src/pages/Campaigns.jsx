import { useEffect, useState } from "react";
import { campaigns as mockCampaigns } from "../data/mockData.js";
import { isRealApiEnabled } from "../api/config.js";
import { getCampaigns } from "../data/dataSource.js";
import {
  Button,
  Card,
  FilterBar,
  FilterChip,
  Icon,
  PageHeader,
  StatusBadge,
  Table,
} from "../components/ui/index.js";

export function Campaigns() {
  const [campaigns, setCampaigns] = useState(mockCampaigns);
  const [apiError, setApiError] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadCampaigns() {
      if (!isRealApiEnabled) return;

      try {
        const apiCampaigns = await getCampaigns();
        if (isMounted) {
          setCampaigns(apiCampaigns);
          setApiError("");
        }
      } catch (error) {
        if (isMounted) {
          setCampaigns(mockCampaigns);
          setApiError(`${error.message} Mock kampanya listesi gösteriliyor.`);
        }
      }
    }

    loadCampaigns();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <>
      <PageHeader
        title="Kampanyalar"
        description="Kampanya durumlarını, ürün eşleşmelerini ve çıktı aksiyonlarını tek listeden yönetin."
        actions={
          <>
            <Button href="#/campaigns/new">Yeni Kampanya</Button>
            <Button variant="primary" href="#/campaigns/new">
              Önizleme Oluştur
            </Button>
          </>
        }
      />

      <FilterBar searchPlaceholder="Kampanya, market veya dosya ara">
        <FilterChip label="Durum" />
        <FilterChip label="Market" />
        <FilterChip label="Kanal" />
        <FilterChip label="Tarih" value="Son 30 gün" />
        <FilterChip label="Eksik ürün" value="Var / Yok" />
      </FilterBar>

      {apiError ? <p className="inline-result inline-result-warning">{apiError}</p> : null}

      <Card title="Kampanya Listesi">
        <Table
          columns={[
            "Kampanya",
            "Market",
            "Ürün Sayısı",
            "Durum",
            "Kanal",
            "Oluşturma Tarihi",
            "Son Güncelleme",
            "Dosyalar",
            "Aksiyonlar",
          ]}
        >
          {campaigns.map((campaign) => (
            <tr key={campaign.id}>
              <td>
                <strong>{campaign.name}</strong>
                <small>{campaign.template}</small>
              </td>
              <td>{campaign.market}</td>
              <td>
                {campaign.productCount} ürün
                {campaign.missingCount ? <small>{campaign.missingCount} eksik ürün</small> : null}
              </td>
              <td>
                <StatusBadge status={campaign.status} />
              </td>
              <td>{campaign.channel}</td>
              <td>{campaign.createdAt}</td>
              <td>{campaign.updatedAt}</td>
              <td>
                <div className="file-badges">
                  {campaign.files.length ? campaign.files.map((file) => <span key={file}>{file}</span>) : <span>Yok</span>}
                </div>
              </td>
              <td>
                <div className="table-actions">
                  <a className="table-action" href={`#/campaigns/${campaign.id}`}>
                    Detay
                  </a>
                  <button className="table-action" type="button">
                    <Icon name="eye" /> Önizleme
                  </button>
                  <button className="table-action" type="button">
                    <Icon name="download" /> PDF
                  </button>
                  <button className="table-action" type="button">
                    <Icon name="refresh" /> Yeniden Oluştur
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
