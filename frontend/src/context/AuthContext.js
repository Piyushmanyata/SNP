import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import api from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=anon, obj=authed
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/auth/me")
      .then((r) => setUser(r.data.user))
      .catch(() => setUser(false))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    setUser(r.data.user);
    return r.data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {
      console.warn("Logout request failed:", e);
    }
    setUser(false);
  }, []);

  const value = useMemo(
    () => ({ user, setUser, login, logout, loading }),
    [user, login, logout, loading]
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
