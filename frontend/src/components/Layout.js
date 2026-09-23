import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LogOut, Stethoscope } from "lucide-react";
import { Alert, Badge } from "./ui";
import { formatApiError } from "../lib/api";
import PinChangeModal from "./PinChangeModal";

const ROLE_LABELS = {
  admin: "Admin",
  team_lead: "Team Lead",
  volunteer: "Volunteer",
  clinical_desk_operator: "Clinical Desk",
};

export default function Layout({ children, title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [changingPin, setChangingPin] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  return (
    <div className="min-h-screen">
      {(user?.must_change_pin || changingPin) && <PinChangeModal onClose={() => setChangingPin(false)} />}
      <header className="sticky top-0 z-40 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 text-white">
        <div className="max-w-6xl mx-auto px-3 sm:px-6 min-h-16 py-2 flex flex-wrap gap-2 items-center justify-between">
          <Link to="/" aria-label="SNP Camps home" className="min-h-[44px] flex items-center gap-3 rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 focus-visible:outline-offset-4">
            <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center">
              <Stethoscope className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="font-display font-extrabold text-lg leading-none">SNP Camps</p>
              <p className="text-[11px] text-slate-400 leading-none mt-1">{title || "Camp Management"}</p>
            </div>
          </Link>
          {user && (
            <div className="ml-auto flex items-center gap-1 sm:gap-3">
              <div className="hidden sm:block text-right">
                <p className="text-sm font-semibold leading-none">{user.name}</p>
              </div>
              <Badge tone="emerald">{ROLE_LABELS[user.role] || user.role}</Badge>
              <button
                type="button"
                data-testid="reset-pin-button"
                className="min-h-[44px] px-3 rounded-xl text-sm font-semibold text-slate-200 hover:text-white hover:bg-slate-800 active:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                onClick={() => setChangingPin(true)}
              >
                Reset PIN
              </button>
              <button
                disabled={loggingOut}
                onClick={async () => {
                  setLoggingOut(true);
                  setLogoutError("");
                  try {
                    await logout();
                    navigate("/login");
                  } catch (error) {
                    setLogoutError(`Logout failed. You are still signed in. Please retry. ${formatApiError(error)}`);
                  } finally {
                    setLoggingOut(false);
                  }
                }}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-slate-300 hover:text-white hover:bg-slate-800 active:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 disabled:opacity-50"
                data-testid="logout-button"
                title="Logout"
                aria-label="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 animate-fade-up">
        {logoutError && <Alert className="mb-4">{logoutError}</Alert>}
        {children}
      </main>
    </div>
  );
}
