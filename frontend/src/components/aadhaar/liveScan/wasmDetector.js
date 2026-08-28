let worker = null;
let seq = 0;
const pending = new Map();

function workerUrl() {
  const base = process.env.PUBLIC_URL || "";
  return `${base}/zxing-worker.js`;
}

export function loadZxingWorker() {
  if (worker) return Promise.resolve();
  if (typeof Worker === "undefined") {
    return Promise.reject(new Error("Worker unavailable"));
  }
  worker = new Worker(workerUrl());
  worker.onmessage = (event) => {
    const { id, text } = event.data || {};
    const job = pending.get(id);
    if (!job) return;
    pending.delete(id);
    job.resolve(text || null);
  };
  worker.onerror = (err) => {
    console.warn("zxing worker error:", err);
  };
  return Promise.resolve();
}

export function detectWasmImageData(imageData) {
  if (!worker || !imageData) return Promise.resolve(null);
  const id = (seq += 1);
  return new Promise((resolve) => {
    pending.set(id, { resolve });
    worker.postMessage({ id, imageData });
  });
}
