import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { statusLabel, t } from "./platformI18n.js";

export function PlatformMarketList() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    platformApi.listMarkets().then((response) => setItems(response.items || [])).catch((err) => setError(err.message));
  }, []);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{t("markets")}</h2>
          <p>{t("marketOverview")}</p>
        </div>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title={t("marketList")}>
        <Table columns={[t("market"), t("lifecycle"), t("onboarding"), t("member"), t("product"), t("campaign"), ""]}>
          {items.map((market) => (
            <tr key={market.id}>
              <td><strong>{market.name}</strong><small>{market.slug}</small></td>
              <td><Badge>{statusLabel(market.lifecycle_status)}</Badge></td>
              <td>{statusLabel(market.onboarding_status)}</td>
              <td>{market.member_count}</td>
              <td>{market.product_count}</td>
              <td>{market.campaign_count}</td>
              <td><a className="table-action" href={`#/platform/markets/${market.id}`}>{t("open")}</a></td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
