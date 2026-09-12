import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

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
