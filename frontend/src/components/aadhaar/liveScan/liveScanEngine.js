export const NATIVE_MISS_LIMIT = 8;
export const PROMOTE_AFTER_MS = 1250;
export const PAYLOAD_IGNORE_MS = 1500;
export const FALLBACK_HINT_MS = 2500;
export const SCAN_STALL_MS = 20000;
export const MAX_DETECT_INTERVAL_MS = 125;

export const ZXING_READER_OPTIONS = {
  formats: ["QRCode"],
  tryHarder: true,
  tryRotate: true,
  tryInvert: false,
  tryDownscale: false,
  maxNumberOfSymbols: 1,
};

export function createLiveScanEngine({
  hasNativeDetector,
  now = () => Date.now(),
  detectNative,
  detectWasm,
  loadWasm,
  decode,
  onLock,
  onFailure,
  onHintFallbacks,
  onScanStall,
} = {}) {
  let started = false;
  let decoder = "native";
  let wasmLoaded = false;
  let wasmLoadPromise = null;
  let inFlight = false;
  let nextRegion = "roi";
  let sessionStart = 0;
  let nativeMisses = 0;
  let frozen = false;
  let softHold = false;
  let fallbackHinted = false;
  let detects = 0;
  let stalled = false;
  const ignoredUntil = new Map();

  function getState() {
    return {
      decoder,
      wasmLoaded,
      frozen,
      softHold,
      inFlight,
      nativeMisses,
      nextRegion,
      started,
      detects,
      stalled,
    };
  }

  function ensureWasm() {
    if (wasmLoaded) return Promise.resolve();
    if (!wasmLoadPromise) {
      wasmLoadPromise = Promise.resolve()
        .then(() => loadWasm())
        .then(() => {
          wasmLoaded = true;
        });
    }
    return wasmLoadPromise;
  }

  function shouldPromote() {
    if (decoder !== "native") return false;
    return nativeMisses >= NATIVE_MISS_LIMIT || now() - sessionStart >= PROMOTE_AFTER_MS;
  }

  async function promote() {
    if (decoder === "wasm") return;
    decoder = "wasm";
    await ensureWasm();
  }

  function hintFallback() {
    if (fallbackHinted || frozen) return;
    if (now() - sessionStart >= FALLBACK_HINT_MS) {
      fallbackHinted = true;
      if (onHintFallbacks) onHintFallbacks();
    }
  }

  function checkStall() {
    if (stalled || frozen || !started) return;
    if (detects > 0) return;
    if (now() - sessionStart < SCAN_STALL_MS) return;
    stalled = true;
    if (onScanStall) onScanStall();
  }

  function isIgnored(payload) {
    const until = ignoredUntil.get(payload);
    if (until == null) return false;
    if (now() <= until) return true;
    ignoredUntil.delete(payload);
    return false;
  }

  async function tick(frame) {
    if (!started || frozen || softHold || inFlight) return { skipped: true };
    inFlight = true;
    try {
      if (decoder === "wasm") {
        await ensureWasm();
      } else if (shouldPromote()) {
        await promote();
      }
      const region = nextRegion;
      nextRegion = region === "roi" ? "full" : "roi";
      const detect = decoder === "native" ? detectNative : detectWasm;
      const payload = await detect(frame, region);
      if (!started || frozen) return { skipped: true };
      if (!payload) {
        if (decoder === "native") nativeMisses += 1;
        if (shouldPromote()) await promote();
        hintFallback();
        checkStall();
        return { miss: true };
      }
      detects += 1;
      if (isIgnored(payload)) return { ignored: true };
      softHold = true;
      const result = await decode(payload);
      if (!started) return { skipped: true };
      if (result && result.outcome === "card") {
        frozen = true;
        softHold = false;
        if (onLock) onLock(result);
        return { lock: true };
      }
      ignoredUntil.set(payload, now() + PAYLOAD_IGNORE_MS);
      softHold = false;
      if (onFailure) onFailure(result);
      return { failure: true };
    } finally {
      inFlight = false;
    }
  }

  function start() {
    started = true;
    frozen = false;
    softHold = false;
    inFlight = false;
    nativeMisses = 0;
    nextRegion = "roi";
    sessionStart = now();
    fallbackHinted = false;
    detects = 0;
    stalled = false;
    ignoredUntil.clear();
    decoder = hasNativeDetector ? "native" : "wasm";
    if (decoder === "wasm") ensureWasm();
  }

  function stop() {
    started = false;
    frozen = true;
    softHold = false;
    inFlight = false;
  }

  return { start, stop, tick, getState };
}
