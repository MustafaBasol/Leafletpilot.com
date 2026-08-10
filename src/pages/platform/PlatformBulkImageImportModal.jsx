import { useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Modal } from "../../components/ui/Modal.jsx";

function errorText(error) {
  return error?.body?.detail || error?.message || "İşlem başarısız oldu.";
}

const STATUS_LABELS = {
  exact_match: "Exact match",
  matched: "Matched",
  ambiguous: "Ambiguous",
  unmatched: "Unmatched",
  invalid: "Invalid",
  error: "Error",
};

export function PlatformBulkImageImportModal({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [resolutions, setResolutions] = useState({});
  const [importResult, setImportResult] = useState(null);
  const [selectedImageIds, setSelectedImageIds] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const chooseFile = (event) => {
    const picked = event.target.files?.[0];
    if (!picked) return;
    if (!picked.name.toLowerCase().endsWith(".zip")) { setError("Please choose a .zip package."); return; }
    if (picked.size > 60 * 1024 * 1024) { setError("ZIP package must be 60 MiB or smaller."); return; }
    setFile(picked); setError(""); setPreview(null); setImportResult(null); setResolutions({});
  };

  const runPreview = async () => {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const result = await platformApi.previewGlobalProductImageBulkImport(file);
      setPreview(result);
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };

  const setResolution = (rowIndex, productId) => setResolutions((current) => ({ ...current, [rowIndex]: productId }));

  const confirmImport = async () => {
    if (!file || !preview) return;
    setBusy(true); setError("");
    try {
      const resolutionList = preview.rows
        .filter((row) => row.status === "ambiguous" && resolutions[row.row_index])
        .map((row) => ({ row_index: row.row_index, product_id: resolutions[row.row_index] }));
      const result = await platformApi.importGlobalProductImageBulkImport(file, resolutionList);
      setImportResult(result);
      setSelectedImageIds(result.rows.filter((row) => row.image_id).map((row) => row.image_id));
      onImported?.();
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };

  const toggleSelected = (imageId) => setSelectedImageIds((current) => (current.includes(imageId) ? current.filter((id) => id !== imageId) : [...current, imageId]));

  const bulkApprove = async () => {
    if (selectedImageIds.length === 0) return;
    setBusy(true); setError("");
    try { await platformApi.bulkApproveGlobalProductImages(selectedImageIds); onImported?.(); setError(""); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };

  const bulkReject = async () => {
    if (selectedImageIds.length === 0) return;
    setBusy(true); setError("");
    try { await platformApi.bulkRejectGlobalProductImages(selectedImageIds); onImported?.(); setError(""); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };

  return (
    <Modal title="Toplu Görsel Yükle" description="Upload a products.zip package containing manifest.csv and an images/ folder." onClose={onClose}>
      <div className="form-grid">
        {error && <p className="error-message" role="alert">{error}</p>}

        {!importResult && (
          <>
            <input type="file" accept=".zip" onChange={chooseFile} />
            <div>
              <button type="button" disabled={!file || busy} onClick={runPreview}>{busy ? "Analyzing..." : "Analyze package"}</button>
              <button type="button" onClick={onClose} disabled={busy}>Cancel</button>
            </div>
          </>
        )}

        {preview && !importResult && (
          <>
            <p>
              Total: {preview.counts.total} · Exact: {preview.counts.exact_match} · Matched: {preview.counts.matched} ·
              {" "}Ambiguous: {preview.counts.ambiguous} · Unmatched: {preview.counts.unmatched} ·
              {" "}Invalid: {preview.counts.invalid} · Errors: {preview.counts.error}
            </p>
            <div style={{ maxHeight: 320, overflowY: "auto" }}>
              <table>
                <thead><tr><th>Preview</th><th>Row</th><th>Name</th><th>Status</th><th>Matched product</th><th /></tr></thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr key={row.row_index}>
                      <td>{row.thumbnail_data_uri && <img src={row.thumbnail_data_uri} alt={row.image_filename || "preview"} style={{ maxWidth: 48, maxHeight: 48 }} />}</td>
                      <td>{row.row_index}</td>
                      <td>{row.name || row.image_filename}</td>
                      <td>{STATUS_LABELS[row.status] || row.status}{row.reason ? ` — ${row.reason}` : ""}</td>
                      <td>{row.matched_product?.name || "—"}</td>
                      <td>
                        {row.status === "ambiguous" && (
                          <select value={resolutions[row.row_index] || ""} onChange={(event) => setResolution(row.row_index, event.target.value)}>
                            <option value="">Choose product…</option>
                            {row.candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
                          </select>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <button type="button" disabled={busy} onClick={confirmImport}>{busy ? "Importing..." : "Confirm import"}</button>
              <button type="button" onClick={onClose} disabled={busy}>Cancel</button>
            </div>
          </>
        )}

        {importResult && (
          <>
            <p>
              Uploaded: {importResult.uploaded} · Needs review: {importResult.needs_review} · Ambiguous skipped:{" "}
              {importResult.ambiguous} · Unmatched: {importResult.unmatched} · Invalid: {importResult.invalid} · Errors: {importResult.errors}
            </p>
            <div style={{ maxHeight: 320, overflowY: "auto" }}>
              <table>
                <thead><tr><th /><th>Row</th><th>Status</th><th>Detail</th></tr></thead>
                <tbody>
                  {importResult.rows.map((row) => (
                    <tr key={row.row_index}>
                      <td>{row.image_id && <input type="checkbox" checked={selectedImageIds.includes(row.image_id)} onChange={() => toggleSelected(row.image_id)} />}</td>
                      <td>{row.row_index}</td>
                      <td>{row.status}</td>
                      <td>{row.reason || (row.image_id ? "Uploaded, needs review" : "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <button type="button" disabled={busy || selectedImageIds.length === 0} onClick={bulkApprove}>Approve selected</button>
              <button type="button" disabled={busy || selectedImageIds.length === 0} onClick={bulkReject}>Reject selected</button>
              <button type="button" onClick={onClose} disabled={busy}>Done</button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
