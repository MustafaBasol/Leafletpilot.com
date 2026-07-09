import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";

export function SignupRequestList() {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ status: "", search: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    platformApi
      .listSignupRequests(filters)
      .then((response) => setItems(response.items || []))
      .catch((err) => setError(err.message));
  }, [filters.status, filters.search]);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Başvurular</h2>
          <p>Ücretsiz deneme başvurularını inceleyin ve uygun olanları markete dönüştürün.</p>
        </div>
      </section>
      <div className="filter-bar">
        <input placeholder="Ara" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">Tüm durumlar</option>
          <option value="pending">Bekliyor</option>
          <option value="reviewing">İnceleniyor</option>
          <option value="rejected">Reddedildi</option>
          <option value="provisioned">Provision edildi</option>
        </select>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title="Başvuru Listesi">
        <Table columns={["Market", "Yetkili", "E-posta", "Durum", "Tarih", ""]}>
          {items.map((item) => (
            <tr key={item.id}>
              <td><strong>{item.market_name}</strong><small>{item.city || item.country_code}</small></td>
              <td>{item.contact_name}</td>
              <td>{item.email}</td>
              <td><Badge>{item.status}</Badge></td>
              <td>{new Date(item.created_at).toLocaleString("tr-TR")}</td>
              <td><a className="table-action" href={`#/platform/signup-requests/${item.id}`}>Aç</a></td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
