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

const SYSTEM = {
  status: "green",
  levels: { backup: "green", disk: "green" },
  backup: {
    last_success_at: "2026-09-24T04:30:00+00:00", last_error_at: null, last_error: null,
    remote_configured: true, remote_last_success_at: "2026-09-24T04:31:00+00:00",
    interval_seconds: 3600, bytes: 2661, patients_count: 50,
  },
  disk: { free_bytes: 40e9, total_bytes: 100e9 },
};

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();

  api.get.mockImplementation((url) => {
    if (url === "/admin/system") {
      return Promise.resolve({ data: SYSTEM });
    }
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
            { id: "c-2", name: "Inactive Camp", venue: "Ranaghat", camp_date: "2026-09-01", camp_number: 161, is_active: false },
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
            { id: "sp-1", day_date: "2026-09-12", end_date: "2026-09-19", venue: "Base Optical", venue_sms: "Base Optical" },
          ],
        },
      });
    }
    if (url === "/clinical/schedule-notices") {
      return Promise.resolve({ data: { notices: [] } });
    }
    if (url === "/leaderboard") {
      return Promise.resolve({
        data: {
          volunteers: [{ name: "Vol 1", registrations: 50, completed: 30 }],
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

  test("only the active camp offers the door manual-entry gate, and opening it posts today", async () => {
    api.post.mockResolvedValue({ data: {} });
    await act(async () => {
      root.render(
        <MemoryRouter>
          <AdminDashboard />
        </MemoryRouter>
      );
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-camps"]').click());

    const active = container.querySelector('[data-testid="camp-card-c-1"]');
    const inactive = container.querySelector('[data-testid="camp-card-c-2"]');
    expect(active.querySelector('[data-testid="door-manual-control"]')).not.toBeNull();
    expect(inactive.querySelector('[data-testid="door-manual-control"]')).toBeNull();
    expect(active.querySelector('[data-testid="door-manual-state"]').textContent).toContain("Closed");

    await act(async () => active.querySelector('[data-testid="door-manual-toggle"]').click());
    expect(api.post).toHaveBeenCalledWith("/camps/door-manual", { enabled: true });
  });

  test("a camp's SMS number is set at creation and can be corrected later", async () => {
    api.post.mockResolvedValue({ data: {} });
    api.patch.mockResolvedValue({ data: {} });
    await act(async () => {
      root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-camps"]').click());

    expect(container.querySelector('[data-testid="camp-number-missing-c-1"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="camp-number-c-2"]').textContent).toContain("161");

    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    const type = (testid, value) => {
      const input = document.querySelector(`[data-testid="${testid}"]`);
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const submit = () => document.querySelector('[data-testid="camp-create-submit"]');

    await act(async () => container.querySelector('[data-testid="create-camp-button"]').click());
    act(() => type("camp-date-input", "2026-10-10"));
    expect(submit().disabled).toBe(true);
    act(() => type("camp-number-input", "163"));
    act(() => type("camp-venue-sms-input", ""));
    expect(submit().disabled).toBe(true);
    act(() => type("camp-venue-sms-input", "Hansa Garden, Baghmara, Jasidih, Deoghar"));
    expect(submit().disabled).toBe(true);
    act(() => type("camp-venue-sms-input", "Hansa Garden, Jasidih, Deoghar"));
    await act(async () => submit().click());
    expect(api.post).toHaveBeenCalledWith("/camps", expect.objectContaining({ camp_date: "2026-10-10", camp_number: 163, venue_sms: "Hansa Garden, Jasidih, Deoghar" }));

    await act(async () => container.querySelector('[data-testid="edit-camp-c-1"]').click());
    act(() => type("camp-number-input", "162"));
    act(() => type("camp-venue-sms-input", "Short Camp Venue"));
    await act(async () => submit().click());
    expect(api.patch).toHaveBeenCalledWith("/camps/c-1", {
      name: "Active Nadia Camp", venue: "Krishnanagar Hall", venue_sms: "Short Camp Venue", camp_date: "2026-08-27", camp_number: 162,
    });
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
    const base = api.get.getMockImplementation();
    let failKpis = true;
    api.get.mockImplementation((url) => {
      if (url === "/kpis" && failKpis) {
        failKpis = false;
        return Promise.reject(new Error("Network unavailable"));
      }
      return base(url);
    });
    await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
    expect(container.querySelector('[data-testid="error-retry-button"]')).not.toBeNull();
    await act(async () => container.querySelector('[data-testid="error-retry-button"]').click());
    expect(container.querySelector('[data-testid="kpi-registered-count"]').textContent).toContain("120");
  });

  describe("System card", () => {
    const renderWith = async (system) => {
      const base = api.get.getMockImplementation();
      api.get.mockImplementation((url) => (url === "/admin/system" ? Promise.resolve({ data: system }) : base(url)));
      await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
      return container.querySelector('[data-testid="system-card"]');
    };

    test("green shows the last backup, the off-site copy and free disk", async () => {
      const card = await renderWith(SYSTEM);
      expect(card.getAttribute("data-status")).toBe("green");
      expect(card.querySelector('[data-testid="system-status"]').textContent).toBe("All good");
      expect(card.querySelector('[data-testid="system-backup"]').textContent).toContain("24-09-2026 10:00");
      expect(card.querySelector('[data-testid="system-remote"]').textContent).toContain("24-09-2026 10:01");
      expect(card.querySelector('[data-testid="system-disk"]').textContent).toContain("40 GB free of 100 GB");
      expect(card.querySelector('[data-testid="system-error"]')).toBeNull();
    });

    test("amber says the off-site copy is not set up", async () => {
      const card = await renderWith({
        ...SYSTEM, status: "amber", levels: { backup: "amber", disk: "green" },
        backup: { ...SYSTEM.backup, remote_configured: false, remote_last_success_at: null },
      });
      expect(card.getAttribute("data-status")).toBe("amber");
      expect(card.querySelector('[data-testid="system-status"]').textContent).toBe("Needs attention");
      expect(card.querySelector('[data-testid="system-remote"]').textContent).toContain("Not set up");
      expect(card.querySelector('[data-testid="system-remote"]').className).toContain("amber");
      expect(card.querySelector('[data-testid="system-disk"]').className).not.toContain("amber");
    });

    test("red with no backup yet shows the latest error and an unknown disk", async () => {
      const card = await renderWith({
        status: "red", levels: { backup: "red", disk: "green" },
        backup: { ...SYSTEM.backup, last_success_at: null, remote_last_success_at: null, last_error_at: "2026-09-24T05:00:00+00:00", last_error: "dump failed" },
        disk: "unknown",
      });
      expect(card.getAttribute("data-status")).toBe("red");
      expect(card.querySelector('[data-testid="system-status"]').textContent).toBe("Failing");
      expect(card.querySelector('[data-testid="system-backup"]').textContent).toContain("No backup yet");
      expect(card.querySelector('[data-testid="system-error"]').textContent).toContain("dump failed");
      expect(card.querySelector('[data-testid="system-disk"]').textContent).toContain("Unknown");
    });

    test("an error from the same pass as the last success is shown", async () => {
      const card = await renderWith({
        ...SYSTEM, status: "amber", levels: { backup: "amber", disk: "green" },
        backup: { ...SYSTEM.backup, last_error_at: SYSTEM.backup.last_success_at, last_error: "prune failed" },
      });
      expect(card.querySelector('[data-testid="system-error"]').textContent).toContain("prune failed");
    });

    test("an error older than the last success is not shown", async () => {
      const card = await renderWith({ ...SYSTEM, backup: { ...SYSTEM.backup, last_error_at: "2026-09-24T01:00:00+00:00", last_error: "dump failed" } });
      expect(card.querySelector('[data-testid="system-error"]')).toBeNull();
    });

    test("a failed status request leaves the KPIs and offers a retry", async () => {
      const base = api.get.getMockImplementation();
      let fail = true;
      api.get.mockImplementation((url) => {
        if (url === "/admin/system" && fail) {
          fail = false;
          return Promise.reject(new Error("Network unavailable"));
        }
        return base(url);
      });
      await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
      expect(container.querySelector('[data-testid="kpi-registered-count"]').textContent).toContain("120");
      await act(async () => container.querySelector('[data-testid="error-retry-button"]').click());
      expect(container.querySelector('[data-testid="system-card"]').getAttribute("data-status")).toBe("green");
    });
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
    expect(container.textContent).toContain("10:00 AM–5:00 PM");
    expect(container.textContent).toContain("05-09-2026");
    expect(container.textContent).toContain("12-09-2026");
    expect(container.textContent).not.toContain("2026-09-05");
    expect(container.textContent).not.toContain("2026-09-12");
    expect(container.textContent).toContain("Specs collection days");

    // Switch to Leaderboards tab
    const boardTab = container.querySelector('[data-testid="admin-tab-board"]');
    await act(async () => {
      boardTab.click();
    });

    const volBoard = container.querySelector('[data-testid="leaderboard-volunteers-table"]');
    expect(volBoard).not.toBeNull();
    expect(volBoard.textContent).toContain("30 completed prescriptions");
    expect(volBoard.textContent).not.toContain("arrivals");

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
    expect(container.textContent).toContain("Krishnanagar Hall · 27-08-2026");
    expect(container.textContent).toContain("01-09-2026");
    expect(container.textContent).not.toContain("2026-08-27");
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

  test("shows a camp day as over capacity after seats fall below bookings", async () => {
    await act(async () => { root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>); });
    await act(async () => { container.querySelector('[data-testid="admin-tab-camps"]').click(); });
    api.get.mockResolvedValueOnce({ data: { days: [
      { id: "cd-1", day_date: "2026-08-27", seat_limit: 2, booked: 3, over_capacity: true, printing_open: false },
    ] } });

    await act(async () => { container.querySelector('[data-testid="manage-days-c-1"]').click(); });

    const day = container.querySelector('[data-testid="day-row-cd-1"]');
    expect(day.textContent).toContain("3 booked / 2 seats");
    expect(day.textContent).toContain("Over capacity");
  });

  test("deleting a camp or a day asks first and clears an old error on success", async () => {
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(false);
    api.delete.mockRejectedValueOnce({ response: { data: { detail: "Camp has registrations; cannot delete" } } });
    api.delete.mockResolvedValue({ data: { ok: true } });
    await act(async () => { root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>); });
    await act(async () => { container.querySelector('[data-testid="admin-tab-camps"]').click(); });
    const deleteCamp = container.querySelector('[data-testid="delete-camp-c-2"]');
    expect(deleteCamp.getAttribute("aria-label")).toBe("Delete Inactive Camp");

    await act(async () => { deleteCamp.click(); });
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(api.delete).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    await act(async () => { deleteCamp.click(); });
    expect(container.textContent).toContain("Camp has registrations; cannot delete");
    await act(async () => { deleteCamp.click(); });
    expect(api.delete).toHaveBeenLastCalledWith("/camps/c-2");
    expect(container.textContent).not.toContain("Camp has registrations");

    await act(async () => { container.querySelector('[data-testid="manage-days-c-1"]').click(); });
    const deleteDay = container.querySelector('[data-testid="delete-day-cd-1"]');
    expect(deleteDay.getAttribute("aria-label")).toBe("Delete camp day 27-08-2026");
    await act(async () => { deleteDay.click(); });
    expect(api.delete).toHaveBeenLastCalledWith("/camps/days/cd-1");
    confirm.mockRestore();
  });

  test("a new camp cannot be submitted twice while the first create is pending", async () => {
    let finish;
    api.post.mockReset();
    api.post.mockImplementationOnce(() => new Promise((done) => { finish = done; }));
    await act(async () => { root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>); });
    await act(async () => { container.querySelector('[data-testid="admin-tab-camps"]').click(); });
    await act(async () => { container.querySelector('[data-testid="create-camp-button"]').click(); });
    const type = (testid, value) => act(() => {
      const input = document.querySelector(`[data-testid="${testid}"]`);
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    type("camp-date-input", "2026-10-01");
    type("camp-number-input", "163");
    const submit = document.querySelector('[data-testid="camp-create-submit"]');
    await act(async () => { submit.click(); });
    expect(submit.isConnected).toBe(true);
    expect(submit.disabled).toBe(true);
    await act(async () => { submit.click(); });
    expect(api.post).toHaveBeenCalledTimes(1);
    await act(async () => { finish({ data: {} }); });
  });

  test("a failed export shows the server reason in a red alert", async () => {
    const body = JSON.stringify({ detail: "No active camp to export" });
    api.get.mockImplementation((url) => (url === "/exports/camp-records"
      ? Promise.reject({ message: "Request failed with status code 409", response: { status: 409, data: { text: () => Promise.resolve(body) } } })
      : Promise.resolve({ data: url === "/admin/system" ? SYSTEM : {} })));
    await act(async () => { root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>); });
    await act(async () => { container.querySelector('[data-testid="admin-tab-exports"]').click(); });
    await act(async () => { container.querySelector('[data-testid="export-camp-records-button"]').click(); });
    const alert = container.querySelector('[role="alert"]');
    expect(alert.textContent).toContain("No active camp to export");
    expect(alert.className).toContain("rose");
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
    expect(container.textContent).toContain("12-09-2026 – 19-09-2026");
    expect(container.textContent).toContain("10:00 AM–5:00 PM");
    expect(container.querySelector('[data-testid="specs-seat-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="specs-days-list"]')).not.toBeNull();

    const dateInput = container.querySelector('[data-testid="specs-date-input"]');
    const untilInput = container.querySelector('[data-testid="specs-end-date-input"]');
    const venueInput = container.querySelector('[data-testid="specs-venue-input"]');
    expect(container.querySelector('[data-testid="specs-start-input"]')).toBeNull();
    expect(container.querySelector('[data-testid="specs-end-input"]')).toBeNull();
    expect(container.textContent).toContain("Collection hours: 10:00 AM–5:00 PM");
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      setter.call(dateInput, "2026-09-20");
      dateInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(untilInput, "2026-09-27");
      untilInput.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(venueInput, "New Optical");
      venueInput.dispatchEvent(new Event("input", { bubbles: true }));
    });

    await act(async () => {
      container.querySelector('[data-testid="add-specs-day-button"]').click();
    });

    expect(api.post).toHaveBeenCalledWith(
      "/clinical/specs-days",
      {
        camp_id: "c-1",
        day_date: "2026-09-20",
        end_date: "2026-09-27",
        venue: "New Optical",
        venue_sms: "",
      }
    );
  });

  test("a Specs collection day is edited in place, never re-added", async () => {
    api.patch.mockResolvedValue({ data: {} });
    await act(async () => {
      root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-ot"]').click());
    act(() => container.querySelector('[data-testid="edit-specs-day-sp-1"]').click());
    const venue = container.querySelector('[data-testid="specs-venue-input"]');
    expect(venue.value).toBe("Base Optical");
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      setter.call(venue, "New Optical");
      venue.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector('[data-testid="save-specs-day-button"]').click());
    expect(api.patch).toHaveBeenCalledWith("/clinical/specs-days/sp-1", {
      camp_id: "c-1", day_date: "2026-09-12", end_date: "2026-09-19", venue: "New Optical", venue_sms: "Base Optical",
    });
    expect(api.post).not.toHaveBeenCalledWith("/clinical/specs-days", expect.anything());
  });

  test("patients whose changed Token got no SMS are listed to phone until marked done", async () => {
    const notice = {
      slip_id: "slip-9", item_type: "ot", reg_no: 501, full_name: "Sita Devi", phone: "9876500001",
      collection_date: "2026-10-09", collection_end_date: null, collection_venue: "New Hospital", sms_status: "not_sent",
    };
    const get = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/clinical/schedule-notices"
      ? Promise.resolve({ data: { notices: [notice] } }) : get(url)));
    api.post.mockResolvedValue({ data: { ok: true } });
    await act(async () => {
      root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-ot"]').click());
    const row = container.querySelector('[data-testid="schedule-notice-slip-9"]');
    expect(row.textContent).toContain("#501 Sita Devi");
    expect(row.textContent).toContain("9876500001");
    expect(row.textContent).toContain("IOL surgery · 09-10-2026 · New Hospital");
    expect(row.textContent).toContain("SMS not sent");
    expect(row.querySelector('a[href="tel:9876500001"]')).not.toBeNull();
    await act(async () => container.querySelector('[data-testid="schedule-notice-done-slip-9"]').click());
    expect(api.post).toHaveBeenCalledWith("/clinical/schedule-notices/slip-9/contacted");
    expect(container.querySelector('[data-testid="schedule-notices"]')).toBeNull();
  });

  test("the phone list reloads after a day is edited", async () => {
    const notice = {
      slip_id: "slip-7", item_type: "ot", reg_no: 502, full_name: "Ram Lal", phone: "9876500002",
      collection_date: "2026-09-06", collection_end_date: null, collection_venue: "Moved Hospital", sms_status: "not_sent",
    };
    let edited = false;
    const get = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/clinical/schedule-notices"
      ? Promise.resolve({ data: { notices: edited ? [notice] : [] } }) : get(url)));
    api.patch.mockImplementation(() => { edited = true; return Promise.resolve({ data: {} }); });
    await act(async () => {
      root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-ot"]').click());
    expect(container.querySelector('[data-testid="schedule-notices"]')).toBeNull();
    act(() => container.querySelector('[data-testid="edit-ot-day-ot-1"]').click());
    await act(async () => container.querySelector('[data-testid="save-ot-day-button"]').click());
    expect(container.querySelector('[data-testid="schedule-notice-slip-7"]')).not.toBeNull();
  });

  test("an SMS venue that would fail DLT blocks saving and says why", async () => {
    await act(async () => {
      root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-ot"]').click());
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    const type = (testid, value) => act(() => {
      const input = container.querySelector(`[data-testid="${testid}"]`);
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const note = () => container.querySelector('[data-testid="specs-venue-sms-input-note"]').textContent;
    const add = () => container.querySelector('[data-testid="add-specs-day-button"]');

    type("specs-date-input", "2026-10-05");
    type("specs-venue-input", "NA");
    expect(note()).toContain("3 to 30 characters");
    expect(add().disabled).toBe(true);

    type("specs-venue-sms-input", "Office 9876543210");
    expect(note()).toBe("SMS venue must not contain a phone number");
    expect(add().disabled).toBe(true);

    type("specs-venue-sms-input", "SNP Office, Deoghar");
    expect(note()).toBe("SMS will say “SNP Office, Deoghar” · 19/30");
    expect(add().disabled).toBe(false);
  });

  test("SMS tab shows each message type and resumes a paused one", async () => {
    const today = { submitted: 3, delivered: 1, dlt_failed: 1, other_failed: 0, uncertain: 0, rejected: 0, unsent: 0, paused: 1, credits: 2.25 };
    const status = (paused) => ({
      reports_enabled: false,
      today,
      types: ["registration", "camp", "ot_token", "ot", "specs_token", "specs"].map((message_type) => ({
        message_type,
        configured: !message_type.startsWith("specs"),
        paused: paused && message_type === "registration",
        paused_at: paused && message_type === "registration" ? "2026-09-23T05:00:00Z" : null,
        paused_reason: paused && message_type === "registration" ? "DLT Template variable exceeded max length" : null,
        today,
      })),
    });
    const getDefault = api.get.getMockImplementation();
    api.get.mockImplementation((url) => (url === "/sms/status" ? Promise.resolve({ data: status(true) }) : getDefault(url)));
    api.post.mockResolvedValue({ data: status(false) });
    jest.spyOn(window, "confirm").mockReturnValue(true);

    await act(async () => {
      root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>);
    });
    await act(async () => container.querySelector('[data-testid="admin-tab-sms"]').click());

    expect(container.textContent).toContain("Delivery reports are off");
    expect(container.querySelector('[data-testid="sms-today-credits"]').textContent).toBe("2.25");
    const registration = container.querySelector('[data-testid="sms-type-registration"]');
    expect(registration.textContent).toContain("Paused");
    expect(container.querySelector('[data-testid="sms-paused-reason-registration"]').textContent).toContain("exceeded max length");
    expect(container.querySelector('[data-testid="sms-type-specs"]').textContent).toContain("Not set up");
    expect(container.querySelector('[data-testid="sms-type-camp"]').textContent).toContain("Sending");
    expect(container.querySelector('[data-testid="sms-resume-camp"]')).toBeNull();

    await act(async () => container.querySelector('[data-testid="sms-resume-registration"]').click());

    expect(api.post).toHaveBeenCalledWith("/sms/registration/resume");
    expect(container.querySelector('[data-testid="sms-resume-registration"]')).toBeNull();
    window.confirm.mockRestore();
  });

  test("an OT day with a long hospital name needs a short SMS name", async () => {
    api.post.mockResolvedValue({ data: {} });
    await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
    await act(async () => container.querySelector('[data-testid="admin-tab-ot"]').click());
    const date = container.querySelector('[data-testid="ot-date-input"]');
    const shortName = container.querySelector('[data-testid="ot-venue-sms-input"]');
    const save = container.querySelector('[data-testid="add-ot-day-button"]');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      setter.call(date, "2026-10-02");
      date.dispatchEvent(new Event("input", { bubbles: true }));
      setter.call(shortName, "");
      shortName.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(save.disabled).toBe(true);
    act(() => {
      setter.call(shortName, "Bajaj Hospital, Deoghar");
      shortName.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => save.click());
    expect(api.post).toHaveBeenCalledWith("/clinical/ot-days", expect.objectContaining({ venue_sms: "Bajaj Hospital, Deoghar" }));
  });

  test("an admin can edit a camp day's date and seats", async () => {
    api.patch.mockResolvedValue({ data: {} });
    await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
    await act(async () => container.querySelector('[data-testid="admin-tab-camps"]').click());
    await act(async () => container.querySelector('[data-testid="manage-days-c-1"]').click());
    await act(async () => container.querySelector('[data-testid="edit-day-cd-1"]').click());
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      const date = container.querySelector('[data-testid="new-day-date"]');
      setter.call(date, "2026-10-05");
      date.dispatchEvent(new Event("input", { bubbles: true }));
      const seats = container.querySelector('[data-testid="new-day-seat"]');
      setter.call(seats, "30");
      seats.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector('[data-testid="save-day-button"]').click());
    expect(api.patch).toHaveBeenCalledWith("/camps/days/cd-1", {
      camp_id: "c-1", day_date: "2026-10-05", seat_limit: 30,
    });
  });

  test("an admin can edit an OT day's date, seats and hospital", async () => {
    api.patch.mockResolvedValue({ data: {} });
    await act(async () => root.render(<MemoryRouter><AdminDashboard /></MemoryRouter>));
    await act(async () => container.querySelector('[data-testid="admin-tab-ot"]').click());
    await act(async () => container.querySelector('[data-testid="edit-ot-day-ot-1"]').click());
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    act(() => {
      const date = container.querySelector('[data-testid="ot-date-input"]');
      setter.call(date, "2026-10-05");
      date.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => container.querySelector('[data-testid="save-ot-day-button"]').click());
    expect(api.patch).toHaveBeenCalledWith("/clinical/ot-days/ot-1", {
      camp_id: "c-1", day_date: "2026-10-05", venue: "Base Eye Hospital", venue_sms: "", seat_limit: 20,
    });
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
