import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import Layout from "../components/Layout";
import AadhaarScanner from "../components/AadhaarScanner";
import { v4 } from "../lib/uuid";
import {
  Button, Card, Input, Field, Alert, Modal, Stat, StatusBadge, Badge, ErrorCard,
} from "../components/ui";
import {
  UserPlus, Search, Printer, CheckCircle2, Undo2, ScanLine, Lock, Users,
} from "lucide-react";

export default function Desk() {
  const navigate = useNavigate();
  const [kpi, setKpi] = useState(null);
  const [patients, setPatients] = useState([]);
  const [loadErr, setLoadErr] = useState("");
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [showReg, setShowReg] = useState(false);
  const [lookupVal, setLookupVal] = useState("");
  const [searchVal, setSearchVal] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [banner, setBanner] = useState("");

  const load = useCallback(async () => {
    setLoadErr("");
    try {
      const [k, p, a] = await Promise.all([
        api.get("/kpis"), api.get("/patients"), api.get("/camps/active"),
      ]);
      setKpi(k.data);
      setPatients(p.data.patients);
      setCamp(a.data.camp);
      setDays(a.data.days || []);
    } catch (e) {
      setLoadErr(formatApiError(e));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doLookup = async (e) => {
    e?.preventDefault();
    if (!lookupVal.trim()) return;
    setBanner("");
    try {
      const { data } = await api.post("/desk/lookup", { value: lookupVal.trim() });
      const el = document.getElementById(`row-${data.registration.id}`);
      setLookupVal("");
      await load();
      setTimeout(() => el?.scrollIntoView({ behavior: "smooth", block: "center" }), 100);
      setBanner(`Found reg #${data.registration.reg_no} — ${data.registration.full_name}`);
    } catch (err) {
      setBanner(formatApiError(err));
    }
  };

  const doSearch = async (e) => {
    e?.preventDefault();
    if (!searchVal.trim()) { setSearchResults(null); return; }
    try {
      const { data } = await api.get(`/patients/search?q=${encodeURIComponent(searchVal.trim())}`);
      setSearchResults(data.results);
    } catch (err) { setBanner(formatApiError(err)); }
  };

  const markSeen = async (id) => {
    setBanner("");
    try { await api.post(`/desk/mark-seen/${id}`); await load(); }
    catch (err) { setBanner(formatApiError(err)); }
  };
  const undoSeen = async (id) => {
    setBanner("");
    try { await api.post(`/desk/undo-seen/${id}`); await load(); }
    catch (err) { setBanner(formatApiError(err)); }
  };

  if (loadErr) return <Layout title="Desk"><ErrorCard message={loadErr} onRetry={load} /></Layout>;

  const noCamp = !camp;

  return (
    <Layout title="Registration Desk">
      {noCamp && <Alert tone="amber" className="mb-4">No active camp. Ask an admin to activate one.</Alert>}

      <div className="grid grid-cols-3 gap-3 mb-5">
        <Stat label="Registered" value={kpi?.registered ?? "—"} testid="kpi-registered-count" />
        <Stat label="Seen" value={kpi?.seen ?? "—"} tone="emerald" testid="kpi-seen-count" />
        <Stat label="Pending" value={kpi?.pending ?? "—"} tone="amber" testid="kpi-pending-count" />
      </div>

      <Card className="mb-5">
        <div className="flex flex-col sm:flex-row gap-3">
          <Button size="lg" className="sm:w-auto" onClick={() => setShowReg(true)} disabled={noCamp} data-testid="new-registration-button">
            <UserPlus className="w-5 h-5" /> New Registration
          </Button>
          <form onSubmit={doLookup} className="flex-1 flex gap-2">
            <Input value={lookupVal} onChange={(e) => setLookupVal(e.target.value)} placeholder="Scan patient QR or type Reg #" data-testid="desk-lookup-input" />
            <Button type="submit" variant="secondary" data-testid="desk-lookup-button"><ScanLine className="w-5 h-5" /></Button>
          </form>
        </div>
        <form onSubmit={doSearch} className="flex gap-2 mt-3">
          <Input value={searchVal} onChange={(e) => setSearchVal(e.target.value)} placeholder="Name search (lost paper/number)" data-testid="desk-name-search-input" />
          <Button type="submit" variant="outline" data-testid="desk-name-search-button"><Search className="w-5 h-5" /></Button>
        </form>
        {banner && <Alert tone="emerald" className="mt-3">{banner}</Alert>}
      </Card>

      {searchResults && (
        <Card className="mb-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display font-bold text-slate-900">Search results ({searchResults.length})</h3>
            <Button variant="ghost" size="sm" onClick={() => { setSearchResults(null); setSearchVal(""); }}>Clear</Button>
          </div>
          <PatientList patients={searchResults} days={days} onMarkSeen={markSeen} onUndo={undoSeen} navigate={navigate} />
        </Card>
      )}

      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Users className="w-5 h-5 text-slate-400" />
          <h3 className="font-display font-bold text-slate-900">Today's patients</h3>
          <Badge className="ml-auto">{patients.length}</Badge>
        </div>
        {patients.length === 0 ? (
          <p className="text-slate-400 text-sm text-center py-8">No registrations yet.</p>
        ) : (
          <PatientList patients={patients} days={days} onMarkSeen={markSeen} onUndo={undoSeen} navigate={navigate} />
        )}
      </Card>

      <RegisterModal open={showReg} onClose={() => setShowReg(false)} days={days} onDone={load} setBanner={setBanner} />
    </Layout>
  );
}

function PatientList({ patients, onMarkSeen, onUndo, navigate }) {
  return (
    <div className="space-y-2" data-testid="patient-list">
      {patients.map((p) => (
        <div key={p.id} id={`row-${p.id}`} className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-slate-200 hover:border-emerald-300 transition-colors" data-testid={`patient-row-${p.reg_no}`}>
          <div className="w-14 shrink-0">
            <span className="font-mono font-bold text-emerald-600">#{p.reg_no}</span>
          </div>
          <div className="flex-1 min-w-[140px]">
            <p className="font-semibold text-slate-900">{p.full_name} {p.aadhaar_scanned && <Lock className="w-3 h-3 inline text-slate-400" />}</p>
            <p className="text-xs text-slate-400">{p.gender_label} · {p.age ?? "-"} yrs {p.phone ? `· ${p.phone}` : ""} {p.is_self_registered && "· self"}</p>
          </div>
          <StatusBadge status={p.queue_status} />
          {p.printed_at && <Badge tone="indigo">Printed</Badge>}
          <div className="flex gap-1.5 ml-auto">
            <Button size="sm" variant="outline" onClick={() => navigate(`/print/prescription/${p.id}`)} data-testid={`print-button-${p.reg_no}`}>
              <Printer className="w-4 h-4" /> Print
            </Button>
            {p.queue_status !== "seen" ? (
              <Button size="sm" onClick={() => onMarkSeen(p.id)} data-testid={`mark-seen-button-${p.reg_no}`}>
                <CheckCircle2 className="w-4 h-4" /> Seen
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => onUndo(p.id)} data-testid={`undo-seen-button-${p.reg_no}`}>
                <Undo2 className="w-4 h-4" /> Undo
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function RegisterModal({ open, onClose, days, onDone, setBanner }) {
  const empty = { full_name: "", age: "", phone: "", gender: "", address: "", aadhaar_last4: "", dob: "" };
  const [form, setForm] = useState(empty);
  const [scanned, setScanned] = useState(false);
  const [dayId, setDayId] = useState("");
  const [manualEx, setManualEx] = useState(false);
  const [manualReason, setManualReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dups, setDups] = useState(null);
  const [reqId, setReqId] = useState(v4());

  useEffect(() => {
    if (open) {
      setForm(empty); setScanned(false); setManualEx(false); setManualReason("");
      setError(""); setDups(null); setReqId(v4());
      const today = days.find((d) => d.is_today);
      setDayId(today ? today.id : (days[0]?.id || ""));
    }
  }, [open]); // eslint-disable-line

  const onScan = (data) => {
    setForm({
      full_name: data.full_name, age: data.age ?? "", phone: form.phone,
      gender: data.gender, address: data.address, aadhaar_last4: data.aadhaar_last4, dob: data.dob,
    });
    setScanned(true);
  };

  const submit = async (override = false) => {
    setBusy(true); setError("");
    try {
      if (!override) {
        const { data } = await api.post("/register/duplicate-check", {
          full_name: form.full_name, age: form.age ? Number(form.age) : null,
        });
        if (data.likely_duplicates.length > 0) { setDups(data.likely_duplicates); setBusy(false); return; }
      }
      const { data } = await api.post("/register", {
        full_name: form.full_name,
        age: form.age ? Number(form.age) : null,
        phone: form.phone || null,
        gender: form.gender || null,
        address: form.address || null,
        aadhaar_last4: form.aadhaar_last4 || null,
        dob: form.dob || null,
        aadhaar_scanned: scanned,
        camp_day_id: dayId,
        registration_request_id: reqId,
        manual_exception: manualEx,
        manual_reason: manualEx ? manualReason : null,
        failed_scan_attempts: manualEx ? 2 : 0,
        override_duplicate: override,
      });
      setBanner(`Registered #${data.registration.reg_no} — ${data.registration.full_name}`);
      onClose(); onDone();
    } catch (err) {
      const payload = errorPayload(err);
      if (payload && payload.code === "DUPLICATE_IN_CAMP") {
        setError(`Already registered as #${payload.registration.reg_no}. Print for them instead.`);
      } else {
        setError(formatApiError(err));
      }
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Registration" size="lg">
      <div className="space-y-4">
        <AadhaarScanner onScanned={onScan} />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Full name" required>
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} readOnly={scanned} className={scanned ? "bg-slate-100" : ""} data-testid="reg-fullname-input" />
          </Field>
          <Field label="Age" required>
            <Input type="number" value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value })} readOnly={scanned} className={scanned ? "bg-slate-100" : ""} data-testid="reg-age-input" />
          </Field>
          <Field label="Gender">
            <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300 disabled:bg-slate-100" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} disabled={scanned} data-testid="reg-gender-select">
              <option value="">—</option><option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
            </select>
          </Field>
          <Field label="Phone (household)" required hint="10-digit mobile">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} inputMode="numeric" data-testid="reg-phone-input" />
          </Field>
          <Field label="Aadhaar last-4">
            <Input value={form.aadhaar_last4} onChange={(e) => setForm({ ...form, aadhaar_last4: e.target.value })} readOnly={scanned} className={scanned ? "bg-slate-100" : ""} maxLength={4} data-testid="reg-last4-input" />
          </Field>
          <Field label="Camp day">
            <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={dayId} onChange={(e) => setDayId(e.target.value)} data-testid="reg-day-select">
              {days.map((d) => <option key={d.id} value={d.id}>{d.day_date}{d.is_today ? " (today)" : ""}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Address">
          <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} readOnly={scanned} className={scanned ? "bg-slate-100" : ""} data-testid="reg-address-input" />
        </Field>

        {!scanned && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
            <label className="flex items-center gap-2 text-sm font-semibold text-amber-800">
              <input type="checkbox" checked={manualEx} onChange={(e) => setManualEx(e.target.checked)} className="w-5 h-5" data-testid="manual-exception-checkbox" />
              Manual exception (after 2 failed scans)
            </label>
            {manualEx && (
              <Input className="mt-2" placeholder="Reason (audited)" value={manualReason} onChange={(e) => setManualReason(e.target.value)} data-testid="manual-exception-reason" />
            )}
          </div>
        )}

        <Alert>{error}</Alert>

        {dups ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 space-y-2" data-testid="duplicate-warning">
            <p className="text-sm font-semibold text-amber-800">Likely duplicate(s) — same name & age:</p>
            {dups.map((d) => (
              <p key={d.id} className="text-sm text-slate-700">#{d.reg_no} — {d.full_name} ({d.age})</p>
            ))}
            <div className="flex gap-2 pt-1">
              <Button variant="outline" size="sm" onClick={() => { setDups(null); onClose(); }} data-testid="dup-print-instead">Cancel / Print for them</Button>
              <Button size="sm" onClick={() => submit(true)} disabled={busy} data-testid="dup-register-anyway">Register anyway</Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2 justify-end pt-1">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={() => submit(false)} disabled={busy || !form.full_name || !dayId} data-testid="patient-register-submit">
              {busy ? "Registering…" : "Register"}
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
