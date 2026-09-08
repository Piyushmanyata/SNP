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

test("encrypted PDF retries transiently and requires review before returning details", async () => {
  const onTranscribed = jest.fn();
  const onScanned = jest.fn();
  act(() => root.render(<AadhaarScanner onScanned={onScanned} onTranscribed={onTranscribed} />));
  api.post.mockRejectedValueOnce({ response: { data: { detail: { code: "PDF_PASSWORD_REQUIRED", message: "Enter the PDF password." } } } });
  const file = await selectPdf();
  const input = container.querySelector('[data-testid="aadhaar-pdf-password"]');
  expect(input).not.toBeNull();
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "TEST1990");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  api.post.mockResolvedValueOnce({ data: { outcome: "review", data: { full_name: "Test Patient", age: 36 } } });
  await act(async () => [...container.querySelectorAll("button")].find((button) => button.textContent === "Open PDF").click());
  expect(api.post).toHaveBeenLastCalledWith("/aadhaar/extract", file, expect.objectContaining({ headers: expect.objectContaining({ "X-PDF-Password": "TEST1990" }) }));
  expect(container.querySelector('[data-testid="aadhaar-pdf-password"]')).toBeNull();
  expect(onTranscribed).not.toHaveBeenCalled();
  act(() => container.querySelector('[data-testid="aadhaar-review-check"]').click());
  act(() => container.querySelector('[data-testid="aadhaar-review-confirm"]').click());
  expect(onTranscribed).toHaveBeenCalledWith(expect.objectContaining({ full_name: "Test Patient" }));
  expect(onScanned).not.toHaveBeenCalled();
});

test("switching to manual entry aborts upload and ignores a late result", async () => {
  let resolveUpload;
  api.post.mockImplementation(() => new Promise((resolve) => { resolveUpload = resolve; }));
  const onScanned = jest.fn();
  act(() => root.render(<AadhaarScanner onScanned={onScanned} onTranscribed={jest.fn()} />));
  await selectPdf();
  const signal = api.post.mock.calls[0][2].signal;
  await act(async () => container.querySelector('[data-testid="aadhaar-enter-details"]').click());
  expect(signal.aborted).toBe(true);
  const name = container.querySelector('[data-testid="aadhaar-review-full_name"]');
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(name, "Manually entered");
    name.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => resolveUpload({ data: { outcome: "card", data: { full_name: "Old file" }, payload: "old-qr" } }));
  expect(name.value).toBe("Manually entered");
  expect(onScanned).not.toHaveBeenCalled();
});
