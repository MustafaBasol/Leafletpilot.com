import { useEffect, useId } from "react";
import { Button } from "./Button.jsx";
import { Modal } from "./Modal.jsx";

export function ConfirmDialog({
  isOpen,
  title,
  description,
  confirmLabel = "Onayla",
  cancelLabel = "Vazgeç",
  onConfirm,
  onCancel,
  isLoading = false,
}) {
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!isOpen) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape" && !isLoading) {
        onCancel?.();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isLoading, isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <Modal
      title={title}
      description={description}
      onClose={isLoading ? undefined : onCancel}
      className="confirm-dialog-panel"
      role="alertdialog"
      labelledBy={titleId}
      describedBy={descriptionId}
      footer={
        <>
          <Button onClick={onCancel} disabled={isLoading}>
            {cancelLabel}
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={isLoading} autoFocus>
            {isLoading ? "İşleniyor..." : confirmLabel}
          </Button>
        </>
      }
    >
      <p id={descriptionId} className="confirm-dialog-copy">
        {description}
      </p>
    </Modal>
  );
}
