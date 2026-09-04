import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LogOut, Stethoscope } from "lucide-react";
import { Badge } from "./ui";
import { needsRoster, readRoster, clearRoster } from "../lib/roster";
import { LEAD_ROLES } from "../constants/roles";

const ROLE_LABELS = {
  admin: "Admin",
  team_lead: "Team Lead",
  volunteer: "Volunteer",
  clinical_desk_operator: "Clinical Desk",
};

export default function Layout({ children, title, onHandOver }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const roster = needsRoster(user) ? readRoster() : null;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 text-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center">
              <Stethoscope className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="font-display font-extrabold text-lg leading-none">SNP Camps</p>
              <p className="text-[11px] text-slate-400 leading-none mt-1">{title || "Camp Management"}</p>
            </div>
          </div>
          {user && (
            <div className="flex items-center gap-3">
              <div className="hidden sm:block text-right">
                <p className="text-sm font-semibold leading-none">{user.name}</p>
                <p className="text-[11px] text-slate-400 mt-1">{user.email}</p>
              </div>
              {LEAD_ROLES.includes(user.role) && (
                <Link
                  to="/board"
                  data-testid="board-link"
                  className="min-h-[44px] px-3 rounded-xl text-sm font-semibold text-slate-300 hover:text-white hover:bg-slate-800 flex items-center"
                >
                  Board
                </Link>
              )}
              <Badge tone="emerald">{ROLE_LABELS[user.role] || user.role}</Badge>
              {roster && (
                <>
                  <span data-testid="roster-name" className="text-sm font-semibold">
                    {roster.name}
                  </span>
                  <button
                    type="button"
                    data-testid="roster-handover"
                    className="min-h-[44px] min-w-[44px] px-3 rounded-xl text-sm font-semibold text-slate-300 hover:text-white hover:bg-slate-800"
                    onClick={() => {
                      clearRoster();
                      onHandOver?.();
                    }}
                  >
                    Hand over
                  </button>
                </>
              )}
              <button
                onClick={async () => { await logout(); navigate("/login"); }}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-slate-300 hover:text-white hover:bg-slate-800"
                data-testid="logout-button"
                title="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6 animate-fade-up">{children}</main>
    </div>
  );
}
