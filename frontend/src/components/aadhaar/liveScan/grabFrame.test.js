import { bitmapToImageData, grabFrame } from "./grabFrame";

let context;

beforeEach(() => {
  context = {
    drawImage: jest.fn(),
    getImageData: jest.fn((_x, _y, width, height) => ({ width, height })),
  };
  jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
});

afterEach(() => jest.restoreAllMocks());

test("large photos preserve proportions while capping decoded pixel allocations", () => {
  const photo = { width: 8000, height: 6000 };
  expect(bitmapToImageData(photo, 1600)).toEqual({ width: 1600, height: 1200 });
  expect(bitmapToImageData(photo)).toEqual({ width: 2560, height: 1920 });
  expect(context.drawImage).toHaveBeenLastCalledWith(photo, 0, 0, 2560, 1920);
});

test("preview frames are bounded without upscaling low-resolution cameras", () => {
  expect(grabFrame({ videoWidth: 3840, videoHeight: 2160 }, "full")).toEqual({ width: 1600, height: 900 });
  expect(grabFrame({ videoWidth: 640, videoHeight: 480 }, "full")).toEqual({ width: 640, height: 480 });
});
