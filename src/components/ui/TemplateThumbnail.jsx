import { useEffect, useState } from "react";
import { fetchImageSource } from "../../api/client.js";

export function TemplateThumbnail({ templateId, thumbnailKey, marketId = "", previewTone = "classic", name = "", type = "" }) {
  const [source, setSource] = useState(null);
  const imageUrl = thumbnailKey && templateId ? `/api/templates/${templateId}/thumbnail` : "";

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let objectUrl = "";

    setSource(imageUrl ? { loading: true } : null);
    if (!imageUrl) return () => controller.abort();

    fetchImageSource(imageUrl, { signal: controller.signal, marketId, cacheKey: thumbnailKey })
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
  }, [imageUrl, marketId, thumbnailKey]);

  const showImage = source?.src && !source.error;

  if (showImage) {
    return (
      <span className="template-thumb template-thumb-image">
        <img src={source.src} alt="" onError={() => setSource({ error: true })} />
      </span>
    );
  }

  return (
    <span className={`template-thumb template-${previewTone}`}>
      <span>{name}</span>
      <strong>{type}</strong>
    </span>
  );
}
