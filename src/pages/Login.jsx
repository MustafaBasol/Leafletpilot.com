import { useEffect, useState } from "react";
import { Button, Checkbox, Input } from "../components/ui/index.js";

export function Login({ onLogin, initialError = "" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [isSubmitting, setSubmitting] = useState(false);
  const [error, setError] = useState(initialError);

  useEffect(() => {
    setError(initialError);
  }, [initialError]);

  async function submitLogin(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await onLogin({ email, password, remember });
    } catch (submitError) {
      setError(submitError.message || "Giriş yapılamadı. Bilgileri kontrol edin.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-copy">
        <a className="brand login-brand" href="#/">
          <span className="brand-mark">LP</span>
          <span>
            <strong>LeafletPilot</strong>
            <small>Broşür Otomasyonu</small>
          </span>
        </a>
        <h1>Kampanya broşürlerinizi dakikalar içinde hazırlayın</h1>
        <p>Ürün listenizi gönderin, LeafletPilot profesyonel PDF ve sosyal medya görsellerinizi otomatik oluştursun.</p>
      </section>
      <form className="login-card" onSubmit={submitLogin}>
        <div>
          <h2>Giriş yap</h2>
          <p>Hesabınıza erişmek için bilgilerinizi girin.</p>
        </div>
        {error ? <p className="inline-result inline-result-warning">{error}</p> : null}
        <Input label="E-posta" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
        <Input label="Şifre" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
        <Checkbox label="Beni hatırla" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
        <Button variant="primary" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Giriş yapılıyor..." : "Giriş Yap"}
        </Button>
      </form>
    </main>
  );
}
