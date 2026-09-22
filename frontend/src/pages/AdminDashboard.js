import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import Layout from "../components/Layout";
import {
  Button, Card, Input, Field, Alert, Modal, Stat, Badge, ErrorCard,
} from "../components/ui";
import {
  Tent, Users, CalendarDays, Trophy, Download, Scissors, Glasses, Power, Trash2,
  Plus, PrinterCheck, ClipboardList, Stethoscope, FileText, BarChart3, Pill, Pencil,
} from "lucide-react";
import { formatPower } from "../components/clinical";
import TemplateEditor from "../components/TemplateEditor";
import { displayDate, displayDateRange } from "../lib/dates";

const CAMP_VENUE = "Hansa Garden, Rohini Road in Baghmara, Jasidih, Deoghar - 814142";
const NEW_CAMP = { name: "SNP नेत्र शिविर", venue: CAMP_VENUE, camp_date: "", camp_number: "" };
const HOSPITAL_VENUE = "Vimla Ramkrishna Bajaj Eye Hospital, Near Canara Bank, Bilasi Mod, Deoghar 814112 (Jharkhand)";

const TABS = [
  { id: "overview", label: "Overview", icon: ClipboardList },
  { id: "camps", label: "Camps & Days", icon: Tent },
  { id: "template", label: "Rx Template", icon: FileText },
  { id: "ot", label: "OT & Specs", icon: Scissors },
  { id: "supplies", label: "Camp supplies", icon: Pill },
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
      {tab === "template" && <TemplateEditor />}
      {tab === "ot" && <div className="space-y-5"><OtSchedule /><SpecsCollectionDays /></div>}
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
        <Button size="lg" variant="outline" onClick={() => navigate("/team")} data-testid="goto-team-button"><Users className="w-5 h-5" /> Team management</Button>
        <Button size="lg" variant="outline" onClick={() => navigate("/analytics")} data-testid="goto-analytics-button"><BarChart3 className="w-5 h-5" /> Analytics</Button>
      </div>
    </div>
  );
}

function Camps() {
  const [camps, setCamps] = useState([]);
  const [err, setErr] = useState("");
  const [showCamp, setShowCamp] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(NEW_CAMP);
  const [expand, setExpand] = useState(null);
  const campNumber = Number(form.camp_number);

  const load = useCallback(() => {
    api.get("/camps").then((r) => setCamps(r.data.camps)).catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCamp = (c) => {
    setEditing(c ? c.id : null);
    setForm(c ? { name: c.name, venue: c.venue, camp_date: c.camp_date, camp_number: c.camp_number ?? "" } : NEW_CAMP);
    setShowCamp(true);
  };

  const saveCamp = useCallback(async () => {
    try {
      const body = { ...form, camp_number: Number(form.camp_number) };
      if (editing) await api.patch(`/camps/${editing}`, body);
      else await api.post("/camps", body);
      setShowCamp(false);
      load();
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, [editing, form, load]);

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

  const setDoorManual = useCallback(async (enabled) => {
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
            <div className="flex-1">
              <p className="font-display font-bold text-slate-900">{c.name} {c.is_active && <Badge tone="emerald">Active</Badge>}</p>
              <p className="text-xs text-slate-400">{c.venue} · {displayDate(c.camp_date)}</p>
              {c.camp_number
                ? <Badge className="mt-1" data-testid={`camp-number-${c.id}`}>SMS camp no. {c.camp_number}</Badge>
                : <Badge tone="amber" className="mt-1" data-testid={`camp-number-missing-${c.id}`}>No camp number: SMS are not sent</Badge>}
            </div>
            <Button size="sm" variant="outline" onClick={() => openCamp(c)} data-testid={`edit-camp-${c.id}`}><Pencil className="w-4 h-4" /> Edit</Button>
            {c.is_active ? (
              <Button size="sm" variant="ghost" onClick={() => deactivate(c.id)} data-testid={`deactivate-camp-${c.id}`}><Power className="w-4 h-4" /> Deactivate</Button>
            ) : (
              <Button size="sm" onClick={() => activate(c.id)} data-testid={`activate-camp-${c.id}`}><Power className="w-4 h-4" /> Activate</Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setExpand(expand === c.id ? null : c.id)} data-testid={`manage-days-${c.id}`}><CalendarDays className="w-4 h-4" /> Days</Button>
            <Button size="sm" variant="ghost" onClick={() => del(c.id)} data-testid={`delete-camp-${c.id}`}><Trash2 className="w-4 h-4 text-rose-500" /></Button>
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
          <Field label="Venue" required hint="Sent in the registration and camp-reminder SMS."><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="camp-venue-input" /></Field>
          <Field label="Camp date" required><Input type="date" value={form.camp_date} onChange={(e) => setForm({ ...form, camp_date: e.target.value })} data-testid="camp-date-input" /></Field>
          <Field label="Camp number" required hint="The SMS reads “SNP के 162वें नेत्र शिविर”."><Input type="number" min="1" step="1" inputMode="numeric" value={form.camp_number} onChange={(e) => setForm({ ...form, camp_number: e.target.value })} data-testid="camp-number-input" /></Field>
          <Button className="w-full" onClick={saveCamp} disabled={!form.name || !form.venue || !form.camp_date || !(Number.isInteger(campNumber) && campNumber > 0)} data-testid="camp-create-submit">{editing ? "Save" : "Create"}</Button>
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
          <span className="font-medium text-slate-800 text-sm">{displayDate(d.day_date)}</span>
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
        <Field label="Date"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid="new-day-date" /></Field>
        <Field label="Seat limit"><Input type="number" value={seat} onChange={(e) => setSeat(e.target.value)} className="w-28" data-testid="new-day-seat" /></Field>
        <Button size="sm" onClick={add} disabled={!date} data-testid="add-day-button"><Plus className="w-4 h-4" /> Add day</Button>
      </div>
    </div>
  );
}


function OtSchedule() {
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ day_date: "", venue: HOSPITAL_VENUE, venue_sms: "", seat_limit: 10 });

  const load = useCallback(() => {
    Promise.all([api.get("/clinical/ot-days"), api.get("/camps/active")])
      .then(([o, a]) => { setDays(o.data.ot_days); setCamp(a.data.camp); })
      .catch((e) => setErr(formatApiError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async () => {
    setErr("");
    if (!camp) { setErr("Activate a camp first."); return; }
    try { await api.post("/clinical/ot-days", { camp_id: camp.id, ...form, seat_limit: Number(form.seat_limit) }); setForm({ day_date: "", venue: HOSPITAL_VENUE, venue_sms: "", seat_limit: 10 }); load(); }
    catch (e) { setErr(formatApiError(e)); }
  }, [camp, form, load]);

  return (
    <div className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card>
        <h3 className="font-display font-bold text-slate-900 mb-3">OT Schedule Days</h3>
        <p className="text-sm text-slate-600 mb-3">Surgery takes place at the hospital. The camp only schedules the appointment.</p>
        <div className="space-y-2" data-testid="ot-days-list">
          {days.length === 0 && <p className="text-slate-400 text-sm">No OT days yet.</p>}
          {days.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50" data-testid={`ot-day-${d.id}`}>
              <Scissors className="w-4 h-4 text-emerald-600" />
              <span className="font-medium text-slate-800 text-sm">{displayDate(d.day_date)}</span>
              <span className="text-xs text-slate-400">{d.venue}</span>
              <Badge tone={d.seats_free > 0 ? "emerald" : "rose"} className="ml-auto">{d.seats_taken}/{d.seat_limit} seats</Badge>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 items-end pt-4 mt-3 border-t border-slate-100">
          <Field label="Date"><Input type="date" value={form.day_date} onChange={(e) => { const existing = days.find((d) => d.day_date === e.target.value); setForm({ ...form, day_date: e.target.value, venue: existing ? existing.venue : HOSPITAL_VENUE, venue_sms: existing?.venue_sms || "", seat_limit: existing ? existing.seat_limit : form.seat_limit }); }} data-testid="ot-date-input" /></Field>
          <Field label="Hospital"><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="ot-venue-input" /></Field>
          <Field label="Short name for SMS"><Input value={form.venue_sms} onChange={(e) => setForm({ ...form, venue_sms: e.target.value })} placeholder={HOSPITAL_VENUE} data-testid="ot-venue-sms-input" /></Field>
          <Field label="Seats"><Input type="number" value={form.seat_limit} onChange={(e) => setForm({ ...form, seat_limit: e.target.value })} className="w-24" data-testid="ot-seat-input" /></Field>
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
  const [form, setForm] = useState({ day_date: "", end_date: "", venue: "", start_time: "", end_time: "" });

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
      setForm({ day_date: "", end_date: "", venue: "", start_time: "", end_time: "" });
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
          {days.length === 0 && <p className="text-slate-400 text-sm">No Specs collection days yet.</p>}
          {days.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-3 rounded-xl bg-slate-50" data-testid={`specs-day-${d.id}`}>
              <Glasses className="w-4 h-4 text-emerald-600" />
              <span className="font-medium text-slate-800 text-sm">{displayDateRange(d.day_date, d.end_date)}</span>
              <span className="text-xs text-slate-400">{d.venue}</span>
              <Badge tone={d.window_required ? "amber" : "emerald"} className="ml-auto">
                {d.start_time && d.end_time ? `${d.start_time}–${d.end_time}` : "window required"}
              </Badge>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 items-end pt-4 mt-3 border-t border-slate-100">
          <Field label="From"><Input type="date" value={form.day_date} onChange={(e) => setForm({ ...form, day_date: e.target.value })} data-testid="specs-date-input" /></Field>
          <Field label="To"><Input type="date" value={form.end_date} min={form.day_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} data-testid="specs-end-date-input" /></Field>
          <Field label="Venue"><Input value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} data-testid="specs-venue-input" /></Field>
          <Field label="Start"><Input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} className="w-28" data-testid="specs-start-input" /></Field>
          <Field label="End"><Input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} className="w-28" data-testid="specs-end-input" /></Field>
          <Button size="sm" onClick={add} disabled={!form.day_date || !form.venue || !form.start_time || !form.end_time} data-testid="add-specs-day-button"><Plus className="w-4 h-4" /> Add</Button>
        </div>
        <p className="text-xs text-slate-500 mt-2">Leave “To” empty for a single day. The SMS reads सुबह (start) से शाम (end), so start before 12:00 and end at 12:00 or later.</p>
      </Card>
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
      {items.length === 0 && <p className="text-slate-400 text-sm">Nothing added yet.</p>}
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
        {safeRows.length === 0 && <p className="text-slate-400 text-sm">No points yet.</p>}
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
