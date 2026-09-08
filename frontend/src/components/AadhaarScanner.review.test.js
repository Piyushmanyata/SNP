import React, { act } from "react";
import { createRoot } from "react-dom/client";
import AadhaarScanner from "./AadhaarScanner";

const mockCancel = jest.fn();
let mockReview = null;
jest.mock("./aadhaar/useAadhaarDecode", () => ({
  useAadhaarDecode: () => ({
    payload: "", setPayload: jest.fn(), error: "", setError: jest.fn(), outcome: mockReview ? "review" : "",
    setOutcome: jest.fn(), source: "", busy: false, decode: jest.fn(), cancelDecode: mockCancel,
    scanFile: jest.fn(), reviewData: mockReview, passwordRequired: false,
  }),
}));
jest.mock("./aadhaar/useAadhaarCamera", () => ({
  useAadhaarCamera: () => ({ cameraState: "idle", cameras: [], startCamera: jest.fn(), stopCamera: jest.fn(), switchCamera: jest.fn(), videoRef: { current: null } }),
}));
global.IS_REACT_ACT_ENVIRONMENT = true;

test("reviewed OCR is delivered as transcription, never as a card scan", () => {
  mockReview = { full_name: "Sunita Devi", age: 51 };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const onTranscribed = jest.fn();
  const onScanned = jest.fn();
  act(() => root.render(<AadhaarScanner onScanned={onScanned} onTranscribed={onTranscribed} />));
  expect(container.querySelector('[data-testid="aadhaar-review-form"]')).not.toBeNull();
  act(() => container.querySelector('[data-testid="aadhaar-review-check"]').click());
  act(() => container.querySelector('[data-testid="aadhaar-review-confirm"]').click());
  expect(onTranscribed).toHaveBeenCalledWith(expect.objectContaining({ full_name: "Sunita Devi" }));
  expect(onScanned).not.toHaveBeenCalled();
  expect(mockCancel).toHaveBeenCalled();
  act(() => root.unmount());
  container.remove();
});
