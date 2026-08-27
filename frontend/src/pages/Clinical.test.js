import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Clinical from "./Clinical";
import api from "../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

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
    expect(medicineStation).not.toBeNull();
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
    warnSpy.mockRestore();
  });
});
