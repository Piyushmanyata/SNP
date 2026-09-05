import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import api from "../lib/api";
import logger from "../lib/logger";
import { clearSessionLine } from "../lib/operatorLines";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=anon, obj=authed
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const path = window.location.pathname || "";
    if (path === "/login" || path === "/self-register") {
      setUser(false);
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((r) => setUser(r.data.user))
      .catch(() => setUser(false))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (name, pin) => {
    clearSessionLine();
    const r = await api.post("/auth/login", { name, pin });
    setUser(r.data.user);
    return r.data.user;
  }, []);

  const changePin = useCallback(async (current_pin, new_pin) => {
    const r = await api.post("/auth/change-pin", { current_pin, new_pin });
    setUser(r.data.user);
    return r.data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {
      logger.warn("Logout request failed:", e);
    }
    clearSessionLine();
    setUser(false);
  }, []);

  const value = useMemo(
    () => ({ user, setUser, login, logout, changePin, loading }),
    [user, login, logout, changePin, loading]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

export function roleHome(role) {
  switch (role) {
    case "admin": return "/admin";
    case "team_lead": return "/desk";
    case "volunteer": return "/desk";
    case "clinical_desk_operator": return "/clinical";
    default: return "/login";
  }
}
