import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card } from "../../components/ui/index.js";
import { canApproveSignup, canProvisionSignup, canRejectSignup, normalizeApiError } from "./platformOps.js";
import { statusLabel, t } from "./platformI18n.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

export function SignupRequestDetail({ id }) {
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
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
    setError("");
    try {
      const response = await platformApi.getSignupRequest(id);
      setItem(response);
      setReviewNotes(response.review_notes || "");
      setRejectReason(response.rejection_reason || "");
      setProvision((current) => ({
        ...current,
        final_market_name: response.market_name,
        country_code: response.country_code,
        preferred_language: response.preferred_language,
      }));
    } catch (err) {
      setError(normalizeApiError(err));
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function updateStatus(status, body = {}) {
    setAction(status);
    setError("");
    try {
      await platformApi.updateSignupRequest(id, { status, review_notes: reviewNotes, ...body });
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function reject() {
    if (!window.confirm(t("confirmRejectSignup"))) return;
    await updateStatus("rejected", { rejection_reason: rejectReason });
  }

  async function provisionMarket() {
    if (!window.confirm(t("confirmProvisionSignup"))) return;
    setAction("provision");
    setInviteUrl("");
    setError("");
    try {
      const response = await platformApi.provisionSignupRequest(id, provision);
      setInviteUrl(response.accept_url || "");
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

  if (!item && !error) return <p className="inline-result">{t("loading")}</p>;

  return (
    <>
      {item ? (
        <section className="page-heading">
          <div>
            <h2>{item.market_name}</h2>
            <p>{item.contact_name} · {item.email}</p>
          </div>
          <Badge>{statusLabel(item.status)}</Badge>
        </section>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {item ? (
        <section className="dashboard-grid">
          <Card title={t("signupRequests")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("phone")}</dt><dd>{item.phone || "-"}</dd></div>
              <div><dt>{t("location")}</dt><dd>{[item.city, item.country_code].filter(Boolean).join(", ")}</dd></div>
              <div><dt>{t("language")}</dt><dd>{item.preferred_language}</dd></div>
              <div><dt>{t("monthlyCampaigns")}</dt><dd>{item.expected_campaigns_per_month ?? "-"}</dd></div>
              <div><dt>{t("created")}</dt><dd>{formatDate(item.created_at)}</dd></div>
              <div><dt>{t("updated")}</dt><dd>{formatDate(item.updated_at)}</dd></div>
              <div><dt>{t("notes")}</dt><dd>{item.notes || "-"}</dd></div>
            </dl>
            <label className="settings-form">
              {t("reviewNotes")}
              <textarea rows="3" value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} />
            </label>
            <div className="page-actions">
              <Button disabled={Boolean(action) || item.status !== "pending"} onClick={() => updateStatus("reviewing")}>{t("review")}</Button>
              <Button disabled={Boolean(action) || !canApproveSignup(item)} onClick={() => updateStatus("approved")}>{t("approve")}</Button>
            </div>
          </Card>
          <Card title={t("reject")} className="span-6">
            <label className="settings-form">
              {t("rejectionReason")}
              <textarea rows="4" value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
            </label>
            <Button variant="danger" disabled={Boolean(action) || !canRejectSignup(item)} onClick={reject}>{t("reject")}</Button>
          </Card>
          <Card title={t("marketProvision")} className="span-8">
            <p className="inline-result inline-result-warning">
              {t("provisionInviteNotice")}
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
            <Button variant="primary" disabled={Boolean(action) || !canProvisionSignup(item)} onClick={provisionMarket}>{t("createMarketAndInvitation")}</Button>
            {inviteUrl ? (
              <div className="invite-result">
                <strong>{t("oneTimeInviteLink")}</strong>
                <input readOnly value={inviteUrl} />
                <Button onClick={copyInvite}>{t("copy")}</Button>
              </div>
            ) : null}
          </Card>
        </section>
      ) : null}
    </>
  );
}
