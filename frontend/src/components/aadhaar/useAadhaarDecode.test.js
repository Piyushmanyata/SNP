import React, { act } from "react";
import ReactDOM from "react-dom/client";
import api, { formatApiError } from "../../lib/api";
import { useAadhaarDecode } from "./useAadhaarDecode";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";
import * as grab from "./liveScan/grabFrame";

jest.mock("../../lib/api");
jest.mock("./liveScan/nativeDetector");
jest.mock("./liveScan/wasmDetector");
jest.mock("./liveScan/grabFrame", () => ({
  ...jest.requireActual("./liveScan/grabFrame"),
  bitmapToImageData: jest.fn(() => ({ width: 4, height: 4, data: new Uint8ClampedArray(64) })),
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
let root;
let container;
let scanner;
let onScanned;

function photoFile(width = 8, height = 8) {
  const bytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 0, 0, 0, 0, 0]);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return new File([bytes], "card.png", { type: "image/png" });
}

function Harness() {
  scanner = useAadhaarDecode({ onScanned });
  return null;
}

beforeEach(() => {
  jest.resetAllMocks();
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  onScanned = jest.fn();
  global.createImageBitmap = jest.fn().mockResolvedValue({ width: 8, height: 8, close: jest.fn() });
  nativeDetector.hasNativeBarcodeDetector.mockReturnValue(false);
  wasmDetector.loadZxingWorker.mockResolvedValue();
  wasmDetector.detectWasmImageData.mockResolvedValue(null);
  grab.bitmapToImageData.mockReturnValue({ width: 4, height: 4, data: new Uint8ClampedArray(64) });
  formatApiError.mockReturnValue("Request failed");
  act(() => root.render(<Harness />));
});

test("dense photo retries with more image detail before requesting OCR", async () => {
  global.createImageBitmap.mockResolvedValueOnce({ width: 2400, height: 1600, close: jest.fn() });
  grab.bitmapToImageData.mockImplementation((_bitmap, size) => ({ width: size, height: size, data: new Uint8ClampedArray(4) }));
  wasmDetector.detectWasmImageData.mockImplementation(async (image) => image.width > 1600 ? "dense-card" : null);
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(photoFile(2400, 1600)));
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "dense-card");
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: "dense-card" });
});

afterEach(() => {
  act(() => root.unmount());
  delete global.createImageBitmap;
});

test("a browser without bitmap decoding can read a photo through its image element", async () => {
  delete global.createImageBitmap;
  const PreviousImage = global.Image;
  const previousCreate = URL.createObjectURL;
  const previousRevoke = URL.revokeObjectURL;
  URL.createObjectURL = jest.fn(() => "blob:test");
  URL.revokeObjectURL = jest.fn();
  global.Image = class {
    width = 8;
    height = 8;
    set src(value) { if (value) Promise.resolve().then(() => this.onload()); }
  };
  wasmDetector.detectWasmImageData.mockResolvedValueOnce("browser-card");
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
  try {
    await act(async () => scanner.scanFile(photoFile()));
    expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "browser-card");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test");
  } finally {
    global.Image = PreviousImage;
    URL.createObjectURL = previousCreate;
    URL.revokeObjectURL = previousRevoke;
  }
});

test("unreadable photo returns backend suggestions for review without locking identity", async () => {
  const file = new File(["image"], "card.jpg", { type: "image/jpeg" });
  const data = { full_name: "Test Person", gender: "F" };
  api.post.mockResolvedValueOnce({ data: { outcome: "review", data, message: "Review extracted details" } });
  await act(async () => scanner.scanFile(file));
  expect(api.post).toHaveBeenCalledWith("/aadhaar/extract", file, expect.objectContaining({
    headers: { "Content-Type": "image/jpeg" },
  }));
  expect(scanner.reviewData).toEqual(data);
  expect(scanner.outcome).toBe("review");
  expect(scanner.busy).toBe(false);
  expect(onScanned).not.toHaveBeenCalled();
});

test("PDF uploads go straight to the backend without allocating a browser bitmap", async () => {
  const file = new File(["pdf"], "card.pdf", { type: "application/pdf" });
  api.post.mockResolvedValueOnce({ data: { outcome: "review", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(file));
  expect(global.createImageBitmap).not.toHaveBeenCalled();
  expect(scanner.reviewData).toEqual({ full_name: "Test Person" });
});

test("password retry sends an encoded transient header and clears the password prompt", async () => {
  const file = new File(["pdf"], "card.pdf", { type: "application/pdf" });
  api.post.mockRejectedValueOnce({ response: { status: 422, data: { detail: { code: "PDF_PASSWORD_REQUIRED" } } } });
  await act(async () => scanner.scanFile(file));
  expect(scanner.passwordRequired).toBe(true);
  expect(scanner.reviewData).toBeNull();
  api.post.mockResolvedValueOnce({ data: { outcome: "review", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(file, "राम 1990"));
  expect(api.post).toHaveBeenLastCalledWith("/aadhaar/extract", file, expect.objectContaining({
    headers: { "Content-Type": "application/pdf", "X-PDF-Password": "%E0%A4%B0%E0%A4%BE%E0%A4%AE%201990" },
  }));
  expect(scanner.passwordRequired).toBe(false);
  expect(onScanned).not.toHaveBeenCalled();
});

test.each(["card", "review"])("cancelled extraction cannot apply an older %s to a newer scan", async (outcome) => {
  let finishPrevious;
  let finishCurrent;
  let uploadStarted;
  const started = new Promise((resolve) => { uploadStarted = resolve; });
  api.post.mockImplementationOnce(() => new Promise((resolve) => {
    finishPrevious = resolve;
    uploadStarted();
  }));
  await act(async () => {
    scanner.scanFile(new File(["image"], "old.jpg", { type: "image/jpeg" }));
    await started;
  });
  const uploadSignal = api.post.mock.calls[0][2].signal;
  act(() => scanner.cancelDecode());
  expect(uploadSignal.aborted).toBe(true);
  api.post.mockImplementationOnce(() => new Promise((resolve) => { finishCurrent = resolve; }));
  await act(async () => { scanner.decode("current-card"); });
  await act(async () => finishPrevious({ data: { outcome, data: { full_name: "Previous Patient" } } }));
  expect(scanner.busy).toBe(true);
  expect(scanner.reviewData).toBeNull();
  expect(onScanned).not.toHaveBeenCalled();
  await act(async () => finishCurrent({ data: { outcome: "card", data: { full_name: "Current Patient" } } }));
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Current Patient" }, "current-card");
});

test("a new attempt and cancellation clear earlier review suggestions", async () => {
  api.post.mockResolvedValue({ data: { outcome: "review", data: { full_name: "Previous Patient" } } });
  await act(async () => scanner.scanFile(new File(["image"], "old.jpg")));
  expect(scanner.reviewData).not.toBeNull();
  act(() => scanner.cancelDecode());
  expect(scanner.reviewData).toBeNull();
  expect(scanner.passwordRequired).toBe(false);
});

test("OCR service failure offers a usable fallback without stale identity", async () => {
  api.post.mockRejectedValueOnce({ response: { status: 503, data: { detail: { code: "OCR_UNAVAILABLE" } } } });
  await act(async () => scanner.scanFile(new File(["image"], "card.jpg")));
  expect(scanner.error).toMatch(/enter details manually/);
  expect(scanner.busy).toBe(false);
  expect(scanner.reviewData).toBeNull();
  expect(onScanned).not.toHaveBeenCalled();
});

test.each(["png", "jpeg"])("a small compressed 48-megapixel %s goes to the backend before browser decoding", async (format) => {
  const bytes = format === "png"
    ? new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 31, 64, 0, 0, 23, 112])
    : new Uint8Array([255, 216, 255, 192, 0, 17, 8, 23, 112, 31, 64, 3, 1, 17, 0, 2, 17, 0, 3, 17, 0]);
  const file = new File([bytes], `card.${format}`, { type: `image/${format}` });
  const imageConstructor = jest.spyOn(global, "Image");
  api.post.mockResolvedValueOnce({ data: { outcome: "review", data: { full_name: "Test Person" } } });
  try {
    await act(async () => scanner.scanFile(file));
    expect(global.createImageBitmap).not.toHaveBeenCalled();
    expect(imageConstructor).not.toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledWith("/aadhaar/extract", file, expect.any(Object));
  } finally {
    imageConstructor.mockRestore();
  }
});

test.each([
  ["unknown format", new Uint8Array([1, 2, 3, 4])],
  ["truncated JPEG segment", new Uint8Array([255, 216, 255, 224, 255, 255])],
])("%s uses backend fallback without speculative browser decoding", async (_name, bytes) => {
  api.post.mockResolvedValueOnce({ data: { outcome: "review", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(new File([bytes], "card.jpg", { type: "image/jpeg" })));
  expect(global.createImageBitmap).not.toHaveBeenCalled();
  expect(scanner.reviewData).toEqual({ full_name: "Test Person" });
});
