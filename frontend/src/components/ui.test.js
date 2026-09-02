import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { Button, Modal } from "./ui";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("sm buttons meet 44px minimum touch target", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = ReactDOM.createRoot(container);
  act(() => {
    root.render(<Button size="sm">Seen</Button>);
  });
  expect(container.querySelector("button").className).toMatch(/min-h-\[44px\]/);
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("Modal", () => {
  let container;
  let root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = ReactDOM.createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function open(onClose = () => {}) {
    act(() => {
      root.render(<Modal open onClose={onClose} title="New Camp">body</Modal>);
    });
  }

  test("announces itself as a dialog to assistive tech", () => {
    open();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("New Camp");
  });

  test("Escape closes it, so a keyboard user is never trapped", () => {
    const onClose = jest.fn();
    open(onClose);
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(onClose).toHaveBeenCalled();
  });

  test("a closed modal does not answer Escape", () => {
    const onClose = jest.fn();
    act(() => {
      root.render(<Modal open={false} onClose={onClose} title="New Camp">body</Modal>);
    });
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  test("closing restores the page scroll it took", () => {
    open();
    expect(document.body.style.overflow).toBe("hidden");
    act(() => {
      root.render(<Modal open={false} onClose={() => {}} title="New Camp">body</Modal>);
    });
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
