import { useEffect, useState } from "react";
import { canManageBilling } from "../api/authSession.js";
import {
  cancelBillingSubscription,
  changeBillingPlan,
  getBillingSubscription,
  getMarketPlan,
  listBillingInvoices,
  openBillingPortal,
  resumeBillingSubscription,
  startBillingCheckout,
} from "../data/dataSource.js";
import { Button, Card, ConfirmDialog, PageHeader, StatusBadge, Table } from "../components/ui/index.js";

const PLAN_LABELS = { starter: "Başlangıç", standard: "Plus", pro: "Pro", unassigned: "Atanmamış" };
const PLAN_ORDER = ["starter", "standard", "pro"];

const STATUS_LABELS = {
  active: "Abonelik aktif",
  trialing: "Deneme sürümü",
  past_due: "Ödeme gecikti",
  unpaid: "Ödenmedi",
  canceled: "Abonelik iptal edildi",
  incomplete: "Ödeme onayı bekleniyor",
  incomplete_expired: "Abonelik iptal edildi",
  paused: "Duraklatıldı",
};

function statusLabel(status) {
  if (!status) return "Abonelik yok";
  return STATUS_LABELS[status] || status;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString("tr-TR") : "-";
}

function formatMoney(unitAmount, currency) {
  if (unitAmount === null || unitAmount === undefined) return "-";
  return `${(unitAmount / 100).toFixed(2)} ${currency || ""}`.trim();
}

function invoiceStatusLabel(invoice) {
  if (invoice.payment_failed) return "Ödeme başarısız";
  const map = { paid: "Ödendi", open: "Açık", draft: "Taslak", uncollectible: "Tahsil edilemedi", void: "İptal" };
  return map[invoice.status] || invoice.status || "-";
}

export function Billing({ checkoutStatus = "" }) {
  const canManage = canManageBilling();
  const [subscription, setSubscription] = useState(null);
  const [plan, setPlan] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [showCheckoutSuccess] = useState(checkoutStatus === "success");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [subscriptionResult, planResult, invoicesResult] = await Promise.all([
        getBillingSubscription(),
        getMarketPlan(),
        listBillingInvoices({ limit: 20 }),
      ]);
      setSubscription(subscriptionResult);
      setPlan(planResult);
      setInvoices(invoicesResult?.items || []);
    } catch (e) {
      setError(e?.message || "Faturalandırma bilgileri yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (checkoutStatus !== "success") return;
    // Strip the query param from the address bar via replaceState (not
    // location.hash=) so we don't trigger a hashchange re-route while the
    // success banner is showing. The webhook that activates the
    // subscription can land a moment after the checkout redirect, so
    // schedule a single re-fetch rather than trusting the first load().
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/settings/billing`);
    const timeoutId = window.setTimeout(load, 2000);
    return () => window.clearTimeout(timeoutId);
  }, []);

  async function runAction(actionKey, fn, successMessage) {
    if (busyAction) return;
    setBusyAction(actionKey);
    setError("");
    setMessage("");
    try {
      const result = await fn();
      if (successMessage) setMessage(successMessage);
      await load();
      return result;
    } catch (e) {
      setError(e?.message || "İşlem başarısız oldu.");
      return null;
    } finally {
      setBusyAction("");
    }
  }

  async function handleCheckout(planCode) {
    const result = await runAction(`checkout:${planCode}`, () => startBillingCheckout(planCode));
    if (result?.checkout_url) window.location.href = result.checkout_url;
  }

  async function handleChangePlan(planCode) {
    const result = await runAction(`change:${planCode}`, () => changeBillingPlan(planCode));
    if (!result) return;
    if (result.status === "pending_payment") {
      setMessage(`Yükseltme ödeme onayı bekliyor. Son tarih: ${formatDate(result.expires_at)}.`);
    } else if (result.status === "scheduled") {
      setMessage(`Plan değişikliği ${formatDate(result.effective_at)} tarihinde geçerli olacak.`);
    } else {
      setMessage("Plan güncellendi.");
    }
  }

  async function handlePortal() {
    const result = await runAction("portal", () => openBillingPortal());
    if (result?.portal_url) window.location.href = result.portal_url;
  }

  async function handleCancel() {
    setConfirm(null);
    await runAction("cancel", () => cancelBillingSubscription(), "İptal talebiniz alındı; dönem sonuna kadar erişiminiz devam edecek.");
  }

  async function handleResume() {
    await runAction("resume", () => resumeBillingSubscription(), "Abonelik yenilemesi yeniden etkinleştirildi.");
  }

  const hasSubscription = Boolean(subscription?.status);
  const currentPlanCode = subscription?.plan_code || "unassigned";

  return (
    <>
      <PageHeader title="Faturalandırma" description="Abonelik planı, ödeme durumu ve fatura geçmişi." />
      {showCheckoutSuccess ? (
        <p className="inline-result" role="status">Ödeme başarıyla tamamlandı. Aboneliğiniz etkinleştirildi.</p>
      ) : null}
      {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}
      {message ? <p className="inline-result" role="status">{message}</p> : null}
      {loading ? <p className="inline-result">Yükleniyor...</p> : null}

      <section className="dashboard-grid">
        <Card title="Mevcut Abonelik" className="span-8">
          <div className="settings-form">
            <p>
              Plan: <strong>{PLAN_LABELS[currentPlanCode] || currentPlanCode}</strong>{" "}
              <StatusBadge status={statusLabel(subscription?.status)} />
            </p>
            {subscription?.unit_amount ? (
              <p>Aylık ücret: {formatMoney(subscription.unit_amount, subscription.currency)}</p>
            ) : null}
            {subscription?.subscription_started_at ? <p>Başlangıç: {formatDate(subscription.subscription_started_at)}</p> : null}
            {subscription?.current_period_end ? (
              <p>{subscription.cancel_at_period_end ? "Erişim sona eriyor" : "Yenilenme tarihi"}: {formatDate(subscription.current_period_end)}</p>
            ) : null}
            {subscription?.pending_plan_code && subscription?.pending_change_reason === "downgrade" ? (
              <p className="inline-result">
                {PLAN_LABELS[subscription.pending_plan_code] || subscription.pending_plan_code} planına geçiş{" "}
                {formatDate(subscription.pending_change_at)} tarihinde gerçekleşecek.
              </p>
            ) : null}
            {subscription?.pending_change_reason === "upgrade_pending_payment" ? (
              <p className="inline-result inline-result-warning">
                {PLAN_LABELS[subscription.pending_plan_code] || subscription.pending_plan_code} planına yükseltme ödeme onayı bekliyor
                (son tarih {formatDate(subscription.pending_change_at)}).
              </p>
            ) : null}
            {subscription?.cancel_at_period_end ? (
              <p className="inline-result inline-result-warning">
                İptal talep edildi; erişiminiz {formatDate(subscription.current_period_end)} tarihine kadar devam edecek, yenileme yapılmayacak.
              </p>
            ) : null}
            {subscription?.status === "past_due" ? (
              <p className="inline-result inline-result-warning">Son ödeme başarısız oldu. Lütfen ödeme yönteminizi güncelleyin.</p>
            ) : null}
            {subscription?.sync_error ? (
              <p className="inline-result inline-result-warning">Faturalandırma senkronizasyon hatası: {subscription.sync_error}</p>
            ) : null}
          </div>
        </Card>

        <Card title="Ödeme Yöntemi" className="span-4">
          <div className="settings-form">
            <p>Kart bilgileri ve fatura adresi Stripe üzerinden güvenle yönetilir.</p>
            <Button onClick={handlePortal} disabled={!hasSubscription || Boolean(busyAction)}>
              {busyAction === "portal" ? "Yönlendiriliyor..." : "Ödeme yöntemini yönet"}
            </Button>
          </div>
        </Card>

        {plan ? (
          <Card title="Plan / Kullanım" className="span-12">
            <div className="settings-form">
              <ul>
                <li>
                  Aylık kampanya: {plan.monthly_campaigns_used} / {plan.monthly_campaigns_limit ?? "Sınırsız"}
                </li>
                <li>Özel ürün limiti: {plan.private_products_limit ?? "Sınırsız"}</li>
                <li>Özel şablon limiti: {plan.private_templates_limit ?? "Sınırsız"}</li>
                <li>Çıktı formatları: {(plan.export_formats || []).join(", ").toUpperCase()}</li>
              </ul>
            </div>
          </Card>
        ) : null}

        <Card title="Plan Seçimi" className="span-12">
          <div className="page-actions">
            {PLAN_ORDER.map((planCode) => {
              const isCurrent = hasSubscription && currentPlanCode === planCode;
              const hasPendingUpgrade = subscription?.pending_change_reason === "upgrade_pending_payment";
              return (
                <Button
                  key={planCode}
                  variant={isCurrent ? "primary" : "secondary"}
                  disabled={!canManage || isCurrent || Boolean(busyAction) || (hasSubscription && hasPendingUpgrade)}
                  onClick={() => (hasSubscription ? handleChangePlan(planCode) : handleCheckout(planCode))}
                >
                  {isCurrent ? `${PLAN_LABELS[planCode]} (mevcut plan)` : hasSubscription ? `${PLAN_LABELS[planCode]} planına geç` : `${PLAN_LABELS[planCode]} planıyla başla`}
                </Button>
              );
            })}
          </div>
          {hasSubscription ? (
            <div className="page-actions">
              {subscription?.cancel_at_period_end ? (
                <Button onClick={handleResume} disabled={!canManage || Boolean(busyAction)}>
                  {busyAction === "resume" ? "İşleniyor..." : "Aboneliği devam ettir"}
                </Button>
              ) : (
                <Button variant="danger" onClick={() => setConfirm(true)} disabled={!canManage || Boolean(busyAction)}>
                  Aboneliği iptal et
                </Button>
              )}
            </div>
          ) : null}
          {!canManage ? <p className="inline-result">Plan işlemleri yalnızca market yöneticileri tarafından yapılabilir.</p> : null}
        </Card>

        <Card title="Fatura Geçmişi" className="span-12" action={<span className="card-summary">{invoices.length} fatura</span>}>
          <Table columns={["Tarih", "Numara", "Tutar", "Durum", "Bağlantı"]}>
            {invoices.map((invoice) => (
              <tr key={invoice.invoice_id}>
                <td>{formatDate(invoice.created_at)}</td>
                <td>{invoice.number || "-"}</td>
                <td>{formatMoney(invoice.total, invoice.currency)}</td>
                <td><StatusBadge status={invoiceStatusLabel(invoice)} /></td>
                <td>
                  {invoice.hosted_invoice_url ? (
                    <a href={invoice.hosted_invoice_url} target="_blank" rel="noreferrer">
                      Faturayı görüntüle
                    </a>
                  ) : (
                    "-"
                  )}
                </td>
              </tr>
            ))}
          </Table>
          {!loading && !invoices.length ? <p className="catalog-empty">Henüz fatura bulunmuyor.</p> : null}
        </Card>
      </section>

      <ConfirmDialog
        isOpen={Boolean(confirm)}
        title="Aboneliği iptal et"
        description="Abonelik dönem sonunda iptal edilecek; erişiminiz mevcut dönem bitene kadar devam edecek."
        confirmLabel="İptal et"
        onCancel={() => setConfirm(null)}
        onConfirm={handleCancel}
        isLoading={busyAction === "cancel"}
      />
    </>
  );
}
