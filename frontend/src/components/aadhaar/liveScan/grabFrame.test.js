import { grabFrame, MAX_FRAME_EDGE } from "./grabFrame";

let context;

beforeEach(() => {
  context = {
    drawImage: jest.fn(),
    getImageData: jest.fn((_x, _y, width, height) => ({ width, height })),
  };
  jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
});

afterEach(() => jest.restoreAllMocks());

test("full frames keep native pixels up to the cap and never upscale", () => {
  expect(grabFrame({ videoWidth: 1920, videoHeight: 1080 }, "full")).toEqual({ width: 1920, height: 1080 });
  expect(grabFrame({ videoWidth: 3840, videoHeight: 2160 }, "full")).toEqual({ width: MAX_FRAME_EDGE, height: 1080 });
  expect(grabFrame({ videoWidth: 640, videoHeight: 480 }, "full")).toEqual({ width: 640, height: 480 });
});

test("the Guide ROI is a centred square of the short edge at native pixels", () => {
  const video = { videoWidth: 1080, videoHeight: 1920 };
  expect(grabFrame(video, "roi")).toEqual({ width: 972, height: 972 });
  expect(context.drawImage).toHaveBeenLastCalledWith(video, 54, 474, 972, 972, 0, 0, 972, 972);
});

test("a video without dimensions yields no frame", () => {
  expect(grabFrame({ videoWidth: 0, videoHeight: 0 }, "full")).toBeNull();
  expect(grabFrame(null, "full")).toBeNull();
  expect(context.drawImage).not.toHaveBeenCalled();
});
