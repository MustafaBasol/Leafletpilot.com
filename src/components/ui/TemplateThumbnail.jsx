import { useEffect, useState } from "react";
import { fetchImageSource } from "../../api/client.js";

export function TemplateThumbnail({ templateId, thumbnailKey, marketId = "", name = "", realPreview = false }) {
  const [source, setSource] = useState(null);
  const imageUrl = templateId ? `/api/templates/${templateId}/${realPreview ? "preview-thumbnail" : "thumbnail"}` : "";
  const cacheKey = realPreview ? `${templateId}-renderer-preview` : thumbnailKey;
  useEffect(() => {
    let active = true; const controller = new AbortController(); let objectUrl = "";
    setSource(imageUrl ? { loading: true } : null);
    if (!imageUrl) return () => controller.abort();
    fetchImageSource(imageUrl, { signal: controller.signal, marketId, cacheKey }).then((next) => {
      if (!active) { if (next.revoke) URL.revokeObjectURL(next.src); return; }
      objectUrl = next.revoke ? next.src : ""; setSource(next);
    }).catch(() => active && setSource({ error: true }));
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [imageUrl, marketId, cacheKey]);
  if (source?.src && !source.error) return <span className="template-thumb template-thumb-image"><img src={source.src} alt={`${name} şablon önizlemesi`} loading="lazy" onError={() => setSource({ error: true })} /></span>;
  return <span className="template-thumb template-thumb-loading" aria-label={`${name} şablon önizlemesi hazırlanıyor`}>{source?.error ? "Önizleme şu an hazırlanamadı" : "Gerçek önizleme hazırlanıyor…"}</span>;
}