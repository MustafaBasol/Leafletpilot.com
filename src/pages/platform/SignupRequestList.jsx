import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { statusLabel, t } from "./platformI18n.js";

const statusOptions = ["pending", "reviewing", "rejected", "provisioned"];

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
          <h2>{t("signupRequests")}</h2>
          <p>{t("signupOverview")}</p>
        </div>
      </section>
      <div className="filter-bar">
        <input placeholder={t("search")} value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
        <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">{t("allStatuses")}</option>
          {statusOptions.map((status) => (
            <option key={status} value={status}>{statusLabel(status)}</option>
          ))}
        </select>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title={t("signupRequestList")}>
        <Table columns={[t("market"), t("contactPerson"), t("email"), t("status"), t("date"), ""]}>
          {items.map((item) => (
            <tr key={item.id}>
              <td><strong>{item.market_name}</strong><small>{item.city || item.country_code}</small></td>
              <td>{item.contact_name}</td>
              <td>{item.email}</td>
              <td><Badge>{statusLabel(item.status)}</Badge></td>
              <td>{new Date(item.created_at).toLocaleString("tr-TR")}</td>
              <td><a className="table-action" href={`#/platform/signup-requests/${item.id}`}>{t("open")}</a></td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
