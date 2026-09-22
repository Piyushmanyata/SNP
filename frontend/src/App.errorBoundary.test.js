import React, { act } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("./context/AuthContext", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => {
    throw new Error("session lookup exploded");
  },
  roleHome: () => "/desk",
}));

test("a screen that fails to render leaves the app recoverable, never blank", () => {
  const consoleError = jest.spyOn(console, "error").mockImplementation(() => {});
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = ReactDOM.createRoot(container);
  try {
    act(() => {
      root.render(<App />);
    });
    expect(container.querySelector('[data-testid="app-error-reload"]')).not.toBeNull();
    expect(container.textContent).not.toContain("session lookup exploded");
  } finally {
    act(() => {
      root.unmount();
    });
    container.remove();
    consoleError.mockRestore();
  }
});
