import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card } from "../../components/ui/index.js";
import { blockerLabel, countRows, deriveReadiness, statusLabel, t } from "./platformI18n.js";

export function PlatformMarketDetail({ id }) {
  const [market, setMarket] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setMarket(await platformApi.getMarket(id));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function setLifecycle(lifecycle_status) {
    const message = lifecycle_status === "archived" ? "Market arşivlensin mi?" : `${statusLabel(lifecycle_status)} yapılsın mı?`;
    if (!window.confirm(message)) return;
    await platformApi.updateMarketLifecycle(id, { lifecycle_status, confirm_archive: lifecycle_status === "archived" });
    await load();
  }

  if (!market) return <p className="inline-result">{t("loading")}</p>;

  const readiness = deriveReadiness(market);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{market.name}</h2>
          <p>{market.slug}</p>
        </div>
        <Badge>{statusLabel(market.lifecycle_status)}</Badge>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="dashboard-grid">
        <Card title={t("operation")} className="span-6">
          <dl className="detail-list">
            <div><dt>{t("trialEnds")}</dt><dd>{market.trial_ends_at ? new Date(market.trial_ends_at).toLocaleDateString("tr-TR") : "-"}</dd></div>
            <div><dt>{t("lifecycle")}</dt><dd>{statusLabel(market.lifecycle_status)}</dd></div>
            <div><dt>{t("onboarding")}</dt><dd>{statusLabel(market.onboarding_status)} · adım {market.onboarding_step}</dd></div>
            <div><dt>{t("activeUser")}</dt><dd>{market.member_count > 0 ? t("yes") : t("no")}</dd></div>
            {countRows(market).map((row) => (
              <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>
            ))}
          </dl>
          <div className="page-actions">
            <Button onClick={() => setLifecycle("active")}>{t("activate")}</Button>
            <Button variant="danger" onClick={() => setLifecycle("suspended")}>{t("suspend")}</Button>
            <Button variant="danger" onClick={() => setLifecycle("archived")}>{t("archive")}</Button>
          </div>
        </Card>
        <Card title={t("readiness")} className="span-6">
          <dl className="detail-list">
            <div><dt>{t("readiness")}</dt><dd>{statusLabel(readiness.status)}</dd></div>
            <div><dt>{t("requiredSetup")}</dt><dd>{readiness.blockers.length ? t("missing") : t("complete")}</dd></div>
          </dl>
          {readiness.blockers.length ? (
            <ul className="readiness-blocker-list" aria-label={t("readiness")}>
              {readiness.blockers.map((blocker) => (
                <li key={blocker.code}>{blockerLabel(blocker)}</li>
              ))}
            </ul>
          ) : (
            <p className="inline-result">{t("readinessReady")}</p>
          )}
        </Card>
        <Card title={t("profile")} className="span-6">
          <dl className="detail-list">
            <div><dt>{t("legalName")}</dt><dd>{market.legal_name || "-"}</dd></div>
            <div><dt>{t("location")}</dt><dd>{[market.city, market.country_code].filter(Boolean).join(", ") || "-"}</dd></div>
            <div><dt>{t("languageCurrency")}</dt><dd>{market.language} / {market.currency}</dd></div>
            <div><dt>{t("timeZone")}</dt><dd>{market.timezone}</dd></div>
            <div><dt>{t("contact")}</dt><dd>{market.contact_email || "-"} {market.contact_phone || ""}</dd></div>
          </dl>
        </Card>
      </section>
    </>
  );
}
