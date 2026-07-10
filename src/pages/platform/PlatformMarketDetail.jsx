import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card, Table } from "../../components/ui/index.js";
import { hasEffectiveOwnerInvitation, normalizeApiError } from "./platformOps.js";
import { blockerLabel, countRows, deriveReadiness, statusLabel, t } from "./platformI18n.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

function ownerInvitationLabel(invitation) {
  if (!invitation) return t("none");
  return `${statusLabel(invitation.status)} · ${statusLabel(invitation.delivery_status)}`;
}

export function PlatformMarketDetail({ id }) {
  const [market, setMarket] = useState(null);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
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
    const reason = lifecycle_status === "active" ? "" : window.prompt(t("reasonPrompt"));
    if (lifecycle_status !== "active" && !reason) return;
    const message = lifecycle_status === "archived"
      ? t("confirmArchiveMarket")
      : `${statusLabel(lifecycle_status)} ${t("confirmStatusChangeSuffix")}`;
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
    setError("");
    try {
      const body = { email: ownerEmail || null };
      operation === "create"
        ? await platformApi.createOwnerInvitation(id, body)
        : await platformApi.rotateOwnerInvitation(id, body);
      await load();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setAction("");
    }
  }

  async function revokeInvitation() {
    if (!window.confirm(t("confirmRevokeOwnerInvitation"))) return;
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

  if (!market && !error) return <p className="inline-result">{t("loading")}</p>;

  const readiness = deriveReadiness(market);

  return (
    <>
      {market ? (
        <section className="page-heading">
          <div>
            <h2>{market.name}</h2>
            <p>{market.slug}</p>
          </div>
          <Badge>{statusLabel(market.lifecycle_status)}</Badge>
        </section>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {market ? (
        <section className="dashboard-grid">
          <Card title={t("readiness")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("status")}</dt><dd>{statusLabel(readiness.status)}</dd></div>
              <div><dt>{t("activeUser")}</dt><dd>{market.readiness?.has_active_market_user ? t("yes") : t("no")}</dd></div>
              <div><dt>{t("requiredSetup")}</dt><dd>{market.readiness?.required_setup_complete ? t("complete") : t("missing")}</dd></div>
              <div><dt>{t("lastActivity")}</dt><dd>{formatDate(market.readiness?.last_activity_at)}</dd></div>
              {countRows(market).map((row) => (
                <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>
              ))}
            </dl>
            {readiness.blockers.length ? (
              <ul className="readiness-blocker-list" aria-label={t("readiness")}>
                {readiness.blockers.map((blocker) => (
                  <li key={`${blockerLabel(blocker)}-${JSON.stringify(blocker)}`}>{blockerLabel(blocker)}</li>
                ))}
              </ul>
            ) : (
              <p className="inline-result">{t("readinessReady")}</p>
            )}
          </Card>
          <Card title={t("lifecycle")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("trialEnds")}</dt><dd>{formatDate(market.trial_ends_at)}</dd></div>
              <div><dt>{t("lastReason")}</dt><dd>{market.lifecycle_reason || "-"}</dd></div>
              <div><dt>{t("lastUpdated")}</dt><dd>{formatDate(market.lifecycle_updated_at)}</dd></div>
            </dl>
            <div className="page-actions">
              <Button disabled={Boolean(action) || market.lifecycle_status === "active"} onClick={() => setLifecycle("active")}>{t("activateOrContinue")}</Button>
              <Button variant="danger" disabled={Boolean(action) || market.lifecycle_status === "suspended"} onClick={() => setLifecycle("suspended")}>{t("suspend")}</Button>
              <Button variant="danger" disabled={Boolean(action) || market.lifecycle_status === "archived"} onClick={() => setLifecycle("archived")}>{t("archive")}</Button>
            </div>
          </Card>
          <Card title={t("ownerInvitation")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("email")}</dt><dd>{market.owner_invitation?.email || market.contact_email || "-"}</dd></div>
              <div><dt>{t("status")}</dt><dd>{ownerInvitationLabel(market.owner_invitation)}</dd></div>
              <div><dt>{t("expires")}</dt><dd>{formatDate(market.owner_invitation?.expires_at)}</dd></div>
              <div><dt>{t("lastSent")}</dt><dd>{formatDate(market.owner_invitation?.last_sent_at)}</dd></div>
              <div><dt>{t("sendCount")}</dt><dd>{market.owner_invitation?.send_count ?? 0}</dd></div>
              <div><dt>{t("accepted")}</dt><dd>{formatDate(market.owner_invitation?.accepted_at)}</dd></div>
              {market.owner_invitation?.last_send_error ? (
                <div><dt>{t("sendError")}</dt><dd>{market.owner_invitation.last_send_error}</dd></div>
              ) : null}
            </dl>
            <label className="settings-form">
              {t("ownerEmail")}
              <input value={ownerEmail} onChange={(event) => setOwnerEmail(event.target.value)} />
            </label>
            <div className="page-actions">
              <Button disabled={Boolean(action) || hasEffectiveOwnerInvitation(market)} onClick={() => runInvitation("create")}>{t("createInvitation")}</Button>
              <Button disabled={Boolean(action)} onClick={() => runInvitation("rotate")}>{t("rotateInvitation")}</Button>
              <Button variant="danger" disabled={Boolean(action) || !hasEffectiveOwnerInvitation(market)} onClick={revokeInvitation}>{t("revokeInvitation")}</Button>
            </div>
            <p className="inline-result">{t("invitationEmailNotice")}</p>
          </Card>
          <Card title={t("profile")} className="span-6">
            <dl className="detail-list">
              <div><dt>{t("legalName")}</dt><dd>{market.legal_name || "-"}</dd></div>
              <div><dt>{t("location")}</dt><dd>{[market.city, market.country_code].filter(Boolean).join(", ") || "-"}</dd></div>
              <div><dt>{t("languageCurrency")}</dt><dd>{market.language} / {market.currency}</dd></div>
              <div><dt>{t("timeZone")}</dt><dd>{market.timezone}</dd></div>
              <div><dt>{t("contact")}</dt><dd>{market.contact_email || "-"} {market.contact_phone || ""}</dd></div>
              <div><dt>{t("onboarding")}</dt><dd>{statusLabel(market.onboarding_status)} · {t("step")} {market.onboarding_step}</dd></div>
            </dl>
          </Card>
          <Card title={t("platformActivity")} className="span-12">
            <Table columns={[t("action"), t("date")]}>
              {(market.recent_activity || []).map((item) => (
                <tr key={item.id}>
                  <td><Badge>{item.action}</Badge></td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {(market.recent_activity || []).length === 0 ? <tr><td colSpan="2">{t("noActivity")}</td></tr> : null}
            </Table>
          </Card>
        </section>
      ) : null}
    </>
  );
}
