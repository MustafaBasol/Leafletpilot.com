import { readFile } from "node:fs/promises";

const distDir = new URL("../dist/", import.meta.url);

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const ICO_SIGNATURE = Buffer.from([0x00, 0x00, 0x01, 0x00]);

const pngCheck = (buffer) => buffer.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE);
const icoCheck = (buffer) => buffer.subarray(0, ICO_SIGNATURE.length).equals(ICO_SIGNATURE);
const manifestCheck = (buffer) => {
  const parsed = JSON.parse(buffer.toString("utf8"));
  return typeof parsed === "object" && parsed !== null && Array.isArray(parsed.icons);
};

const requiredAssets = [
  { path: "brand/wordmark-dark.png", check: pngCheck, kind: "PNG" },
  { path: "brand/wordmark-light.png", check: pngCheck, kind: "PNG" },
  { path: "brand/mark-dark.png", check: pngCheck, kind: "PNG" },
  { path: "brand/mark-white.png", check: pngCheck, kind: "PNG" },
  { path: "brand/icon-32.png", check: pngCheck, kind: "PNG" },
  { path: "brand/icon-180.png", check: pngCheck, kind: "PNG" },
  { path: "brand/icon-192.png", check: pngCheck, kind: "PNG" },
  { path: "brand/icon-512.png", check: pngCheck, kind: "PNG" },
  { path: "brand/favicon.ico", check: icoCheck, kind: "ICO" },
  { path: "site.webmanifest", check: manifestCheck, kind: "manifest" },
];

const indexHtml = await readFile(new URL("index.html", distDir));

const failures = [];

for (const asset of requiredAssets) {
  const url = new URL(asset.path, distDir);
  let buffer;
  try {
    buffer = await readFile(url);
  } catch {
    failures.push(`${asset.path}: missing from dist/`);
    continue;
  }

  if (buffer.equals(indexHtml)) {
    failures.push(`${asset.path}: body is identical to dist/index.html (SPA fallback served instead of the asset)`);
    continue;
  }

  let signatureOk = false;
  try {
    signatureOk = asset.check(buffer);
  } catch (error) {
    failures.push(`${asset.path}: failed to validate as ${asset.kind} (${error.message})`);
    continue;
  }

  if (!signatureOk) {
    failures.push(`${asset.path}: does not look like a valid ${asset.kind} file`);
    continue;
  }

  console.log(`OK ${asset.path} (${asset.kind}, ${buffer.length} bytes)`);
}

if (failures.length > 0) {
  console.error("Brand asset verification failed:");
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exitCode = 1;
} else {
  console.log(`All ${requiredAssets.length} brand assets verified in dist/.`);
}
