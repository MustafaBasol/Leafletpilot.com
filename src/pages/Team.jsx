import { useEffect, useState } from "react";
import { createMarketInvitation, listMarketInvitations, listMarketMembers, revokeMarketInvitation, updateMarketMember } from "../api/teamApi.js";
import { Badge, Button, Card, Table } from "../components/ui/index.js";

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

export function Team() {
  const [members, setMembers] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [form, setForm] = useState({ email: "", role: "market_staff" });
  const [createdInvite, setCreatedInvite] = useState(null);
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [copyError, setCopyError] = useState("");
  const [isLoading, setLoading] = useState(true);

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

  async function handleRoleChange(member, role) {
    if (!window.confirm(`${member.email} rolü ${roleLabels[role]} olarak değiştirilsin mi?`)) return;
    try {
      await updateMarketMember(member.membership_id, { role });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCreateInvitation(event) {
    event.preventDefault();
    setCreatedInvite(null);
    setCopyMessage("");
    setCopyError("");
    setError("");
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

  async function handleRevoke(invitation) {
    if (!window.confirm(`${invitation.email} daveti iptal edilsin mi?`)) return;
    try {
      await revokeMarketInvitation(invitation.id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Ekip</h2>
          <p>Market üyelerini ve manuel paylaşılacak davet bağlantılarını yönetin.</p>
        </div>
      </section>
      {error && <div className="form-error">{error}</div>}
      <Card title="Üyeler">
        <Table columns={["Kullanıcı", "Rol", "Durum", "İşlem"]}>
          {members.map((member) => (
            <tr key={member.membership_id}>
              <td>
                <strong>{member.full_name || member.email}</strong>
                <small>{member.email}</small>
              </td>
              <td><Badge>{roleLabels[member.role] || member.role}</Badge></td>
              <td>{member.is_active ? "Aktif" : "Pasif"}</td>
              <td>
                <select value={member.role} onChange={(event) => handleRoleChange(member, event.target.value)}>
                  <option value="market_admin">Yönetici</option>
                  <option value="market_staff">Personel</option>
                  <option value="viewer">Görüntüleyici</option>
                </select>
              </td>
            </tr>
          ))}
        </Table>
        {isLoading && <p>Yükleniyor...</p>}
      </Card>
      <Card title="Davet Oluştur">
        <form className="settings-form" onSubmit={handleCreateInvitation}>
          <label>
            E-posta
            <input value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
          </label>
          <label>
            Rol
            <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              <option value="market_staff">Personel</option>
              <option value="viewer">Görüntüleyici</option>
              <option value="market_admin">Yönetici</option>
            </select>
          </label>
          <Button variant="primary" type="submit">Davet Oluştur</Button>
        </form>
        {createdInvite && (
          <div className="invite-result">
            <strong>Davet bağlantısı</strong>
            <input readOnly value={createdInvite.accept_url} />
            <Button onClick={handleCopyInvite}>{copyMessage ? "Kopyalandı" : "Kopyala"}</Button>
            {copyMessage ? <p className="inline-result">{copyMessage}</p> : null}
            {copyError ? <p className="inline-result inline-result-warning">{copyError}</p> : null}
            <p>E-posta gönderimi henüz otomatik değildir. Bu bağlantıyı kullanıcıyla güvenli şekilde paylaşın.</p>
          </div>
        )}
      </Card>
      <Card title="Davetler">
        <Table columns={["E-posta", "Rol", "Durum", "Son Tarih", "İşlem"]}>
          {invitations.map((invitation) => (
            <tr key={invitation.id}>
              <td>{invitation.email}</td>
              <td>{roleLabels[invitation.role] || invitation.role}</td>
              <td><Badge tone={statusTones[invitation.status] || "neutral"}>{statusLabels[invitation.status] || invitation.status}</Badge></td>
              <td>{new Date(invitation.expires_at).toLocaleString("tr-TR")}</td>
              <td>
                {invitation.status === "pending" && (
                  <Button variant="danger" onClick={() => handleRevoke(invitation)}>İptal Et</Button>
                )}
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
