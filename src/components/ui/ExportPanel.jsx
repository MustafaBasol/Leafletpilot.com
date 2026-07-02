import { Button } from "./Button.jsx";
import { FileCard } from "./FileCard.jsx";

export function ExportPanel({ files, onAction }) {
  return (
    <div className="export-panel">
      <div className="export-panel-actions">
        <Button onClick={() => onAction?.("Önizleme yeniden oluşturuldu.")}>Önizlemeyi Yeniden Oluştur</Button>
        <Button variant="primary" onClick={() => onAction?.("Final dosyaları üretim için hazırlandı.")}>
          Final Dosyaları Üret
        </Button>
      </div>
      <div className="stack-list">
        {files.map((file) => (
          <FileCard file={file} key={file.name} />
        ))}
      </div>
    </div>
  );
}
