import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PrintSlip from "./PrintSlip";
import api from "../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
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

describe("Token print page", () => {
  test("renders A6 bilingual Token without QR or thermal slip", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        slip: {
          id: "tok-1",
          item_type: "ot",
          version: 2,
          collection_date: "2026-12-01",
          collection_venue: "Base Hospital",
          active: true,
        },
        registration: { id: "reg-1", reg_no: 1001, full_name: "Aparna Sen" },
        camp_name: "SNP Camp Nadia",
      },
    });

    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/print/slip/tok-1"]}>
          <Routes>
            <Route path="/print/slip/:id" element={<PrintSlip />} />
          </Routes>
        </MemoryRouter>
      );
    });

    const surface = container.querySelector('[data-testid="a6-token"]');
    expect(surface).not.toBeNull();
    expect(surface.style.width).toBe("105mm");
    expect(surface.style.height).toBe("148mm");
    expect(container.querySelector("style").textContent).toContain("105mm");
    expect(container.querySelector("style").textContent).toContain("148mm");
    expect(container.textContent).toContain("SNP Camp Nadia");
    expect(container.textContent).toContain("ऑपरेशन");
    expect(container.textContent).toContain("Surgery");
    expect(container.textContent).toContain("Aparna Sen");
    expect(container.textContent).toContain("#1001");
    expect(container.textContent).toContain("v2");
    expect(container.textContent).toContain("2026-12-01");
    expect(container.textContent).toContain("Base Hospital");
    expect(container.textContent).toContain("यह टोकन साथ लाएँ");
    expect(container.textContent).toContain("Bring this Token");
    expect(container.textContent).toContain("नाम / Name");
    expect(surface.querySelector("svg")).toBeNull();
    expect(container.querySelector('[data-testid="thermal-slip"]')).toBeNull();
    expect(container.querySelector(".print-thermal")).toBeNull();
    expect(container.innerHTML).not.toContain("58mm");
    expect(container.innerHTML).not.toContain("print-thermal");
    expect(container.innerHTML).not.toContain("thermal-slip");
  });
});
