import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Desk from "./Desk";
import api from "../lib/api";

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
  return function MockAadhaarScanner({ onScanned, onFailure, onScanStall }) {
    return (
      <div data-testid="mock-aadhaar-scanner">
        <button
          type="button"
          data-testid="mock-scan-trigger"
          onClick={() =>
            onScanned(
              {
                full_name: "Aadhaar Scanned User",
                age: 42,
                gender: "M",
                address: "10 Downing St, Kolkata",
                aadhaar_last4: "8888",
                dob: "1984-05-12",
              },
              "AADHAAR|Aadhaar Scanned User|M|1984-05-12|8888|10 Downing St, Kolkata"
            )
          }
        >
          Simulate Scan
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
          onClick={() => onScanStall && onScanStall()}
        >
          Simulate Scan stall
        </button>
      </div>
    );
  };
});

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

function setInput(el, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
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

async function renderDesk() {
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

describe("Desk page", () => {
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
    expect(container.textContent).toContain("Decoding Aadhaar");
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

    expect(api.post).toHaveBeenCalledWith("/desk/scan", { payload: CARD_PAYLOAD });
    expect(container.querySelector('[data-testid="scan-arrived"]')).not.toBeNull();
    expect(container.textContent).toContain("Checked in #101");
    expect(container.querySelector('[data-testid="scan-print-button"]')).not.toBeNull();
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
      .toContain("2026-08-28");
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
      setInput(container.querySelector('[data-testid="door-phone-input"]'), "9876500001");
    });
    await act(async () => {
      container.querySelector('[data-testid="door-register-button"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/register", expect.objectContaining({
      full_name: "Aadhaar Scanned User",
      age: 42,
      phone: "9876500001",
      aadhaar_scanned: true,
      manual_entry: false,
      camp_day_id: "day-1",
    }));
    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-9");
    expect(container.textContent).toContain("Registered and checked in #109");
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
    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    expect(api.post).not.toHaveBeenCalledWith("/desk/arrive/p-7");
    expect(container.textContent).toContain("SMS sent");
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
      setInput(container.querySelector('[data-testid="desk-lookup-input"]'), "101");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-lookup-button"]').click();
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
      setInput(container.querySelector('[data-testid="desk-name-search-input"]'), "Aadhaar");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-name-search-button"]').click();
    });

    expect(container.querySelector('[data-testid="desk-search-results"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="mark-seen-button-101"]')).toBeNull();
  });

  test("print is offered to an arrived patient and withdrawn once the doctor has seen them", async () => {
    api.get.mockImplementation((url) => {
      if (url === "/kpis") return Promise.resolve({ data: { registered: 2, seen: 1, pending: 1 } });
      if (url === "/camps/active") {
        return Promise.resolve({ data: { camp: { id: "camp-1", name: "C" }, days: [] } });
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
      setInput(container.querySelector('[data-testid="desk-name-search-input"]'), "Aadhaar");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-name-search-button"]').click();
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
      setInput(container.querySelector('[data-testid="desk-lookup-input"]'), "101");
    });
    await act(async () => {
      container.querySelector('[data-testid="desk-lookup-button"]').click();
    });

    expect(container.querySelector('[data-testid="awaiting-scan-101"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="arrive-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="print-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="mark-seen-button-101"]')).toBeNull();
    expect(api.post).not.toHaveBeenCalledWith("/desk/arrive/p-1");
  });

  test("three Failures reveal the typed form and there is no Register anyway", async () => {
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
      modalScanner("mock-failure-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();

    act(() => {
      modalScanner("mock-failure-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();
    act(() => {
      modalScanner("mock-failure-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();
    expect(document.body.querySelector('[data-testid="manual-entry-note"]')).not.toBeNull();
    expect(document.body.textContent).not.toContain("Register anyway");
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
      modalScanner("mock-failure-trigger").click();
      modalScanner("mock-failure-trigger").click();
      modalScanner("mock-failure-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();

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
    expect(cards).toEqual(["prereg", "find", "scan"]);
    expect(container.querySelector('[data-testid="kpi-registered-count"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="kpi-seen-count"]')).toBeNull();
    expect(container.querySelector('[data-testid="door-scan-details"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="door-scan-details"]').open).toBeFalsy();
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

  test("door manual books the operating day and checks in when printing is open", async () => {
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
      if (url === "/register") {
        return Promise.resolve({ data: { registration: { id: "p-8", reg_no: "108", full_name: body.full_name } } });
      }
      if (url === "/desk/arrive/p-8") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, id: "p-8", reg_no: "108" } } });
      }
      return Promise.resolve({ data: {} });
    });
    await renderDesk();
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
    act(() => {
      setInput(container.querySelector('[data-testid="reg-fullname-input"]'), "Manual Patient");
      setInput(container.querySelector('[data-testid="reg-age-input"]'), "40");
      setInput(container.querySelector('[data-testid="reg-phone-input"]'), "9876500002");
    });
    await act(async () => {
      container.querySelector('[data-testid="door-manual-submit"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/register", expect.objectContaining({
      full_name: "Manual Patient",
      camp_day_id: "day-2",
      manual_entry: true,
    }));
    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-8");
    expect(container.textContent).toContain("Registered and checked in #108");
  });

  test("camp-day mode hides Pre-registration and shows the full KPI strip", async () => {
    await renderDesk();
    const cards = [...container.querySelectorAll("[data-desk-card]")].map((el) => el.getAttribute("data-desk-card"));
    expect(cards).toEqual(["scan", "find"]);
    expect(container.querySelector('[data-testid="desk-card-prereg"]')).toBeNull();
    expect(container.querySelector('[data-testid="kpi-seen-count"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="kpi-pending-count"]')).not.toBeNull();
  });

  test("three Failures at the door reveal the typed form", async () => {
    await renderDesk();
    expect(container.querySelector('[data-testid="door-manual-form"]')).toBeNull();
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
    expect(container.querySelector('[data-testid="door-manual-form"]')).toBeNull();
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
    expect(container.querySelector('[data-testid="door-manual-form"]')).toBeNull();
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-failure-trigger"]').click(); });
    expect(container.querySelector('[data-testid="door-manual-form"]')).not.toBeNull();
    expect(container.querySelectorAll('[data-testid="mock-aadhaar-scanner"]').length).toBe(1);
  });

  test("camp-day desk shows wedge-panel and hides scanner behind camera-fallback", async () => {
    await renderDesk();
    expect(container.querySelector('[data-testid="wedge-panel"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="camera-fallback"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="camera-fallback"] [data-testid="mock-aadhaar-scanner"]')).not.toBeNull();
  });

  test("desk manual registration is available before any scan failure", async () => {
    await renderDesk();
    const button = container.querySelector('[data-testid="door-manual-toggle"]');
    expect(button).not.toBeNull();
    act(() => button.click());
    expect(container.querySelector('[data-testid="door-manual-form"]')).not.toBeNull();
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

  test("desk shows receiving before Enter and decoding until the response", async () => {
    let resolveScan;
    api.post.mockImplementation((url) => url === "/desk/scan" ? new Promise((resolve) => { resolveScan = resolve; }) : Promise.resolve({ data: {} }));
    await renderDesk();
    let time = 1000;
    const spy = jest.spyOn(performance, "now").mockImplementation(() => time);
    act(() => {
      for (const key of "1234567890".repeat(4)) {
        time += 10;
        document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      }
    });
    expect(container.querySelector('[data-testid="wedge-panel"]').textContent).toContain("Receiving Aadhaar");
    expect(api.post).not.toHaveBeenCalled();
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(container.querySelector('[data-testid="wedge-panel"]').textContent).toContain("Decoding Aadhaar");
    await act(async () => resolveScan({ data: { outcome: "arrived", registration: ARRIVED } }));
    expect(container.querySelector('[data-testid="wedge-panel"]').textContent).toContain("Ready for USB scan");
    spy.mockRestore();
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

  test("a wedge burst posts /desk/scan", async () => {
    api.post.mockResolvedValueOnce({ data: { outcome: "arrived", registration: ARRIVED } });
    await renderDesk();
    await fireBurst(CARD_PAYLOAD);
    expect(api.post).toHaveBeenCalledWith("/desk/scan", { payload: CARD_PAYLOAD });
  });

  test("a second identical burst within 3 s is ignored", async () => {
    api.post.mockResolvedValue({ data: { outcome: "arrived", registration: ARRIVED } });
    const nowSpy = jest.spyOn(Date, "now").mockReturnValue(1_000_000);
    await renderDesk();
    await fireBurst(CARD_PAYLOAD);
    await fireBurst(CARD_PAYLOAD);
    const scans = api.post.mock.calls.filter((c) => c[0] === "/desk/scan");
    expect(scans).toHaveLength(1);
    nowSpy.mockReturnValue(1_000_000 + 3001);
    await fireBurst(CARD_PAYLOAD);
    expect(api.post.mock.calls.filter((c) => c[0] === "/desk/scan")).toHaveLength(2);
    nowSpy.mockRestore();
  });

  test("two NOT_A_CARD bursts reveal the typed form", async () => {
    await renderDesk();
    const rejectCard = () => api.post.mockRejectedValueOnce({
      response: { status: 400, data: { detail: { code: "NOT_A_CARD", message: "not a card" } } },
    });
    rejectCard();
    await fireBurst("X".repeat(24));
    expect(container.querySelector('[data-testid="door-manual-form"]')).toBeNull();
    rejectCard();
    await fireBurst("Y".repeat(24));
    expect(container.querySelector('[data-testid="door-manual-form"]')).toBeNull();
    rejectCard();
    await fireBurst("Z".repeat(24));
    expect(container.querySelector('[data-testid="door-manual-form"]')).not.toBeNull();
  });

  test("a Scan stall at the door does not reveal the typed form", async () => {
    await renderDesk();
    act(() => { deskScanner().parentNode.querySelector('[data-testid="mock-stall-trigger"]').click(); });
    expect(container.querySelector('[data-testid="door-manual-form"]')).toBeNull();
  });
});
