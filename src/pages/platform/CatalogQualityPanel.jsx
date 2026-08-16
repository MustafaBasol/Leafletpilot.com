import { useEffect, useMemo, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Button } from "../../components/ui/Button.jsx";
import { Modal } from "../../components/ui/Modal.jsx";
import { Table } from "../../components/ui/Table.jsx";
import {
  candidateProducts,
  catalogQualitySeverityLabel,
  catalogQualityStateLabel,
  mergeSelection,
  readableQualityItems,
} from "./catalogQualityUtils.js";

const PAGE_SIZE = 25;
const stateOptions = [
  ["", "Çözülmemiş adaylar"],
  ["exact_duplicate", "Kesin yinelenenler"],
  ["strong_candidate", "Güçlü adaylar"],
  ["barcode_conflict", "Barkod çakışmaları"],
  ["identity_conflict", "Kimlik çakışmaları"],
  ["alias_conflict", "Alternatif ad çakışmaları"],
  ["ignored", "Yok sayılanlar"],
];

function errorText(error) {
  return error?.body?.detail || error?.message || "Veri kalitesi işlemi tamamlanamadı.";
}

function productSummary(product) {
  const brand = product.brand_name || product.brand || "Marka belirtilmedi";
  const packageText = [product.package_size, product.package_type].filter(Boolean).join(" ");
  return <div className="catalog-quality-product">{product.image_url ? <img src={product.image_url} alt="" /> : null}<div><strong>{product.name || "Bilinmeyen ürün"}</strong><small>{[brand, packageText, product.barcode].filter(Boolean).join(" · ") || "Ek kimlik bilgisi yok"}</small></div></div>;
}

function detailList(values, className) {
  const items = readableQualityItems(values);
  if (!items.length) return null;
  return <ul className={className}>{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

export function CatalogQualityPanel({ onMerged }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [state, setState] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [comparison, setComparison] = useState(null);
  const [winnerId, setWinnerId] = useState("");
  const [preview, setPreview] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [barcodeConfirmed, setBarcodeConfirmed] = useState(false);
  const [ignoreTarget, setIgnoreTarget] = useState(null);
  const [ignoreNote, setIgnoreNote] = useState("");

  const load = async (nextOffset = offset, nextState = state) => {
    setLoading(true);
    setError("");
    try {
      const response = await platformApi.listCatalogQualityCandidates({ state: nextState || undefined, limit: PAGE_SIZE, offset: nextOffset });
      setItems(response.items || []);
      setTotal(response.total || 0);
      setOffset(nextOffset);
    } catch (loadError) {
      setError(errorText(loadError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(0, state); }, [state]);

  const selectedProducts = useMemo(() => candidateProducts(comparison), [comparison]);
  const selection = useMemo(() => mergeSelection(comparison, winnerId), [comparison, winnerId]);
  const previewBlockers = readableQualityItems(preview?.blockers);
  const previewWarnings = readableQualityItems(preview?.warnings);
  const requiresBarcodeConfirmation = previewWarnings.some((item) => /barkod|barcode/i.test(item));

  const openComparison = (candidate) => {
    const { productB } = candidateProducts(candidate);
    setComparison(candidate);
    setWinnerId(productB.id || "");
    setPreview(null);
    setConfirmed(false);
    setBarcodeConfirmed(false);
    setError("");
  };

  const loadPreview = async () => {
    if (!selection.sourceId || !selection.targetId || selection.sourceId === selection.targetId) return;
    setBusy(true);
    setError("");
    try {
      const response = await platformApi.previewCatalogProductMerge({ source_product_id: selection.sourceId, target_product_id: selection.targetId });
      setPreview(response);
      setConfirmed(false);
      setBarcodeConfirmed(false);
    } catch (previewError) {
      setError(errorText(previewError));
    } finally {
      setBusy(false);
    }
  };

  const merge = async () => {
    if (!preview || !confirmed || !selection.sourceId || !selection.targetId) return;
    if (requiresBarcodeConfirmation && !barcodeConfirmed) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.mergeCatalogProducts({ source_product_id: selection.sourceId, target_product_id: selection.targetId, confirm_barcode_mismatch: barcodeConfirmed });
      setComparison(null);
      setPreview(null);
      setNotice("Ürünler birleştirildi. Katalog listesi yenilendi.");
      await load(0);
      await onMerged?.();
    } catch (mergeError) {
      setError(errorText(mergeError));
    } finally {
      setBusy(false);
    }
  };

  const ignore = async () => {
    const { productA, productB } = candidateProducts(ignoreTarget);
    if (!productA.id || !productB.id) return;
    setBusy(true);
    setError("");
    try {
      await platformApi.ignoreCatalogQualityCandidate({ product_a_id: productA.id, product_b_id: productB.id, note: ignoreNote.trim() || null });
      setIgnoreTarget(null);
      setIgnoreNote("");
      setNotice("Aday aynı ürün değil olarak işaretlendi.");
      await load(0);
    } catch (ignoreError) {
      setError(errorText(ignoreError));
    } finally {
      setBusy(false);
    }
  };

  return <section className="catalog-quality" aria-label="Katalog veri kalitesi">
    <div className="catalog-quality-heading"><div><h2>Veri Kalitesi</h2><p>Olası yinelenenleri inceleyin; birleşme yalnızca açık onayla uygulanır.</p></div><Button variant="primary" onClick={() => load(0)} disabled={loading || busy}>Yenile</Button></div>
    <div className="catalog-quality-filters"><label>Göster<select value={state} onChange={(event) => setState(event.target.value)}>{stateOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><span>{total} aday</span></div>
    {error ? <p className="error-message" role="alert">{error}</p> : null}
    {notice ? <p className="success-message" role="status">{notice}</p> : null}
    {loading ? <p>Yükleniyor...</p> : <Table columns={["Ürün A", "Ürün B", "Neden", "Durum", "İşlemler"]}>{items.map((candidate) => {
      const { productA, productB } = candidateProducts(candidate);
      const blockers = readableQualityItems(candidate.blockers);
      return <tr key={candidate.id || `${productA.id}-${productB.id}`}><td>{productSummary(productA)}</td><td>{productSummary(productB)}</td><td><strong>{candidate.reason || "Kanıt bekliyor"}</strong>{detailList(candidate.matching_fields, "catalog-quality-details")}{blockers.length ? <small className="catalog-quality-blocked">{blockers.join(" · ")}</small> : null}</td><td><span className={`badge catalog-quality-severity-${candidate.severity || "medium"}`}>{catalogQualityStateLabel(candidate.state)} · {catalogQualitySeverityLabel(candidate.severity)}</span></td><td className="catalog-quality-actions"><Button onClick={() => openComparison(candidate)}>Karşılaştır</Button><Button variant="primary" disabled={busy} onClick={() => openComparison(candidate)}>Birleştir</Button><Button disabled={busy} onClick={() => { setIgnoreTarget(candidate); setIgnoreNote(""); }}>Aynı ürün değil</Button></td></tr>;
    })}</Table>}
    {!loading && !items.length ? <p className="empty-state">Bu filtre için incelenecek aday yok.</p> : null}
    <div className="catalog-quality-pagination"><Button disabled={loading || offset === 0} onClick={() => load(Math.max(0, offset - PAGE_SIZE))}>Önceki</Button><span>{offset + 1}-{Math.min(offset + PAGE_SIZE, total)} / {total}</span><Button disabled={loading || offset + PAGE_SIZE >= total} onClick={() => load(offset + PAGE_SIZE)}>Sonraki</Button></div>
    {comparison ? <Modal className="catalog-quality-modal" title="Ürünleri karşılaştır ve birleştir" description="Kazanan ürün korunur; kaybeden ürün yönlendirilmiş, pasif bir katalog kaydı olarak tutulur." onClose={() => !busy && setComparison(null)} footer={<><Button onClick={() => setComparison(null)} disabled={busy}>İptal</Button><Button onClick={loadPreview} disabled={busy || !selection.sourceId || !selection.targetId}>Etki önizlemesi</Button><Button variant="primary" onClick={merge} disabled={busy || !preview?.can_merge || !confirmed || (requiresBarcodeConfirmation && !barcodeConfirmed)}>{busy ? "Birleştiriliyor..." : "Birleştirmeyi Onayla"}</Button></>}>
      <div className="catalog-quality-compare"><div>{productSummary(selectedProducts.productA)}</div><div>{productSummary(selectedProducts.productB)}</div></div>
      <label className="catalog-quality-winner">Korunacak kanonik ürün<select value={winnerId} onChange={(event) => { setWinnerId(event.target.value); setPreview(null); setConfirmed(false); setBarcodeConfirmed(false); }}><option value={selectedProducts.productA.id}>{selectedProducts.productA.name || "Ürün A"}</option><option value={selectedProducts.productB.id}>{selectedProducts.productB.name || "Ürün B"}</option></select></label>
      <p>Kaybeden ürün: <strong>{selection.sourceId === selectedProducts.productA.id ? selectedProducts.productA.name : selectedProducts.productB.name}</strong></p>
      {detailList(comparison.matching_fields, "catalog-quality-details")}
      {preview ? <section className="catalog-quality-preview"><h3>Etki önizlemesi</h3><dl><div><dt>Market benimsemeleri</dt><dd>{preview.market_adoptions?.source_count ?? preview.market_adoptions ?? 0}</dd></div><div><dt>Taşınacak alternatif ad</dt><dd>{preview.aliases?.move_count ?? 0}</dd></div><div><dt>Geçmiş kampanya kaydı</dt><dd>{(preview.historical_references?.campaign_items || 0) + (preview.historical_references?.matching_suggestions || 0)}</dd></div></dl>{previewBlockers.length ? <><h4>Birleştirmeyi engelleyen durumlar</h4>{detailList(previewBlockers, "catalog-quality-blockers")}</> : null}{previewWarnings.length ? <><h4>Uyarılar</h4>{detailList(previewWarnings, "catalog-quality-warnings")}</> : null}{preview.can_merge ? <label className="catalog-quality-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> Etkiyi inceledim; bu kalıcı bir katalog birleşimidir.</label> : <p className="catalog-quality-blocked">Bu seçim mevcut haliyle birleştirilemez.</p>}{requiresBarcodeConfirmation ? <label className="catalog-quality-confirm"><input type="checkbox" checked={barcodeConfirmed} onChange={(event) => setBarcodeConfirmed(event.target.checked)} /> Farklı açık barkodları inceledim ve kanonik ürünü bilerek seçtim.</label> : null}</section> : <p className="catalog-quality-hint">Birleştirme öncesi market benimsemeleri, alternatif adlar, görseller ve geçmiş kayıtlar için etki önizlemesini yükleyin.</p>}
    </Modal> : null}
    {ignoreTarget ? <Modal className="catalog-quality-ignore-modal" title="Aynı ürün değil" description="Bu çift sonraki kalite taramalarında yok sayılacaktır." onClose={() => !busy && setIgnoreTarget(null)} footer={<><Button onClick={() => setIgnoreTarget(null)} disabled={busy}>İptal</Button><Button variant="primary" onClick={ignore} disabled={busy}>{busy ? "Kaydediliyor..." : "Kararı Kaydet"}</Button></>}><label>Not (isteğe bağlı)<textarea value={ignoreNote} onChange={(event) => setIgnoreNote(event.target.value)} maxLength={500} placeholder="Örn. Paket boyutları farklı ürünler" /></label></Modal> : null}
  </section>;
}
