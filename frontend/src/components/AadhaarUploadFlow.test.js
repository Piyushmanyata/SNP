import React, { act } from "react";
import { createRoot } from "react-dom/client";
import AadhaarScanner from "./AadhaarScanner";
import api from "../lib/api";

jest.mock("../lib/api", () => ({
  __esModule: true,
  default: { post: jest.fn() },
  formatApiError: (error) => error.response?.data?.detail?.message || error.message,
  errorPayload: (error) => error.response?.data?.detail,
}));
const mockStop = jest.fn();
jest.mock("./aadhaar/useAadhaarCamera", () => ({
  useAadhaarCamera: () => ({ cameraState: "idle", cameras: [], stopCamera: mockStop, startCamera: jest.fn(), videoRef: { current: null } }),
}));
global.IS_REACT_ACT_ENVIRONMENT = true;
let container;
let root;
beforeEach(() => {
  api.post.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

async function selectPdf() {
  const file = new File(["%PDF-1.7 synthetic"], "aadhaar.pdf", { type: "application/pdf" });
  const input = container.querySelector('[data-testid="aadhaar-file-input"]');
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  return file;
}

test("encrypted PDF retries transiently and returns only QR details", async () => {
  const onScanned = jest.fn();
  act(() => root.render(<AadhaarScanner onScanned={onScanned} />));
  api.post.mockRejectedValueOnce({ response: { data: { detail: { code: "PDF_PASSWORD_REQUIRED", message: "Enter the PDF password." } } } });
  const file = await selectPdf();
  const input = container.querySelector('[data-testid="aadhaar-pdf-password"]');
  expect(input).not.toBeNull();
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "TEST1990");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Patient", age: 36 }, payload: "pdf-qr" } });
  await act(async () => [...container.querySelectorAll("button")].find((button) => button.textContent === "Open PDF").click());
  expect(api.post).toHaveBeenLastCalledWith("/aadhaar/extract", file, expect.objectContaining({ headers: expect.objectContaining({ "X-PDF-Password": "TEST1990" }) }));
  expect(container.querySelector('[data-testid="aadhaar-pdf-password"]')).toBeNull();
  expect(onScanned).toHaveBeenCalledWith(expect.objectContaining({ full_name: "Test Patient" }), "pdf-qr");
});

test("an unreadable PDF reports a manual-entry fallback without OCR review", async () => {
  act(() => root.render(<AadhaarScanner onScanned={jest.fn()} />));
  expect(container.querySelector('[data-testid="aadhaar-review-form"]')).toBeNull();
  api.post.mockRejectedValueOnce({ response: { data: { detail: { code: "QR_NOT_FOUND", message: "No readable Aadhaar QR was found. Enter details manually at the desk." } } } });
  await selectPdf();
  expect(container.querySelector('[data-testid="aadhaar-review-form"]')).toBeNull();
  expect(container.textContent).toMatch(/enter details manually/i);
});

test("cancelling a read aborts the upload and ignores a late result", async () => {
  let resolveUpload;
  api.post.mockImplementation(() => new Promise((resolve) => { resolveUpload = resolve; }));
  const onScanned = jest.fn();
  act(() => root.render(<AadhaarScanner onScanned={onScanned} />));
  await selectPdf();
  const signal = api.post.mock.calls[0][2].signal;
  await act(async () => [...container.querySelectorAll("button")].find((button) => button.textContent === "Cancel reading").click());
  expect(signal.aborted).toBe(true);
  await act(async () => resolveUpload({ data: { outcome: "card", data: { full_name: "Old file" }, payload: "old-qr" } }));
  expect(onScanned).not.toHaveBeenCalled();
  expect(container.querySelector('[data-testid="aadhaar-review-form"]')).toBeNull();
});
