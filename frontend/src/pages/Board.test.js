import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import Board from "./Board";
import api from "../lib/api";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api", () => {
  const actual = jest.requireActual("../lib/api");
  return {
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn() },
    formatApiError: actual.formatApiError,
    errorPayload: actual.errorPayload,
  };
});

jest.mock("../components/Layout", () => {
  return function MockLayout({ children, title }) {
    return <div data-testid="mock-layout">{title}{children}</div>;
  };
});

const PAYLOAD = {
  as_of: "2026-09-01T10:00:00+00:00",
  state: "current",
  camp: { id: "c1", name: "Sikar Camp" },
  day: { id: "d1", day_date: "2026-09-01" },
  stages: {
    arrived: 12,
    awaiting_print: 2,
    awaiting_seen: 1,
    seen: 8,
    transcription_backlog: 3,
  },
  fulfilment: {
    medicine: { fulfilled: 4, not_available: 1 },
    specs_fixed: { fulfilled: 0 },
    specs_made: { deferred: 2 },
    ot: { deferred: 3, declined: 2 },
  },
  activity: [
    { id: "d1", name: "Vol 1", last_arrival_at: "10:00", quiet: false },
    { id: "d2", name: "Vol 2", last_arrival_at: "09:20", quiet: true },
  ],
  quiet_count: 1,
  sms_failures: 1,
  next_ot: { day_date: "2026-09-02", venue: "OT Hall", seats_left: 7 },
  next_specs: { day_date: "2026-09-05", venue: "Optical", start_time: "09:00", end_time: "12:00" },
};

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  api.get.mockResolvedValue({ data: PAYLOAD });
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
});

describe("Camp-day board", () => {
  test("shows an initial request failure and recovers on the next refresh", async () => {
    api.get.mockRejectedValueOnce(new Error("Network Error"));
    await act(async () => { root.render(<MemoryRouter><Board /></MemoryRouter>); });
    expect(container.querySelector('[data-testid="board-loading"]')).toBeNull();
    expect(container.querySelector('[role="alert"]').textContent).toContain("Network Error");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('[data-testid="board-kpis"]')).not.toBeNull();
  });

  test("renders KPIs before the activity table with camp day and quiet text", async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Board />
        </MemoryRouter>,
      );
    });
    const page = container.querySelector('[data-testid="board-page"]').textContent;
    const kpis = container.querySelector('[data-testid="board-kpis"]');
    const table = container.querySelector('[data-testid="board-activity"]');
    expect(kpis).not.toBeNull();
    expect(table).not.toBeNull();
    expect(page.indexOf("Arrived")).toBeLessThan(page.indexOf("Registration activity"));
    expect(container.querySelector('[data-testid="board-context"]').textContent).toContain("Sikar Camp");
    expect(container.querySelector('[data-testid="board-context"]').textContent).toContain("Sikar Camp · 01-09-2026 · as of 01-09-2026 15:30");
    expect(container.querySelector('[data-testid="board-next-ot"]').textContent).toContain("02-09-2026");
    expect(container.querySelector('[data-testid="board-next-specs"]').textContent).toContain("05-09-2026");
    expect(container.querySelector('[data-testid="board-next-ot"]').textContent).toContain("7 seats");
    expect(container.querySelector('[data-testid="board-next-specs"]').textContent).toContain("09:00–12:00");
    expect(container.querySelector('[data-testid="board-ot-scheduled"]').textContent).toContain("3");
    expect(page).toContain("Surgery declined");
    expect(container.querySelector('[data-testid="board-ot-declined"]').textContent).toBe("2");
    expect(container.querySelector('[data-testid="board-ot-done"]')).toBeNull();
    expect(page).not.toContain("OT done");
    expect(container.querySelector('[data-testid="quiet-text-d2"]').textContent).toBe("Quiet");
    expect(table.querySelector("caption")).not.toBeNull();
    expect(table.querySelector("th[scope='col']")).not.toBeNull();
  });

  test("poll pauses while hidden, ignores stale, and resumes on visible", async () => {
    jest.useFakeTimers();
    let resolveFirst;
    api.get.mockImplementation(() => new Promise((resolve) => {
      resolveFirst = resolve;
    }));
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Board />
        </MemoryRouter>,
      );
    });
    expect(api.get).toHaveBeenCalledTimes(1);
    await act(async () => {
      jest.advanceTimersByTime(15000);
    });
    expect(api.get).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveFirst({ data: PAYLOAD });
    });
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    api.get.mockResolvedValue({ data: PAYLOAD });
    await act(async () => {
      jest.advanceTimersByTime(15000);
    });
    expect(api.get).toHaveBeenCalledTimes(1);
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(api.get).toHaveBeenCalledTimes(2);
    jest.useRealTimers();
  });

  test("no-camp and stale states are explicit", async () => {
    api.get.mockResolvedValueOnce({ data: { ...PAYLOAD, state: "no_camp", camp: null, day: null } });
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Board />
        </MemoryRouter>,
      );
    });
    expect(container.querySelector('[data-testid="board-no-camp"]').textContent).toContain("No active camp");

    api.get.mockRejectedValueOnce({ response: { data: { detail: "down" } } });
    await act(async () => {
      root.unmount();
      root = ReactDOM.createRoot(container);
      root.render(
        <MemoryRouter>
          <Board />
        </MemoryRouter>,
      );
    });
    api.get.mockResolvedValueOnce({ data: PAYLOAD });
    await act(async () => {
      root.unmount();
      root = ReactDOM.createRoot(container);
      root.render(
        <MemoryRouter>
          <Board />
        </MemoryRouter>,
      );
    });
    api.get.mockRejectedValueOnce(new Error("network"));
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
  });
});
