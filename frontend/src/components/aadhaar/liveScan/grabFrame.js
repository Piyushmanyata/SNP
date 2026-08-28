import { guideRoi } from "./guideRoi";

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
  if (!canvas) canvas = document.createElement("canvas");
  canvas.width = sw;
  canvas.height = sh;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, sw, sh);
  return ctx.getImageData(0, 0, sw, sh);
}

export function bitmapToImageData(bitmap) {
  if (!bitmap) return null;
  if (!canvas) canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(bitmap, 0, 0, bitmap.width, bitmap.height);
  return ctx.getImageData(0, 0, bitmap.width, bitmap.height);
}
