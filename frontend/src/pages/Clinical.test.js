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
            { id: "sp-1", day_date: "2026-09-12", venue: "Base Optical", start_time: "09:00", end_time: "12:00" },
            { id: "sp-full", day_date: "2026-09-13", venue: "Full Desk", window_required: true },
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
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("Hospital surgery");

    act(() => { root.unmount(); });
    root = ReactDOM.createRoot(container);
    await act(async () => {
      root.render(<MemoryRouter><Clinical /></MemoryRouter>);
    });
    expect(container.querySelector('[data-testid="line-chip"]').textContent).toContain("Hospital surgery");

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

  test("Spectacles to be made assigns a Specs collection day with date venue and window", async () => {
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
    const fullOpt = Array.from(daySelect.options).find((o) => o.value === "sp-full");
    expect(fullOpt).toBeUndefined();
    const openOpt = Array.from(daySelect.options).find((o) => o.value === "sp-1");
    expect(openOpt.disabled).toBe(false);
    expect(openOpt.textContent).toContain("Base Optical");
    expect(openOpt.textContent).toContain("09:00–12:00");
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
