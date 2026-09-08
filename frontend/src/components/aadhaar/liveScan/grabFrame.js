import { guideRoi } from "./guideRoi";

async function photoDimensions(file) {
  const header = file.slice(0, 65536);
  const buffer = typeof header.arrayBuffer === "function"
    ? await header.arrayBuffer()
    : await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(header);
    });
  const view = new DataView(buffer);
  if (view.byteLength >= 24 && view.getUint32(0) === 0x89504e47 && view.getUint32(4) === 0x0d0a1a0a
    && view.getUint32(8) === 13 && view.getUint32(12) === 0x49484452) {
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null;
  let offset = 2;
  while (offset + 4 <= view.byteLength) {
    if (view.getUint8(offset++) !== 0xff) return null;
    while (offset < view.byteLength && view.getUint8(offset) === 0xff) offset++;
    if (offset + 3 > view.byteLength) return null;
    const marker = view.getUint8(offset++);
    const length = view.getUint16(offset);
    if (length < 2 || offset + length > view.byteLength) return null;
    if (marker === 0xc0 || marker === 0xc2) {
      if (length < 8) return null;
      return { width: view.getUint16(offset + 5), height: view.getUint16(offset + 3) };
    }
    if (!(marker >= 0xe0 && marker <= 0xef) && ![0xdb, 0xc4, 0xdd, 0xfe].includes(marker)) return null;
    offset += length;
  }
  return null;
}

export async function canDecodePhoto(file) {
  const dimensions = await photoDimensions(file);
  return Boolean(dimensions && dimensions.width > 0 && dimensions.height > 0
    && Math.max(dimensions.width, dimensions.height) <= 2560 && dimensions.width * dimensions.height <= 4000000);
}
let canvas;

export function grabFrame(video, region) {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return null;
  let sx = 0;
  let sy = 0;
  let sw = width;
  let sh = height;
  if (region === "roi") {
    const roi = guideRoi(width, height);
    sx = roi.x;
    sy = roi.y;
    sw = roi.size;
    sh = roi.size;
  }
  const scale = Math.min(1, 1600 / Math.max(sw, sh));
  if (!canvas) canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(sw * scale));
  canvas.height = Math.max(1, Math.round(sh * scale));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

export function bitmapToImageData(bitmap, maxDimension = 2560) {
  if (!bitmap) return null;
  const width = bitmap.naturalWidth || bitmap.width;
  const height = bitmap.naturalHeight || bitmap.height;
  if (!width || !height) return null;
  const scale = Math.min(1, maxDimension / Math.max(width, height));
  if (!canvas) canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}
