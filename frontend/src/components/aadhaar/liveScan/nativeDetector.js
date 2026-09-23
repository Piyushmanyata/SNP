import logger from "../../../lib/logger";

let cached = { ctor: null, detector: null };

export function hasNativeBarcodeDetector() {
  return typeof window !== "undefined" && typeof window.BarcodeDetector === "function";
}

export async function loadNativeDetector() {
  const ctor = hasNativeBarcodeDetector() ? window.BarcodeDetector : null;
  if (!ctor) throw new Error("BarcodeDetector unavailable");
  if (cached.ctor !== ctor) {
    const pending = (async () => {
      const formats = typeof ctor.getSupportedFormats === "function" ? await ctor.getSupportedFormats() : ["qr_code"];
      if (!formats.includes("qr_code")) throw new Error("BarcodeDetector cannot read QR codes");
      return new ctor({ formats: ["qr_code"] });
    })();
    cached = { ctor, detector: pending };
    pending.catch(() => {
      if (cached.detector === pending) cached = { ctor: null, detector: null };
    });
  }
  return cached.detector;
}

export async function detectNative(source) {
  if (!source || !hasNativeBarcodeDetector()) return null;
  try {
    const detector = await loadNativeDetector();
    const codes = await detector.detect(source);
    return codes?.find((code) => code.rawValue)?.rawValue || null;
  } catch (e) {
    logger.warn("BarcodeDetector failed:", e);
    return null;
  }
}
