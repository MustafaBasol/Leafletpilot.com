import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card, Table } from "../../components/ui/index.js";
import { hasEffectiveOwnerInvitation, labelFor, lifecycleLabels, normalizeApiError, readinessLabels } from "./platformOps.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

export function PlatformMarketDetail({ id }) {
  const [market, setMarket] = useState(null);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");

  async function load() {
    setError("");
    try {
      const response = await platformApi.getMarket(id);
      setMarket(response);
      setOwnerEmail(response.owner_invitation?.email || response.contact_email || "");
    } catch (err) {
      setError(normalizeApiError(err));
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function setLifecycle(lifecycle_status) {
    const reason = lifecycle_status === "active" ? "" : window.prompt("Neden girin");
    if (lifecycle_status !== "active" && !reason) return;
    const message = lifecycle_status === "archived" ? "Market arşivlensin mi?" : `Lifecycle ${labelFor(lifecycleLabels, lifecycle_status)} yapılsın mı?`;
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

  async function runInvitation(operation) {
    setAction(operation);
    setInviteUrl("");
    setError("");
    try {
      const body = { email: ownerEmail || null };
      const response = operation === "create"
        ? await platformApi.createOwnerInvitation(id, body)
        : await platformApi.rotateOwnerInvitation(id, body);
      setInviteUrl(response.accept_url || "");
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function revokeInvitation() {
    if (!window.confirm("Kullanılmamış owner daveti iptal edilsin mi?")) return;
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

  async function copyInvite() {
    if (inviteUrl) await navigator.clipboard.writeText(inviteUrl);
  }

  if (!market && !error) return <p className="inline-result">Yükleniyor...</p>;

  return (
    <>
      {market ? (
        <section className="page-heading">
          <div>
            <h2>{market.name}</h2>
            <p>{market.slug}</p>
          </div>
          <Badge>{labelFor(lifecycleLabels, market.lifecycle_status)}</Badge>
        </section>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {market ? (
        <section className="dashboard-grid">
          <Card title="Readiness" className="span-6">
            <dl className="detail-list">
              <div><dt>Durum</dt><dd>{labelFor(readinessLabels, market.readiness?.state)}</dd></div>
              <div><dt>Aktif kullanıcı</dt><dd>{market.readiness?.has_active_market_user ? "Var" : "Yok"}</dd></div>
              <div><dt>Gerekli kurulum</dt><dd>{market.readiness?.required_setup_complete ? "Tamam" : "Eksik"}</dd></div>
              <div><dt>Son aktivite</dt><dd>{formatDate(market.readiness?.last_activity_at)}</dd></div>
            </dl>
            {(market.readiness?.blockers || []).map((blocker) => <p className="inline-result inline-result-warning" key={blocker}>{blocker}</p>)}
          </Card>
          <Card title="Lifecycle" className="span-6">
            <dl className="detail-list">
              <div><dt>Deneme bitişi</dt><dd>{formatDate(market.trial_ends_at)}</dd></div>
              <div><dt>Son neden</dt><dd>{market.lifecycle_reason || "-"}</dd></div>
              <div><dt>Son güncelleme</dt><dd>{formatDate(market.lifecycle_updated_at)}</dd></div>
            </dl>
            <div className="page-actions">
              <Button disabled={Boolean(action) || market.lifecycle_status === "active"} onClick={() => setLifecycle("active")}>Aktifleştir / Sürdür</Button>
              <Button variant="danger" disabled={Boolean(action) || market.lifecycle_status === "suspended"} onClick={() => setLifecycle("suspended")}>Askıya Al</Button>
              <Button variant="danger" disabled={Boolean(action) || market.lifecycle_status === "archived"} onClick={() => setLifecycle("archived")}>Arşivle</Button>
            </div>
          </Card>
          <Card title="Owner Daveti" className="span-6">
            <dl className="detail-list">
              <div><dt>E-posta</dt><dd>{market.owner_invitation?.email || market.contact_email || "-"}</dd></div>
              <div><dt>Durum</dt><dd>{market.owner_invitation ? `${market.owner_invitation.status} · ${market.owner_invitation.delivery_status}` : "Yok"}</dd></div>
              <div><dt>Bitiş</dt><dd>{formatDate(market.owner_invitation?.expires_at)}</dd></div>
              <div><dt>Kabul</dt><dd>{formatDate(market.owner_invitation?.accepted_at)}</dd></div>
            </dl>
            <label className="settings-form">
              Owner e-posta
              <input value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} />
            </label>
            <div className="page-actions">
              <Button disabled={Boolean(action) || hasEffectiveOwnerInvitation(market)} onClick={() => runInvitation("create")}>Davet Oluştur</Button>
              <Button disabled={Boolean(action)} onClick={() => runInvitation("rotate")}>Davet Döndür</Button>
              <Button variant="danger" disabled={Boolean(action) || !hasEffectiveOwnerInvitation(market)} onClick={revokeInvitation}>Davet İptal</Button>
            </div>
            {inviteUrl ? (
              <div className="invite-result">
                <strong>Tek seferlik davet bağlantısı</strong>
                <input readOnly value={inviteUrl} />
                <Button onClick={copyInvite}>Kopyala</Button>
              </div>
            ) : null}
          </Card>
          <Card title="Profil" className="span-6">
            <dl className="detail-list">
              <div><dt>Yasal ad</dt><dd>{market.legal_name || "-"}</dd></div>
              <div><dt>Konum</dt><dd>{[market.city, market.country_code].filter(Boolean).join(", ")}</dd></div>
              <div><dt>Dil / Para</dt><dd>{market.language} / {market.currency}</dd></div>
              <div><dt>Zaman dilimi</dt><dd>{market.timezone}</dd></div>
              <div><dt>İletişim</dt><dd>{market.contact_email || "-"} {market.contact_phone || ""}</dd></div>
              <div><dt>Onboarding</dt><dd>{market.onboarding_status} · adım {market.onboarding_step}</dd></div>
              <div><dt>Ürün / Kampanya</dt><dd>{market.product_count} / {market.campaign_count}</dd></div>
            </dl>
          </Card>
          <Card title="Platform Aktivitesi" className="span-12">
            <Table columns={["Aksiyon", "Tarih"]}>
              {(market.recent_activity || []).map((item) => (
                <tr key={item.id}>
                  <td><Badge>{item.action}</Badge></td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {(market.recent_activity || []).length === 0 ? <tr><td colSpan="2">Aktivite yok.</td></tr> : null}
            </Table>
          </Card>
        </section>
      ) : null}
    </>
  );
}
