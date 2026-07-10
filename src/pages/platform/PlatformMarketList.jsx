import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { labelFor, lifecycleLabels, normalizeApiError, readinessLabels } from "./platformOps.js";

export function PlatformMarketList() {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ lifecycle_status: "", readiness: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    platformApi
      .listMarkets(filters)
      .then((response) => setItems(response.items || []))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [filters.lifecycle_status, filters.readiness]);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Marketler</h2>
          <p>Lifecycle, readiness, owner daveti ve onboarding durumlarını izleyin.</p>
        </div>
      </section>
      <div className="filter-bar">
        <select value={filters.lifecycle_status} onChange={(event) => setFilters({ ...filters, lifecycle_status: event.target.value })}>
          <option value="">Tüm lifecycle</option>
          <option value="trial">Deneme</option>
          <option value="active">Aktif</option>
          <option value="suspended">Askıda</option>
          <option value="archived">Arşivli</option>
        </select>
        <select value={filters.readiness} onChange={(event) => setFilters({ ...filters, readiness: event.target.value })}>
          <option value="">Tüm readiness</option>
          <option value="awaiting_owner">Owner bekliyor</option>
          <option value="onboarding">Onboarding</option>
          <option value="ready">Hazır</option>
          <option value="suspended">Askıda</option>
          <option value="blocked">Blokeli</option>
        </select>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title="Market Listesi">
        {loading ? <p className="inline-result">Yükleniyor...</p> : null}
        {!loading && items.length === 0 ? <p className="inline-result">Bu filtrelerde market yok.</p> : null}
        {!loading && items.length > 0 ? (
          <Table columns={["Market", "Lifecycle", "Readiness", "Owner Daveti", "Onboarding", "Üye", ""]}>
            {items.map((market) => (
              <tr key={market.id}>
                <td><strong>{market.name}</strong><small>{market.slug}</small></td>
                <td><Badge>{labelFor(lifecycleLabels, market.lifecycle_status)}</Badge></td>
                <td><Badge>{labelFor(readinessLabels, market.readiness?.state)}</Badge></td>
                <td>{market.owner_invitation ? `${market.owner_invitation.status} · ${market.owner_invitation.delivery_status}` : "Yok"}</td>
                <td>{market.onboarding_status}</td>
                <td>{market.member_count}</td>
                <td><a className="table-action" href={`#/platform/markets/${market.id}`}>Aç</a></td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>
    </>
  );
}
