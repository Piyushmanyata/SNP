import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import api from "../lib/api";
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
    let cancelled = false;
    let retry;
    const check = (attempt) => {
      api
        .get("/auth/me")
        .then((r) => {
          if (cancelled) return;
          setUser(r.data.user);
          setLoading(false);
        })
        .catch((err) => {
          if (cancelled) return;
          const status = err?.response?.status;
          if (status && status < 500) {
            setUser(false);
            setLoading(false);
            return;
          }
          retry = setTimeout(() => check(attempt + 1), Math.min(1000 * 2 ** attempt, 15000));
        });
    };
    check(0);
    return () => {
      cancelled = true;
      clearTimeout(retry);
    };
  }, []);

  useEffect(() => {
    const signOut = () => {
      setUser(false);
      setLoading(false);
    };
    window.addEventListener("snp:unauthorized", signOut);
    return () => window.removeEventListener("snp:unauthorized", signOut);
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
    await api.post("/auth/logout");
    clearSessionLine();
    setUser(false);
  }, []);

  const value = useMemo(
    () => ({ user, login, logout, changePin, loading }),
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
