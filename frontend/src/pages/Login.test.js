import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Login from "./Login";
import api from "../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
    },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ login: jest.fn(), user: null, loading: false }),
  roleHome: () => "/desk",
}));

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  jest.useFakeTimers();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });

  api.get.mockResolvedValue({
    data: {
      camp: { id: "c-live", name: "Active Howrah Camp", venue: "Hall" },
      total_seats: 80,
      total_registered: 15,
      days: [
        { id: "d-1", day_date: "2026-09-01", registered: 12, seat_limit: 50, remaining: 38 },
        { id: "d-2", day_date: "2026-09-02", registered: 3, seat_limit: 30, remaining: 27 },
      ],
    },
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
  jest.useRealTimers();
});

describe("Login page occupancy", () => {
  test("does not overlap occupancy requests while a slow response is pending", async () => {
    let resolve;
    api.get.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    await act(async () => { root.render(<MemoryRouter><Login /></MemoryRouter>); });
    await act(async () => { jest.advanceTimersByTime(15000); });
    expect(api.get).toHaveBeenCalledTimes(1);
    await act(async () => { resolve({ data: { camp: null } }); });
    await act(async () => { jest.advanceTimersByTime(5000); });
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  test("pauses occupancy requests while hidden and refreshes when visible", async () => {
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    await act(async () => { root.render(<MemoryRouter><Login /></MemoryRouter>); });
    await act(async () => { jest.advanceTimersByTime(15000); });
    expect(api.get).not.toHaveBeenCalled();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  test("leads with registrations against total camp seats and shows no patient details", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      );
    });

    expect(container.querySelector('[data-testid="goto-self-register-link"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="public-occupancy"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="occupancy-headline"]').textContent).toBe("15 / 80");
    expect(container.textContent).toContain("registered against 80 seats");
    expect(container.textContent).toContain("65 left");
    expect(container.textContent).not.toContain("Anil Kapoor");
    expect(container.textContent).not.toContain("9876543210");
    expect(api.get).toHaveBeenCalledWith("/camps/active/public");
  });

  test("replaces the marketing copy", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      );
    });
    expect(container.textContent).not.toContain("calm precision");
    expect(container.textContent).not.toContain("Aadhaar-based registration, prescription printing");
  });

  test("refreshes occupancy on a short poll", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      );
    });
    expect(api.get).toHaveBeenCalledTimes(1);

    await act(async () => {
      jest.advanceTimersByTime(5000);
    });
    expect(api.get.mock.calls.filter((c) => c[0] === "/camps/active/public").length).toBeGreaterThanOrEqual(2);
  });
});
