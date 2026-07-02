import { botConnections, messageFlow } from "../data/mockData.js";
import { Card, MessageFlowPreview, PageHeader, ProviderConnectionCard } from "../components/ui/index.js";

export function BotConnections() {
  return (
    <>
      <PageHeader
        title="Bot Bağlantıları"
        description="Telegram MVP bağlantısını ve gelecekteki WhatsApp kanalını tek ekrandan izleyin. Bu fazda tüm aksiyonlar yerel simülasyondur."
      />
      <section className="provider-grid">
        {botConnections.map((connection) => (
          <ProviderConnectionCard connection={connection} key={connection.id} />
        ))}
      </section>
      <section className="dashboard-grid">
        <Card title="Mesaj Akışı Önizlemesi" className="span-8">
          <MessageFlowPreview steps={messageFlow} />
        </Card>
        <Card title="Operasyon Notu" className="span-4">
          <div className="empty-state compact-empty">
            <div>
              <h2>Gerçek API çağrısı yok</h2>
              <p>Bu ekran demo ve satış sunumu için bağlantı durumlarını temsil eder. Telegram ve WhatsApp entegrasyonu sonraki fazda planlanacak.</p>
            </div>
          </div>
        </Card>
      </section>
    </>
  );
}
