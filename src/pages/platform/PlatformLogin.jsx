import { useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { savePlatformSession } from "../../api/platformSession.js";

export function PlatformLogin({ onLogin }) {
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await platformApi.login(form.email, form.password);
      savePlatformSession(session);
      onLogin();
      window.location.hash = "#/platform/signup-requests";
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page platform-login">
      <form className="login-card" onSubmit={submit}>
        <span className="brand-mark">LP</span>
        <h1>Platform Admin</h1>
        <label>
          E-posta
          <input type="email" autoComplete="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        </label>
        <label>
          Şifre
          <input type="password" autoComplete="current-password" required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="login-button" disabled={loading}>{loading ? "Giriş yapılıyor..." : "Giriş Yap"}</button>
      </form>
    </main>
  );
}
