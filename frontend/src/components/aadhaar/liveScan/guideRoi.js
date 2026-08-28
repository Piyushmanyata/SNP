export const GUIDE_ROI_FRACTION = 0.9;

export function guideRoi(width, height) {
  const w = Math.max(1, Math.floor(Number(width) || 0));
  const h = Math.max(1, Math.floor(Number(height) || 0));
  const size = Math.max(1, Math.round(Math.min(w, h) * GUIDE_ROI_FRACTION));
  const x = Math.floor((w - size) / 2);
  const y = Math.floor((h - size) / 2);
  return { x, y, size };
}
