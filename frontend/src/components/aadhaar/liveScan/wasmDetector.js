import logger from "../../../lib/logger";

export const WASM_DETECT_TIMEOUT_MS = 4000;

let worker = null;
let seq = 0;
const pending = new Map();

function workerUrl() {
  const base = process.env.PUBLIC_URL || "";
  return `${base}/zxing-worker.js`;
}

function settle(id, text) {
  const job = pending.get(id);
  if (!job) return;
  pending.delete(id);
  clearTimeout(job.timer);
  job.resolve(text);
}

function releaseWaiters(reason) {
  logger.warn("zxing worker error:", reason);
  if (worker) {
    worker.onmessage = null;
    worker.onerror = null;
    worker.terminate();
    worker = null;
  }
  for (const id of [...pending.keys()]) settle(id, null);
}

export function loadZxingWorker() {
  if (worker) return Promise.resolve();
  if (typeof Worker === "undefined") {
    return Promise.reject(new Error("Worker unavailable"));
  }
  worker = new Worker(workerUrl());
  worker.onmessage = (event) => {
    const { id, text } = event.data || {};
    settle(id, text || null);
  };
  worker.onerror = releaseWaiters;
  return Promise.resolve();
}

export function detectWasmImageData(imageData) {
  if (!imageData) return Promise.resolve(null);
  if (!worker) return loadZxingWorker().then(() => detectWasmImageData(imageData));
  const id = (seq += 1);
  return new Promise((resolve) => {
    const timer = setTimeout(() => settle(id, null), WASM_DETECT_TIMEOUT_MS);
    pending.set(id, { resolve, timer });
    worker.postMessage({ id, imageData });
  });
}
