import { detectNative, hasNativeBarcodeDetector, loadNativeDetector } from "./nativeDetector";

function fakeDetector({ formats = ["qr_code"], results = [] } = {}) {
  const detect = jest.fn().mockResolvedValue(results);
  const Ctor = jest.fn().mockImplementation(() => ({ detect }));
  Ctor.getSupportedFormats = jest.fn().mockResolvedValue(formats);
  return { Ctor, detect };
}

afterEach(() => {
  delete window.BarcodeDetector;
  jest.restoreAllMocks();
});

test("reports the platform detector only when the browser has one", () => {
  expect(hasNativeBarcodeDetector()).toBe(false);
  window.BarcodeDetector = fakeDetector().Ctor;
  expect(hasNativeBarcodeDetector()).toBe(true);
});

test("builds one QR detector and reuses it for every frame", async () => {
  const { Ctor, detect } = fakeDetector({ results: [{ rawValue: "" }, { rawValue: "123456" }] });
  window.BarcodeDetector = Ctor;
  const video = {};
  await expect(detectNative(video)).resolves.toBe("123456");
  await expect(detectNative(video)).resolves.toBe("123456");
  expect(Ctor).toHaveBeenCalledTimes(1);
  expect(Ctor).toHaveBeenCalledWith({ formats: ["qr_code"] });
  expect(detect).toHaveBeenCalledWith(video);
});

test("a detector that cannot read QR codes is refused so the WASM lane takes over", async () => {
  const { Ctor } = fakeDetector({ formats: ["ean_13"] });
  window.BarcodeDetector = Ctor;
  await expect(loadNativeDetector()).rejects.toThrow("cannot read QR");
  expect(Ctor).not.toHaveBeenCalled();
});

test("a failing detect is a miss, not an error", async () => {
  const { Ctor, detect } = fakeDetector();
  detect.mockRejectedValue(new Error("frame not ready"));
  window.BarcodeDetector = Ctor;
  jest.spyOn(console, "warn").mockImplementation(() => {});
  await expect(detectNative({})).resolves.toBeNull();
});

test("no source or no API means no detect", async () => {
  await expect(detectNative({})).resolves.toBeNull();
  window.BarcodeDetector = fakeDetector().Ctor;
  await expect(detectNative(null)).resolves.toBeNull();
});
