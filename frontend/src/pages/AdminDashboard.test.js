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
    if (url === "/catalogue/medicines?include_inactive=true") {
      return Promise.resolve({
        data: {
          medicines: [
            { id: "med-1", name: "Moxifloxacin", active: true },
            { id: "med-2", name: "Atropine", active: false },
          ],
        },
      });
    }
    if (url === "/catalogue/powers?include_inactive=true") {
      return Promise.resolve({
        data: { powers: [{ id: "p-1", value: 2, label: "+2.00", active: true }] },
      });
    }
    if (url === "/clinical/specs-days") {
      return Promise.resolve({
        data: {
          specs_days: [
            { id: "sp-1", day_date: "2026-09-12", venue: "Base Optical", start_time: "10:00", end_time: "12:00" },
          ],
        },
      });
    }
    if (url === "/leaderboard") {
      return Promise.resolve({
        data: {
          volunteers: [{ name: "Vol 1", registrations: 50, arrivals: 30, points: 80 }],
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

  test("has no Staff or Roster tab or content and links to Team once", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    expect(container.querySelector('[data-testid="admin-tab-staff"]')).toBeNull();
    expect(container.querySelector('[data-testid="admin-tab-roster"]')).toBeNull();
    expect(container.querySelector('[data-testid="create-staff-button"]')).toBeNull();
    expect(container.querySelector('[data-testid="roster-names-input"]')).toBeNull();
    const teamLinks = container.querySelectorAll('[data-testid="goto-team-button"]');
    expect(teamLinks).toHaveLength(1);
    expect(teamLinks[0].textContent).toMatch(/Team/i);
    expect(teamLinks[0].nextElementSibling.dataset.testid).toBe("goto-analytics-button");
    expect(teamLinks[0].nextElementSibling.textContent).toContain("Analytics");
  });

  test("overview recovers after a failed request is retried", async () => {
    api.get.mockRejectedValueOnce(new Error("Network unavailable"));
    await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
    expect(container.querySelector('[data-testid="error-retry-button"]')).not.toBeNull();
    await act(async () => container.querySelector('[data-testid="error-retry-button"]').click());
    expect(container.querySelector('[data-testid="kpi-registered-count"]').textContent).toContain("120");
  });

  test("switches tabs smoothly (Camps, Template, OT & Specs, Leaderboard, Exports)", async () => {
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

    expect(otTab.textContent).toContain("OT & Specs");
    expect(container.textContent).toContain("Base Eye Hospital");
    expect(container.textContent).toContain("5/20 seats");
    expect(container.querySelector('[data-testid="specs-days-list"]')).not.toBeNull();
    expect(container.textContent).toContain("Base Optical");
    expect(container.textContent).toContain("10:00–12:00");
    expect(container.textContent).toContain("Specs collection days");

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
    expect(container.querySelector('[data-testid="export-clinical-audit-button"]')).toBeNull();
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

  test("OT & Specs tab lists Specs collection days and posts create", async () => {
    api.post.mockResolvedValueOnce({ data: { specs_day: { id: "sp-2" } } });

    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });

    await act(async () => {
      container.querySelector('[data-testid="admin-tab-ot"]').click();
    });

    expect(container.textContent).toContain("Base Optical");
    expect(container.textContent).toContain("10:00–12:00");
    expect(container.querySelector('[data-testid="specs-seat-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="specs-days-list"]')).not.toBeNull();

    const dateInput = container.querySelector('[data-testid="specs-date-input"]');
    const venueInput = container.querySelector('[data-testid="specs-venue-input"]');
    const startInput = container.querySelector('[data-testid="specs-start-input"]');
    const endInput = container.querySelector('[data-testid="specs-end-input"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      setter.call(dateInput, "2026-09-20");
      dateInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(venueInput, "New Optical");
      venueInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(startInput, "09:00");
      startInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(endInput, "11:30");
      endInput.dispatchEvent(new Event("input", { bubbles: true }));
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
        start_time: "09:00",
        end_time: "11:30",
      })
    );
  });

  describe("Camp supplies", () => {
    async function openSupplies() {
      await act(async () => {
        root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
      });
      await act(async () => {
        container.querySelector('[data-testid="admin-tab-supplies"]').click();
      });
    }

    function type(testid, value) {
      act(() => {
        const node = container.querySelector(`[data-testid="${testid}"]`);
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")
          .set.call(node, value);
        node.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }

    test("lists both catalogues including retired entries, and labels powers with a sign", async () => {
      await openSupplies();
      expect(container.textContent).toContain("Moxifloxacin");
      expect(container.textContent).toContain("Atropine");
      expect(container.querySelector('[data-testid="power-p-1"]').textContent).toContain("+2.00");
      expect(container.querySelector('[data-testid="medicine-med-1-toggle"]').textContent)
        .toContain("Retire");
      expect(container.querySelector('[data-testid="medicine-med-2-toggle"]').textContent)
        .toContain("Restore");
    });

    test("adding a medicine posts the name and clears the field", async () => {
      api.post.mockResolvedValue({ data: { medicine: { id: "med-3" } } });
      await openSupplies();
      type("medicine-name-input", "Timolol");
      await act(async () => {
        container.querySelector('[data-testid="add-medicine-button"]').click();
      });
      expect(api.post).toHaveBeenCalledWith("/catalogue/medicines", { name: "Timolol" });
      expect(container.querySelector('[data-testid="medicine-name-input"]').value).toBe("");
    });

    test("a failed add keeps what the admin typed", async () => {
      api.post.mockRejectedValue(new Error("boom"));
      await openSupplies();
      type("power-value-input", "+2.25");
      await act(async () => {
        container.querySelector('[data-testid="add-power-button"]').click();
      });
      expect(api.post).toHaveBeenCalledWith("/catalogue/powers", { value: "+2.25" });
      expect(container.querySelector('[data-testid="power-value-input"]').value).toBe("+2.25");
    });

    test("retiring an entry patches it inactive rather than deleting it", async () => {
      api.patch.mockResolvedValue({ data: {} });
      await openSupplies();
      await act(async () => {
        container.querySelector('[data-testid="medicine-med-1-toggle"]').click();
      });
      expect(api.patch).toHaveBeenCalledWith("/catalogue/medicines/med-1", { active: false });
      expect(api.delete).not.toHaveBeenCalled();
    });
  });
});
