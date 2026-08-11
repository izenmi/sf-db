// One-off asset generator: renders public/favicon.ico and public/apple-touch-icon.png from the
// same design as public/favicon.svg. Not part of the build pipeline — re-run manually
// (`node scripts/generate-icons.mjs`) if the mark or the accent colour changes.
//
// Why render in a browser instead of converting the SVG directly: the mark uses
// "M PLUS Rounded 1c", which isn't installed in this container. A headless Chromium page can
// pull it from Google Fonts and wait for it to load, so the glyph shape matches the site's
// display font instead of falling back to whatever sans-serif ImageMagick happens to find.
//
// The four corners stay opaque black. The sister sites' icons use a rounded rect (rx=16), which
// leaves the corners transparent — and a transparent corner gets composited onto white by some
// browsers' tab strips and by ICO consumers that ignore the alpha channel. Every surface here is
// filled edge to edge and every PNG is flattened onto black before packing, so there is no alpha
// left to misinterpret.
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "playwright";

const rootDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const publicDir = path.join(rootDir, "public");

const BG = "#000000";
const FG = "#6e8bff";
const GLYPH = "S";

/** ICO sizes browsers actually pick from. Stopping at 64 keeps the file ~10KB; adding a 256px
 *  frame pushed it past 100KB for a mark that is never displayed that large. */
const ICO_SIZES = [16, 32, 48, 64];
const APPLE_TOUCH_SIZE = 180;

function pageHtml(size) {
  // Geometry is scaled from the 64px viewBox in public/favicon.svg so the raster icons and the
  // SVG stay visually identical — keep the two in sync when either changes.
  const fontSize = (46 / 64) * size;
  const centerY = (33 / 64) * size;
  const centerX = size / 2;
  return `<!doctype html>
<html><head><meta charset="UTF-8" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=M+PLUS+Rounded+1c:wght@800&display=swap" rel="stylesheet" />
<style>
  * { margin: 0; padding: 0; }
  html, body { width: ${size}px; height: ${size}px; background: ${BG}; overflow: hidden; }
  svg { display: block; }
</style></head>
<body>
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" fill="${BG}" />
  <text x="${centerX}" y="${centerY}"
    font-family="'M PLUS Rounded 1c', sans-serif" font-weight="800"
    font-size="${fontSize}" fill="${FG}" text-anchor="middle"
    dominant-baseline="central">${GLYPH}</text>
</svg>
</body></html>`;
}

const browser = await chromium.launch();
const workDir = mkdtempSync(path.join(tmpdir(), "sf-icons-"));

try {
  const pngPaths = [];
  for (const size of [...ICO_SIZES, APPLE_TOUCH_SIZE]) {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    await page.setContent(pageHtml(size), { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    const out =
      size === APPLE_TOUCH_SIZE
        ? path.join(publicDir, "apple-touch-icon.png")
        : path.join(workDir, `icon-${size}.png`);
    // omitBackground defaults to false, so the page's black background is baked in — the PNG has
    // no transparent pixels at all.
    await page.screenshot({ path: out, omitBackground: false });
    await page.close();
    if (size !== APPLE_TOUCH_SIZE) pngPaths.push(out);
    console.log(`generate-icons: rendered ${size}x${size}`);
  }

  // -background black -alpha remove -alpha off: flatten before packing, so no ICO consumer sees
  // an alpha channel it might composite onto white.
  execFileSync("convert", [
    ...pngPaths,
    "-background",
    "black",
    "-alpha",
    "remove",
    "-alpha",
    "off",
    path.join(publicDir, "favicon.ico"),
  ]);
  console.log(`generate-icons: wrote public/favicon.ico (${ICO_SIZES.join(", ")}px)`);
  console.log("generate-icons: wrote public/apple-touch-icon.png (180px)");
} finally {
  await browser.close();
  rmSync(workDir, { recursive: true, force: true });
}
