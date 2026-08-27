import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PrintPrescription from "./PrintPrescription";
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
  test("renders prescription sheet with default render fallback when template API fails with warning", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});

    api.post.mockResolvedValueOnce({
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
    });

    api.get.mockRejectedValueOnce(new Error("Template service unavailable"));

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
      "Failed to fetch active template for camp, falling back to default render:",
      expect.any(Error)
    );

    const sheet = container.querySelector('[data-testid="a4-prescription-sheet"]');
    expect(sheet).not.toBeNull();
    expect(container.textContent).toContain("SNP Camp Nadia");
    expect(container.textContent).toContain("Aparna Sen");
    expect(container.textContent).toContain("#1001");

    warnSpy.mockRestore();
  });

  test("handles prescription loading error", async () => {
    api.post.mockRejectedValueOnce(new Error("Prescription not found"));

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
