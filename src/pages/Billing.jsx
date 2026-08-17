import { useEffect, useState } from "react";
import { canManageBilling } from "../api/authSession.js";
import {
  cancelBillingPlanChange,
  cancelBillingSubscription,
  changeBillingPlan,
  getBillingSubscription,
  getMarketPlan,
  getPublicPlans,
  listBillingInvoices,
  openBillingPortal,
  previewBillingPlanChange,
  resumeBillingSubscription,
  startBillingCheckout,
} from "../data/dataSource.js";
import { Button, Card, ConfirmDialog, Icon, PageHeader, PlanChangeModal, StatusBadge, Table } from "../components/ui/index.js";

const PLAN_LABELS = { starter: "Başlangıç", standard: "Plus", pro: "Pro", unassigned: "Atanmamış" };
const PLAN_ORDER = ["starter", "standard", "pro"];

// Mirrors backend CHECKOUT_BLOCKING_STATUSES (backend/app/services/billing/service.py)
// exactly: a subscription in one of these statuses is active or in-progress
// on Stripe, so a plan click may change it directly. Any other status —
// canceled/unpaid/incomplete_expired (backend DOWNGRADE_TO_UNASSIGNED_STATUSES)
// — or no subscription row at all is a terminal/absent lifecycle: a plan
// click must start a fresh Checkout instead (see PART B/H in
// docs/backend/09_STRIPE_BILLING_SANDBOX.md).
const CHANGEABLE_SUBSCRIPTION_STATUSES = new Set(["active", "trialing", "past_due", "incomplete", "paused"]);

// An "applied" plan change only means Stripe accepted the mutation — the
// local MarketSubscription mirror is written exclusively by webhook
// processing (see docs/backend/09_STRIPE_BILLING_SANDBOX.md), which can lag
// the mutation response by a second or more. Bounded re-fetch here instead
// of requiring a manual page refresh; never becomes unbounded polling.
const PLAN_SYNC_MAX_ATTEMPTS = 4;
const PLAN_SYNC_RETRY_DELAY_MS = 1500;

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

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
  return `${(unitAmount / 100).toFixed(2)} ${(currency || "").toUpperCase()}`.trim();
}

function formatPublicPlanPrice(publicPlan) {
  if (!publicPlan || publicPlan.monthly_price == null) return null;
  const symbol = publicPlan.currency === "EUR" ? "€" : ` ${publicPlan.currency}`;
  return `${publicPlan.monthly_price}${symbol}/ay`;
}

function invoiceStatusLabel(invoice) {
  if (invoice.payment_failed) return "Ödeme başarısız";
  const map = { paid: "Ödendi", open: "Açık", draft: "Taslak", uncollectible: "Tahsil edilemedi", void: "İptal" };
  return map[invoice.status] || invoice.status || "-";
}

function usageTone(ratio) {
  if (ratio === null) return "success";
  if (ratio >= 0.9) return "danger";
  if (ratio >= 0.7) return "warning";
  return "success";
}

function UsageCard({ label, icon, used, limit, formats }) {
  const hasUsage = typeof used === "number";
  const isUnlimited = limit === null || limit === undefined;
  const ratio = hasUsage && !isUnlimited && limit > 0 ? Math.min(1, used / limit) : null;
  const tone = usageTone(ratio);

  return (
    <section className={`metric-card usage-card metric-${tone}`}>
      <div className="metric-top">
        <span>
          <Icon name={icon} />
        </span>
      </div>
      <p>{label}</p>
      {formats ? (
        <div className="usage-format-list">
          {formats.length ? (
            formats.map((format) => (
              <span key={format} className="badge badge-neutral">
                {format.toUpperCase()}
              </span>
            ))
          ) : (
            <span className="usage-empty">-</span>
          )}
        </div>
      ) : (
        <>
          <strong>{hasUsage ? `${used} / ${isUnlimited ? "Sınırsız" : limit}` : isUnlimited ? "Sınırsız" : limit}</strong>
          {ratio !== null ? (
            <div
              className="usage-bar"
              role="progressbar"
              aria-valuenow={Math.round(ratio * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className={`usage-bar-fill usage-bar-${tone}`} style={{ width: `${Math.round(ratio * 100)}%` }} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

export function Billing({ checkoutStatus = "" }) {
  const canManage = canManageBilling();
  const [subscription, setSubscription] = useState(null);
  const [plan, setPlan] = useState(null);
  const [publicPlans, setPublicPlans] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [confirmPlanChangeCancel, setConfirmPlanChangeCancel] = useState(null);
  const [planChange, setPlanChange] = useState(null);
  const [showCheckoutSuccess] = useState(checkoutStatus === "success");
  const [pendingSync, setPendingSync] = useState(false);

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
      return subscriptionResult;
    } catch (e) {
      setError(e?.message || "Faturalandırma bilgileri yüklenemedi.");
      return null;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    getPublicPlans()
      .then((result) => setPublicPlans(Array.isArray(result) ? result : []))
      .catch(() => setPublicPlans([]));
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
    if (busyAction) return null;
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

  function openPlanChangeModal(planCode) {
    if (planChange || busyAction) return;
    setError("");
    setPlanChange({ targetPlanCode: planCode, preview: null, isLoadingPreview: true, error: "", isConfirming: false });
    previewBillingPlanChange(planCode)
      .then((preview) => {
        setPlanChange((current) =>
          current && current.targetPlanCode === planCode ? { ...current, preview, isLoadingPreview: false } : current,
        );
      })
      .catch((e) => {
        setPlanChange((current) =>
          current && current.targetPlanCode === planCode
            ? { ...current, isLoadingPreview: false, error: e?.message || "Önizleme alınamadı." }
            : current,
        );
      });
  }

  function closePlanChangeModal() {
    setPlanChange((current) => (current?.isConfirming ? current : null));
  }

  async function confirmPlanChange() {
    if (!planChange || planChange.isConfirming) return;
    const { targetPlanCode } = planChange;
    setPlanChange({ ...planChange, isConfirming: true, isSyncing: false, error: "" });
    setPendingSync(false);
    try {
      const result = await changeBillingPlan(targetPlanCode);

      if (result?.status === "pending_payment") {
        setPlanChange(null);
        setMessage(`Yükseltme ödeme onayı bekliyor. Son tarih: ${formatDate(result.expires_at)}.`);
        await load();
        return;
      }

      if (result?.status === "scheduled") {
        // Downgrades never take effect immediately (see change_plan) — the
        // plan stays as-is until the scheduled phase transition. The mutation
        // response already carries the correct schedule, but the local
        // MarketSubscription mirror is written by the same request handler
        // and a read immediately after write can still race the commit
        // becoming visible. Bounded re-fetch here instead of trusting a
        // single unchecked load() (see the "applied" branch below).
        setPlanChange((current) => (current ? { ...current, isSyncing: true } : current));
        let downgradeSynced = false;
        for (let attempt = 0; attempt < PLAN_SYNC_MAX_ATTEMPTS && !downgradeSynced; attempt++) {
          if (attempt > 0) await wait(PLAN_SYNC_RETRY_DELAY_MS);
          const subscriptionResult = await load();
          downgradeSynced =
            subscriptionResult?.plan_code === currentPlanCode &&
            subscriptionResult?.pending_plan_code === targetPlanCode &&
            Boolean(subscriptionResult?.pending_change_at);
        }
        setPlanChange(null);
        setPendingSync(!downgradeSynced);
        setMessage(
          downgradeSynced
            ? `Plan değişikliği ${formatDate(result.effective_at)} tarihinde geçerli olacak.`
            : "Plan değişikliğiniz alındı. Bilgileriniz birkaç saniye içinde güncellenecek.",
        );
        return;
      }

      // status === "applied": Stripe confirmed the upgrade, but the local
      // mirror only updates once the resulting webhook lands. Keep the
      // modal open with a "processing" state and poll a bounded number of
      // times instead of requiring a manual page refresh.
      setPlanChange((current) => (current ? { ...current, isSyncing: true } : current));
      let synced = false;
      for (let attempt = 0; attempt < PLAN_SYNC_MAX_ATTEMPTS && !synced; attempt++) {
        if (attempt > 0) await wait(PLAN_SYNC_RETRY_DELAY_MS);
        const subscriptionResult = await load();
        synced = subscriptionResult?.plan_code === targetPlanCode;
      }
      setPlanChange(null);
      setPendingSync(!synced);
      setMessage(
        synced
          ? `${PLAN_LABELS[targetPlanCode] || targetPlanCode} planınız etkinleştirildi.`
          : "Ödemeniz alındı. Plan bilgileriniz birkaç saniye içinde güncellenecek.",
      );
    } catch (e) {
      setPlanChange({ ...planChange, isConfirming: false, isSyncing: false, error: e?.message || "Plan değişikliği uygulanamadı." });
    }
  }

  async function handleManualSync() {
    const subscriptionResult = await load();
    if (subscriptionResult) {
      setPendingSync(false);
      setMessage("Plan bilgileri güncellendi.");
    }
  }

  async function handlePortal() {
    const result = await runAction("portal", () => openBillingPortal());
    if (result?.portal_url) window.location.href = result.portal_url;
  }

  // Cancel/resume mutate cancel_at_period_end (and, for cancel, release any
  // pending downgrade schedule), but the local MarketSubscription mirror is
  // only written once the resulting webhook lands — the same race as the
  // upgrade/downgrade sync above. A single unchecked load() after the
  // mutation can read the pre-webhook row and show stale state until a
  // manual refresh. Bounded re-fetch here instead, shared by both actions.
  async function runActionWithSync(actionKey, fn, isConverged, { convergedMessage, pendingMessage }) {
    if (busyAction) return null;
    setBusyAction(actionKey);
    setError("");
    setMessage("");
    try {
      await fn();
      let converged = false;
      for (let attempt = 0; attempt < PLAN_SYNC_MAX_ATTEMPTS && !converged; attempt++) {
        if (attempt > 0) await wait(PLAN_SYNC_RETRY_DELAY_MS);
        const subscriptionResult = await load();
        converged = isConverged(subscriptionResult);
      }
      setPendingSync(!converged);
      setMessage(converged ? convergedMessage : pendingMessage);
      return converged;
    } catch (e) {
      setError(e?.message || "İşlem başarısız oldu.");
      return null;
    } finally {
      setBusyAction("");
    }
  }

  async function handleCancel() {
    setConfirm(null);
    await runActionWithSync(
      "cancel",
      () => cancelBillingSubscription(),
      (s) =>
        s?.cancel_at_period_end === true &&
        s?.pending_plan_code == null &&
        s?.pending_change_reason == null &&
        s?.pending_change_at == null,
      {
        convergedMessage: "İptal talebiniz alındı; dönem sonuna kadar erişiminiz devam edecek.",
        pendingMessage: "İptal talebiniz alındı. Bilgileriniz birkaç saniye içinde güncellenecek.",
      },
    );
  }

  async function handleResume() {
    await runActionWithSync(
      "resume",
      () => resumeBillingSubscription(),
      (s) => s?.cancel_at_period_end === false,
      {
        convergedMessage: "Abonelik yenilemesi yeniden etkinleştirildi.",
        pendingMessage: "Abonelik yenilemesi işleniyor. Bilgileriniz birkaç saniye içinde güncellenecek.",
      },
    );
  }

  // Undo for a scheduled downgrade (see docs/backend/09_STRIPE_BILLING_SANDBOX.md):
  // only releases the Stripe SubscriptionSchedule, never mutates the current
  // plan directly — so convergence must also confirm plan_code held steady,
  // not just that the pending_* fields cleared (no optimistic entitlement change).
  async function handleCancelPlanChange() {
    setConfirmPlanChangeCancel(null);
    const planBeforeCancel = currentPlanCode;
    await runActionWithSync(
      "cancel-plan-change",
      () => cancelBillingPlanChange(),
      (s) =>
        s?.pending_plan_code == null &&
        s?.pending_change_reason == null &&
        s?.pending_change_at == null &&
        s?.plan_code === planBeforeCancel,
      {
        convergedMessage: `Plan değişikliği iptal edildi. ${PLAN_LABELS[planBeforeCancel] || planBeforeCancel} planınız devam edecek.`,
        pendingMessage: "Plan değişikliği iptali alındı. Bilgileriniz birkaç saniye içinde güncellenecek.",
      },
    );
  }

  // A subscription row existing at all (any status, including terminal ones
  // like "canceled") is enough to justify Customer Portal access for invoice
  // history/payment method management — see PART F. It is NOT enough to
  // justify plan-change routing; that requires `isActiveSubscription` below.
  const hasSubscriptionRow = Boolean(subscription?.status);
  const isActiveSubscription = hasSubscriptionRow && CHANGEABLE_SUBSCRIPTION_STATUSES.has(subscription.status);
  const currentPlanCode = subscription?.plan_code || "unassigned";
  const publicPlanByCode = Object.fromEntries(publicPlans.map((item) => [item.code, item]));

  return (
    <>
      <PageHeader title="Faturalandırma" description="Abonelik planınızı, ödeme yönteminizi ve fatura geçmişinizi tek yerden yönetin." />
      {showCheckoutSuccess ? (
        <p className="inline-result inline-result-success billing-alert" role="status">
          <Icon name="check" /> Ödeme başarıyla tamamlandı. Aboneliğiniz etkinleştirildi.
        </p>
      ) : null}
      {error ? (
        <p className="inline-result inline-result-danger billing-alert" role="alert">
          <Icon name="alert" /> {error}
        </p>
      ) : null}
      {message ? (
        <p className="inline-result inline-result-success billing-alert" role="status">
          <Icon name="check" /> {message}
          {pendingSync ? (
            <Button variant="secondary" className="billing-inline-refresh" onClick={handleManualSync}>
              Yenile
            </Button>
          ) : null}
        </p>
      ) : null}
      {loading ? <p className="inline-result">Yükleniyor...</p> : null}

      <section className="dashboard-grid">
        <Card title="Mevcut Abonelik" className="span-8">
          <div className="billing-plan-card">
            <div className="billing-plan-heading">
              <strong>{PLAN_LABELS[currentPlanCode] || currentPlanCode}</strong>
              <StatusBadge status={statusLabel(subscription?.status)} />
            </div>
            {isActiveSubscription ? (
              <>
                {subscription?.unit_amount ? (
                  <p className="billing-plan-price">
                    Aylık ücret: <strong>{formatMoney(subscription.unit_amount, subscription.currency)}</strong>
                  </p>
                ) : null}

                <ul className="billing-fact-list">
                  {subscription?.subscription_started_at ? (
                    <li>
                      <Icon name="calendar" /> Başlangıç: <strong>{formatDate(subscription.subscription_started_at)}</strong>
                    </li>
                  ) : null}
                  {subscription?.current_period_end ? (
                    <li>
                      <Icon name="calendar" /> {subscription.cancel_at_period_end ? "Erişim sona eriyor" : "Yenilenme tarihi"}: <strong>{formatDate(subscription.current_period_end)}</strong>
                    </li>
                  ) : null}
                </ul>

                {subscription?.pending_plan_code && subscription?.pending_change_reason === "downgrade" ? (
                  <p className="inline-result billing-alert">
                    <Icon name="refresh" /> {PLAN_LABELS[subscription.pending_plan_code] || subscription.pending_plan_code} planına
                    geçiş {formatDate(subscription.pending_change_at)} tarihinde gerçekleşecek.
                    <Button
                      variant="secondary"
                      className="billing-inline-refresh"
                      disabled={!canManage || Boolean(busyAction)}
                      onClick={() => setConfirmPlanChangeCancel(true)}
                    >
                      {busyAction === "cancel-plan-change" ? "İşleniyor..." : "Plan değişikliğini iptal et"}
                    </Button>
                  </p>
                ) : null}
                {subscription?.pending_change_reason === "upgrade_pending_payment" ? (
                  <p className="inline-result inline-result-warning billing-alert">
                    <Icon name="alert" /> {PLAN_LABELS[subscription.pending_plan_code] || subscription.pending_plan_code} planına
                    yükseltme ödeme onayı bekliyor (son tarih {formatDate(subscription.pending_change_at)}).
                  </p>
                ) : null}
                {subscription?.cancel_at_period_end ? (
                  <p className="inline-result inline-result-warning billing-alert">
                    <Icon name="alert" /> İptal talep edildi; erişiminiz {formatDate(subscription.current_period_end)} tarihine
                    kadar devam edecek, yenileme yapılmayacak.
                  </p>
                ) : null}
                {subscription?.status === "past_due" ? (
                  <p className="inline-result inline-result-warning billing-alert">
                    <Icon name="alert" /> Son ödeme başarısız oldu. Lütfen ödeme yönteminizi güncelleyin.
                  </p>
                ) : null}
              </>
            ) : (
              <>
                <p className="inline-result billing-alert" role="status">
                  <Icon name="refresh" /> Aktif abonelik yok. Devam etmek için aşağıdan bir plan seçin.
                </p>
                {subscription?.canceled_at ? (
                  <ul className="billing-fact-list">
                    <li>
                      <Icon name="calendar" /> Son aboneliğiniz <strong>{formatDate(subscription.canceled_at)}</strong> tarihinde iptal edildi.
                    </li>
                  </ul>
                ) : null}
              </>
            )}
            {subscription?.sync_error ? (
              <p className="inline-result inline-result-warning billing-alert">
                <Icon name="alert" /> Faturalandırma senkronizasyon hatası: {subscription.sync_error}
              </p>
            ) : null}
          </div>
        </Card>

        <Card title="Ödeme Yöntemi" className="span-4">
          <p className="billing-payment-copy">
            <Icon name="creditCard" /> Kart bilgileri ve fatura adresi Stripe üzerinden güvenle yönetilir.
          </p>
          <Button onClick={handlePortal} disabled={!hasSubscriptionRow || Boolean(busyAction)}>
            {busyAction === "portal" ? "Yönlendiriliyor..." : "Ödeme yöntemini yönet"}
          </Button>
        </Card>

        {plan ? (
          <Card title="Plan / Kullanım" className="span-12">
            {plan.code === "unassigned" ? (
              <p className="catalog-empty">Aktif plan yok. Plan seçtiğinizde kullanım limitleri burada görüntülenecek.</p>
            ) : (
              <div className="metric-grid">
                <UsageCard
                  label="Aylık kampanya"
                  icon="megaphone"
                  used={plan.monthly_campaigns_used}
                  limit={plan.monthly_campaigns_limit}
                />
                <UsageCard label="Özel ürün limiti" icon="box" limit={plan.private_products_limit} />
                <UsageCard label="Özel şablon limiti" icon="layoutTemplate" limit={plan.private_templates_limit} />
                <UsageCard label="Çıktı formatları" icon="file" formats={plan.export_formats || []} />
              </div>
            )}
          </Card>
        ) : null}

        <Card title="Plan Seçimi" className="span-12">
          <div className="plan-picker-grid">
            {PLAN_ORDER.map((planCode) => {
              const isCurrent = isActiveSubscription && currentPlanCode === planCode;
              const hasPendingUpgrade = subscription?.pending_change_reason === "upgrade_pending_payment";
              const publicPlan = publicPlanByCode[planCode];
              const priceLabel = formatPublicPlanPrice(publicPlan);
              return (
                <div key={planCode} className={`plan-option-card ${isCurrent ? "is-current" : ""}`.trim()}>
                  <div className="plan-option-heading">
                    <strong>{PLAN_LABELS[planCode]}</strong>
                    {isCurrent ? <StatusBadge status="Mevcut plan" /> : null}
                  </div>
                  {priceLabel ? <p className="plan-option-price">{priceLabel}</p> : null}
                  {publicPlan?.tagline ? <p className="plan-option-price">{publicPlan.tagline}</p> : null}
                  <Button
                    variant={isCurrent ? "secondary" : "primary"}
                    disabled={!canManage || isCurrent || Boolean(busyAction) || Boolean(planChange) || (isActiveSubscription && hasPendingUpgrade)}
                    onClick={() => (isActiveSubscription ? openPlanChangeModal(planCode) : handleCheckout(planCode))}
                  >
                    {isCurrent ? "Mevcut planınız" : isActiveSubscription ? `${PLAN_LABELS[planCode]} planına geç` : `${PLAN_LABELS[planCode]} planıyla başla`}
                  </Button>
                </div>
              );
            })}
          </div>
          {isActiveSubscription ? (
            <div className="page-actions billing-cancel-row">
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
          {invoices.length ? (
            <Table columns={["Tarih", "Numara", "Tutar", "Durum", "Bağlantı"]}>
              {invoices.map((invoice) => (
                <tr key={invoice.invoice_id}>
                  <td>{formatDate(invoice.created_at)}</td>
                  <td>{invoice.number || "-"}</td>
                  <td>{formatMoney(invoice.total, invoice.currency)}</td>
                  <td>
                    <StatusBadge status={invoiceStatusLabel(invoice)} />
                  </td>
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
          ) : !loading ? (
            <p className="catalog-empty">Henüz fatura bulunmuyor.</p>
          ) : null}
        </Card>
      </section>

      <PlanChangeModal
        isOpen={Boolean(planChange)}
        currentPlanLabel={PLAN_LABELS[currentPlanCode] || currentPlanCode}
        targetPlanLabel={planChange ? PLAN_LABELS[planChange.targetPlanCode] || planChange.targetPlanCode : ""}
        preview={planChange?.preview || null}
        isLoadingPreview={Boolean(planChange?.isLoadingPreview)}
        error={planChange?.error || ""}
        isConfirming={Boolean(planChange?.isConfirming)}
        isSyncing={Boolean(planChange?.isSyncing)}
        onConfirm={confirmPlanChange}
        onCancel={closePlanChangeModal}
        formatMoney={formatMoney}
        formatDate={formatDate}
      />

      <ConfirmDialog
        isOpen={Boolean(confirm)}
        title="Aboneliği iptal et"
        description="Abonelik dönem sonunda iptal edilecek; erişiminiz mevcut dönem bitene kadar devam edecek."
        confirmLabel="İptal et"
        onCancel={() => setConfirm(null)}
        onConfirm={handleCancel}
        isLoading={busyAction === "cancel"}
      />

      <ConfirmDialog
        isOpen={Boolean(confirmPlanChangeCancel)}
        title="Plan değişikliğini iptal et"
        description={`${PLAN_LABELS[subscription?.pending_plan_code] || subscription?.pending_plan_code || ""} planına planlanan geçiş iptal edilecek ve mevcut ${PLAN_LABELS[currentPlanCode] || currentPlanCode} planınız devam edecek.`}
        confirmLabel="Plan değişikliğini iptal et"
        onCancel={() => setConfirmPlanChangeCancel(null)}
        onConfirm={handleCancelPlanChange}
        isLoading={busyAction === "cancel-plan-change"}
      />
    </>
  );
}
