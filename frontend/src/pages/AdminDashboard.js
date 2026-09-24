import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import Layout from "../components/Layout";
import {
  Button, Card, Input, Field, Alert, Modal, Stat, Badge, ErrorCard,
} from "../components/ui";
import {
  Tent, Users, CalendarDays, Trophy, Download, Scissors, Glasses, Power, Trash2,
  Plus, PrinterCheck, ClipboardList, Stethoscope, FileText, BarChart3, Pill, Pencil, MessageSquare, RefreshCw,
} from "lucide-react";
import { formatPower } from "../components/clinical";
import TemplateEditor from "../components/TemplateEditor";
import { displayDate, displayDateRange, displayTimeRange, displayTimestamp } from "../lib/dates";
import { SMS_LABELS, SMS_VENUE_MAX, smsVenueFor } from "../lib/sms";

const CAMP_VENUE = "Hansa Garden, Rohini Road in Baghmara, Jasidih, Deoghar - 814142";
const NEW_CAMP = { name: "SNP नेत्र शिविर", venue: CAMP_VENUE, venue_sms: "Hansa Garden, Jasidih, Deoghar", camp_date: "", camp_number: "" };
const HOSPITAL_VENUE = "Vimla Ramkrishna Bajaj Eye Hospital, Near Canara Bank, Bilasi Mod, Deoghar 814112 (Jharkhand)";
const HOSPITAL_SMS_VENUE = "बजाज हॉस्पिटल, देवघर";
const NEW_SPECS_DAY = { day_date: "", end_date: "", venue: "", venue_sms: "" };

const TABS = [
  { id: "overview", label: "Overview", icon: ClipboardList },
  { id: "camps", label: "Camps & Days", icon: Tent },
  { id: "template", label: "Rx Template", icon: FileText },
  { id: "ot", label: "OT & Specs", icon: Scissors },
  { id: "sms", label: "SMS", icon: MessageSquare },
  { id: "supplies", label: "Camp supplies", icon: Pill },
  { id: "board", label: "Leaderboards", icon: Trophy },
  { id: "exports", label: "Exports", icon: Download },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState("overview");
  return (
    <Layout title="Admin">
      <div className="flex gap-2 mb-5 -mx-4 px-4 overflow-x-auto [scrollbar-width:none] sm:mx-0 sm:px-0 sm:flex-wrap sm:overflow-visible" data-testid="admin-tabs">
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
      {tab === "template" && <TemplateEditor />}
      {tab === "ot" && <div className="space-y-5"><OtSchedule /><SpecsCollectionDays /></div>}
      {tab === "sms" && <SmsHealth />}
      {tab === "supplies" && <div className="space-y-5"><Medicines /><FixedPowers /></div>}
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
    setErr("");
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
          <>
            <p className="font-display font-extrabold text-2xl text-slate-900 mt-1">{camp.name}</p>
            <p className="text-slate-600 text-sm mt-1 break-words">{camp.venue}</p>
          </>
        ) : (
          <p className="text-slate-600 mt-1">No active camp. Create & activate one under “Camps & Days”.</p>
        )}
      </Card>
      <SystemCard />
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Registered" value={kpi?.registered ?? 0} testid="kpi-registered-count" />
        <Stat label="Seen" value={kpi?.seen ?? 0} tone="emerald" testid="kpi-seen-count" />
        <Stat label="Pending" value={kpi?.pending ?? 0} tone="amber" testid="kpi-pending-count" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Button size="lg" variant="outline" onClick={() => navigate("/desk")} data-testid="goto-desk-button"><Stethoscope className="w-5 h-5" /> Open Registration Desk</Button>
        <Button size="lg" variant="outline" onClick={() => navigate("/clinical")} data-testid="goto-clinical-button"><ClipboardList className="w-5 h-5" /> Open Clinical Desk</Button>
        <Button size="lg" variant="outline" onClick={() => navigate("/team")} data-testid="goto-team-button"><Users className="w-5 h-5" /> Team management</Button>
        <Button size="lg" variant="outline" onClick={() => navigate("/analytics")} data-testid="goto-analytics-button"><BarChart3 className="w-5 h-5" /> Analytics</Button>
      </div>
    </div>
  );
}

const SYSTEM_LEVELS = {
  green: { tone: "emerald", label: "All good", card: "border-emerald-300", text: "text-slate-700" },
  amber: { tone: "amber", label: "Needs attention", card: "border-amber-300 bg-amber-50/40", text: "text-amber-800" },
  red: { tone: "rose", label: "Failing", card: "border-rose-300 bg-rose-50/40", text: "text-rose-700" },
};

function gigabytes(bytes) {
  return `${Math.round(bytes / 1e9)} GB`;
}

function SystemCard() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    setErr("");
    api.get("/admin/system").then((r) => setData(r.data)).catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);
  if (err) return <ErrorCard message={err} onRetry={load} />;
  if (!data) return null;

  const level = SYSTEM_LEVELS[data.status];
  const backup = data.backup || {};
  const errorIsLatest = backup.last_error && (!backup.last_success_at || backup.last_error_at >= backup.last_success_at);
  const backupText = SYSTEM_LEVELS[data.levels.backup].text;
  return (
    <Card className={level.card} data-testid="system-card" data-status={data.status}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-mono uppercase tracking-widest text-slate-500">System</p>
        <Badge tone={level.tone} data-testid="system-status">{level.label}</Badge>
      </div>
      <ul className="mt-3 space-y-1 text-sm">
        <li className={backupText} data-testid="system-backup">
          Backup: {backup.last_success_at ? `last ${displayTimestamp(backup.last_success_at)}` : "No backup yet"}
        </li>
        <li className={backupText} data-testid="system-remote">
          Off-site copy: {!backup.remote_configured ? "Not set up"
            : backup.remote_last_success_at ? `last ${displayTimestamp(backup.remote_last_success_at)}` : "Not copied yet"}
        </li>
        <li className={SYSTEM_LEVELS[data.levels.disk].text} data-testid="system-disk">
          Backup disk: {data.disk === "unknown" ? "Unknown" : `${gigabytes(data.disk.free_bytes)} free of ${gigabytes(data.disk.total_bytes)}`}
        </li>
        {errorIsLatest && (
          <li className="text-rose-700" data-testid="system-error">
            Last error {displayTimestamp(backup.last_error_at)}: {backup.last_error}
          </li>
        )}
      </ul>
    </Card>
  );
}

function Camps() {
  const [camps, setCamps] = useState([]);
  const [err, setErr] = useState("");
  const [showCamp, setShowCamp] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(NEW_CAMP);
  const [expand, setExpand] = useState(null);
  const [busy, setBusy] = useState(false);
  const campNumber = Number(form.camp_number);

  const load = useCallback(() => {
    api.get("/camps").then((r) => setCamps(r.data.camps)).catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCamp = (c) => {
    setEditing(c ? c.id : null);
    setForm(c ? { name: c.name, venue: c.venue, venue_sms: c.venue_sms || "", camp_date: c.camp_date, camp_number: c.camp_number ?? "" } : NEW_CAMP);
    setShowCamp(true);
  };

  const saveCamp = useCallback(async () => {
    setErr("");
    setBusy(true);
    try {
      const body = { ...form, camp_number: Number(form.camp_number) };
      if (editing) await api.patch(`/camps/${editing}`, body);
      else await api.post("/camps", body);
      setShowCamp(false);
      load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }, [editing, form, load]);

  const activate = useCallback(async (id) => {
    setErr("");
    try { await api.post(`/camps/${id}/activate`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const deactivate = useCallback(async (id) => {
    setErr("");
    try { await api.post(`/camps/${id}/deactivate`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const del = useCallback(async (camp) => {
    if (!window.confirm(`Delete ${camp.name} and its days? This cannot be undone.`)) return;
    setErr("");
    try { await api.delete(`/camps/${camp.id}`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const setDoorManual = useCallback(async (enabled) => {
    setErr("");
    try { await api.post("/camps/door-manual", { enabled }); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Button onClick={() => openCamp(null)} data-testid="create-camp-button"><Plus className="w-4 h-4" /> New Camp</Button>
      {camps.map((c) => (
        <Card key={c.id} data-testid={`camp-card-${c.id}`}>
          <div className="flex flex-wrap items-center gap-3">
            <Tent className={`w-5 h-5 ${c.is_active ? "text-emerald-500" : "text-slate-300"}`} />
            <div className="flex-1 min-w-0 basis-56">
              <p className="font-display font-bold text-slate-900">{c.name} {c.is_active && <Badge tone="emerald">Active</Badge>}</p>
              <p className="text-xs text-slate-600">{c.venue} · {displayDate(c.camp_date)}</p>
              {c.camp_number
                ? <Badge className="mt-1" data-testid={`camp-number-${c.id}`}>SMS camp no. {c.camp_number}</Badge>
                : <Badge tone="amber" className="mt-1" data-testid={`camp-number-missing-${c.id}`}>No camp number: SMS are not sent</Badge>}
<SmsVenueBadge venue={c.venue} venueSms={c.venue_sms} testid={`camp-sms-venue-missing-${c.id}`} />
            </div>
            <Button size="sm" variant="outline" onClick={() => openCamp(c)} data-testid={`edit-camp-${c.id}`}><Pencil className="w-4 h-4" /> Edit</Button>
            {c.is_active ? (
              <Button size="sm" variant="ghost" onClick={() => deactivate(c.id)} data-testid={`deactivate-camp-${c.id}`}><Power className="w-4 h-4" /> Deactivate</Button>
            ) : (
              <Button size="sm" onClick={() => activate(c.id)} data-testid={`activate-camp-${c.id}`}><Power className="w-4 h-4" /> Activate</Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setExpand(expand === c.id ? null : c.id)} data-testid={`manage-days-${c.id}`}><CalendarDays className="w-4 h-4" /> Days</Button>
            <Button size="sm" variant="ghost" onClick={() => del(c)} aria-label={`Delete ${c.name}`} data-testid={`delete-camp-${c.id}`}><Trash2 className="w-4 h-4 text-rose-500" /></Button>
          </div>
          {c.is_active && (
            <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center gap-3" data-testid="door-manual-control">
              <div className="flex-1 min-w-[220px]">
                <p className="font-semibold text-slate-900 text-sm">Manual entry at the door</p>
                <p className="text-xs text-slate-500" data-testid="door-manual-state">
                  {c.door_manual_entry
                    ? "Open for today. It closes on its own when the camp day ends."
                    : "Closed. Open it only when the scanners are down."}
                </p>
              </div>
              <Button
                size="sm"
                variant={c.door_manual_entry ? "danger" : "outline"}
                onClick={() => setDoorManual(!c.door_manual_entry)}
                data-testid="door-manual-toggle"
              >
                {c.door_manual_entry ? "Close manual entry" : "Open for today"}
              </Button>
            </div>
          )}
          {expand === c.id && <CampDays campId={c.id} />}
        </Card>
      ))}

      <Modal open={showCamp} onClose={() => setShowCamp(false)} title={editing ? "Edit Camp" : "New Camp"}>
        <div className="space-y-3">
          <Field label="Camp name" required><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="camp-name-input" /></Field>
          <Field label="Venue" required hint="Full address shown on camp records."><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="camp-venue-input" /></Field>
          <SmsVenueField label="Short venue for SMS" venue={form.venue} value={form.venue_sms} onChange={(venue_sms) => setForm({ ...form, venue_sms })} testid="camp-venue-sms-input" />
          <Field label="Camp date" required><Input type="date" value={form.camp_date} onChange={(e) => setForm({ ...form, camp_date: e.target.value })} data-testid="camp-date-input" /></Field>
          <Field label="Camp number" required hint="The SMS reads “Sikar Zilla Welfare Trust के 162वें नेत्र शिविर”."><Input type="number" min="1" step="1" inputMode="numeric" value={form.camp_number} onChange={(e) => setForm({ ...form, camp_number: e.target.value })} data-testid="camp-number-input" /></Field>
          <Button className="w-full" onClick={saveCamp} disabled={busy || !form.name || !form.venue || Boolean(smsVenueFor(form.venue, form.venue_sms).problem) || !form.camp_date || !(Number.isInteger(campNumber) && campNumber > 0)} data-testid="camp-create-submit">{editing ? "Save" : "Create"}</Button>
        </div>
      </Modal>
    </div>
  );
}

function CampDays({ campId }) {
  const [days, setDays] = useState([]);
  const [date, setDate] = useState("");
  const [seat, setSeat] = useState(50);
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.get(`/camps/${campId}/days`).then((r) => setDays(r.data.days)).catch((e) => setErr(formatApiError(e)));
  }, [campId]);
  useEffect(() => { load(); }, [load]);

  const save = useCallback(async () => {
    setErr("");
    setBusy(true);
    try {
      const body = { camp_id: campId, day_date: date, seat_limit: Number(seat) };
      if (editing) await api.patch(`/camps/days/${editing}`, body);
      else await api.post("/camps/days", body);
      setDate("");
      setSeat(50);
      setEditing(null);
      load();
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setBusy(false);
    }
  }, [campId, date, seat, editing, load]);

  const edit = (day) => {
    setEditing(day.id);
    setDate(day.day_date);
    setSeat(day.seat_limit);
    setErr("");
  };

  const cancelEdit = () => {
    setEditing(null);
    setDate("");
    setSeat(50);
  };

  const togglePrint = useCallback(async (id, val) => {
    setErr("");
    try { await api.patch(`/camps/days/${id}/print-window`, { printing_open: val }); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  const del = useCallback(async (day) => {
    if (!window.confirm(`Delete camp day ${displayDate(day.day_date)}? This cannot be undone.`)) return;
    setErr("");
    try { await api.delete(`/camps/days/${day.id}`); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [load]);

  return (
    <div className="mt-4 pt-4 border-t border-slate-100 space-y-2" data-testid={`camp-days-${campId}`}>
      {err && <Alert>{err}</Alert>}
      {days.map((d) => (
        <div key={d.id} className="flex flex-wrap items-center gap-2 p-2.5 rounded-xl bg-slate-50" data-testid={`day-row-${d.id}`}>
          <CalendarDays className="w-4 h-4 text-slate-400" />
          <span className="font-medium text-slate-800 text-sm">{displayDate(d.day_date)}</span>
          {d.is_today && <Badge tone="emerald">Today</Badge>}
          <span className="text-xs text-slate-600">{d.booked ?? 0} booked / {d.seat_limit} seats</span>
          {d.over_capacity && <Badge tone="rose">Over capacity</Badge>}
          <div className="ml-auto flex items-center gap-2">
            <Badge tone={d.printing_open ? "emerald" : "slate"}>{d.printing_open ? "Print open" : "Print closed"}</Badge>
            {d.can_edit !== false && <Button size="sm" variant="outline" onClick={() => edit(d)} data-testid={`edit-day-${d.id}`}><Pencil className="w-4 h-4" /> Edit</Button>}
            <Button size="sm" variant={d.printing_open ? "outline" : "primary"} onClick={() => togglePrint(d.id, !d.printing_open)} data-testid={`toggle-print-window-${d.id}`}>
              <PrinterCheck className="w-4 h-4" /> {d.printing_open ? "Close" : "Open"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => del(d)} aria-label={`Delete camp day ${displayDate(d.day_date)}`} data-testid={`delete-day-${d.id}`}><Trash2 className="w-4 h-4 text-rose-500" /></Button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2 items-end pt-2">
        <Field label="Date"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid="new-day-date" /></Field>
        <Field label="Seat limit"><Input type="number" min="1" value={seat} onChange={(e) => setSeat(e.target.value)} className="w-28" data-testid="new-day-seat" /></Field>
        <Button size="sm" onClick={save} disabled={busy || !date || Number(seat) < 1} data-testid={editing ? "save-day-button" : "add-day-button"}>{editing ? <Pencil className="w-4 h-4" /> : <Plus className="w-4 h-4" />} {editing ? "Save day" : "Add day"}</Button>
        {editing && <Button size="sm" variant="ghost" onClick={cancelEdit}>Cancel</Button>}
      </div>
    </div>
  );
}


function OtSchedule() {
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ day_date: "", venue: HOSPITAL_VENUE, venue_sms: HOSPITAL_SMS_VENUE, seat_limit: 10 });
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.get("/clinical/ot-days"), api.get("/camps/active")])
      .then(([o, a]) => { setDays(o.data.ot_days); setCamp(a.data.camp); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = useCallback(async () => {
    setErr("");
    if (!camp) { setErr("Activate a camp first."); return; }
    setBusy(true);
    try {
      const body = { camp_id: camp.id, ...form, seat_limit: Number(form.seat_limit) };
      if (editing) await api.patch(`/clinical/ot-days/${editing}`, body);
      else await api.post("/clinical/ot-days", body);
      setForm({ day_date: "", venue: HOSPITAL_VENUE, venue_sms: HOSPITAL_SMS_VENUE, seat_limit: 10 });
      setEditing(null);
      load();
    } catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  }, [camp, form, editing, load]);

  const edit = (day) => {
    setEditing(day.id);
    setForm({ day_date: day.day_date, venue: day.venue, venue_sms: day.venue_sms || "", seat_limit: day.seat_limit });
    setErr("");
  };

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-3">OT Schedule Days</h3>
        <p className="text-sm text-slate-600 mb-3">Surgery takes place at the hospital. The camp only schedules the appointment.</p>
        <div className="space-y-2" data-testid="ot-days-list">
          {days.length === 0 && <p className="text-slate-600 text-sm">No OT days yet.</p>}
          {days.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 p-3 rounded-xl bg-slate-50" data-testid={`ot-day-${d.id}`}>
              <Scissors className="w-4 h-4 text-emerald-600" />
              <span className="font-medium text-slate-800 text-sm">{displayDate(d.day_date)}</span>
              <Badge tone={d.seats_free > 0 ? "emerald" : "rose"} className="ml-auto">{d.seats_taken}/{d.seat_limit} seats</Badge>
              <Button size="sm" variant="outline" onClick={() => edit(d)} data-testid={`edit-ot-day-${d.id}`}><Pencil className="w-4 h-4" /> Edit</Button>
              <span className="basis-full text-xs text-slate-600 break-words">{d.venue}</span>
              <SmsVenueBadge venue={d.venue} venueSms={d.venue_sms} testid={`ot-sms-venue-problem-${d.id}`} />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-start pt-4 mt-3 border-t border-slate-100">
          <Field label="Date"><Input type="date" value={form.day_date} onChange={(e) => { const existing = editing ? null : days.find((d) => d.day_date === e.target.value); setForm({ ...form, day_date: e.target.value, venue: existing ? existing.venue : form.venue, venue_sms: existing ? existing.venue_sms || "" : form.venue_sms, seat_limit: existing ? existing.seat_limit : form.seat_limit }); }} data-testid="ot-date-input" /></Field>
          <Field label="Seats"><Input type="number" inputMode="numeric" min="1" value={form.seat_limit} onChange={(e) => setForm({ ...form, seat_limit: e.target.value })} data-testid="ot-seat-input" /></Field>
          <Field label="Hospital"><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="ot-venue-input" /></Field>
          <SmsVenueField label="Short name for SMS" venue={form.venue} value={form.venue_sms} onChange={(venue_sms) => setForm({ ...form, venue_sms })} placeholder={HOSPITAL_SMS_VENUE} testid="ot-venue-sms-input" />
          <Button className="sm:col-span-2" onClick={save} disabled={busy || !form.day_date || !form.venue || Number(form.seat_limit) < 1 || Boolean(smsVenueFor(form.venue, form.venue_sms).problem)} data-testid={editing ? "save-ot-day-button" : "add-ot-day-button"}>{editing ? <Pencil className="w-4 h-4" /> : <Plus className="w-4 h-4" />} {editing ? "Save OT day" : "Add OT day"}</Button>
          {editing && <Button variant="ghost" onClick={() => { setEditing(null); setForm({ day_date: "", venue: HOSPITAL_VENUE, venue_sms: HOSPITAL_SMS_VENUE, seat_limit: 10 }); }}>Cancel</Button>}
        </div>
      </Card>
    </div>
  );
}

function SpecsCollectionDays() {
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState(NEW_SPECS_DAY);

  const load = useCallback(() => {
    Promise.all([api.get("/clinical/specs-days"), api.get("/camps/active")])
      .then(([o, a]) => { setDays(o.data.specs_days); setCamp(a.data.camp); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async () => {
    setErr("");
    if (!camp) { setErr("Activate a camp first."); return; }
    try {
      await api.post("/clinical/specs-days", { camp_id: camp.id, ...form });
      setForm(NEW_SPECS_DAY);
      load();
    }
    catch (e) { setErr(formatApiError(e)); }
  }, [camp, form, load]);

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-3">Specs collection days</h3>
        <div className="space-y-2" data-testid="specs-days-list">
          {days.length === 0 && <p className="text-slate-600 text-sm">No Specs collection days yet.</p>}
          {days.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 p-3 rounded-xl bg-slate-50" data-testid={`specs-day-${d.id}`}>
              <Glasses className="w-4 h-4 text-emerald-600" />
              <span className="font-medium text-slate-800 text-sm">{displayDateRange(d.day_date, d.end_date)}</span>
              <Badge tone={d.window_required ? "amber" : "emerald"} className="ml-auto">
                {d.start_time && d.end_time ? displayTimeRange(d.start_time, d.end_time) : "window required"}
              </Badge>
              <span className="basis-full text-xs text-slate-600 break-words">{d.venue}</span>
              <SmsVenueBadge venue={d.venue} venueSms={d.venue_sms} testid={`specs-sms-venue-problem-${d.id}`} />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-start pt-4 mt-3 border-t border-slate-100">
          <Field label="From"><Input type="date" value={form.day_date} onChange={(e) => setForm({ ...form, day_date: e.target.value })} data-testid="specs-date-input" /></Field>
          <Field label="To"><Input type="date" value={form.end_date} min={form.day_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} data-testid="specs-end-date-input" /></Field>
          <Field label="Venue"><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="specs-venue-input" /></Field>
          <SmsVenueField label="Short venue for SMS" venue={form.venue} value={form.venue_sms} onChange={(venue_sms) => setForm({ ...form, venue_sms })} testid="specs-venue-sms-input" />
          <Button className="sm:col-span-2" onClick={add} disabled={!form.day_date || !form.venue || Boolean(smsVenueFor(form.venue, form.venue_sms).problem)} data-testid="add-specs-day-button"><Plus className="w-4 h-4" /> Add collection days</Button>
        </div>
        <p className="text-xs text-slate-500 mt-2">Leave “To” empty for a single day. Collection hours: 10:00 AM–5:00 PM.</p>
      </Card>
    </div>
  );
}

function SmsVenueField({ label, venue, value, onChange, placeholder, testid }) {
  const sms = smsVenueFor(venue, value);
  const note = sms.problem
    ? `${sms.problem}${value.trim() ? "" : ". Set a short name patients will recognise."}`
    : sms.text ? `SMS will say “${sms.text}” · ${sms.length}/${SMS_VENUE_MAX}` : `Up to ${SMS_VENUE_MAX} characters. Leave empty to use the venue.`;
  return (
    <Field label={label}>
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-invalid={Boolean(sms.problem)} className={sms.problem ? "border-rose-400 focus:ring-rose-500 focus:border-rose-500" : ""} data-testid={testid} />
      <span className={`block text-xs mt-1 break-words ${sms.problem ? "text-rose-700 font-medium" : "text-slate-600"}`} data-testid={`${testid}-note`}>{note}</span>
    </Field>
  );
}

function SmsVenueBadge({ venue, venueSms, testid }) {
  const { problem } = smsVenueFor(venue, venueSms);
  return problem ? <Badge tone="amber" className="mt-1" data-testid={testid}>No SMS until fixed: {problem}</Badge> : null;
}

function todayLine(t) {
  const parts = [
    [t.submitted, "submitted"], [t.delivered, "delivered"], [t.dlt_failed + t.other_failed, "failed"],
    [t.uncertain, "reply lost"], [t.rejected + t.unsent, "not accepted"], [t.paused, "held back"],
  ].filter(([n]) => n > 0);
  return parts.length ? `Today: ${parts.map(([n, label]) => `${n} ${label}`).join(" · ")}` : "Nothing sent today";
}

function SmsHealth() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(() => {
    setErr("");
    api.get("/sms/status").then((r) => setData(r.data)).catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const resume = useCallback(async (type) => {
    if (!window.confirm(`Resume ${SMS_LABELS[type]}? Fix the cause first: a message that fails again is still charged.`)) return;
    setBusy(type);
    setErr("");
    try { setData((await api.post(`/sms/${type}/resume`)).data); }
    catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(""); }
  }, []);

  if (!data) return err ? <ErrorCard message={err} onRetry={load} /> : <p className="text-slate-600" data-testid="sms-loading">Loading SMS status…</p>;
  const today = data.today;
  return (
    <div className="space-y-4" data-testid="sms-health">
      {err && <Alert>{err}</Alert>}
      {!data.reports_enabled && (
        <Alert tone="amber">Delivery reports are off. Failed messages are not counted here, and a DLT failure cannot pause sending.</Alert>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Submitted today" value={today.submitted} testid="sms-today-submitted" />
        <Stat label="Delivered" value={today.delivered} tone="emerald" testid="sms-today-delivered" />
        <Stat label="DLT failures" value={today.dlt_failed} tone={today.dlt_failed ? "amber" : "slate"} testid="sms-today-dlt" />
        <Stat label="Credits charged" value={today.credits} testid="sms-today-credits" />
      </div>
      <Card className="!p-0 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-100">
          <h3 className="font-display font-bold text-slate-900">Message types</h3>
          <Button size="sm" variant="ghost" onClick={load} aria-label="Refresh SMS status" data-testid="sms-refresh"><RefreshCw className="w-4 h-4" /></Button>
        </div>
        <ul className="divide-y divide-slate-100">
          {data.types.map((t) => (
            <li key={t.message_type} className="p-4 flex flex-col sm:flex-row sm:items-center gap-3" data-testid={`sms-type-${t.message_type}`}>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-900">{SMS_LABELS[t.message_type]}</p>
                  {t.paused ? <Badge tone="rose">Paused</Badge> : t.configured ? <Badge tone="emerald">Sending</Badge> : <Badge>Not set up</Badge>}
                </div>
                {t.paused && (
                  <p className="text-sm text-rose-700 mt-1 break-words" data-testid={`sms-paused-reason-${t.message_type}`}>
                    {t.paused_reason} · {displayTimestamp(t.paused_at)}
                    {t.paused_request_id && <span className="block text-xs text-slate-600 font-mono">MSG91 request {t.paused_request_id}</span>}
                  </p>
                )}
                <p className="text-xs text-slate-600 mt-1" data-testid={`sms-today-${t.message_type}`}>{todayLine(t.today)}</p>
              </div>
              {t.paused && (
                <Button className="w-full sm:w-auto" onClick={() => resume(t.message_type)} disabled={busy === t.message_type} data-testid={`sms-resume-${t.message_type}`}>
                  Resume
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-xs text-slate-600">
        A DLT failure pauses that message type, because the provider charges for every failed message. Registration and Token SMS due while paused are not sent later; the day’s reminders wait and go out if you resume before the day ends.
      </p>
    </div>
  );
}

function useCatalogue(resource) {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get(`/catalogue/${resource}?include_inactive=true`)
      .then((r) => setItems(r.data[resource] || []))
      .catch((e) => setErr(formatApiError(e)));
  }, [resource]);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async (body) => {
    setErr("");
    setBusy(true);
    try {
      await api.post(`/catalogue/${resource}`, body);
      load();
      return true;
    } catch (e) {
      setErr(formatApiError(e));
      return false;
    } finally {
      setBusy(false);
    }
  }, [resource, load]);

  const setActive = useCallback(async (id, active) => {
    setErr("");
    try {
      await api.patch(`/catalogue/${resource}/${id}`, { active });
      load();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, [resource, load]);

  return { items, err, busy, add, setActive };
}

function CatalogueChips({ items, setActive, testid, label, icon: Icon }) {
  return (
    <div className="flex flex-wrap gap-2" data-testid={`${testid}-list`}>
      {items.length === 0 && <p className="text-slate-600 text-sm">Nothing added yet.</p>}
      {items.map((item) => (
        <div
          key={item.id}
          className={`flex items-center gap-2 px-3 py-2 rounded-xl ${item.active ? "bg-slate-50" : "bg-slate-100 opacity-60"}`}
          data-testid={`${testid}-${item.id}`}
        >
          <Icon className="w-4 h-4 text-emerald-600" />
          <span className="text-sm font-medium text-slate-800">{label(item)}</span>
          <Button size="sm" variant="ghost" onClick={() => setActive(item.id, !item.active)}
            data-testid={`${testid}-${item.id}-toggle`}>
            {item.active ? "Retire" : "Restore"}
          </Button>
        </div>
      ))}
    </div>
  );
}

function Medicines() {
  const [name, setName] = useState("");
  const { items, err, busy, add, setActive } = useCatalogue("medicines");
  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-1">Medicines</h3>
        <p className="text-sm text-slate-600 mb-3">The clinical desk can only prescribe what is on this list. Retiring one hides it from operators without touching past prescriptions.</p>
        <CatalogueChips items={items} setActive={setActive} testid="medicine" icon={Pill} label={(m) => m.name} />
        <div className="flex flex-wrap gap-2 items-end pt-4 mt-3 border-t border-slate-100">
          <Field label="Medicine name">
            <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="medicine-name-input" />
          </Field>
          <Button size="sm" disabled={busy || !name.trim()}
            onClick={() => add({ name }).then((ok) => ok && setName(""))}
            data-testid="add-medicine-button">
            <Plus className="w-4 h-4" /> Add
          </Button>
        </div>
      </Card>
    </div>
  );
}

function FixedPowers() {
  const [value, setValue] = useState("");
  const { items, err, busy, add, setActive } = useCatalogue("powers");
  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-1">Fixed-power specs</h3>
        <p className="text-sm text-slate-600 mb-3">Every ready-made power this camp carries, plus or minus. The clinical desk picks from these.</p>
        <CatalogueChips items={items} setActive={setActive} testid="power" icon={Glasses} label={(p) => formatPower(p.value)} />
        <div className="flex flex-wrap gap-2 items-end pt-4 mt-3 border-t border-slate-100">
          <Field label="Power (dioptres)">
            <Input value={value} inputMode="decimal" placeholder="+2.00" className="w-32"
              onChange={(e) => setValue(e.target.value)} data-testid="power-value-input" />
          </Field>
          <Button size="sm" disabled={busy || !value.trim()}
            onClick={() => add({ value }).then((ok) => ok && setValue(""))}
            data-testid="add-power-button">
            <Plus className="w-4 h-4" /> Add
          </Button>
        </div>
      </Card>
    </div>
  );
}

function Board({ title, rows = [], testid }) {
  const safeRows = rows || [];
  return (
    <Card>
      <h3 className="font-display font-bold text-slate-900 mb-3 flex items-center gap-2">
        <Trophy className="w-5 h-5 text-amber-500" /> {title}
      </h3>
      <div className="space-y-2" data-testid={testid}>
        {safeRows.length === 0 && <p className="text-slate-600 text-sm">No points yet.</p>}
        {safeRows.map((r, i) => (
          <div key={`${r.name}-${i}`} className="flex items-center gap-3 p-2.5 rounded-xl bg-slate-50">
            <span className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold ${i === 0 ? "bg-amber-400 text-white" : "bg-slate-200 text-slate-600"}`}>
              {i + 1}
            </span>
            <span className="flex-1 font-medium text-slate-800">{r.name}</span>
            {r.registrations !== undefined && <Badge tone="slate">{r.registrations} registrations</Badge>}
            {r.arrivals !== undefined && <Badge tone="slate">{r.arrivals} arrivals</Badge>}
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
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Board title="Volunteers" rows={data.volunteers} testid="leaderboard-volunteers-table" />
      <Board title="Team Leads" rows={data.team_leads} testid="leaderboard-team-leads-table" />
    </div>
  );
}

async function exportErrorMessage(e) {
  try {
    const body = JSON.parse(await e.response.data.text());
    return body.detail != null ? formatApiError({ response: { data: body } }) : body.message || formatApiError(e);
  } catch {
    return formatApiError(e);
  }
}

function Exports() {
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const download = useCallback(async (path, filename) => {
    setMsg("");
    setErr("");
    try {
      const res = await api.get(path, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = filename; a.click();
      setTimeout(() => window.URL.revokeObjectURL(url), 0);
      setMsg(`Downloaded ${filename}`);
    } catch (e) { setErr(await exportErrorMessage(e)); }
  }, []);
  return (
    <div className="space-y-4">
      {msg && <Alert tone="emerald">{msg}</Alert>}
      <Alert>{err}</Alert>
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
