import { Button } from "./Button.jsx";
import { Icon } from "./Icon.jsx";

export function Modal({
  title,
  description,
  children,
  footer,
  onClose,
  className = "",
  role = "dialog",
  labelledBy = "modal-title",
  describedBy,
}) {
  if (!title) return null;

  const panelClassName = `modal-panel ${className}`.trim();

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className={panelClassName}
        role={role}
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
      >
        <div className="modal-header">
          <div>
            <h2 id={labelledBy}>{title}</h2>
            {description ? <p>{description}</p> : null}
          </div>
          <Button className="icon-button" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </Button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </section>
    </div>
  );
}
