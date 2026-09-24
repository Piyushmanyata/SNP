import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

function javascriptFiles(dir, found = []) {
  if (!existsSync(dir)) return found;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) javascriptFiles(path, found);
    else if (entry.name.endsWith(".js")) found.push(path);
  }
  return found;
}

const html = readFileSync("build/index.html", "utf8");
const assets = [...html.matchAll(/(?:src|href)="(\/static\/[^"?]+\.(?:js|css))"/g)].map((match) => match[1]);
assert(assets.some((asset) => asset.endsWith(".js")), "Missing JavaScript entry in production HTML");
assert(assets.some((asset) => asset.endsWith(".css")), "Missing stylesheet in production HTML");
for (const extension of ["js", "css"]) {
  const bytes = assets.filter((asset) => asset.endsWith(`.${extension}`))
    .reduce((total, asset) => total + gzipSync(readFileSync(resolve("build", `.${asset}`))).length, 0);
  const limit = extension === "js" ? 150_000 : 15_000;
  console.log(`Initial ${extension}: ${bytes} bytes gzip; limit ${limit}`);
  assert(bytes <= limit, `Initial ${extension} exceeds the gzip budget`);
}
const builtJs = javascriptFiles(resolve("build", "static"));
const initial = new Set(assets.filter((asset) => asset.endsWith(".js")).map((asset) => resolve("build", `.${asset}`)));
let allJs = 0;
for (const path of builtJs) {
  const bytes = gzipSync(readFileSync(path)).length;
  allJs += bytes;
  if (!initial.has(path)) {
    console.log(`Lazy ${path}: ${bytes} bytes gzip; limit 20000`);
    assert(bytes <= 20_000, `Lazy chunk exceeds the 20 KB gzip budget: ${path}`);
  }
}
console.log(`All JavaScript: ${allJs} bytes gzip; limit 200000`);
assert(allJs <= 200_000, "JavaScript exceeds the 200 KB gzip budget");
for (const file of ["zxing-worker.js", "zxing-wasm-reader.js", "wasm/zxing_reader.wasm"]) {
  const path = resolve("build", file);
  assert(existsSync(path) && statSync(path).size > 0, `Missing QR reader asset build/${file}`);
}
