import React, { useEffect, useState, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import AadhaarScanner from "../components/AadhaarScanner";
import { useWedgeBurst } from "../components/aadhaar";
import { ScanOutcome } from "../components/desk/ScanOutcome";
import { v4 } from "../lib/uuid";
import { displayDate } from "../lib/dates";
import {
  Button, Card, Input, Field, Alert, Modal, Stat, StatusBadge, Badge, ErrorCard, Spinner, Select,
} from "../components/ui";
import {
  UserPlus, Search, Printer, ScanLine,
} from "lucide-react";

const EMPTY_REG_FORM = Object.freeze({
  full_name: "",
  age: "",
  phone: "",
  gender: "",
  address: "",
  aadhaar_last4: "",
  dob: "",
});

const AADHAAR_PAYLOAD = /^(\d{100,}|<.*>)$/s;

function registrationError(err) {
  const payload = errorPayload(err);
  if (payload?.code === "DUPLICATE_IN_CAMP") {
    return `Already registered as #${payload.registration.reg_no}. Find them below and print.`;
  }
  if (payload?.code === "AMBIGUOUS_MANUAL_ENTRY") {
    const nos = (payload.registrations || []).map((r) => `#${r.reg_no}`).join(", ");
    return `Multiple Manual entries match (${nos}). Scan the card at the door to pick one.`;
  }
  return formatApiError(err);
}

async function registerPatient({ form, qrPayload, dayId, reqId, manualReason, failedAttempts, atDoor, arrive }) {
  const scanned = Boolean(qrPayload);
  const { data } = await api.post("/register", {
    full_name: form.full_name,
    age: form.age ? Number(form.age) : null,
    phone: form.phone || null,
    gender: form.gender || null,
    address: form.address || null,
    aadhaar_last4: form.aadhaar_last4 || null,
    dob: form.dob || null,
    aadhaar_scanned: scanned,
    qr_payload: qrPayload || null,
    camp_day_id: dayId,
    registration_request_id: reqId,
    manual_reason: scanned ? null : (manualReason || null),
    failed_scan_attempts: scanned ? 0 : (failedAttempts || 0),
    at_door: Boolean(atDoor) && !scanned,
  });
  if (!arrive) return data.registration;
  const arrived = await api.post(`/desk/arrive/${data.registration.id}`);
  return arrived.data.registration;
}

export default function Desk() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [kpi, setKpi] = useState(null);
  const [loadErr, setLoadErr] = useState("");
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [showReg, setShowReg] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [scanPayload, setScanPayload] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState(null);
  const [findVal, setFindVal] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [banner, setBanner] = useState("");
  const [error, setError] = useState("");
  const [doorPhone, setDoorPhone] = useState("");
  const [doorForm, setDoorForm] = useState(EMPTY_REG_FORM);
  const [doorReqId, setDoorReqId] = useState(v4());
  const [doorCameraFailures, setDoorCameraFailures] = useState(0);
  const [doorReason, setDoorReason] = useState("");
  const walkAttempt = useRef({ key: "", reqId: "", patientId: "" });
  const [scanning, setScanning] = useState(false);
  const findSequence = useRef(0);
  const [printingOpen, setPrintingOpen] = useState(false);
  const [operatingDayId, setOperatingDayId] = useState("");
  const todayDay = days.find((d) => d.is_today);
  const campDayMode = printingOpen;
  const noCamp = !camp;

  const load = useCallback(async () => {
    setLoadErr("");
    try {
      const [k, a] = await Promise.all([api.get("/kpis"), api.get("/camps/active")]);
      setKpi(k.data);
      setCamp(a.data.camp);
      setDays(a.data.days || []);
      const today = (a.data.days || []).find((d) => d.is_today);
      const open = a.data.printing_open != null
        ? Boolean(a.data.printing_open)
        : Boolean(today?.printing_open);
      setPrintingOpen(open);
      setOperatingDayId(
        a.data.operating_day_id
        || (open ? (today?.id || (a.data.days || []).find((d) => d.printing_open)?.id || "") : ""),
      );
    } catch (e) {
      setLoadErr(formatApiError(e));
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { findSequence.current += 1; }, []);

  const clearScan = useCallback(() => { setScanResult(null); setScanPayload(""); }, []);
  const abandonScan = useCallback(() => {
    findSequence.current += 1;
    clearScan();
    setScanning(false);
  }, [clearScan]);

  const resolveDoorScan = useCallback(async (payload) => {
    const request = ++findSequence.current;
    setBanner(""); setError(""); setSearchResults(null); setFound(null);
    clearScan();
    setScanPayload(payload);
    setScanning(true);
    try {
      const { data } = await api.post("/desk/scan", { payload });
      if (request !== findSequence.current) return { outcome: "card", quiet: true, superseded: true };
      setScanResult(data);
      if (data.outcome === "arrived") {
        const extra = data.overwritten ? " (card details updated)" : "";
        setBanner(`Arrived: #${data.registration.reg_no} — ${data.registration.full_name}${extra}`);
        load();
      }
      return { outcome: "card", source: "desk_scan" };
    } catch (err) {
      if (request !== findSequence.current) return { outcome: "card", quiet: true, superseded: true };
      clearScan();
      const detail = errorPayload(err);
      if (detail?.code === "NOT_A_CARD") return { outcome: "garbage", message: detail.message };
      throw err;
    } finally {
      if (request === findSequence.current) setScanning(false);
    }
  }, [load, clearScan]);

  const confirmPatient = useCallback(async (patientId) => {
    if (!patientId || busy || scanning) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/desk/scan/confirm", {
        patient_id: patientId,
        payload: scanPayload,
      });
      setScanResult(data);
      setBanner(`Arrived: #${data.registration.reg_no} — ${data.registration.full_name}`);
      await load();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [scanPayload, load, busy, scanning]);

  const confirmMismatch = useCallback(() => {
    confirmPatient(scanResult?.registration?.id);
  }, [confirmPatient, scanResult]);

  const lookupValue = useCallback(async (value) => {
    const request = ++findSequence.current;
    setScanning(false);
    setBanner(""); setError(""); setSearchResults(null); setFound(null);
    clearScan();
    try {
      const { data } = await api.post("/desk/lookup", { value });
      if (request !== findSequence.current) return false;
      setFound(data.registration);
      return true;
    } catch (err) {
      if (request !== findSequence.current) return false;
      setFound(null);
      setError(formatApiError(err));
      return false;
    }
  }, [clearScan]);

  const doFind = useCallback(async (e) => {
    e?.preventDefault();
    const value = findVal.trim();
    if (!value) { setSearchResults(null); return; }
    if (AADHAAR_PAYLOAD.test(value)) {
      setFindVal("");
      if (!campDayMode) {
        setError("That is an Aadhaar QR. Use New Registration to register this patient.");
        return;
      }
      try {
        const result = await resolveDoorScan(value);
        if (result && result.outcome !== "card") setError(result.message);
      } catch (err) {
        setError(formatApiError(err));
      }
      return;
    }
    if (/^\d+$/.test(value) || /^snp:/i.test(value)) {
      if (await lookupValue(value)) setFindVal("");
      return;
    }
    const request = ++findSequence.current;
    setBanner(""); setError(""); setFound(null); setSearchResults(null);
    clearScan();
    setScanning(false);
    try {
      const { data } = await api.get(`/patients/search?q=${encodeURIComponent(value)}`);
      if (request !== findSequence.current) return;
      setSearchResults(data.results);
    } catch (err) {
      if (request !== findSequence.current) return;
      setError(formatApiError(err));
    }
  }, [findVal, lookupValue, clearScan, campDayMode, resolveDoorScan]);

  const print = useCallback(async (reg) => {
    setError("");
    try {
      if (!reg.arrived_at) await api.post(`/desk/arrive/${reg.id}`);
      navigate(`/print/prescription/${reg.id}`);
    } catch (err) {
      setError(formatApiError(err));
    }
  }, [navigate]);

  const confirmIdentity = useCallback(async (reg, reason) => {
    setError("");
    try {
      const { data } = await api.post("/desk/identity-check", { patient_id: reg.id, reason });
      const checked = data.registration;
      setFound((current) => (current?.id === checked.id ? checked : current));
      setSearchResults((current) => current && current.map((row) => (row.id === checked.id ? checked : row)));
      return true;
    } catch (err) {
      setError(formatApiError(err));
      return false;
    }
  }, []);
  const onConfirmIdentity = user?.role === "admin" ? confirmIdentity : undefined;

  const openPreReg = useCallback(() => { setShowReg(true); }, []);

  const submitDoorWalkIn = useCallback(async () => {
    if (!scanResult?.card) return;
    if (!operatingDayId) {
      setError("No operating camp day. Use Pre-registration.");
      return;
    }
    setBusy(true); setError("");
    const key = scanPayload || "";
    if (walkAttempt.current.key !== key) {
      walkAttempt.current = { key, reqId: v4(), patientId: "" };
    }
    try {
      const card = scanResult.card;
      let patientId = walkAttempt.current.patientId;
      if (!patientId) {
        const created = await registerPatient({
          form: {
            full_name: card.full_name,
            age: card.age ?? "",
            phone: doorPhone,
            gender: card.gender,
            address: card.address,
            aadhaar_last4: card.aadhaar_last4,
            dob: card.dob,
          },
          qrPayload: scanPayload,
          dayId: operatingDayId,
          reqId: walkAttempt.current.reqId,
        });
        patientId = created.id;
        walkAttempt.current.patientId = patientId;
      }
      const arrived = await api.post(`/desk/arrive/${patientId}`);
      const reg = arrived.data.registration;
      walkAttempt.current = { key: "", reqId: "", patientId: "" };
      clearScan();
      setFound(reg);
      setBanner(`Registered and arrived: #${reg.reg_no} — ${reg.full_name}`);
      setDoorPhone("");
      load();
    } catch (err) {
      setError(registrationError(err));
    } finally { setBusy(false); }
  }, [scanResult, scanPayload, operatingDayId, doorPhone, load, clearScan]);

  const submitDoorManual = useCallback(async () => {
    const dayId = operatingDayId || todayDay?.id || days[0]?.id;
    if (!dayId) return;
    setBusy(true); setError("");
    try {
      const asWalkIn = Boolean(printingOpen);
      const reg = await registerPatient({
        form: doorForm,
        dayId,
        reqId: doorReqId,
        arrive: asWalkIn,
        manualReason: doorReason,
        failedAttempts: doorCameraFailures,
        atDoor: true,
      });
      setFound(reg);
      setBanner(
        asWalkIn
          ? `Registered and arrived: #${reg.reg_no} — ${reg.full_name}`
          : `Registered #${reg.reg_no} — ${reg.full_name}. SMS sent.`
      );
      setDoorForm(EMPTY_REG_FORM);
      setDoorReason("");
      setDoorCameraFailures(0);
      setDoorReqId(v4());
      load();
    } catch (err) {
      setError(registrationError(err));
    } finally { setBusy(false); }
  }, [operatingDayId, printingOpen, todayDay, days, doorForm, doorReqId, doorReason, doorCameraFailures, load]);

  if (loadErr && !kpi) return <Layout title="Desk"><ErrorCard message={loadErr} onRetry={load} /></Layout>;

  return (
    <Layout title="Registration Desk">
      {user?.role === "team_lead" && (
        <div className="flex flex-wrap gap-3 mb-5">
          <Link to="/team" className="min-h-[44px] flex items-center px-4 rounded-xl border border-slate-300 font-semibold text-slate-900" data-testid="desk-team-link">Team Management</Link>
          <Link to="/analytics" className="min-h-[44px] flex items-center px-4 rounded-xl border border-slate-300 font-semibold text-slate-900" data-testid="desk-analytics-link">Analytics</Link>
        </div>
      )}
      {noCamp && <Alert tone="amber" className="mb-4">No active camp. Ask an admin to activate one.</Alert>}
      {loadErr && (
        <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="desk-refresh-error">
          <Alert tone="amber" className="flex-1">Could not refresh the desk: {loadErr}</Alert>
          <Button variant="outline" size="sm" onClick={load}>Retry</Button>
        </div>
      )}

      <div className={`grid gap-2 sm:gap-3 mb-5 ${campDayMode ? "grid-cols-3" : "grid-cols-1"}`}>
        <Stat label="Registered" value={kpi?.registered ?? "—"} testid="kpi-registered-count" />
        {campDayMode && <Stat label="Seen" value={kpi?.seen ?? "—"} tone="emerald" testid="kpi-seen-count" />}
        {campDayMode && <Stat label="Pending" value={kpi?.pending ?? "—"} tone="amber" testid="kpi-pending-count" />}
      </div>

      {!campDayMode && (
        <>
          <Card className="mb-5" data-desk-card="prereg" data-testid="desk-card-prereg">
            <h3 className="font-display font-bold text-slate-900 mb-1">Pre-registration</h3>
            <p className="text-sm text-slate-500 mb-3">
              Books a seat and sends the patient their registration number. Nothing prints.
            </p>
            <Button size="lg" onClick={openPreReg} disabled={noCamp} data-testid="new-registration-button">
              <UserPlus className="w-5 h-5" /> New Registration
            </Button>
          </Card>
          {error && <Alert className="mb-5">{error}</Alert>}
          {banner && <Alert tone="emerald" className="mb-5">{banner}</Alert>}
        </>
      )}

      {campDayMode && <DoorScanCard
        noCamp={noCamp}
        resolveDoorScan={resolveDoorScan}
        onPatientCode={lookupValue}
        error={error}
        banner={banner}
        scanResult={scanResult}
        busy={busy}
        print={print}
        confirmMismatch={confirmMismatch}
        confirmPatient={confirmPatient}
        doorPhone={doorPhone}
        setDoorPhone={setDoorPhone}
        submitDoorWalkIn={submitDoorWalkIn}
        doorForm={doorForm}
        setDoorForm={setDoorForm}
        submitDoorManual={submitDoorManual}
        scanning={scanning}
        doorManualEntry={Boolean(camp?.door_manual_entry)}
        doorCameraFailures={doorCameraFailures}
        onTerminalAttempt={() => setDoorCameraFailures((n) => n + 1)}
        doorReason={doorReason}
        setDoorReason={setDoorReason}
        clearScan={abandonScan}
      />}

      <Card className="mb-5" data-desk-card="find" data-testid="desk-card-find">
        <h3 className="font-display font-bold text-slate-900 mb-3">Find one patient</h3>
        <form onSubmit={doFind} className="flex gap-2">
          <Input value={findVal} onChange={(e) => setFindVal(e.target.value)}
            aria-label="Registration number or name" autoComplete="off" enterKeyHint="search"
            placeholder="Registration number or name" data-testid="desk-find-input" />
          <Button type="submit" variant="secondary" aria-label="Find patient" data-testid="desk-find-button"><Search className="w-5 h-5" /></Button>
        </form>

        {found && (
          <div className="mt-4" data-testid="desk-found-patient">
            <PatientRow p={found} onPrint={print} printingOpen={printingOpen} onConfirmIdentity={onConfirmIdentity} />
          </div>
        )}

        {searchResults && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-semibold text-slate-700">Search results ({searchResults.length})</p>
              <Button variant="ghost" size="sm" onClick={() => { setSearchResults(null); setFindVal(""); }}>Clear</Button>
            </div>
            <div className="space-y-2" data-testid="desk-search-results">
              {searchResults.map((p) => (
                <PatientRow key={p.id} p={p} onPrint={print} printingOpen={printingOpen} onConfirmIdentity={onConfirmIdentity} />
              ))}
            </div>
          </div>
        )}
      </Card>

      <RegisterModal
        open={showReg}
        onClose={() => setShowReg(false)}
        days={days}
        onDone={load}
        setBanner={setBanner}
        onRegistered={setFound}
      />
    </Layout>
  );
}

function DoorScanCard({
  noCamp, resolveDoorScan, onPatientCode, error, banner, scanResult, busy,
  print, confirmMismatch, confirmPatient, doorPhone, setDoorPhone, submitDoorWalkIn,
  doorForm, setDoorForm, submitDoorManual, scanning,
  doorManualEntry, doorCameraFailures, onTerminalAttempt, doorReason, setDoorReason, clearScan,
}) {
  const manualOpen = doorManualEntry && doorCameraFailures >= 3;
  const manualReady = !busy && !scanning && Boolean(doorReason.trim()) && Boolean(doorForm.full_name) && Boolean(doorForm.age) && /^\d{10}$/.test(doorForm.phone || "");
  return (
    <Card className="mb-5" data-desk-card="scan" data-testid="desk-card-scan">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <h3 className="font-display font-bold text-slate-900">Scan at the door</h3>
      </div>
      <AadhaarScanner
        resolvePayload={resolveDoorScan}
        onPatientCode={onPatientCode}
        usbFirst
        disabled={noCamp || busy}
        onCaptureStart={clearScan}
        onFailure={(kind) => { if (kind === "error") onTerminalAttempt(); }}
      />
      {scanning && (
        <div data-testid="door-scan-status" role="status" aria-live="polite" aria-atomic="true" className="flex items-center gap-2 mt-3 min-h-[44px] text-slate-900 font-semibold">
          <Spinner className="w-5 h-5 text-emerald-700" />
          <span>Reading the QR and finding the patient…</span>
        </div>
      )}
      {error && <Alert className="mt-3">{error}</Alert>}
      {banner && <Alert tone="emerald" className="mt-3">{banner}</Alert>}
      <div className="mt-3">
        <ScanOutcome
          result={scanResult}
          busy={busy || scanning}
          onPrint={print}
          onConfirm={confirmMismatch}
          phone={doorPhone}
          setPhone={setDoorPhone}
          onWalkIn={submitDoorWalkIn}
          onChoose={confirmPatient}
        />
      </div>
      {manualOpen && (
        <form
          className="mt-4 space-y-3"
          data-testid="door-manual-form"
          onSubmit={(e) => { e.preventDefault(); if (manualReady) submitDoorManual(); }}
        >
          <p className="text-sm font-semibold text-amber-800" data-testid="manual-entry-note">
            Manual entry — an admin opened this because the scanners are down. It closes at the end of today.
            Failed camera attempts: {doorCameraFailures}. मैनुअल एंट्री के लिए कारण लिखें।
          </p>
          <Field label="Reason" required>
            <Input value={doorReason} onChange={(e) => setDoorReason(e.target.value)} data-testid="door-manual-reason" />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Full name" required>
              <Input value={doorForm.full_name} onChange={(e) => setDoorForm({ ...doorForm, full_name: e.target.value })} data-testid="reg-fullname-input" />
            </Field>
            <Field label="Age" required>
              <Input type="number" inputMode="numeric" pattern="[0-9]*" value={doorForm.age} onChange={(e) => setDoorForm({ ...doorForm, age: e.target.value })} data-testid="reg-age-input" />
            </Field>
            <Field label="Phone (household)" required>
              <Input value={doorForm.phone} onChange={(e) => setDoorForm({ ...doorForm, phone: e.target.value.replace(/\D/g, "").slice(0, 10) })} inputMode="numeric" autoComplete="tel" data-testid="reg-phone-input" />
            </Field>
          </div>
          <Button
            type="submit"
            disabled={!manualReady}
            data-testid="door-manual-submit"
          >
            Register
          </Button>
        </form>
      )}
    </Card>
  );
}

export function PatientRow({ p, onPrint, printingOpen, onConfirmIdentity }) {
  const [checking, setChecking] = useState(false);
  const [reason, setReason] = useState("");
  const needsDoorScan = !p.arrived_at && !p.aadhaar_scanned && !p.identity_checked;
  const identityHold = Boolean(p.identity_recheck_required) && !p.printed_at && p.queue_status !== "seen";
  const windowShut = !printingOpen && !p.printed_at;
  const canPrint = p.queue_status !== "seen" && !needsDoorScan && !windowShut && !identityHold;
  const submitCheck = async (e) => {
    e.preventDefault();
    if (await onConfirmIdentity(p, reason.trim())) {
      setChecking(false);
      setReason("");
    }
  };
  return (
    <div
      id={`row-${p.id}`}
      className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-slate-200"
      data-testid={`patient-row-${p.reg_no}`}
    >
      <span className="font-mono font-bold text-emerald-600 w-14 shrink-0">#{p.reg_no}</span>
      <div className="flex-1 min-w-[140px]">
        <p className="font-semibold text-slate-900">{p.full_name}</p>
        <p className="text-xs text-slate-600">
          {p.gender_label} · {p.age ?? "-"} yrs {p.phone ? `· ${p.phone}` : ""}
        </p>
      </div>
      <StatusBadge status={p.queue_status} />
      {p.printed_at && <Badge tone="indigo">Printed</Badge>}
      {needsDoorScan && (
        <span className="text-xs text-slate-600" data-testid={`awaiting-scan-${p.reg_no}`}>
          Scan their Aadhaar at the door to print
        </span>
      )}
      {!needsDoorScan && identityHold && (
        <span className="text-xs text-amber-800" data-testid={`identity-hold-${p.reg_no}`}>
          Typed entry. An admin must confirm identity before printing.
        </span>
      )}
      {!needsDoorScan && !identityHold && p.queue_status !== "seen" && windowShut && (
        <span className="text-xs text-slate-600" data-testid={`print-window-closed-${p.reg_no}`}>
          The print window is closed.
        </span>
      )}
      <div className="flex gap-1.5 ml-auto">
        {canPrint && (
          <Button size="sm" variant="outline" onClick={() => onPrint(p)} data-testid={`print-button-${p.reg_no}`}>
            <Printer className="w-4 h-4" /> Print
          </Button>
        )}
        {identityHold && onConfirmIdentity && !checking && (
          <Button size="sm" variant="outline" onClick={() => setChecking(true)} data-testid={`identity-check-${p.reg_no}`}>
            Confirm identity
          </Button>
        )}
      </div>
      {checking && (
        <form onSubmit={submitCheck} className="w-full flex gap-2">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="ID seen, e.g. voter ID card"
            aria-label="Identity evidence seen"
            data-testid={`identity-reason-${p.reg_no}`}
          />
          <Button size="sm" type="submit" disabled={!reason.trim()} data-testid={`identity-submit-${p.reg_no}`}>
            Confirm
          </Button>
        </form>
      )}
    </div>
  );
}

export function RegisterModal({ open, onClose, days, onDone, setBanner, onRegistered }) {
  const [form, setForm] = useState(EMPTY_REG_FORM);
  const [qrPayload, setQrPayload] = useState("");
  const [manualMode, setManualMode] = useState(false);
  const [dayId, setDayId] = useState("");
  const scanRequest = useRef(0);
  const [failures, setFailures] = useState(0);
  const [manualReason, setManualReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [wedgeReading, setWedgeReading] = useState(false);
  const [reqId, setReqId] = useState(v4());
  const prevOpenRef = useRef(false);

  useEffect(() => {
    scanRequest.current += 1;
    setWedgeReading(false);
    return () => { scanRequest.current += 1; };
  }, [open, manualMode]);

  useEffect(() => {
    if (open && !prevOpenRef.current) {
      setForm(EMPTY_REG_FORM);
      setQrPayload("");
      setManualMode(false);
      setFailures(0);
      setManualReason("");
      setError("");
      setReqId(v4());
      const today = days.find((d) => d.is_today);
      setDayId(today ? today.id : (days[0]?.id || ""));
    } else if (open && !dayId && days.length > 0) {
      const today = days.find((d) => d.is_today);
      setDayId(today ? today.id : (days[0]?.id || ""));
    }
    prevOpenRef.current = open;
  }, [open, days, dayId]);

  const scanned = Boolean(qrPayload);

  const onScan = useCallback((data, payload) => {
    setForm((prev) => ({
      full_name: data.full_name,
      age: data.age ?? "",
      phone: prev.phone,
      gender: data.gender,
      address: data.address,
      aadhaar_last4: data.aadhaar_last4,
      dob: data.dob,
    }));
    setQrPayload(payload || "");
    setManualMode(false);
    setError("");
    setReqId(v4());
  }, []);

  const onFailure = useCallback((outcome) => {
    if (outcome === "error") setFailures((n) => n + 1);
  }, []);

  const { receiving } = useWedgeBurst({
    enabled: open && !manualMode && !busy,
    onBurst: async (payload) => {
      const request = ++scanRequest.current;
      setError("");
      setWedgeReading(true);
      try {
        const { data } = await api.post("/aadhaar/decode", { payload });
        if (request !== scanRequest.current) return;
        if (data.outcome === "card") {
          onScan(data.data, payload);
        } else {
          setError(data.message || "Could not read that card. Scan it again.");
          onFailure(data.outcome);
        }
      } catch (err) {
        if (request !== scanRequest.current) return;
        setError(formatApiError(err));
        onFailure("error");
      } finally {
        if (request === scanRequest.current) setWedgeReading(false);
      }
    },
    onInterrupted: () => setError("The USB scan was cut off. Scan the card again."),
  });

  const manualAllowed = !scanned && failures >= 3;
  const showForm = scanned || manualMode;
  const canSubmit = !busy && Boolean(form.full_name) && Boolean(dayId) && (scanned || Boolean(manualReason.trim()));
  const locked = (field) => scanned && form[field] !== "" && form[field] != null;
  const setField = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true); setError("");
    try {
      const reg = await registerPatient({
        form,
        qrPayload,
        dayId,
        reqId,
        manualReason: manualReason.trim(),
        failedAttempts: failures,
      });
      setBanner(`Registered #${reg.reg_no} — ${reg.full_name}. SMS sent.`);
      onRegistered?.(reg);
      onClose(); onDone();
    } catch (err) {
      setError(registrationError(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Registration" size="lg">
      <div className="space-y-4">
        <AadhaarScanner onScanned={onScan} onFailure={onFailure} disabled={busy || manualMode}
          onCaptureStart={() => { scanRequest.current += 1; setWedgeReading(false); setQrPayload(""); setForm((prev) => ({ ...EMPTY_REG_FORM, phone: prev.phone })); }} />
        {(receiving || wedgeReading) && (
          <div role="status" aria-live="polite" className="flex items-center gap-2 min-h-[44px] font-semibold text-slate-900" data-testid="reg-wedge-status">
            <Spinner className="w-5 h-5 text-emerald-700" />
            {receiving ? "Receiving from the USB scanner…" : "Reading the card…"}
          </div>
        )}
        {manualAllowed && (
          <Button type="button" variant="outline" disabled={busy} data-testid="reg-manual-toggle" onClick={() => {
            setQrPayload("");
            setManualMode(!manualMode);
          }}>{manualMode ? "Use scanner" : "Enter details manually"}</Button>
        )}
        {manualAllowed && (
          <p className="text-sm text-slate-700" data-testid="manual-attempt-count">
            Camera attempts failed: {failures}. Manual entry is unverified. तीन असफल कोशिशों के बाद ही मैनुअल एंट्री खुलती है।
          </p>
        )}

        {showForm && (
          <form id="register-form" onSubmit={submit} className="space-y-4">
            {!scanned && (
              <>
                <p className="text-sm font-semibold text-amber-800" data-testid="manual-entry-note">Manual entry</p>
                <Field label="Reason" required>
                  <Input value={manualReason} onChange={(e) => setManualReason(e.target.value)} data-testid="manual-reason-input" />
                </Field>
              </>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Full name" required>
                <Input value={form.full_name} onChange={setField("full_name")} readOnly={locked("full_name")} className={locked("full_name") ? "bg-slate-100" : ""} autoComplete="off" data-testid="reg-fullname-input" />
              </Field>
              <Field label="Age" required>
                <Input type="number" inputMode="numeric" value={form.age} onChange={setField("age")} readOnly={locked("age")} className={locked("age") ? "bg-slate-100" : ""} data-testid="reg-age-input" />
              </Field>
              <Field label="Gender">
                <Select value={form.gender} onChange={setField("gender")} disabled={locked("gender")} data-testid="reg-gender-select">
                  <option value="">—</option><option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
                </Select>
              </Field>
              <Field label="Phone (household)" required hint="10-digit mobile">
                <Input value={form.phone} onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value.replace(/\D/g, "").slice(0, 10) }))} inputMode="numeric" autoComplete="tel" data-testid="reg-phone-input" />
              </Field>
              <Field label="Aadhaar last-4">
                <Input value={form.aadhaar_last4} onChange={setField("aadhaar_last4")} readOnly={locked("aadhaar_last4")} className={locked("aadhaar_last4") ? "bg-slate-100" : ""} inputMode="numeric" maxLength={4} data-testid="reg-last4-input" />
              </Field>
              <Field label="Camp day">
                <Select value={dayId} onChange={(e) => setDayId(e.target.value)} data-testid="reg-day-select">
                  {days.map((d) => <option key={d.id} value={d.id}>{displayDate(d.day_date)}{d.is_today ? " (today)" : ""}</option>)}
                </Select>
              </Field>
            </div>
            <Field label="Address">
              <Input value={form.address} onChange={setField("address")} readOnly={locked("address")} className={locked("address") ? "bg-slate-100" : ""} data-testid="reg-address-input" />
            </Field>
          </form>
        )}

        <Alert>{error}</Alert>

        {showForm && (
          <div className="flex gap-2 justify-end pt-1">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" form="register-form" disabled={!canSubmit} data-testid="patient-register-submit">
              {busy ? "Registering…" : "Register"}
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
