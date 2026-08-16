import { useRef, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Button } from "../../components/ui/Button.jsx";
import { Modal } from "../../components/ui/Modal.jsx";

const stateLabels = {
  global_exact_match: "Global eşleşme (barkod)",
  global_strong_match: "Global eşleşme (isim/paket)",
  global_ambiguous: "Belirsiz — seçim gerekli",
  existing_market_product: "Markette zaten var",
  new_market_local: "Yeni yerel ürün",
  invalid: "Geçersiz",
  duplicate_in_file: "Dosyada tekrar eden",
  conflict: "Çelişki — çözülmeli",
};
const actionLabels = {
  adopt_global: "Global ürünü kullan",
  create_local: "Yerel ürün oluştur",
  update_existing: "Mevcut ürünü güncelle",
  skip: "Atlanacak",
  blocked: "Atlanacak (çözülmeli)",
};
const BLOCKED_STATES = new Set(["invalid", "duplicate_in_file", "conflict", "global_ambiguous"]);
const errorText = (error) => error?.body?.detail || (error?.status === 0 ? "Sunucuya ulaşılamadı. Lütfen tekrar deneyin." : "İşlem tamamlanamadı. Lütfen tekrar deneyin.");
const fileInfo = (file) => file ? `${file.name} · ${Math.ceil(file.size / 1024)} KB` : ".xlsx · En fazla 10 MiB";
const packageText = (normalized) => [normalized.package_amount, normalized.package_unit].filter(Boolean).join(" ") || normalized.package_size || "-";

export function PlatformMarketProductImportModal({ marketId, onClose, onImported }) {
  const fileInput = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const choose = (event) => {
    const next = event.target.files?.[0];
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".xlsx")) { setError("Lütfen .xlsx dosyası seçin."); return; }
    if (next.size > 10 * 1024 * 1024) { setError("Excel dosyası en fazla 10 MiB olabilir."); return; }
    setFile(next); setPreview(null); setResult(null); setOverrides({}); setError("");
  };

  const downloadTemplate = async () => {
    setError("");
    try { await platformApi.downloadMarketProductImportTemplate(marketId); } catch (err) { setError(errorText(err)); }
  };

  const analyze = async () => {
    if (!file) return;
    setBusy(true); setError("");
    try {
      setPreview(await platformApi.previewMarketProductImport(marketId, file));
      setOverrides({});
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };

  const setOverride = (row, decision) => setOverrides((current) => {
    const next = { ...current };
    if (decision) next[String(row)] = decision; else delete next[String(row)];
    return next;
  });

  const confirm = async () => {
    if (!preview) return;
    setBusy(true); setError("");
    try {
      const next = await platformApi.commitMarketProductImport(marketId, preview.import_id, overrides);
      setResult(next);
      onImported?.();
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };

  const counts = preview?.counts;
  const quota = preview?.quota;
  const actionableCount = preview ? preview.rows.filter((row) => !BLOCKED_STATES.has(row.state) || overrides[String(row.row)]).length : 0;

  const footer = result
    ? <Button variant="primary" onClick={onClose}>Tamam</Button>
    : <>
        <Button onClick={onClose} disabled={busy}>İptal</Button>
        {preview
          ? <Button variant="primary" onClick={confirm} disabled={busy || !actionableCount}>{busy ? "Aktarılıyor..." : `${actionableCount} satırı aktar`}</Button>
          : <Button variant="primary" onClick={analyze} disabled={!file || busy}>{busy ? "Kontrol ediliyor..." : "Önizleme oluştur"}</Button>}
      </>;

  return (
    <Modal className="catalog-import-modal" title="Excel ile Market Kataloğu Yükle" description="Önce dosyayı doğrulayın; belirsiz satırlar için seçim yapın, geçersiz satırlar aktarılmaz." onClose={onClose} footer={footer}>
      <div className="catalog-import-workflow">
        {error ? <p className="error-message" role="alert">{error}</p> : null}
        {!result && (
          <section className="catalog-import-files">
            <h3>Dosya</h3>
            <input ref={fileInput} className="visually-hidden" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={choose} />
            <div className="catalog-import-file-card">
              <div><strong>Market ürün Excel dosyası</strong><small>{fileInfo(file)}</small></div>
              <Button onClick={() => fileInput.current?.click()} disabled={busy}>{file ? "Değiştir" : "Dosya seç"}</Button>
            </div>
            <Button onClick={downloadTemplate} disabled={busy}>Şablonu indir</Button>
          </section>
        )}
        {preview && !result && (
          <section>
            <h3>Önizleme özeti</h3>
            <div className="catalog-import-summary">
              {[
                ["Toplam", counts.total],
                ["Global eşleşme", counts.global_exact_match + counts.global_strong_match],
                ["Belirsiz", counts.global_ambiguous],
                ["Markette var", counts.existing_market_product],
                ["Yeni yerel", counts.new_market_local],
                ["Geçersiz", counts.invalid],
                ["Tekrar/Çelişki", counts.duplicate_in_file + counts.conflict],
              ].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}
            </div>
            {quota?.would_exceed ? (
              <p className="error-message" role="alert">
                Plan kotası aşılacak: {quota.current_local_count} + {quota.projected_new_local} &gt; {quota.limit}. Bazı yeni yerel ürün satırları aktarım sırasında reddedilebilir.
              </p>
            ) : quota ? (
              <p className="inline-result">Özel ürün kullanımı: {quota.current_local_count} / {quota.limit ?? "sınırsız"} (+{quota.projected_new_local} önerilen)</p>
            ) : null}
            <div className="catalog-import-table">
              <table>
                <thead>
                  <tr><th>Satır</th><th>Ürün</th><th>Marka</th><th>Paket</th><th>Barkod</th><th>Fiyat</th><th>Eşleşme</th><th>İşlem</th></tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => {
                    const decision = overrides[String(row.row)];
                    const action = decision?.action || row.proposed_action;
                    const candidates = row.global_match?.candidates || [];
                    return (
                      <tr key={row.row}>
                        <td>{row.row}</td>
                        <td>{row.normalized?.product_name || "-"}{row.errors?.length ? <div className="form-error">{row.errors.join(" ")}</div> : null}{row.warnings?.length ? <div className="inline-result">{row.warnings.join(" ")}</div> : null}</td>
                        <td>{row.normalized?.brand || "-"}</td>
                        <td>{row.normalized ? packageText(row.normalized) : "-"}</td>
                        <td>{row.normalized?.barcode || "-"}</td>
                        <td>{row.normalized?.price || "-"}</td>
                        <td>{stateLabels[row.state] || row.state}</td>
                        <td>
                          {row.state === "global_ambiguous" && candidates.length ? (
                            <select value={decision?.target_id || ""} onChange={(event) => setOverride(row.row, event.target.value ? { action: "adopt_global", target_id: event.target.value } : null)}>
                              <option value="">Atlanacak</option>
                              {candidates.map((candidate) => <option key={candidate.product_id} value={candidate.product_id}>{candidate.name}{candidate.brand ? ` · ${candidate.brand}` : ""}</option>)}
                            </select>
                          ) : row.state === "existing_market_product" ? (
                            <select value={decision?.action || "update_existing"} onChange={(event) => setOverride(row.row, event.target.value === "update_existing" ? null : { action: event.target.value })}>
                              <option value="update_existing">Güncelle</option>
                              <option value="skip">Atla</option>
                            </select>
                          ) : row.state === "global_strong_match" ? (
                            <select value={decision?.action || "adopt_global"} onChange={(event) => setOverride(row.row, event.target.value === "adopt_global" ? null : { action: event.target.value })}>
                              <option value="adopt_global">Global ürünü kullan</option>
                              <option value="create_local">Yerel devam et</option>
                            </select>
                          ) : (
                            actionLabels[action] || action
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {result && (
          <p className="success-message" role="status">
            Toplam {result.total_rows} satır işlendi: {result.imported_rows} oluşturuldu/eklendi, {result.updated_rows} güncellendi, {result.skipped_rows} atlandı, {result.failed_rows} başarısız oldu.
          </p>
        )}
      </div>
    </Modal>
  );
}
