import { Button } from "./Button.jsx";
import { Icon } from "./Icon.jsx";

export function Modal({ title, description, children, footer, onClose }) {
  if (!title) return null;

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-header">
          <div>
            <h2 id="modal-title">{title}</h2>
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
