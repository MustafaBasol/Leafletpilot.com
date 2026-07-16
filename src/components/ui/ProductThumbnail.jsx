import { useEffect, useState } from "react";
import { fetchImageSource } from "../../api/client.js";

const sizeClasses = {
  sm: "product-thumb--sm",
  md: "product-thumb--md",
  lg: "product-thumb--lg",
};

export function ProductThumbnail({ label, hasImage = true, imageUrl = "", marketId = "", refreshKey = "", size = "sm" }) {
  const [source, setSource] = useState(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let objectUrl = "";

    setSource(imageUrl ? { loading: true } : null);
    if (!imageUrl) return () => controller.abort();

    fetchImageSource(imageUrl, { signal: controller.signal, marketId })
      .then((nextSource) => {
        if (!active) {
          if (nextSource.revoke) URL.revokeObjectURL(nextSource.src);
          return;
        }
        objectUrl = nextSource.revoke ? nextSource.src : "";
        setSource(nextSource);
      })
      .catch(() => {
        if (active) setSource({ error: true });
      });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageUrl, marketId, refreshKey]);

  const showImage = source?.src && !source.error;
  const sizeClass = sizeClasses[size] || sizeClasses.sm;

  return (
    <span className={`product-thumb ${sizeClass} ${hasImage ? "" : "is-empty"}`.trim()}>
      {showImage ? <img src={source.src} alt="" aria-hidden="true" onError={() => setSource({ error: true })} /> : source?.loading ? null : source?.error || !hasImage ? "Yok" : label.slice(0, 2).toUpperCase()}
    </span>
  );
}
