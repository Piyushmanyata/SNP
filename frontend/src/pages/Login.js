import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, roleHome } from "../context/AuthContext";
import { Button, Input, Field, Alert } from "../components/ui";
import { formatApiError } from "../lib/api";
import { Stethoscope, ScanLine } from "lucide-react";

export default function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) navigate(roleHome(user.role), { replace: true });
  }, [user, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const u = await login(email.trim(), password);
      navigate(roleHome(u.role), { replace: true });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-slate-900 text-white p-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center">
            <Stethoscope className="w-6 h-6" />
          </div>
          <span className="font-display font-extrabold text-xl">SNP Camps</span>
        </div>
        <div>
          <h1 className="font-display text-4xl font-extrabold leading-tight">
            Run eye camps with<br /><span className="text-emerald-400">calm precision.</span>
          </h1>
          <p className="mt-4 text-slate-400 max-w-md">
            Aadhaar-based registration, prescription printing, and a full clinical desk — built for the field, on any device.
          </p>
          <div className="mt-8 flex items-center gap-3 text-slate-300">
            <ScanLine className="w-5 h-5 text-emerald-400" />
            <span className="text-sm">Scan · Register · Print · See · Transcribe</span>
          </div>
        </div>
        <p className="text-xs text-slate-500 font-mono">Registered → Seen · one active camp · presence-once</p>
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
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="you@snpcamps.org" required autoComplete="username" data-testid="login-email-input" />
            </Field>
            <Field label="Password">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••" required autoComplete="current-password" data-testid="login-password-input" />
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
          </div>
        </div>
      </div>
    </div>
  );
}
