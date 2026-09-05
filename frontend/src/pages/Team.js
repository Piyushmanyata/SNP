import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import api, { formatApiError } from "../lib/api";
import { Alert, Badge, Button, Card, Field, Input, Select } from "../components/ui";

const ALL_ROLES = [
  { value: "volunteer", label: "Volunteer" },
  { value: "clinical_desk_operator", label: "Clinical Desk Operator" },
  { value: "team_lead", label: "Team Lead" },
  { value: "admin", label: "Admin" },
];

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
        await api.post("/staff", payload);
        setMsg(`Added ${name.trim()} successfully with default PIN 1234.`);
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

  const resetPin = useCallback(
    async (id, staffName) => {
      setErr("");
      setMsg("");
      try {
        await api.post(`/staff/${id}/reset-pin`);
        setMsg(`PIN for ${staffName} has been reset to 1234.`);
      } catch (error) {
        setErr(formatApiError(error));
      }
    },
    []
  );

  const toggleStatus = useCallback(
    async (s) => {
      setErr("");
      setMsg("");
      try {
        if (s.disabled_at) {
          await api.patch(`/staff/${s.id}/enable`);
          setMsg(`Enabled account for ${s.name}.`);
        } else {
          await api.patch(`/staff/${s.id}/disable`);
          setMsg(`Disabled account for ${s.name}.`);
        }
        load();
      } catch (error) {
        setErr(formatApiError(error));
      }
    },
    [load]
  );

  return (
    <Layout title={isTeamLead ? "My Team" : "Staff & Team Management"}>
      <div className="space-y-6">
        {err && <Alert tone="rose">{err}</Alert>}
        {msg && <Alert tone="emerald">{msg}</Alert>}

        <Card>
          <h3 className="font-display font-bold text-lg text-slate-900 mb-1">
            {isTeamLead ? "Add Volunteer to Your Team" : "Add Staff Member"}
          </h3>
          <p className="text-xs text-slate-500 mb-4">
            New accounts are provisioned with default PIN <strong>1234</strong>. The user will be required to change it upon first login.
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
          {staff.length === 0 ? (
            <p className="text-sm text-slate-500">No staff members found.</p>
          ) : (
            <div className="divide-y divide-slate-100" data-testid="staff-list">
              {staff.map((s) => (
                <div
                  key={s.id}
                  className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  data-testid={`staff-row-${s.id}`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{s.name}</span>
                      <Badge tone={s.role === "admin" ? "emerald" : "slate"}>
                        {ALL_ROLES.find((r) => r.value === s.role)?.label || s.role}
                      </Badge>
                      {s.disabled_at && <Badge tone="rose">Disabled</Badge>}
                      {s.must_change_pin && <Badge tone="amber">Default PIN</Badge>}
                    </div>
                    {s.phone && (
                      <p className="text-xs text-slate-500 mt-0.5">{s.phone}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`reset-pin-${s.id}`}
                      onClick={() => resetPin(s.id, s.name)}
                    >
                      Reset PIN (1234)
                    </Button>
                    <Button
                      size="sm"
                      variant={s.disabled_at ? "primary" : "ghost"}
                      data-testid={`toggle-status-${s.id}`}
                      onClick={() => toggleStatus(s)}
                    >
                      {s.disabled_at ? "Enable" : "Disable"}
                    </Button>
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
