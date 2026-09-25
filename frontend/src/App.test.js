import React, { act } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;

let mockUser = false;

jest.mock("./context/AuthContext", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({ user: mockUser, loading: false }),
  roleHome: () => "/desk",
}));
jest.mock("./pages/SelfRegister", () => ({ __esModule: true, default: () => <p>patient page</p> }));
jest.mock("./pages/Login", () => ({ __esModule: true, default: () => <p>staff sign-in</p> }));
jest.mock("./pages/Desk", () => ({ __esModule: true, default: () => <p>desk page</p> }));

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
  window.history.pushState({}, "", "/");
});

async function open(path) {
  window.history.pushState({}, "", path);
  await act(async () => root.render(<App />));
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
}

test("a visitor who is not signed in lands on patient self-registration", async () => {
  mockUser = false;
  await open("/");
  expect(container.textContent).toBe("patient page");
  expect(window.location.pathname).toBe("/");
});

test("signed-in staff who open the site go to their own screen", async () => {
  mockUser = { role: "volunteer" };
  await open("/");
  expect(window.location.pathname).toBe("/desk");
  expect(container.textContent).toBe("desk page");
});

test("staff sign-in keeps its own address", async () => {
  mockUser = false;
  await open("/login");
  expect(container.textContent).toBe("staff sign-in");
});
