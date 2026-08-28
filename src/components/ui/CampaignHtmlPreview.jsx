import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCampaignPreviewDimensions } from "./campaignPreviewSizing.js";

export function CampaignHtmlPreview({ html, title = "Kampanya önizlemesi", fallbackFormat = "pdf", className = "" }) {
  const viewportRef = useRef(null);
  const { width, height } = useMemo(
    () => getCampaignPreviewDimensions(html, fallbackFormat),
    [html, fallbackFormat],
  );
  const [fitScale, setFitScale] = useState(1);

  const measurePreview = useCallback(() => {
    const element = viewportRef.current;
    if (!element) return;
    const styles = getComputedStyle(element);
    const availableWidth = element.clientWidth - (parseFloat(styles.paddingLeft) || 0) - (parseFloat(styles.paddingRight) || 0);
    const availableHeight = element.clientHeight - (parseFloat(styles.paddingTop) || 0) - (parseFloat(styles.paddingBottom) || 0);
    if (availableWidth <= 0 || availableHeight <= 0) return;
    setFitScale(Math.min(availableWidth / width, availableHeight / height));
  }, [height, width]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return undefined;
    measurePreview();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measurePreview);
    observer?.observe(element);
    window.addEventListener("resize", measurePreview);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measurePreview);
    };
  }, [html, measurePreview]);

  return (
    <div
      ref={viewportRef}
      className={`campaign-preview-viewport campaign-preview-html-viewport ${className}`.trim()}
      style={{ aspectRatio: `${width} / ${height}` }}
    >
      <div className="campaign-preview-page-box" style={{ width: width * fitScale, height: height * fitScale }}>
        <iframe
          className="campaign-preview-iframe"
          style={{ width, height, transform: `scale(${fitScale})` }}
          title={title}
          srcDoc={html}
          sandbox=""
          scrolling="no"
        />
      </div>
    </div>
  );
}
