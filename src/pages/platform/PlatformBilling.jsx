import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { normalizeApiError } from "./platformOps.js";

const PLAN_LABELS = { starter: "Başlangıç", standard: "Standart", pro: "Pro" };

const HEALTH_LABELS = {
  ok: "Sağlıklı",
  missing: "Eksik",
  inactive: "Pasif",
  duplicate: "Yinelenen",
  currency_mismatch: "Para birimi uyuşmuyor",
  amount_mismatch: "Tutar uyuşmuyor",
  stripe_error: "Stripe hatası",
  stripe_disabled: "Stripe devre dışı",
};

export function PlatformBilling() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    platformApi
      .getBillingPlanHealth()
      .then(setData)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Faturalandırma</h2>
          <p>Plan / Stripe Price eşleştirme sağlığı.</p>
        </div>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      {loading ? <p className="inline-result">Yükleniyor...</p> : null}
      {!loading && data && !data.stripe_enabled ? (
        <p className="inline-result inline-result-warning">Stripe devre dışı (STRIPE_ENABLED=false).</p>
      ) : null}
      {!loading && data ? (
        <Card title="Plan Eşleştirmeleri">
          <Table columns={["Plan", "Lookup key", "Durum", "Stripe Price", "Tutar", "Detay"]}>
            {data.plans.map((plan) => (
              <tr key={plan.plan_code}>
                <td>{PLAN_LABELS[plan.plan_code] || plan.plan_code}</td>
                <td>{plan.lookup_key}</td>
                <td><Badge tone={plan.health === "ok" ? "success" : "warning"}>{HEALTH_LABELS[plan.health] || plan.health}</Badge></td>
                <td>{plan.stripe_price_id || "-"}</td>
                <td>{plan.unit_amount !== undefined && plan.unit_amount !== null ? `${(plan.unit_amount / 100).toFixed(2)} ${plan.currency || ""}` : "-"}</td>
                <td>{plan.detail || "-"}</td>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
    </>
  );
}
