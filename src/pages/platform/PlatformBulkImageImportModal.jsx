import { useRef, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Button } from "../../components/ui/Button.jsx";
import { Modal } from "../../components/ui/Modal.jsx";

const STATUS_LABELS = { exact_match: "Kesin eşleşme", matched: "Eşleşti", ambiguous: "Belirsiz", unmatched: "Eşleşmedi", invalid: "Geçersiz", error: "Hata" };
const STATUS_CLASSES = { exact_match: "badge-success", matched: "badge-success", ambiguous: "badge-warning", unmatched: "badge-neutral", invalid: "badge-danger", error: "badge-danger" };
const ERROR_MESSAGES = {
  "ZIP package must contain manifest.csv.": "ZIP paketinde manifest.csv bulunamadı.",
  "ZIP package must contain an images/ folder.": "ZIP paketinde images/ klasörü bulunamadı.",
  "File is not a valid ZIP package.": "Seçilen dosya geçerli bir ZIP paketi değil.",
  "ZIP package is empty.": "ZIP paketi boş.",
  "ZIP package exceeds the upload size limit.": "ZIP paketi en fazla 60 MiB olabilir.",
};
const errorText = (error) => ERROR_MESSAGES[error?.body?.detail || error?.message] || (error?.status === 0 ? "Sunucuya ulaşılamadı. Lütfen tekrar deneyin." : "İşlem tamamlanamadı. Lütfen tekrar deneyin.");
const countForImport = (preview, resolutions) => (preview?.rows || []).filter((row) => row.status === "exact_match" || row.status === "matched" || (row.status === "ambiguous" && resolutions[row.row_index])).length;

export function PlatformBulkImageImportModal({ onClose, onImported }) {
  const fileInput = useRef(null);
  const [file, setFile] = useState(null); const [preview, setPreview] = useState(null); const [resolutions, setResolutions] = useState({}); const [importResult, setImportResult] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const chooseFile = (event) => { const picked = event.target.files?.[0]; if (!picked) return; if (!picked.name.toLowerCase().endsWith(".zip")) { setError("Lütfen .zip paketi seçin."); return; } if (picked.size > 60 * 1024 * 1024) { setError("ZIP paketi en fazla 60 MiB olabilir."); return; } setFile(picked); setPreview(null); setImportResult(null); setResolutions({}); setError(""); event.target.value = ""; };
  const runPreview = async () => { if (!file) return; setBusy(true); setError(""); try { setPreview(await platformApi.previewGlobalProductImageBulkImport(file)); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } };
  const confirmImport = async () => { if (!file || !preview) return; setBusy(true); setError(""); try { const resolutionList = preview.rows.filter((row) => row.status === "ambiguous" && resolutions[row.row_index]).map((row) => ({ row_index: row.row_index, product_id: resolutions[row.row_index] })); setImportResult(await platformApi.importGlobalProductImageBulkImport(file, resolutionList)); onImported?.(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } };
  const importCount = countForImport(preview, resolutions);
  const footer = importResult ? <Button variant="primary" onClick={onClose} disabled={busy}>Tamam</Button> : <><Button onClick={onClose} disabled={busy}>İptal</Button><Button variant="primary" onClick={preview ? confirmImport : runPreview} disabled={!file || busy || Boolean(preview && !importCount)}>{busy ? (preview ? "Görseller yükleniyor..." : "Paket analiz ediliyor...") : preview ? `${importCount} görseli yükle` : "Paketi Analiz Et"}</Button></>;
  return <Modal className="catalog-import-modal bulk-image-import-modal" title="Toplu Görsel Yükle" description="Paketinizi doğrulayın ve eşleşen görselleri güvenle global kataloğa ekleyin." onClose={onClose} footer={footer}>
    <div className="catalog-import-workflow">
      {error && <p className="error-message" role="alert">{error}</p>}
      {!importResult && <><input ref={fileInput} className="visually-hidden" type="file" accept=".zip,application/zip" onChange={chooseFile} />
        <section className="catalog-import-files"><h3>Toplu görsel paketi</h3><div className="catalog-import-file-card bulk-image-file-card"><div className="bulk-image-file-icon" aria-hidden="true">⇧</div><div><strong>{file ? file.name : "ZIP paketi seçilmedi"}</strong><small>{file ? `${Math.ceil(file.size / 1024)} KB · Analiz için hazır` : "ZIP dosyası manifest.csv ve images/ klasörü içermelidir."}</small><small>PNG, JPEG ve WebP desteklenir.</small></div><Button onClick={() => fileInput.current?.click()} disabled={busy}>{file ? "Değiştir" : "ZIP seç"}</Button></div></section>
        {preview && <section><h3>Önizleme özeti</h3><div className="catalog-import-summary bulk-image-summary">{[["Toplam", preview.counts.total], ["Kesin eşleşme", preview.counts.exact_match], ["Eşleşen", preview.counts.matched], ["Belirsiz", preview.counts.ambiguous], ["Eşleşmeyen", preview.counts.unmatched], ["Geçersiz", preview.counts.invalid], ["Yüklemeye hazır", importCount]].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div><div className="catalog-import-table bulk-image-preview-table"><table><thead><tr><th>Önizleme</th><th>Ürün</th><th>Eşleşme</th><th>Dosya</th><th>Durum</th><th>Uyarı</th></tr></thead><tbody>{preview.rows.map((row) => <tr key={row.row_index}><td>{row.thumbnail_data_uri ? <img className="catalog-thumb" src={row.thumbnail_data_uri} alt={`${row.image_filename || "Görsel"} önizlemesi`} /> : "—"}</td><td>{row.matched_product?.name || row.name || "—"}</td><td>{row.match_method === "id" ? "Ürün kimliği" : row.match_method === "barcode" ? "Barkod" : row.match_method === "name" ? "Ürün adı" : "—"}</td><td>{row.image_filename || "—"}</td><td><span className={`badge ${STATUS_CLASSES[row.status] || "badge-neutral"}`}>{STATUS_LABELS[row.status] || "Bilinmiyor"}</span></td><td>{row.status === "ambiguous" ? <select aria-label="Belirsiz ürün eşleşmesi" value={resolutions[row.row_index] || ""} onChange={(event) => setResolutions((current) => ({ ...current, [row.row_index]: event.target.value }))}><option value="">Ürün seçin</option>{row.candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}</select> : row.reason || "—"}</td></tr>)}</tbody></table></div></section>}</>}
      {importResult && <section className="bulk-image-success" role="status"><div className="bulk-image-success-icon" aria-hidden="true">✓</div><div><h3>{importResult.uploaded} görsel başarıyla yüklendi.</h3><p>{importResult.approved || 0} görsel onaylandı ve global katalogda kullanıma hazır.</p></div></section>}
    </div>
  </Modal>;
}