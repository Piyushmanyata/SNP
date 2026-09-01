import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Desk from "./Desk";
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

  api.get.mockImplementation((url) => {
    if (url === "/kpis") {
      return Promise.resolve({ data: { registered: 45, seen: 30, pending: 15 } });
    }
    if (url === "/camps/active") {
      return Promise.resolve({
        data: {
          camp: { id: "camp-1", name: "Howrah Eye Camp", venue: "Community Hall" },
          days: [
            { id: "day-1", day_date: "2026-08-27", is_today: true },
            { id: "day-2", day_date: "2026-08-28", is_today: false },
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
      data: { outcome: "no_match", card: { full_name: "Aadhaar Scanned User", age: 42 } },
    });
    await renderDesk();
    await scanAtDoor();

    expect(container.querySelector('[data-testid="scan-no-match"]')).not.toBeNull();
    expect(container.textContent).toContain("Use the search below before registering anyone");
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).not.toHaveBeenCalledWith("/register", expect.anything());
    expect(container.querySelector('[data-testid="register-walk-in-button"]')).not.toBeNull();
  });

  test("registering a walk-in is a deliberate second action that also checks them in", async () => {
    api.post.mockImplementation((url, body) => {
      if (url === "/desk/scan") {
        return Promise.resolve({ data: { outcome: "no_match", card: { full_name: "X" } } });
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
      container.querySelector('[data-testid="register-walk-in-button"]').click();
    });
    expect(document.body.querySelector('[data-testid="walk-in-note"]')).not.toBeNull();

    act(() => {
      modalScanner("mock-scan-trigger").click();
    });
    act(() => {
      setInput(document.body.querySelector('[data-testid="reg-phone-input"]'), "9876500001");
    });
    await act(async () => {
      document.body.querySelector('[data-testid="patient-register-submit"]').click();
    });

    expect(api.post).toHaveBeenCalledWith("/desk/arrive/p-9");
    expect(container.textContent).toContain("Registered and checked in #109");
  });

  test("a pre-registration prints nothing and says the SMS went out", async () => {
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

  test("marking Seen by typing a reg_no", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/desk/lookup") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, printed_at: "2026-09-01T05:00:00Z" } } });
      }
      if (url === "/desk/mark-seen/p-1") {
        return Promise.resolve({ data: { registration: { ...ARRIVED, queue_status: "seen", printed_at: "x" } } });
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

    await act(async () => {
      container.querySelector('[data-testid="mark-seen-button-101"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/desk/mark-seen/p-1");
  });

  test("marking Seen by searching a name", async () => {
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
    await act(async () => {
      container.querySelector('[data-testid="mark-seen-button-101"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/desk/mark-seen/p-1");
  });

  test("a booking that has not arrived offers Check in, not Print", async () => {
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

    expect(container.querySelector('[data-testid="arrive-button-101"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="print-button-101"]')).toBeNull();
    expect(container.querySelector('[data-testid="mark-seen-button-101"]')).toBeNull();
  });

  test("two Failures reveal the typed form and there is no Register anyway", async () => {
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
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();
    expect(document.body.querySelector('[data-testid="manual-entry-note"]')).not.toBeNull();
    expect(document.body.textContent).not.toContain("Register anyway");
  });

  test("a Scan stall counts the same as two Failures", async () => {
    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).toBeNull();

    act(() => {
      modalScanner("mock-stall-trigger").click();
    });
    expect(document.body.querySelector('[data-testid="reg-fullname-input"]')).not.toBeNull();
    expect(document.body.querySelector('[data-testid="manual-entry-note"]')).not.toBeNull();
  });

  test("a Lock before two Failures never reveals a typed path", async () => {
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
    await renderDesk();
    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });
    act(() => {
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
});
