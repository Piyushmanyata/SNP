import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import PrintPrescription, { PrescriptionSheet } from "./PrintPrescription";
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

describe("PrintPrescription component", () => {
  test.each(["unmount", "patient change"])("a print stamp completing after %s cannot print the current document", async (transition) => {
    const print = jest.spyOn(window, "print").mockImplementation(() => {});
    let resolveStamp;
    api.post.mockImplementationOnce(() => new Promise((resolve) => { resolveStamp = resolve; }));
    await act(async () => root.render(<PrescriptionSheet rx={{ patient_qr: "qr1" }} patientId="p1" navigate={jest.fn()} />));
    try {
      await act(async () => container.querySelector('[data-testid="print-a4-prescription-button"]').click());
      await act(async () => root.render(transition === "unmount"
        ? <p>Another page</p>
        : <PrescriptionSheet rx={{ patient_qr: "qr2" }} patientId="p2" navigate={jest.fn()} />));
      await act(async () => resolveStamp({ data: {} }));
      expect(print).not.toHaveBeenCalled();
    } finally {
      print.mockRestore();
    }
  });

  test("a failed print stamp prevents printing and allows an explicit retry", async () => {
    const print = jest.spyOn(window, "print").mockImplementation(() => {});
    api.post.mockRejectedValueOnce(new Error("Network Error")).mockResolvedValueOnce({ data: {} });
    await act(async () => root.render(<PrescriptionSheet rx={{ patient_qr: "qr1" }} patientId="p1" navigate={jest.fn()} />));
    try {
      await act(async () => container.querySelector('[data-testid="print-a4-prescription-button"]').click());
      expect(print).not.toHaveBeenCalled();
      expect(container.textContent).toContain("Network Error");
      await act(async () => container.querySelector('[data-testid="print-a4-prescription-button"]').click());
      expect(print).toHaveBeenCalledTimes(1);
    } finally {
      print.mockRestore();
    }
  });

  test("changing patients hides the previous printable sheet until the new prescription loads", async () => {
    let resolveNext;
    api.get.mockImplementation((url) => {
      if (url === "/desk/print/p1") return Promise.resolve({ data: { prescription: { full_name: "Previous patient", patient_qr: "qr1" } } });
      if (url === "/desk/print/p2") return new Promise((resolve) => { resolveNext = resolve; });
      return Promise.resolve({ data: { logos: [] } });
    });
    await act(async () => root.render(
      <MemoryRouter initialEntries={["/print/rx/p1"]}>
        <Link to="/print/rx/p2">Next patient</Link>
        <Routes><Route path="/print/rx/:id" element={<PrintPrescription />} /></Routes>
      </MemoryRouter>,
    ));
    expect(container.textContent).toContain("Previous patient");
    await act(async () => container.querySelector("a").click());
    expect(container.querySelector('[data-testid="print-a4-prescription-button"]')).toBeNull();
    expect(container.textContent).not.toContain("Previous patient");
    await act(async () => resolveNext({ data: { prescription: { full_name: "Current patient", patient_qr: "qr2" } } }));
    expect(container.textContent).toContain("Current patient");
  });

  test("prints the fixed trust letterhead even when the sponsor logos cannot be fetched", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});

    api.get
      .mockResolvedValueOnce({
        data: {
          prescription: {
            id: "rx-123",
            camp_id: "camp-001",
            camp_name: "SNP Camp Nadia",
            venue: "Community Center",
            reg_no: "1001",
            patient_qr: "qr-1001",
            full_name: "Aparna Sen",
            age: 45,
            gender: "Female",
            date: "2026-08-27",
          },
        },
      })
      .mockRejectedValueOnce(new Error("Template service unavailable"));

    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/print/rx/rx-123"]}>
          <Routes>
            <Route path="/print/rx/:id" element={<PrintPrescription />} />
          </Routes>
        </MemoryRouter>
      );
    });

    expect(warnSpy).toHaveBeenCalledWith(
      "Failed to fetch sponsor logos, printing without them:",
      expect.any(Error)
    );

    const sheet = container.querySelector('[data-testid="a4-prescription-sheet"]');
    expect(sheet).not.toBeNull();
    expect(container.textContent).toContain("SIKAR NAGARIK PARISHAD (KOLKATA)");
    expect(container.textContent).toContain("SIKAR ZILLA WELFARE TRUST");
    expect(container.textContent).toContain("sikarkolkata@gmail.com");
    expect(container.textContent).toContain("ARRANGMENT");
    expect(container.textContent).toContain("Remaks");
    expect(container.textContent).toContain("Sponsorer :");
    expect(container.textContent).toContain("Community Center");
    expect(container.textContent).toContain("Aparna Sen");
    expect(container.textContent).toContain("#1001");

    warnSpy.mockRestore();
  });

  test("renders every fixed block and asks the server only for logos", async () => {
    api.get
      .mockResolvedValueOnce({
        data: {
          prescription: {
            id: "rx-1", camp_id: "camp-001", camp_name: "SNP Camp Nadia",
            venue: "Community Center", reg_no: "1001", patient_qr: "qr-1001",
            full_name: "Aparna Sen", age: 45, gender: "Female", date: "2026-08-27",
          },
        },
      })
      .mockResolvedValueOnce({ data: { logos: [] } });

    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/print/rx/rx-1"]}>
          <Routes>
            <Route path="/print/rx/:id" element={<PrintPrescription />} />
          </Routes>
        </MemoryRouter>
      );
    });

    expect(api.get).toHaveBeenCalledWith("/templates/logos?camp_id=camp-001");
    expect(container.querySelector('[data-testid="rx-block-identity"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="rx-diagnosis-row"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="rx-operation-box"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="rx-footer"]')).not.toBeNull();
  });

  test("the reference form snapshot and named strings stay put", () => {
    const sample = {
      camp_name: "Kolkata Eye Camp",
      venue: "Rotary Club",
      reg_no: "101",
      patient_qr: "qr-fixed",
      full_name: "Sample Patient",
      age: 52,
      gender: "M",
      date: "2026-09-01",
      phone: "9876543210",
      address: "12 MG Road",
    };
    const logos = [{ id: "logo-1", name: "rupa.png", data_url: "data:image/png;base64,aaa" }];
    act(() => {
      root.render(<PrescriptionSheet rx={sample} logos={logos} preview />);
    });
    const sheet = container.querySelector('[data-testid="a4-prescription-sheet"]');
    expect(sheet.textContent).toContain("ARRANGMENT");
    expect(sheet.textContent).toContain("Remaks");
    expect(sheet.textContent).toContain("PRESCRIPTION FOR GLASSES");
    expect(sheet.textContent).toContain("Inter Pupillary distance");
    expect(sheet.textContent).toContain("Sponsorer :");
    expect(sheet).toMatchSnapshot();
  });

  test("handles prescription loading error", async () => {
    api.get.mockRejectedValueOnce(new Error("Prescription not found"));

    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/print/rx/rx-invalid"]}>
          <Routes>
            <Route path="/print/rx/:id" element={<PrintPrescription />} />
          </Routes>
        </MemoryRouter>
      );
    });

    expect(container.textContent).toContain("Prescription not found");
  });
});
