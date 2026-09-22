import React, { act, lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import ErrorBoundary from "./ErrorBoundary";

global.IS_REACT_ACT_ENVIRONMENT = true;

let container = null;
let root = null;
let logged = [];
let consoleError = null;

const reloaded = () => logged.some((line) => line.includes("Not implemented: navigation"));

function Boom() {
  throw new Error("TypeError: cannot read property stack of undefined");
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  logged = [];
  consoleError = jest.spyOn(console, "error").mockImplementation((...args) => {
    logged.push(String(args[0]));
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  container = null;
  consoleError.mockRestore();
});

describe("ErrorBoundary", () => {
  test("renders its children while nothing fails", () => {
    act(() => {
      root.render(<ErrorBoundary><p>Desk queue</p></ErrorBoundary>);
    });
    expect(container.textContent).toContain("Desk queue");
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  test("a render failure offers recovery instead of a blank app and hides the technical error", () => {
    act(() => {
      root.render(<ErrorBoundary><Boom /></ErrorBoundary>);
    });
    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(container.textContent).not.toContain("cannot read property stack");
    expect(alert.className).toContain("no-print");

    const retry = container.querySelector('[data-testid="app-error-reload"]');
    expect(retry.tagName).toBe("BUTTON");
    expect(retry.className).toContain("min-h-[44px]");
    expect(reloaded()).toBe(false);

    act(() => {
      retry.click();
    });
    expect(reloaded()).toBe(true);
  });

  test("a lazy chunk that never arrives offers recovery instead of a blank app", async () => {
    const Missing = lazy(() => Promise.reject(new Error("Failed to fetch dynamically imported module")));
    await act(async () => {
      root.render(
        <ErrorBoundary>
          <Suspense fallback={<p>Loading</p>}><Missing /></Suspense>
        </ErrorBoundary>
      );
    });
    expect(container.querySelector('[data-testid="app-error-reload"]')).not.toBeNull();
    expect(container.textContent).not.toContain("dynamically imported module");
    expect(reloaded()).toBe(false);
  });
});
