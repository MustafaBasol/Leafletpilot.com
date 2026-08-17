import { useEffect, useState } from "react";
import { canMutateCampaigns, getSelectedMarketId } from "../api/authSession.js";
import { isRealApiEnabled } from "../api/config.js";
import { campaigns as mockCampaigns } from "../data/mockData.js";
import { getCampaigns, regenerateCampaignPreview } from "../data/dataSource.js";
import { Button, Card, ConfirmDialog, FilterBar, Icon, PageHeader, StatusBadge, Table } from "../components/ui/index.js";

const STATUS_OPTIONS = [
  { id: "all", name: "Tümü" },
  { id: "draft", name: "Taslak" },
  { id: "parsing", name: "Ürünler analiz ediliyor" },
  { id: "matching", name: "Ürünler eşleştiriliyor" },
  { id: "missing_products", name: "Eksik ürün var" },
  { id: "preview_ready", name: "Önizleme hazır" },
  { id: "waiting_approval", name: "Onay bekliyor" },
  { id: "revision_requested", name: "Revizyon istendi" },
  { id: "approved", name: "Onaylandı" },
  { id: "generating_files", name: "Dosyalar oluşturuluyor" },
  { id: "completed", name: "Tamamlandı" },
  { id: "failed", name: "Başarısız" },
  { id: "cancelled", name: "İptal edildi" },
];

const CHANNEL_OPTIONS = [
  { id: "all", name: "Tümü" },
  { id: "panel", name: "Panel" },
  { id: "telegram", name: "Telegram" },
  { id: "whatsapp", name: "WhatsApp" },
  { id: "import", name: "İçe Aktarım" },
];

const DATE_OPTIONS = [
  { id: "all", name: "Tüm zamanlar" },
  { id: "7", name: "Son 7 gün" },
  { id: "30", name: "Son 30 gün" },
  { id: "90", name: "Son 90 gün" },
];

const MISSING_OPTIONS = [
  { id: "all", name: "Tümü" },
  { id: "yes", name: "Eksik ürün var" },
  { id: "no", name: "Eksik ürün yok" },
];

// Campaigns not yet through parsing/matching have nothing to regenerate a preview from,
// and a cancelled campaign is a closed terminal state.
const REGENERATE_BLOCKED_STATUSES = new Set(["draft", "parsing", "matching", "cancelled"]);

const defaultFilters = {
  status: "all",
  channel: "all",
  date: "all",
  missing: "all",
};

function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="filter-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function dateFromForPreset(preset) {
  if (preset === "all") return undefined;
  const days = Number(preset);
  if (!Number.isFinite(days)) return undefined;
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

export function Campaigns() {
  const [campaigns, setCampaigns] = useState(() => (isRealApiEnabled ? [] : mockCampaigns));
  const [apiError, setApiError] = useState("");
  const [isLoading, setIsLoading] = useState(isRealApiEnabled);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filters, setFilters] = useState(defaultFilters);
  const [regeneratingId, setRegeneratingId] = useState("");
  const [regenerateTarget, setRegenerateTarget] = useState(null);
  const [notice, setNotice] = useState("");
  const selectedMarketId = getSelectedMarketId();
  const canEditCampaigns = canMutateCampaigns();

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm.trim()), 350);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    let isMounted = true;

    async function loadCampaigns() {
      if (!isRealApiEnabled) return;

      try {
        setIsLoading(true);
        setCampaigns([]);
        const apiCampaigns = await getCampaigns({
          search: debouncedSearch || undefined,
          status: filters.status === "all" ? undefined : filters.status,
          channel: filters.channel === "all" ? undefined : filters.channel,
          dateFrom: dateFromForPreset(filters.date),
          hasMissingProducts: filters.missing === "all" ? undefined : filters.missing === "yes",
        });
        if (isMounted) {
          setCampaigns(apiCampaigns);
          setApiError("");
        }
      } catch (error) {
        if (isMounted) {
          setCampaigns([]);
          setApiError(error.message || "Kampanyalar yüklenemedi.");
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadCampaigns();

    return () => {
      isMounted = false;
    };
  }, [selectedMarketId, debouncedSearch, filters.status, filters.channel, filters.date, filters.missing]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function resetFilters() {
    setFilters(defaultFilters);
    setSearchTerm("");
  }

  const hasActiveFilters =
    Boolean(searchTerm) || Object.keys(defaultFilters).some((key) => filters[key] !== defaultFilters[key]);

  async function confirmRegenerate() {
    const campaign = regenerateTarget;
    if (!campaign) return;
    try {
      setRegeneratingId(campaign.id);
      setApiError("");
      await regenerateCampaignPreview(campaign.id);
      setNotice(`${campaign.name} için önizleme yeniden oluşturuldu.`);
      const refreshed = await getCampaigns({
        search: debouncedSearch || undefined,
        status: filters.status === "all" ? undefined : filters.status,
        channel: filters.channel === "all" ? undefined : filters.channel,
        dateFrom: dateFromForPreset(filters.date),
        hasMissingProducts: filters.missing === "all" ? undefined : filters.missing === "yes",
      });
      setCampaigns(refreshed);
    } catch (error) {
      setApiError(error.message || "Önizleme yeniden oluşturulamadı.");
    } finally {
      setRegeneratingId("");
      setRegenerateTarget(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Kampanyalar"
        description="Kampanya durumlarını, ürün eşleşmelerini ve çıktı aksiyonlarını tek listeden yönetin."
        actions={
          canEditCampaigns ? (
            <>
              <Button href="#/campaigns/new">Yeni Kampanya</Button>
              <Button variant="primary" href="#/campaigns/new">
                Önizleme Oluştur
              </Button>
            </>
          ) : null
        }
      />

      <FilterBar
        searchPlaceholder="Kampanya veya dosya ara"
        searchValue={searchTerm}
        onSearchChange={(event) => setSearchTerm(event.target.value)}
      >
        <FilterSelect label="Durum" value={filters.status} onChange={(value) => updateFilter("status", value)} options={STATUS_OPTIONS} />
        <FilterSelect label="Kanal" value={filters.channel} onChange={(value) => updateFilter("channel", value)} options={CHANNEL_OPTIONS} />
        <FilterSelect label="Tarih" value={filters.date} onChange={(value) => updateFilter("date", value)} options={DATE_OPTIONS} />
        <FilterSelect
          label="Eksik ürün"
          value={filters.missing}
          onChange={(value) => updateFilter("missing", value)}
          options={MISSING_OPTIONS}
        />
        {hasActiveFilters ? (
          <button className="filter-reset" type="button" onClick={resetFilters}>
            <Icon name="close" /> Filtreleri Temizle
          </button>
        ) : null}
      </FilterBar>

      {apiError ? (
        <p className="inline-result inline-result-danger" role="alert">
          {apiError}
        </p>
      ) : null}
      {notice ? (
        <p className="inline-result inline-result-success" role="status">
          {notice}
        </p>
      ) : null}

      <Card title="Kampanya Listesi">
        {isLoading ? <p className="inline-result">Kampanyalar yükleniyor...</p> : null}
        {!isLoading && campaigns.length === 0 ? (
          <p className="catalog-empty">
            {hasActiveFilters ? "Filtrelerle eşleşen kampanya bulunamadı." : "Kampanya verisi gösterilemiyor."}
          </p>
        ) : null}
        {!isLoading && campaigns.length > 0 ? (
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
            {campaigns.map((campaign) => {
              const regenerateBlocked = REGENERATE_BLOCKED_STATUSES.has(campaign.rawStatus);
              const isRegenerating = regeneratingId === campaign.id;
              return (
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
                      <a className="table-action" href={`#/campaigns/${campaign.id}?view=preview`}>
                        <Icon name="eye" /> Önizleme
                      </a>
                      {canEditCampaigns ? (
                        <button
                          className="table-action"
                          type="button"
                          disabled={regenerateBlocked || isRegenerating}
                          title={regenerateBlocked ? "Bu kampanya durumunda önizleme yeniden oluşturulamaz." : undefined}
                          onClick={() => setRegenerateTarget(campaign)}
                        >
                          <Icon name="refresh" /> {isRegenerating ? "Oluşturuluyor..." : "Yeniden Oluştur"}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : null}
      </Card>

      <ConfirmDialog
        isOpen={Boolean(regenerateTarget)}
        title="Önizlemeyi yeniden oluştur"
        description={
          regenerateTarget
            ? `${regenerateTarget.name} için önizleme ve çıktı dosyaları yeniden oluşturulacak. Devam edilsin mi?`
            : ""
        }
        confirmLabel="Yeniden Oluştur"
        isLoading={Boolean(regeneratingId)}
        onCancel={() => setRegenerateTarget(null)}
        onConfirm={confirmRegenerate}
      />
    </>
  );
}
