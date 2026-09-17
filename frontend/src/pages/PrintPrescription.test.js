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
    expect(container.querySelector('[data-testid="rx-glasses-box"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="rx-bring-list"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="rx-footer"]')).not.toBeNull();
  });

  test("the sheet declares one A4 page with no margin and a fixed page box", () => {
    act(() => {
      root.render(<PrescriptionSheet rx={{ patient_qr: "qr-1" }} navigate={jest.fn()} />);
    });
    const printRules = container.querySelector("style").textContent;
    expect(printRules).toContain("@page { size: A4; margin: 0; }");
    expect(printRules).toMatch(/.print-rx-page { padding: 0; min-height: 0;/);
    expect(container.querySelector(".print-rx-page")).not.toBeNull();
    const sheet = container.querySelector('[data-testid="a4-prescription-sheet"]');
    expect(sheet.style.height).toBe("297mm");
    expect(sheet.style.overflow).toBe("hidden");
    expect(sheet.querySelector('[data-testid="rx-write-area"]').className).toContain("flex-1");
  });

  test("the sheet is a full page and every sponsor sits in the footer band", () => {
    const logos = Array.from({ length: 5 }, (_, i) => ({
      id: `logo-${i}`, name: `sponsor-${i}.png`, data_url: "data:image/png;base64,aaa",
    }));
    act(() => {
      root.render(<PrescriptionSheet rx={{ patient_qr: "qr-1" }} logos={logos} />);
    });
    const sheet = container.querySelector('[data-testid="a4-prescription-sheet"]');
    expect(sheet.style.width).toBe("210mm");
    expect(sheet.style.height).toBe("297mm");
    expect(sheet.querySelector('[data-testid="rx-write-area"]')).not.toBeNull();
    expect(sheet.querySelectorAll('[data-testid="rx-medicine-line"]')).toHaveLength(3);

    const strip = sheet.querySelector('[data-testid="rx-sponsor-strip"]');
    expect(strip.children).toHaveLength(5);
    expect(sheet.querySelector('[data-testid="rx-footer"]').contains(strip)).toBe(true);
    expect(sheet.querySelector('[data-testid="rx-signature"]')).not.toBeNull();
  });

  test("the patient QR carries an uppercase SNP prefix and a printable quiet zone", () => {
    act(() => {
      root.render(<PrescriptionSheet rx={{ patient_qr: "K7M2QX9F" }} preview />);
    });
    const svg = container.querySelector('[data-testid="a4-prescription-sheet"] svg');
    // 21 modules of Version 1 plus the spec's 4-module quiet zone on each side.
    expect(svg.getAttribute("viewBox")).toBe("0 0 29 29");
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
    const band = sheet.querySelector('[data-testid="rx-bring-list"]');
    expect([...band.querySelectorAll("p")].map((line) => line.textContent)).toEqual([
      "केवल मोतियाबिंद (IOL) ऑपरेशन की व्यवस्था की जाती है। ऑपरेशन के दिन लाएँ: यह पर्चा, टोकन, आधार कार्ड, राशन कार्ड, मोबाइल फ़ोन।",
      "Only cataract (IOL) operations are arranged. On the day of the operation bring: this prescription, token, Aadhaar card, ration card, mobile phone.",
    ]);
    expect(sheet.textContent).not.toContain("Please carry");
    expect(sheet.textContent).toContain("01-09-2026");
    expect(sheet.textContent).not.toContain("2026-09-01");
    expect(sheet.textContent).not.toContain("Operation will be done at");
    expect(sheet.textContent).toContain("Operation will be done by");
    expect(sheet.querySelectorAll('[data-testid="rx-medicine-line"]')).toHaveLength(3);
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
