import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";

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
          <h2>Marketler</h2>
          <p>Lifecycle, deneme ve onboarding durumlarını izleyin.</p>
        </div>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title="Market Listesi">
        <Table columns={["Market", "Lifecycle", "Onboarding", "Üye", "Ürün", "Kampanya", ""]}>
          {items.map((market) => (
            <tr key={market.id}>
              <td><strong>{market.name}</strong><small>{market.slug}</small></td>
              <td><Badge>{market.lifecycle_status}</Badge></td>
              <td>{market.onboarding_status}</td>
              <td>{market.member_count}</td>
              <td>{market.product_count}</td>
              <td>{market.campaign_count}</td>
              <td><a className="table-action" href={`#/platform/markets/${market.id}`}>Aç</a></td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
