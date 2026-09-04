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
  arrived_today: 12,
  seen_today: 8,
  transcription_backlog: 3,
  sms_failed_today: 1,
  desks: [
    { account_id: "d1", name: "Desk 1", last_15m: 4, last_60m: 10, quiet: false },
    { account_id: "d2", name: "Desk 2", last_15m: 0, last_60m: 2, quiet: true },
  ],
  lines: { medicine: 1, specs_fixed: 0, specs_made: 2, ot: 1 },
  next_ot_day: { day_date: "2026-09-02", seats_left: 7 },
  next_specs_day: null,
};

let container = null;
let root = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  jest.clearAllMocks();
  api.get.mockResolvedValue({ data: PAYLOAD });
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
});

describe("Camp-day board", () => {
  test("quiet rows have data-quiet true and polls again after 15 s", async () => {
    jest.useFakeTimers();
    await act(async () => {
      root.render(
        <MemoryRouter>
          <Board />
        </MemoryRouter>,
      );
    });
    const quiet = container.querySelector('[data-quiet="true"]');
    expect(quiet).not.toBeNull();
    expect(quiet.textContent).toContain("Desk 2");
    expect(container.querySelector('[data-testid="board-backlog"]').textContent).toContain("3");
    expect(api.get).toHaveBeenCalledWith("/board");
    expect(api.get).toHaveBeenCalledTimes(1);
    await act(async () => {
      jest.advanceTimersByTime(15000);
    });
    expect(api.get).toHaveBeenCalledTimes(2);
    jest.useRealTimers();
  });
});
