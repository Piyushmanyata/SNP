import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { scrubActiveInput, useWedgeBurst } from "./useWedgeBurst";

global.IS_REACT_ACT_ENVIRONMENT = true;

function Harness({ onBurst, enabled = true, minLength = 20 }) {
  useWedgeBurst({ enabled, minLength, onBurst });
  return null;
}

let container = null;
let root = null;
let now = 0;

function fireKey(key) {
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  document.dispatchEvent(ev);
  return ev;
}

function typeFast(text, gap) {
  for (const ch of text) {
    now += gap;
    fireKey(ch);
  }
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  now = 0;
  jest.useFakeTimers();
  jest.spyOn(performance, "now").mockImplementation(() => now);
});

afterEach(() => {
  act(() => { root.unmount(); });
  container.remove();
  performance.now.mockRestore();
  jest.useRealTimers();
});

describe("useWedgeBurst", () => {
  test("fires onBurst for 40 chars at 10 ms gaps then Enter and prevents default", async () => {
    const onBurst = jest.fn();
    await act(async () => {
      root.render(<Harness onBurst={onBurst} />);
    });
    const payload = "A".repeat(40);
    typeFast(payload, 10);
    now += 10;
    const enter = fireKey("Enter");
    expect(onBurst).toHaveBeenCalledWith(payload);
    expect(enter.defaultPrevented).toBe(true);
  });

  test("does not fire at 120 ms gaps", async () => {
    const onBurst = jest.fn();
    await act(async () => {
      root.render(<Harness onBurst={onBurst} />);
    });
    typeFast("A".repeat(40), 120);
    now += 120;
    fireKey("Enter");
    expect(onBurst).not.toHaveBeenCalled();
  });

  test("does not fire for 10 fast chars", async () => {
    const onBurst = jest.fn();
    await act(async () => {
      root.render(<Harness onBurst={onBurst} />);
    });
    typeFast("A".repeat(10), 10);
    now += 10;
    fireKey("Enter");
    expect(onBurst).not.toHaveBeenCalled();
  });

  test("resets after a 600 ms pause", async () => {
    const onBurst = jest.fn();
    await act(async () => {
      root.render(<Harness onBurst={onBurst} />);
    });
    typeFast("HELLO", 10);
    now += 600;
    typeFast("B".repeat(40), 10);
    now += 10;
    fireKey("Enter");
    expect(onBurst).toHaveBeenCalledTimes(1);
    expect(onBurst).toHaveBeenCalledWith("B".repeat(40));
  });

  test("Tab also terminates a burst", async () => {
    const onBurst = jest.fn();
    await act(async () => {
      root.render(<Harness onBurst={onBurst} />);
    });
    typeFast("A".repeat(40), 10);
    now += 10;
    const tab = fireKey("Tab");
    expect(onBurst).toHaveBeenCalledWith("A".repeat(40));
    expect(tab.defaultPrevented).toBe(true);
  });
});

describe("scrubActiveInput", () => {
  test("strips the trailing burst from a focused input and dispatches input", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.value = "99AADHAAR|Sunita Devi|F|1975-06-14|123456781234|addr";
    input.focus();
    const seen = [];
    input.addEventListener("input", () => seen.push(input.value));
    const burst = "AADHAAR|Sunita Devi|F|1975-06-14|123456781234|addr";
    scrubActiveInput(burst);
    expect(input.value).toBe("99");
    expect(seen).toEqual(["99"]);
    input.remove();
  });
});
