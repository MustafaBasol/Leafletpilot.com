import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card, Table } from "../../components/ui/index.js";
import { PlatformMarketProductImportModal } from "./PlatformMarketProductImportModal.jsx";
import {
  hasEffectiveOwnerInvitation,
  needsManualInvitationDelivery,
  normalizeApiError,
  normalizeManualLinkError,
  ownerInvitationStatusLabel,
} from "./platformOps.js";
import { blockerLabel, countRows, deriveReadiness, statusLabel, t } from "./platformI18n.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

function formatMoney(unitAmount, currency) {
  if (unitAmount === null || unitAmount === undefined) return "-";
  return `${(unitAmount / 100).toFixed(2)} ${currency || ""}`.trim();
}

const PLAN_CODES = ["starter", "standard", "pro"];

const BILLING_SYNC_LABELS = {
  ok: "Sağlıklı",
  error: "Hata",
  no_subscription: "Abonelik yok",
};

const PENDING_REASON_LABELS = {
  downgrade: "Planlanan düşürme",
  upgrade_pending_payment: "Yükseltme ödemesi bekleniyor",
};

export function PlatformMarketDetail({ id }) {
  const [market, setMarket] = useState(null);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [manualLinkMessage, setManualLinkMessage] = useState("");
  const [manualLinkCopied, setManualLinkCopied] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState("starter");
  const [planMessage, setPlanMessage] = useState("");
  const [showImportModal, setShowImportModal] = useState(false);

  async function load() {
    setError("");
    try {
      const response = await platformApi.getMarket(id);
      setMarket(response);
      setOwnerEmail(response.owner_invitation?.email || response.contact_email || "");
      setSelectedPlan(response.subscription_plan || "starter");
    } catch (err) {
      setError(normalizeApiError(err));
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function setLifecycle(lifecycle_status) {
    const reason = lifecycle_status === "active" ? "" : window.prompt(t("reasonPrompt"));
    if (lifecycle_status !== "active" && !reason) return;
    const message = lifecycle_status === "archived"
      ? t("confirmArchiveMarket")
      : `${statusLabel(lifecycle_status)} ${t("confirmStatusChangeSuffix")}`;
    if (!window.confirm(message)) return;
    setAction(`lifecycle-${lifecycle_status}`);
    setError("");
    try {
      await platformApi.updateMarketLifecycle(id, { lifecycle_status, reason, confirm_archive: lifecycle_status === "archived" });
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function changePlan() {
    if (!market || selectedPlan === market.subscription_plan) return;
    setAction("plan");
    setError("");
    setPlanMessage("");
    try {
      const reason = window.prompt(t("reasonPrompt")) || undefined;
      await platformApi.updateMarketPlan(id, { subscription_plan: selectedPlan, reason });
      setPlanMessage(t("planChanged"));
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function runInvitation(operation) {
    setAction(operation);
    setError("");
    try {
      const body = { email: ownerEmail || null };
      if (operation === "create") {
        await platformApi.createOwnerInvitation(id, body);
      } else {
        await platformApi.rotateOwnerInvitation(id, body);
      }
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function revokeInvitation() {
    if (!window.confirm(t("confirmRevokeOwnerInvitation"))) return;
    setAction("revoke");
    setError("");
    try {
      await platformApi.revokeOwnerInvitation(id);
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function resyncBilling() {
    setAction("billing-resync");
    setError("");
    try {
      await platformApi.resyncMarketBilling(id);
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function copyManualLink() {
    setAction("manual-link");
    setManualLinkMessage("");
    setManualLinkCopied(false);
    setError("");
    try {
      const response = await platformApi.createManualOwnerInvitationLink(id);
      await navigator.clipboard.writeText(response.accept_url);
      setManualLinkMessage(t("manualLinkCopied"));
      setManualLinkCopied(true);
      await load();
    } catch (err) {
      setError(normalizeManualLinkError(err));
      setManualLinkMessage("");
    } finally {
      setAction("");
    }
  }

  if (!market && !error) return <p className="inline-result">{t("loading")}</p>;

  const readiness = deriveReadiness(market);

  return (
    <>
      {market ? (
        <section className="page-heading">
          <div>
            <h2>{market.name}</h2>
            <p>{market.slug}</p>
          </div>
          <Badge>{statusLabel(market.lifecycle_status)}</Badge>
        </section>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {market ? (
        <section className="dashboard-grid">
          <Card title={t("readiness")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("status")}</dt><dd>{statusLabel(readiness.status)}</dd></div>
              <div><dt>{t("activeUser")}</dt><dd>{market.readiness?.has_active_market_user ? t("yes") : t("no")}</dd></div>
              <div><dt>{t("requiredSetup")}</dt><dd>{market.readiness?.required_setup_complete ? t("complete") : t("missing")}</dd></div>
              <div><dt>{t("lastActivity")}</dt><dd>{formatDate(market.readiness?.last_activity_at)}</dd></div>
              {countRows(market).map((row) => (
                <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>
              ))}
            </dl>
            {readiness.blockers.length ? (
              <ul className="readiness-blocker-list" aria-label={t("readiness")}>
                {readiness.blockers.map((blocker) => (
                  <li key={`${blockerLabel(blocker)}-${JSON.stringify(blocker)}`}>{blockerLabel(blocker)}</li>
                ))}
              </ul>
            ) : (
              <p className="inline-result">{t("readinessReady")}</p>
            )}
          </Card>
          <Card title={t("lifecycle")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("trialEnds")}</dt><dd>{formatDate(market.trial_ends_at)}</dd></div>
              <div><dt>{t("lastReason")}</dt><dd>{market.lifecycle_reason || "-"}</dd></div>
              <div><dt>{t("lastUpdated")}</dt><dd>{formatDate(market.lifecycle_updated_at)}</dd></div>
            </dl>
            <div className="page-actions">
              <Button disabled={Boolean(action) || market.lifecycle_status === "active"} onClick={() => setLifecycle("active")}>{t("activateOrContinue")}</Button>
              <Button variant="danger" disabled={Boolean(action) || market.lifecycle_status === "suspended"} onClick={() => setLifecycle("suspended")}>{t("suspend")}</Button>
              <Button variant="danger" disabled={Boolean(action) || market.lifecycle_status === "archived"} onClick={() => setLifecycle("archived")}>{t("archive")}</Button>
            </div>
          </Card>
          <Card title={t("plan")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("currentPlan")}</dt><dd>{market.subscription_plan_display || market.subscription_plan}</dd></div>
              <div><dt>{t("monthlyCampaignQuota")}</dt><dd>{market.plan_quota ? `${market.plan_quota.monthly_campaigns_used} / ${market.plan_quota.monthly_campaigns_limit ?? t("unlimited")}` : "-"}</dd></div>
              <div><dt>{t("monthlyExportQuota")}</dt><dd>{market.plan_quota?.monthly_exports_limit ?? t("unlimited")}</dd></div>
              <div><dt>{t("privateProductLimit")}</dt><dd>{market.plan_quota?.private_products_limit ?? t("unlimited")}</dd></div>
              <div><dt>{t("privateTemplateLimit")}</dt><dd>{market.plan_quota?.private_templates_limit ?? t("unlimited")}</dd></div>
              <div><dt>{t("brandingAssetLimit")}</dt><dd>{market.plan_quota?.branding_assets_limit ?? t("unlimited")}</dd></div>
            </dl>
            <label className="settings-form">
              {t("changePlan")}
              <select value={selectedPlan} onChange={(event) => setSelectedPlan(event.target.value)}>
                {PLAN_CODES.map((code) => (
                  <option key={code} value={code}>{code}</option>
                ))}
              </select>
            </label>
            <div className="page-actions">
              <Button disabled={Boolean(action) || selectedPlan === market.subscription_plan} onClick={changePlan}>{t("savePlan")}</Button>
            </div>
            {planMessage ? <p className="inline-result">{planMessage}</p> : null}
          </Card>
          <Card title="Faturalandırma (Stripe)" className="span-6">
            <dl className="detail-list">
              <div><dt>Senkronizasyon durumu</dt><dd>{BILLING_SYNC_LABELS[market.billing?.billing_sync_status] || market.billing?.billing_sync_status || "-"}</dd></div>
              <div><dt>Abonelik durumu</dt><dd>{market.billing?.status || "-"}</dd></div>
              <div><dt>Aylık ücret</dt><dd>{formatMoney(market.billing?.unit_amount, market.billing?.currency)}</dd></div>
              <div><dt>Sonraki yenileme</dt><dd>{formatDate(market.billing?.current_period_end)}</dd></div>
              <div><dt>İptal bekliyor mu</dt><dd>{market.billing?.cancel_at_period_end ? "Evet" : "Hayır"}</dd></div>
              {market.billing?.pending_plan_code ? (
                <div>
                  <dt>{PENDING_REASON_LABELS[market.billing.pending_change_reason] || "Bekleyen değişiklik"}</dt>
                  <dd>{market.billing.pending_plan_code} · {formatDate(market.billing.pending_change_at)}</dd>
                </div>
              ) : null}
              <div><dt>Son senkronizasyon</dt><dd>{formatDate(market.billing?.last_synced_at)}</dd></div>
              <div><dt>Stripe Customer</dt><dd>{market.billing?.stripe_customer_id || "-"}</dd></div>
              <div><dt>Stripe Subscription</dt><dd>{market.billing?.stripe_subscription_id || "-"}</dd></div>
              <div><dt>Stripe Price</dt><dd>{market.billing?.stripe_price_id || "-"}</dd></div>
            </dl>
            {market.billing?.sync_error ? (
              <p className="inline-result inline-result-warning">Senkronizasyon hatası: {market.billing.sync_error}</p>
            ) : null}
            <div className="page-actions">
              <Button disabled={Boolean(action) || !market.billing?.stripe_subscription_id} onClick={resyncBilling}>
                {action === "billing-resync" ? "Senkronize ediliyor..." : "Stripe'tan yeniden senkronize et"}
              </Button>
            </div>
          </Card>
          <Card title="Katalog İçe Aktarma" className="span-6">
            <p className="inline-result">Bu marketin ürün kataloğunu Excel dosyasından önizleme onaylı olarak içe aktarın.</p>
            <div className="page-actions">
              <Button onClick={() => setShowImportModal(true)}>Excel ile Ürün Yükle</Button>
            </div>
          </Card>
          <Card title={t("ownerInvitation")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("email")}</dt><dd>{market.owner_invitation?.email || market.contact_email || "-"}</dd></div>
              <div><dt>{t("status")}</dt><dd>{ownerInvitationStatusLabel(market.owner_invitation)}</dd></div>
              <div><dt>{t("expires")}</dt><dd>{formatDate(market.owner_invitation?.expires_at)}</dd></div>
              <div><dt>{t("lastSent")}</dt><dd>{formatDate(market.owner_invitation?.last_sent_at)}</dd></div>
              <div><dt>{t("sendCount")}</dt><dd>{market.owner_invitation?.send_count ?? 0}</dd></div>
              <div><dt>{t("accepted")}</dt><dd>{formatDate(market.owner_invitation?.accepted_at)}</dd></div>
              {market.owner_invitation?.last_send_error ? (
                <div><dt>{t("sendError")}</dt><dd>{market.owner_invitation.last_send_error}</dd></div>
              ) : null}
            </dl>
            <label className="settings-form">
              {t("ownerEmail")}
              <input value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} />
            </label>
            <div className="page-actions">
              <Button disabled={Boolean(action) || hasEffectiveOwnerInvitation(market)} onClick={() => runInvitation("create")}>{t("createInvitation")}</Button>
              <Button disabled={Boolean(action)} onClick={() => runInvitation("rotate")}>{t("rotateInvitation")}</Button>
              <Button variant="danger" disabled={Boolean(action) || !hasEffectiveOwnerInvitation(market)} onClick={revokeInvitation}>{t("revokeInvitation")}</Button>
              {needsManualInvitationDelivery(market.owner_invitation) ? (
                <Button disabled={Boolean(action)} onClick={copyManualLink}>
                  {manualLinkCopied ? t("copyInvitationLink") : t("createInvitationLink")}
                </Button>
              ) : null}
            </div>
            <p className="inline-result">
              {needsManualInvitationDelivery(market.owner_invitation) ? t("manualDeliveryNotice") : t("invitationEmailNotice")}
            </p>
            {manualLinkMessage ? <p className="inline-result">{manualLinkMessage}</p> : null}
          </Card>
          <Card title={t("profile")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("legalName")}</dt><dd>{market.legal_name || "-"}</dd></div>
              <div><dt>{t("location")}</dt><dd>{[market.city, market.country_code].filter(Boolean).join(", ") || "-"}</dd></div>
              <div><dt>{t("languageCurrency")}</dt><dd>{market.language} / {market.currency}</dd></div>
              <div><dt>{t("timeZone")}</dt><dd>{market.timezone}</dd></div>
              <div><dt>{t("contact")}</dt><dd>{market.contact_email || "-"} {market.contact_phone || ""}</dd></div>
              <div><dt>{t("onboarding")}</dt><dd>{statusLabel(market.onboarding_status)} · {t("step")} {market.onboarding_step}</dd></div>
            </dl>
          </Card>
          <Card title={t("platformActivity")} className="span-12">
            <Table columns={[t("action"), t("date")]}>
              {(market.recent_activity || []).map((item) => (
                <tr key={item.id}>
                  <td><Badge>{item.action}</Badge></td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {(market.recent_activity || []).length === 0 ? <tr><td colSpan="2">{t("noActivity")}</td></tr> : null}
            </Table>
          </Card>
        </section>
      ) : null}
      {showImportModal ? (
        <PlatformMarketProductImportModal
          marketId={id}
          onClose={() => setShowImportModal(false)}
          onImported={load}
        />
      ) : null}
    </>
  );
}
