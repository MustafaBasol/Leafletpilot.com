import { useState } from "react";
import { apiBaseUrl, demoMarketId, isRealApiEnabled } from "../api/config.js";
import { apiClient } from "../api/client.js";
import { Button, Card } from "./ui/index.js";

export function ApiStatus() {
  const [result, setResult] = useState("");
  const [isChecking, setChecking] = useState(false);

  async function checkHealth() {
    setChecking(true);
    setResult("");

    try {
      const health = await apiClient.get("/health");
      setResult(`Sağlıklı: ${health.status || "ok"}`);
    } catch (error) {
      setResult(error.message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <Card
      title="API Durumu"
      className="span-12"
      action={
        <Button onClick={checkHealth} disabled={isChecking}>
          {isChecking ? "Kontrol ediliyor" : "Sağlık Kontrolü"}
        </Button>
      }
    >
      <dl className="api-status-grid">
        <div>
          <dt>API modu</dt>
          <dd>{isRealApiEnabled ? "Real API" : "Mock"}</dd>
        </div>
        <div>
          <dt>API adresi</dt>
          <dd>{apiBaseUrl}</dd>
        </div>
        <div>
          <dt>Demo market id</dt>
          <dd>{demoMarketId ? "Var" : "Eksik"}</dd>
        </div>
        <div>
          <dt>Son kontrol</dt>
          <dd>{result || "Henüz kontrol edilmedi"}</dd>
        </div>
      </dl>
    </Card>
  );
}

