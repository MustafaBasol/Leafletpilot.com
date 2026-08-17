import { useEffect, useState } from "react";
import {
  createMarketInvitation,
  listMarketInvitations,
  listMarketMembers,
  requestMemberEmailChange,
  requestMemberPasswordReset,
  resendMarketInvitation,
  revokeMarketInvitation,
  updateMarketMember,
} from "../api/teamApi.js";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Table } from "../components/ui/index.js";

const roleLabels = {
  market_admin: "Yönetici",
  market_staff: "Personel",
  viewer: "Görüntüleyici",
};

// Never render the raw backend enum value — every status the backend can return must map here.
const statusLabels = {
  pending: "Beklemede",
  sent: "Gönderildi",
  manual_delivery_required: "E-posta gönderilemedi",
  accepted: "Kabul edildi",
  revoked: "İptal edildi",
  expired: "Süresi doldu",
  failed: "E-posta gönderilemedi",
};

const statusTones = {
  pending: "warning",
  sent: "success",
  manual_delivery_required: "warning",
  accepted: "success",
  revoked: "danger",
  expired: "neutral",
  failed: "danger",
};

// Statuses where the invite link is still worth surfacing as a manual-share fallback.
const MANUAL_SHARE_STATUSES = new Set(["manual_delivery_required", "failed"]);
// Statuses the "Yeniden Gönder" / "İptal Et" row actions remain available for.
const ACTIVE_INVITATION_STATUSES = new Set(["pending", "sent", "manual_delivery_required", "failed"]);

const memberColumns = [
  { label: "Kullanıcı" },
  { label: "Rol", width: "16%" },
  { label: "Durum", width: "12%" },
  { label: "Aksiyonlar", width: "30%" },
];

export function Team() {
  const [members, setMembers] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [form, setForm] = useState({ email: "", role: "market_staff" });
  const [createdInvite, setCreatedInvite] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [copyError, setCopyError] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [roleChange, setRoleChange] = useState(null);
  const [isRoleChanging, setRoleChanging] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [isRevoking, setRevoking] = useState(false);
  const [resendingId, setResendingId] = useState(null);
  const [resettingId, setResettingId] = useState(null);
  const [emailEditId, setEmailEditId] = useState(null);
  const [emailEditValue, setEmailEditValue] = useState("");
  const [emailChangingId, setEmailChangingId] = useState(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [memberList, invitationList] = await Promise.all([listMarketMembers(), listMarketInvitations()]);
      setMembers(memberList);
      setInvitations(invitationList);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function requestRoleChange(member, role) {
    if (role === member.role) return;
    setNotice("");
    setRoleChange({ member, role });
  }

  async function confirmRoleChange() {
    if (!roleChange) return;
    setRoleChanging(true);
    setError("");
    try {
      await updateMarketMember(roleChange.member.membership_id, { role: roleChange.role });
      setRoleChange(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setRoleChanging(false);
    }
  }

  async function handleCreateInvitation(event) {
    event.preventDefault();
    setCreatedInvite(null);
    setCopyMessage("");
    setCopyError("");
    setError("");
    setNotice("");
    try {
      const invitation = await createMarketInvitation(form);
      setCreatedInvite(invitation);
      setForm({ email: "", role: "market_staff" });
      await load();
    } catch (err) {
      setError(err.message);
      if (err.status === 409) {
        // A duplicate-active-invitation conflict — refresh so the existing invitation
        // (with its own Yeniden Gönder / İptal Et actions) is visible below.
        await load();
      }
    }
  }

  async function handleCopyInvite() {
    if (!createdInvite?.accept_url) return;
    setCopyMessage("");
    setCopyError("");
    try {
      await navigator.clipboard.writeText(createdInvite.accept_url);
      setCopyMessage("Davet bağlantısı panoya kopyalandı.");
      window.setTimeout(() => setCopyMessage(""), 2000);
    } catch {
      setCopyError("Davet bağlantısı kopyalanamadı. Bağlantıyı elle seçip kopyalayın.");
    }
  }

  function requestRevoke(invitation) {
    setNotice("");
    setRevokeTarget(invitation);
  }

  async function confirmRevoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    setError("");
    try {
      await revokeMarketInvitation(revokeTarget.id);
      setRevokeTarget(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setRevoking(false);
    }
  }

  async function handleResendInvitation(invitation) {
    if (resendingId) return;
    setError("");
    setNotice("");
    setResendingId(invitation.id);
    try {
      const resent = await resendMarketInvitation(invitation.id);
      setCreatedInvite(resent);
      setNotice(
        MANUAL_SHARE_STATUSES.has(resent.status)
          ? `${resent.email} için davet e-postası gönderilemedi. Bağlantıyı elle paylaşabilirsiniz.`
          : `${resent.email} için davet yeniden gönderildi.`,
      );
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setResendingId(null);
    }
  }

  async function handlePasswordReset(member) {
    if (resettingId) return;
    setError("");
    setNotice("");
    setResettingId(member.membership_id);
    try {
      const result = await requestMemberPasswordReset(member.membership_id);
      setNotice(
        MANUAL_SHARE_STATUSES.has(result.delivery)
          ? `${member.email} için şifre sıfırlama bağlantısı gönderilemedi. Lütfen daha sonra tekrar deneyin.`
          : `${member.email} adresine şifre sıfırlama bağlantısı gönderildi.`,
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setResettingId(null);
    }
  }

  function startEmailEdit(member) {
    setError("");
    setNotice("");
    setEmailEditId(member.membership_id);
    setEmailEditValue("");
  }

  function cancelEmailEdit() {
    setEmailEditId(null);
    setEmailEditValue("");
  }

  async function handleEmailChange(member) {
    if (emailChangingId) return;
    if (!emailEditValue.trim()) return;
    setError("");
    setNotice("");
    setEmailChangingId(member.membership_id);
    try {
      const result = await requestMemberEmailChange(member.membership_id, emailEditValue.trim());
      setNotice(
        MANUAL_SHARE_STATUSES.has(result.delivery)
          ? `${emailEditValue.trim()} adresine doğrulama bağlantısı gönderilemedi. Lütfen daha sonra tekrar deneyin.`
          : `${emailEditValue.trim()} adresine doğrulama bağlantısı gönderildi. E-posta yalnızca bağlantı tıklanınca değişir.`,
      );
      setEmailEditId(null);
      setEmailEditValue("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setEmailChangingId(null);
    }
  }

  return (
    <>
      <PageHeader title="Ekip" description="Market üyelerini ve manuel paylaşılacak davet bağlantılarını yönetin." />
      {error ? <p className="inline-result inline-result-warning" role="alert">{error}</p> : null}
      {notice ? <p className="inline-result" role="status">{notice}</p> : null}
      <Card title="Üyeler" action={<span className="card-summary">{members.length} üye</span>}>
        {isLoading ? <p className="inline-result">Yükleniyor...</p> : null}
        {!isLoading && !members.length ? (
          <EmptyState title="Henüz üye yok" text="Ekip üyeleri davet ettikçe burada listelenecek." />
        ) : null}
        {!isLoading && members.length ? (
          <Table columns={memberColumns}>
            {members.map((member) => (
              <tr key={member.membership_id}>
                <td>
                  <strong>{member.full_name || member.email}</strong>
                  <small>{member.email}</small>
                  {member.pending_email ? (
                    <small className="table-hint">Bekleyen e-posta: {member.pending_email} — doğrulama bekleniyor</small>
                  ) : null}
                </td>
                <td><Badge>{roleLabels[member.role] || member.role}</Badge></td>
                <td>{member.is_active ? "Aktif" : "Pasif"}</td>
                <td className="table-actions">
                  <label className="field">
                    <span>Rol</span>
                    <select value={member.role} onChange={(event) => requestRoleChange(member, event.target.value)}>
                      <option value="market_admin">Yönetici</option>
                      <option value="market_staff">Personel</option>
                      <option value="viewer">Görüntüleyici</option>
                    </select>
                  </label>
                  <Button onClick={() => handlePasswordReset(member)} disabled={resettingId === member.membership_id}>
                    {resettingId === member.membership_id ? "Gönderiliyor..." : "Şifre Sıfırlama Bağlantısı Gönder"}
                  </Button>
                  {emailEditId === member.membership_id ? (
                    <div className="field-stack">
                      <Input
                        label="Yeni e-posta"
                        type="email"
                        value={emailEditValue}
                        onChange={(event) => setEmailEditValue(event.target.value)}
                      />
                      <div className="table-actions">
                        <Button
                          variant="primary"
                          onClick={() => handleEmailChange(member)}
                          disabled={emailChangingId === member.membership_id || !emailEditValue.trim()}
                        >
                          {emailChangingId === member.membership_id ? "Gönderiliyor..." : "Doğrulama Bağlantısı Gönder"}
                        </Button>
                        <Button onClick={cancelEmailEdit} disabled={emailChangingId === member.membership_id}>Vazgeç</Button>
                      </div>
                    </div>
                  ) : (
                    <Button onClick={() => startEmailEdit(member)}>E-posta Değiştir</Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>
      <Card title="Davet Oluştur">
        <form className="inline-form field-stack" onSubmit={handleCreateInvitation}>
          <Input label="E-posta" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          <label className="field">
            <span>Rol</span>
            <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              <option value="market_staff">Personel</option>
              <option value="viewer">Görüntüleyici</option>
              <option value="market_admin">Yönetici</option>
            </select>
          </label>
          <Button variant="primary" type="submit">Davet Oluştur</Button>
        </form>
        {createdInvite && (
          <div className="invite-result field-stack">
            <strong>{createdInvite.status === "sent" ? "Davet e-postası gönderildi" : "Davet bağlantısı"}</strong>
            <Input label="Bağlantı" readOnly value={createdInvite.accept_url} />
            <Button onClick={handleCopyInvite}>{copyMessage ? "Kopyalandı" : "Kopyala"}</Button>
            {copyMessage ? <p className="inline-result" role="status">{copyMessage}</p> : null}
            {copyError ? <p className="inline-result inline-result-warning" role="alert">{copyError}</p> : null}
            {MANUAL_SHARE_STATUSES.has(createdInvite.status) ? (
              <p className="table-hint">Davet e-postası gönderilemedi. Bu bağlantıyı kullanıcıyla güvenli şekilde paylaşın.</p>
            ) : (
              <p className="table-hint">Davet e-postası {createdInvite.email} adresine gönderildi. Sorun olursa bağlantıyı elle de paylaşabilirsiniz.</p>
            )}
          </div>
        )}
      </Card>
      <Card title="Davetler">
        {!invitations.length ? (
          <EmptyState title="Henüz davet yok" text="Oluşturduğunuz davetler burada listelenecek." />
        ) : (
          <Table columns={["E-posta", "Rol", "Durum", "Son Tarih", "Aksiyonlar"]}>
            {invitations.map((invitation) => (
              <tr key={invitation.id}>
                <td>{invitation.email}</td>
                <td>{roleLabels[invitation.role] || invitation.role}</td>
                <td><Badge tone={statusTones[invitation.status] || "neutral"}>{statusLabels[invitation.status] || invitation.status}</Badge></td>
                <td>{new Date(invitation.expires_at).toLocaleString("tr-TR")}</td>
                <td className="table-actions">
                  {ACTIVE_INVITATION_STATUSES.has(invitation.status) && (
                    <>
                      <Button onClick={() => handleResendInvitation(invitation)} disabled={resendingId === invitation.id}>
                        {resendingId === invitation.id ? "Gönderiliyor..." : "Yeniden Gönder"}
                      </Button>
                      <Button variant="danger" onClick={() => requestRevoke(invitation)}>İptal Et</Button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <ConfirmDialog
        isOpen={Boolean(roleChange)}
        title="Rol değişikliği"
        description={roleChange ? `${roleChange.member.email} rolü ${roleLabels[roleChange.role]} olarak değiştirilsin mi?` : ""}
        confirmLabel="Rolü Değiştir"
        onCancel={() => setRoleChange(null)}
        onConfirm={confirmRoleChange}
        isLoading={isRoleChanging}
      />
      <ConfirmDialog
        isOpen={Boolean(revokeTarget)}
        title="Daveti iptal et"
        description={revokeTarget ? `${revokeTarget.email} daveti iptal edilsin mi?` : ""}
        confirmLabel="Daveti İptal Et"
        onCancel={() => setRevokeTarget(null)}
        onConfirm={confirmRevoke}
        isLoading={isRevoking}
      />
    </>
  );
}
