import React, { act } from "react";
import ReactDOM from "react-dom/client";
import api, { formatApiError } from "../../lib/api";
import { decodePayload, useAadhaarDecode } from "./useAadhaarDecode";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";

jest.mock("../../lib/api");
jest.mock("./liveScan/nativeDetector");
jest.mock("./liveScan/wasmDetector");

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

let classify;
let resolveCard;

function Harness() {
  scanner = useAadhaarDecode({ onScanned, classify: classify || decodePayload, resolveCard });
  return null;
}

beforeEach(() => {
  jest.resetAllMocks();
  container = document.createElement("div");
  root = ReactDOM.createRoot(container);
  onScanned = jest.fn();
  classify = undefined;
  resolveCard = undefined;
  global.createImageBitmap = jest.fn().mockResolvedValue({ width: 8, height: 8, close: jest.fn() });
  nativeDetector.hasNativeBarcodeDetector.mockReturnValue(false);
  wasmDetector.loadZxingWorker.mockResolvedValue();
  wasmDetector.detectWasmPhoto.mockResolvedValue(null);
  formatApiError.mockReturnValue("Request failed");
  act(() => root.render(<Harness />));
});

test("a phone photo is read whole in the worker before any upload", async () => {
  const file = photoFile(4000, 3000);
  wasmDetector.detectWasmPhoto.mockResolvedValueOnce("dense-card");
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(file));
  expect(wasmDetector.detectWasmPhoto).toHaveBeenCalledWith(file);
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "dense-card");
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: "dense-card" });
});

test("the platform detector reads the photo bitmap first and skips the worker", async () => {
  const bitmap = { width: 4000, height: 3000, close: jest.fn() };
  global.createImageBitmap.mockResolvedValueOnce(bitmap);
  nativeDetector.hasNativeBarcodeDetector.mockReturnValue(true);
  nativeDetector.detectNative.mockResolvedValueOnce("native-card");
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(photoFile(4000, 3000)));
  expect(nativeDetector.detectNative).toHaveBeenCalledWith(bitmap);
  expect(bitmap.close).toHaveBeenCalled();
  expect(wasmDetector.detectWasmPhoto).not.toHaveBeenCalled();
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "native-card");
});

test("a platform miss falls through to the worker", async () => {
  nativeDetector.hasNativeBarcodeDetector.mockReturnValue(true);
  nativeDetector.detectNative.mockResolvedValueOnce(null);
  wasmDetector.detectWasmPhoto.mockResolvedValueOnce("wasm-card");
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(photoFile()));
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "wasm-card");
});

test("a page resolver classifies the photo payload instead of the default decode", async () => {
  classify = jest.fn().mockResolvedValue({ outcome: "card", source: "desk_scan" });
  act(() => root.render(<Harness />));
  wasmDetector.detectWasmPhoto.mockResolvedValueOnce("door-card");
  await act(async () => scanner.scanFile(photoFile()));
  expect(classify).toHaveBeenCalledWith("door-card");
  expect(api.post).not.toHaveBeenCalled();
  expect(scanner.outcome).toBe("card");
});

test("a patient code photo that matches nobody is not uploaded for OCR", async () => {
  classify = jest.fn().mockResolvedValue({ outcome: "not-aadhaar", source: "patient_code", message: "No patient found for that code." });
  act(() => root.render(<Harness />));
  wasmDetector.detectWasmPhoto.mockResolvedValueOnce("snp:unknown1");
  await act(async () => scanner.scanFile(photoFile()));
  expect(api.post).not.toHaveBeenCalled();
  expect(scanner.busy).toBe(false);
});

test("a card read by the server is resolved by the page resolver too", async () => {
  resolveCard = jest.fn().mockResolvedValue({ outcome: "card", source: "desk_scan" });
  act(() => root.render(<Harness />));
  const file = new File(["pdf"], "card.pdf", { type: "application/pdf" });
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" }, payload: "server-card" } });
  await act(async () => scanner.scanFile(file));
  expect(resolveCard).toHaveBeenCalledWith("server-card");
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(scanner.outcome).toBe("card");
});

test("without a page resolver a server-read card is accepted without a second decode", async () => {
  const file = new File(["pdf"], "card.pdf", { type: "application/pdf" });
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" }, payload: "server-card" } });
  await act(async () => scanner.scanFile(file));
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "server-card");
});

test("a resolver failure is shown and counted as an error", async () => {
  classify = jest.fn().mockRejectedValue(new Error("offline"));
  act(() => root.render(<Harness />));
  await act(async () => { await scanner.decode("card"); });
  expect(scanner.error).toBe("Request failed");
  expect(scanner.busy).toBe(false);
});

afterEach(() => {
  act(() => root.unmount());
  delete global.createImageBitmap;
});

test("a browser without bitmap decoding still reads the photo in the worker", async () => {
  delete global.createImageBitmap;
  nativeDetector.hasNativeBarcodeDetector.mockReturnValue(true);
  wasmDetector.detectWasmPhoto.mockResolvedValueOnce("browser-card");
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
  await act(async () => scanner.scanFile(photoFile()));
  expect(nativeDetector.detectNative).not.toHaveBeenCalled();
  expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "browser-card");
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
