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

jest.mock("../components/AadhaarScanner", () => {
  return function MockAadhaarScanner({ onScanned }) {
    return (
      <div data-testid="mock-aadhaar-scanner">
        <button
          type="button"
          data-testid="mock-scan-trigger"
          onClick={() =>
            onScanned({
              full_name: "Aadhaar Scanned User",
              age: 42,
              gender: "M",
              address: "10 Downing St, Kolkata",
              aadhaar_last4: "8888",
              dob: "1984-05-12",
            })
          }
        >
          Simulate Scan
        </button>
      </div>
    );
  };
});

let container = null;
let root = null;

beforeEach(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();

  api.get.mockImplementation((url) => {
    if (url === "/kpis") {
      return Promise.resolve({
        data: { registered: 45, seen: 30, pending: 15 },
      });
    }
    if (url === "/patients") {
      return Promise.resolve({
        data: {
          patients: [
            {
              id: "p-1",
              reg_no: "101",
              full_name: "Anil Kapoor",
              gender_label: "Male",
              age: 50,
              phone: "9876543210",
              queue_status: "registered",
              printed_at: "2026-08-27T10:00:00Z",
              aadhaar_scanned: true,
            },
            {
              id: "p-2",
              reg_no: "102",
              full_name: "Sunita Roy",
              gender_label: "Female",
              age: 35,
              queue_status: "seen",
            },
          ],
        },
      });
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

describe("Desk page component", () => {
  test("renders KPI statistics and patient list with actions", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    const regStat = container.querySelector('[data-testid="kpi-registered-count"]');
    const seenStat = container.querySelector('[data-testid="kpi-seen-count"]');
    const pendingStat = container.querySelector('[data-testid="kpi-pending-count"]');

    expect(regStat.textContent).toContain("45");
    expect(seenStat.textContent).toContain("30");
    expect(pendingStat.textContent).toContain("15");

    const patientRow1 = container.querySelector('[data-testid="patient-row-101"]');
    const patientRow2 = container.querySelector('[data-testid="patient-row-102"]');
    expect(patientRow1).not.toBeNull();
    expect(patientRow2).not.toBeNull();
    expect(patientRow1.textContent).toContain("Anil Kapoor");

    const markSeenBtn = container.querySelector('[data-testid="mark-seen-button-101"]');
    const undoSeenBtn = container.querySelector('[data-testid="undo-seen-button-102"]');
    expect(markSeenBtn).not.toBeNull();
    expect(undoSeenBtn).not.toBeNull();
  });

  test("handles lookup by Reg number and scrolls to patient row", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/desk/lookup") {
        return Promise.resolve({
          data: {
            registration: { id: "p-1", reg_no: "101", full_name: "Anil Kapoor" },
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    const lookupInput = container.querySelector('[data-testid="desk-lookup-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(lookupInput, "101");
      lookupInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const lookupBtn = container.querySelector('[data-testid="desk-lookup-button"]');
    await act(async () => {
      lookupBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith("/desk/lookup", { value: "101" });
    expect(container.textContent).toContain("Found reg #101 — Anil Kapoor");
  });

  test("handles name search and clears results", async () => {
    api.get.mockImplementation((url) => {
      if (url.startsWith("/patients/search")) {
        return Promise.resolve({
          data: {
            results: [
              {
                id: "p-10",
                reg_no: "110",
                full_name: "Search Result Patient",
                gender_label: "Female",
                age: 60,
                queue_status: "registered",
              },
            ],
          },
        });
      }
      if (url === "/kpis") return Promise.resolve({ data: { registered: 0, seen: 0, pending: 0 } });
      if (url === "/patients") return Promise.resolve({ data: { patients: [] } });
      if (url === "/camps/active") return Promise.resolve({ data: { camp: { name: "Camp" }, days: [] } });
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    const searchInput = container.querySelector('[data-testid="desk-name-search-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(searchInput, "Search");
      searchInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const searchBtn = container.querySelector('[data-testid="desk-name-search-button"]');
    await act(async () => {
      searchBtn.click();
    });

    expect(container.textContent).toContain("Search Result Patient");
    expect(container.textContent).toContain("Search results (1)");
  });

  test("opens Registration modal, populates scanned Aadhaar, locks fields and registers patient", async () => {
    api.post.mockImplementation((url, body) => {
      if (url === "/register/duplicate-check") {
        return Promise.resolve({ data: { likely_duplicates: [] } });
      }
      if (url === "/register") {
        return Promise.resolve({
          data: {
            registration: {
              id: "reg-new",
              reg_no: "103",
              full_name: body.full_name,
            },
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    const newRegBtn = container.querySelector('[data-testid="new-registration-button"]');
    act(() => {
      newRegBtn.click();
    });

    // Verify modal inputs are present in portal (document.body)
    const nameInput = document.body.querySelector('[data-testid="reg-fullname-input"]');
    const ageInput = document.body.querySelector('[data-testid="reg-age-input"]');
    const phoneInput = document.body.querySelector('[data-testid="reg-phone-input"]');
    expect(nameInput).not.toBeNull();
    expect(ageInput).not.toBeNull();

    // Trigger mock Aadhaar scan
    const scanTrigger = document.body.querySelector('[data-testid="mock-scan-trigger"]');
    act(() => {
      scanTrigger.click();
    });

    expect(nameInput.value).toBe("Aadhaar Scanned User");
    expect(nameInput.readOnly).toBe(true);
    expect(ageInput.value).toBe("42");
    expect(ageInput.readOnly).toBe(true);

    // Provide phone
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(phoneInput, "9830098300");
      phoneInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const submitBtn = document.body.querySelector('[data-testid="patient-register-submit"]');
    await act(async () => {
      submitBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/register",
      expect.objectContaining({
        full_name: "Aadhaar Scanned User",
        age: 42,
        gender: "M",
        phone: "9830098300",
        aadhaar_last4: "8888",
        aadhaar_scanned: true,
      })
    );
  });

  test("handles duplicate detection warning and allows override registration", async () => {
    api.post.mockImplementation((url, body) => {
      if (url === "/register/duplicate-check") {
        return Promise.resolve({
          data: {
            likely_duplicates: [
              { id: "dup-1", reg_no: "50", full_name: "Duplicate Person", age: 30 },
            ],
          },
        });
      }
      if (url === "/register") {
        return Promise.resolve({
          data: {
            registration: { id: "reg-dup", reg_no: "104", full_name: body.full_name },
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });

    const nameInput = document.body.querySelector('[data-testid="reg-fullname-input"]');
    const ageInput = document.body.querySelector('[data-testid="reg-age-input"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(nameInput, "Duplicate Person");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(ageInput, "30");
      ageInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const submitBtn = document.body.querySelector('[data-testid="patient-register-submit"]');
    await act(async () => {
      submitBtn.click();
    });

    // Check duplicate warning is rendered
    const dupWarning = document.body.querySelector('[data-testid="duplicate-warning"]');
    expect(dupWarning).not.toBeNull();
    expect(document.body.textContent).toContain("Likely duplicate(s) — same name & age:");

    const overrideBtn = document.body.querySelector('[data-testid="dup-register-anyway"]');
    await act(async () => {
      overrideBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/register",
      expect.objectContaining({
        full_name: "Duplicate Person",
        override_duplicate: true,
      })
    );
  });

  test("handles manual exception checkbox and audited reason input", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Desk />
        </MemoryRouter>
      );
    });

    act(() => {
      container.querySelector('[data-testid="new-registration-button"]').click();
    });

    const manualCheckbox = document.body.querySelector('[data-testid="manual-exception-checkbox"]');
    expect(manualCheckbox).not.toBeNull();

    act(() => {
      manualCheckbox.click();
    });

    const reasonInput = document.body.querySelector('[data-testid="manual-exception-reason"]');
    expect(reasonInput).not.toBeNull();

    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(reasonInput, "Aadhaar QR unreadable / worn out");
      reasonInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(reasonInput.value).toBe("Aadhaar QR unreadable / worn out");
  });
});
