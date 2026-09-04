import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Layout from "./Layout";
import { ROSTER_STORAGE_KEY } from "../lib/roster";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockAuth = { user: null, logout: jest.fn() };

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
  mockAuth.user = { id: "u1", name: "Desk 1", role: "volunteer", email: "desk1@snpcamps.org" };
  sessionStorage.setItem(ROSTER_STORAGE_KEY, JSON.stringify({ id: "r-1", name: "Ramesh Kumar" }));
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

describe("Layout roster chrome", () => {
  test("shows roster-name and roster-handover only for desk roles", async () => {
    await renderLayout();
    expect(container.querySelector('[data-testid="roster-name"]').textContent).toContain("Ramesh Kumar");
    expect(container.querySelector('[data-testid="roster-handover"]')).not.toBeNull();

    mockAuth.user = { id: "a1", name: "Admin", role: "admin", email: "admin@snpcamps.org" };
    await renderLayout();
    expect(container.querySelector('[data-testid="roster-name"]')).toBeNull();
    expect(container.querySelector('[data-testid="roster-handover"]')).toBeNull();

    mockAuth.user = { id: "t1", name: "Lead", role: "team_lead", email: "lead@snpcamps.org" };
    await renderLayout();
    expect(container.querySelector('[data-testid="roster-name"]')).toBeNull();
    expect(container.querySelector('[data-testid="roster-handover"]')).toBeNull();
    expect(container.querySelector('[data-testid="board-link"]')).not.toBeNull();

    mockAuth.user = { id: "u1", name: "Desk 1", role: "volunteer", email: "desk1@snpcamps.org" };
    await renderLayout();
    expect(container.querySelector('[data-testid="board-link"]')).toBeNull();
  });
});
