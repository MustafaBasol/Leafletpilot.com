export function ProductThumbnail({ label, hasImage = true }) {
  return (
    <span className={`product-thumb ${hasImage ? "" : "is-empty"}`.trim()}>
      {hasImage ? label.slice(0, 2).toUpperCase() : "Yok"}
    </span>
  );
}
