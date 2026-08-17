import { Button } from "./Button.jsx";
import { Modal } from "./Modal.jsx";

export function PlanChangeModal({
  isOpen,
  currentPlanLabel,
  targetPlanLabel,
  preview,
  isLoadingPreview,
  error,
  isConfirming,
  onConfirm,
  onCancel,
  formatMoney,
  formatDate,
}) {
  if (!isOpen) return null;

  const hasImmediateCharge = Boolean(preview && preview.immediate_amount_due > 0);
  const canConfirm = Boolean(preview) && !isLoadingPreview && !error && !isConfirming;

  return (
    <Modal
      title={`${targetPlanLabel} planına geç`}
      description={`${currentPlanLabel} planından ${targetPlanLabel} planına geçiş yapıyorsunuz.`}
      onClose={isConfirming ? undefined : onCancel}
      className="plan-change-modal-panel"
      footer={
        <>
          <Button onClick={onCancel} disabled={isConfirming}>
            Vazgeç
          </Button>
          <Button variant="primary" onClick={onConfirm} disabled={!canConfirm} autoFocus>
            {isConfirming ? "Uygulanıyor..." : "Değişikliği onayla"}
          </Button>
        </>
      }
    >
      {isLoadingPreview ? (
        <p className="inline-result billing-alert" role="status">
          Önizleme hazırlanıyor...
        </p>
      ) : null}
      {error ? (
        <p className="inline-result inline-result-danger billing-alert" role="alert">
          {error}
        </p>
      ) : null}
      {preview ? (
        <div className="plan-change-summary">
          <div className="plan-change-row-plans">
            <div>
              <span className="plan-change-label">Mevcut plan</span>
              <strong>{currentPlanLabel}</strong>
            </div>
            <div className="plan-change-arrow" aria-hidden="true">
              →
            </div>
            <div>
              <span className="plan-change-label">Yeni plan</span>
              <strong>{targetPlanLabel}</strong>
            </div>
          </div>

          <div className="plan-change-row">
            <span>Bugün tahsil edilecek tutar</span>
            <strong className={hasImmediateCharge ? "plan-change-amount-charge" : ""}>
              {hasImmediateCharge ? formatMoney(preview.immediate_amount_due, preview.currency) : "Ek ücret yok"}
            </strong>
          </div>

          <p className="plan-change-explanation">{preview.explanation}</p>

          <div className="plan-change-row">
            <span>Bir sonraki yenileme tarihi</span>
            <strong>{formatDate(preview.next_renewal_date)}</strong>
          </div>
          <div className="plan-change-row">
            <span>Bir sonraki yenilemede aylık ücret</span>
            <strong>{formatMoney(preview.next_renewal_amount, preview.currency)}</strong>
          </div>

          {preview.line_items?.length ? (
            <details className="plan-change-details">
              <summary>Hesaplama detayları</summary>
              <ul>
                {preview.line_items.map((item, index) => (
                  <li key={index}>
                    <span>{item.description}</span>
                    <span>{formatMoney(item.amount, preview.currency)}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {preview.is_estimate ? (
            <p className="plan-change-note">
              Tutarlar Stripe önizlemesine dayanır; onay anında ödeme yönteminize bağlı olarak çok az farklılık
              gösterebilir.
            </p>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}
