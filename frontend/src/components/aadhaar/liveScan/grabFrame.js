import { guideRoi } from "./guideRoi";

export const MAX_FRAME_EDGE = 1920;

let canvas;

export function grabFrame(video, region) {
  const width = video?.videoWidth;
  const height = video?.videoHeight;
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
  const scale = Math.min(1, MAX_FRAME_EDGE / Math.max(sw, sh));
  const w = Math.max(1, Math.round(sw * scale));
  const h = Math.max(1, Math.round(sh * scale));
  if (!canvas) canvas = document.createElement("canvas");
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, w, h);
  return ctx.getImageData(0, 0, w, h);
}
