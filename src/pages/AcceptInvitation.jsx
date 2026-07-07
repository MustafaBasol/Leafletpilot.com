import { useState } from "react";
import { acceptInvitation, acceptInvitationAuthenticated } from "../api/teamApi.js";
import { clearAuthSession, saveAuthSession } from "../api/authSession.js";
import { Button, Card } from "../components/ui/index.js";

const mismatchMessage =
  "Bu davet başka bir e-posta adresi için oluşturulmuş. Davet edilen hesapla giriş yapın veya mevcut oturumdan çıkın.";

function getToken() {
  const hash = window.location.hash || "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?")) : "";
  return new URLSearchParams(query).get("token") || "";
}

export function AcceptInvitation({ isAuthenticated, onSessionUpdated }) {
  const [form, setForm] = useState({ full_name: "", password: "", passwordConfirm: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showMismatchActions, setShowMismatchActions] = useState(false);
  const [isSubmitting, setSubmitting] = useState(false);
  const token = getToken();

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
    setError("");
    setMessage("");
    setShowMismatchActions(false);
    if (!token) {
      setError("Geçersiz davet.");
      return;
    }
    if (!isAuthenticated && form.password !== form.passwordConfirm) {
      setError("Şifreler eşleşmiyor.");
      return;
    }
    try {
      setSubmitting(true);
      const session = isAuthenticated
        ? await acceptInvitationAuthenticated({ token })
        : await acceptInvitation({ token, full_name: form.full_name, password: form.password });
      saveAuthSession(session);
      onSessionUpdated?.();
      if (isAuthenticated) {
        window.location.hash = "#/";
        return;
      }
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/login`);
      setMessage("Hesabınız oluşturuldu. Şimdi giriş yapabilirsiniz.");
      window.setTimeout(() => {
        window.location.hash = "#/login";
      }, 1200);
    } catch (err) {
      if (err.message === mismatchMessage || err.body?.detail?.code === "invitation_email_mismatch") {
        setError(mismatchMessage);
        setShowMismatchActions(true);
      } else {
        setError(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <Card title="Daveti Kabul Et">
        <form className="login-form" onSubmit={handleSubmit}>
          {!isAuthenticated && (
            <>
              <label>
                Ad Soyad
                <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required />
              </label>
              <label>
                Şifre
                <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required minLength={8} />
              </label>
              <label>
                Şifre Tekrar
                <input type="password" value={form.passwordConfirm} onChange={(event) => setForm({ ...form, passwordConfirm: event.target.value })} required minLength={8} />
              </label>
            </>
          )}
          {isAuthenticated && <p>Mevcut oturumunuzla daveti kabul edebilirsiniz.</p>}
          {error && <div className="form-error">{error}</div>}
          {showMismatchActions ? (
            <div className="modal-action-grid">
              <Button onClick={logoutAndStay}>Çıkış Yap</Button>
              <Button variant="primary" onClick={goToLogin}>Giriş Sayfasına Git</Button>
            </div>
          ) : null}
          {message && <div className="form-success">{message}</div>}
          <Button variant="primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Kabul ediliyor..." : "Daveti Kabul Et"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
