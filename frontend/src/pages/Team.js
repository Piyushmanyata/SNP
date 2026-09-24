import React, { useCallback, useEffect, useRef, useState } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import api, { formatApiError } from "../lib/api";
import { Alert, Badge, Button, Card, Field, Input, Modal, Select } from "../components/ui";
import { displayTimestamp } from "../lib/dates";

const ALL_ROLES = [
  { value: "volunteer", label: "Volunteer" },
  { value: "clinical_desk_operator", label: "Clinical Desk Operator" },
  { value: "team_lead", label: "Team Lead" },
  { value: "admin", label: "Admin" },
];

function OneTimePin({ name, pin, onDone }) {
  const [copy, setCopy] = useState("Copy");
  const onCopy = () => navigator.clipboard.writeText(pin).then(() => setCopy("Copied"), () => setCopy("Copy failed"));
  return (
    <Modal open title={`One-time PIN for ${name}`} size="sm">
      <div data-testid="one-time-pin" className="space-y-4">
        <p className="font-mono text-4xl font-bold tracking-[0.3em] text-slate-900 text-center">{pin}</p>
        <p className="text-sm text-slate-600">
          This PIN is shown once. Give it to {name} in person; they choose their own PIN at first sign-in.
        </p>
        <div className="flex gap-2">
          {navigator.clipboard && (
            <Button type="button" variant="outline" className="flex-1" onClick={onCopy} data-testid="one-time-pin-copy">
              {copy}
            </Button>
          )}
          <Button type="button" className="flex-1" onClick={onDone} data-testid="one-time-pin-done">Done</Button>
        </div>
      </div>
    </Modal>
  );
}

export default function Team() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isTeamLead = user?.role === "team_lead";

  const [staff, setStaff] = useState([]);
  const [teamLeads, setTeamLeads] = useState([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState("volunteer");
  const [selectedLead, setSelectedLead] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [oneTimePin, setOneTimePin] = useState(null);
  const [nameFilter, setNameFilter] = useState("");
  const assigning = useRef(false);

  const load = useCallback(async () => {
    try {
      const [staffRes, leadsRes] = await Promise.all([
        api.get("/staff"),
        isAdmin ? api.get("/staff/team-leads") : Promise.resolve({ data: { team_leads: [] } }),
      ]);
      setStaff(staffRes.data.staff || []);
      setTeamLeads(leadsRes.data.team_leads || []);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, [isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  const onAdd = useCallback(
    async (e) => {
      e.preventDefault();
      setErr("");
      setMsg("");
      if (!name.trim()) {
        setErr("Name is required");
        return;
      }
      setBusy(true);
      try {
        const payload = {
          name: name.trim(),
          role: isAdmin ? role : "volunteer",
          phone: phone.trim() || null,
          team_lead_id: isAdmin && role === "volunteer" ? (selectedLead || null) : null,
        };
        const created = await api.post("/staff", payload);
        setOneTimePin({ name: payload.name, pin: created.data.temporary_pin });
        setMsg(`Added ${payload.name}.`);
        setName("");
        setPhone("");
        setRole("volunteer");
        setSelectedLead("");
        load();
      } catch (error) {
        setErr(formatApiError(error));
      } finally {
        setBusy(false);
      }
    },
    [name, role, phone, selectedLead, isAdmin, load]
  );

  const run = useCallback(async (confirmText, request, doneMsg) => {
    if (confirmText && !window.confirm(confirmText)) return null;
    setErr("");
    setMsg("");
    try {
      const response = await request();
      setMsg(doneMsg);
      load();
      return response;
    } catch (error) {
      setErr(formatApiError(error));
      return null;
    }
  }, [load]);

  const resetPin = async (s) => {
    const reset = await run(
      `Reset ${s.name}'s PIN? Their current PIN and open sessions stop working.`,
      () => api.post(`/staff/${s.id}/reset-pin`),
      `Reset ${s.name}'s PIN.`,
    );
    if (reset) setOneTimePin({ name: s.name, pin: reset.data.temporary_pin });
  };
  const unlock = (s) => run(`Unlock ${s.name}? Their PIN stays the same.`, () => api.post(`/staff/${s.id}/unlock`), `Unlocked ${s.name}.`);
  const toggleStatus = (s) => (s.disabled_at
    ? run(null, () => api.patch(`/staff/${s.id}/enable`), `Enabled account for ${s.name}.`)
    : run(`Disable ${s.name}'s account? They are signed out and cannot sign in.`, () => api.patch(`/staff/${s.id}/disable`), `Disabled account for ${s.name}.`));
  const reassign = (s, teamLeadId) => {
    if (assigning.current) return null;
    assigning.current = true;
    return run(
      null, () => api.patch(`/staff/${s.id}/team-lead`, { team_lead_id: teamLeadId || null }), `Updated team assignment for ${s.name}.`,
    ).finally(() => { assigning.current = false; });
  };
  const deleteStaff = (s) => run(
    `Delete ${s.name}'s account? They will lose access; past activity stays in reports.`,
    () => api.delete(`/staff/${s.id}`),
    `Deleted account for ${s.name}.`,
  );

  return (
    <Layout title={isTeamLead ? "My Team" : "Staff & Team Management"}>
      <div className="space-y-6">
        {err && <Alert tone="rose">{err}</Alert>}
        {msg && <Alert tone="emerald">{msg}</Alert>}
        {oneTimePin && <OneTimePin {...oneTimePin} onDone={() => setOneTimePin(null)} />}

        <Card>
          <h3 className="font-display font-bold text-lg text-slate-900 mb-1">
            {isTeamLead ? "Add Volunteer to Your Team" : "Add Staff Member"}
          </h3>
          <p className="text-xs text-slate-500 mb-4">
            Each new account gets a one-time PIN, shown once. The user chooses their own PIN at first sign-in.
          </p>

          <form onSubmit={onAdd} className="space-y-4" data-testid="add-staff-form">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="Full Name" required>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Ramesh Kumar"
                  required
                  data-testid="staff-name-input"
                />
              </Field>
              <Field label="Mobile Phone (Optional)">
                <Input
                  value={phone}
                  type="tel"
                  inputMode="tel"
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="10-digit mobile number"
                  data-testid="staff-phone-input"
                />
              </Field>
            </div>

            {isAdmin && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <Field label="Role">
                  <Select
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    data-testid="staff-role-select"
                  >
                    {ALL_ROLES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </Select>
                </Field>

                {role === "volunteer" && (
                  <Field label="Assign to Team Lead">
                    <Select
                      value={selectedLead}
                      onChange={(e) => setSelectedLead(e.target.value)}
                      data-testid="staff-teamlead-select"
                    >
                      <option value="">No Team Lead (Direct)</option>
                      {teamLeads.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                )}

                {role === "clinical_desk_operator" && <p className="text-sm text-slate-700 self-center">Operators choose their own line at the clinical desk.</p>}
              </div>
            )}

            <Button
              type="submit"
              size="md"
              disabled={busy}
              data-testid="add-staff-button"
            >
              {busy ? "Adding…" : isTeamLead ? "Add Volunteer" : "Add Staff"}
            </Button>
          </form>
        </Card>

        <Card>
          <h3 className="font-display font-bold text-lg text-slate-900 mb-3">
            {isTeamLead ? "Volunteers in Your Team" : "All Staff"}
          </h3>
          <Field label="Find by name">
            <Input value={nameFilter} onChange={(e) => setNameFilter(e.target.value)} data-testid="staff-name-filter" />
          </Field>
          {staff.length === 0 ? (
            <p className="text-sm text-slate-500">No staff members found.</p>
          ) : (
            <div className="divide-y divide-slate-100" data-testid="staff-list">
              {staff.filter((s) => s.name.toLocaleLowerCase().includes(nameFilter.trim().toLocaleLowerCase())).map((s) => (
                <div
                  key={s.id}
                  className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  data-testid={`staff-row-${s.id}`}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="min-w-0 break-words font-semibold text-slate-900">{s.name}</span>
                      <Badge tone={s.role === "admin" ? "emerald" : "slate"}>
                        {ALL_ROLES.find((r) => r.value === s.role)?.label || s.role}
                      </Badge>
                      {s.disabled_at && <Badge tone="rose">Disabled</Badge>}
                      {s.must_change_pin && <Badge tone="amber">One-time PIN</Badge>}
                      {s.locked_until && <Badge tone="rose" data-testid={`locked-${s.id}`}>Locked until {displayTimestamp(s.locked_until)}</Badge>}
                    </div>
                    {s.lockouts_24h > 1 && (
                      <p className="text-xs text-rose-700 mt-0.5" data-testid={`lockouts-${s.id}`}>
                        Locked out {s.lockouts_24h} times in 24 h, from {s.lockout_sources_24h} {s.lockout_sources_24h === 1 ? "network" : "networks"}
                      </p>
                    )}
                    {s.phone && (
                      <p className="text-xs text-slate-500 mt-0.5">{s.phone}</p>
                    )}
                    {isAdmin && s.role === "volunteer" && (
                      <label className="block text-xs text-slate-700 mt-2" htmlFor={`reassign-team-${s.id}`}>
                        Team Lead
                        <Select
                          id={`reassign-team-${s.id}`}
                          value={s.team_lead_id || ""}
                          onChange={(e) => reassign(s, e.target.value)}
                          data-testid={`reassign-team-${s.id}`}
                        >
                          <option value="">No Team Lead (Direct)</option>
                          {teamLeads.map((lead) => <option key={lead.id} value={lead.id}>{lead.name}</option>)}
                        </Select>
                      </label>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`reset-pin-${s.id}`}
                      onClick={() => resetPin(s)}
                    >
                      Reset PIN
                    </Button>
                    {s.locked_until && (
                      <Button size="sm" variant="outline" data-testid={`unlock-${s.id}`} onClick={() => unlock(s)}>
                        Unlock
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant={s.disabled_at ? "primary" : "ghost"}
                      data-testid={`toggle-status-${s.id}`}
                      onClick={() => toggleStatus(s)}
                    >
                      {s.disabled_at ? "Enable" : "Disable"}
                    </Button>
                    {s.id !== user?.id && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="min-h-11 min-w-11"
                        data-testid={`delete-staff-${s.id}`}
                        onClick={() => deleteStaff(s)}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </Layout>
  );
}
