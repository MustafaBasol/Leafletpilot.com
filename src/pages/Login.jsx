import { useState } from "react";
import { Button, Checkbox, Input } from "../components/ui/index.js";

export function Login({ onLogin }) {
  const [email, setEmail] = useState("operator@leafletpilot.com");
  const [password, setPassword] = useState("demo");
  const [remember, setRemember] = useState(true);

  function submitLogin(event) {
    event.preventDefault();
    onLogin({ email, remember });
  }

  return (
    <main className="login-shell">
      <section className="login-copy">
        <a className="brand login-brand" href="#/login">
          <span className="brand-mark">LP</span>
          <span>
            <strong>LeafletPilot</strong>
            <small>AI Brochure Automation</small>
          </span>
        </a>
        <h1>Kampanya broşürlerinizi dakikalar içinde hazırlayın</h1>
        <p>Ürün listenizi gönderin, LeafletPilot profesyonel PDF ve sosyal medya görsellerinizi otomatik oluştursun.</p>
        <div className="login-preview-card">
          <strong>Anadolu Market</strong>
          <span>Önizleme hazır · 24 ürün · 3 çıktı</span>
        </div>
      </section>
      <form className="login-card" onSubmit={submitLogin}>
        <div>
          <h2>Giriş yap</h2>
          <p>Demo paneline devam etmek için bilgileri kullanabilirsiniz.</p>
        </div>
        <Input label="E-posta" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <Input label="Şifre" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        <Checkbox label="Beni hatırla" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
        <Button variant="primary" type="submit">
          Giriş Yap
        </Button>
      </form>
    </main>
  );
}
