import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Layout from "./Layout";
import { setOffline } from "../lib/connection";
import api from "../lib/api";

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
  test("SNP Camps is an accessible link back to the home route", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/team"]}>
          <Routes>
            <Route path="/team" element={<Layout title="Team">Staff management</Layout>} />
            <Route path="/" element={<p>Main page</p>} />
          </Routes>
        </MemoryRouter>,
      );
    });
    const home = container.querySelector('a[aria-label="SNP Camps home"]');
    expect(home).not.toBeNull();
    expect(home.textContent).toContain("SNP Camps");
    expect(home.getAttribute("href")).toBe("/");
    await act(async () => { home.click(); });
    expect(container.textContent).toBe("Main page");
  });

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

describe("the offline banner", () => {
  afterEach(() => { act(() => setOffline(false)); jest.useRealTimers(); });

  test("asks the server every 10 seconds while offline, so a screen that does not poll recovers", async () => {
    jest.useFakeTimers();
    const get = jest.spyOn(api, "get").mockImplementation(async () => { setOffline(false); return { data: {} }; });
    await renderLayout();
    act(() => setOffline(true));
    await act(async () => { jest.advanceTimersByTime(10000); });
    expect(get).toHaveBeenCalledWith("/health");
    expect(container.querySelector('[data-testid="offline-banner"]')).toBeNull();
    get.mockRestore();
  });

  test("appears when the server cannot be reached and clears when it answers again", async () => {
    await renderLayout();
    const banner = () => container.querySelector('[data-testid="offline-banner"]');
    expect(banner()).toBeNull();
    act(() => setOffline(true));
    expect(banner().textContent).toBe(
      "No connection to the server. Hold the queue — nothing is lost. This clears by itself when the connection returns.",
    );
    expect(banner().getAttribute("role")).toBe("alert");
    expect(container.textContent).toContain("ok");
    act(() => setOffline(false));
    expect(banner()).toBeNull();
  });
});
