/**
 * Render the staged brand-logo SVGs (mocks/data/_logo-src/*.svg on the demo
 * box) into 512x512 PNGs for the DAM S3 mock.
 *
 * Runs on the WORKSTATION, not the box: librsvg only draws <text> when
 * fontconfig finds a font, and neither the mocks container nor the box has
 * fonts installed. Uses sharp from analog-elk-front-end's node_modules:
 *
 *   cd ~/Desktop/DevProd/analog-elk-front-end && \
 *     NODE_PATH=$PWD/node_modules node \
 *     ~/Desktop/DevProd/elk-os/provision/seed-full/render-logo-pngs.js \
 *     <svg-dir> <png-out-dir>
 *
 * Then scp the PNGs to the box at
 *   ~/elk-os/mocks/data/agency-directus-assets/dam/<org-slug>/<name>.png
 * (see patch-dam-logo-keys.py for the key mapping).
 */
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const [svgDir, outDir] = process.argv.slice(2);
if (!svgDir || !outDir) {
  console.error("usage: render-logo-pngs.js <svg-dir> <png-out-dir>");
  process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const svgs = fs.readdirSync(svgDir).filter((f) => f.endsWith(".svg"));
  for (const name of svgs) {
    const out = path.join(outDir, name.replace(/\.svg$/, ".png"));
    if (fs.existsSync(out) && fs.statSync(out).size > 0) {
      console.log(`skip ${out} (exists)`);
      continue;
    }
    const buf = fs.readFileSync(path.join(svgDir, name));
    // density 144 => 256px viewBox rasterizes at 512px before resize.
    const png = await sharp(buf, { density: 144 })
      .resize(512, 512)
      .png()
      .toBuffer();
    fs.writeFileSync(out, png);
    console.log(`wrote ${out} (${png.length} bytes)`);
  }
})();
