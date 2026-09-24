import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Clinical from "./Clinical";
import api from "../lib/api";
import { LINE_STORAGE_KEY } from "../lib/operatorLines";
import * as nativeDetector from "../components/aadhaar/liveScan/nativeDetector";
import * as grab from "../components/aadhaar/liveScan/grabFrame";
import * as wasmDetector from "../components/aadhaar/liveScan/wasmDetector";

global.IS_REACT_ACT_ENVIRONMENT = true;

const auth = {
  user: { id: "u1", name: "Op", role: "clinical_desk_operator", line: "rx" },
};

jest.mock("../context/AuthContext", () => ({
  useAuth: () => auth,
}));

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
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

jest.mock("../components/Layout", () => {
  return function MockLayout({ children }) {
    return <div data-testid="mock-layout">{children}</div>;
  };
});

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem("snp.roster", JSON.stringify({ id: "r-1", name: "Op" }));
  sessionStorage.setItem(LINE_STORAGE_KEY, "medicine");
  auth.user = { id: "u1", name: "Op", role: "clinical_desk_operator", line: "rx" };

  api.get.mockImplementation((url) => {
    if (url === "/clinical/diagnosis-options") {
      return Promise.resolve({ data: { options: ["Cataract", "Refractive Error", "Glaucoma"] } });
    }
    if (url === "/clinical/ot-days") {
      return Promise.resolve({
        data: {
          ot_days: [
            { id: "ot-1", day_date: "2026-09-01", venue: "Base Hospital", seats_free: 5 },
          ],
        },
      });
    }
    if (url === "/clinical/specs-days") {
      return Promise.resolve({
        data: {
          specs_days: [
            { id: "sp-1", day_date: "2026-09-12", venue: "Base Optical" },
          ],
        },
      });
    }
    return Promise.resolve({ data: {} });
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
  jest.restoreAllMocks();
});

const renderPage = () => act(async () => root.render(<MemoryRouter><Clinical /></MemoryRouter>));

const typeLookup = (value) => act(() => {
  const input = container.querySelector('[data-testid="clinical-lookup-input"]');
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
});

const submitLookup = () => act(async () => container.querySelector('[data-testid="clinical-lookup-button"]').click());

const patientFound = (id, name) => ({ data: {
  registration: { id, reg_no: id, full_name: name }, person: { id }, transcription: null, fulfilments: [], slips: [],
} });

async function scanWithCamera(payload) {
  const track = { stop: jest.fn(), getSettings: () => ({}) };
  const stream = { getTracks: () => [track], getVideoTracks: () => [track] };
  navigator.mediaDevices = {
    getUserMedia: jest.fn().mockResolvedValue(stream),
    enumerateDevices: jest.fn().mockResolvedValue([]),
  };
  Object.defineProperty(window.HTMLMediaElement.prototype, "play", { configurable: true, value: jest.fn().mockResolvedValue() });
  Object.defineProperty(window.HTMLMediaElement.prototype, "pause", { configurable: true, value: jest.fn() });
  Object.defineProperty(window.HTMLVideoElement.prototype, "videoWidth", { configurable: true, get: () => 1280 });
  jest.spyOn(grab, "grabFrame").mockReturnValue({ width: 4, height: 4, data: new Uint8ClampedArray(64) });
  jest.spyOn(nativeDetector, "hasNativeBarcodeDetector").mockReturnValue(true);
  jest.spyOn(nativeDetector, "loadNativeDetector").mockResolvedValue({});
  jest.spyOn(nativeDetector, "detectNative").mockResolvedValueOnce(payload).mockResolvedValue(null);
  jest.spyOn(wasmDetector, "loadZxingWorker").mockResolvedValue();
  jest.spyOn(wasmDetector, "detectWasmImageData").mockResolvedValue(null);
  await act(async () => container.querySelector('[data-testid="aadhaar-camera-button"]').click());
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
  return track;
}

describe("Clinical find", () => {
  test("one field labelled for a registration number or name states the arrived-and-printed rule", async () => {
    await renderPage();
    expect(container.querySelector('[data-testid="clinical-lookup-input"]').getAttribute("aria-label")).toBe("Registration number or name");
    expect(container.textContent).toContain("arrived");
    expect(container.textContent).toContain("printed");
    expect(container.textContent).not.toContain("marked Seen");
  });

  test.each([
    ["1001", "lookup"],
    ["SNP:AB3K7T29", "lookup"],
    ["snp:ab3k7t29", "lookup"],
    ["Sunita Devi", "search"],
    ["12 Sunita", "search"],
  ])("%s goes to the %s", async (value, route) => {
    if (route === "lookup") api.post.mockResolvedValueOnce(patientFound("1001", "Found Patient"));
    await renderPage();
    typeLookup(value);
    await submitLookup();
    if (route === "lookup") {
      expect(api.post).toHaveBeenCalledWith("/clinical/lookup", { value });
      expect(api.get).not.toHaveBeenCalledWith(expect.stringMatching(/^\/clinical\/search/));
    } else {
      expect(api.get).toHaveBeenCalledWith(`/clinical/search?q=${encodeURIComponent(value)}`);
      expect(api.post).not.toHaveBeenCalled();
    }
  });

  test("a name lists matching patients and tapping one opens it as a scan would", async () => {
    const loadGet = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url.startsWith("/clinical/search")
      ? Promise.resolve({ data: { results: [
        { id: "r-7", reg_no: 1007, full_name: "Sunita Devi", age: 51, gender_label: "Female", phone_last4: "4321" },
      ] } })
      : loadGet(url)));
    api.post.mockResolvedValueOnce(patientFound("r-7", "Sunita Devi"));
    await renderPage();
    typeLookup("Sunita");
    await submitLookup();
    const results = container.querySelector('[data-testid="clinical-search-results"]');
    for (const text of ["#1007", "Sunita Devi", "51", "Female", "4321"]) expect(results.textContent).toContain(text);
    expect(api.post).not.toHaveBeenCalled();
    await act(async () => container.querySelector('[data-testid="clinical-search-result-r-7"]').click());
    expect(api.post).toHaveBeenCalledWith("/clinical/lookup", { value: "1007" });
    expect(container.querySelector('[data-testid="clinical-search-results"]')).toBeNull();
    expect(container.querySelector('[data-testid="clinical-prescription-form"]')).not.toBeNull();
  });

  test("a USB scan of a Patient code opens the patient without pressing the focused button", async () => {
    let now = 0;
    jest.spyOn(performance, "now").mockImplementation(() => now);
    api.post
      .mockResolvedValueOnce(patientFound("1001", "First Patient"))
      .mockResolvedValueOnce(patientFound("1002", "Scanned Patient"));
    await renderPage();
    typeLookup("1001");
    await submitLookup();
    container.querySelector('[data-testid="wizard-next"]').focus();
    await act(async () => {
      for (const key of [..."SNP:AB3K7T29", "Enter"]) {
        now += 10;
        const target = document.activeElement;
        const keydown = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
        target.dispatchEvent(keydown);
        if (key === "Enter" && !keydown.defaultPrevented) target.click();
      }
    });
    expect(api.post).not.toHaveBeenCalledWith("/clinical/transcription", expect.anything());
    expect(api.post).toHaveBeenLastCalledWith("/clinical/lookup", { value: "SNP:AB3K7T29" });
    expect(container.textContent).toContain("Scanned Patient");
  });

  test("a USB scan while a correction is open does not switch patients", async () => {
    let now = 0;
    jest.spyOn(performance, "now").mockImplementation(() => now);
    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-7", reg_no: 7, full_name: "Corrected Patient", queue_status: "seen" },
      person: { id: "p-7" },
      transcription: { id: "tx-7", locked: true, diagnosis_options: ["Cataract"] },
      committed_revision: { id: "rev-7", prescribed_lines: ["medicine"] },
      clinical_generation: 1,
      fulfilments: [],
      slips: [],
    } });
    await renderPage();
    typeLookup("7");
    await submitLookup();
    await act(async () => container.querySelector('[data-testid="add-correction-button"]').click());
    expect(document.querySelector('[data-testid="correction-form"]')).not.toBeNull();
    await act(async () => {
      for (const key of [..."SNP:AB3K7T29", "Enter"]) {
        now += 10;
        document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
      }
    });
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Corrected Patient");
  });

  test("the camera opens a patient from the prescription QR and then closes", async () => {
    api.post.mockResolvedValueOnce(patientFound("1002", "Camera Patient"));
    await renderPage();
    const track = await scanWithCamera("SNP:AB3K7T29");
    expect(api.post).toHaveBeenCalledWith("/clinical/lookup", { value: "SNP:AB3K7T29" });
    expect(container.textContent).toContain("Camera Patient");
    expect(track.stop).toHaveBeenCalled();
    expect(container.querySelector('[data-testid="aadhaar-camera-stop"]')).toBeNull();
  });

  test("the camera refuses an Aadhaar QR and never decodes it", async () => {
    await renderPage();
    const track = await scanWithCamera("2567820190301120000");
    expect(container.textContent).toContain("Scan the QR on the prescription");
    expect(api.post).not.toHaveBeenCalled();
    expect(track.stop).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="aadhaar-upload-button"]')).toBeNull();
    expect(container.querySelector('[data-testid="aadhaar-manual-toggle"]')).toBeNull();
  });
});

describe("Clinical page component", () => {
  test("keeps the current wizard step until its draft saves and permits retry after failure", async () => {
    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-save", reg_no: "1001", full_name: "Draft Patient", queue_status: "arrived" },
      person: { id: "person-save" }, transcription: null, fulfilments: [], slips: [],
    } });
    await act(async () => { root.render(<MemoryRouter><Clinical /></MemoryRouter>); });
    act(() => {
      const input = container.querySelector('[data-testid="clinical-lookup-input"]');
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, "1001");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { container.querySelector('[data-testid="clinical-lookup-button"]').click(); });
    await act(async () => container.querySelector('[data-testid="diagnosis-opt-cataract"]').click());
    let reject;
    api.post.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
    await act(async () => { container.querySelector('[data-testid="wizard-next"]').click(); });
    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 1 of");
    expect(container.querySelector('[data-testid="wizard-next"]').disabled).toBe(true);
    expect(container.querySelector('[data-testid="clinical-lookup-button"]').disabled).toBe(true);
    await act(async () => { reject(new Error("Draft save failed")); });
    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 1 of");
    expect(container.textContent).toContain("Draft save failed");
    expect(container.querySelector('[data-testid="wizard-next"]').disabled).toBe(false);
    api.post.mockResolvedValueOnce({ data: { transcription: { id: "tx-save" } } });
    await act(async () => { container.querySelector('[data-testid="wizard-next"]').click(); });
    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 2 of");
    expect(container.textContent).not.toContain("Draft save failed");
  });

  test("renders lookup form and handles initial diagnosis options and OT days load", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Clinical />
        </MemoryRouter>
      );
    });

    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    const lookupBtn = container.querySelector('[data-testid="clinical-lookup-button"]');
    expect(lookupInput).not.toBeNull();
    expect(lookupBtn).not.toBeNull();
  });

  test("handles lookup success and renders patient card, prescription form, and fulfilment stations", async () => {
    const mockLookupData = {
      registration: {
        id: "reg-101",
        reg_no: "1001",
        full_name: "Subhash Bose",
        gender_label: "Male",
        age: 58,
        queue_status: "seen",
      },
      person: { id: "p-101" },
      transcription: {
        id: "tx-101",
        locked: false,
        diagnosis_options: ["Cataract"],
        diagnosis_other: "Early stage",
        bp: "130/85",
        blood_sugar: "110",
        remarks: "Fit for surgery",
        specs_measurements: {
          r_sph: "-1.5",
          r_cyl: "",
          r_axis: "",
          l_sph: "-1.0",
          l_cyl: "",
          l_axis: "",
          add: "+2.0",
        },
        ot_eye: "R",
        ot_outcome: "iol_surgery",
      },
      fulfilments: [
        { item_type: "medicine", status: "fulfilled" },
      ],
      slips: [],
    };

    api.post.mockResolvedValueOnce({ data: mockLookupData });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Clinical />
        </MemoryRouter>
      );
    });

    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value"
      ).set;
      nativeSetter.call(lookupInput, "1001");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const lookupBtn = container.querySelector('[data-testid="clinical-lookup-button"]');
    await act(async () => {
      lookupBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/clinical/lookup", { value: "1001" });
    expect(container.textContent).toContain("#1001");
    expect(container.textContent).toContain("Subhash Bose");

    await act(async () => container.querySelector('[data-testid="edit-transcription-button"]').click());
    const rxForm = container.querySelector('[data-testid="clinical-prescription-form"]');
    expect(rxForm).not.toBeNull();

    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 1 of");
    expect(container.querySelector('[data-testid="diagnosis-other-input"]').value).toBe("Early stage");
    expect(container.querySelector('[data-testid="specs-r_sph"]')).toBeNull();
    expect(container.querySelector('[data-testid="ot-eye-select"]')).toBeNull();

    const medicineStation = container.querySelector('[data-testid="station-medicine"]');
    expect(medicineStation).toBeNull();
    expect(container.querySelector('[data-testid="fulfilment-section"]')).toBeNull();
    expect(container.textContent).toContain("Save the prescription before issuing");
  });

  test("a line desk renders one control and a read-only prescription", async () => {
    auth.user.line = "medicine";
    const mockLookupData = {
      registration: { id: "reg-101", reg_no: "1001", full_name: "Subhash Bose", gender_label: "Male", age: 58, queue_status: "seen" },
      person: { id: "p-101" },
      transcription: {
        id: "tx-101", locked: true, diagnosis_options: ["Cataract"],
        specs_measurements: { r_sph: "-1.5", l_sph: "-1.0" },
      },
      committed_revision: { id: "rev-101" },
      clinical_generation: 1,
      fulfilments: [],
      slips: [],
    };
    api.post.mockResolvedValueOnce({ data: mockLookupData });
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      nativeSetter.call(lookupInput, "1001");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector('[data-testid="clinical-lookup-button"]').click();
    });
    expect(container.querySelector('[data-testid="clinical-prescription-form"]')).toBeNull();
    expect(container.querySelector('[data-testid="readonly-prescription"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-medicine"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-ot"]')).toBeNull();
    expect(container.querySelector('[data-testid="station-medicine-save"]')).not.toBeNull();
  });

  test("the line picker appears when there is no line", async () => {
    auth.user.line = null;
    sessionStorage.removeItem(LINE_STORAGE_KEY);
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-picker"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="clinical-lookup-input"]')).toBeNull();
  });

  test("a chosen line survives remount and a fresh session asks the operator", async () => {
    sessionStorage.setItem(LINE_STORAGE_KEY, "ot");
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("Hospital");

    act(() => { root.unmount(); });
    root = ReactDOM.createRoot(container);
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("Hospital");

    sessionStorage.clear();
    auth.user.line = "medicine";
    act(() => { root.unmount(); });
    root = ReactDOM.createRoot(container);
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-picker"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="pick-line-rx"]')).toBeNull();
  });

  test("a mismatch is advisory and the control stays usable", async () => {
    auth.user.line = "ot";
    sessionStorage.setItem(LINE_STORAGE_KEY, "ot");
    api.post.mockResolvedValueOnce({
      data: {
        registration: { id: "reg-101", reg_no: "1001", full_name: "Subhash Bose", gender_label: "Male", age: 58 },
        person: { id: "p-101" },
        transcription: { id: "tx-101", locked: true, diagnosis_options: ["Cataract"], specs_measurements: { r_sph: "-1", l_sph: "-1" } },
        committed_revision: { id: "rev-101", prescribed_lines: ["medicine", "specs_fixed"] },
        clinical_generation: 1,
        fulfilments: [],
        slips: [],
      },
    });
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      nativeSetter.call(lookupInput, "1001");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector('[data-testid="clinical-lookup-button"]').click();
    });
    expect(container.querySelector('[data-testid="line-mismatch-warning"]').textContent).toContain("Record anyway");
    expect(container.querySelector('[data-testid="station-ot-fulfilled"]')).toBeNull();
    expect(container.querySelector('[data-testid="station-ot-save"]').disabled).toBe(true);
    await act(async () => {
      container.querySelector('[data-testid="station-ot-paper-review"]').click();
    });
    expect(container.querySelector('[data-testid="station-ot-save"]').disabled).toBe(false);
  });

  test("operators transcribe a patient at their own line", async () => {
    auth.user.line = "medicine";
    api.post.mockResolvedValueOnce({
      data: {
        registration: { id: "reg-101", reg_no: "1001", full_name: "Subhash Bose", gender_label: "Male", age: 58 },
        person: { id: "p-101" },
        transcription: null,
        fulfilments: [],
        slips: [],
      },
    });
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      nativeSetter.call(lookupInput, "1001");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector('[data-testid="clinical-lookup-button"]').click();
    });
    expect(container.querySelector('[data-testid="send-to-rx"]')).toBeNull();
    expect(container.querySelector('[data-testid="clinical-prescription-form"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-medicine"]')).toBeNull();
  });

  test("handles lookup failure gracefully", async () => {
    api.post.mockRejectedValueOnce({
      response: { data: { detail: "Patient not found or not marked seen" } },
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Clinical />
        </MemoryRouter>
      );
    });

    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value"
      ).set;
      nativeSetter.call(lookupInput, "9999");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const lookupBtn = container.querySelector('[data-testid="clinical-lookup-button"]');
    await act(async () => {
      lookupBtn.click();
    });

    expect(container.textContent).toContain("Patient not found or not marked seen");
  });

  test("a slow previous lookup cannot replace the current patient", async () => {
    let firstResolve;
    let secondResolve;
    api.post.mockImplementationOnce(() => new Promise((resolve) => { firstResolve = resolve; }));
    api.post.mockImplementationOnce(() => new Promise((resolve) => { secondResolve = resolve; }));
    await act(async () => root.render(<MemoryRouter><Clinical /></MemoryRouter>));
    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    for (const number of ["1001", "1002"]) {
      act(() => {
        setter.call(lookupInput, number);
        lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await act(async () => container.querySelector('[data-testid="clinical-lookup-button"]').click());
    }
    const patient = (id, name) => ({ data: {
      registration: { id, reg_no: id, full_name: name }, person: { id }, transcription: null, fulfilments: [], slips: [],
    } });
    await act(async () => secondResolve(patient("1002", "Latest patient")));
    await act(async () => firstResolve(patient("1001", "Previous patient")));
    expect(container.textContent).toContain("Latest patient");
    expect(container.textContent).not.toContain("Previous patient");
  });

  test("history from a previous patient cannot open after a new lookup", async () => {
    const patient = (id) => ({ data: {
      registration: { id, reg_no: id, full_name: `Patient ${id}` }, person: { id }, transcription: null, fulfilments: [], slips: [],
    } });
    api.post.mockResolvedValueOnce(patient("1001")).mockResolvedValueOnce(patient("1002"));
    await act(async () => root.render(<MemoryRouter><Clinical /></MemoryRouter>));
    const input = container.querySelector('[data-testid="clinical-lookup-input"]');
    const lookup = async (id) => {
      act(() => {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, id);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await act(async () => container.querySelector('[data-testid="clinical-lookup-button"]').click());
    };
    await lookup("1001");
    let resolveHistory;
    api.get.mockImplementationOnce(() => new Promise((resolve) => { resolveHistory = resolve; }));
    await act(async () => container.querySelector('[data-testid="clinical-history-button"]').click());
    await lookup("1002");
    await act(async () => resolveHistory({ data: { history: [] } }));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(container.textContent).toContain("Patient 1002");
  });

  test("patient and line controls stay disabled while issuing medicine", async () => {
    let resolveIssue;
    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "r1", reg_no: "1001", full_name: "Patient" }, person: { id: "p1" },
      transcription: { id: "tx1", locked: true, diagnosis_options: ["Cataract"] },
      committed_revision: { id: "rev1" },
      clinical_generation: 1,
      fulfilments: [], slips: [],
    } });
    api.post.mockImplementationOnce(() => new Promise((resolve) => { resolveIssue = resolve; }));
    await act(async () => root.render(<MemoryRouter><Clinical /></MemoryRouter>));
    act(() => {
      const node = container.querySelector('[data-testid="clinical-lookup-input"]');
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(node, "1001");
      node.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector('[data-testid="clinical-lookup-button"]').click());
    await act(async () => {
      container.querySelector('[data-testid="station-medicine-paper-review"]')?.click();
      container.querySelector('[data-testid="station-medicine-save"]').click();
    });
    expect(container.querySelector('[data-testid="clinical-lookup-input"]').disabled).toBe(true);
    expect(container.querySelector('[data-testid="line-change-button"]').disabled).toBe(true);
    await act(async () => resolveIssue({ data: { fulfilment: { id: "f1" } } }));
    expect(container.querySelector('[data-testid="clinical-lookup-input"]').disabled).toBe(false);
  });

  test.each([["medicine"], ["specs_fixed"], ["specs_made"], ["ot"]])(
    "%s monitoring starts every operator on the same first step",
    async (line) => {
      sessionStorage.setItem(LINE_STORAGE_KEY, line);
      api.post.mockResolvedValueOnce({ data: {
        registration: { id: "r1", reg_no: "1001", full_name: "Patient" }, person: { id: "p1" }, transcription: null, fulfilments: [], slips: [],
      } });
      await act(async () => root.render(<MemoryRouter><Clinical /></MemoryRouter>));
      act(() => {
        const node = container.querySelector('[data-testid="clinical-lookup-input"]');
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(node, "1001");
        node.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await act(async () => container.querySelector('[data-testid="clinical-lookup-button"]').click());
      expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 1 of 3");
      expect(container.querySelector('[data-testid="diagnosis-options"]')).not.toBeNull();
      expect(document.activeElement).toBe(container.querySelector('[data-testid="diagnosis-opt-cataract"]'));
    },
  );

  test("gracefully falls back when diagnosis options and ot-days API fail", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    api.get.mockRejectedValue(new Error("Network Error"));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Clinical />
        </MemoryRouter>
      );
    });

    expect(warnSpy).toHaveBeenCalledWith(
      "Failed to fetch diagnosis options:",
      expect.any(Error)
    );
    expect(warnSpy).toHaveBeenCalledWith(
      "Failed to fetch OT days:",
      expect.any(Error)
    );
    expect(warnSpy).toHaveBeenCalledWith(
      "Failed to fetch Specs collection days:",
      expect.any(Error)
    );
    warnSpy.mockRestore();
  });

  test("Spectacles to be made assigns a Specs collection day with date, venue and the fixed hours", async () => {
    auth.user.line = "specs_made";
    sessionStorage.setItem(LINE_STORAGE_KEY, "specs_made");
    const mockLookupData = {
      registration: {
        id: "reg-101",
        reg_no: "1001",
        full_name: "Subhash Bose",
        gender_label: "Male",
        age: 58,
        queue_status: "seen",
      },
      person: { id: "p-101" },
      transcription: {
        id: "tx-101", locked: true, diagnosis_options: ["Cataract"],
        specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" },
      },
      committed_revision: { id: "rev-101" },
      clinical_generation: 1,
      fulfilments: [],
      slips: [],
    };
    api.post.mockResolvedValueOnce({ data: mockLookupData });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Clinical />
        </MemoryRouter>
      );
    });

    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value"
      ).set;
      nativeSetter.call(lookupInput, "1001");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector('[data-testid="clinical-lookup-button"]').click();
    });

    const daySelect = container.querySelector('[data-testid="specs_collection_day_id-select"]');
    expect(daySelect).not.toBeNull();
    expect(container.querySelector('[data-testid="specs-collection-date"]')).toBeNull();
    expect(container.querySelector('[data-testid="specs-collection-venue"]')).toBeNull();
    const openOpt = Array.from(daySelect.options).find((o) => o.value === "sp-1");
    expect(openOpt.disabled).toBe(false);
    expect(openOpt.textContent).toContain("Base Optical");
    expect(openOpt.textContent).toContain("10:00 AM–5:00 PM");
  });

  test("advancing a wizard step saves a draft so an interrupted transcription is not lost", async () => {
    jest.useFakeTimers();
    const mockLookupData = {
      registration: {
        id: "reg-101",
        reg_no: "1001",
        full_name: "Subhash Bose",
        gender_label: "Male",
        age: 58,
        queue_status: "seen",
      },
      person: { id: "p-101" },
      transcription: null,
      fulfilments: [],
      slips: [],
    };
    api.post.mockResolvedValueOnce({ data: mockLookupData });
    api.post.mockResolvedValueOnce({ data: { transcription: { id: "tx-1", diagnosis_options: ["Cataract"] } } });
    api.post.mockResolvedValueOnce({ data: { fulfilment: { id: "f-1" } } });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Clinical />
        </MemoryRouter>
      );
    });
    const lookupInput = container.querySelector('[data-testid="clinical-lookup-input"]');
    act(() => {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value"
      ).set;
      nativeSetter.call(lookupInput, "1001");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector('[data-testid="clinical-lookup-button"]').click();
    });
    await act(async () => { jest.runAllTimers(); });
    expect(document.activeElement).toBe(container.querySelector('[data-testid="diagnosis-opt-cataract"]'));
    await act(async () => container.querySelector('[data-testid="diagnosis-opt-cataract"]').click());

    await act(async () => {
      container.querySelector('[data-testid="wizard-next"]').click();
    });
    await act(async () => { jest.runAllTimers(); });
    expect(api.post).toHaveBeenCalledWith(
      "/clinical/transcription",
      expect.objectContaining({ patient_id: "reg-101" }),
    );
    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 2 of");
    expect(container.querySelector('[data-testid="prescribed-lines"]')).not.toBeNull();
    expect(container.textContent).toContain("#1001");
    expect(container.querySelector('[data-testid="station-medicine"]')).toBeNull();
    jest.useRealTimers();
  });
});

describe("Clinical draft version and dirty-draft protection", () => {
  beforeEach(() => api.post.mockReset());

  const draftPatient = (draft_version) => ({ data: {
    registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient", queue_status: "arrived" },
    person: { id: "p-1" },
    transcription: { id: "tx-1", locked: false, draft_version, diagnosis_options: [] },
    fulfilments: [],
    slips: [],
  } });

  const savedDraft = (draft_version) => ({ data: { transcription: { id: "tx-1", draft_version } } });

  const conflictError = { response: { status: 409, data: { detail: {
    code: "DRAFT_VERSION_CONFLICT",
    message: "Another operator saved this prescription; reload before saving.",
  } } } };

  const openDraft = async (version) => {
    api.post.mockResolvedValueOnce(draftPatient(version));
    await renderPage();
    typeLookup("1001");
    await submitLookup();
    await act(async () => container.querySelector('[data-testid="edit-transcription-button"]').click());
  };

  const typeOther = (value) => act(() => {
    const input = container.querySelector('[data-testid="diagnosis-other-input"]');
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });

  const otherValue = () => container.querySelector('[data-testid="diagnosis-other-input"]').value;

  test("the draft save and the completion both carry the loaded draft version", async () => {
    await openDraft(3);
    await act(async () => container.querySelector('[data-testid="diagnosis-opt-cataract"]').click());

    api.post.mockResolvedValueOnce(savedDraft(4));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    expect(api.post).toHaveBeenLastCalledWith(
      "/clinical/transcription",
      expect.objectContaining({ patient_id: "reg-1", expected_draft_version: 3 }),
    );

    await act(async () => container.querySelector('[data-testid="none-prescribed"]').click());
    api.post.mockResolvedValueOnce(savedDraft(5));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    expect(api.post).toHaveBeenLastCalledWith(
      "/clinical/transcription",
      expect.objectContaining({ expected_draft_version: 4 }),
    );

    await act(async () => container.querySelector('[data-testid="full-transcription-confirmed"]').click());
    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient", clinical_generation: 1 },
      revision: { id: "rev-1", prescribed_lines: [] },
      transcription: { id: "tx-1", locked: true, draft_version: 6 },
    } });
    await act(async () => container.querySelector('[data-testid="complete-prescription-button"]').click());
    expect(api.post).toHaveBeenLastCalledWith(
      "/clinical/transcription/complete",
      expect.objectContaining({ expected_draft_version: 5 }),
    );
    expect(container.textContent).toContain("Prescription completed");
  });

  test("a draft version conflict keeps the typed entries and offers review instead of overwriting", async () => {
    await openDraft(2);
    typeOther("Pterygium left eye");
    api.post.mockRejectedValueOnce(conflictError);
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());

    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 1 of");
    expect(otherValue()).toBe("Pterygium left eye");
    expect(container.querySelector('[data-testid="draft-conflict"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="draft-conflict-reload"]')).not.toBeNull();

    api.post.mockResolvedValueOnce({ data: {
      ...draftPatient(7).data,
      transcription: { id: "tx-1", locked: false, draft_version: 7, diagnosis_options: [], diagnosis_other: "Theirs" },
    } });
    await act(async () => container.querySelector('[data-testid="draft-conflict-review"]').click());
    expect(container.querySelector('[data-testid="draft-conflict"]')).toBeNull();
    expect(otherValue()).toBe("Pterygium left eye");

    api.post.mockResolvedValueOnce(savedDraft(8));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    expect(api.post).toHaveBeenLastCalledWith(
      "/clinical/transcription",
      expect.objectContaining({ expected_draft_version: 7, diagnosis_other: "Pterygium left eye" }),
    );
    expect(container.querySelector('[data-testid="draft-conflict"]')).toBeNull();
  });

  test("a completion retry reuses its operation id only while the request is unchanged", async () => {
    await openDraft(3);
    await act(async () => container.querySelector('[data-testid="diagnosis-opt-cataract"]').click());
    api.post.mockResolvedValueOnce(savedDraft(4));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    await act(async () => container.querySelector('[data-testid="none-prescribed"]').click());
    api.post.mockResolvedValueOnce(savedDraft(5));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    await act(async () => container.querySelector('[data-testid="full-transcription-confirmed"]').click());
    const complete = () => act(async () => container.querySelector('[data-testid="complete-prescription-button"]').click());
    const ids = () => api.post.mock.calls
      .filter(([url]) => url === "/clinical/transcription/complete")
      .map(([, body]) => body.operation_id);

    api.post.mockRejectedValueOnce(new Error("Network Error"));
    await complete();
    api.post.mockRejectedValueOnce(new Error("Network Error"));
    await complete();
    expect(ids()[1]).toBe(ids()[0]);

    await act(async () => container.querySelector('[data-testid="add-vitals-button"]').click());
    act(() => {
      const bp = container.querySelector('[data-testid="bp-input"]');
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(bp, "130/80");
      bp.dispatchEvent(new Event("input", { bubbles: true }));
    });
    api.post.mockRejectedValueOnce(new Error("Network Error"));
    await complete();
    expect(ids()[2]).not.toBe(ids()[0]);
  });

  test("a completion refused as stale retries under a new operation id after reloading", async () => {
    await openDraft(3);
    await act(async () => container.querySelector('[data-testid="diagnosis-opt-cataract"]').click());
    api.post.mockResolvedValueOnce(savedDraft(4));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    await act(async () => container.querySelector('[data-testid="none-prescribed"]').click());
    api.post.mockResolvedValueOnce(savedDraft(5));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    await act(async () => container.querySelector('[data-testid="full-transcription-confirmed"]').click());

    api.post.mockRejectedValueOnce(conflictError);
    await act(async () => container.querySelector('[data-testid="complete-prescription-button"]').click());
    const refused = api.post.mock.calls.at(-1)[1].operation_id;
    expect(refused).toBeTruthy();

    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient" },
      person: { id: "p-1" },
      transcription: { id: "tx-1", locked: false, draft_version: 9 },
      fulfilments: [],
      slips: [],
    } });
    await act(async () => container.querySelector('[data-testid="draft-conflict-reload"]').click());
    expect(container.querySelector('[data-testid="wizard-progress"]').textContent).toContain("Step 1 of");
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    await act(async () => container.querySelector('[data-testid="none-prescribed"]').click());
    api.post.mockResolvedValueOnce(savedDraft(10));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    await act(async () => container.querySelector('[data-testid="full-transcription-confirmed"]').click());
    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient", clinical_generation: 1 },
      revision: { id: "rev-2", prescribed_lines: [] },
      transcription: { id: "tx-1", locked: true, draft_version: 12 },
    } });
    await act(async () => container.querySelector('[data-testid="complete-prescription-button"]').click());
    expect(api.post.mock.calls.at(-1)[1].operation_id).not.toBe(refused);
  });

  test("reloading after a conflict replaces the draft with the saved prescription", async () => {
    await openDraft(2);
    typeOther("Mine");
    api.post.mockRejectedValueOnce(conflictError);
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());

    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient" },
      person: { id: "p-1" },
      transcription: { id: "tx-1", locked: false, draft_version: 7, diagnosis_other: "Theirs" },
      fulfilments: [],
      slips: [],
    } });
    await act(async () => container.querySelector('[data-testid="draft-conflict-reload"]').click());
    expect(api.post).toHaveBeenLastCalledWith("/clinical/lookup", { value: "1001" });
    expect(container.querySelector('[data-testid="draft-conflict"]')).toBeNull();
    expect(otherValue()).toBe("Theirs");
    typeOther("Theirs, checked");
    api.post.mockResolvedValueOnce(savedDraft(8));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    expect(api.post).toHaveBeenLastCalledWith(
      "/clinical/transcription",
      expect.objectContaining({ expected_draft_version: 7 }),
    );
  });

  test("an uncommitted draft shows no line mismatch", async () => {
    api.post.mockResolvedValueOnce(draftPatient(1));
    await renderPage();
    typeLookup("1001");
    await submitLookup();
    expect(container.querySelector('[data-testid="edit-transcription-button"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="line-mismatch-warning"]')).toBeNull();
  });

  test("the Doctor Rx line shows no line mismatch after completion", async () => {
    auth.user.line = "doctor_rx";
    sessionStorage.setItem(LINE_STORAGE_KEY, "doctor_rx");
    api.post.mockResolvedValueOnce({ data: {
      ...draftPatient(1).data,
      transcription: { id: "tx-1", locked: true, diagnosis_options: [] },
      committed_revision: { id: "rev-1", prescribed_lines: ["medicine"] },
    } });
    await renderPage();
    typeLookup("1001");
    await submitLookup();
    expect(container.querySelector('[data-testid="add-correction-button"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="line-mismatch-warning"]')).toBeNull();
  });

  test("a failed draft save keeps the entries and leaves no conflict prompt", async () => {
    await openDraft(2);
    typeOther("Kept after failure");
    api.post.mockRejectedValueOnce(new Error("Draft save failed"));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    expect(container.textContent).toContain("Draft save failed");
    expect(container.querySelector('[data-testid="draft-conflict"]')).toBeNull();
    expect(otherValue()).toBe("Kept after failure");
  });

  test("cancelling a discard stays on the same patient and confirming switches exactly once", async () => {
    await openDraft(1);
    typeOther("Unsaved work");

    typeLookup("1002");
    await submitLookup();
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Draft Patient");

    await act(async () => document.querySelector('[data-testid="discard-cancel"]').click());
    expect(document.querySelector('[data-testid="discard-confirm"]')).toBeNull();
    expect(container.textContent).toContain("Draft Patient");
    expect(api.post).toHaveBeenCalledTimes(1);

    await submitLookup();
    api.post.mockResolvedValueOnce(patientFound("1002", "Second Patient"));
    await act(async () => document.querySelector('[data-testid="discard-confirm"]').click());
    expect(api.post).toHaveBeenCalledTimes(2);
    expect(api.post).toHaveBeenLastCalledWith("/clinical/lookup", { value: "1002" });
    expect(container.textContent).toContain("Second Patient");
    expect(container.textContent).not.toContain("Draft Patient");
  });

  test("a background wedge scan does not silently change the patient while the draft is dirty", async () => {
    let now = 0;
    jest.spyOn(performance, "now").mockImplementation(() => now);
    await openDraft(1);
    typeOther("Unsaved work");

    await act(async () => {
      for (const key of [..."SNP:AB3K7T29", "Enter"]) {
        now += 10;
        document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
      }
    });

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Draft Patient");
    expect(document.querySelector('[data-testid="discard-confirm"]')).not.toBeNull();

    api.post.mockResolvedValueOnce(patientFound("1002", "Scanned Patient"));
    await act(async () => document.querySelector('[data-testid="discard-confirm"]').click());
    expect(api.post).toHaveBeenLastCalledWith("/clinical/lookup", { value: "SNP:AB3K7T29" });
  });

  test("changing line asks before discarding a dirty draft", async () => {
    await openDraft(1);
    typeOther("Unsaved work");
    await act(async () => container.querySelector('[data-testid="line-change-button"]').click());
    expect(container.querySelector('[data-testid="line-picker"]')).toBeNull();
    await act(async () => document.querySelector('[data-testid="discard-confirm"]').click());
    expect(container.querySelector('[data-testid="line-picker"]')).not.toBeNull();
  });

  test("the unsaved-work warning is registered only while the draft is dirty", async () => {
    await openDraft(1);
    const warns = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(warns()).toBe(false);

    typeOther("Unsaved work");
    expect(warns()).toBe(true);

    api.post.mockResolvedValueOnce(savedDraft(2));
    await act(async () => container.querySelector('[data-testid="wizard-next"]').click());
    expect(warns()).toBe(false);
  });
});

describe("S7 clinical desk", () => {
  beforeEach(() => api.post.mockReset());

  const draft = (draft_version) => ({ data: {
    registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient", queue_status: "arrived" },
    person: { id: "p-1" },
    transcription: { id: "tx-1", locked: false, draft_version, diagnosis_options: [] },
    fulfilments: [],
    slips: [],
  } });

  const completed = (fulfilments = []) => ({ data: {
    registration: { id: "reg-1", reg_no: "1001", full_name: "Done Patient", queue_status: "seen", clinical_generation: 1 },
    person: { id: "p-1" },
    transcription: { id: "tx-1", locked: true, draft_version: 3, diagnosis_options: ["Cataract"] },
    committed_revision: { id: "rev-1", prescribed_lines: ["medicine"] },
    clinical_generation: 1,
    fulfilments,
    slips: [],
  } });

  async function open(response) {
    api.post.mockResolvedValueOnce(response);
    await renderPage();
    typeLookup("1001");
    await submitLookup();
  }

  const q = (id) => container.querySelector(`[data-testid="${id}"]`);
  const posts = (url) => api.post.mock.calls.filter(([u]) => u === url);

  async function toReview() {
    await act(async () => q("edit-transcription-button").click());
    await act(async () => q("wizard-next").click());
    await act(async () => q("none-prescribed").click());
    api.post.mockResolvedValueOnce({ data: { transcription: { id: "tx-1", draft_version: 4 } } });
    await act(async () => q("wizard-next").click());
    await act(async () => q("full-transcription-confirmed").click());
  }

  test("a step with no changes advances without a save", async () => {
    await open(draft(3));
    await act(async () => q("edit-transcription-button").click());
    await act(async () => q("wizard-next").click());
    expect(posts("/clinical/transcription")).toHaveLength(0);
    expect(q("wizard-progress").textContent).toContain("Step 2 of");
  });

  test("a stale-generation refusal offers the same Reload as a draft conflict", async () => {
    await open(draft(3));
    await toReview();
    api.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: {
      code: "STALE_GENERATION", message: "The prescription changed; reload and retry.",
    } } } });
    await act(async () => q("complete-prescription-button").click());
    expect(q("draft-conflict-reload")).not.toBeNull();
  });

  test("after completion the lookup is cleared and ready for the next patient", async () => {
    await open(draft(3));
    await toReview();
    api.post.mockResolvedValueOnce({ data: {
      registration: { id: "reg-1", reg_no: "1001", full_name: "Draft Patient", clinical_generation: 1 },
      revision: { id: "rev-1", prescribed_lines: [] },
      transcription: { id: "tx-1", locked: true, draft_version: 5 },
    } });
    await act(async () => q("complete-prescription-button").click());
    const lookup = q("clinical-lookup-input");
    expect(lookup.value).toBe("");
    expect(document.activeElement).toBe(lookup);
  });

  test("Undo completion is offered before any line is issued and sends the patient back to Arrived", async () => {
    sessionStorage.setItem(LINE_STORAGE_KEY, "doctor_rx");
    await open(completed());
    await act(async () => q("undo-completion-button").click());
    const confirm = document.querySelector('[data-testid="undo-completion-confirm"]');
    expect(confirm.disabled).toBe(true);
    act(() => {
      const reason = document.querySelector('[data-testid="undo-completion-reason"]');
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(reason, "Wrong patient");
      reason.dispatchEvent(new Event("input", { bubbles: true }));
    });
    api.post.mockResolvedValueOnce({ data: { registration: { id: "reg-1", queue_status: "arrived", clinical_generation: 2 } } });
    api.post.mockResolvedValueOnce(draft(4));
    await act(async () => document.querySelector('[data-testid="undo-completion-confirm"]').click());
    expect(posts("/clinical/transcription/undo")[0][1]).toEqual(expect.objectContaining({
      patient_id: "reg-1", expected_generation: 1, reason: "Wrong patient", operation_id: expect.any(String),
    }));
    expect(container.textContent).toContain("Completion undone");
  });

  test("Undo completion is not offered once any line is issued", async () => {
    sessionStorage.setItem(LINE_STORAGE_KEY, "doctor_rx");
    await open(completed([{ id: "f-1", item_type: "medicine", status: "fulfilled" }]));
    expect(q("undo-completion-button")).toBeNull();
  });

  test("a conflict reload starts the wizard again from its first step", async () => {
    await open(draft(3));
    await act(async () => q("edit-transcription-button").click());
    await act(async () => q("wizard-next").click());
    expect(q("wizard-progress").textContent).toContain("Step 2 of");
    await act(async () => q("none-prescribed").click());
    api.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: {
      code: "DRAFT_VERSION_CONFLICT", message: "Another operator saved this prescription; reload before saving.",
    } } } });
    await act(async () => q("wizard-next").click());
    api.post.mockResolvedValueOnce(draft(9));
    await act(async () => q("draft-conflict-reload").click());
    await act(async () => q("edit-transcription-button")?.click());
    expect(q("wizard-progress").textContent).toContain("Step 1 of");
  });
});

