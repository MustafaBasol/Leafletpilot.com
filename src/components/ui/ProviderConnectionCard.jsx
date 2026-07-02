import { useState } from "react";
import { Badge } from "./Badge.jsx";
import { Button } from "./Button.jsx";
import { Icon } from "./Icon.jsx";
import { StatusBadge } from "./StatusBadge.jsx";

export function SetupChecklist({ items }) {
  return (
    <ul className="setup-checklist">
      {items.map((item) => (
        <li key={item}>
          <Icon name="check" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function ProviderConnectionCard({ connection }) {
  const [result, setResult] = useState("");
  const identity = connection.botName || connection.phoneNumber || "Tanımlanmadı";

  return (
    <article className="provider-card">
      <div className="provider-card-top">
        <div className="provider-icon">
          <Icon name={connection.id === "telegram" ? "send" : "message"} />
        </div>
        <div>
          <h3>{connection.provider}</h3>
          <Badge tone={connection.tone}>{connection.status}</Badge>
        </div>
      </div>
      <dl className="detail-list">
        <div>
          <dt>Bot / Numara</dt>
          <dd>{identity}</dd>
        </div>
        <div>
          <dt>Webhook</dt>
          <dd>
            <StatusBadge status={connection.webhookStatus} />
          </dd>
        </div>
        <div>
          <dt>Son mesaj</dt>
          <dd>{connection.lastMessageAt}</dd>
        </div>
        <div>
          <dt>Son hata</dt>
          <dd>{connection.lastError || "Hata yok"}</dd>
        </div>
      </dl>
      <SetupChecklist items={connection.setupChecklist} />
      {result ? <p className="inline-result">{result}</p> : null}
      <div className="card-actions">
        <Button onClick={() => setResult(`${connection.provider} bağlantı testi simüle edildi.`)}>Bağlantıyı Test Et</Button>
        <Button variant="primary" onClick={() => setResult(`${connection.provider} test mesajı kuyruğa alındı.`)}>
          Test Mesajı Gönder
        </Button>
      </div>
    </article>
  );
}
