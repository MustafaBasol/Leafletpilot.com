import { useMemo, useState } from "react";
import { confirmPasswordReset } from "../api/authApi.js";
import { Button, Card } from "../components/ui/index.js";

function getToken() {
  const hash = window.location.hash || "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?")) : "";
  return new URLSearchParams(query).get("token") || "";
}

export function ResetPassword() {
  const token = useMemo(() => getToken(), []);
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) return;
    setError("");
    setMessage("");
    if (!token) {
      setError("Bu şifre sıfırlama bağlantısı geçerli değil.");
      return;
    }
    if (password.length < 8) {
      setError("Şifre en az 8 karakter olmalıdır.");
      return;
    }
    if (password !== passwordConfirm) {
      setError("Şifreler eşleşmiyor.");
      return;
    }
    try {
      setSubmitting(true);
      await confirmPasswordReset({ token, password });
      setMessage("Şifreniz güncellendi. Giriş sayfasına yönlendiriliyorsunuz.");
      window.setTimeout(() => {
        window.location.hash = "#/login";
      }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <Card title="Şifre Sıfırlama">
        {!token ? (
          <p className="form-error">Bu şifre sıfırlama bağlantısı geçerli değil.</p>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <label>
              Yeni şifre
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
              />
            </label>
            <label>
              Yeni şifre (tekrar)
              <input
                type="password"
                value={passwordConfirm}
                onChange={(event) => setPasswordConfirm(event.target.value)}
                required
                minLength={8}
              />
            </label>
            {error ? <div className="form-error">{error}</div> : null}
            {message ? <div className="form-success">{message}</div> : null}
            <Button variant="primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Kaydediliyor..." : "Şifreyi Güncelle"}
            </Button>
          </form>
        )}
      </Card>
    </main>
  );
}
