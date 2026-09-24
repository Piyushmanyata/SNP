import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { FulfilmentStation } from "./components/clinical/FulfilmentStation";
import { FulfilmentSection } from "./components/clinical/FulfilmentSection";
import Desk from "./pages/Desk";
import { MemoryRouter } from "react-router-dom";
import {
  acquireCameraStream,
  buildCameraConstraintAttempts,
  checkTorchCapability,
  applyTorch,
  cameraErrorMessage
} from "./components/aadhaar/cameraHelpers";
import { swapItems, validateLogoFile } from "./components/template/templateHelpers";
import { TemplatePreview } from "./components/template/TemplatePreview";
import api from "./lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("./context/AuthContext", () => ({
  useAuth: () => ({ user: { id: "lead-1", role: "team_lead" } }),
}));

jest.mock("./lib/api", () => {
  const actual = jest.requireActual("./lib/api");
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
    },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

jest.mock("./components/Layout", () => {
  return function MockLayout({ children }) {
    return <div data-testid="mock-layout">{children}</div>;
  };
});

jest.mock("./components/AadhaarScanner", () => {
  return function MockAadhaarScanner({ onScanned, onFailure, onScanStall }) {
    return (
      <div data-testid="mock-aadhaar-scanner">
        <button
          type="button"
          data-testid="mock-scan-trigger"
          onClick={() =>
            onScanned(
              {
                full_name: "Aadhaar Scanned User",
                age: 42,
                gender: "M",
                address: "10 Downing St, Kolkata",
                aadhaar_last4: "8888",
                dob: "1984-05-12",
              },
              "AADHAAR|Aadhaar Scanned User|M|1984-05-12|8888|10 Downing St, Kolkata"
            )
          }
        >
          Simulate Scan
        </button>
        <button
          type="button"
          data-testid="mock-failure-trigger"
          onClick={() => onFailure && onFailure("garbage")}
        >
          Simulate Failure
        </button>
        <button
          type="button"
          data-testid="mock-stall-trigger"
          onClick={() => {
            onFailure && onFailure("error");
            onScanStall && onScanStall();
          }}
        >
          Simulate Scan stall
        </button>
      </div>
    );
  };
});

let container = null;
let root = null;

beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
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

describe("CHALLENGE 1: FulfilmentStation & FulfilmentSection Patient Switch State Sync", () => {
  test("1.1: Switching patient with existing fulfilment resets status and day selections", async () => {
    const patient1Data = {
      transcription: { id: "tx-1" },
      registration: { id: "reg-1" },
      fulfilments: [
        { item_type: "ot", status: "deferred", ot_schedule_day_id: "day-1" },
      ],
    };

    const otDays = [
      { id: "day-1", day_date: "2026-09-02", venue: "OT Room A", seats_free: 5 },
      { id: "day-2", day_date: "2026-09-03", venue: "OT Room B", seats_free: 2 }
    ];

    await act(async () => {
      root.render(
        <FulfilmentStation
          line="ot"
          data={patient1Data}
          otDays={otDays}
          onDone={jest.fn()}
          navigate={jest.fn()}
          setBanner={jest.fn()}
          setError={jest.fn()}
        />
      );
    });

    expect(container.querySelector('[data-testid="station-ot-recorded"]').textContent).toBe("IOL surgery scheduled");
    expect(container.querySelector('[data-testid="station-ot-print-token"]')).toBeNull();

    const patient2Data = {
      transcription: { id: "tx-2" },
      registration: { id: "reg-2" },
      fulfilments: [
        { item_type: "ot", status: "declined" }
      ],
    };

    await act(async () => {
      root.render(
        <FulfilmentStation
          line="ot"
          data={patient2Data}
          otDays={otDays}
          onDone={jest.fn()}
          navigate={jest.fn()}
          setBanner={jest.fn()}
          setError={jest.fn()}
        />
      );
    });

    expect(container.querySelector('[data-testid="station-ot-recorded"]').textContent).toBe("Surgery declined");
    expect(container.querySelector('[data-testid="ot_schedule_day_id-select"]')).toBeNull();
  });

  test("1.2: Unsaved dropdown selection on Patient 1 is NOT retained when switching to Patient 2 with existing record", async () => {
    const patient1Data = {
      transcription: { id: "tx-1" },
      registration: { id: "reg-1" },
      fulfilments: [],
    };

    const otDays = [
      { id: "day-1", day_date: "2026-09-02", venue: "Bajaj Hospital", seats_free: 5 },
      { id: "day-2", day_date: "2026-09-03", venue: "Bajaj Hospital", seats_free: 5 },
    ];

    await act(async () => {
      root.render(
        <FulfilmentStation
          line="ot"
          data={patient1Data}
          otDays={otDays}
          onDone={jest.fn()}
          navigate={jest.fn()}
          setBanner={jest.fn()}
          setError={jest.fn()}
        />
      );
    });

    expect(container.querySelector('[data-testid="station-ot-fulfilled"]')).toBeNull();
    await act(async () => {
      const picker = container.querySelector('[data-testid="ot_schedule_day_id-select"]');
      picker.value = "day-2";
      picker.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.querySelector('[data-testid="ot_schedule_day_id-select"]').value).toBe("day-2");

    const patient2Data = {
      transcription: { id: "tx-2" },
      registration: { id: "reg-2" },
      fulfilments: [{ item_type: "ot", status: "deferred", ot_schedule_day_id: "day-1" }],
    };

    await act(async () => {
      root.render(
        <FulfilmentStation
          line="ot"
          data={patient2Data}
          otDays={otDays}
          onDone={jest.fn()}
          navigate={jest.fn()}
          setBanner={jest.fn()}
          setError={jest.fn()}
        />
      );
    });

    expect(container.querySelector('[data-testid="station-ot-recorded"]').textContent).toBe("IOL surgery scheduled");
    expect(container.querySelector('[data-testid="ot_schedule_day_id-select"]')).toBeNull();
  });

  test("1.3: FulfilmentSection properly keys FulfilmentStation so patient switches cleanly reset station state even if both have empty fulfilments", async () => {
    const patient1Data = {
      transcription: { id: "tx-1" },
      registration: { id: "reg-1" },
      fulfilments: [],
    };

    await act(async () => {
      root.render(
        <FulfilmentSection
          line="medicine"
          data={patient1Data}
          otDays={[]}
          specsDays={[]}
          onDone={jest.fn()}
          navigate={jest.fn()}
          setBanner={jest.fn()}
          setError={jest.fn()}
        />
      );
    });

    expect(container.querySelector('[data-testid="station-medicine-save"]')).not.toBeNull();

    const patient2Data = {
      transcription: { id: "tx-2" },
      registration: { id: "reg-2" },
      fulfilments: [{ item_type: "medicine", status: "not_available" }],
    };

    await act(async () => {
      root.render(
        <FulfilmentSection
          line="medicine"
          data={patient2Data}
          otDays={[]}
          specsDays={[]}
          onDone={jest.fn()}
          navigate={jest.fn()}
          setBanner={jest.fn()}
          setError={jest.fn()}
        />
      );
    });

    expect(container.querySelector('[data-testid="station-medicine-recorded"]').textContent).toContain("not available");
  });

  test("1.4: Save sends the active patient's transcription_id and correct item parameters", async () => {
    const patientData = {
      transcription: { id: "tx-specs-99", specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" } },
      registration: { id: "reg-99" },
      fulfilments: [],
    };

    const specsDays = [
      { id: "sp-day-1", day_date: "2026-09-05", venue: "Specs Counter", start_time: "09:00", end_time: "17:00" }
    ];

    const onDoneMock = jest.fn();
    const setBannerMock = jest.fn();

    api.post.mockResolvedValueOnce({
      data: { fulfilment: { id: "f-1" } }
    });

    await act(async () => {
      root.render(
        <FulfilmentStation
          line="specs_made"
          data={patientData}
          specsDays={specsDays}
          onDone={onDoneMock}
          navigate={jest.fn()}
          setBanner={setBannerMock}
          setError={jest.fn()}
        />
      );
    });

    const specsDaySelect = container.querySelector('[data-testid="specs_collection_day_id-select"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
      setter.call(specsDaySelect, "sp-day-1");
      specsDaySelect.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const saveBtn = container.querySelector('[data-testid="station-specs_made-save"]');
    await act(async () => {
      container.querySelector('[data-testid="station-specs_made-paper-review"]').click();
      saveBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/clinical/fulfilment", expect.objectContaining({
      transcription_id: "tx-specs-99",
      item_type: "specs_made",
      status: "deferred",
      specs_collection_day_id: "sp-day-1",
      paper_reviewed: true,
    }));
    expect(onDoneMock).toHaveBeenCalled();
  });
});

describe("CHALLENGE 2: Desk.js Form Persistence vs Modal Lifecycle", () => {
  beforeEach(() => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 10, seen: 5, pending: 5 } });
      if (url === "/patients") return Promise.resolve({ data: { patients: [] } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Camp 1" },
            days: [
              { id: "day-1", day_date: "2026-09-01", is_today: true },
              { id: "day-2", day_date: "2026-09-02", is_today: false },
            ],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  test("2.1: Reopening RegisterModal cleanly resets previous manual form inputs and state", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    // 1st open
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });

    act(() => {
      const stall = () => [...document.body.querySelectorAll('[data-testid="mock-stall-trigger"]')].pop();
      stall().click(); stall().click(); stall().click();
    });
    act(() => { [...document.body.querySelectorAll('[data-testid="reg-manual-toggle"]')].pop().click(); });

    const nameInput = document.body.querySelector('[data-testid="reg-fullname-input"]');
    const phoneInput = document.body.querySelector('[data-testid="reg-phone-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(nameInput, "Patient One");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(phoneInput, "9876543210");
      phoneInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(nameInput.value).toBe("Patient One");
    expect(phoneInput.value).toBe("9876543210");

    // Close modal
    const discard = jest.spyOn(window, "confirm").mockReturnValue(true);
    act(() => {
      document.body.querySelector('[data-testid="modal-close-button"]').click();
    });
    expect(discard).toHaveBeenCalledWith("Discard changes?");
    discard.mockRestore();

    // 2nd open
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });

    // Manual form should be closed (failures reset to 0)
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();

    act(() => {
      const stall = () => [...document.body.querySelectorAll('[data-testid="mock-stall-trigger"]')].pop();
      stall().click(); stall().click(); stall().click();
    });
    act(() => { [...document.body.querySelectorAll('[data-testid="reg-manual-toggle"]')].pop().click(); });

    const reopenedNameInput = document.body.querySelector('[data-testid="reg-fullname-input"]');
    const reopenedPhoneInput = document.body.querySelector('[data-testid="reg-phone-input"]');
    expect(reopenedNameInput.value).toBe("");
    expect(reopenedPhoneInput.value).toBe("");
  });

  test("2.2: Generates a fresh registration_request_id on each new modal open for idempotency", async () => {
    let capturedReqIds = [];
    api.post.mockImplementation((url, body) => {
      if (url === "/register") {
        capturedReqIds.push(body.registration_request_id);
        return Promise.resolve({
          data: { registration: { id: "r-1", reg_no: "101", full_name: body.full_name } }
        });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    // Registration 1
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
      [...document.body.querySelectorAll('[data-testid="mock-scan-trigger"]')].pop().click();
    });
    act(() => {
      const phoneInput = document.body.querySelector('[data-testid="reg-phone-input"]');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(phoneInput, "9000000001");
      phoneInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    // Registration 2
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
      [...document.body.querySelectorAll('[data-testid="mock-scan-trigger"]')].pop().click();
    });
    act(() => {
      const phoneInput = document.body.querySelector('[data-testid="reg-phone-input"]');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(phoneInput, "9000000002");
      phoneInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    expect(capturedReqIds.length).toBe(2);
    expect(capturedReqIds[0]).toBeTruthy();
    expect(capturedReqIds[1]).toBeTruthy();
    expect(capturedReqIds[0]).not.toBe(capturedReqIds[1]);
  });

  test("2.3: Form stays intact and error is displayed when backend returns 409 Duplicate", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/register") {
        const err = new Error("Duplicate");
        err.response = {
          data: {
            detail: {
              code: "DUPLICATE_IN_CAMP",
              registration: { reg_no: 77, full_name: "Existing Person" }
            }
          }
        };
        return Promise.reject(err);
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
      [...document.body.querySelectorAll('[data-testid="mock-scan-trigger"]')].pop().click();
    });
    const phoneInput = document.body.querySelector('[data-testid="reg-phone-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(phoneInput, "9123456789");
      phoneInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    // Error shown
    expect(document.body.textContent).toContain("Already registered as #77");
    // Form still present with phone intact
    expect(phoneInput.value).toBe("9123456789");
  });

  test("2.4: Desk background data refresh does not erase active in-progress form inputs", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });

    act(() => {
      const stall = () => [...document.body.querySelectorAll('[data-testid="mock-stall-trigger"]')].pop();
      stall().click(); stall().click(); stall().click();
    });
    act(() => { [...document.body.querySelectorAll('[data-testid="reg-manual-toggle"]')].pop().click(); });

    const nameInput = document.body.querySelector('[data-testid="reg-fullname-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(nameInput, "In-Progress Name");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    // Simulate background re-render
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    const currentNameInput = document.body.querySelector('[data-testid="reg-fullname-input"]');
    expect(currentNameInput.value).toBe("In-Progress Name");
  });
});

describe("CHALLENGE 3: Camera Fallback and Torch Toggling in useAadhaarCamera", () => {
  let mockTrack;
  let mockStream;

  beforeEach(() => {
    mockTrack = {
      stop: jest.fn(),
      getCapabilities: jest.fn().mockReturnValue({ torch: true }),
      applyConstraints: jest.fn().mockResolvedValue(),
      getSettings: jest.fn().mockReturnValue({ width: 1280, height: 720 }),
    };
    mockStream = {
      getTracks: () => [mockTrack],
      getVideoTracks: () => [mockTrack],
    };
    navigator.mediaDevices = {
      getUserMedia: jest.fn().mockResolvedValue(mockStream),
      enumerateDevices: jest.fn().mockResolvedValue([{ kind: "videoinput", deviceId: "cam-back", label: "Rear Cam" }]),
    };
  });

  test("3.1: the ladder asks for 1080p with continuous focus first, then weakens", () => {
    const attemptsWithDevice = buildCameraConstraintAttempts("custom-device-id");
    expect(attemptsWithDevice.length).toBe(7);
    expect(attemptsWithDevice[0].video.deviceId.exact).toBe("custom-device-id");
    expect(attemptsWithDevice[0].video.width).toEqual({ ideal: 1920 });
    expect(attemptsWithDevice[0].video.height).toEqual({ ideal: 1080 });
    expect(attemptsWithDevice[0].video.focusMode).toEqual({ ideal: "continuous" });
    expect(attemptsWithDevice[1].video.width).toEqual({ ideal: 1280 });
    expect(attemptsWithDevice[2].video.facingMode.ideal).toBe("environment");
    expect(attemptsWithDevice[2].video.height).toEqual({ ideal: 1080 });
    expect(attemptsWithDevice[4].video.facingMode).toBe("environment");
    expect(attemptsWithDevice[5].video.facingMode).toBe("user");
    expect(attemptsWithDevice[6].video).toBe(true);

    const attemptsNoDevice = buildCameraConstraintAttempts(undefined);
    expect(attemptsNoDevice.length).toBe(5);
    expect(attemptsNoDevice[0].video.facingMode.ideal).toBe("environment");
    expect(attemptsNoDevice[0].video.height).toEqual({ ideal: 1080 });
  });

  test("3.2: acquireCameraStream succeeds on fallback attempts when initial attempts fail", async () => {
    navigator.mediaDevices.getUserMedia
      .mockRejectedValueOnce(new Error("Overconstrained deviceId"))
      .mockRejectedValueOnce(new Error("Overconstrained ideal 720p"))
      .mockResolvedValueOnce(mockStream);

    const stream = await acquireCameraStream("custom-device-id");
    expect(stream).toBe(mockStream);
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(3);
  });

  test("3.3: acquireCameraStream throws last error when all fallback attempts fail", async () => {
    const finalErr = new Error("Device busy");
    navigator.mediaDevices.getUserMedia.mockRejectedValue(finalErr);

    await expect(acquireCameraStream("cam-1")).rejects.toThrow("Device busy");
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(7);
  });

  test("3.4: checkTorchCapability detects torch support accurately", () => {
    expect(checkTorchCapability(mockStream)).toBe(true);

    const streamNoTorch = {
      getVideoTracks: () => [{ getCapabilities: () => ({}) }]
    };
    expect(checkTorchCapability(streamNoTorch)).toBe(false);

    expect(checkTorchCapability(null)).toBe(false);
  });

  test("3.5: applyTorch applies constraints safely", async () => {
    await applyTorch(mockStream, true);
    expect(mockTrack.applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] });

    await applyTorch(mockStream, false);
    expect(mockTrack.applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: false }] });
  });

  test("3.6: cameraErrorMessage formats standard WebRTC camera errors correctly", () => {
    expect(cameraErrorMessage({ name: "NotAllowedError" })).toContain("Camera permission is off");
    expect(cameraErrorMessage({ name: "NotFoundError" })).toContain("No camera found");
    expect(cameraErrorMessage({ name: "NotReadableError" })).toContain("Camera is currently busy");
    expect(cameraErrorMessage(new Error("random error"))).toContain("Unable to start camera");
  });
});

describe("CHALLENGE 4: Prescription lockdown and logo validation", () => {
  test("4.1: swapItems correctly reorders array items and guards boundary conditions", () => {
    const list = ["A", "B", "C", "D"];

    // Top boundary (index 0, -1)
    expect(swapItems(list, 0, -1)).toEqual(["A", "B", "C", "D"]);

    // Bottom boundary (index 3, +1)
    expect(swapItems(list, 3, 1)).toEqual(["A", "B", "C", "D"]);

    // Swap middle down (B down)
    const swappedDown = swapItems(list, 1, 1);
    expect(swappedDown).toEqual(["A", "C", "B", "D"]);

    // Swap middle up (C up)
    const swappedUp = swapItems(swappedDown, 1, -1);
    expect(swappedUp).toEqual(["C", "A", "B", "D"]);

    // Immutability: original list unchanged
    expect(list).toEqual(["A", "B", "C", "D"]);
  });

  test("4.2: the prescription layout is fixed and cannot be reordered from the UI", () => {
    const sampleRx = {
      reg_no: 101, full_name: "Sample Patient", date: "2026-09-01", age: 52, gender: "M",
      phone: "9876543210", address: "12 MG Road", patient_qr: "qr-123",
      camp_name: "Kolkata Eye Camp", venue: "Rotary Club",
    };

    act(() => {
      root.render(<TemplatePreview sampleRx={sampleRx} logos={[]} />);
    });

    expect(container.querySelector('[data-testid="tpl-blocks-editor"]')).toBeNull();
    const blockIds = [...container.querySelectorAll("[data-testid^=\"rx-block-\"]")].map(
      (el) => el.getAttribute("data-testid")
    );
    expect(blockIds).toEqual([
      "rx-block-identity",
    ]);
    expect(container.querySelector('[data-testid="rx-diagnosis-row"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="rx-glasses-box"]')).not.toBeNull();
  });

  test("4.3: the sheet carries the trust letterhead and footer regardless of stored data", () => {
    const sampleRx = {
      reg_no: 101, full_name: "Sample Patient", date: "2026-09-01", age: 52, gender: "M",
      phone: "9876543210", address: "12 MG Road", patient_qr: "qr-123",
      camp_name: "Kolkata Eye Camp", venue: "Rotary Club",
    };
    const logos = [{ id: "logo-1", name: "logo.png", data_url: "data:image/png;base64,aaa" }];

    act(() => {
      root.render(<TemplatePreview sampleRx={sampleRx} logos={logos} />);
    });

    const sheet = container.querySelector('[data-testid="a4-prescription-sheet"]');
    expect(sheet).not.toBeNull();
    expect(sheet.textContent).toContain("SIKAR NAGARIK PARISHAD (KOLKATA)");
    expect(sheet.textContent).toContain("sikarkolkata@gmail.com");
    expect(sheet.textContent).toContain("Sponsorer :");
    expect(sheet.textContent).toContain("ARRANGMENT");
    expect(container.querySelectorAll("img").length).toBeGreaterThan(1);
  });

  test("4.4: validateLogoFile enforces size <= 2MB and allowed image MIME types", () => {
    const validPng = { size: 1.5 * 1024 * 1024, type: "image/png" };
    expect(validateLogoFile(validPng)).toEqual({ valid: true, error: "" });

    const validJpg = { size: 500 * 1024, type: "image/jpeg" };
    expect(validateLogoFile(validJpg)).toEqual({ valid: true, error: "" });

    const oversized = { size: 3 * 1024 * 1024, type: "image/png" };
    expect(validateLogoFile(oversized)).toEqual({
      valid: false,
      error: "Logo must be 2 MB or smaller."
    });

    const invalidType = { size: 100 * 1024, type: "image/gif" };
    expect(validateLogoFile(invalidType)).toEqual({
      valid: false,
      error: "Use PNG, JPEG or WebP."
    });
  });
});
