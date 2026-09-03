import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Clinical from "./Clinical";
import api from "../lib/api";
import { LINE_STORAGE_KEY } from "../lib/operatorLines";

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
            { id: "sp-1", day_date: "2026-09-12", venue: "Base Optical", seats_free: 4 },
            { id: "sp-full", day_date: "2026-09-13", venue: "Full Desk", seats_free: 0 },
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
});

describe("Clinical page component", () => {
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
        ot_procedure: "Phaco + IOL",
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

    // Verify subcomponents exist
    const rxForm = container.querySelector('[data-testid="clinical-prescription-form"]');
    expect(rxForm).not.toBeNull();

    const specInput = container.querySelector('[data-testid="specs-r_sph"]');
    expect(specInput.value).toBe("-1.5");

    const otSelect = container.querySelector('[data-testid="ot-eye-select"]');
    expect(otSelect.value).toBe("R");

    const medicineStation = container.querySelector('[data-testid="station-medicine"]');
    expect(medicineStation).toBeNull();
    expect(container.querySelector('[data-testid="fulfilment-section"]')).toBeNull();
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
    expect(container.querySelector('[data-testid="station-medicine-fulfilled"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="station-medicine-not_available"]')).not.toBeNull();
  });

  test("the line picker appears when there is no line", async () => {
    auth.user.line = null;
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-picker"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="clinical-lookup-input"]')).toBeNull();
  });

  test("a session override survives remount and a fresh load uses the account default", async () => {
    sessionStorage.setItem(LINE_STORAGE_KEY, "ot");
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("OT");

    act(() => { root.unmount(); });
    root = ReactDOM.createRoot(container);
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("OT");

    sessionStorage.clear();
    auth.user.line = "medicine";
    act(() => { root.unmount(); });
    root = ReactDOM.createRoot(container);
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("Medicine");
  });

  test("a mismatch is advisory and the control stays usable", async () => {
    auth.user.line = "ot";
    api.post.mockResolvedValueOnce({
      data: {
        registration: { id: "reg-101", reg_no: "1001", full_name: "Subhash Bose", gender_label: "Male", age: 58 },
        person: { id: "p-101" },
        transcription: { id: "tx-101", locked: true, diagnosis_options: ["Cataract"], specs_measurements: { r_sph: "-1", l_sph: "-1" } },
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
    expect(container.querySelector('[data-testid="station-ot-fulfilled"]').disabled).toBe(false);
  });

  test("no transcription sends the patient to Doctor's Rx", async () => {
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
    expect(container.querySelector('[data-testid="send-to-rx"]').textContent).toContain("Doctor");
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

  test("Spectacles to be made assigns a Specs collection day with full days unselectable", async () => {
    auth.user.line = "specs_made";
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
        id: "tx-101", locked: false, diagnosis_options: ["Cataract"],
        specs_measurements: { r_sph: "-1.00", l_sph: "-1.25" },
      },
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
    const fullOpt = Array.from(daySelect.options).find((o) => o.value === "sp-full");
    expect(fullOpt).toBeTruthy();
    expect(fullOpt.disabled).toBe(true);
    const openOpt = Array.from(daySelect.options).find((o) => o.value === "sp-1");
    expect(openOpt.disabled).toBe(false);
  });
});
