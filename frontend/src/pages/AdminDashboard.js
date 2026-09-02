import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import Layout from "../components/Layout";
import {
  Button, Card, Input, Field, Alert, Modal, Stat, Badge, ErrorCard,
} from "../components/ui";
import {
  Tent, Users, CalendarDays, Trophy, Download, Scissors, Glasses, Power, Trash2,
  Plus, PrinterCheck, ClipboardList, Stethoscope, FileText,
} from "lucide-react";
import TemplateEditor from "../components/TemplateEditor";

const TABS = [
  { id: "overview", label: "Overview", icon: ClipboardList },
  { id: "camps", label: "Camps & Days", icon: Tent },
  { id: "staff", label: "Staff", icon: Users },
  { id: "template", label: "Rx Template", icon: FileText },
  { id: "ot", label: "OT & Specs", icon: Scissors },
  { id: "board", label: "Leaderboards", icon: Trophy },
  { id: "exports", label: "Exports", icon: Download },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("overview");
  return (
    <Layout title="Admin">
      <div className="flex flex-wrap gap-2 mb-5" data-testid="admin-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`shrink-0 min-h-[44px] px-4 rounded-xl text-sm font-semibold inline-flex items-center gap-2 transition-colors ${tab === t.id ? "bg-slate-900 text-white" : "bg-white text-slate-600 border border-slate-200 hover:border-emerald-400"}`}
              data-testid={`admin-tab-${t.id}`}>
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "camps" && <Camps />}
      {tab === "staff" && <Staff />}
      {tab === "template" && <TemplateEditor />}
      {tab === "ot" && <div className="space-y-5"><OtSchedule /><SpecsCollectionDays /></div>}
      {tab === "board" && <Leaderboards />}
      {tab === "exports" && <Exports />}
    </Layout>
  );
}

function Overview() {
  const navigate = useNavigate();
  const [kpi, setKpi] = useState(null);
  const [camp, setCamp] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    Promise.all([api.get("/kpis"), api.get("/camps/active")])
      .then(([k, a]) => { setKpi(k.data); setCamp(a.data.camp); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);
  if (err) return <ErrorCard message={err} onRetry={load} />;

  return (
    <div className="space-y-5">
      <Card>
        <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Active Camp</p>
        {camp ? (
          <p className="font-display font-extrabold text-2xl text-slate-900 mt-1">{camp.name} <span className="text-slate-400 font-normal text-base">· {camp.venue}</span></p>
        ) : (
          <p className="text-slate-400 mt-1">No active camp. Create & activate one under “Camps & Days”.</p>
        )}
      </Card>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Registered" value={kpi?.registered ?? 0} testid="kpi-registered-count" />
        <Stat label="Seen" value={kpi?.seen ?? 0} tone="emerald" testid="kpi-seen-count" />
        <Stat label="Pending" value={kpi?.pending ?? 0} tone="amber" testid="kpi-pending-count" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Button size="lg" variant="outline" onClick={() => navigate("/desk")} data-testid="goto-desk-button"><Stethoscope className="w-5 h-5" /> Open Registration Desk</Button>
        <Button size="lg" variant="outline" onClick={() => navigate("/clinical")} data-testid="goto-clinical-button"><ClipboardList className="w-5 h-5" /> Open Clinical Desk</Button>
      </div>
    </div>
  );
}

function Camps() {
  const [camps, setCamps] = useState([]);
  const [err, setErr] = useState("");
  const [showCamp, setShowCamp] = useState(false);
  const [form, setForm] = useState({ name: "", venue: "", camp_date: "" });
  const [expand, setExpand] = useState(null);

  const load = useCallback(() => {
    api.get("/camps").then((r) => setCamps(r.data.camps)).catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const createCamp = useCallback(async () => {
    try {
      await api.post("/camps", form);
      setShowCamp(false);
      setForm({ name: "", venue: "", camp_date: "" });
      load();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, [form, load]);

  const activate = useCallback(async (id) => {
    try { await api.post(`/camps/${id}/activate`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const deactivate = useCallback(async (id) => {
    try { await api.post(`/camps/${id}/deactivate`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const del = useCallback(async (id) => {
    try { await api.delete(`/camps/${id}`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Button onClick={() => setShowCamp(true)} data-testid="create-camp-button"><Plus className="w-4 h-4" /> New Camp</Button>
      {camps.map((c) => (
        <Card key={c.id} data-testid={`camp-card-${c.id}`}>
          <div className="flex flex-wrap items-center gap-3">
            <Tent className={`w-5 h-5 ${c.is_active ? "text-emerald-500" : "text-slate-300"}`} />
            <div className="flex-1">
              <p className="font-display font-bold text-slate-900">{c.name} {c.is_active && <Badge tone="emerald">Active</Badge>}</p>
              <p className="text-xs text-slate-400">{c.venue} · {c.camp_date}</p>
            </div>
            {c.is_active ? (
              <Button size="sm" variant="ghost" onClick={() => deactivate(c.id)} data-testid={`deactivate-camp-${c.id}`}><Power className="w-4 h-4" /> Deactivate</Button>
            ) : (
              <Button size="sm" onClick={() => activate(c.id)} data-testid={`activate-camp-${c.id}`}><Power className="w-4 h-4" /> Activate</Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setExpand(expand === c.id ? null : c.id)} data-testid={`manage-days-${c.id}`}><CalendarDays className="w-4 h-4" /> Days</Button>
            <Button size="sm" variant="ghost" onClick={() => del(c.id)} data-testid={`delete-camp-${c.id}`}><Trash2 className="w-4 h-4 text-rose-500" /></Button>
          </div>
          {expand === c.id && <CampDays campId={c.id} />}
        </Card>
      ))}

      <Modal open={showCamp} onClose={() => setShowCamp(false)} title="New Camp">
        <div className="space-y-3">
          <Field label="Camp name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="camp-name-input" /></Field>
          <Field label="Venue" required><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="camp-venue-input" /></Field>
          <Field label="Camp date" required><Input type="date" value={form.camp_date} onChange={(e) => setForm({ ...form, camp_date: e.target.value })} data-testid="camp-date-input" /></Field>
          <Button className="w-full" onClick={createCamp} disabled={!form.name || !form.venue || !form.camp_date} data-testid="camp-create-submit">Create</Button>
        </div>
      </Modal>
    </div>
  );
}

function CampDays({ campId }) {
  const [days, setDays] = useState([]);
  const [date, setDate] = useState("");
  const [seat, setSeat] = useState(50);
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    api.get(`/camps/${campId}/days`).then((r) => setDays(r.data.days)).catch((e) => setErr(formatApiError(e)));
  }, [campId]);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async () => {
    try {
      await api.post("/camps/days", { camp_id: campId, day_date: date, seat_limit: Number(seat) });
      setDate("");
      setSeat(50);
      load();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, [campId, date, seat, load]);

  const togglePrint = useCallback(async (id, val) => {
    try { await api.patch(`/camps/days/${id}/print-window`, { printing_open: val }); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const del = useCallback(async (id) => {
    try { await api.delete(`/camps/days/${id}`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  return (
    <div className="mt-4 pt-4 border-t border-slate-100 space-y-2" data-testid={`camp-days-${campId}`}>
      {err && <Alert>{err}</Alert>}
      {days.map((d) => (
        <div key={d.id} className="flex flex-wrap items-center gap-2 p-2.5 rounded-xl bg-slate-50" data-testid={`day-row-${d.id}`}>
          <CalendarDays className="w-4 h-4 text-slate-400" />
          <span className="font-medium text-slate-800 text-sm">{d.day_date}</span>
          {d.is_today && <Badge tone="emerald">Today</Badge>}
          <span className="text-xs text-slate-400">seats: {d.seat_limit}</span>
          <div className="ml-auto flex items-center gap-2">
            <Badge tone={d.printing_open ? "emerald" : "slate"}>{d.printing_open ? "Print open" : "Print closed"}</Badge>
            <Button size="sm" variant={d.printing_open ? "outline" : "primary"} onClick={() => togglePrint(d.id, !d.printing_open)} data-testid={`toggle-print-window-${d.id}`}>
              <PrinterCheck className="w-4 h-4" /> {d.printing_open ? "Close" : "Open"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => del(d.id)} data-testid={`delete-day-${d.id}`}><Trash2 className="w-4 h-4 text-rose-500" /></Button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2 items-end pt-2">
        <div><label className="text-[10px] font-mono text-slate-400 uppercase">Date</label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid="new-day-date" /></div>
        <div><label className="text-[10px] font-mono text-slate-400 uppercase">Seat limit</label><Input type="number" value={seat} onChange={(e) => setSeat(e.target.value)} className="w-28" data-testid="new-day-seat" /></div>
        <Button size="sm" onClick={add} disabled={!date} data-testid="add-day-button"><Plus className="w-4 h-4" /> Add day</Button>
      </div>
    </div>
  );
}

function Staff() {
  const [staff, setStaff] = useState([]);
  const [leads, setLeads] = useState([]);
  const [err, setErr] = useState("");
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "volunteer", phone: "", team_lead_id: "" });

  const load = useCallback(() => {
    Promise.all([api.get("/staff"), api.get("/staff/team-leads")])
      .then(([s, l]) => { setStaff(s.data.staff); setLeads(l.data.team_leads); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = useCallback(async () => {
    setErr("");
    try {
      await api.post("/staff", { ...form, team_lead_id: form.role === "volunteer" ? (form.team_lead_id || null) : null });
      setShow(false);
      setForm({ email: "", password: "", name: "", role: "volunteer", phone: "", team_lead_id: "" });
      load();
    } catch (e) { setErr(formatApiError(e)); }
  }, [form, load]);
  const disable = useCallback(async (id) => { try { await api.patch(`/staff/${id}/disable`); load(); } catch (e) { setErr(formatApiError(e)); } }, [load]);
  const enable = useCallback(async (id) => { try { await api.patch(`/staff/${id}/enable`); load(); } catch (e) { setErr(formatApiError(e)); } }, [load]);

  const roleLabel = { admin: "Admin", team_lead: "Team Lead", volunteer: "Volunteer", clinical_desk_operator: "Clinical Desk" };

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Button onClick={() => setShow(true)} data-testid="create-staff-button"><Plus className="w-4 h-4" /> Add Staff</Button>
      <Card>
        <div className="space-y-2" data-testid="staff-list">
          {staff.map((s) => (
            <div key={s.id} className="flex items-center gap-3 p-3 rounded-xl border border-slate-200" data-testid={`staff-row-${s.id}`}>
              <div className="flex-1">
                <p className="font-semibold text-slate-900">{s.name} {s.disabled_at && <Badge tone="rose">Disabled</Badge>}</p>
                <p className="text-xs text-slate-400">{s.email}</p>
              </div>
              <Badge tone="slate">{roleLabel[s.role]}</Badge>
              {s.role !== "admin" && (s.disabled_at
                ? <Button size="sm" variant="outline" onClick={() => enable(s.id)} data-testid={`enable-staff-${s.id}`}>Enable</Button>
                : <Button size="sm" variant="ghost" onClick={() => disable(s.id)} data-testid={`disable-staff-${s.id}`}><Power className="w-4 h-4 text-rose-500" /></Button>)}
            </div>
          ))}
        </div>
      </Card>

      <Modal open={show} onClose={() => setShow(false)} title="Add Staff">
        <div className="space-y-3">
          <Field label="Name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="staff-name-input" /></Field>
          <Field label="Email" required><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="staff-email-input" /></Field>
          <Field label="Password" required hint="≥12 chars, upper/lower/digit/symbol"><Input type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="staff-password-input" /></Field>
          <Field label="Role" required>
            <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="staff-role-select">
              <option value="volunteer">Volunteer</option>
              <option value="team_lead">Team Lead</option>
              <option value="clinical_desk_operator">Clinical Desk Operator</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
          {form.role === "volunteer" && (
            <Field label="Team Lead (optional)">
              <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={form.team_lead_id} onChange={(e) => setForm({ ...form, team_lead_id: e.target.value })} data-testid="staff-teamlead-select">
                <option value="">Unassigned</option>
                {leads.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </Field>
          )}
          <Field label="Phone"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="staff-phone-input" /></Field>
          {err && <Alert data-testid="staff-modal-error">{err}</Alert>}
          <Button className="w-full" onClick={create} disabled={!form.name || !form.email || !form.password} data-testid="staff-create-submit">Create Staff</Button>
        </div>
      </Modal>
    </div>
  );
}

function OtSchedule() {
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ day_date: "", venue: "", seat_limit: 10 });

  const load = useCallback(() => {
    Promise.all([api.get("/clinical/ot-days"), api.get("/camps/active")])
      .then(([o, a]) => { setDays(o.data.ot_days); setCamp(a.data.camp); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async () => {
    setErr("");
    if (!camp) { setErr("Activate a camp first."); return; }
    try { await api.post("/clinical/ot-days", { camp_id: camp.id, ...form, seat_limit: Number(form.seat_limit) }); setForm({ day_date: "", venue: "", seat_limit: 10 }); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [camp, form, load]);

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-3">OT Schedule Days</h3>
        <div className="space-y-2" data-testid="ot-days-list">
          {days.length === 0 && <p className="text-slate-400 text-sm">No OT days yet.</p>}
          {days.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50" data-testid={`ot-day-${d.id}`}>
              <Scissors className="w-4 h-4 text-emerald-600" />
              <span className="font-medium text-slate-800 text-sm">{d.day_date}</span>
              <span className="text-xs text-slate-400">{d.venue}</span>
              <Badge tone={d.seats_free > 0 ? "emerald" : "rose"} className="ml-auto">{d.seats_taken}/{d.seat_limit} seats</Badge>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 items-end pt-4 mt-3 border-t border-slate-100">
          <div><label className="text-[10px] font-mono text-slate-400 uppercase">Date</label><Input type="date" value={form.day_date} onChange={(e) => setForm({ ...form, day_date: e.target.value })} data-testid="ot-date-input" /></div>
          <div><label className="text-[10px] font-mono text-slate-400 uppercase">Venue</label><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="ot-venue-input" /></div>
          <div><label className="text-[10px] font-mono text-slate-400 uppercase">Seats</label><Input type="number" value={form.seat_limit} onChange={(e) => setForm({ ...form, seat_limit: e.target.value })} className="w-24" data-testid="ot-seat-input" /></div>
          <Button size="sm" onClick={add} disabled={!form.day_date || !form.venue} data-testid="add-ot-day-button"><Plus className="w-4 h-4" /> Add</Button>
        </div>
      </Card>
    </div>
  );
}

function SpecsCollectionDays() {
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ day_date: "", venue: "", seat_limit: 10 });

  const load = useCallback(() => {
    Promise.all([api.get("/clinical/specs-days"), api.get("/camps/active")])
      .then(([o, a]) => { setDays(o.data.specs_days); setCamp(a.data.camp); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async () => {
    setErr("");
    if (!camp) { setErr("Activate a camp first."); return; }
    try { await api.post("/clinical/specs-days", { camp_id: camp.id, ...form, seat_limit: Number(form.seat_limit) }); setForm({ day_date: "", venue: "", seat_limit: 10 }); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [camp, form, load]);

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-3">Specs collection days</h3>
        <div className="space-y-2" data-testid="specs-days-list">
          {days.length === 0 && <p className="text-slate-400 text-sm">No Specs collection days yet.</p>}
          {days.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50" data-testid={`specs-day-${d.id}`}>
              <Glasses className="w-4 h-4 text-emerald-600" />
              <span className="font-medium text-slate-800 text-sm">{d.day_date}</span>
              <span className="text-xs text-slate-400">{d.venue}</span>
              <Badge tone={d.seats_free > 0 ? "emerald" : "rose"} className="ml-auto">{d.seats_taken}/{d.seat_limit} seats</Badge>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 items-end pt-4 mt-3 border-t border-slate-100">
          <div><label className="text-[10px] font-mono text-slate-400 uppercase">Date</label><Input type="date" value={form.day_date} onChange={(e) => setForm({ ...form, day_date: e.target.value })} data-testid="specs-date-input" /></div>
          <div><label className="text-[10px] font-mono text-slate-400 uppercase">Venue</label><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="specs-venue-input" /></div>
          <div><label className="text-[10px] font-mono text-slate-400 uppercase">Seats</label><Input type="number" value={form.seat_limit} onChange={(e) => setForm({ ...form, seat_limit: e.target.value })} className="w-24" data-testid="specs-seat-input" /></div>
          <Button size="sm" onClick={add} disabled={!form.day_date || !form.venue} data-testid="add-specs-day-button"><Plus className="w-4 h-4" /> Add</Button>
        </div>
      </Card>
    </div>
  );
}

function Board({ title, rows, testid }) {
  return (
    <Card>
      <h3 className="font-display font-bold text-slate-900 mb-3 flex items-center gap-2">
        <Trophy className="w-5 h-5 text-amber-500" /> {title}
      </h3>
      <div className="space-y-2" data-testid={testid}>
        {rows.length === 0 && <p className="text-slate-400 text-sm">No points yet.</p>}
        {rows.map((r, i) => (
          <div key={`${r.name}-${i}`} className="flex items-center gap-3 p-2.5 rounded-xl bg-slate-50">
            <span className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold ${i === 0 ? "bg-amber-400 text-white" : "bg-slate-200 text-slate-600"}`}>
              {i + 1}
            </span>
            <span className="flex-1 font-medium text-slate-800">{r.name}</span>
            <Badge tone="emerald">{r.points} pts</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Leaderboards() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    api.get("/leaderboard").then((r) => setData(r.data)).catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);
  if (err) return <ErrorCard message={err} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <Board title="Volunteers" rows={data.volunteers} testid="leaderboard-volunteers-table" />
      <Board title="Team Leads" rows={data.team_leads} testid="leaderboard-team-leads-table" />
    </div>
  );
}

function Exports() {
  const [msg, setMsg] = useState("");
  const download = useCallback(async (path, filename) => {
    setMsg("");
    try {
      const res = await api.get(path, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 0);
      setMsg(`Downloaded ${filename}`);
    } catch (e) { setMsg(formatApiError(e)); }
  }, []);
  return (
    <div className="space-y-4">
      {msg && <Alert tone="emerald">{msg}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-1">Camp Records Export</h3>
        <p className="text-sm text-slate-500 mb-3">
          One row per patient: identity, registration, arrival and seen times, clinical values,
          each eye's power, all four Fulfilment lines and their assigned days.
        </p>
        <Button variant="outline" onClick={() => download("/exports/camp-records", "camp_records.csv")} data-testid="export-camp-records-button"><Download className="w-4 h-4" /> Download CSV</Button>
      </Card>
    </div>
  );
}
