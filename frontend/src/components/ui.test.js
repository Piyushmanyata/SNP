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

  test("keyboard focus stays inside the dialog and returns to its opener", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    act(() => root.render(<Modal open title="PIN"><input aria-label="PIN" /><button>Save</button></Modal>));
    const input = document.querySelector('input[aria-label="PIN"]');
    const save = document.querySelector('[role="dialog"] button:last-child');
    expect(document.activeElement).toBe(input);
    save.focus();
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", cancelable: true })));
    expect(document.activeElement).toBe(input);
    act(() => root.render(<Modal open={false} title="PIN" />));
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  test("first focus lands on the first form field, not the close button", () => {
    act(() => root.render(<Modal open onClose={() => {}} title="New Registration"><button>Scan</button><input aria-label="Name" /></Modal>));
    expect(document.activeElement).toBe(document.querySelector('input[aria-label="Name"]'));
  });

  test("a dirty dialog ignores the backdrop and asks before Escape or the X discards it", () => {
    const onClose = jest.fn();
    const confirm = jest.spyOn(window, "confirm").mockReturnValue(false);
    act(() => root.render(<Modal open dirty onClose={onClose} title="New Registration"><input aria-label="Name" /></Modal>));
    act(() => document.querySelector('[role="presentation"]').click());
    expect(confirm).not.toHaveBeenCalled();
    act(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(confirm).toHaveBeenCalledWith("Discard changes?");
    expect(onClose).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    act(() => document.querySelector('[data-testid="modal-close-button"]').click());
    expect(onClose).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
  });

  test("a clean dialog closes on the backdrop without asking", () => {
    const onClose = jest.fn();
    const confirm = jest.spyOn(window, "confirm");
    open(onClose);
    act(() => document.querySelector('[role="presentation"]').click());
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirm).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  test("a mandatory dialog has no inactive close button", () => {
    act(() => root.render(<Modal open title="Set PIN">Required</Modal>));
    expect(document.querySelector('[data-testid="modal-close-button"]')).toBeNull();
  });
});
