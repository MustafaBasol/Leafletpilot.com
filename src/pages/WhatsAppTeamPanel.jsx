import { useEffect, useState } from "react";
import {
  cancelWhatsAppVerification,
  createWhatsAppVerification,
  getWhatsAppChannelStatus,
  getWhatsAppVerification,
  revokeMemberWhatsApp,
} from "../api/whatsappApi.js";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, Modal, Table } from "../components/ui/index.js";
import {
  buildWhatsAppDeepLink,
  describeFailureReason,
  formatCountdown,
  formatWhatsAppStatus,
  MEMBER_ACTIONABLE_STATUSES,
  secondsUntil,
} from "./whatsappStatus.js";

const roleLabels = {
  market_admin: "Yönetici",
  market_staff: "Personel",
  viewer: "Görüntüleyici",
};

const memberColumns = [
  { label: "Kullanıcı", minWidth: "180px" },
  { label: "Rol", width: "14%", minWidth: "110px" },
  { label: "WhatsApp Durumu", width: "16%", minWidth: "150px" },
  { label: "Doğrulanmış Numara", width: "18%", minWidth: "160px" },
  { label: "Doğrulama Tarihi", width: "16%", minWidth: "150px" },
  { label: "Aksiyonlar", width: "24%", minWidth: "220px" },
];

// Terminal states — the code is gone and the only path forward is generating a new one.
const RESTARTABLE_STATUSES = new Set(["expired", "failed", "cancelled"]);

export function WhatsAppTeamPanel() {
  const [status, setStatus] = useState(null);
  const [isLoading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [verifyTarget, setVerifyTarget] = useState(null);
  const [verification, setVerification] = useState(null);
  const [phoneInput, setPhoneInput] = useState("");
  const [typedPhone, setTypedPhone] = useState("");
  const [isCreating, setCreating] = useState(false);
  const [isCancelling, setCancelling] = useState(false);
  const [modalError, setModalError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [copyError, setCopyError] = useState("");
  const [nowMs, setNowMs] = useState(() => Date.now());

  const [revokeTarget, setRevokeTarget] = useState(null);
  const [isRevoking, setRevoking] = useState(false);

  async function load() {
    setLoading(true);
    setLoadError("");
    try {
      const result = await getWhatsAppChannelStatus();
      setStatus(result);
    } catch (err) {
      setLoadError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Countdown tick — refreshes the visible expiry countdown and resend-cooldown label every second.
  // Cleared whenever the modal closes, the verification changes, or the component unmounts.
  useEffect(() => {
    if (!verifyTarget || !verification) return undefined;
    const tickId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(tickId);
  }, [verifyTarget, verification?.verification_id, verification?.status]);

  // Poll the verification every 5s while it is live. Stops the moment the status leaves "pending",
  // the local countdown hits zero, the modal closes (verification becomes null) or on unmount.
  useEffect(() => {
    if (!verification || verification.status !== "pending") return undefined;
    const pollId = window.setInterval(() => {
      const remaining = secondsUntil(verification.expires_at, Date.now());
      if (remaining !== null && remaining <= 0) {
        window.clearInterval(pollId);
        return;
      }
      getWhatsAppVerification(verification.verification_id)
        .then((latest) => {
          setVerification((prev) => (prev ? { ...prev, ...latest, code: prev.code } : latest));
          if (latest.status === "verified") {
            load();
          }
        })
        .catch(() => {
          // Transient poll failures stay silent — the panel keeps showing the last known state.
        });
    }, 5000);
    return () => window.clearInterval(pollId);
  }, [verification?.verification_id, verification?.status]);

  function openVerifyModal(member) {
    setVerifyTarget(member);
    setVerification(null);
    setPhoneInput("");
    setTypedPhone("");
    setModalError("");
    setCopyMessage("");
    setCopyError("");
  }

  function closeModal() {
    // Closing must NOT cancel a live code. The realistic flow is: the admin
    // reads the code out, closes the dialog, and the user walks to their phone
    // — silently invalidating the code there would break the feature. The
    // challenge simply expires on its own, and the members table keeps showing
    // "Doğrulama bekleniyor" so the state stays visible. Cancelling is an
    // explicit action instead (see "Doğrulamayı İptal Et" below).
    setVerifyTarget(null);
    setVerification(null);
    setPhoneInput("");
    setTypedPhone("");
    setModalError("");
    load();
  }

  async function handleCancelVerification() {
    if (!verification) return;
    setCancelling(true);
    setModalError("");
    try {
      await cancelWhatsAppVerification(verification.verification_id);
      setVerifyTarget(null);
      setVerification(null);
      await load();
    } catch (err) {
      setModalError(err.message);
    } finally {
      setCancelling(false);
    }
  }

  async function handleCreateVerification(member, phone) {
    setCreating(true);
    setModalError("");
    try {
      const trimmedPhone = phone ? phone.trim() : "";
      const created = await createWhatsAppVerification({
        membership_id: member.membership_id,
        phone: trimmedPhone || null,
      });
      setVerification({ ...created, status: "pending" });
      setTypedPhone(trimmedPhone);
      setCopyMessage("");
      setCopyError("");
    } catch (err) {
      setModalError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleCopyCode() {
    if (!verification?.code) return;
    setCopyMessage("");
    setCopyError("");
    try {
      await navigator.clipboard.writeText(verification.code);
      setCopyMessage("Kod panoya kopyalandı.");
      window.setTimeout(() => setCopyMessage(""), 2000);
    } catch {
      setCopyError("Kod kopyalanamadı. Kodu elle seçip kopyalayın.");
    }
  }

  function requestRevoke(member) {
    setRevokeTarget(member);
  }

  async function confirmRevoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    try {
      await revokeMemberWhatsApp(revokeTarget.membership_id, null);
      setRevokeTarget(null);
      await load();
    } catch (err) {
      setLoadError(err.message);
    } finally {
      setRevoking(false);
    }
  }

  if (isLoading) {
    return (
      <Card title="WhatsApp Ekip Erişimi">
        <p className="inline-result">Yükleniyor...</p>
      </Card>
    );
  }

  if (loadError) {
    return (
      <Card title="WhatsApp Ekip Erişimi">
        <p className="inline-result inline-result-warning" role="alert">{loadError}</p>
        <Button onClick={load}>Tekrar dene</Button>
      </Card>
    );
  }

  if (!status?.enabled) {
    return (
      <Card title="WhatsApp Ekip Erişimi">
        <EmptyState
          title="WhatsApp kanalı henüz etkin değil"
          text="WhatsApp kanalı henüz etkin değil. Etkinleştirildiğinde ekip üyeleri buradan numaralarını doğrulayabilecek."
        />
      </Card>
    );
  }

  const members = status.members || [];
  const remainingSeconds = verification ? secondsUntil(verification.expires_at, nowMs) : null;
  const effectiveStatus =
    verification && verification.status === "pending" && remainingSeconds === 0 ? "expired" : verification?.status;
  const resendCooldownRemaining = verification ? secondsUntil(verification.resend_available_at, nowMs) || 0 : 0;

  return (
    <Card title="WhatsApp Ekip Erişimi" action={<span className="card-summary">{members.length} üye</span>}>
      <p className="table-hint">
        LeafletPilot numarası: <strong>{status.official_number_display}</strong>
      </p>
      {!members.length ? (
        <EmptyState title="Henüz üye yok" text="Ekip üyeleri eklendikçe WhatsApp doğrulama durumları burada listelenecek." />
      ) : (
        <Table columns={memberColumns}>
          {members.map((member) => {
            const canActOnMember = Boolean(status.can_manage_members || member.can_manage);
            const { label, tone } = formatWhatsAppStatus(member.status);
            // A pending row also gets an action: the previous code is only ever
            // shown once, so "generate a fresh one" (which supersedes the old
            // challenge server-side) is the only way to recover from a code the
            // admin no longer has.
            const showVerifyAction =
              MEMBER_ACTIONABLE_STATUSES.has(member.status) || member.status === "pending";
            const showRevokeAction = member.status === "verified";
            return (
              <tr key={member.membership_id}>
                <td>
                  <strong>{member.full_name || member.email}</strong>
                  <small>{member.email}</small>
                </td>
                <td>{roleLabels[member.role] || member.role}</td>
                <td>
                  <Badge tone={tone}>{label}</Badge>
                  {member.status === "pending" && member.pending_expires_at ? (
                    <small className="table-hint">
                      Son geçerlilik: {new Date(member.pending_expires_at).toLocaleTimeString("tr-TR")}
                    </small>
                  ) : null}
                </td>
                <td>{member.verified_phone || member.verified_phone_masked || "—"}</td>
                <td>{member.verified_at ? new Date(member.verified_at).toLocaleString("tr-TR") : "—"}</td>
                <td className="table-actions">
                  {canActOnMember ? (
                    <>
                      {showVerifyAction ? (
                        <Button onClick={() => openVerifyModal(member)}>
                          {member.status === "pending" ? "Yeni Kod Oluştur" : "WhatsApp ile Doğrula"}
                        </Button>
                      ) : null}
                      {showRevokeAction ? (
                        <Button variant="danger" onClick={() => requestRevoke(member)}>WhatsApp Erişimini Kaldır</Button>
                      ) : null}
                    </>
                  ) : (
                    showVerifyAction || showRevokeAction ? (
                      <small className="table-hint">Bu kaydı yalnızca market yöneticisi yönetebilir.</small>
                    ) : null
                  )}
                </td>
              </tr>
            );
          })}
        </Table>
      )}

      {verifyTarget ? (
        <Modal
          title="WhatsApp Doğrulama"
          description={`${verifyTarget.full_name || verifyTarget.email} için WhatsApp numarası doğrulanıyor.`}
          onClose={closeModal}
          className="whatsapp-verify-modal"
        >
          {modalError ? <p className="inline-result inline-result-warning" role="alert">{modalError}</p> : null}
          {!verification ? (
            <div className="field-stack">
              <Input
                label="Telefon (isteğe bağlı)"
                value={phoneInput}
                onChange={(event) => setPhoneInput(event.target.value)}
                placeholder="+90 5xx xxx xx xx"
              />
              <Button
                variant="primary"
                onClick={() => handleCreateVerification(verifyTarget, phoneInput)}
                disabled={isCreating}
              >
                {isCreating ? "Oluşturuluyor..." : "Kod Oluştur"}
              </Button>
            </div>
          ) : (
            <div className="whatsapp-verify-panel field-stack">
              <p className="whatsapp-verify-subject">
                Doğrulanan kullanıcı: <strong>{verifyTarget.full_name || verifyTarget.email}</strong>
                <small>{verifyTarget.email}</small>
              </p>

              {effectiveStatus === "pending" ? (
                <>
                  <p className="whatsapp-official-number">
                    LeafletPilot numarası:{" "}
                    <strong>{verification.official_number_display || status.official_number_display}</strong>
                  </p>
                  <div className="whatsapp-code-block">
                    <span className="whatsapp-code">{verification.code}</span>
                    <Button onClick={handleCopyCode}>{copyMessage ? "Kopyalandı" : "Kodu Kopyala"}</Button>
                  </div>
                  {copyMessage ? <p className="inline-result" role="status">{copyMessage}</p> : null}
                  {copyError ? <p className="inline-result inline-result-warning" role="alert">{copyError}</p> : null}
                  <p className="table-hint">
                    Aşağıdaki doğrulama kodunu KENDİ WhatsApp hesabınızdan LeafletPilot numarasına gönderin.
                  </p>
                  <a
                    className="button button-secondary"
                    href={
                      verification.whatsapp_deep_link ||
                      buildWhatsAppDeepLink(verification.official_number, verification.code)
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    WhatsApp'ta Aç
                  </a>
                  <div className="whatsapp-countdown-row">
                    <span>Kalan süre: {formatCountdown(remainingSeconds)}</span>
                  </div>
                  {verification.failure_reason ? (
                    // A still-pending challenge can carry a reason when the
                    // code arrived from the wrong handset — recoverable, so
                    // the countdown keeps running and the user can resend.
                    <p className="inline-result inline-result-warning" role="alert">
                      {describeFailureReason(verification.failure_reason)}
                    </p>
                  ) : (
                    <p className="inline-result" role="status">Doğrulama bekleniyor...</p>
                  )}
                  <p className="table-hint">
                    Bu pencereyi kapatabilirsiniz; kod süresi dolana kadar geçerli kalır. Kod yalnızca bir kez
                    gösterilir.
                  </p>
                  <Button onClick={handleCancelVerification} disabled={isCancelling}>
                    {isCancelling ? "İptal ediliyor..." : "Doğrulamayı İptal Et"}
                  </Button>
                </>
              ) : null}

              {effectiveStatus === "verified" ? (
                <>
                  <p className="inline-result" role="status">WhatsApp numarası doğrulandı.</p>
                  <p>
                    Doğrulanan numara:{" "}
                    <strong>{verification.verified_phone || verification.verified_phone_masked || "—"}</strong>
                  </p>
                  {typedPhone && verification.verified_phone && typedPhone !== verification.verified_phone ? (
                    <p className="table-hint">
                      Doğrulanan numara girilen numaradan farklı. WhatsApp hesabının gerçek numarası kaydedildi.
                    </p>
                  ) : null}
                  <Button variant="primary" onClick={closeModal}>Kapat</Button>
                </>
              ) : null}

              {RESTARTABLE_STATUSES.has(effectiveStatus) ? (
                <>
                  <p className="inline-result inline-result-warning" role="alert">
                    {describeFailureReason(verification.failure_reason)}
                  </p>
                  <Button
                    variant="primary"
                    onClick={() => handleCreateVerification(verifyTarget, typedPhone)}
                    disabled={isCreating || resendCooldownRemaining > 0}
                  >
                    {resendCooldownRemaining > 0
                      ? `Yeni kod oluştur (${resendCooldownRemaining}sn)`
                      : isCreating
                        ? "Oluşturuluyor..."
                        : "Yeni kod oluştur"}
                  </Button>
                </>
              ) : null}
            </div>
          )}
        </Modal>
      ) : null}

      <ConfirmDialog
        isOpen={Boolean(revokeTarget)}
        title="WhatsApp erişimini kaldır"
        description={
          revokeTarget
            ? `${revokeTarget.full_name || revokeTarget.email} için WhatsApp erişimi kaldırılsın mı? Kullanıcı WhatsApp komut erişimini anında kaybedecek.`
            : ""
        }
        confirmLabel="Erişimi Kaldır"
        onCancel={() => setRevokeTarget(null)}
        onConfirm={confirmRevoke}
        isLoading={isRevoking}
      />
    </Card>
  );
}
