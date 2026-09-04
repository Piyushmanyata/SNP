import React, { act } from "react";
import ReactDOM from "react-dom/client";
import RosterPicker from "./RosterPicker";
import api from "../lib/api";
import { ROSTER_STORAGE_KEY } from "../lib/roster";

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

let container = null;
let root = null;
let picked = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  picked = null;
  sessionStorage.clear();
  jest.clearAllMocks();
  api.get.mockResolvedValue({
    data: {
      entries: [
        { id: "r-1", name: "Anita Sharma" },
        { id: "r-2", name: "Ramesh Kumar" },
      ],
    },
  });
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
});

async function renderPicker(open = true) {
  await act(async () => {
    root.render(
      <RosterPicker open={open} onPicked={(e) => { picked = e; }} />,
    );
  });
}

describe("RosterPicker", () => {
  test("filters names and writes sessionStorage on pick", async () => {
    await renderPicker();
    const search = document.querySelector('[data-testid="roster-search"]');
    expect(search).not.toBeNull();
    expect(document.querySelector('[data-testid="roster-pick-r-1"]')).not.toBeNull();
    expect(document.querySelector('[data-testid="roster-pick-r-2"]')).not.toBeNull();

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(search, "ram");
      search.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(document.querySelector('[data-testid="roster-pick-r-1"]')).toBeNull();
    expect(document.querySelector('[data-testid="roster-pick-r-2"]')).not.toBeNull();

    await act(async () => {
      document.querySelector('[data-testid="roster-pick-r-2"]').click();
    });
    expect(picked).toEqual({ id: "r-2", name: "Ramesh Kumar" });
    expect(JSON.parse(sessionStorage.getItem(ROSTER_STORAGE_KEY))).toEqual({
      id: "r-2",
      name: "Ramesh Kumar",
    });
  });
});
