import { useEffect, useState } from "react";
import { createMarketInvitation, listMarketInvitations, listMarketMembers, revokeMarketInvitation, updateMarketMember } from "../api/teamApi.js";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Table } from "../components/ui/index.js";

const roleLabels = {
  market_admin: "Yönetici",
  market_staff: "Personel",
  viewer: "Görüntüleyici",
};

const statusLabels = {
  pending: "Bekliyor",
  accepted: "Kabul Edildi",
  revoked: "İptal Edildi",
  expired: "Süresi Doldu",
};

const statusTones = {
  pending: "warning",
  accepted: "success",
  revoked: "danger",
  expired: "neutral",
};

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

  // TODO(Phase 7b): wire to a real resend endpoint once invitation email sending is implemented.
  function handleResendInvitation(invitation) {
    setError("");
    setNotice(`${invitation.email} için yeniden gönderme özelliği yakında eklenecek.`);
  }

  // TODO(Phase 7c): wire to the admin-triggered password-reset endpoint once implemented.
  function handlePasswordReset(member) {
    setError("");
    setNotice(`${member.email} için şifre sıfırlama bağlantısı gönderme özelliği yakında eklenecek.`);
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
                  <Button onClick={() => handlePasswordReset(member)}>Şifre Sıfırlama Bağlantısı Gönder</Button>
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
            <strong>Davet bağlantısı</strong>
            <Input label="Bağlantı" readOnly value={createdInvite.accept_url} />
            <Button onClick={handleCopyInvite}>{copyMessage ? "Kopyalandı" : "Kopyala"}</Button>
            {copyMessage ? <p className="inline-result" role="status">{copyMessage}</p> : null}
            {copyError ? <p className="inline-result inline-result-warning" role="alert">{copyError}</p> : null}
            <p className="table-hint">E-posta gönderimi henüz otomatik değildir. Bu bağlantıyı kullanıcıyla güvenli şekilde paylaşın.</p>
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
                  {invitation.status === "pending" && (
                    <>
                      <Button onClick={() => handleResendInvitation(invitation)}>Yeniden Gönder</Button>
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
