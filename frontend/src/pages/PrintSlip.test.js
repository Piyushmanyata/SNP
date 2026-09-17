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

const OT_SLIP = {
  id: "tok-1",
  item_type: "ot",
  version: 2,
  collection_date: "2026-12-01",
  collection_venue: "Base Hospital",
  active: true,
  ot_eye: "R",
  bp: "140/90",
  blood_sugar: "110",
};

async function renderToken(slip) {
  api.get.mockResolvedValueOnce({
    data: {
      slip,
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
  return container.querySelector('[data-testid="a6-token"]');
}

describe("Token print page", () => {
  test("renders A6 bilingual Token without QR or thermal slip", async () => {
    const surface = await renderToken(OT_SLIP);

    expect(surface).not.toBeNull();
    expect(surface.style.maxWidth).toBe("95mm");
    expect(container.querySelector("style").textContent).toContain("105mm");
    expect(container.querySelector("style").textContent).toContain("148mm");
    expect(container.textContent).toContain("SNP Camp Nadia");
    expect(container.textContent).toContain("Aparna Sen");
    expect(container.textContent).toContain("#1001");
    expect(container.textContent).not.toContain("Version");
    expect(container.textContent).toContain("Base Hospital");
    expect(container.textContent).toContain("9835317006");
    expect(container.textContent).toContain("नाम / Name");
    expect(surface.querySelector("svg")).toBeNull();
    expect(container.querySelector('[data-testid="thermal-slip"]')).toBeNull();
    expect(container.querySelector(".print-thermal")).toBeNull();
    expect(container.innerHTML).not.toContain("58mm");
    expect(container.innerHTML).not.toContain("print-thermal");
    expect(container.innerHTML).not.toContain("thermal-slip");
  });

  test("an IOL surgery Token names the operation, the eye, the vitals and the Bring list with a DD-MM-YYYY date", async () => {
    const surface = await renderToken(OT_SLIP);

    expect(surface.textContent).toContain("मोतियाबिंद (IOL) ऑपरेशन / IOL Surgery");
    expect(surface.textContent).toContain("दायीं आँख / Right eye");
    expect(surface.textContent).toContain("140/90");
    expect(surface.textContent).toContain("110");
    expect(surface.textContent).toContain("01-12-2026");
    expect(surface.textContent).not.toContain("2026-12-01");
    expect(surface.textContent).toContain("पर्चा, यह टोकन, आधार कार्ड, राशन कार्ड, मोबाइल फ़ोन");
    expect(surface.textContent).not.toContain("वोटर");
  });

  test("an IOL surgery Token without recorded vitals prints no BP or blood sugar line", async () => {
    const surface = await renderToken({ ...OT_SLIP, ot_eye: "L", bp: null, blood_sugar: null });

    expect(surface.textContent).toContain("बायीं आँख / Left eye");
    expect(surface.textContent).not.toContain("BP");
    expect(surface.textContent).not.toContain("Blood sugar");
  });

  test("a Spectacles to be made Token keeps its collection line with a DD-MM-YYYY date", async () => {
    const surface = await renderToken({
      id: "tok-2",
      item_type: "specs_made",
      collection_date: "2026-12-05",
      collection_venue: "Base Optical",
      collection_start_time: "10:00",
      collection_end_time: "12:00",
    });

    expect(surface.textContent).toContain("चश्मा / Spectacles");
    expect(surface.textContent).toContain("05-12-2026");
    expect(surface.textContent).toContain("10:00–12:00");
    expect(surface.textContent).toContain("Bring this token for collection.");
    expect(surface.textContent).not.toContain("IOL");
    expect(surface.textContent).not.toContain("आधार कार्ड");
  });
});
