import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import Layout from "../components/Layout";
import api from "../lib/api";
import { LINE_STORAGE_KEY } from "../lib/operatorLines";

jest.mock("../lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
  formatApiError: jest.requireActual("../lib/api").formatApiError,
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

test("failed logout preserves the session and explains that retry is required", async () => {
  window.history.replaceState({}, "", "/desk");
  sessionStorage.setItem(LINE_STORAGE_KEY, "medicine");
  api.get.mockResolvedValue({ data: { user: { id: "u1", name: "Operator", role: "volunteer" } } });
  api.post.mockRejectedValueOnce(new Error("Network Error")).mockResolvedValueOnce({ data: {} });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = ReactDOM.createRoot(container);
  try {
    await act(async () => root.render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/desk"]}>
          <Routes>
            <Route path="/desk" element={<Layout>Patient desk</Layout>} />
            <Route path="/login" element={<p>Login page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    ));
    await act(async () => container.querySelector('[data-testid="logout-button"]').click());
    expect(container.textContent).toContain("Logout failed. You are still signed in.");
    expect(container.textContent).toContain("Operator");
    expect(sessionStorage.getItem(LINE_STORAGE_KEY)).toBe("medicine");
    await act(async () => container.querySelector('[data-testid="logout-button"]').click());
    expect(container.textContent).toContain("Login page");
    expect(sessionStorage.getItem(LINE_STORAGE_KEY)).toBeNull();
  } finally {
    act(() => root.unmount());
    container.remove();
    window.history.replaceState({}, "", "/");
    sessionStorage.clear();
  }
});

describe("session check", () => {
  let container;
  let root;

  function Probe() {
    const { user, loading } = useAuth();
    return <p data-testid="probe">{loading ? "loading" : user ? user.name : "signed out"}</p>;
  }

  const probe = () => container.querySelector('[data-testid="probe"]').textContent;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    window.history.replaceState({}, "", "/desk");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = ReactDOM.createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    window.history.replaceState({}, "", "/");
    localStorage.clear();
    jest.useRealTimers();
  });

  test("a patient's phone at the front page is not asked for a session", async () => {
    window.history.replaceState({}, "", "/");
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    expect(api.get).not.toHaveBeenCalled();
    expect(probe()).toBe("signed out");
  });

  test("a staff device at the front page checks its session", async () => {
    localStorage.setItem("snp:staff-device", "1");
    window.history.replaceState({}, "", "/");
    api.get.mockResolvedValueOnce({ data: { user: { id: "u1", name: "Operator", role: "volunteer" } } });
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    expect(api.get).toHaveBeenCalledWith("/auth/me");
    expect(probe()).toBe("Operator");
  });

  test("a live session marks the device as staff and a sign-out clears the mark", async () => {
    api.get.mockResolvedValueOnce({ data: { user: { id: "u1", name: "Operator", role: "volunteer" } } });
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    expect(localStorage.getItem("snp:staff-device")).toBe("1");
    await act(async () => { window.dispatchEvent(new Event("snp:unauthorized")); });
    expect(localStorage.getItem("snp:staff-device")).toBeNull();
  });

  test("signing in marks the device as staff", async () => {
    window.history.replaceState({}, "", "/login");
    api.post.mockResolvedValueOnce({ data: { user: { id: "u1", name: "Operator", role: "volunteer" } } });
    let auth;
    function Grab() {
      auth = useAuth();
      return null;
    }
    await act(async () => root.render(<AuthProvider><Grab /></AuthProvider>));
    await act(async () => { await auth.login("Operator", "1234"); });
    expect(localStorage.getItem("snp:staff-device")).toBe("1");
  });

  test("a network failure keeps the session loading and retries", async () => {
    api.get
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { user: { id: "u1", name: "Operator", role: "volunteer" } } });
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    expect(probe()).toBe("loading");
    await act(async () => { jest.advanceTimersByTime(1000); });
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(probe()).toBe("Operator");
  });

  test("a 401 signs out without retrying", async () => {
    api.get.mockRejectedValueOnce({ response: { status: 401 } });
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    await act(async () => { jest.advanceTimersByTime(30000); });
    expect(probe()).toBe("signed out");
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  test("an unauthorized response elsewhere signs the user out", async () => {
    api.get.mockResolvedValueOnce({ data: { user: { id: "u1", name: "Operator", role: "volunteer" } } });
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    expect(probe()).toBe("Operator");
    await act(async () => { window.dispatchEvent(new Event("snp:unauthorized")); });
    expect(probe()).toBe("signed out");
  });
});
