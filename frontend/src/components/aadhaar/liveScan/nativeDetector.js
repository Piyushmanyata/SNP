import logger from "../../../lib/logger";

export function hasNativeBarcodeDetector() {
  return typeof window !== "undefined" && typeof window.BarcodeDetector === "function";
}

export async function detectNativeImageData(imageData) {
  if (!hasNativeBarcodeDetector() || !imageData) return null;
  try {
    const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
    const codes = await detector.detect(imageData);
    const hit = codes && codes[0];
    return hit && hit.rawValue ? hit.rawValue : null;
  } catch (e) {
    logger.warn("BarcodeDetector failed:", e);
    return null;
  }
}

