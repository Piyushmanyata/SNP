import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import AdminDashboard from "./AdminDashboard";
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
      patch: jest.fn(),
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

jest.mock("../components/TemplateEditor", () => {
  return function MockTemplateEditor() {
    return <div data-testid="mock-template-editor">Template Editor Tab</div>;
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
    if (url === "/kpis") {
      return Promise.resolve({
        data: { registered: 120, seen: 90, pending: 30 },
      });
    }
    if (url === "/camps/active") {
      return Promise.resolve({
        data: {
          camp: { id: "c-1", name: "Active Nadia Camp", venue: "Krishnanagar Hall" },
          days: [],
        },
      });
    }
    if (url === "/camps") {
      return Promise.resolve({
        data: {
          camps: [
            { id: "c-1", name: "Active Nadia Camp", venue: "Krishnanagar Hall", camp_date: "2026-08-27", is_active: true },
            { id: "c-2", name: "Inactive Camp", venue: "Ranaghat", camp_date: "2026-09-01", is_active: false },
          ],
        },
      });
    }
    if (url === "/camps/c-1/days") {
      return Promise.resolve({
        data: {
          days: [
            { id: "cd-1", day_date: "2026-08-27", is_today: true, seat_limit: 100, printing_open: true },
          ],
        },
      });
    }
    if (url === "/staff") {
      return Promise.resolve({
        data: {
          staff: [
            { id: "u-1", name: "Admin Lead", email: "admin@snp.org", role: "admin", disabled_at: null },
            { id: "u-2", name: "Vol 1", email: "vol@snp.org", role: "volunteer", disabled_at: null },
          ],
        },
      });
    }
    if (url === "/staff/team-leads") {
      return Promise.resolve({
        data: {
          team_leads: [{ id: "tl-1", name: "Lead One" }],
        },
      });
    }
    if (url === "/clinical/ot-days") {
      return Promise.resolve({
        data: {
          ot_days: [
            { id: "ot-1", day_date: "2026-09-05", venue: "Base Eye Hospital", seat_limit: 20, seats_taken: 5, seats_free: 15 },
          ],
        },
      });
    }
    if (url === "/clinical/specs-days") {
      return Promise.resolve({
        data: {
          specs_days: [
            { id: "sp-1", day_date: "2026-09-12", venue: "Base Optical", seat_limit: 12, seats_taken: 3, seats_free: 9 },
          ],
        },
      });
    }
    if (url === "/leaderboard") {
      return Promise.resolve({
        data: {
          volunteers: [{ user_id: "u-2", name: "Vol 1", points: 80 }],
          team_leads: [{ user_id: "tl-1", name: "Lead One", points: 200 }],
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

describe("AdminDashboard component", () => {
  test("renders Overview tab by default with KPIs and active camp info", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    expect(container.textContent).toContain("Active Nadia Camp");
    const regStat = container.querySelector('[data-testid="kpi-registered-count"]');
    expect(regStat.textContent).toContain("120");

    const gotoDesk = container.querySelector('[data-testid="goto-desk-button"]');
    const gotoClinical = container.querySelector('[data-testid="goto-clinical-button"]');
    expect(gotoDesk).not.toBeNull();
    expect(gotoClinical).not.toBeNull();
  });

  test("switches tabs smoothly (Camps, Staff, Template, OT, Leaderboard, Exports)", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    // Switch to Camps tab
    const campsTab = container.querySelector('[data-testid="admin-tab-camps"]');
    await act(async () => {
      campsTab.click();
    });

    expect(container.querySelector('[data-testid="create-camp-button"]')).not.toBeNull();
    expect(container.textContent).toContain("Inactive Camp");

    // Switch to Staff tab
    const staffTab = container.querySelector('[data-testid="admin-tab-staff"]');
    await act(async () => {
      staffTab.click();
    });

    expect(container.querySelector('[data-testid="create-staff-button"]')).not.toBeNull();
    expect(container.textContent).toContain("Admin Lead");
    expect(container.textContent).toContain("Vol 1");

    // Switch to Rx Template tab
    const tplTab = container.querySelector('[data-testid="admin-tab-template"]');
    await act(async () => {
      tplTab.click();
    });

    expect(container.querySelector('[data-testid="mock-template-editor"]')).not.toBeNull();

    // Switch to OT tab
    const otTab = container.querySelector('[data-testid="admin-tab-ot"]');
    await act(async () => {
      otTab.click();
    });

    expect(container.textContent).toContain("Base Eye Hospital");
    expect(container.textContent).toContain("5/20 seats");

    // Switch to Leaderboards tab
    const boardTab = container.querySelector('[data-testid="admin-tab-board"]');
    await act(async () => {
      boardTab.click();
    });

    const volBoard = container.querySelector('[data-testid="leaderboard-volunteers-table"]');
    expect(volBoard).not.toBeNull();
    expect(volBoard.textContent).toContain("80 pts");

    // Switch to Exports tab
    const expTab = container.querySelector('[data-testid="admin-tab-exports"]');
    await act(async () => {
      expTab.click();
    });

    expect(container.querySelector('[data-testid="export-camp-records-button"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="export-clinical-audit-button"]')).not.toBeNull();
  });

  test("manages camps: creates camp and expands camp days with printing window toggle", async () => {
    api.post.mockResolvedValueOnce({ data: { message: "Created" } });
    api.patch.mockResolvedValueOnce({ data: { message: "Updated" } });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    // Go to camps
    await act(async () => {
      container.querySelector('[data-testid="admin-tab-camps"]').click();
    });

    // Expand days for c-1
    const manageDaysBtn = container.querySelector('[data-testid="manage-days-c-1"]');
    await act(async () => {
      manageDaysBtn.click();
    });

    expect(api.get).toHaveBeenCalledWith("/camps/c-1/days");
    const togglePrintBtn = container.querySelector('[data-testid="toggle-print-window-cd-1"]');
    expect(togglePrintBtn).not.toBeNull();

    await act(async () => {
      togglePrintBtn.click();
    });

    expect(api.patch).toHaveBeenCalledWith(
      "/camps/days/cd-1/print-window",
      { printing_open: false }
    );
  });

  test("manages staff: opens modal, creates volunteer with team lead", async () => {
    api.post.mockResolvedValueOnce({ data: { message: "Staff created" } });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    await act(async () => {
      container.querySelector('[data-testid="admin-tab-staff"]').click();
    });

    const addStaffBtn = container.querySelector('[data-testid="create-staff-button"]');
    act(() => {
      addStaffBtn.click();
    });

    const nameInput = document.body.querySelector('[data-testid="staff-name-input"]');
    const emailInput = document.body.querySelector('[data-testid="staff-email-input"]');
    const passInput = document.body.querySelector('[data-testid="staff-password-input"]');

    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(nameInput, "New Volunteer");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(emailInput, "newvol@snp.org");
      emailInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(passInput, "Secret@123456");
      passInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const createBtn = document.body.querySelector('[data-testid="staff-create-submit"]');
    await act(async () => {
      createBtn.click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/staff",
      expect.objectContaining({
        name: "New Volunteer",
        email: "newvol@snp.org",
        role: "volunteer",
      })
    );
  });

  test("handles disable/enable staff action", async () => {
    api.patch.mockResolvedValueOnce({ data: { message: "Disabled" } });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    await act(async () => {
      container.querySelector('[data-testid="admin-tab-staff"]').click();
    });

    const disableBtn = container.querySelector('[data-testid="disable-staff-u-2"]');
    expect(disableBtn).not.toBeNull();

    await act(async () => {
      disableBtn.click();
    });

    expect(api.patch).toHaveBeenCalledWith("/staff/u-2/disable");
  });

  test("Specs collection days tab lists days and posts create", async () => {
    api.post.mockResolvedValueOnce({ data: { specs_day: { id: "sp-2" } } });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    await act(async () => {
      container.querySelector('[data-testid="admin-tab-specs"]').click();
    });

    expect(container.textContent).toContain("Base Optical");
    expect(container.textContent).toContain("3/12 seats");
    expect(container.querySelector('[data-testid="specs-days-list"]')).not.toBeNull();

    const dateInput = container.querySelector('[data-testid="specs-date-input"]');
    const venueInput = container.querySelector('[data-testid="specs-venue-input"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      setter.call(dateInput, "2026-09-20");
      dateInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(venueInput, "New Optical");
      venueInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await act(async () => {
      container.querySelector('[data-testid="add-specs-day-button"]').click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/clinical/specs-days",
      expect.objectContaining({
        camp_id: "c-1",
        day_date: "2026-09-20",
        venue: "New Optical",
      })
    );
  });
});
