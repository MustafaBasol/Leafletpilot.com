import { useRef, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Button } from "../../components/ui/Button.jsx";
import { Modal } from "../../components/ui/Modal.jsx";

const labels = { new: "Yeni", update: "Güncellenecek", unchanged: "Değişiklik yok", invalid: "Geçersiz", ambiguous: "Belirsiz", conflict: "Çakışma" };
const errorText = (error) => error?.body?.detail || (error?.status === 0 ? "Sunucuya ulaşılamadı. Lütfen tekrar deneyin." : "İşlem tamamlanamadı. Lütfen tekrar deneyin.");
const fileInfo = (file, hint) => file ? `${file.name} · ${Math.ceil(file.size / 1024)} KB` : hint;

export function PlatformProductImportModal({ onClose, onImported }) {
  const excelInput = useRef(null);
  const zipInput = useRef(null);
  const [file, setFile] = useState(null); const [imagesZip, setImagesZip] = useState(null); const [preview, setPreview] = useState(null); const [result, setResult] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const choose = (event) => { const next = event.target.files?.[0]; if (!next) return; if (!next.name.toLowerCase().endsWith(".xlsx")) { setError("Lütfen .xlsx dosyası seçin."); return; } if (next.size > 10 * 1024 * 1024) { setError("Excel dosyası en fazla 10 MiB olabilir."); return; } setFile(next); setPreview(null); setResult(null); setError(""); };
  const chooseZip = (event) => { const next = event.target.files?.[0]; if (next && !next.name.toLowerCase().endsWith(".zip")) { setError("Lütfen .zip dosyası seçin."); return; } setImagesZip(next || null); setPreview(null); setResult(null); setError(""); };
  const analyze = async () => { if (!file) return; setBusy(true); setError(""); try { setPreview(await platformApi.previewGlobalProductImport(file, imagesZip)); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } };
  const confirm = async () => { if (!file) return; setBusy(true); setError(""); try { const next = await platformApi.importGlobalProducts(file, imagesZip); setResult(next); onImported?.(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } };
  const summary = preview?.counts;
  const validRows = (summary?.new || 0) + (summary?.update || 0) + (summary?.unchanged || 0);
  const footer = result ? <Button variant="primary" onClick={onClose}>Tamam</Button> : <><Button onClick={onClose} disabled={busy}>İptal</Button>{summary ? <Button variant="primary" onClick={confirm} disabled={busy || !validRows}>{busy ? "Aktarılıyor..." : `${validRows} geçerli satırı aktar`}</Button> : <Button variant="primary" onClick={analyze} disabled={!file || busy}>{busy ? "Kontrol ediliyor..." : "Önizleme oluştur"}</Button>}</>;
  return <Modal className="catalog-import-modal" title="Excel ile Ürün Yükle" description="Önce dosyayı doğrulayın; geçersiz veya çakışan satırlar aktarılmaz." onClose={onClose} footer={footer}>
    <div className="catalog-import-workflow">
      {error && <p className="error-message" role="alert">{error}</p>}
      {!result && <section className="catalog-import-files"><h3>Dosyalar</h3><input ref={excelInput} className="visually-hidden" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={choose} /><input ref={zipInput} className="visually-hidden" type="file" accept=".zip,application/zip" onChange={chooseZip} /><div className="catalog-import-file-card"><div><strong>Ürün Excel dosyası</strong><small>{fileInfo(file, ".xlsx · En fazla 10 MiB")}</small></div><Button onClick={() => excelInput.current?.click()} disabled={busy}>{file ? "Değiştir" : "Dosya seç"}</Button></div><div className="catalog-import-file-card"><div><strong>Görseller ZIP dosyası</strong><small>{fileInfo(imagesZip, "İsteğe bağlı · .zip")}</small></div><Button onClick={() => zipInput.current?.click()} disabled={busy}>{imagesZip ? "Değiştir" : "ZIP seç"}</Button></div></section>}
      {summary && !result && <section><h3>Önizleme özeti</h3><div className="catalog-import-summary">{[["Toplam", summary.total], ["Yeni", summary.new], ["Güncellenecek", summary.update], ["Hatalı", summary.invalid], ["Çakışan", summary.conflict + summary.ambiguous], ["Görselli", summary.with_image], ["Eksik görsel", summary.images_missing], ["Geçersiz görsel", summary.images_invalid]].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div><div className="catalog-import-table"><table><thead><tr><th>Satır</th><th>Ürün</th><th>Marka</th><th>Kategori</th><th>Görsel</th><th>İşlem</th><th>Uyarı</th></tr></thead><tbody>{preview.rows.map((row) => <tr key={row.row}><td>{row.row}</td><td>{row.canonical_name}</td><td>{row.brand}</td><td>{row.category}</td><td>{row.image_filename || "-"}</td><td>{labels[row.status] || row.status}</td><td>{row.error || row.image_error || "-"}</td></tr>)}</tbody></table></div></section>}
      {result && <p className="success-message" role="status">{result.created} ürün oluşturuldu, {result.updated} ürün güncellendi, {result.unchanged} ürün değişmedi; {result.skipped} satır atlandı. {result.images_uploaded} görsel yüklendi, {result.images_missing} görsel eksik, {result.images_invalid} görsel geçersiz; {result.images_awaiting_review} görsel inceleme bekliyor.</p>}
    </div>
  </Modal>;
}
