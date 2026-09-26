import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Desk from "./Desk";
import api from "../lib/api";
import { forgetLogos } from "../lib/logoCache";

const mockAuth = { user: { id: "u1", name: "Lead", role: "team_lead" } };

jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

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

const CARD_PAYLOAD = "AADHAAR|Aadhaar Scanned User|M|1984-05-12|8888|10 Downing St, Kolkata";

jest.mock("../components/AadhaarScanner", () => {
  const { useState } = require("react");
  const payload = "AADHAAR|Aadhaar Scanned User|M|1984-05-12|8888|10 Downing St, Kolkata";
  return function MockAadhaarScanner({ onScanned, resolvePayload, onFailure, onScanStall, onPatientCode, onCaptureStart, disabled }) {
    const [resolved, setResolved] = useState("");
    const scan = async () => {
      if (onScanned) {
        onScanned(
          {
            full_name: "Aadhaar Scanned User",
            age: 42,
            gender: "M",
            address: "10 Downing St, Kolkata",
            aadhaar_last4: "8888",
            dob: "1984-05-12",
          },
          payload
        );
        return;
      }
      setResolved("");
      try {
        setResolved(JSON.stringify(await resolvePayload(payload)));
      } catch (err) {
        setResolved(`threw: ${err.message}`);
      }
    };
    return (
      <div data-testid="mock-aadhaar-scanner" data-disabled={String(Boolean(disabled))}>
        <textarea data-usb-box="" aria-label="USB scanner" data-testid="mock-usb-box" />
        <button type="button" data-testid="mock-scan-trigger" onClick={scan}>
          Simulate Scan
        </button>
        <output data-testid="mock-resolve-result">{resolved}</output>
        <button type="button" data-testid="mock-capture-start" onClick={() => onCaptureStart && onCaptureStart()}>
          Simulate new capture
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
        <button
          type="button"
          data-testid="mock-patient-code-trigger"
          onClick={() => onPatientCode && onPatientCode("snp:ABC12345")}
        >
          Simulate patient QR
        </button>
      </div>
    );
  };
});

const RX = {
  camp_id: "camp-1", camp_name: "Howrah Eye Camp", venue: "Community Hall", reg_no: "101",
  full_name: "Aadhaar Scanned User", patient_qr: "qr-101", date: "2026-08-27", age: 42, gender: "M",
};

const ARRIVED = {
  id: "p-1",
  reg_no: "101",
  full_name: "Aadhaar Scanned User",
  gender_label: "Male",
  age: 42,
  phone: "9876543210",
  queue_status: "arrived",
  arrived_at: "2026-09-01T04:00:00Z",
  printed_at: null,
  camp_day_changed_from: null,
};

let container = null;
let root = null;

function deskScanner() {
  return container.querySelectorAll('[data-testid="mock-scan-trigger"]')[0];
}

function modalScanner(testid) {
  return [...document.body.querySelectorAll(`[data-testid="${testid}"]`)].pop();
}

function resolveResult() {
  const text = container.querySelector('[data-testid="mock-resolve-result"]').textContent;
  return text.startsWith("threw: ") ? text : JSON.parse(text);
}

function apiError(detail) {
  const err = new Error("Request failed with status code 400");
  err.response = { status: 400, data: { detail } };
  return err;
}

const AADHAAR_DIGITS = "2".repeat(120);

function setInput(el, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

let printedText = [];

beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
  window.HTMLImageElement.prototype.decode = () => Promise.resolve();
  printedText = [];
  window.print = jest.fn(() => {
    printedText.push(document.getElementById("print-root")?.textContent);
    window.dispatchEvent(new Event("afterprint"));
  });
  forgetLogos("camp-1");
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  sessionStorage.clear();
  mockAuth.user = { id: "u1", name: "Lead", role: "team_lead" };

  api.get.mockImplementation((url) => {
    if (url === "/roster") {
      return Promise.resolve({ data: { entries: [{ id: "r-1", name: "Ramesh Kumar" }] } });
    }
    if (url === "/kpis") {
      return Promise.resolve({ data: { registered: 45, seen: 30, pending: 15 } });
    }
    if (url === "/camps/active") {
      return Promise.resolve({
        data: {
          camp: { id: "camp-1", name: "Howrah Eye Camp", venue: "Community Hall" },
          days: [
            { id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: true },
            { id: "day-2", day_date: "2026-08-28", is_today: false, printing_open: false },
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

async function renderDesk(campOverrides) {
  if (campOverrides) {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation(async (url) => {
      const r = await base(url);
      if (url !== "/camps/active") return r;
      return { ...r, data: { ...r.data, camp: { ...r.data.camp, ...campOverrides } } };
    });
  }
  await act(async () => {
    root.render(
      <MemoryRouter>
        <Desk />
      </MemoryRouter>
    );
  });
}

async function scanAtDoor() {
  await act(async () => {
    deskScanner().click();
  });
}

test("a new patient lookup immediately removes the previous patient's actions", async () => {
  api.post.mockResolvedValueOnce({ data: { registration: ARRIVED } });
  await renderDesk();
  const code = () => container.querySelector('[data-testid="mock-patient-code-trigger"]');
  await act(async () => { code().click(); });
  expect(container.querySelector('[data-testid="desk-found-patient"]')).not.toBeNull();
  let resolve;
  api.post.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  await act(async () => { code().click(); });
  expect(container.querySelector('[data-testid="desk-found-patient"]')).toBeNull();
  await act(async () => { resolve({ data: { registration: { ...ARRIVED, id: "p-2", full_name: "Next Patient" } } }); });
  expect(container.querySelector('[data-testid="desk-found-patient"]').textContent).toContain("Next Patient");
});

test("a new name search immediately removes the previous search results", async () => {
  const base = api.get.getMockImplementation();
  api.get.mockImplementation((url) => url.startsWith("/patients/search")
    ? Promise.resolve({ data: { results: [ARRIVED] } }) : base(url));
  await renderDesk();
  act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), "Scanned"); });
  await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });
  expect(container.querySelector('[data-testid="desk-search-results"]')).not.toBeNull();
  let reject;
  api.get.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), "Another"); });
  await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });
  expect(container.querySelector('[data-testid="desk-search-results"]')).toBeNull();
  await act(async () => { reject(new Error("Network Error")); });
  expect(container.querySelector('[data-testid="desk-search-results"]')).toBeNull();
});

describe("Desk page", () => {
  test.each(["41", "Scanned"])("search %s releases a superseded scan's busy state", async (value) => {
    let finishScan;
    api.post.mockImplementationOnce(() => new Promise((resolve) => { finishScan = resolve; }));
    if (value === "41") api.post.mockResolvedValueOnce({ data: { registration: ARRIVED } });
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => url.startsWith("/patients/search")
      ? Promise.resolve({ data: { results: [ARRIVED] } }) : base(url));
    await renderDesk();
    await scanAtDoor();
    expect(container.querySelector('[data-testid="door-scan-status"]')).not.toBeNull();
    act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), value); });
    await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
    await act(async () => finishScan({ data: { outcome: "no_match", card: { full_name: "Old scan" } } }));
    expect(container.textContent).not.toContain("Old scan");
    expect(resolveResult()).toEqual({ outcome: "card", quiet: true, superseded: true });
  });

  test("starting a new capture abandons the door scan still in flight", async () => {
    let finishScan;
    api.post.mockImplementationOnce(() => new Promise((resolve) => { finishScan = resolve; }));
    await renderDesk();
    await scanAtDoor();
    expect(container.querySelector('[data-testid="door-scan-status"]')).not.toBeNull();
    act(() => { container.querySelector('[data-testid="mock-capture-start"]').click(); });
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
    await act(async () => finishScan({ data: { outcome: "no_match", card: { full_name: "Old scan" } } }));
    expect(container.textContent).not.toContain("Old scan");
    expect(container.querySelector('[data-testid="scan-no-match"]')).toBeNull();
  });

  test("a superseded door scan that fails stops quietly and shows no error", async () => {
    let failScan;
    api.post.mockImplementationOnce(() => new Promise((_resolve, fail) => { failScan = fail; }));
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => url.startsWith("/patients/search")
      ? Promise.resolve({ data: { results: [ARRIVED] } }) : base(url));
    await renderDesk();
    await scanAtDoor();
    act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), "Scanned"); });
    await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });
    await act(async () => failScan(new Error("Network Error")));
    expect(resolveResult()).toEqual({ outcome: "card", quiet: true, superseded: true });
    expect(container.textContent).not.toContain("Network Error");
    expect(container.querySelector('[data-testid="desk-search-results"]')).not.toBeNull();
  });

  test("a new scan immediately removes the previous mismatch confirmation", async () => {
    api.post.mockResolvedValueOnce({ data: { outcome: "mismatch_review", registration: ARRIVED, diff: [] } });
    let resolveScan;
    api.post.mockImplementationOnce(() => new Promise((resolve) => { resolveScan = resolve; }));
    await renderDesk();
    await scanAtDoor();
    expect(container.querySelector('[data-testid="mismatch-confirm-button"]')).not.toBeNull();
    await scanAtDoor();
    expect(container.querySelector('[data-testid="mismatch-confirm-button"]')).toBeNull();
    await act(async () => resolveScan({ data: { outcome: "no_match", card: { full_name: "Next patient" } } }));
  });

  test("an older scan cannot overwrite the newest card or finish its loading state", async () => {
    let resolveFirst;
    let resolveSecond;
    api.post.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }));
    api.post.mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));
    await renderDesk();
    await scanAtDoor();
    await scanAtDoor();
    await act(async () => resolveFirst({ data: { outcome: "no_match", card: { full_name: "Previous patient" } } }));
    expect(container.textContent).not.toContain("Previous patient");
    expect(container.textContent).toContain("Reading the QR");
    await act(async () => resolveSecond({ data: { outcome: "no_match", card: { full_name: "Latest patient" } } }));
    expect(container.textContent).toContain("Latest patient");
  });

  test("team leads can reach Team Management and Analytics from the desk overview", async () => {
    await renderDesk();
    expect(container.querySelector('[data-testid="desk-team-link"]').getAttribute("href")).toBe("/team");
    expect(container.querySelector('[data-testid="desk-analytics-link"]').getAttribute("href")).toBe("/analytics");
  });

  test("volunteers do not see management navigation", async () => {
    mockAuth.user.role = "volunteer";
    await renderDesk();
    expect(container.querySelector('[data-testid="desk-team-link"]')).toBeNull();
    expect(container.querySelector('[data-testid="desk-analytics-link"]')).toBeNull();
  });

  test("shows KPIs and never lists patients", async () => {
    await renderDesk();

    expect(container.querySelector('[data-testid="kpi-registered-count"]').textContent).toContain("45");
    expect(container.querySelector('[data-testid="kpi-seen-count"]').textContent).toContain("30");
    expect(container.querySelector('[data-testid="patient-list"]')).toBeNull();
    expect(api.get).not.toHaveBeenCalledWith("/patients");
    expect(container.textContent).not.toContain("Today's patients");
  });

  test("one scan box, no mode to choose first", async () => {
    await renderDesk();
    expect(container.querySelectorAll('[data-testid="mock-aadhaar-scanner"]').length).toBe(1);
    expect(container.textContent).toContain("Scan at the door");
  });

  test("a card already on file checks the patient in", async () => {
    api.post.mockResolvedValueOnce({ data: { outcome: "arrived", registration: ARRIVED } });
    await renderDesk();
    await scanAtDoor();

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/desk/scan", { payload: CARD_PAYLOAD });
    expect(api.post).not.toHaveBeenCalledWith("/aadhaar/decode", expect.anything());
    expect(resolveResult()).toEqual({ outcome: "card", source: "desk_scan" });
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    expect(container.textContent).toContain("Arrived: #101");
    expect(container.querySelector('[data-testid="scan-print-button"]')).not.toBeNull();
  });

  test("a door scan the server says is not a card goes back to the scanner as garbage", async () => {
    api.post.mockRejectedValueOnce(apiError({ code: "NOT_A_CARD", message: "That QR is not an Aadhaar card." }));
    await renderDesk();
    await scanAtDoor();

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(resolveResult()).toEqual({ outcome: "garbage", message: "That QR is not an Aadhaar card." });
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
    expect(container.querySelector('[data-testid="desk-card-scan"] [role="alert"]')).toBeNull();
  });

  test("any other door scan failure is thrown for the scanner to show", async () => {
    api.post.mockRejectedValueOnce(new Error("Network Error"));
    await renderDesk();
    await scanAtDoor();

    expect(resolveResult()).toBe("threw: Network Error");
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
    expect(container.querySelector('[data-testid="scan-no-match"]')).toBeNull();
  });

  test("a door scan refresh failure keeps the desk and offers a retry", async () => {
    api.post.mockResolvedValueOnce({ data: { outcome: "arrived", registration: ARRIVED } });
    await renderDesk();
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/kpis" ? Promise.reject(new Error("Network Error")) : base(url)));
    await scanAtDoor();
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });

    const refresh = container.querySelector('[data-testid="desk-refresh-error"]');
    expect(refresh.textContent).toContain("Could not refresh the desk: Network Error");
    expect(container.querySelector('[data-testid="error-retry-button"]')).toBeNull();
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    expect(container.textContent).toContain("Arrived: #101");

    api.get.mockImplementation(base);
    await act(async () => { refresh.querySelector("button").click(); });
    expect(container.querySelector('[data-testid="desk-refresh-error"]')).toBeNull();
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
  });

  test("a first load failure shows the error card", async () => {
    api.get.mockRejectedValue(new Error("Network Error"));
    await renderDesk();

    expect(container.textContent).toContain("Network Error");
    expect(container.querySelector('[data-testid="error-retry-button"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="desk-refresh-error"]')).toBeNull();
    expect(container.querySelector('[data-testid="desk-card-find"]')).toBeNull();
  });

  test("an Aadhaar QR typed into find at the door is resolved as a door scan", async () => {
    api.post.mockResolvedValueOnce({ data: { outcome: "arrived", registration: ARRIVED } });
    await renderDesk();
    act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), AADHAAR_DIGITS); });
    await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/desk/scan", { payload: AADHAAR_DIGITS });
    expect(container.querySelector('[data-testid="desk-find-input"]').value).toBe("");
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    expect(container.textContent).toContain("Arrived: #101");
  });

  test.each([
    ["not a card", () => apiError({ code: "NOT_A_CARD", message: "That QR is not an Aadhaar card." }), "That QR is not an Aadhaar card."],
    ["a failed", () => new Error("Network Error"), "Network Error"],
  ])("%s Aadhaar QR typed into find at the door shows the error", async (_label, failure, message) => {
    api.post.mockRejectedValueOnce(failure());
    await renderDesk();
    act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), AADHAAR_DIGITS); });
    await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });

    expect(api.post).toHaveBeenCalledWith("/desk/scan", { payload: AADHAAR_DIGITS });
    expect(container.querySelector('[data-testid="desk-card-scan"] [role="alert"]').textContent).toBe(message);
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
  });

  test("a repeat door scan of a patient the doctor has seen offers no print", async () => {
    api.post.mockResolvedValueOnce({
      data: { outcome: "arrived", registration: { ...ARRIVED, queue_status: "seen" } },
    });
    await renderDesk();
    await scanAtDoor();

    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="scan-print-button"]')).toBeNull();
    expect(container.querySelector('[data-testid="scan-already-seen"]')).not.toBeNull();
  });

  test("a wrong-day arrival is shown as moved to the day they came", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        outcome: "arrived",
        registration: { ...ARRIVED, camp_day_changed_from: "2026-08-28" },
      },
    });
    await renderDesk();
    await scanAtDoor();

    expect(container.querySelector('[data-testid="scan-day-changed"]').textContent)
      .toContain("28-08-2026");
  });

  test("a Manual entry match shows both value sets with no edit affordance", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        outcome: "mismatch_review",
        registration: { ...ARRIVED, queue_status: "registered", arrived_at: null },
        card: { full_name: "Aadhaar Scanned User", age: 42 },
        diff: [
          { field: "full_name", stored: "A Scanned User", card: "Aadhaar Scanned User" },
          { field: "age", stored: 39, card: 42 },
          { field: "dob", stored: null, card: "1984-05-12" },
        ],
      },
    });
    await renderDesk();
    await scanAtDoor();

    const review = container.querySelector('[data-testid="mismatch-review"]');
    expect(review).not.toBeNull();
    expect(review.textContent).toContain("A Scanned User");
    expect(review.textContent).toContain("Aadhaar Scanned User");
    expect(review.textContent).toContain("39");
    expect(review.textContent).toContain("42");
    expect(review.querySelector('[data-testid="diff-dob"]').textContent).toBe("Date of birth—12-05-1984");
    expect(review.querySelectorAll("input").length).toBe(0);
    expect(review.querySelectorAll("select").length).toBe(0);
    expect(review.textContent).not.toContain("Keep stored");
  });

  test("confirming Mismatch review applies the card and checks in", async () => {
    api.post
      .mockResolvedValueOnce({
        data: {
          outcome: "mismatch_review",
          registration: { ...ARRIVED, arrived_at: null },
          card: { full_name: "Aadhaar Scanned User" },
          diff: [{ field: "age", stored: 39, card: 42 }],
        },
      })
      .mockResolvedValueOnce({ data: { outcome: "arrived", registration: ARRIVED } });

    await renderDesk();
    await scanAtDoor();
    await act(async () => {
      container.querySelector('[data-testid="mismatch-confirm-button"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/desk/scan/confirm", {
      patient_id: "p-1",
      payload: CARD_PAYLOAD,
    });
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
  });

  test("a scan matching nothing registers nobody and offers search first", async () => {
    api.post.mockResolvedValueOnce({
      data: { outcome: "no_match", card: { full_name: "Aadhaar Scanned User", age: 42, gender: "M", address: "10 Downing St, Kolkata" } },
    });
    await renderDesk();
    await scanAtDoor();

    expect(container.querySelector('[data-testid="scan-no-match"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="door-card-readonly"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="door-card-name"]').textContent).toContain("Aadhaar Scanned User");
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).not.toHaveBeenCalledWith("/register", expect.anything());
    expect(container.querySelector('[data-testid="door-register-button"]').disabled).toBe(true);
    expect(container.querySelectorAll('[data-testid="mock-aadhaar-scanner"]').length).toBe(1);
  });

  test("registering a walk-in posts register then arrive from the card already read", async () => {
    api.post.mockImplementation((url, body) => {
      if (url === "/desk/scan") {
        return Promise.resolve({
          data: {
            outcome: "no_match",
            card: {
              full_name: "Aadhaar Scanned User",
              age: 42,
              gender: "M",
              address: "10 Downing St, Kolkata",
              aadhaar_last4: "8888",
              dob: "1984-05-12",
            },
          },
        });
      }
      if (url === "/register") {
        return Promise.resolve({ data: { registration: { id: "p-9", reg_no: "109", full_name: body.full_name } } });
      }
      if (url === "/desk/arrive/p-9") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-9", reg_no: "109" } } });
      }
      return Promise.resolve({ data: {} });
    });

    await renderDesk();
    await scanAtDoor();
    expect(container.querySelector('[data-testid="register-walk-in-button"]')).toBeNull();
    expect(document.body.querySelector('[data-testid="walk-in-note"]')).toBeNull();
    act(() => {
      setInput(container.querySelector('[data-testid="door-phone-input"]'), "98765 00001");
    });
    expect(container.querySelector('[data-testid="door-phone-input"]').value).toBe("98765 00001");
    await act(async () => {
      container.querySelector('[data-testid="door-register-button"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/register", expect.objectContaining({
      full_name: "Aadhaar Scanned User",
      age: 42,
      phone: "9876500001",
      aadhaar_scanned: true,
      qr_payload: CARD_PAYLOAD,
      camp_day_id: "day-1",
    }));
    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-9");
    expect(container.textContent).toContain("Registered and arrived: #109");
    expect(container.querySelector('[data-testid="scan-arrived"]').textContent).toContain("#109");
    expect(container.querySelector('[data-testid="scan-print-button"]')).not.toBeNull();
    expect(container.querySelectorAll('[data-testid="mock-aadhaar-scanner"]').length).toBe(1);
  });

  test("a pre-registration prints nothing and says the SMS went out", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp", venue: "Community Hall" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url, body) => {
      if (url === "/register") {
        return Promise.resolve({ data: { registration: { id: "p-7", reg_no: "107", full_name: body.full_name } } });
      }
      return Promise.resolve({ data: {} });
    });

    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    expect(document.body.querySelector('[data-testid="walk-in-note"]')).toBeNull();

    act(() => {
      modalScanner("mock-scan-trigger").click();
    });
    act(() => {
      setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500001");
    });
    expect(document.body.querySelector('[data-testid="reg-day-select"]').textContent).toBe("27-08-2026 (today)");
    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    expect(api.post).not.toHaveBeenCalledWith("/desk/arrive/p-7");
    expect(container.textContent).toContain("SMS sent");
  });

  function preRegistrationMode() {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url, body) => (url === "/register"
      ? Promise.resolve({ data: { registration: { id: "p-7", reg_no: "107", full_name: body.full_name }, created: true } })
      : Promise.resolve({ data: {} })));
  }

  function registerBodies() {
    return api.post.mock.calls.filter((c) => c[0] === "/register").map((c) => c[1]);
  }

  function cancelRegistration() {
    return [...document.body.querySelectorAll("button")].find((b) => b.textContent === "Cancel");
  }

  test("a scanned registration sends the card payload with the scanned claim", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    act(() => { modalScanner("mock-scan-trigger").click(); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "98765-00001 99"); });
    expect(document.body.querySelector('[data-testid="patient-register-submit"]').disabled).toBe(true);
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "+91 98765-00001"); });
    expect(document.body.querySelector('[data-testid="reg-phone-input"]').value).toBe("+91 98765-00001");
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });

    expect(registerBodies()).toHaveLength(1);
    expect(registerBodies()[0].aadhaar_scanned).toBe(true);
    expect(registerBodies()[0].qr_payload).toBe(CARD_PAYLOAD);
    expect(registerBodies()[0].phone).toBe("9876500001");
  });

  function revealManual() {
    act(() => { modalScanner("reg-manual-toggle").click(); });
    act(() => { modalScanner("manual-reason-no_card").click(); });
    act(() => {
      const gender = document.body.querySelector('[data-testid="reg-gender-select"]');
      gender.value = "F";
      gender.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  test("a manual registration claims no scan and carries no card payload", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    revealManual();
    act(() => { setInput(document.body.querySelector('[data-testid="reg-fullname-input"]'), "Manual Patient"); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-age-input"]'), "44"); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500002"); });
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });

    expect(registerBodies()).toHaveLength(1);
    expect(registerBodies()[0].aadhaar_scanned).toBe(false);
    expect(registerBodies()[0].qr_payload).toBeFalsy();
    expect(registerBodies()[0]).not.toHaveProperty("failed_scan_attempts");
    expect(registerBodies()[0].age).toBe(44);
    expect(registerBodies()[0].manual_reason).toBe("no_card");
  });

  test("a reopened registration cannot reuse the previous patient's card payload", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    act(() => { modalScanner("mock-scan-trigger").click(); });
    await act(async () => { cancelRegistration().click(); });

    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
    revealManual();
    act(() => { setInput(document.body.querySelector('[data-testid="reg-fullname-input"]'), "Second Patient"); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-age-input"]'), "50"); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500003"); });
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });

    expect(registerBodies()).toHaveLength(1);
    expect(registerBodies()[0].full_name).toBe("Second Patient");
    expect(registerBodies()[0].aadhaar_scanned).toBe(false);
    expect(registerBodies()[0].qr_payload).toBeFalsy();
  });

  test("desk does not offer independent mark seen", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/desk/lookup") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" } } });
      }

      return Promise.resolve({ data: {} });
    });

    await renderDesk();
    act(() => {
      setInput(container.querySelector('[data-testid="desk-find-input"]'), "101");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-find-button"]').click();
    });
    expect(container.querySelector('[data-testid="desk-found-patient"]')).not.toBeNull();

    expect(container.querySelector('[data-testid="mark-seen-button-101"]')).toBeNull();
    expect(api.post).not.toHaveBeenCalledWith("/desk/mark-seen/p-1");
  });

  test("name search does not offer mark seen", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 1, seen: 0, pending: 1 } });
      if (url === "/camps/active") {
        return Promise.resolve({ data: { camp: { id: "camp-1", name: "C" }, days: [] } });
      }
      if (url.startsWith("/patients/search")) {
        return Promise.resolve({
          data: { results: [{ ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" }] },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockResolvedValue({ data: { registration: { ...ARRIVED, queue_status: "seen" } } });

    await renderDesk();
    act(() => {
      setInput(container.querySelector('[data-testid="desk-find-input"]'), "Aadhaar");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-find-button"]').click();
    });

    expect(container.querySelector('[data-testid="desk-search-results"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="mark-seen-button-101"]')).toBeNull();
  });

  test("print is offered to an arrived patient and withdrawn once the doctor has seen them", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 2, seen: 1, pending: 1 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "C" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: true }],
          },
        });
      }
      if (url.startsWith("/patients/search")) {
        return Promise.resolve({
          data: {
            results: [
              ARRIVED,
              {
                ...ARRIVED,
                id: "p-2",
                reg_no: "102",
                queue_status: "seen",
                printed_at: "2026-09-01T05:00:00Z",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    await renderDesk();
    act(() => {
      setInput(container.querySelector('[data-testid="desk-find-input"]'), "Aadhaar");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-find-button"]').click();
    });

    expect(container.querySelector('[data-testid="print-button-101"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="print-button-102"]')).toBeNull();
  });

  test("a booking that has not arrived cannot be checked in from a lookup", async () => {
    api.post.mockResolvedValue({
      data: { registration: { ...ARRIVED, queue_status: "registered", arrived_at: null } },
    });
    await renderDesk();
    act(() => {
      setInput(container.querySelector('[data-testid="desk-find-input"]'), "101");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-find-button"]').click();
    });

    expect(container.querySelector('[data-testid="awaiting-scan-101"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="arrive-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="print-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="mark-seen-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="print-button-101"]')).toBeNull();
    expect(api.post).not.toHaveBeenCalledWith("/desk/arrive/p-1");
  });

  async function lookup(registration, days) {
    if (days) {
      api.get.mockImplementation((url) => {
        if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
        if (url === "/camps/active") {
          return Promise.resolve({
            data: { camp: { id: "camp-1", name: "Howrah Eye Camp", venue: "Community Hall" }, days },
          });
        }
        return Promise.resolve({ data: {} });
      });
    }
    api.post.mockImplementation((url) => {
      if (url === "/desk/lookup") return Promise.resolve({ data: { registration } });
      if (url.startsWith("/desk/arrive/")) return Promise.resolve({ data: { registration: { ...registration, arrived_at: "2026-09-01T04:00:00Z" }, prescription: RX } });
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    act(() => {
      setInput(container.querySelector('[data-testid="desk-find-input"]'), "101");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-find-button"]').click();
    });
  }

  test("a QR-locked booking checks in and prints without a door re-scan", async () => {
    await lookup({ ...ARRIVED, queue_status: "registered", arrived_at: null, aadhaar_scanned: true });

    expect(container.querySelector('[data-testid="awaiting-scan-101"]')).toBeNull();
    await act(async () => {
      container.querySelector('[data-testid="print-button-101"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-1");
  });

  test("a closed print window withdraws print and says so instead", async () => {
    await lookup(ARRIVED, [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }]);

    expect(container.querySelector('[data-testid="print-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="print-window-closed-101"]')).not.toBeNull();
  });

  test("a closed print window still reprints a sheet that already printed", async () => {
    await lookup(
      { ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" },
      [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
    );

    expect(container.querySelector('[data-testid="reprint-button-101"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="print-window-closed-101"]')).toBeNull();
  });

  test("a Scan stall does not unlock manual entry", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();

    act(() => {
      modalScanner("mock-stall-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
  });

  test("a Lock before two Failures never reveals a typed path", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
      modalScanner("mock-scan-trigger").click();
    });

    expect(document.body.querySelector('[data-testid="manual-entry-note"]')).toBeNull();
    const name = document.body.querySelector('[data-testid="reg-fullname-input"]');
    expect(name.readOnly).toBe(true);
    expect(name.value).toBe("Aadhaar Scanned User");
  });

  test("closing New Registration resets the Failure count", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
      modalScanner("mock-stall-trigger").click();
      modalScanner("mock-stall-trigger").click();
      modalScanner("mock-stall-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-manual-toggle"]')).not.toBeNull();

    act(() => {
      document.body.querySelector('[data-testid="modal-close-button"]').click();
    });
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
  });

  test("Duplicate in camp 409 shows the existing reg_no and has no override", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url) => {
      if (url === "/register") {
        const err = new Error("Duplicate");
        err.response = {
          data: {
            detail: {
              code: "DUPLICATE_IN_CAMP",
              message: "Already registered in this camp",
              registration: { reg_no: "999" },
            },
          },
        };
        return Promise.reject(err);
      }
      return Promise.resolve({ data: {} });
    });

    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
      modalScanner("mock-scan-trigger").click();
    });
    act(() => {
      setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500001");
    });
    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    expect(document.body.textContent).toContain("Already registered as #999");
    expect(document.body.textContent).not.toContain("Register anyway");
  });

  test("an ambiguous Manual entry match names the candidates and asks for a door scan", async () => {
    preRegistrationMode();
    api.post.mockImplementation((url) => (url === "/register"
      ? Promise.reject(apiError({
        code: "AMBIGUOUS_MANUAL_ENTRY",
        message: "Multiple manual entries",
        registrations: [{ reg_no: "301" }, { reg_no: "302" }],
      }))
      : Promise.resolve({ data: {} })));
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    act(() => { modalScanner("mock-scan-trigger").click(); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500001"); });
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });

    expect(document.body.textContent).toContain("Multiple Manual entries match (#301, #302). Scan the card at the door to pick one.");
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();
  });

  test("an ambiguous scan lists the candidates and checks nobody in", async () => {
    api.post.mockResolvedValueOnce({
      data: {
        outcome: "ambiguous",
        registrations: [
          { id: "a", reg_no: "201", full_name: "Same Name", age: 40 },
          { id: "b", reg_no: "202", full_name: "Same Name", age: 41 },
        ],
      },
    });
    await renderDesk();
    await scanAtDoor();

    expect(container.querySelector('[data-testid="scan-ambiguous"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="ambiguous-201"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="ambiguous-202"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="scan-arrived"]')).toBeNull();
  });

  test("pre-registration mode orders cards and reduces the KPI strip", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 12, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    const cards = [...container.querySelectorAll("[data-desk-card]")].map((el) => el.getAttribute("data-desk-card"));
    expect(cards).toEqual(["prereg", "find"]);
    expect(container.querySelector('[data-testid="kpi-registered-count"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="kpi-seen-count"]')).toBeNull();
    expect(container.querySelector('[data-testid="desk-card-scan"]')).toBeNull();
    expect(container.querySelector('[data-testid="mock-aadhaar-scanner"]')).toBeNull();
    expect(container.textContent).not.toContain("Scan at the door");
  });

  test("pre-registration mode shows a find error with no door card", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 12, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockRejectedValueOnce(new Error("Registration not found"));
    await renderDesk();
    act(() => {
      setInput(container.querySelector('[data-testid="desk-find-input"]'), "404");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-find-button"]').click();
    });
    expect(container.querySelector('[data-testid="desk-card-scan"]')).toBeNull();
    expect(container.textContent).toContain("Registration not found");
  });

  test.each([
    ["secure QR digits", AADHAAR_DIGITS],
    ["old XML QR", '<?xml version="1.0"?><PrintLetterBarcodeData uid="xxxxxxxx8888" name="A"/>'],
  ])("pre-registration find refuses an Aadhaar %s and points to New Registration", async (_label, value) => {
    preRegistrationMode();
    await renderDesk();
    act(() => { setInput(container.querySelector('[data-testid="desk-find-input"]'), value); });
    await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });

    expect(api.post).not.toHaveBeenCalled();
    expect(api.get).not.toHaveBeenCalledWith(expect.stringMatching(/^\/patients\/search/));
    expect(container.textContent).toContain("That is an Aadhaar QR. Use New Registration to register this patient.");
    expect(container.querySelector('[data-testid="desk-find-input"]').value).toBe("");
  });

  test("no camp day today is pre-registration mode", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 3, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-2", day_date: "2026-08-28", is_today: false, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    expect(container.querySelector('[data-testid="desk-card-prereg"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="kpi-seen-count"]')).toBeNull();
  });

  test("server printing_open on a non-today operating day is camp-day mode", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 3, seen: 1, pending: 2 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [
              { id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false },
              { id: "day-2", day_date: "2026-08-28", is_today: false, printing_open: true },
            ],
            printing_open: true,
            operating_day_id: "day-2",
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    expect(container.querySelector('[data-testid="desk-card-prereg"]')).toBeNull();
    expect(container.querySelector('[data-testid="kpi-seen-count"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="desk-card-scan"]')).not.toBeNull();
  });

  test("door walk-in books the operating day, not calendar today", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 3, seen: 1, pending: 2 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [
              { id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false },
              { id: "day-2", day_date: "2026-08-28", is_today: false, printing_open: true },
            ],
            printing_open: true,
            operating_day_id: "day-2",
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url, body) => {
      if (url === "/desk/scan") {
        return Promise.resolve({
          data: {
            outcome: "no_match",
            card: { full_name: "Aadhaar Scanned User", age: 42, gender: "M", address: "10 Downing St, Kolkata", aadhaar_last4: "8888", dob: "1984-05-12" },
          },
        });
      }
      if (url === "/register") {
        return Promise.resolve({ data: { registration: { id: "p-9", reg_no: "109", full_name: body.full_name } } });
      }
      if (url === "/desk/arrive/p-9") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-9", reg_no: "109" } } });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    await scanAtDoor();
    act(() => {
      setInput(container.querySelector('[data-testid="door-phone-input"]'), "9876500001");
    });
    await act(async () => {
      container.querySelector('[data-testid="door-register-button"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/register", expect.objectContaining({
      camp_day_id: "day-2",
      aadhaar_scanned: true,
    }));
    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-9");
  });

  test("door manual books the operating day and arrives them when printing is open", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 3, seen: 1, pending: 2 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp", door_manual_entry: true },
            days: [
              { id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false },
              { id: "day-2", day_date: "2026-08-28", is_today: false, printing_open: true },
            ],
            printing_open: true,
            operating_day_id: "day-2",
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url, body) => {
      if (url === "/register") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-8", reg_no: "108", full_name: body.full_name } } });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    await fillDoorManual("Manual Patient");
    expect(api.post).toHaveBeenCalledWith("/register", expect.objectContaining({
      full_name: "Manual Patient",
      phone: "9876500002",
      camp_day_id: "day-2",
      at_door: true,
      manual_reason: "no_card",
    }));
    expect(registerBodies()[0]).not.toHaveProperty("failed_scan_attempts");
    expect(api.post).not.toHaveBeenCalledWith("/desk/arrive/p-8");
    expect(container.textContent).toContain("Registered and arrived: #108");
  });

  test("a typed door entry never carries the card details of an earlier scan", async () => {
    api.post.mockImplementation((url, body) => {
      if (url === "/desk/scan") {
        return Promise.resolve({ data: { outcome: "no_match", card: { full_name: "Aadhaar Scanned User", aadhaar_last4: "8888", dob: "1984-05-12" } } });
      }
      if (url === "/register") {
        return Promise.resolve({ data: { registration: { id: "p-9", reg_no: "109", full_name: body.full_name } } });
      }
      return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-9", reg_no: "109" } } });
    });
    await renderDesk();
    await scanAtDoor();
    await fillDoorManual("Different Person");
    const register = api.post.mock.calls.find(([url]) => url === "/register")[1];
    expect(register).toEqual(expect.objectContaining({
      full_name: "Different Person", aadhaar_last4: null, dob: null, address: null,
    }));
  });

  test("camp-day mode hides Pre-registration and shows the full KPI strip", async () => {
    await renderDesk();
    const cards = [...container.querySelectorAll("[data-desk-card]")].map((el) => el.getAttribute("data-desk-card"));
    expect(cards).toEqual(["scan", "find"]);
    expect(container.querySelector('[data-testid="desk-card-prereg"]')).toBeNull();
    expect(container.querySelector('[data-testid="kpi-seen-count"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="kpi-pending-count"]')).not.toBeNull();
  });

  test("no number of Failures opens the typed form at the door; only Manual entry does", async () => {
    await renderDesk();
    for (let i = 0; i < 4; i += 1) {
      act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
      expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
    }
    act(() => { container.querySelector('[data-testid="door-manual-button"]').click(); });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();
    expect(document.body.querySelector('[data-testid="reg-day-select"]')).toBeNull();
  });

  test("the door card shows the scanner itself, with no USB panel and no camera fallback", async () => {
    await renderDesk();
    const card = container.querySelector('[data-testid="desk-card-scan"]');
    expect(card.querySelector('[data-testid="mock-aadhaar-scanner"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="wedge-panel"]')).toBeNull();
    expect(container.querySelector('[data-testid="camera-fallback"]')).toBeNull();
    expect(container.querySelector('[data-testid="door-manual-toggle"]')).toBeNull();
  });

  test("a door scan closes an open Manual entry, since a card beats typing", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    act(() => { container.querySelector('[data-testid="door-manual-button"]').click(); });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();
    await scanAtDoor();
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
  });

  test("Manual entry at the door takes patient after patient, each with its own request", async () => {
    api.post.mockImplementation((url, body) => (url === "/register"
      ? Promise.resolve({ data: { registration: { ...ARRIVED, id: `p-${body.full_name}`, reg_no: "108", full_name: body.full_name } } })
      : Promise.resolve({ data: {} })));
    await renderDesk();
    await fillDoorManual("First Patient");
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
    await fillDoorManual("Second Patient");
    expect(registerBodies().map((b) => b.full_name)).toEqual(["First Patient", "Second Patient"]);
    expect(registerBodies()[0].phone).toBe("9876500002");
    expect(registerBodies()[0].registration_request_id).not.toBe(registerBodies()[1].registration_request_id);
    expect(api.post.mock.calls.filter(([url]) => url.startsWith("/desk/arrive"))).toHaveLength(0);
  });

  test("a scanned patient QR is looked up instead of decoded as a card", async () => {
    api.post.mockResolvedValue({ data: { registration: ARRIVED } });
    await renderDesk();
    await act(async () => {
      deskScanner().parentNode.querySelector('[data-testid="mock-patient-code-trigger"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/desk/lookup", { value: "snp:ABC12345" });
    expect(api.post.mock.calls.filter((c) => c[0] === "/desk/scan")).toHaveLength(0);
    expect(container.querySelector('[data-testid="desk-found-patient"]')).not.toBeNull();
  });

  test("switching the registration modal to manual ignores a pending USB decode", async () => {
    api.get.mockImplementation((url) => url === "/camps/active" ? Promise.resolve({ data: { camp: { id: "camp-1" }, days: [{ id: "day-1", printing_open: false }], printing_open: false } }) : Promise.resolve({ data: {} }));
    let resolveDecode;
    api.post.mockImplementation(() => new Promise((resolve) => { resolveDecode = resolve; }));
    await renderDesk();
    act(() => container.querySelector('[data-testid="new-registration-button"]').click());
    await fireBurst(CARD_PAYLOAD);
    act(() => document.querySelector('[data-testid="reg-manual-toggle"]').click());
    act(() => setInput(document.querySelector('[data-testid="reg-fullname-input"]'), "Manual Name"));
    await act(async () => resolveDecode({ data: { outcome: "card", data: { full_name: "Late scan", age: 42 } } }));
    expect(document.querySelector('[data-testid="reg-fullname-input"]').value).toBe("Manual Name");
    expect(document.querySelector('[data-testid="reg-fullname-input"]').readOnly).toBe(false);
  });

  async function openRegistrationForUsb() {
    api.get.mockImplementation((url) => url === "/camps/active" ? Promise.resolve({ data: { camp: { id: "camp-1" }, days: [{ id: "day-1", printing_open: false }], printing_open: false } }) : Promise.resolve({ data: {} }));
    let resolveDecode;
    api.post.mockImplementation(() => new Promise((resolve) => { resolveDecode = resolve; }));
    await renderDesk();
    act(() => container.querySelector('[data-testid="new-registration-button"]').click());
    return (response) => act(async () => resolveDecode(response));
  }

  function wedgeStatus() {
    return document.querySelector('[data-testid="reg-wedge-status"]');
  }

  test("the registration modal says when it is receiving and reading a USB scan", async () => {
    const finishDecode = await openRegistrationForUsb();
    expect(wedgeStatus()).toBeNull();
    let t = Number(performance.now()) || 0;
    const spy = jest.spyOn(performance, "now").mockImplementation(() => t);
    act(() => {
      for (const ch of CARD_PAYLOAD.slice(0, 30)) {
        t += 10;
        document.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true, cancelable: true }));
      }
    });
    expect(wedgeStatus().getAttribute("role")).toBe("status");
    expect(wedgeStatus().textContent).toBe("Receiving from the USB scanner…");
    act(() => {
      for (const ch of CARD_PAYLOAD.slice(30)) {
        t += 10;
        document.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true, cancelable: true }));
      }
      t += 10;
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    spy.mockRestore();
    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: CARD_PAYLOAD });
    expect(wedgeStatus().textContent).toBe("Reading the card…");
    await finishDecode({ data: { outcome: "card", data: { full_name: "Usb Patient", age: 42 } } });
    expect(wedgeStatus()).toBeNull();
    expect(document.querySelector('[data-testid="reg-fullname-input"]').value).toBe("Usb Patient");
  });

  test.each([
    [{ outcome: "garbage", message: "That is not an Aadhaar QR." }, "That is not an Aadhaar QR."],
    [{ outcome: "garbage" }, "Could not read that card. Scan it again."],
  ])("a USB scan that decodes as %o shows an error", async (data, message) => {
    const finishDecode = await openRegistrationForUsb();
    await fireBurst(CARD_PAYLOAD);
    await finishDecode({ data });
    expect(wedgeStatus()).toBeNull();
    expect(document.querySelector('[role="dialog"] [role="alert"]').textContent).toBe(message);
    expect(document.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
  });

  test("the door shows a reading status while the scan resolves", async () => {
    let resolveScan;
    api.post.mockImplementation((url) => url === "/desk/scan" ? new Promise((resolve) => { resolveScan = resolve; }) : Promise.resolve({ data: {} }));
    await renderDesk();
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
    await act(async () => { deskScanner().click(); });
    expect(container.querySelector('[data-testid="door-scan-status"]').textContent).toContain("Reading the QR");
    expect(container.querySelector('[data-testid="mock-aadhaar-scanner"]').getAttribute("data-disabled")).toBe("false");
    await act(async () => resolveScan({ data: { outcome: "arrived", registration: ARRIVED } }));
    expect(container.querySelector('[data-testid="door-scan-status"]')).toBeNull();
  });

  async function fireBurst(text) {
    let t = Number(performance.now()) || 0;
    const spy = jest.spyOn(performance, "now").mockImplementation(() => t);
    await act(async () => {
      for (const ch of text) {
        t += 10;
        document.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true, cancelable: true }));
      }
      t += 10;
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    spy.mockRestore();
  }

  test("the door no longer listens for USB bursts behind the scanner", async () => {
    api.post.mockResolvedValue({ data: { outcome: "arrived", registration: ARRIVED } });
    await renderDesk();
    await fireBurst(CARD_PAYLOAD);
    expect(api.post.mock.calls.filter((c) => c[0] === "/desk/scan")).toHaveLength(0);
  });

  test("a slow lookup cannot land on top of a newer name search", async () => {
    let resolveLookup;
    api.post.mockImplementation((url) => url === "/desk/lookup"
      ? new Promise((resolve) => { resolveLookup = resolve; })
      : Promise.resolve({ data: {} }));
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => url.startsWith("/patients/search")
      ? Promise.resolve({ data: { results: [{ ...ARRIVED, id: "p-2", reg_no: "202", full_name: "Someone Else" }] } })
      : base(url));
    await renderDesk();

    act(() => setInput(container.querySelector('[data-testid="desk-find-input"]'), "101"));
    act(() => { container.querySelector('[data-testid="desk-find-button"]').click(); });

    act(() => setInput(container.querySelector('[data-testid="desk-find-input"]'), "Someone"));
    await act(async () => { container.querySelector('[data-testid="desk-find-button"]').click(); });
    expect(container.querySelector('[data-testid="desk-search-results"]')).not.toBeNull();

    await act(async () => resolveLookup({ data: { registration: ARRIVED } }));
    expect(container.querySelector('[data-testid="desk-found-patient"]')).toBeNull();
    expect(container.querySelector('[data-testid="print-button-101"]')).toBeNull();
  });

  test("a Scan stall at the door does not reveal the typed form", async () => {
    await renderDesk();
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-stall-trigger"]').click(); });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
  });

  async function fillDoorManual(name) {
    const modal = (id) => document.body.querySelector(`[data-testid="${id}"]`);
    act(() => { container.querySelector('[data-testid="door-manual-button"]').click(); });
    act(() => {
      setInput(modal("reg-fullname-input"), name);
      setInput(modal("reg-age-input"), "40");
      setInput(modal("reg-phone-input"), "+91 98765 00002");
    });
    act(() => {
      modal("manual-reason-no_card").click();
      modal("reg-gender-select").value = "F";
      modal("reg-gender-select").dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => { modal("patient-register-submit").click(); });
  }

  function noMatch(name) {
    return { data: { outcome: "no_match", card: { full_name: name, age: 42, gender: "M", address: "Sikar", aadhaar_last4: "8888", dob: "1984-05-12" } } };
  }

  function doorPhone() {
    return container.querySelector('[data-testid="door-phone-input"]');
  }

  test("each walk-in starts with an empty household phone", async () => {
    api.post.mockResolvedValueOnce(noMatch("Patient A")).mockResolvedValueOnce(noMatch("Patient B")).mockResolvedValueOnce(noMatch("Patient C"));
    await renderDesk();
    await scanAtDoor();
    act(() => setInput(doorPhone(), "9876500001"));
    await scanAtDoor();
    expect(container.querySelector('[data-testid="door-card-name"]').textContent).toContain("Patient B");
    expect(doorPhone().value).toBe("");
    act(() => setInput(doorPhone(), "9876500002"));
    act(() => { container.querySelector('[data-testid="mock-capture-start"]').click(); });
    await scanAtDoor();
    expect(container.querySelector('[data-testid="door-card-name"]').textContent).toContain("Patient C");
    expect(doorPhone().value).toBe("");
  });

  test("a walk-in with no booking puts the cursor in the phone field", async () => {
    api.post.mockResolvedValueOnce(noMatch("Patient A"));
    await renderDesk();
    await scanAtDoor();
    expect(document.activeElement).toBe(doorPhone());
  });

  test.each([
    ["door manual", async () => {
      await renderDesk();
      await fillDoorManual("Timed Out");
    }, async () => { await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); }); }],
    ["walk-in", async () => {
      await renderDesk();
      await scanAtDoor();
      act(() => setInput(doorPhone(), "9876500001"));
      await act(async () => { container.querySelector('[data-testid="door-register-button"]').click(); });
    }, async () => { await act(async () => { container.querySelector('[data-testid="door-register-button"]').click(); }); }],
  ])("a %s request-id conflict points to search and the next try uses a new id", async (_path, first, again) => {
    api.post.mockImplementation((url) => {
      if (url === "/desk/scan") return Promise.resolve(noMatch("Patient A"));
      if (url === "/register") {
        return Promise.reject(apiError({ code: "REGISTRATION_REQUEST_CONFLICT", message: "Request id reused." }));
      }
      return Promise.resolve({ data: {} });
    });
    await first();
    expect(document.body.textContent).toContain("Saved earlier. Search for the patient.");
    await again();
    const ids = registerBodies().map((b) => b.registration_request_id);
    expect(ids).toHaveLength(2);
    expect(ids[0]).not.toBe(ids[1]);
  });

  test("a registration-desk request-id conflict points to search and the next try uses a new id", async () => {
    preRegistrationMode();
    api.post.mockImplementation((url) => (url === "/register"
      ? Promise.reject(apiError({ code: "REGISTRATION_REQUEST_CONFLICT", message: "Request id reused." }))
      : Promise.resolve({ data: {} })));
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    act(() => { modalScanner("mock-scan-trigger").click(); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500001"); });
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });
    expect(document.body.textContent).toContain("Saved earlier. Search for the patient.");
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });
    const ids = registerBodies().map((b) => b.registration_request_id);
    expect(ids[0]).not.toBe(ids[1]);
  });

  test("New Registration needs a valid household phone and an age", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    revealManual();
    const field = (id) => document.body.querySelector(`[data-testid="${id}"]`);
    const submit = () => field("patient-register-submit");
    act(() => {
      setInput(field("reg-fullname-input"), "Manual Patient");
      setInput(field("reg-phone-input"), "9876500002");
    });
    expect(submit().disabled).toBe(true);
    act(() => setInput(field("reg-age-input"), "4a0"));
    expect(field("reg-age-input").value).toBe("40");
    expect(field("reg-age-input").type).toBe("text");
    expect(field("reg-age-input").inputMode).toBe("numeric");
    expect(submit().disabled).toBe(false);
    act(() => setInput(field("reg-phone-input"), "98765"));
    expect(submit().disabled).toBe(true);
    act(() => setInput(field("reg-phone-input"), "+91 98765 00002"));
    act(() => setInput(field("reg-last4-input"), "12a345"));
    expect(field("reg-last4-input").value).toBe("1234");
    await act(async () => { submit().click(); });
    expect(registerBodies()[0]).toEqual(expect.objectContaining({ phone: "9876500002", age: 40, aadhaar_last4: "1234" }));
  });

  test("the door typed form takes only digits for age", async () => {
    await renderDesk();
    act(() => { container.querySelector('[data-testid="door-manual-button"]').click(); });
    const age = document.body.querySelector('[data-testid="reg-age-input"]');
    act(() => setInput(age, "6x5"));
    expect(age.value).toBe("65");
    expect(age.type).toBe("text");
    expect(age.inputMode).toBe("numeric");
  });

  test("a scan in pre-registration opens New Registration with the card and the phone field focused", async () => {
    preRegistrationMode();
    api.post.mockImplementation((url) => (url === "/aadhaar/decode"
      ? Promise.resolve({ data: { outcome: "card", data: { full_name: "Usb Patient", age: 42, gender: "F" } } })
      : Promise.resolve({ data: {} })));
    await renderDesk();
    const find = container.querySelector('[data-testid="desk-find-input"]');
    find.focus();
    await fireBurst(CARD_PAYLOAD);
    expect(api.post).toHaveBeenCalledWith("/aadhaar/decode", { payload: CARD_PAYLOAD });
    expect(api.post.mock.calls.filter(([url]) => url === "/aadhaar/decode")).toHaveLength(1);
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    expect(document.querySelector('[data-testid="reg-fullname-input"]').value).toBe("Usb Patient");
    expect(document.activeElement).toBe(document.querySelector('[data-testid="reg-phone-input"]'));
    expect(find.value).toBe("");
  });

  test("a card read in New Registration moves the cursor to the phone field", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    act(() => { modalScanner("mock-scan-trigger").click(); });
    expect(document.activeElement).toBe(document.querySelector('[data-testid="reg-phone-input"]'));
  });

  test("Register & next saves and leaves a clean form for the next patient", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    for (const phone of ["9876500001", "9876500002"]) {
      act(() => { modalScanner("mock-scan-trigger").click(); });
      act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), phone); });
      await act(async () => { document.body.querySelector('[data-testid="patient-register-next"]').click(); });
      expect(document.querySelector('[role="dialog"]')).not.toBeNull();
      expect(document.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
    }
    expect(registerBodies().map((b) => b.phone)).toEqual(["9876500001", "9876500002"]);
    expect(registerBodies()[0].registration_request_id).not.toBe(registerBodies()[1].registration_request_id);
    expect(container.textContent).toContain("Registered #107");
    expect(container.querySelector('[data-testid="kpi-registered-count"]').textContent).toBe("47");
  });

  test("a card that differs from a Manual entry goes through Mismatch review at the registration desk", async () => {
    preRegistrationMode();
    const manual = { id: "p-3", reg_no: "103", full_name: "Aadhaar Scanned User" };
    api.post.mockImplementationOnce(() => Promise.reject(Object.assign(new Error("409"), { response: { status: 409, data: { detail: {
      code: "MISMATCH_REVIEW_REQUIRED",
      message: "Review the card against the Manual entry.",
      registration: manual,
      card: { full_name: "Aadhaar Scanned User", age: 42 },
      diff: [{ field: "age", stored: 30, card: 42 }],
    } } } })));
    api.post.mockImplementationOnce(() => Promise.resolve({ data: { registration: { ...manual, aadhaar_scanned: true } } }));
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    act(() => { modalScanner("mock-scan-trigger").click(); });
    act(() => { setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500001"); });
    await act(async () => { document.body.querySelector('[data-testid="patient-register-submit"]').click(); });
    const review = document.querySelector('[data-testid="mismatch-review"]');
    expect(review.querySelector('[data-testid="diff-age"]').textContent).toContain("30");
    expect(review.querySelector('[data-testid="diff-age"]').textContent).toContain("42");
    await act(async () => { review.querySelector('[data-testid="mismatch-confirm-button"]').click(); });
    expect(registerBodies()[1].review_confirmed_id).toBe("p-3");
    expect(registerBodies()[1].registration_request_id).toBe(registerBodies()[0].registration_request_id);
    expect(registerBodies()[0].review_confirmed_id).toBeNull();
    expect(container.textContent).toContain("Registered #103");
  });

  test("the door scanner stays live while a check-in is pending, and the late reply is dropped", async () => {
    let finishConfirm;
    api.post.mockImplementation((url) => {
      if (url === "/desk/scan/confirm") return new Promise((done) => { finishConfirm = done; });
      return Promise.resolve({ data: { outcome: "mismatch_review", registration: ARRIVED, diff: [] } });
    });
    await renderDesk();
    await scanAtDoor();
    await act(async () => { container.querySelector('[data-testid="mismatch-confirm-button"]').click(); });
    expect(container.querySelector('[data-testid="mock-aadhaar-scanner"]').getAttribute("data-disabled")).toBe("false");
    api.post.mockImplementation(() => Promise.resolve(noMatch("Next Patient")));
    await scanAtDoor();
    await act(async () => finishConfirm({ data: { outcome: "arrived", registration: ARRIVED } }));
    expect(container.querySelector('[data-testid="scan-no-match"]')).not.toBeNull();
    expect(container.textContent).not.toContain("Arrived: #101");
  });

  test("a walk-in reply that lands after the next scan is dropped", async () => {
    let finishArrive;
    api.post.mockImplementation((url, body) => {
      if (url === "/desk/scan") return Promise.resolve(noMatch("Patient A"));
      if (url === "/register") return Promise.resolve({ data: { registration: { id: "p-9", reg_no: "109", full_name: body.full_name } } });
      return new Promise((done) => { finishArrive = done; });
    });
    await renderDesk();
    await scanAtDoor();
    act(() => setInput(doorPhone(), "9876500001"));
    await act(async () => { container.querySelector('[data-testid="door-register-button"]').click(); });
    api.post.mockImplementation(() => Promise.resolve(noMatch("Patient B")));
    await scanAtDoor();
    await act(async () => finishArrive({ data: { registration: { ...ARRIVED, id: "p-9", reg_no: "109" } } }));
    expect(container.querySelector('[data-testid="door-card-name"]').textContent).toContain("Patient B");
    expect(container.querySelector('[data-testid="scan-arrived"]')).toBeNull();
  });

  test("an arrival does not refetch the desk, and a walk-in adds one to the counts", async () => {
    api.post.mockImplementation((url, body) => {
      if (url === "/desk/scan") return Promise.resolve(noMatch("Patient A"));
      if (url === "/register") return Promise.resolve({ data: { registration: { id: "p-9", reg_no: "109", full_name: body.full_name }, created: true } });
      return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-9", reg_no: "109" } } });
    });
    await renderDesk();
    const fetches = () => api.get.mock.calls.filter(([url]) => url === "/kpis" || url === "/camps/active").length;
    const before = fetches();
    await scanAtDoor();
    act(() => setInput(doorPhone(), "9876500001"));
    await act(async () => { container.querySelector('[data-testid="door-register-button"]').click(); });
    expect(fetches()).toBe(before);
    expect(container.querySelector('[data-testid="kpi-registered-count"]').textContent).toBe("46");
    expect(container.querySelector('[data-testid="kpi-pending-count"]').textContent).toBe("15");
  });

  test("the desk refreshes its operating state every 30 seconds while visible, keeping typed work", async () => {
    jest.useFakeTimers();
    try {
      let pending = 15;
      const base = api.get.getMockImplementation();
      api.get.mockImplementation(async (url) => {
        const r = await base(url);
        return url === "/kpis" ? { data: { ...r.data, pending } } : r;
      });
      await renderDesk();
      const campFetches = () => api.get.mock.calls.filter(([url]) => url === "/camps/active").length;
      expect(campFetches()).toBe(1);
      pending = 9;
      await act(async () => { jest.advanceTimersByTime(30000); });
      expect(campFetches()).toBe(2);
      expect(container.querySelector('[data-testid="kpi-pending-count"]').textContent).toBe("9");
      act(() => { container.querySelector('[data-testid="door-manual-button"]').click(); });
      act(() => setInput(document.body.querySelector('[data-testid="reg-fullname-input"]'), "Half Typed"));
      Object.defineProperty(document, "hidden", { configurable: true, value: true });
      await act(async () => { jest.advanceTimersByTime(30000); });
      expect(campFetches()).toBe(2);
      Object.defineProperty(document, "hidden", { configurable: true, value: false });
      await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
      expect(campFetches()).toBe(3);
      expect(document.body.querySelector('[data-testid="reg-fullname-input"]').value).toBe("Half Typed");
    } finally {
      Object.defineProperty(document, "hidden", { configurable: true, value: false });
      jest.useRealTimers();
    }
  });

  test("a background refresh keeps a half-typed New Registration", async () => {
    jest.useFakeTimers();
    try {
      preRegistrationMode();
      await renderDesk();
      act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
      revealManual();
      act(() => setInput(document.body.querySelector('[data-testid="reg-fullname-input"]'), "Half Typed"));
      await act(async () => { jest.advanceTimersByTime(30000); });
      expect(api.get.mock.calls.filter(([url]) => url === "/camps/active")).toHaveLength(2);
      expect(document.body.querySelector('[data-testid="reg-fullname-input"]').value).toBe("Half Typed");
    } finally {
      jest.useRealTimers();
    }
  });

  test("a half-typed New Registration asks before it is discarded", async () => {
    preRegistrationMode();
    await renderDesk();
    act(() => { container.querySelector('[data-testid="new-registration-button"]').click(); });
    revealManual();
    act(() => setInput(document.body.querySelector('[data-testid="reg-fullname-input"]'), "Half Typed"));
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(false);
    act(() => document.querySelector('[role="presentation"]').click());
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(confirm).toHaveBeenCalledWith("Discard changes?");
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    confirm.mockRestore();
  });

  test("the scan outcome is announced and registration numbers read at AA contrast", async () => {
    api.post.mockResolvedValueOnce({ data: { registration: ARRIVED } });
    await renderDesk();
    expect(container.querySelector('[data-testid="door-scan-outcome"]').getAttribute("aria-live")).toBe("polite");
    await act(async () => { container.querySelector('[data-testid="mock-patient-code-trigger"]').click(); });
    const regNo = container.querySelector('[data-testid="patient-row-101"] .font-mono');
    expect(regNo.className).toContain("text-emerald-700");
  });

  test("Mismatch review of a scanned registration says nothing is replaced", async () => {
    api.post.mockResolvedValueOnce({ data: {
      outcome: "mismatch_review",
      registration: { ...ARRIVED, aadhaar_scanned: true, manual_entry: false, arrived_at: null },
      diff: [{ field: "dob", stored: "1960-01-01", card: "1962-01-01" }],
    } });
    await renderDesk();
    await scanAtDoor();
    const review = container.querySelector('[data-testid="mismatch-review"]').textContent;
    expect(review).toContain("registered from another card");
    expect(review).not.toContain("replaces the stored values");
  });

  const ARRIVED_SCAN = { data: { outcome: "arrived", registration: ARRIVED, prescription: RX } };

  function stampCalls() {
    return api.post.mock.calls.filter(([url]) => url.startsWith("/desk/print/"));
  }

  function paperCheck() {
    return document.querySelector('[data-testid="paper-check"]');
  }

  function paperButton(name) {
    return document.querySelector(`[data-testid="paper-check-${name}"]`);
  }

  async function printFromDoor() {
    await scanAtDoor();
    await act(async () => { container.querySelector('[data-testid="scan-print-button"]').click(); });
  }

  test("Print stays on the Desk, prints the scanned prescription and asks for a Paper check", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    expect(window.print).toHaveBeenCalledTimes(1);
    expect(printedText[0]).toContain("Aadhaar Scanned User");
    expect(printedText[0]).toContain("#101");
    expect(api.get).not.toHaveBeenCalledWith("/desk/print/p-1");
    expect(stampCalls()).toHaveLength(0);
    expect(paperCheck().textContent).toContain("#101");
    expect(document.activeElement).toBe(paperButton("confirm"));
    expect(document.getElementById("print-root")).toBeNull();
  });

  test("Escape on the Paper check records nothing and keeps the patient", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(paperCheck()).toBeNull();
    expect(stampCalls()).toHaveLength(0);
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    expect(container.textContent).toContain("Not recorded as printed");
  });

  test("Printed — next patient sends one stamp, clears the card and puts the cursor in the USB box", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN)
      .mockResolvedValueOnce({ data: { registration: { ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" }, prescription: RX } });
    await renderDesk();
    await printFromDoor();
    await act(async () => { paperButton("confirm").click(); });
    expect(stampCalls()).toEqual([["/desk/print/p-1"]]);
    expect(paperCheck()).toBeNull();
    expect(container.querySelector('[data-testid="scan-arrived"]')).toBeNull();
    expect(container.textContent).toContain("Printed #101");
    expect(document.activeElement).toBe(container.querySelector('[data-testid="mock-usb-box"]'));
  });

  test("a failed stamp offers Retry and never advances", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN)
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { registration: { ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" }, prescription: RX } });
    await renderDesk();
    await printFromDoor();
    await act(async () => { paperButton("confirm").click(); });
    expect(paperCheck().textContent).toContain("Network Error");
    expect(paperButton("confirm").textContent).toBe("Retry");
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    await act(async () => { paperButton("confirm").click(); });
    expect(stampCalls()).toHaveLength(2);
    expect(paperCheck()).toBeNull();
  });

  test("Print again prints the sheet once more and still records nothing", async () => {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/desk/print/p-1"
      ? Promise.resolve({ data: { registration: ARRIVED, prescription: RX } }) : base(url)));
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    await act(async () => { paperButton("print-again").click(); });
    expect(window.print).toHaveBeenCalledTimes(2);
    expect(paperCheck()).not.toBeNull();
    expect(stampCalls()).toHaveLength(0);
  });

  test("Printer problem keeps the patient on the card and says nothing was recorded", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    await act(async () => { paperButton("problem").click(); });
    expect(paperCheck()).toBeNull();
    expect(stampCalls()).toHaveLength(0);
    expect(container.querySelector('[data-testid="scan-print-button"]')).not.toBeNull();
    expect(container.textContent).toContain("Nothing was recorded");
  });

  test("two patients in a row fetch the sponsor logos once", async () => {
    const stamped = { data: { registration: { ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" }, prescription: RX } };
    api.post.mockResolvedValueOnce(ARRIVED_SCAN).mockResolvedValueOnce(stamped)
      .mockResolvedValueOnce(ARRIVED_SCAN).mockResolvedValueOnce(stamped);
    await renderDesk();
    for (let i = 0; i < 2; i += 1) {
      await printFromDoor();
      await act(async () => { paperButton("confirm").click(); });
    }
    expect(window.print).toHaveBeenCalledTimes(2);
    expect(api.get.mock.calls.filter(([url]) => url.startsWith("/templates/logos"))).toHaveLength(1);
  });

  test("a patient switch while the print is pending never stamps the old patient", async () => {
    window.print = jest.fn();
    api.post.mockResolvedValueOnce(ARRIVED_SCAN).mockResolvedValueOnce({
      data: { outcome: "no_match", card: { full_name: "Next Patient" } },
    });
    await renderDesk();
    await printFromDoor();
    expect(window.print).toHaveBeenCalledTimes(1);
    await scanAtDoor();
    await act(async () => { window.dispatchEvent(new Event("afterprint")); });
    expect(paperCheck()).toBeNull();
    expect(stampCalls()).toHaveLength(0);
    expect(container.querySelector('[data-testid="door-card-name"]').textContent).toContain("Next Patient");
  });

  test("a found patient prints from the server's prescription", async () => {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/desk/print/p-1"
      ? Promise.resolve({ data: { registration: ARRIVED, prescription: RX } }) : base(url)));
    await lookup(ARRIVED);
    await act(async () => { container.querySelector('[data-testid="print-button-101"]').click(); });
    expect(api.get).toHaveBeenCalledWith("/desk/print/p-1");
    expect(window.print).toHaveBeenCalledTimes(1);
    expect(paperCheck()).not.toBeNull();
  });

  test("sponsor logos that cannot load are named on the Desk, and the prescription still prints", async () => {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url.startsWith("/templates/logos") ? Promise.reject(new Error("down")) : base(url)));
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    expect(container.querySelector('[data-testid="logo-status"]').textContent).toContain("Sponsor logos unavailable");
    await printFromDoor();
    expect(window.print).toHaveBeenCalledTimes(1);
    expect(paperCheck()).not.toBeNull();
  });

  test("after Printer problem, Print asks the server again instead of reusing the scanned sheet", async () => {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/desk/print/p-1"
      ? Promise.reject(apiError({ code: "PRINT_WINDOW_CLOSED", message: "The print window is closed." })) : base(url)));
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    await act(async () => { paperButton("problem").click(); });
    await act(async () => { container.querySelector('[data-testid="scan-print-button"]').click(); });
    expect(api.get).toHaveBeenCalledWith("/desk/print/p-1");
    expect(window.print).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("The print window is closed.");
  });

  test("Print again asks the server again and a second tap cannot start a second print", async () => {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/desk/print/p-1"
      ? Promise.resolve({ data: { registration: ARRIVED, prescription: RX } }) : base(url)));
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    window.print = jest.fn();
    await act(async () => { paperButton("print-again").click(); });
    expect(api.get).toHaveBeenCalledWith("/desk/print/p-1");
    expect(window.print).toHaveBeenCalledTimes(1);
    await act(async () => { container.querySelector('[data-testid="scan-print-button"]').click(); });
    expect(window.print).toHaveBeenCalledTimes(1);
    await act(async () => { window.dispatchEvent(new Event("afterprint")); });
    expect(paperCheck()).not.toBeNull();
  });

  test("a scan while the Paper check is open closes it without a stamp", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN).mockResolvedValueOnce({
      data: { outcome: "no_match", card: { full_name: "Next Patient" } },
    });
    await renderDesk();
    await printFromDoor();
    await scanAtDoor();
    expect(paperCheck()).toBeNull();
    expect(stampCalls()).toHaveLength(0);
  });

  test("a space from a scanner burst never confirms the Paper check", async () => {
    api.post.mockResolvedValueOnce(ARRIVED_SCAN);
    await renderDesk();
    await printFromDoor();
    for (const type of ["keydown", "keyup"]) {
      const space = new KeyboardEvent(type, { key: " ", bubbles: true, cancelable: true });
      paperButton("confirm").dispatchEvent(space);
      expect(space.defaultPrevented).toBe(true);
    }
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    paperButton("confirm").dispatchEvent(enter);
    expect(enter.defaultPrevented).toBe(false);
  });
});

describe("Manual entry, Pending and Reprint (ADR 0084)", () => {
  const q = (id) => document.body.querySelector(`[data-testid="${id}"]`);
  const registered = () => api.post.mock.calls.filter((c) => c[0] === "/register").map((c) => c[1]);
  const PRINTED = { ...ARRIVED, printed_at: "2026-09-01T04:42:00Z", printed_by_name: "Ramesh" };
  const lookalikes = (registrations) => Object.assign(new Error("Request failed with status code 409"), {
    response: { status: 409, data: { detail: { code: "LOOKALIKES", registrations } } },
  });

  function typeManual(name = "Kamla Bai") {
    act(() => {
      setInput(q("reg-fullname-input"), name);
      setInput(q("reg-age-input"), "62");
      setInput(q("reg-phone-input"), "9876500011");
    });
    act(() => {
      const gender = q("reg-gender-select");
      gender.value = "F";
      gender.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  async function findTyped(value) {
    act(() => { setInput(q("desk-find-input"), value); });
    await act(async () => { q("desk-find-button").click(); });
  }

  test("the Pending count opens who is printed and waiting for the doctor", async () => {
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/pending"
      ? Promise.resolve({ data: { patients: [PRINTED] } })
      : base(url)));
    await renderDesk();
    await act(async () => { q("kpi-pending-count-button").click(); });
    const row = q("pending-row-101");
    expect(row.textContent).toContain("Aadhaar Scanned User");
    expect(row.textContent).toContain("9876543210");
    expect(row.textContent).toContain("Printed 10:12 by Ramesh");
    expect(row.querySelector("button")).toBeNull();
  });

  test("a volunteer opens Manual entry under the door scanner, picks a reason and it prints at once", async () => {
    mockAuth.user = { id: "u2", name: "Vol", role: "volunteer" };
    api.post.mockImplementation((url, sent) => (url === "/register"
      ? Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-8", reg_no: "108", full_name: sent.full_name }, created: true } })
      : Promise.resolve({ data: {} })));
    await renderDesk();
    act(() => { container.querySelector('[data-testid="desk-card-scan"] [data-testid="door-manual-button"]').click(); });
    typeManual();
    expect(q("patient-register-submit").disabled).toBe(true);
    act(() => { q("manual-reason-no_card").click(); });
    await act(async () => { q("patient-register-submit").click(); });

    expect(registered()[0]).toEqual(expect.objectContaining({
      full_name: "Kamla Bai", gender: "F", camp_day_id: "day-1", at_door: true,
      manual_reason: "no_card", manual_note: null, different_person: false,
    }));
    expect(container.textContent).toContain("Registered and arrived: #108");
    expect(q("print-button-108")).not.toBeNull();
  });

  test("a card in hand needs its last-4, and Other needs a note, before Register", async () => {
    await renderDesk();
    act(() => { q("door-manual-button").click(); });
    typeManual();
    act(() => { q("manual-reason-card_unreadable").click(); });
    expect(q("patient-register-submit").disabled).toBe(true);
    act(() => { setInput(q("reg-last4-input"), "4321"); });
    expect(q("patient-register-submit").disabled).toBe(false);
    act(() => { q("manual-reason-other").click(); });
    expect(q("patient-register-submit").disabled).toBe(true);
    act(() => { setInput(q("manual-reason-note"), "Card is with her son"); });
    expect(q("patient-register-submit").disabled).toBe(false);
  });

  test("a Lookalike is shown before saving, and Different person registers anyway", async () => {
    const seen = { ...ARRIVED, id: "p-3", reg_no: "103", full_name: "Ram Kumar", queue_status: "seen", phone: "9876500021" };
    api.post.mockImplementation((url, sent) => {
      if (url !== "/register") return Promise.resolve({ data: {} });
      if (!sent.different_person) return Promise.reject(lookalikes([seen]));
      return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-8", reg_no: "108" }, created: true } });
    });
    await renderDesk();
    act(() => { q("door-manual-button").click(); });
    typeManual("Kumar Ram");
    act(() => { q("manual-reason-no_card").click(); });
    await act(async () => { q("patient-register-submit").click(); });

    expect(q("lookalike-103").textContent).toContain("Doctor seen");
    expect(q("lookalike-103").textContent).toContain("0021");
    await act(async () => { q("lookalike-different").click(); });
    expect(registered()).toHaveLength(2);
    expect(registered()[1].different_person).toBe(true);
  });

  test("This is them opens the existing registration instead of saving a second one", async () => {
    const seen = { ...ARRIVED, id: "p-3", reg_no: "103", full_name: "Ram Kumar", queue_status: "seen" };
    api.post.mockImplementation((url) => (url === "/register" ? Promise.reject(lookalikes([seen])) : Promise.resolve({ data: {} })));
    await renderDesk();
    act(() => { q("door-manual-button").click(); });
    typeManual("Ram Kumar");
    act(() => { q("manual-reason-no_card").click(); });
    await act(async () => { q("patient-register-submit").click(); });
    await act(async () => { q("lookalike-open-103").click(); });

    expect(q("patient-register-submit")).toBeNull();
    expect(q("desk-found-patient").textContent).toContain("#103");
    expect(q("print-button-103")).toBeNull();
    expect(registered()).toHaveLength(1);
  });

  test("a door scan of a printed patient says so and offers no print", async () => {
    api.post.mockResolvedValueOnce({ data: { outcome: "arrived", registration: PRINTED, prescription: null } });
    await renderDesk();
    await scanAtDoor();
    expect(q("scan-print-button")).toBeNull();
    expect(q("scan-already-printed").textContent).toContain("Already printed at 10:12 by Ramesh");
  });

  test("a typed reg number or name offers Reprint; a Patient code read does not", async () => {
    api.post.mockImplementation((url) => (url === "/desk/lookup"
      ? Promise.resolve({ data: { registration: PRINTED } })
      : Promise.resolve({ data: {} })));
    const base = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url.startsWith("/patients/search")
      ? Promise.resolve({ data: { results: [PRINTED] } })
      : base(url)));
    await renderDesk();
    await act(async () => { container.querySelector('[data-testid="mock-patient-code-trigger"]').click(); });
    expect(q("reprint-button-101")).toBeNull();
    expect(q("print-button-101")).toBeNull();
    expect(q("already-printed-101").textContent).toContain("find them by name or reg #");

    await findTyped("101");
    expect(q("reprint-button-101")).not.toBeNull();
    expect(q("desk-found-patient").textContent).toContain("Printed 10:12 by Ramesh");

    await findTyped("Aadhaar");
    expect(q("desk-search-results").querySelector('[data-testid="reprint-button-101"]')).not.toBeNull();
  });

  test("a typed booking with no card at the door gets a No-card print from a volunteer", async () => {
    mockAuth.user = { id: "u2", name: "Vol", role: "volunteer" };
    const typed = {
      ...ARRIVED, queue_status: "registered", arrived_at: null, aadhaar_scanned: false,
      manual_entry: true, identity_recheck_required: true,
    };
    api.post.mockImplementation((url) => {
      if (url === "/desk/lookup") return Promise.resolve({ data: { registration: typed } });
      if (url === "/desk/no-card") {
        return Promise.resolve({ data: { registration: { ...typed, identity_recheck_required: false, no_card_print: true } } });
      }
      if (url.startsWith("/desk/arrive/")) {
        return Promise.resolve({ data: { registration: { ...typed, arrived_at: "2026-09-01T04:00:00Z" }, prescription: RX } });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    await findTyped("101");
    expect(q("awaiting-scan-101")).not.toBeNull();
    expect(q("print-button-101")).toBeNull();
    act(() => { q("no-card-101").click(); });
    expect(q("no-card-submit-101").disabled).toBe(true);
    act(() => { q("no-card-reason-101-no_card").click(); });
    await act(async () => { q("no-card-submit-101").click(); });

    expect(api.post).toHaveBeenCalledWith("/desk/no-card", { patient_id: "p-1", reason: "no_card", note: null });
    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-1");
    expect(window.print).toHaveBeenCalled();
  });

  test("Pre-registration offers Manual entry at once, with no failed scans first", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 45, seen: 0, pending: 0 } });
      if (url === "/camps/active") {
        return Promise.resolve({
          data: {
            camp: { id: "camp-1", name: "Howrah Eye Camp" },
            days: [{ id: "day-1", day_date: "2026-08-27", is_today: true, printing_open: false }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockImplementation((url, sent) => (url === "/register"
      ? Promise.resolve({ data: { registration: { id: "p-7", reg_no: "107", full_name: sent.full_name }, created: true } })
      : Promise.resolve({ data: {} })));
    await renderDesk();
    act(() => { q("new-registration-button").click(); });
    act(() => { q("reg-manual-toggle").click(); });
    typeManual();
    act(() => { q("manual-reason-no_card").click(); });
    await act(async () => { q("patient-register-submit").click(); });

    expect(registered()[0]).toEqual(expect.objectContaining({
      at_door: false, manual_reason: "no_card", camp_day_id: "day-1", aadhaar_scanned: false,
    }));
  });
});
