export const WASM_LOAD_TIMEOUT_MS = 45000;
export const WASM_DETECT_TIMEOUT_MS = 4000;
export const WASM_PHOTO_TIMEOUT_MS = 20000;

let worker = null;
let ready = null;
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

function reset() {
  if (worker) {
    worker.onmessage = null;
    worker.onerror = null;
    worker.terminate();
  }
  worker = null;
  ready = null;
  for (const id of [...pending.keys()]) settle(id, null);
}

export function loadZxingWorker() {
  if (ready) return ready;
  if (typeof Worker === "undefined") return Promise.reject(new Error("Worker unavailable"));
  const current = new Worker(workerUrl());
  worker = current;
  ready = new Promise((resolve, reject) => {
    const fail = () => {
      clearTimeout(timer);
      if (worker === current) reset();
      reject(new Error("QR reader unavailable"));
    };
    const timer = setTimeout(fail, WASM_LOAD_TIMEOUT_MS);
    current.onmessage = (event) => {
      const data = event.data || {};
      if ("ready" in data) {
        if (!data.ready) return fail();
        clearTimeout(timer);
        resolve();
        return;
      }
      settle(data.id, data.text || null);
    };
    current.onerror = fail;
  });
  ready.catch(() => {});
  return ready;
}

function detect(image, timeoutMs, message, transfer) {
  if (!image) return Promise.resolve(null);
  return loadZxingWorker().then(() => new Promise((resolve) => {
    const current = worker;
    const id = (seq += 1);
    const timer = setTimeout(() => {
      if (worker === current) reset();
    }, timeoutMs);
    pending.set(id, { resolve, timer });
    try {
      current.postMessage({ id, image, ...message }, transfer);
    } catch {
      settle(id, null);
    }
  }));
}

export function detectWasmImageData(imageData) {
  return detect(imageData, WASM_DETECT_TIMEOUT_MS, {}, imageData ? [imageData.data.buffer] : []);
}

export function detectWasmPhoto(file) {
  return detect(file, WASM_PHOTO_TIMEOUT_MS, { photo: true }, []);
}
