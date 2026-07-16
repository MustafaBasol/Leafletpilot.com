import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const componentSource = await readFile(new URL("./ProductThumbnail.jsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../../styles.css", import.meta.url), "utf8");

test("ProductThumbnail exposes explicit reusable size variants", () => {
  assert.match(componentSource, /size = "sm"/);
  assert.match(componentSource, /product-thumb--sm/);
  assert.match(componentSource, /product-thumb--md/);
  assert.match(componentSource, /product-thumb--lg/);
  assert.match(componentSource, /refreshKey = ""/);
  assert.match(componentSource, /\[imageUrl, marketId, refreshKey\]/);
  assert.match(componentSource, /<span className=\{`product-thumb/);
});

test("thumbnail variants constrain images and preserve fallback bounds", () => {
  assert.match(styles, /\.product-thumb--sm\s*\{[^}]*width:\s*56px;[^}]*height:\s*56px;/s);
  assert.match(styles, /\.product-thumb--md\s*\{[^}]*width:\s*72px;[^}]*height:\s*72px;/s);
  assert.match(styles, /\.product-thumb--lg\s*\{[^}]*width:\s*min\(320px, 100%\);[^}]*height:\s*240px;/s);
  assert.match(styles, /\.product-thumb\s*\{[^}]*place-items:\s*center;/s);
  assert.match(styles, /\.product-thumb--lg\s*\{[^}]*align-items:\s*center;[^}]*justify-content:\s*center;/s);
  assert.match(styles, /\.product-thumb\s*\{[^}]*overflow:\s*hidden;/s);
  assert.match(styles, /\.product-thumb img\s*\{[^}]*object-fit:\s*contain;/s);
  assert.match(styles, /\.product-thumb img\s*\{[^}]*object-position:\s*center;/s);
  assert.match(styles, /\.product-thumb--lg\s*\{[^}]*overflow:\s*visible;/s);
  assert.match(componentSource, /showImage \? <img[\s\S]*onError/);
  assert.match(componentSource, /source\?\.error \|\| !hasImage/);
  assert.match(componentSource, /"Yok"/);
});

test("image replacement refreshes the same URL and cleans blob URLs", () => {
  assert.match(componentSource, /fetchImageSource\(imageUrl, \{ signal: controller\.signal, marketId \}\)/);
  assert.match(componentSource, /URL\.revokeObjectURL\(nextSource\.src\)/);
  assert.match(componentSource, /if \(objectUrl\) URL\.revokeObjectURL\(objectUrl\)/);
});
