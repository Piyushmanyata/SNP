import { guideRoi } from "./guideRoi";

describe("guideRoi", () => {
  test("720p: centered square is 90% of the short edge", () => {
    expect(guideRoi(1280, 720)).toEqual({ x: 316, y: 36, size: 648 });
  });

  test("640x480 still produces a native-pixel ROI from actual dimensions", () => {
    expect(guideRoi(640, 480)).toEqual({ x: 104, y: 24, size: 432 });
  });

  test("portrait uses the actual short edge, not a requested 720p size", () => {
    expect(guideRoi(480, 640)).toEqual({ x: 24, y: 104, size: 432 });
  });
});
