import { useEffect, useMemo, useState } from "react";
import { acceptInvitation, acceptInvitationAuthenticated, previewInvitation } from "../api/teamApi.js";
import { clearAuthSession, getStoredMarkets, saveAuthSession, setSelectedMarketId } from "../api/authSession.js";
import { Button, Card } from "../components/ui/index.js";

const labels = {
  tr: {
    title: "LeafletPilot Daveti",
    loading: "Davet kontrol ediliyor...",
    invalid: "Bu davet bağlantısı geçerli değil.",
    expired: "Bu davetin süresi dolmuş.",
    revoked: "Bu davet iptal edilmiş.",
    accepted: "Bu davet daha önce kullanılmış.",
    failed: "Davet e-postası gönderilemedi. Lütfen destek ekibinden yeni davet isteyin.",
    server: "Davet işlemi tamamlanamadı.",
    invitedEmail: "Davet edilen e-posta",
    market: "Market",
    role: "Rol",
    expires: "Son geçerlilik",
    fullName: "Ad soyad",
    password: "Şifre",
    passwordConfirm: "Şifre tekrar",
    show: "Göster",
    hide: "Gizle",
    submit: "Daveti Kabul Et",
    submitting: "Kabul ediliyor...",
    existing: "Bu e-posta için mevcut hesap bulundu. Aynı hesapla giriş yaptıktan sonra daveti kabul edin.",
    authenticated: "Mevcut oturumunuzla daveti kabul edebilirsiniz.",
    mismatch: "Bu davet başka bir e-posta adresi için oluşturulmuş. Davet edilen hesapla giriş yapın veya mevcut oturumdan çıkın.",
    logout: "Çıkış yap",
    login: "Giriş sayfasına git",
    passwordMismatch: "Şifreler eşleşmiyor.",
    success: "Davet kabul edildi. Yönlendiriliyorsunuz.",
  },
  en: {
    title: "LeafletPilot Invitation",
    loading: "Checking invitation...",
    invalid: "This invitation link is not valid.",
    expired: "This invitation has expired.",
    revoked: "This invitation was revoked.",
    accepted: "This invitation has already been used.",
    failed: "The invitation email could not be delivered. Ask support for a new invitation.",
    server: "The invitation could not be completed.",
    invitedEmail: "Invited email",
    market: "Market",
    role: "Role",
    expires: "Expires",
    fullName: "Full name",
    password: "Password",
    passwordConfirm: "Confirm password",
    show: "Show",
    hide: "Hide",
    submit: "Accept Invitation",
    submitting: "Accepting...",
    existing: "An account already exists for this email. Sign in with that account, then accept the invitation.",
    authenticated: "You can accept the invitation with your current session.",
    mismatch: "This invitation is for another email address. Sign in with the invited account or sign out first.",
    logout: "Sign out",
    login: "Go to login",
    passwordMismatch: "Passwords do not match.",
    success: "Invitation accepted. Redirecting.",
  },
  fr: {
    title: "Invitation LeafletPilot",
    loading: "Vérification de l'invitation...",
    invalid: "Ce lien d'invitation n'est pas valide.",
    expired: "Cette invitation a expiré.",
    revoked: "Cette invitation a été révoquée.",
    accepted: "Cette invitation a déjà été utilisée.",
    failed: "L'e-mail d'invitation n'a pas pu être envoyé. Demandez une nouvelle invitation au support.",
    server: "L'invitation n'a pas pu être finalisée.",
    invitedEmail: "E-mail invité",
    market: "Market",
    role: "Rôle",
    expires: "Expiration",
    fullName: "Nom complet",
    password: "Mot de passe",
    passwordConfirm: "Confirmer le mot de passe",
    show: "Afficher",
    hide: "Masquer",
    submit: "Accepter l'invitation",
    submitting: "Acceptation...",
    existing: "Un compte existe déjà pour cet e-mail. Connectez-vous avec ce compte, puis acceptez l'invitation.",
    authenticated: "Vous pouvez accepter l'invitation avec votre session actuelle.",
    mismatch: "Cette invitation est destinée à une autre adresse e-mail. Connectez-vous avec le compte invité ou déconnectez-vous.",
    logout: "Déconnexion",
    login: "Aller à la connexion",
    passwordMismatch: "Les mots de passe ne correspondent pas.",
    success: "Invitation acceptée. Redirection.",
  },
  de: {
    title: "LeafletPilot-Einladung",
    loading: "Einladung wird geprüft...",
    invalid: "Dieser Einladungslink ist ungültig.",
    expired: "Diese Einladung ist abgelaufen.",
    revoked: "Diese Einladung wurde widerrufen.",
    accepted: "Diese Einladung wurde bereits verwendet.",
    failed: "Die Einladungs-E-Mail konnte nicht zugestellt werden. Bitte Support um eine neue Einladung.",
    server: "Die Einladung konnte nicht abgeschlossen werden.",
    invitedEmail: "Eingeladene E-Mail",
    market: "Market",
    role: "Rolle",
    expires: "Ablauf",
    fullName: "Vollständiger Name",
    password: "Passwort",
    passwordConfirm: "Passwort bestätigen",
    show: "Anzeigen",
    hide: "Ausblenden",
    submit: "Einladung annehmen",
    submitting: "Wird angenommen...",
    existing: "Für diese E-Mail existiert bereits ein Konto. Melden Sie sich damit an und nehmen Sie dann die Einladung an.",
    authenticated: "Sie können die Einladung mit Ihrer aktuellen Sitzung annehmen.",
    mismatch: "Diese Einladung gilt für eine andere E-Mail-Adresse. Melden Sie sich mit dem eingeladenen Konto an oder melden Sie sich ab.",
    logout: "Abmelden",
    login: "Zur Anmeldung",
    passwordMismatch: "Passwörter stimmen nicht überein.",
    success: "Einladung angenommen. Weiterleitung.",
  },
};

function locale() {
  const lang = navigator.language?.slice(0, 2);
  return labels[lang] ? lang : "tr";
}

function getToken(path = "") {
  if (path.startsWith("/invite/")) return decodeURIComponent(path.replace("/invite/", "").split("?")[0]);
  const hash = window.location.hash || "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?")) : "";
  return new URLSearchParams(query).get("token") || "";
}

function normalizeError(error, text) {
  const code = error?.body?.detail?.code;
  if (code === "invitation_email_mismatch") return text.mismatch;
  if (code === "invitation_existing_user") return text.existing;
  if (code === "invitation_invalid") return text.invalid;
  if (code === "invitation_expired") return text.expired;
  if (code === "invitation_revoked") return text.revoked;
  if (code === "invitation_accepted") return text.accepted;
  if (code === "invitation_delivery_failed") return text.failed;
  if (code === "invitation_unavailable") return text.invalid;
  const detail = error?.body?.detail;
  if (typeof detail === "object" && typeof detail?.message === "string") {
    return detail.message;
  }
  return typeof error?.message === "string" ? error.message : text.server;
}

function resolveAcceptedMarket(previousMarkets, session) {
  const previousIds = new Set(previousMarkets.map((market) => market.id));
  return session.markets?.find((market) => !previousIds.has(market.id)) || session.markets?.[0] || null;
}

function marketNeedsOnboarding(market) {
  return Boolean(market && market.role === "market_admin" && market.onboarding_status !== "completed");
}

export function AcceptInvitation({ path, isAuthenticated, onSessionUpdated }) {
  const text = labels[locale()];
  const token = useMemo(() => getToken(path), [path]);
  const [preview, setPreview] = useState(null);
  const [form, setForm] = useState({ full_name: "", password: "", passwordConfirm: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showMismatchActions, setShowMismatchActions] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setSubmitting] = useState(false);
  const [isLoading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = token ? await previewInvitation({ token }) : { status: "invalid" };
        if (mounted) setPreview(response);
      } catch (err) {
        if (mounted) setError(normalizeError(err, text));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [token]);

  function goToLogin() {
    window.location.hash = "#/login";
  }

  function logoutAndStay() {
    clearAuthSession();
    onSessionUpdated?.();
    setShowMismatchActions(false);
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) return;
    setError("");
    setMessage("");
    setShowMismatchActions(false);
    if (!token || preview?.status !== "valid") {
      setError(text.invalid);
      return;
    }
    if (!isAuthenticated && form.password !== form.passwordConfirm) {
      setError(text.passwordMismatch);
      return;
    }
    try {
      setSubmitting(true);
      const previousMarkets = getStoredMarkets();
      const session = isAuthenticated
        ? await acceptInvitationAuthenticated({ token })
        : await acceptInvitation({ token, full_name: form.full_name, password: form.password });
      saveAuthSession(session);
      const acceptedMarket = resolveAcceptedMarket(previousMarkets, session);
      if (acceptedMarket) setSelectedMarketId(acceptedMarket.id);
      onSessionUpdated?.();
      setMessage(text.success);
      window.location.hash = marketNeedsOnboarding(acceptedMarket) ? "#/onboarding" : "#/dashboard";
    } catch (err) {
      const normalized = normalizeError(err, text);
      setError(normalized);
      setShowMismatchActions(normalized === text.mismatch);
    } finally {
      setSubmitting(false);
    }
  }

  const statusMessage = preview?.status && preview.status !== "valid" ? text[preview.status] || text.invalid : "";

  return (
    <main className="login-page">
      <Card title={text.title}>
        {isLoading ? <p className="inline-result">{text.loading}</p> : null}
        {!isLoading && statusMessage ? <div className="form-error">{statusMessage}</div> : null}
        {!isLoading && preview?.status === "valid" ? (
          <form className="login-form" onSubmit={handleSubmit}>
            <dl className="detail-list">
              <div><dt>{text.market}</dt><dd>{preview.market_name || "-"}</dd></div>
              <div><dt>{text.invitedEmail}</dt><dd>{preview.email}</dd></div>
              <div><dt>{text.role}</dt><dd>{preview.role}</dd></div>
              <div><dt>{text.expires}</dt><dd>{preview.expires_at ? new Date(preview.expires_at).toLocaleString() : "-"}</dd></div>
            </dl>
            {!isAuthenticated && !preview.requires_existing_login ? (
              <>
                <label>
                  {text.fullName}
                  <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required />
                </label>
                <label>
                  {text.password}
                  <div className="password-field">
                    <input type={showPassword ? "text" : "password"} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required minLength={8} />
                    <button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? text.hide : text.show}</button>
                  </div>
                </label>
                <label>
                  {text.passwordConfirm}
                  <input type={showPassword ? "text" : "password"} value={form.passwordConfirm} onChange={(event) => setForm({ ...form, passwordConfirm: event.target.value })} required minLength={8} />
                </label>
              </>
            ) : null}
            {!isAuthenticated && preview.requires_existing_login ? <p className="inline-result">{text.existing}</p> : null}
            {isAuthenticated ? <p className="inline-result">{text.authenticated}</p> : null}
            {error ? <div className="form-error">{error}</div> : null}
            {showMismatchActions ? (
              <div className="modal-action-grid">
                <Button onClick={logoutAndStay}>{text.logout}</Button>
                <Button variant="primary" onClick={goToLogin}>{text.login}</Button>
              </div>
            ) : null}
            {message ? <div className="form-success">{message}</div> : null}
            <Button variant="primary" type="submit" disabled={isSubmitting || (!isAuthenticated && preview.requires_existing_login)}>
              {isSubmitting ? text.submitting : text.submit}
            </Button>
          </form>
        ) : null}
      </Card>
    </main>
  );
}
