"""Database-independent browser acceptance gate for canonical A4 flyers."""
from __future__ import annotations
import argparse, json, shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.services.preview_renderer import render_render_payload_html
from app.services.rendering import render_html_to_pdf_sync, render_html_to_png_sync

def fixture_payload(count: int, names: list[str]) -> dict:
    def product_key(i: int) -> str: return f"acceptance/products/{names[i % len(names)]}"
    items = [{"id": str(uuid4()), "name": ("Extra Long Supermarket Product Name " * 3) if i == 0 else f"Product {i+1}", "brand": ("Very Long Demonstration Brand " * 2) if i == 1 else "Demo Brand", "image_key": product_key(i), "price": "999999.99" if i == 2 else f"{i+1}.99", "old_price": f"{i+3}.99", "currency": "EUR", "package_size": "500g", "package_type": "family pack", "quantity_label": "2 units", "badge": "SPECIAL", "stock_note": "While stocks last"} for i in range(count)]
    return {"contract_version": 2, "template_slug": f"promo-{count}", "template_name": "Premium Market", "title": "Weekly supermarket offers", "market_name": "Demo Market", "header": {"market_logo": {"storage_key": "acceptance/branding/market-logo.svg"}, "header_logos": [{"storage_key": "acceptance/branding/fresh.svg"}, {"storage_key": "acceptance/branding/value.svg"}], "payment_icons": [{"storage_key": "acceptance/branding/card.svg"}, {"storage_key": "acceptance/branding/cash.svg"}], "promo_title": "Weekly supermarket offers", "validity_text": "01-07 July 2026", "stock_message": "While stocks last", "footer_note": "Stoklarla sınırlıdır."}, "items": items, "template_config": {"show_old_price": True}}

def write_branding_assets(root: Path) -> None:
    branding = root / "branding"; branding.mkdir(parents=True, exist_ok=True)
    assets = {"market-logo.svg": '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="64"><rect width="220" height="64" rx="12" fill="#c1121f"/><text x="110" y="41" text-anchor="middle" font-family="Arial" font-size="28" font-weight="700" fill="white">DEMO MART</text></svg>', "fresh.svg": '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="44"><rect width="100" height="44" rx="8" fill="#2a9d8f"/><text x="50" y="29" text-anchor="middle" font-family="Arial" font-size="14" font-weight="700" fill="white">FRESH</text></svg>', "value.svg": '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="44"><rect width="100" height="44" rx="8" fill="#f4a261"/><text x="50" y="29" text-anchor="middle" font-family="Arial" font-size="14" font-weight="700" fill="#16202a">VALUE</text></svg>', "card.svg": '<svg xmlns="http://www.w3.org/2000/svg" width="72" height="40"><rect x="2" y="6" width="68" height="28" rx="4" fill="#264653"/><rect x="10" y="13" width="22" height="5" fill="#e9c46a"/><circle cx="56" cy="20" r="7" fill="#e76f51"/></svg>', "cash.svg": '<svg xmlns="http://www.w3.org/2000/svg" width="72" height="40"><rect x="2" y="6" width="68" height="28" rx="4" fill="#457b9d"/><circle cx="36" cy="20" r="9" fill="#a8dadc"/><text x="36" y="24" text-anchor="middle" font-family="Arial" font-size="12" font-weight="700" fill="#1d3557">€</text></svg>'}
    for name, content in assets.items(): (branding / name).write_text(content, encoding="utf-8")

def png_dimensions(path: Path) -> list[int]:
    data = path.read_bytes(); return [int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")]

def pdf_metadata(path: Path) -> dict:
    from pypdf import PdfReader
    pages = PdfReader(str(path)).pages; box = pages[0].mediabox
    return {"path": str(path), "pages": len(pages), "width_points": round(float(box.width), 3), "height_points": round(float(box.height), 3), "portrait_a4": len(pages) == 1 and abs(float(box.width) - 595.276) < 2 and abs(float(box.height) - 841.89) < 2, "file_size": path.stat().st_size}

def browser_checks(html: str, count: int) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754}, device_scale_factor=1); page.set_content(html, wait_until="networkidle")
            return page.evaluate("""expected => { const c=document.querySelector('.preview-document'),g=document.querySelector('.product-grid'),cards=[...document.querySelectorAll('.product-card')],tol=2,cr=c.getBoundingClientRect(),gr=g.getBoundingClientRect(),rs=cards.map(e=>e.getBoundingClientRect()),imgs=[...document.images],rows=expected===4?2:expected===9?3:4,clamps=[],violations=[]; const bounded=[...document.querySelectorAll('[data-clamp-enabled],.price')]; for(const e of bounded){const s=getComputedStyle(e),r=e.getBoundingClientRect(),p=e.closest('.product-card,.hero,.footer')?.getBoundingClientRect(),horizontal=e.scrollWidth>e.clientWidth+1,marker=e.hasAttribute('data-clamp-enabled'),lines=Number(e.dataset.clampLines||0),line=parseFloat(s.lineHeight)||parseFloat(s.fontSize)*1.2; if(marker){const valid=s.webkitLineClamp!=='none'&&lines>0&&e.clientHeight<=lines*line+2&&!horizontal&&(!p||(r.left>=p.left-1&&r.right<=p.right+1&&r.top>=p.top-1&&r.bottom<=p.bottom+1)); clamps.push({element:e.className||e.tagName,lines,visible_height:r.height,allowed_height:lines*line,horizontal,valid}); if(!valid) violations.push(e.className||e.tagName); } else if(horizontal||e.scrollHeight>e.clientHeight+1) violations.push(e.className||e.tagName); } return {cards:cards.length,real_images:imgs.filter(e=>e.classList.contains('product-image')).length,images_decoded:imgs.every(e=>e.complete&&e.naturalWidth>0&&e.naturalHeight>0),all_real_images_nonzero:imgs.filter(e=>e.classList.contains('product-image')).every(e=>e.naturalWidth>0&&e.naturalHeight>0),canvas_bounds:cr.width===1240&&cr.height===1754,grid_bounds:gr.left>=cr.left&&gr.right<=cr.right&&gr.top>=gr.top&&gr.bottom<=cr.bottom,cards_in_grid:rs.every(r=>r.left>=gr.left-tol&&r.right<=gr.right+tol&&r.top>=gr.top-tol&&r.bottom<=gr.bottom+tol),cards_in_canvas:rs.every(r=>r.left>=cr.left-tol&&r.right<=cr.right+tol&&r.top>=cr.top-tol&&r.bottom<=cr.bottom+tol),no_overflow:violations.length===0,overflow_elements:violations,clamp_records:clamps,no_text_fit_failures:document.querySelectorAll('[data-text-fit-failed]').length===0,title_present:(document.querySelector('h1')?.textContent||'').trim().length>0,validity_present:(document.querySelector('.meta')?.textContent||'').includes('01-07 July 2026'),market_logo:document.querySelectorAll('.market-logo').length===1,additional_logos:document.querySelectorAll('.header-logo').length===2,payment_icons:document.querySelectorAll('.payment-icon').length===2,explicit_rows:getComputedStyle(g).gridTemplateRows.split(' ').length===rows,no_implicit_extra_rows:getComputedStyle(g).gridTemplateRows.split(' ').length===rows}; }""", count)
        finally: browser.close()

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, required=True); args = parser.parse_args(); output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    assets = sorted((Path(__file__).resolve().parents[1] / "app/assets/demo/products").glob("*.png"))
    if len(assets) < 5: raise SystemExit("acceptance requires at least five local PNG fixtures")
    root = settings.local_storage_path / "acceptance"; (root / "products").mkdir(parents=True, exist_ok=True)
    for asset in assets: shutil.copyfile(asset, root / "products" / asset.name)
    write_branding_assets(root); names = [asset.name for asset in assets]; reports = []
    for count in (4, 9, 16):
        html = render_render_payload_html(fixture_payload(count, names), generated_at=datetime.now(UTC)); png = output / f"promo-{count}.png"; pdf = output / f"promo-{count}.pdf"; render_html_to_png_sync(html, png); render_html_to_pdf_sync(html, pdf); checks = browser_checks(html, count); report = {"layout": f"promo-{count}", "png": str(png), "pdf": pdf_metadata(pdf), "png_dimensions": png_dimensions(png), **checks}; required = [report["png_dimensions"] == [2480,3508], report["pdf"]["pages"] == 1, report["pdf"]["portrait_a4"], report["cards"] == count, report["real_images"] == count, report["images_decoded"], report["all_real_images_nonzero"], report["canvas_bounds"], report["grid_bounds"], report["cards_in_grid"], report["cards_in_canvas"], report["no_overflow"], report["no_text_fit_failures"], report["title_present"], report["validity_present"], report["market_logo"], report["additional_logos"], report["payment_icons"], report["explicit_rows"], report["no_implicit_extra_rows"]]
        if not all(required): raise SystemExit(json.dumps(report, indent=2))
        reports.append(report)
    missing = render_render_payload_html({"contract_version": 2, "template_slug": "promo-4", "items": [{"name": "Missing image"}]}, generated_at=datetime.now(UTC))
    if "image-placeholder" not in missing or 'class="product-image"' in missing: raise SystemExit("missing-image fallback acceptance failed")
    summary = {"generated_at": datetime.now(UTC).isoformat(), "layouts": reports, "missing_image_fallback": True}; (output / "acceptance-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8"); print(json.dumps(summary, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
