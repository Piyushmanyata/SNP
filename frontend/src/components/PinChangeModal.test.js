import React, { act } from "react";
import ReactDOM from "react-dom/client";
import PinChangeModal from "./PinChangeModal";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockAuth = { user: null, changePin: jest.fn() };

jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

let container = null;
let root = null;

function type(testid, value) {
  const node = document.querySelector(`[data-testid="${testid}"]`);
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(node, value);
  node.dispatchEvent(new Event("input", { bubbles: true }));
}

async function submit() {
  await act(async () => {
    document.querySelector('[data-testid="pin-change-form"]').dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = ReactDOM.createRoot(container);
  mockAuth.changePin = jest.fn().mockResolvedValue({});
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PIN change", () => {
  test("a team lead's first sign-in asks for the one-time PIN and a 6-digit PIN of their own", async () => {
    mockAuth.user = { id: "t1", name: "Priya", role: "team_lead", pin_length: 6, must_change_pin: true };
    await act(async () => root.render(<PinChangeModal />));
    expect(document.querySelector('[data-testid="current-pin-input"]').value).toBe("");
    expect(document.body.textContent).toContain("New 6-digit PIN");
    expect(document.body.textContent).not.toContain("1234");

    act(() => {
      type("current-pin-input", "904512");
      type("new-pin-input", "2580");
      type("confirm-pin-input", "2580");
    });
    await submit();
    expect(mockAuth.changePin).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alert"]').textContent).toContain("6 digits");

    act(() => {
      type("new-pin-input", "2580149");
      type("confirm-pin-input", "258014");
    });
    expect(document.querySelector('[data-testid="new-pin-input"]').value).toBe("258014");
    await submit();
    expect(mockAuth.changePin).toHaveBeenCalledWith("904512", "258014");
  });

  test("a volunteer chooses 4 digits and sees the server's reason for a refused PIN", async () => {
    mockAuth.user = { id: "v1", name: "Ramesh", role: "volunteer", pin_length: 4, must_change_pin: true };
    mockAuth.changePin = jest.fn().mockRejectedValue({
      response: { data: { detail: { code: "PIN_POLICY", message: "Choose a PIN that is not one digit repeated or a straight run like 1234." } } },
    });
    await act(async () => root.render(<PinChangeModal />));
    expect(document.body.textContent).toContain("New 4-digit PIN");
    act(() => {
      type("current-pin-input", "9051");
      type("new-pin-input", "7777");
      type("confirm-pin-input", "7777");
    });
    await submit();
    expect(mockAuth.changePin).toHaveBeenCalledWith("9051", "7777");
    expect(document.querySelector('[role="alert"]').textContent).toContain("straight run");
  });
});
