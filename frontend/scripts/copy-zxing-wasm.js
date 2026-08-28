const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pkg = path.join(root, "node_modules", "zxing-wasm");
const wasmSrc = path.join(pkg, "dist", "reader", "zxing_reader.wasm");
const iifeSrc = path.join(pkg, "dist", "iife", "reader", "index.js");
const wasmDir = path.join(root, "public", "wasm");
const wasmDest = path.join(wasmDir, "zxing_reader.wasm");
const iifeDest = path.join(root, "public", "zxing-wasm-reader.js");

if (!fs.existsSync(wasmSrc) || !fs.existsSync(iifeSrc)) {
  console.warn("zxing-wasm binaries not found; skip copy");
  process.exit(0);
}
fs.mkdirSync(wasmDir, { recursive: true });
fs.copyFileSync(wasmSrc, wasmDest);
fs.copyFileSync(iifeSrc, iifeDest);
console.log("copied zxing-wasm reader assets to public/");
