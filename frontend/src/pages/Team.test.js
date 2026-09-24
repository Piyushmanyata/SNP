import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Team from "./Team";
import api from "../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockAuth = {
  user: { id: "a1", name: "System Admin", role: "admin" },
};

jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

jest.mock("../components/Layout", () => {
  return function MockLayout({ children, title }) {
    return (
      <div data-testid="mock-layout" data-title={title}>
        {children}
      </div>
    );
  };
});

const ADMIN_STAFF = [
  { id: "a1", name: "System Admin", role: "admin", disabled_at: null, must_change_pin: false },
  {
    id: "cdo-1",
    name: "Clinical Op",
    role: "clinical_desk_operator",
    line: "rx",
    disabled_at: null,
    must_change_pin: false,
  },
  { id: "v1", name: "Vol One", role: "volunteer", team_lead_id: "tl-1", disabled_at: null },
  {
    id: "v2", name: "Vol Locked", role: "volunteer", team_lead_id: "tl-1", disabled_at: null,
    locked_until: "2026-09-24T05:15:00+00:00", lockouts_24h: 3, lockout_sources_24h: 2,
  },
];

const TEAM_LEADS = [{ id: "tl-1", name: "Lead One" }];

let container = null;
let root = null;

function setInputValue(node, value) {
  const proto = node.tagName === "SELECT"
    ? window.HTMLSelectElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(node, value);
  node.dispatchEvent(new Event(node.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  mockAuth.user = { id: "a1", name: "System Admin", role: "admin" };

  api.get.mockImplementation((url) => {
    if (url === "/staff") {
      return Promise.resolve({ data: { staff: ADMIN_STAFF } });
    }
    if (url === "/staff/team-leads") {
      return Promise.resolve({ data: { team_leads: TEAM_LEADS } });
    }
    return Promise.resolve({ data: {} });
  });
  api.post.mockResolvedValue({ data: { staff: { id: "new-1", name: "New Person" } } });
  api.patch.mockResolvedValue({ data: { ok: true } });
  api.delete.mockResolvedValue({ data: { ok: true } });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
});

async function renderTeam() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <Team />
      </MemoryRouter>,
    );
  });
}

describe("Team page", () => {
  test("admin sees Admin, Team Lead, Volunteer, and Clinical Desk Operator roles", async () => {
    await renderTeam();
    const roleSelect = container.querySelector('[data-testid="staff-role-select"]');
    expect(roleSelect).not.toBeNull();
    const values = Array.from(roleSelect.options).map((o) => o.value);
    expect(values).toEqual(["volunteer", "clinical_desk_operator", "team_lead", "admin"]);
    expect(roleSelect.textContent).toContain("Volunteer");
    expect(roleSelect.textContent).toContain("Clinical Desk Operator");
    expect(roleSelect.textContent).toContain("Team Lead");
    expect(roleSelect.textContent).toContain("Admin");
  });

  test("admin creates operators without assigning a line", async () => {
    await renderTeam();
    const roleSelect = container.querySelector('[data-testid="staff-role-select"]');
    act(() => {
      setInputValue(roleSelect, "clinical_desk_operator");
    });
    expect(container.querySelector('[data-testid="staff-line-select"]')).toBeNull();
    expect(container.querySelector('[data-testid="staff-line-cdo-1"]')).toBeNull();
    act(() => setInputValue(container.querySelector('[data-testid="staff-name-input"]'), "New Operator"));
    await act(async () => {
      container.querySelector('[data-testid="add-staff-form"]').dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(api.post).toHaveBeenCalledWith("/staff", { name: "New Operator", role: "clinical_desk_operator", phone: null, team_lead_id: null });
  });

  test("successful create resets name, phone, role and Team Lead", async () => {
    await renderTeam();
    act(() => {
      setInputValue(container.querySelector('[data-testid="staff-name-input"]'), "New Volunteer");
      setInputValue(container.querySelector('[data-testid="staff-phone-input"]'), "9876543210");
      setInputValue(container.querySelector('[data-testid="staff-role-select"]'), "volunteer");
      setInputValue(container.querySelector('[data-testid="staff-teamlead-select"]'), "tl-1");
    });
    await act(async () => {
      container.querySelector('[data-testid="add-staff-form"]').dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });
    expect(api.post).toHaveBeenCalledWith(
      "/staff",
      expect.objectContaining({
        name: "New Volunteer",
        role: "volunteer",
        phone: "9876543210",
        team_lead_id: "tl-1",
      }),
    );
    expect(container.querySelector('[data-testid="staff-name-input"]').value).toBe("");
    expect(container.querySelector('[data-testid="staff-phone-input"]').value).toBe("");
    expect(container.querySelector('[data-testid="staff-role-select"]').value).toBe("volunteer");
    expect(container.querySelector('[data-testid="staff-teamlead-select"]').value).toBe("");
    expect(container.querySelector('[data-testid="staff-line-select"]')).toBeNull();
  });

  test("shows API error, busy state, enable/disable, and reset PIN", async () => {
    let resolveCreate;
    api.post.mockImplementation((url) => {
      if (url === "/staff") {
        return new Promise((resolve) => {
          resolveCreate = resolve;
        });
      }
      return Promise.resolve({ data: { ok: true } });
    });
    await renderTeam();
    act(() => {
      setInputValue(container.querySelector('[data-testid="staff-name-input"]'), "Busy Person");
    });
    act(() => {
      container.querySelector('[data-testid="add-staff-form"]').dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });
    expect(container.querySelector('[data-testid="add-staff-button"]').disabled).toBe(true);
    expect(container.textContent).toContain("Adding");
    await act(async () => {
      resolveCreate({ data: { staff: { id: "n1" } } });
    });

    api.post.mockRejectedValueOnce({
      response: { data: { detail: "Name already exists" } },
    });
    act(() => {
      setInputValue(container.querySelector('[data-testid="staff-name-input"]'), "Vol One");
    });
    await act(async () => {
      container.querySelector('[data-testid="add-staff-form"]').dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });
    expect(container.textContent).toContain("Name already exists");

    const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
    await act(async () => {
      container.querySelector('[data-testid="reset-pin-v1"]').click();
    });
    expect(api.post).toHaveBeenCalledWith("/staff/v1/reset-pin");

    await act(async () => {
      container.querySelector('[data-testid="toggle-status-v1"]').click();
    });
    expect(api.patch).toHaveBeenCalledWith("/staff/v1/disable");
    confirm.mockRestore();
  });

  test("a new account's one-time PIN is shown once with a Copy button", async () => {
    const writeText = jest.fn().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    api.post.mockResolvedValue({ data: { staff: { id: "n1", name: "New Person" }, temporary_pin: "4071" } });
    await renderTeam();
    expect(container.textContent).not.toContain("1234");
    act(() => {
      setInputValue(container.querySelector('[data-testid="staff-name-input"]'), "New Person");
    });
    await act(async () => {
      container.querySelector('[data-testid="add-staff-form"]').dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    const dialog = document.querySelector('[data-testid="one-time-pin"]');
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(document.querySelector('[data-testid="modal-close-button"]')).toBeNull();
    expect(document.querySelector('[data-testid="one-time-pin"]')).not.toBeNull();
    expect(dialog.textContent).toContain("New Person");
    expect(dialog.textContent).toContain("4071");
    expect(dialog.textContent).toContain("shown once");
    await act(async () => document.querySelector('[data-testid="one-time-pin-copy"]').click());
    expect(writeText).toHaveBeenCalledWith("4071");
    expect(document.querySelector('[data-testid="one-time-pin-copy"]').textContent).toBe("Copied");
    await act(async () => document.querySelector('[data-testid="one-time-pin-done"]').click());
    expect(document.querySelector('[data-testid="one-time-pin"]')).toBeNull();
    expect(document.body.textContent).not.toContain("4071");
  });

  test("reset and disable name the person first; cancel sends nothing", async () => {
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(false);
    await renderTeam();
    await act(async () => container.querySelector('[data-testid="reset-pin-v1"]').click());
    await act(async () => container.querySelector('[data-testid="toggle-status-v1"]').click());
    expect(confirm.mock.calls.map(([text]) => text)).toEqual([
      expect.stringContaining("Vol One"),
      expect.stringContaining("Vol One"),
    ]);
    expect(api.post).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="reset-pin-v1"]').textContent).not.toContain("1234");

    confirm.mockReturnValue(true);
    api.post.mockResolvedValue({ data: { ok: true, temporary_pin: "8350" } });
    const loads = api.get.mock.calls.length;
    await act(async () => container.querySelector('[data-testid="reset-pin-v1"]').click());
    expect(api.post).toHaveBeenCalledWith("/staff/v1/reset-pin");
    expect(document.querySelector('[data-testid="one-time-pin"]').textContent).toContain("8350");
    expect(api.get.mock.calls.length).toBeGreaterThan(loads);
    confirm.mockRestore();
  });

  test("a locked account shows its lockouts and can be unlocked after confirming", async () => {
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
    api.post.mockResolvedValue({ data: { ok: true } });
    await renderTeam();
    const row = container.querySelector('[data-testid="staff-row-v2"]');
    expect(row.querySelector('[data-testid="locked-v2"]').textContent).toContain("Locked until 24-09-2026 10:45");
    expect(row.querySelector('[data-testid="lockouts-v2"]').textContent).toContain("Locked out 3 times in 24 h, from 2 networks");
    expect(container.querySelector('[data-testid="unlock-v1"]')).toBeNull();
    const loads = api.get.mock.calls.length;
    await act(async () => row.querySelector('[data-testid="unlock-v2"]').click());
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Vol Locked"));
    expect(api.post).toHaveBeenCalledWith("/staff/v2/unlock");
    expect(api.get.mock.calls.length).toBeGreaterThan(loads);
    confirm.mockRestore();
  });

  test("team lead sees only volunteer create and no role or operator-line controls", async () => {
    mockAuth.user = { id: "tl-1", name: "Lead One", role: "team_lead" };
    api.get.mockImplementation((url) => {
      if (url === "/staff") {
        return Promise.resolve({
          data: {
            staff: [
              { id: "v1", name: "Vol One", role: "volunteer", team_lead_id: "tl-1", disabled_at: null },
            ],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    await renderTeam();
    expect(container.querySelector('[data-testid="staff-role-select"]')).toBeNull();
    expect(container.querySelector('[data-testid="staff-teamlead-select"]')).toBeNull();
    expect(container.querySelector('[data-testid="staff-line-select"]')).toBeNull();
    expect(container.textContent).toContain("Add Volunteer");
    expect(container.textContent).toContain("Vol One");
    expect(container.textContent).not.toContain("System Admin");
    act(() => {
      setInputValue(container.querySelector('[data-testid="staff-name-input"]'), "Vol Two");
    });
    await act(async () => {
      container.querySelector('[data-testid="add-staff-form"]').dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
    });
    expect(api.post).toHaveBeenCalledWith(
      "/staff",
      expect.objectContaining({ name: "Vol Two", role: "volunteer" }),
    );
    expect(api.get).not.toHaveBeenCalledWith("/staff/team-leads");
  });

  test("admin can reassign a volunteer before deleting a team lead", async () => {
    await renderTeam();
    const selector = container.querySelector('[data-testid="reassign-team-v1"]');
    expect(selector).not.toBeNull();

    await act(async () => {
      setInputValue(selector, "");
    });

    expect(api.patch).toHaveBeenCalledWith("/staff/v1/team-lead", { team_lead_id: null });
  });

  test("delete confirms account removal and calls the staff endpoint", async () => {
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
    await renderTeam();

    await act(async () => {
      container.querySelector('[data-testid="delete-staff-v1"]').click();
    });

    expect(confirm).toHaveBeenCalled();
    expect(api.delete).toHaveBeenCalledWith("/staff/v1");
    confirm.mockRestore();
  });
});
