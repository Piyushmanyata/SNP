import React, { act } from "react";
import ReactDOM from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./AuthContext";
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
