import { Badge } from "./Badge.jsx";
import { Button } from "./Button.jsx";
import { Icon } from "./Icon.jsx";
import { StatusBadge } from "./StatusBadge.jsx";

export function FileCard({ file, onDownload, onPreview, isPreviewing }) {
  const isReady = file.rawStatus === "ready" || file.status === "Hazır";
  return (
    <article className="file-card">
      <div className="file-icon">
        <Icon name="file" />
      </div>
      <div>
        <strong>{file.name}</strong>
        <small>
          {file.type} · {file.format || "PNG"} · {file.size}
        </small>
        {file.createdAt ? <small>Oluşturma: {file.createdAt}</small> : null}
      </div>
      {file.status ? <StatusBadge status={file.status} /> : <Badge tone="neutral">Taslak</Badge>}
      <div className="file-actions">
        <Button disabled={!isReady || !onPreview || isPreviewing} onClick={() => onPreview?.(file)}>
          {isPreviewing ? "Yükleniyor..." : "Önizle"}
        </Button>
        <Button disabled={!isReady || !onDownload} onClick={() => onDownload?.(file)}>
          İndir
        </Button>
        <Button>Kullanıcıya Gönder</Button>
      </div>
    </article>
  );
}
