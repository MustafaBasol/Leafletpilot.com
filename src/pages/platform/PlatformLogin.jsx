import { useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { savePlatformSession } from "../../api/platformSession.js";
import { t } from "./platformI18n.js";

function normalizeLoginError(error) {
  if (error?.status === 401 || error?.status === 422) return t("invalidCredentials");
  return error?.message || t("invalidCredentials");
}

export function PlatformLogin({ onLogin }) {
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      const session = await platformApi.login(form.email, form.password);
      savePlatformSession(session);
      onLogin();
      window.location.hash = "#/platform/signup-requests";
    } catch (err) {
      setError(normalizeLoginError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="platform-login-page">
      <form className="platform-login-card" onSubmit={submit}>
        <div className="platform-login-brand">
          <span className="brand-mark">LP</span>
          <span>
            <strong>LeafletPilot</strong>
            <small>{t("platformAdmin")}</small>
          </span>
        </div>
        <div className="platform-login-heading">
          <h1>{t("platformAdmin")}</h1>
          <p>{t("platformAdminDescription")}</p>
        </div>
        <label className="platform-login-field" htmlFor="platform-admin-email">
          <span>{t("email")}</span>
          <input
            id="platform-admin-email"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </label>
        <label className="platform-login-field" htmlFor="platform-admin-password">
          <span>{t("password")}</span>
          <span className="platform-password-control">
            <input
              id="platform-admin-password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
            <button
              type="button"
              className="platform-password-toggle"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={showPassword ? t("hidePassword") : t("showPassword")}
            >
              {showPassword ? "Gizle" : "Göster"}
            </button>
          </span>
        </label>
        {error ? (
          <p className="platform-login-error" role="alert">
            {error}
          </p>
        ) : null}
        <button className="platform-login-submit" type="submit" disabled={loading} aria-busy={loading}>
          {loading ? t("signingIn") : t("signIn")}
        </button>
      </form>
    </main>
  );
}
