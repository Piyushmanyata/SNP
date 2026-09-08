import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { scrubActiveInput, useWedgeBurst } from "./useWedgeBurst";

global.IS_REACT_ACT_ENVIRONMENT = true;

function Harness({ onBurst, onInterrupted, enabled = true, minLength = 20 }) {
  const scan = useWedgeBurst({ enabled, minLength, onBurst, onInterrupted });
  return <output>{scan?.receiving ? "Receiving scanner data" : "Ready"}</output>;
}

let container = null;
let root = null;
let now = 0;

function fireKey(key, options = {}) {
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options });
  act(() => { document.dispatchEvent(ev); });
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
  test.each(["timeout", "late terminator", "Escape"])("reports an identified burst interrupted by %s once without exposing its data", async (interruption) => {
    const onBurst = jest.fn();
    const onInterrupted = jest.fn();
    await act(async () => { root.render(<Harness onBurst={onBurst} onInterrupted={onInterrupted} />); });
    typeFast("9".repeat(30), 10);
    if (interruption === "timeout") act(() => { jest.advanceTimersByTime(501); });
    else if (interruption === "late terminator") {
      now += 501;
      fireKey("Enter");
    } else fireKey("Escape");
    expect(onInterrupted).toHaveBeenCalledTimes(1);
    expect(onInterrupted).toHaveBeenCalledWith();
    fireKey("Enter");
    act(() => { jest.advanceTimersByTime(501); });
    expect(onInterrupted).toHaveBeenCalledTimes(1);
    expect(onBurst).not.toHaveBeenCalled();
  });

  test("does not report interruption for typing, complete scans, disabling or unmounting", async () => {
    const onInterrupted = jest.fn();
    await act(async () => { root.render(<Harness onInterrupted={onInterrupted} />); });
    typeFast("Typing", 120);
    act(() => { jest.advanceTimersByTime(501); });
    typeFast("9".repeat(30), 10);
    fireKey("Enter");
    typeFast("8".repeat(30), 10);
    await act(async () => { root.render(<Harness enabled={false} onInterrupted={onInterrupted} />); });
    await act(async () => { root.render(<Harness onInterrupted={onInterrupted} />); });
    typeFast("7".repeat(30), 10);
    await act(async () => { root.render(null); });
    act(() => { jest.advanceTimersByTime(501); });
    expect(onInterrupted).not.toHaveBeenCalled();
  });

  test.each([
    ["Backspace", {}],
    ["ArrowLeft", {}],
    ["Escape", {}],
    ["a", { ctrlKey: true }],
    ["a", { altKey: true }],
    ["a", { metaKey: true }],
    ["9", { repeat: true }],
    ["9", { isComposing: true }],
  ])("does not consume typing interrupted by %s %j", async (key, options) => {
    const onBurst = jest.fn();
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    typeFast("9".repeat(30), 10);
    expect(fireKey(key, options).defaultPrevented).toBe(false);
    expect(container.textContent).toBe("Ready");
    expect(fireKey("Enter").defaultPrevented).toBe(false);
    expect(onBurst).not.toHaveBeenCalled();
  });

  test("unmounting removes capture and a new mount starts ready", async () => {
    const onBurst = jest.fn();
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    typeFast("9".repeat(30), 10);
    await act(async () => { root.render(null); });
    expect(fireKey("Enter").defaultPrevented).toBe(false);
    act(() => { jest.advanceTimersByTime(501); });
    expect(onBurst).not.toHaveBeenCalled();
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    expect(container.textContent).toBe("Ready");
  });

  test("disabling and re-enabling discards the partial scan and receiving state", async () => {
    const onBurst = jest.fn();
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    typeFast("9".repeat(30), 10);
    await act(async () => { root.render(<Harness enabled={false} onBurst={onBurst} />); });
    expect(container.textContent).toBe("Ready");
    typeFast("8".repeat(30), 10);
    fireKey("Enter");
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    expect(container.textContent).toBe("Ready");
    fireKey("Enter");
    expect(onBurst).not.toHaveBeenCalled();
    typeFast("7".repeat(30), 10);
    fireKey("Enter");
    expect(onBurst).toHaveBeenCalledWith("7".repeat(30));
  });

  test.each([true, false])("discards an interrupted burst even when the idle timer runs: %s", async (runTimer) => {
    const onBurst = jest.fn();
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    typeFast("9".repeat(40), 10);
    now += 501;
    if (runTimer) {
      act(() => { jest.advanceTimersByTime(501); });
      expect(container.textContent).toBe("Ready");
    }
    expect(fireKey("Enter").defaultPrevented).toBe(false);
    expect(onBurst).not.toHaveBeenCalled();
    expect(container.textContent).toBe("Ready");
    typeFast("8".repeat(40), 10);
    fireKey("Tab");
    expect(onBurst).toHaveBeenCalledWith("8".repeat(40));
  });

  test("shows receiving during a long burst before its terminator", async () => {
    const onBurst = jest.fn();
    await act(async () => { root.render(<Harness onBurst={onBurst} />); });
    typeFast("9".repeat(20), 10);
    expect(container.textContent).toBe("Receiving scanner data");
    expect(onBurst).not.toHaveBeenCalled();
    typeFast("9".repeat(4000), 10);
    expect(container.textContent).toBe("Receiving scanner data");
    fireKey("Enter");
    expect(container.textContent).toBe("Ready");
    expect(onBurst).toHaveBeenCalledWith("9".repeat(4020));
  });

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
    expect(container.textContent).toBe("Ready");
    now += 120;
    expect(fireKey("Enter").defaultPrevented).toBe(false);
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
