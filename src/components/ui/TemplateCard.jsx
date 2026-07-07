import { Badge } from "./Badge.jsx";
import { Button } from "./Button.jsx";
import { StatusBadge } from "./StatusBadge.jsx";

export function TemplateCard({ template, onMakeDefault, onDuplicate, onToggle, canManage = true }) {
  return (
    <article className="template-management-card">
      <a className={`template-thumb template-${template.previewTone}`} href={`#/templates/${template.id}`}>
        <span>{template.name}</span>
        <strong>{template.type}</strong>
      </a>
      <div className="template-card-body">
        <div className="template-title-row">
          <div>
            <h3>{template.name}</h3>
            <small>{template.recommendation}</small>
          </div>
          <StatusBadge status={template.status} />
        </div>
        <dl className="compact-definition-list">
          <div>
            <dt>Tip</dt>
            <dd>{template.type}</dd>
          </div>
          <div>
            <dt>Kapasite</dt>
            <dd>{template.capacity}</dd>
          </div>
        </dl>
        <div className="file-badges">
          {template.formats.map((format) => (
            <span key={format}>{format}</span>
          ))}
        </div>
        <div className="template-card-footer">
          {template.isDefault ? <Badge tone="primary">Varsayılan</Badge> : <span />}
          <div className="table-actions">
            <Button href={`#/templates/${template.id}`}>Önizle</Button>
            {canManage ? (
              <>
                <Button onClick={() => onMakeDefault(template.id)} disabled={template.isDefault}>
                  Varsayılan Yap
                </Button>
                <Button onClick={() => onDuplicate(template.id)}>Kopyala</Button>
                <Button>Düzenle</Button>
                <Button onClick={() => onToggle(template.id)}>{template.status === "Aktif" ? "Pasifleştir" : "Aktifleştir"}</Button>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}
