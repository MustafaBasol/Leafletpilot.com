import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { labelFor, normalizeApiError, signupStatusLabels } from "./platformOps.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

export function SignupRequestList() {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ status: "", search: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    platformApi
      .listSignupRequests(filters)
      .then((response) => setItems(response.items || []))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [filters.status, filters.search]);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Başvurular</h2>
          <p>Başvuruları inceleyin, onaylayın ve pilot markete dönüştürün.</p>
        </div>
      </section>
      <div className="filter-bar">
        <input placeholder="Ara" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">Tüm durumlar</option>
          <option value="pending">Bekliyor</option>
          <option value="reviewing">İncelemede</option>
          <option value="approved">Onaylandı</option>
          <option value="rejected">Reddedildi</option>
          <option value="provisioned">Provision edildi</option>
        </select>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title="Başvuru Listesi">
        {loading ? <p className="inline-result">Yükleniyor...</p> : null}
        {!loading && items.length === 0 ? <p className="inline-result">Bu filtrelerde başvuru yok.</p> : null}
        {!loading && items.length > 0 ? (
          <Table columns={["Market", "Yetkili", "E-posta", "Durum", "Güncellendi", ""]}>
            {items.map((item) => (
              <tr key={item.id}>
                <td><strong>{item.market_name}</strong><small>{item.city || item.country_code}</small></td>
                <td>{item.contact_name}</td>
                <td>{item.email}</td>
                <td><Badge>{labelFor(signupStatusLabels, item.status)}</Badge></td>
                <td>{formatDate(item.updated_at || item.created_at)}</td>
                <td><a className="table-action" href={`#/platform/signup-requests/${item.id}`}>Aç</a></td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>
    </>
  );
}
