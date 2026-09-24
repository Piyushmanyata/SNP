import React, { act } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockDesk = jest.fn(() => <p data-testid="desk-page">desk</p>);

jest.mock("./context/AuthContext", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({
    user: { id: "v1", name: "Ramesh", role: "volunteer", pin_length: 4, must_change_pin: true },
    loading: false,
    logout: jest.fn(),
    changePin: jest.fn(),
  }),
  roleHome: () => "/desk",
}));
jest.mock("./pages/Desk", () => ({ __esModule: true, default: () => mockDesk() }));

test("a forced PIN change shows only the PIN form, so no page loads data first", async () => {
  window.history.pushState({}, "", "/desk");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = ReactDOM.createRoot(container);
  try {
    await act(async () => {
      root.render(<App />);
    });
    expect(document.querySelector('[data-testid="pin-change-form"]')).not.toBeNull();
    expect(mockDesk).not.toHaveBeenCalled();
  } finally {
    act(() => {
      root.unmount();
    });
    container.remove();
  }
});
