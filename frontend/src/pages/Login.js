import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, roleHome } from "../context/AuthContext";
import { Button, Input, Field, Alert } from "../components/ui";
import api, { formatApiError } from "../lib/api";
import { Stethoscope } from "lucide-react";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [occupancy, setOccupancy] = useState(null);

  useEffect(() => {
    if (user) navigate(roleHome(user.role), { replace: true });
  }, [user, navigate]);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api.get("/camps/active/public").then((r) => {
        if (!cancelled) setOccupancy(r.data);
      }).catch(() => {});
    };
    load();
    const t = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const submit = useCallback(async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const u = await login(name.trim(), pin.trim());
      navigate(roleHome(u.role), { replace: true });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [name, pin, login, navigate]);

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-slate-900 text-white p-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center">
            <Stethoscope className="w-6 h-6" />
          </div>
          <span className="font-display font-extrabold text-xl">SNP Camps</span>
        </div>
        <Occupancy occupancy={occupancy} />
        <p className="text-xs text-slate-500 font-mono">Registered → Arrived → Seen · one active camp</p>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12 bg-slate-50">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center">
              <Stethoscope className="w-6 h-6 text-white" />
            </div>
            <span className="font-display font-extrabold text-xl">SNP Camps</span>
          </div>
          <h2 className="font-display text-2xl font-bold text-slate-900">Staff sign in</h2>
          <p className="text-sm text-slate-500 mt-1 mb-6">Patients never sign in. Staff only.</p>

          <form onSubmit={submit} className="space-y-4" data-testid="login-form">
            <Field label="Name">
              <Input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your registered name"
                required
                autoFocus
                autoComplete="username"
                data-testid="login-name-input"
              />
            </Field>
            <Field label="4-digit PIN">
              <Input
                type="password"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
                placeholder="••••"
                required
                maxLength={4}
                autoComplete="current-password"
                data-testid="login-pin-input"
              />
            </Field>
            <Alert>{error}</Alert>
            <Button type="submit" size="lg" className="w-full" disabled={busy} data-testid="login-submit-button">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-200">
            <a href="/self-register" className="block text-center text-sm font-semibold text-emerald-600 hover:text-emerald-700 min-h-[44px] flex items-center justify-center" data-testid="goto-self-register-link">
              Patient self-registration →
            </a>
            <div className="lg:hidden mt-4">
              <Occupancy occupancy={occupancy} compact />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Occupancy({ occupancy, compact }) {
  if (!occupancy?.camp) return null;
  const seats = occupancy.total_seats ?? 0;
  const registered = occupancy.total_registered ?? 0;
  const remaining = Math.max(0, seats - registered);
  return (
    <div
      className={compact ? "rounded-xl border border-slate-200 bg-white p-4" : ""}
      data-testid="public-occupancy"
    >
      <p className={`text-xs font-semibold uppercase tracking-wide ${compact ? "text-slate-500" : "text-emerald-400"}`}>
        {occupancy.camp.name}
      </p>
      <p
        className={`font-display font-extrabold leading-tight ${compact ? "text-2xl text-slate-900 mt-1" : "text-5xl mt-3"}`}
        data-testid="occupancy-headline"
      >
        {registered} / {seats}
      </p>
      <p className={`mt-2 text-sm ${compact ? "text-slate-600" : "text-slate-400"}`}>
        registered against {seats} seats · {remaining} left
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {occupancy.camp.venue}
      </p>
    </div>
  );
}
