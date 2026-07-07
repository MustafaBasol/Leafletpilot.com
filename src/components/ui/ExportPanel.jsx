import { Button } from "./Button.jsx";
import { FileCard } from "./FileCard.jsx";

export function ExportPanel({ files, onAction, onDownload, isGenerating }) {
  return (
    <div className="export-panel">
      {onAction ? (
        <div className="export-panel-actions">
          <Button disabled={isGenerating} onClick={() => onAction("PDF dosyası üretildi.", ["pdf"])}>
            PDF Üret
          </Button>
          <Button disabled={isGenerating} onClick={() => onAction("PNG dosyası üretildi.", ["png"])}>
            PNG Üret
          </Button>
          <Button disabled={isGenerating} variant="primary" onClick={() => onAction("PDF ve PNG dosyaları üretildi.", ["pdf", "png"])}>
            Dosya Üret
          </Button>
        </div>
      ) : null}
      <div className="stack-list">
        {files.length === 0 ? <p className="catalog-empty">Henüz üretilmiş dosya yok.</p> : null}
        {files.map((file) => (
          <FileCard file={file} key={file.id || file.name} onDownload={onDownload} />
        ))}
      </div>
    </div>
  );
}
