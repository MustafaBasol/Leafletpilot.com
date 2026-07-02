import { useState } from "react";
import { outputFormats, sampleBrochurePages } from "../../data/mockData.js";
import { Badge } from "./Badge.jsx";
import { Button } from "./Button.jsx";

export function PreviewFrame({ title = "Broşür Önizleme", status = "Taslak", products, formats = outputFormats }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [selectedFormat, setSelectedFormat] = useState(formats[0]?.label || "A4 PDF");
  const pages = products ? [{ page: 1, title, products }] : sampleBrochurePages;
  const page = pages[pageIndex] || pages[0];

  return (
    <div className="preview-frame">
      <div className="preview-toolbar">
        <div>
          <strong>{title}</strong>
          <small>
            {selectedFormat} · Sayfa {page.page}/{pages.length} · %{zoom}
          </small>
        </div>
        <Badge tone="primary">{status}</Badge>
      </div>
      <div className="preview-controls">
        <div className="segmented-controls">
          {formats.map((format) => (
            <button
              className={selectedFormat === format.label ? "is-selected" : ""}
              key={format.id || format.label}
              type="button"
              onClick={() => setSelectedFormat(format.label)}
            >
              {format.label}
            </button>
          ))}
        </div>
        <div className="preview-control-actions">
          <Button onClick={() => setPageIndex((current) => Math.max(current - 1, 0))} disabled={pageIndex === 0}>
            Önceki
          </Button>
          <Button onClick={() => setPageIndex((current) => Math.min(current + 1, pages.length - 1))} disabled={pageIndex === pages.length - 1}>
            Sonraki
          </Button>
          <Button onClick={() => setZoom((current) => Math.max(current - 10, 80))}>-</Button>
          <Button onClick={() => setZoom((current) => Math.min(current + 10, 130))}>+</Button>
        </div>
      </div>
      <div className="brochure-preview-shell">
        <div className="brochure-preview" style={{ transform: `scale(${zoom / 100})` }}>
          <div className="brochure-top">
            <span>Anadolu Market</span>
            <strong>{page.title}</strong>
          </div>
          <div className="brochure-grid">
            {page.products.slice(0, 6).map((item) => (
              <div className="brochure-item" key={item.id || item.name}>
                <span>{item.shortName || item.name}</span>
                <strong>{item.price}</strong>
              </div>
            ))}
          </div>
          <p className="brochure-footer">Kampanyalar stoklarla sınırlıdır. Fiyatlar belirtilen tarih aralığında geçerlidir.</p>
        </div>
      </div>
    </div>
  );
}
