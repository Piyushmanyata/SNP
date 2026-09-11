import React, { act } from "react";
import ReactDOM from "react-dom/client";
import AadhaarScanner from "./AadhaarScanner";
import api from "../lib/api";
import * as nativeDetector from "./aadhaar/liveScan/nativeDetector";
import * as grab from "./aadhaar/liveScan/grabFrame";
import * as wasmDetector from "./aadhaar/liveScan/wasmDetector";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api");
jest.mock("./aadhaar/liveScan/wasmDetector", () => ({
  loadZxingWorker: jest.fn().mockResolvedValue(),
  detectWasmImageData: jest.fn().mockResolvedValue(null),
}));

let container = null;
let root = null;
let mediaTrack = null;
let mediaStream = null;
const PHOTO_HEADER = new Uint8Array([255, 216, 255, 192, 0, 17, 8, 0, 8, 0, 8, 3, 1, 17, 0, 2, 17, 0, 3, 17, 0]);

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  jest.spyOn(nativeDetector, "hasNativeBarcodeDetector").mockReturnValue(true);
  jest.spyOn(nativeDetector, "detectNativeImageData").mockResolvedValue(null);
  jest.spyOn(grab, "grabFrame").mockReturnValue({
    width: 4,
    height: 4,
    data: new Uint8ClampedArray(64),
  });
  jest.spyOn(grab, "bitmapToImageData").mockReturnValue({
    width: 4,
    height: 4,
    data: new Uint8ClampedArray(64),
  });

  mediaTrack = {
    stop: jest.fn(),
    getCapabilities: jest.fn().mockReturnValue({ torch: true }),
    applyConstraints: jest.fn().mockResolvedValue(),
    getSettings: jest.fn().mockReturnValue({ width: 1280, height: 720 }),
  };
  mediaStream = {
    getTracks: () => [mediaTrack],
    getVideoTracks: () => [mediaTrack],
  };

  Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
    configurable: true,
    value: jest.fn().mockResolvedValue(),
  });
  Object.defineProperty(window.HTMLMediaElement.prototype, "pause", {
    configurable: true,
    value: jest.fn(),
  });
  Object.defineProperty(window.HTMLVideoElement.prototype, "videoWidth", {
    configurable: true,
    get() {
      return 1280;
    },
  });
  Object.defineProperty(window.HTMLVideoElement.prototype, "videoHeight", {
    configurable: true,
    get() {
      return 720;
    },
  });

  navigator.mediaDevices = {
    getUserMedia: jest.fn().mockResolvedValue(mediaStream),
    enumerateDevices: jest.fn().mockResolvedValue([{ kind: "videoinput", deviceId: "cam1", label: "Back Camera" }]),
  };

  global.createImageBitmap = jest.fn().mockResolvedValue({ width: 8, height: 8, close: jest.fn() });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
  jest.restoreAllMocks();
});

describe("AadhaarScanner component", () => {
  test("renders scanner options and capture buttons", () => {
    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    const uploadBtn = container.querySelector('[data-testid="aadhaar-upload-button"]');
    const manualBtn = container.querySelector('[data-testid="aadhaar-manual-toggle"]');

    expect(cameraBtn).not.toBeNull();
    expect(uploadBtn).not.toBeNull();
    expect(manualBtn).not.toBeNull();
    expect(cameraBtn.textContent).toContain("Scan with camera");
  });

  test("offers USB / paste entry without a demo card", async () => {
    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const manualBtn = container.querySelector('[data-testid="aadhaar-manual-toggle"]');
    act(() => {
      manualBtn.click();
    });

    const textarea = container.querySelector('[data-testid="aadhaar-qr-input"]');
    const demoBtn = container.querySelector('[data-testid="generate-demo-aadhaar-button"]');
    expect(textarea).not.toBeNull();
    expect(demoBtn).toBeNull();
    expect(textarea.placeholder).not.toMatch(/demo/i);
  });

  test("decodes manual input and triggers onScanned callback", async () => {
    const onScannedMock = jest.fn();
    const fakeData = {
      full_name: "Priya Sharma",
      gender: "F",
      dob: "1992-04-10",
      age: 34,
      aadhaar_last4: "9876",
      address: "45 Station Rd, Howrah",
    };

    api.post.mockResolvedValueOnce({
      data: {
        outcome: "card",
        source: "secure_qr_xml",
        data: fakeData,
      },
    });

    act(() => {
      root.render(<AadhaarScanner onScanned={onScannedMock} />);
    });

    const manualBtn = container.querySelector('[data-testid="aadhaar-manual-toggle"]');
    act(() => {
      manualBtn.click();
    });

    const textarea = container.querySelector('[data-testid="aadhaar-qr-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value"
      ).set;
      nativeSetter.call(textarea, '<PrintLetterBarcodeData uid="999999999876" name="Priya Sharma" gender="F" dob="10/04/1992" house="45 Station Rd" vtc="Howrah" />');
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const decodeBtn = container.querySelector('[data-testid="aadhaar-scan-button"]');
    await act(async () => {
      decodeBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: '<PrintLetterBarcodeData uid="999999999876" name="Priya Sharma" gender="F" dob="10/04/1992" house="45 Station Rd" vtc="Howrah" />',
    });
    expect(onScannedMock).toHaveBeenCalledWith(fakeData, expect.any(String));
    expect(container.textContent).toContain("Identity locked from card");
  });

  test("starts environment camera and Locks after Decode card", async () => {
    const onScannedMock = jest.fn();
    nativeDetector.detectNativeImageData.mockResolvedValue("2567820190301120000...");
    api.post.mockResolvedValue({
      data: {
        outcome: "card",
        source: "secure_qr",
        data: {
          full_name: "Ramesh Kumar",
          gender: "M",
          dob: "1975-08-15",
          aadhaar_last4: "5678",
          address: "12-A, MG Road",
        },
      },
    });

    act(() => {
      root.render(<AadhaarScanner onScanned={onScannedMock} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: "2567820190301120000...",
    });
    expect(onScannedMock).toHaveBeenCalledWith(
      expect.objectContaining({
        full_name: "Ramesh Kumar",
        aadhaar_last4: "5678",
      }),
      expect.any(String)
    );
  });

  test("stopping the camera discards a pending identity response", async () => {
    const onScanned = jest.fn();
    let finishDecode;
    nativeDetector.detectNativeImageData.mockResolvedValue("pending-card");
    api.post.mockImplementationOnce(() => new Promise((resolve) => {
      finishDecode = resolve;
    }));
    act(() => root.render(<AadhaarScanner onScanned={onScanned} />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: "pending-card" });
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-stop"]').click());
    await act(async () => finishDecode({
      data: { outcome: "card", source: "secure_qr", data: { full_name: "Previous Patient" } },
    }));
    expect(onScanned).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain("Identity locked from card");
    expect(container.querySelector('[data-testid="aadhaar-camera-button"]').disabled).toBe(false);
  });

  test.each(["success", "failure"])("a restarted scan ignores an older %s without clearing its busy state", async (outcome) => {
    const onScanned = jest.fn();
    let resolvePrevious;
    let rejectPrevious;
    let resolveCurrent;
    nativeDetector.detectNativeImageData.mockResolvedValue("test-card");
    api.post
      .mockImplementationOnce(() => new Promise((resolve, reject) => {
        resolvePrevious = resolve;
        rejectPrevious = reject;
      }))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveCurrent = resolve;
      }));
    act(() => root.render(<AadhaarScanner onScanned={onScanned} />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-stop"]').click());
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    expect(api.post).toHaveBeenCalledTimes(2);
    await act(async () => {
      if (outcome === "success") {
        resolvePrevious({ data: { outcome: "card", data: { full_name: "Previous Patient" } } });
      } else {
        rejectPrevious(new Error("Previous request failed"));
      }
    });
    expect(onScanned).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="aadhaar-upload-button"]').disabled).toBe(true);
    expect(container.textContent).not.toContain("Previous request failed");
    await act(async () => resolveCurrent({
      data: { outcome: "card", source: "secure_qr", data: { full_name: "Current Patient" } },
    }));
    expect(onScanned).toHaveBeenCalledTimes(1);
    expect(onScanned).toHaveBeenCalledWith({ full_name: "Current Patient" }, "test-card");
  });

  test("opens the rear camera even when the front camera is enumerated first", async () => {
    navigator.mediaDevices.enumerateDevices.mockResolvedValue([
      { kind: "videoinput", deviceId: "front", label: "Front" },
      { kind: "videoinput", deviceId: "rear", label: "Rear" },
    ]);
    act(() => root.render(<AadhaarScanner />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    expect(navigator.mediaDevices.getUserMedia.mock.calls[0][0].video).toEqual(
      expect.objectContaining({ facingMode: { ideal: "environment" } })
    );
    expect(navigator.mediaDevices.getUserMedia.mock.calls[0][0].video.deviceId).toBeUndefined();
  });

  test("stopping during permission request releases the stream when permission arrives", async () => {
    let grantPermission;
    navigator.mediaDevices.getUserMedia.mockImplementation(() => new Promise((resolve) => {
      grantPermission = resolve;
    }));
    act(() => root.render(<AadhaarScanner />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    expect(container.textContent).toContain("Starting camera");
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-stop"]').click());
    await act(async () => grantPermission(mediaStream));
    expect(mediaTrack.stop).toHaveBeenCalled();
    expect(nativeDetector.detectNativeImageData).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="aadhaar-camera-region"]').srcObject).toBeNull();
  });

  test("handles camera permission denial gracefully with clear feedback and retry", async () => {
    const permError = new Error("NotAllowedError: Permission denied");
    permError.name = "NotAllowedError";
    navigator.mediaDevices.getUserMedia.mockRejectedValue(permError);
    navigator.mediaDevices.enumerateDevices.mockRejectedValue(new Error("Permission denied"));

    const onFailure = jest.fn();
    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} onFailure={onFailure} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    expect(container.textContent).toContain("Camera permission is off");
    const retryBtn = container.querySelector('[data-testid="aadhaar-camera-retry"]');
    expect(retryBtn).not.toBeNull();
    expect(onFailure).toHaveBeenCalled();
  });

  test("handles disabled state properly", () => {
    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} disabled={true} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    const uploadBtn = container.querySelector('[data-testid="aadhaar-upload-button"]');
    const manualBtn = container.querySelector('[data-testid="aadhaar-manual-toggle"]');

    expect(cameraBtn.disabled).toBe(true);
    expect(uploadBtn.disabled).toBe(true);
    expect(manualBtn.disabled).toBe(true);
  });

  test("handles file upload QR scan successfully", async () => {
    const onScannedMock = jest.fn();
    nativeDetector.detectNativeImageData.mockResolvedValue(
      '<PrintLetterBarcodeData uid="999999991234" name="Test Person" gender="M" dob="01/01/1980" house="Test Address" />'
    );
    api.post.mockResolvedValueOnce({
      data: {
        outcome: "card",
        source: "secure_qr_xml",
        data: { full_name: "Test Person", aadhaar_last4: "1234" },
      },
    });

    act(() => {
      root.render(<AadhaarScanner onScanned={onScannedMock} />);
    });

    const fileInput = container.querySelector('[data-testid="aadhaar-file-input"]');
    const file = new File([PHOTO_HEADER], "aadhaar_qr.jpg", { type: "image/jpeg" });

    await act(async () => {
      Object.defineProperty(fileInput, "files", {
        value: [file],
      });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(global.createImageBitmap).toHaveBeenCalledWith(file);
    expect(nativeDetector.detectNativeImageData).toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: '<PrintLetterBarcodeData uid="999999991234" name="Test Person" gender="M" dob="01/01/1980" house="Test Address" />',
    });
    expect(onScannedMock).toHaveBeenCalledWith(
      expect.objectContaining({ full_name: "Test Person", aadhaar_last4: "1234" }),
      expect.any(String)
    );
  });

  test("a native image decoder error still permits the WASM reader to scan the card", async () => {
    const onScanned = jest.fn();
    nativeDetector.detectNativeImageData.mockRejectedValueOnce(new Error("Unsupported image"));
    wasmDetector.detectWasmImageData.mockResolvedValueOnce("fallback-card");
    api.post.mockResolvedValueOnce({ data: { outcome: "card", data: { full_name: "Test Person" } } });
    act(() => root.render(<AadhaarScanner onScanned={onScanned} />));
    const fileInput = container.querySelector('[data-testid="aadhaar-file-input"]');
    await act(async () => {
      Object.defineProperty(fileInput, "files", { value: [new File([PHOTO_HEADER], "card.jpg", { type: "image/jpeg" })] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(onScanned).toHaveBeenCalledWith({ full_name: "Test Person" }, "fallback-card");
  });

  test.each(["bitmap", "native", "wasm"])("cancelled upload during %s recognition cannot replace the next scan", async (stage) => {
    const onScanned = jest.fn();
    let now = 10000;
    let tick;
    let finishRecognition;
    let finishCurrent;
    jest.spyOn(Date, "now").mockImplementation(() => now);
    jest.spyOn(global, "setInterval").mockImplementation((callback) => {
      tick = callback;
      return 12345;
    });
    act(() => root.render(<AadhaarScanner onScanned={onScanned} />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    now += 21000;
    await act(async () => tick());
    await act(async () => container.querySelector('[data-testid="fallback-upload-button"]').click());

    const recognition = new Promise((resolve) => { finishRecognition = resolve; });
    const bitmap = { width: 8, height: 8, close: jest.fn() };
    if (stage === "bitmap") {
      global.createImageBitmap.mockReturnValueOnce(recognition);
      nativeDetector.detectNativeImageData.mockResolvedValueOnce("old-upload");
    } else if (stage === "native") {
      nativeDetector.detectNativeImageData.mockReturnValueOnce(recognition);
    } else {
      wasmDetector.detectWasmImageData.mockReturnValueOnce(recognition);
    }
    const fileInput = container.querySelector('[data-testid="aadhaar-file-input"]');
    await act(async () => {
      Object.defineProperty(fileInput, "files", { value: [new File([PHOTO_HEADER], "card.jpg")] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    await act(async () => container.querySelector('[data-testid="fallback-manual-button"]').click());
    api.post.mockImplementationOnce(() => new Promise((resolve) => { finishCurrent = resolve; }));
    const textarea = container.querySelector('[data-testid="aadhaar-qr-input"]');
    act(() => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(textarea, "current-card");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector('[data-testid="aadhaar-scan-button"]').click());
    await act(async () => finishRecognition(stage === "bitmap" ? bitmap : "old-upload"));
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: "current-card" });
    expect(container.querySelector('[data-testid="aadhaar-scan-button"]').disabled).toBe(true);
    expect(onScanned).not.toHaveBeenCalled();
    await act(async () => finishCurrent({
      data: { outcome: "card", source: "secure_qr", data: { full_name: "Current Patient" } },
    }));
    expect(onScanned).toHaveBeenCalledTimes(1);
    expect(onScanned).toHaveBeenCalledWith({ full_name: "Current Patient" }, "current-card");
  });

  test("supports camera switching and torch toggle when available", async () => {
    navigator.mediaDevices.enumerateDevices.mockResolvedValue([
      { kind: "videoinput", deviceId: "cam1", label: "Rear Camera 1" },
      { kind: "videoinput", deviceId: "cam2", label: "Front Camera 2" },
    ]);

    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    const torchBtn = container.querySelector('[data-testid="aadhaar-torch-toggle"]');
    const switchBtn = container.querySelector('[data-testid="aadhaar-switch-camera"]');

    expect(torchBtn).not.toBeNull();
    expect(switchBtn).not.toBeNull();

    await act(async () => {
      torchBtn.click();
    });

    expect(mediaTrack.applyConstraints).toHaveBeenCalledWith({
      advanced: [{ torch: true }],
    });

    await act(async () => {
      switchBtn.click();
    });

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
  });

  test("handles insecure context (non-HTTPS) with helpful error message", async () => {
    const originalSecureContext = window.isSecureContext;
    Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });
    navigator.mediaDevices.getUserMedia.mockRejectedValue(new Error("MediaDevices not supported"));
    navigator.mediaDevices.enumerateDevices.mockRejectedValue(new Error("Insecure"));

    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    expect(container.textContent).toContain("Camera access requires HTTPS or localhost");

    Object.defineProperty(window, "isSecureContext", { value: originalSecureContext, configurable: true });
  });

  test("triggers decode on Enter keypress in manual USB scanner textarea", async () => {
    const onScannedMock = jest.fn();
    api.post.mockResolvedValueOnce({
      data: {
        outcome: "card",
        source: "secure_qr_xml",
        data: { full_name: "Anita Rao", aadhaar_last4: "4321" },
      },
    });

    act(() => {
      root.render(<AadhaarScanner onScanned={onScannedMock} />);
    });

    const manualBtn = container.querySelector('[data-testid="aadhaar-manual-toggle"]');
    act(() => {
      manualBtn.click();
    });

    const textarea = container.querySelector('[data-testid="aadhaar-qr-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value"
      ).set;
      nativeSetter.call(textarea, '<PrintLetterBarcodeData uid="999999994321" name="Anita Rao" gender="F" dob="14/02/1990" house="MG Road" />');
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await act(async () => {
      textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });

    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: '<PrintLetterBarcodeData uid="999999994321" name="Anita Rao" gender="F" dob="14/02/1990" house="MG Road" />',
    });
    expect(onScannedMock).toHaveBeenCalledWith(
      expect.objectContaining({ full_name: "Anita Rao", aadhaar_last4: "4321" }),
      expect.any(String)
    );
  });

  test("stops camera and switches to idle when upload button is clicked in camera mode", async () => {
    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    const uploadBtn = container.querySelector('[data-testid="aadhaar-upload-button"]');
    await act(async () => {
      uploadBtn.click();
    });

    expect(mediaTrack.stop).toHaveBeenCalled();
  });

  test("requests 1080p with continuous focus and still starts if the track is 640x480", async () => {
    mediaTrack.getSettings.mockReturnValue({ width: 640, height: 480 });

    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith(
      expect.objectContaining({
        video: expect.objectContaining({
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          focusMode: { ideal: "continuous" },
        }),
      })
    );
    expect(container.querySelector('[data-testid="aadhaar-camera-stop"]')).not.toBeNull();
  });

  test.each(["bounded", "oversized", "unknown"])("keeps preview scanning fast with %s still photos and spaces captures three seconds apart", async (kind) => {
    let now = 10000;
    let tick;
    jest.spyOn(Date, "now").mockImplementation(() => now);
    jest.spyOn(global, "setInterval").mockImplementation((callback) => {
      tick = callback;
      return 12345;
    });
    const header = new Uint8Array(PHOTO_HEADER);
    if (kind === "oversized") header.set([23, 112, 31, 64], 7);
    const takePhoto = jest.fn().mockResolvedValue(new Blob(kind === "unknown" ? [] : [header]));
    window.ImageCapture = jest.fn().mockImplementation(() => ({ takePhoto }));
    const scanNextFrame = async () => {
      tick();
      await new Promise((resolve) => setTimeout(resolve, 20));
    };
    try {
      act(() => root.render(<AadhaarScanner />));
      await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
      for (let i = 0; i < 8; i += 1) {
        now += 125;
        await act(scanNextFrame);
      }
      expect(takePhoto).not.toHaveBeenCalled();
      expect(grab.grabFrame).toHaveBeenCalledTimes(9);
      now += 3000;
      await act(scanNextFrame);
      expect(takePhoto).toHaveBeenCalledTimes(1);
      if (kind === "bounded") {
        expect(global.createImageBitmap).toHaveBeenCalledTimes(1);
      } else {
        expect(global.createImageBitmap).not.toHaveBeenCalled();
        expect(grab.grabFrame).toHaveBeenCalledTimes(10);
      }
      for (let i = 0; i < 8; i += 1) {
        now += 125;
        await act(scanNextFrame);
      }
      expect(takePhoto).toHaveBeenCalledTimes(1);
    } finally {
      delete window.ImageCapture;
    }
  });

  test("trims leading and trailing whitespace on manual decode button click", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        outcome: "card",
        source: "secure_qr_xml",
        data: { full_name: "Trim Test", aadhaar_last4: "9999" },
      },
    });

    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const manualBtn = container.querySelector('[data-testid="aadhaar-manual-toggle"]');
    act(() => {
      manualBtn.click();
    });

    const textarea = container.querySelector('[data-testid="aadhaar-qr-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value"
      ).set;
      nativeSetter.call(textarea, '   <PrintLetterBarcodeData uid="999999999999" name="Trim Test" gender="M" dob="01/01/1990" house="Address" />   \n');
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const decodeBtn = container.querySelector('[data-testid="aadhaar-scan-button"]');
    await act(async () => {
      decodeBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: '<PrintLetterBarcodeData uid="999999999999" name="Trim Test" gender="M" dob="01/01/1990" house="Address" />',
    });
  });

  test("a patient code found on camera tears the camera down", async () => {
    const onPatientCode = jest.fn().mockResolvedValue(true);
    nativeDetector.detectNativeImageData.mockResolvedValue("SNP:AB3K7T29");
    act(() => root.render(<AadhaarScanner onScanned={jest.fn()} onPatientCode={onPatientCode} />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });

    expect(onPatientCode).toHaveBeenCalledWith("SNP:AB3K7T29");
    expect(api.post).not.toHaveBeenCalledWith("/aadhaar/decode", expect.anything());
    expect(mediaTrack.stop).toHaveBeenCalled();
  });

  test("a patient code that matches nobody leaves the camera scanning", async () => {
    const onPatientCode = jest.fn().mockResolvedValue(false);
    nativeDetector.detectNativeImageData.mockResolvedValue("SNP:NOBODY99");
    act(() => root.render(<AadhaarScanner onScanned={jest.fn()} onPatientCode={onPatientCode} />));
    await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });

    expect(onPatientCode).toHaveBeenCalledWith("SNP:NOBODY99");
    expect(mediaTrack.stop).not.toHaveBeenCalled();
  });

  test.each(["SNP:AB3K7T29", "snp:ab3k7t29"])("%s is looked up as a patient, never decoded as a card", async (code) => {
    const onPatientCode = jest.fn().mockResolvedValue(true);
    act(() => root.render(<AadhaarScanner onScanned={jest.fn()} onPatientCode={onPatientCode} />));
    act(() => container.querySelector('[data-testid="aadhaar-manual-toggle"]').click());

    const textarea = container.querySelector('[data-testid="aadhaar-qr-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
      nativeSetter.call(textarea, code);
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector('[data-testid="aadhaar-scan-button"]').click());

    expect(onPatientCode).toHaveBeenCalledWith(code);
    expect(api.post).not.toHaveBeenCalledWith("/aadhaar/decode", expect.anything());
  });
});
