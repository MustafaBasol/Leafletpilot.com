import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card } from "../../components/ui/index.js";

export function SignupRequestDetail({ id }) {
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [provision, setProvision] = useState({
    final_market_name: "",
    requested_slug: "",
    country_code: "FR",
    preferred_language: "tr",
    currency: "EUR",
    timezone: "Europe/Paris",
    trial_length_days: 14,
  });

  async function load() {
    try {
      const response = await platformApi.getSignupRequest(id);
      setItem(response);
      setProvision((current) => ({
        ...current,
        final_market_name: response.market_name,
        country_code: response.country_code,
        preferred_language: response.preferred_language,
      }));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function markReviewing() {
    await platformApi.updateSignupRequest(id, { status: "reviewing" });
    await load();
  }

  async function reject() {
    if (!window.confirm("Bu başvuru reddedilsin mi?")) return;
    await platformApi.updateSignupRequest(id, { status: "rejected", rejection_reason: rejectReason });
    await load();
  }

  async function provisionMarket() {
    if (!window.confirm("Bu başvuru için market ve yönetici daveti oluşturulsun mu?")) return;
    setInviteUrl("");
    const response = await platformApi.provisionSignupRequest(id, provision);
    setInviteUrl(response.accept_url || "");
    await load();
  }

  async function copyInvite() {
    if (inviteUrl) await navigator.clipboard.writeText(inviteUrl);
  }

  if (!item) return <p className="inline-result">Yükleniyor...</p>;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{item.market_name}</h2>
          <p>{item.contact_name} · {item.email}</p>
        </div>
        <Badge>{item.status}</Badge>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="dashboard-grid">
        <Card title="Başvuru" className="span-6">
          <dl className="detail-list">
            <div><dt>Telefon</dt><dd>{item.phone || "-"}</dd></div>
            <div><dt>Konum</dt><dd>{[item.city, item.country_code].filter(Boolean).join(", ")}</dd></div>
            <div><dt>Dil</dt><dd>{item.preferred_language}</dd></div>
            <div><dt>Aylık kampanya</dt><dd>{item.expected_campaigns_per_month ?? "-"}</dd></div>
            <div><dt>Not</dt><dd>{item.notes || "-"}</dd></div>
          </dl>
          <div className="page-actions">
            <Button onClick={markReviewing}>İncelemeye Al</Button>
          </div>
        </Card>
        <Card title="Ret" className="span-6">
          <label className="settings-form">
            Ret nedeni
            <textarea rows="4" value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
          </label>
          <Button variant="danger" onClick={reject}>Reddet</Button>
        </Card>
        <Card title="Market Provision" className="span-8">
          <p className="inline-result inline-result-warning">
            Davet bağlantısı yalnızca başarılı provision yanıtında gösterilir. Güvenli şekilde kopyalayın.
          </p>
          <div className="form-grid">
            {["final_market_name", "requested_slug", "country_code", "preferred_language", "currency", "timezone", "trial_length_days"].map((field) => (
              <label key={field}>
                {field}
                <input
                  type={field === "trial_length_days" ? "number" : "text"}
                  value={provision[field]}
                  onChange={(event) => setProvision({ ...provision, [field]: field === "trial_length_days" ? Number(event.target.value) : event.target.value })}
                />
              </label>
            ))}
          </div>
          <Button variant="primary" onClick={provisionMarket}>Market Oluştur ve Davet Üret</Button>
          {inviteUrl ? (
            <div className="invite-result">
              <strong>Tek seferlik davet bağlantısı</strong>
              <input readOnly value={inviteUrl} />
              <Button onClick={copyInvite}>Kopyala</Button>
            </div>
          ) : null}
        </Card>
      </section>
    </>
  );
}
