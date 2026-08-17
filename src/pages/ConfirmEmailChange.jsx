import { useEffect, useMemo, useState } from "react";
import { confirmEmailChange } from "../api/authApi.js";
import { Card } from "../components/ui/index.js";

function getToken() {
  const hash = window.location.hash || "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?")) : "";
  return new URLSearchParams(query).get("token") || "";
}

export function ConfirmEmailChange() {
  const token = useMemo(() => getToken(), []);
  const [status, setStatus] = useState("pending");
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setError("Bu doğrulama bağlantısı geçerli değil.");
      return;
    }
    let cancelled = false;
    confirmEmailChange({ token })
      .then((result) => {
        if (cancelled) return;
        setEmail(result.email || "");
        setStatus("success");
        window.setTimeout(() => {
          window.location.hash = "#/login";
        }, 2000);
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main className="login-page">
      <Card title="E-posta Doğrulama">
        {status === "pending" ? <p className="inline-result" role="status">Doğrulanıyor...</p> : null}
        {status === "success" ? (
          <p className="inline-result" role="status">
            E-posta adresiniz {email ? `${email} olarak ` : ""}güncellendi. Bundan sonra bu adresle giriş
            yapabilirsiniz. Giriş sayfasına yönlendiriliyorsunuz.
          </p>
        ) : null}
        {status === "error" ? (
          <p className="inline-result inline-result-warning" role="alert">{error}</p>
        ) : null}
      </Card>
    </main>
  );
}
