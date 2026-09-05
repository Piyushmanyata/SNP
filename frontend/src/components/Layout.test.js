import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Layout from "./Layout";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockAuth = { user: null, logout: jest.fn(), mustChangePin: false, changePin: jest.fn() };

jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  sessionStorage.clear();
  mockAuth.user = { id: "u1", name: "Ramesh Kumar", role: "volunteer" };
  mockAuth.logout.mockClear();
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
});

async function renderLayout() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <Layout title="Desk">ok</Layout>
      </MemoryRouter>,
    );
  });
}

describe("Layout header chrome", () => {
  test("shows identity and PIN reset beside logout without duplicate switching", async () => {
    await renderLayout();
    expect(container.textContent).toContain("Ramesh Kumar");
    expect(container.textContent).toContain("Volunteer");
    expect(container.querySelector('[data-testid="switch-volunteer-button"]')).toBeNull();
    const reset = container.querySelector('[data-testid="reset-pin-button"]');
    expect(reset).not.toBeNull();
    expect(reset.nextElementSibling.dataset.testid).toBe("logout-button");
    expect(container.querySelector('[data-testid="board-link"]')).toBeNull();
    expect(container.querySelector('[data-testid="team-link"]')).toBeNull();
  });

  test("keeps management navigation out of the header", async () => {
    mockAuth.user = { id: "t1", name: "Priya Lead", role: "team_lead" };
    await renderLayout();
    expect(container.textContent).toContain("Priya Lead");
    expect(container.querySelector('[data-testid="team-link"]')).toBeNull();
    expect(container.querySelector('[data-testid="board-link"]')).toBeNull();

    mockAuth.user = { id: "a1", name: "System Admin", role: "admin" };
    await renderLayout();
    expect(container.textContent).toContain("System Admin");
    expect(container.querySelector('[data-testid="team-link"]')).toBeNull();
    expect(container.querySelector('[data-testid="board-link"]')).toBeNull();
  });

  test("opens an optional PIN change with empty current PIN and allows cancellation", async () => {
    await renderLayout();
    await act(async () => container.querySelector('[data-testid="reset-pin-button"]').click());
    expect(document.querySelector('[data-testid="current-pin-input"]').value).toBe("");
    expect(document.body.textContent).toContain("Reset Your PIN");
    await act(async () => document.querySelector('[data-testid="pin-change-cancel"]').click());
    expect(document.querySelector('[data-testid="pin-change-form"]')).toBeNull();
  });
});
