import { useState } from "react";
import { products } from "../../data/mockData.js";
import { Button } from "./Button.jsx";
import { ConfirmDialog } from "./ConfirmDialog.jsx";
import { Modal } from "./Modal.jsx";
import { ProductThumbnail } from "./ProductThumbnail.jsx";

export function MissingProductModal({ product, onClose, onResolve }) {
  const [selectedId, setSelectedId] = useState(products[0].id);
  const [isRemoveConfirmOpen, setRemoveConfirmOpen] = useState(false);

  if (!product) return null;

  const suggestions = products.slice(0, 4);
  const productName = product.incoming || product.incomingName;

  return (
    <>
      <Modal
        title="Eksik Ürünü Eşleştir"
        description={`${productName} için katalog önerilerinden birini seçin veya alternatif aksiyon kullanın.`}
        onClose={onClose}
        footer={
          <>
            <Button onClick={onClose}>Vazgeç</Button>
            <Button variant="primary" onClick={() => onResolve("Eşleşti")}>
              Eşleştir
            </Button>
          </>
        }
      >
        <div className="suggestion-list">
          {suggestions.map((suggestion) => (
            <button
              className={`suggestion-row ${selectedId === suggestion.id ? "is-selected" : ""}`.trim()}
              type="button"
              onClick={() => setSelectedId(suggestion.id)}
              key={suggestion.id}
            >
              <ProductThumbnail label={suggestion.name} hasImage={suggestion.imageStatus !== "Görsel yok"} />
              <span>
                <strong>{suggestion.name}</strong>
                <small>
                  {suggestion.brand} · {suggestion.category} · {suggestion.barcode}
                </small>
              </span>
            </button>
          ))}
        </div>
        <div className="modal-action-grid">
          <Button onClick={() => onResolve("Yeni ürün gerekli")}>Yeni ürün olarak ekle</Button>
          <Button onClick={() => onResolve("Görselsiz devam")}>Görselsiz devam et</Button>
          <Button variant="danger" onClick={() => setRemoveConfirmOpen(true)}>
            Kampanyadan çıkar
          </Button>
        </div>
      </Modal>
      <ConfirmDialog
        isOpen={isRemoveConfirmOpen}
        title="Ürünü kampanyadan çıkar"
        description={`${productName} kampanya ürün listesinden çıkarılacak. Devam edilsin mi?`}
        confirmLabel="Kampanyadan çıkar"
        onCancel={() => setRemoveConfirmOpen(false)}
        onConfirm={() => {
          setRemoveConfirmOpen(false);
          onResolve("Kampanyadan çıkarıldı");
        }}
      />
    </>
  );
}
