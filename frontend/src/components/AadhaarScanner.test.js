import React, { act } from "react";
import ReactDOM from "react-dom/client";
import AadhaarScanner from "./AadhaarScanner";
import api from "../lib/api";
import { Html5Qrcode } from "html5-qrcode";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api");
jest.mock("html5-qrcode");

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
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

  test("toggles manual USB / paste mode and generates demo payload", async () => {
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
    expect(demoBtn).not.toBeNull();

    act(() => {
      demoBtn.click();
    });

    expect(textarea.value).toMatch(/^AADHAAR\|/);
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
        source: "demo",
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
      nativeSetter.call(textarea, "AADHAAR|Priya Sharma|F|1992-04-10|9876|45 Station Rd, Howrah");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const decodeBtn = container.querySelector('[data-testid="aadhaar-scan-button"]');
    await act(async () => {
      decodeBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: "AADHAAR|Priya Sharma|F|1992-04-10|9876|45 Station Rd, Howrah",
    });
    expect(onScannedMock).toHaveBeenCalledWith(fakeData);
    expect(container.textContent).toContain("Identity locked from card");
  });

  test("initializes camera scanner with environment facingMode and handles successful scan", async () => {
    const onScannedMock = jest.fn();
    let scanSuccessCallback = null;

    const mockStart = jest.fn().mockImplementation((cameraId, config, onSuccess) => {
      scanSuccessCallback = onSuccess;
      return Promise.resolve();
    });
    const mockStop = jest.fn().mockResolvedValue();
    const mockClear = jest.fn().mockResolvedValue();

    Html5Qrcode.getCameras = jest.fn().mockResolvedValue([{ id: "cam1", label: "Back Camera" }]);
    Html5Qrcode.mockImplementation(() => ({
      start: mockStart,
      stop: mockStop,
      clear: mockClear,
      isScanning: true,
      getRunningTrackCapabilities: jest.fn().mockReturnValue({ torch: true }),
    }));

    api.post.mockResolvedValueOnce({
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

    expect(mockStart).toHaveBeenCalled();

    const stopBtn = container.querySelector('[data-testid="aadhaar-camera-stop"]');
    expect(stopBtn).not.toBeNull();

    await act(async () => {
      await scanSuccessCallback("2567820190301120000...");
    });

    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: "2567820190301120000...",
    });
    expect(onScannedMock).toHaveBeenCalledWith(
      expect.objectContaining({
        full_name: "Ramesh Kumar",
        aadhaar_last4: "5678",
      })
    );
  });

  test("handles camera permission denial gracefully with clear feedback and retry", async () => {
    Html5Qrcode.getCameras = jest.fn().mockRejectedValue(new Error("Permission denied"));
    const permError = new Error("NotAllowedError: Permission denied");
    permError.name = "NotAllowedError";

    Html5Qrcode.mockImplementation(() => ({
      start: jest.fn().mockRejectedValue(permError),
      stop: jest.fn().mockResolvedValue(),
      clear: jest.fn().mockResolvedValue(),
      isScanning: false,
    }));

    act(() => {
      root.render(<AadhaarScanner onScanned={jest.fn()} />);
    });

    const cameraBtn = container.querySelector('[data-testid="aadhaar-camera-button"]');
    await act(async () => {
      cameraBtn.click();
    });

    expect(container.textContent).toContain("Camera permission denied");
    const retryBtn = container.querySelector('[data-testid="aadhaar-camera-retry"]');
    expect(retryBtn).not.toBeNull();
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
    const mockScanFile = jest.fn().mockResolvedValue("AADHAAR|Test Person|M|1980-01-01|1234|Test Address");
    const mockClear = jest.fn().mockResolvedValue();

    Html5Qrcode.mockImplementation(() => ({
      scanFile: mockScanFile,
      clear: mockClear,
    }));

    api.post.mockResolvedValueOnce({
      data: {
        outcome: "card",
        source: "demo",
        data: { full_name: "Test Person", aadhaar_last4: "1234" },
      },
    });

    act(() => {
      root.render(<AadhaarScanner onScanned={onScannedMock} />);
    });

    const fileInput = container.querySelector('[data-testid="aadhaar-file-input"]');
    const file = new File(["fake-image-data"], "aadhaar_qr.jpg", { type: "image/jpeg" });

    await act(async () => {
      Object.defineProperty(fileInput, "files", {
        value: [file],
      });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(mockScanFile).toHaveBeenCalledWith(file, false);
    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", {
      payload: "AADHAAR|Test Person|M|1980-01-01|1234|Test Address",
    });
    expect(onScannedMock).toHaveBeenCalledWith(
      expect.objectContaining({ full_name: "Test Person", aadhaar_last4: "1234" })
    );
  });
});
