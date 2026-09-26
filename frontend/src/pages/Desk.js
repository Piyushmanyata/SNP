import React, { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import AadhaarScanner from "../components/AadhaarScanner";
import { useWedgeBurst } from "../components/aadhaar";
import { ScanOutcome, MismatchReview } from "../components/desk/ScanOutcome";
import { PaperCheck } from "../components/desk/PaperCheck";
import { PendingStat } from "../components/desk/Pending";
import { Lookalikes } from "../components/desk/Lookalikes";
import { EMPTY_REASON, ManualReason, cardInHand, reasonBody, reasonReady } from "../components/desk/ManualReason";
import { alreadyPrintedLine, printedLine } from "../components/desk/printed";
import { PrescriptionSheet } from "../components/print/PrescriptionSheet";
import { printDocument, IMAGE_WAIT_MS } from "../lib/printJob";
import { loadLogos } from "../lib/logoCache";
import { PhoneInput } from "../components/PhoneInput";
import { v4 } from "../lib/uuid";
import { normalizePhone } from "../lib/phone";
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
const REFRESH_MS = 30000;
const REQUEST_CONFLICT = "REGISTRATION_REQUEST_CONFLICT";

function digitsOnly(value, max) {
  return value.replace(/\D/g, "").slice(0, max);
}

function hasAge(age) {
  return String(age ?? "") !== "";
}

function registrationError(err) {
  const payload = errorPayload(err);
  if (payload?.code === "DUPLICATE_IN_CAMP") {
    return `Already registered as #${payload.registration.reg_no}. Find them below and print.`;
  }
  if (payload?.code === "AMBIGUOUS_MANUAL_ENTRY") {
    const nos = (payload.registrations || []).map((r) => `#${r.reg_no}`).join(", ");
    return `Multiple Manual entries match (${nos}). Scan the card at the door to pick one.`;
  }
  if (payload?.code === REQUEST_CONFLICT) return "Saved earlier. Search for the patient.";
  return formatApiError(err);
}

function logosWithin(campId) {
  let timer;
  return Promise.race([
    loadLogos(campId).catch(() => []),
    new Promise((resolve) => { timer = setTimeout(() => resolve([]), IMAGE_WAIT_MS); }),
  ]).finally(() => clearTimeout(timer));
}

async function printPrescription(rx) {
  const logos = await logosWithin(rx.camp_id);
  await printDocument(<PrescriptionSheet rx={rx} logos={logos} />, { pageSize: "A4" });
}

async function registerPatient({ form, qrPayload, dayId, reqId, reason, atDoor, reviewConfirmedId, differentPerson }) {
  const scanned = Boolean(qrPayload);
  const manual = scanned ? { code: null, note: null } : reasonBody(reason);
  const { data } = await api.post("/register", {
    full_name: form.full_name,
    age: hasAge(form.age) ? Number(form.age) : null,
    phone: normalizePhone(form.phone),
    gender: form.gender || null,
    address: form.address || null,
    aadhaar_last4: form.aadhaar_last4 || null,
    dob: form.dob || null,
    aadhaar_scanned: scanned,
    qr_payload: qrPayload || null,
    camp_day_id: dayId,
    registration_request_id: reqId,
    manual_reason: manual.code,
    manual_note: manual.note,
    at_door: Boolean(atDoor) && !scanned,
    review_confirmed_id: reviewConfirmedId || null,
    different_person: Boolean(differentPerson),
  });
  return data;
}

export default function Desk() {
  const { user } = useAuth();
  const [kpi, setKpi] = useState(null);
  const [loadErr, setLoadErr] = useState("");
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const [regMode, setRegMode] = useState("");
  const [scanResult, setScanResult] = useState(null);
  const [scanPayload, setScanPayload] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState(null);
  const [findVal, setFindVal] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [banner, setBanner] = useState("");
  const [error, setError] = useState("");
  const [doorPhone, setDoorPhone] = useState("");
  const walkAttempt = useRef({ key: "", reqId: "", patientId: "" });
  const [scanning, setScanning] = useState(false);
  const findSequence = useRef(0);
  const loadSequence = useRef(0);
  const [preRegPayload, setPreRegPayload] = useState("");
  const [paperCheck, setPaperCheck] = useState(null);
  const [printNote, setPrintNote] = useState("");
  const [logoState, setLogoState] = useState("loading");
  const printing = useRef(false);
  const focusUsbBox = useRef(false);
  const [printingOpen, setPrintingOpen] = useState(false);
  const [operatingDayId, setOperatingDayId] = useState("");
  const noCamp = !camp;

  const load = useCallback(async () => {
    const request = ++loadSequence.current;
    try {
      const [k, a] = await Promise.all([api.get("/kpis"), api.get("/camps/active")]);
      if (request !== loadSequence.current) return;
      setLoadErr("");
      setKpi(k.data);
      setCamp(a.data.camp);
      if (a.data.camp) {
        loadLogos(a.data.camp.id).then(() => setLogoState("ready"), () => setLogoState("failed"));
      }
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
      if (request === loadSequence.current) setLoadErr(formatApiError(e));
    }
  }, []);

  useEffect(() => {
    load();
    const refresh = () => { if (!document.hidden) load(); };
    const timer = setInterval(refresh, REFRESH_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);
  useEffect(() => () => { findSequence.current += 1; }, []);

  const countRegistration = useCallback((data) => {
    if (data.created) setKpi((k) => k && { ...k, registered: k.registered + 1 });
  }, []);

  const clearScan = useCallback(() => { setScanResult(null); setScanPayload(""); }, []);
  const abandonScan = useCallback(() => {
    findSequence.current += 1;
    clearScan();
    setDoorPhone("");
    setScanning(false);
  }, [clearScan]);

  const resolveDoorScan = useCallback(async (payload) => {
    const request = ++findSequence.current;
    setBanner(""); setError(""); setSearchResults(null); setFound(null); setPaperCheck(null);
    setRegMode((mode) => (mode === "door" ? "" : mode));
    clearScan();
    setDoorPhone("");
    setScanPayload(payload);
    setScanning(true);
    try {
      const { data } = await api.post("/desk/scan", { payload });
      if (request !== findSequence.current) return { outcome: "card", quiet: true, superseded: true };
      setScanResult(data);
      if (data.outcome === "arrived") {
        const extra = data.overwritten ? " (card details updated)" : "";
        setBanner(`Arrived: #${data.registration.reg_no} — ${data.registration.full_name}${extra}`);
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
  }, [clearScan]);

  const confirmPatient = useCallback(async (patientId) => {
    if (!patientId || busy || scanning) return;
    const request = ++findSequence.current;
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/desk/scan/confirm", {
        patient_id: patientId,
        payload: scanPayload,
      });
      if (request !== findSequence.current) return;
      setScanResult(data);
      setBanner(`Arrived: #${data.registration.reg_no} — ${data.registration.full_name}`);
    } catch (err) {
      if (request === findSequence.current) setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [scanPayload, busy, scanning]);

  const confirmMismatch = useCallback(() => {
    confirmPatient(scanResult?.registration?.id);
  }, [confirmPatient, scanResult]);

  const lookupValue = useCallback(async (value, reprint = false) => {
    const request = ++findSequence.current;
    setScanning(false);
    setBanner(""); setError(""); setSearchResults(null); setFound(null); setPaperCheck(null);
    clearScan();
    try {
      const { data } = await api.post("/desk/lookup", { value });
      if (request !== findSequence.current) return false;
      setFound({ reg: data.registration, reprint });
      return true;
    } catch (err) {
      if (request !== findSequence.current) return false;
      setFound(null);
      setError(formatApiError(err));
      return false;
    }
  }, [clearScan]);

  const lookupCode = useCallback((value) => lookupValue(value, false), [lookupValue]);

  const doFind = useCallback(async (e) => {
    e?.preventDefault();
    const value = findVal.trim();
    if (!value) { setSearchResults(null); return; }
    if (AADHAAR_PAYLOAD.test(value)) {
      setFindVal("");
      if (!printingOpen) {
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
      if (await lookupValue(value, /^\d+$/.test(value))) setFindVal("");
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
  }, [findVal, lookupValue, clearScan, printingOpen, resolveDoorScan]);

  const print = useCallback(async (reg, known) => {
    if (printing.current) return;
    printing.current = true;
    const request = findSequence.current;
    setError(""); setPrintNote("");
    try {
      let rx = known;
      if (!reg.arrived_at) rx = (await api.post(`/desk/arrive/${reg.id}`)).data.prescription;
      if (!rx) rx = (await api.get(`/desk/print/${reg.id}`)).data.prescription;
      if (request !== findSequence.current) return;
      await printPrescription(rx);
      if (request === findSequence.current) setPaperCheck({ reg, rx, request, busy: false, error: "" });
    } catch (err) {
      if (request === findSequence.current) setError(formatApiError(err));
    } finally {
      printing.current = false;
    }
  }, []);

  const printScanned = useCallback((reg) => print(reg, scanResult?.prescription), [print, scanResult]);

  const confirmPaper = useCallback(async () => {
    const check = paperCheck;
    if (check.request !== findSequence.current) {
      setPaperCheck(null);
      return;
    }
    setPaperCheck({ ...check, busy: true, error: "" });
    try {
      const { data } = await api.post(`/desk/print/${check.reg.id}`);
      setPaperCheck(null);
      if (check.request !== findSequence.current) return;
      findSequence.current += 1;
      clearScan();
      setFound(null);
      setBanner(`Printed #${data.registration.reg_no} — ${data.registration.full_name}. Next patient.`);
      focusUsbBox.current = true;
    } catch (err) {
      setPaperCheck({ ...check, busy: false, error: formatApiError(err) });
    }
  }, [paperCheck, clearScan]);

  const dismissPaper = useCallback((note) => {
    setPaperCheck(null);
    setScanResult((result) => result && { ...result, prescription: null });
    setPrintNote(note);
  }, []);

  const printAgain = useCallback(() => {
    const check = paperCheck;
    dismissPaper("");
    print(check.reg);
  }, [paperCheck, dismissPaper, print]);

  useEffect(() => {
    if (paperCheck || !focusUsbBox.current) return;
    focusUsbBox.current = false;
    document.querySelector("[data-usb-box]")?.focus();
  }, [paperCheck]);

  const noCardPrint = useCallback(async (reg, reason) => {
    setError("");
    try {
      const { data } = await api.post("/desk/no-card", { patient_id: reg.id, reason: reason.code, note: reasonBody(reason).note });
      const released = data.registration;
      setFound((current) => (current?.reg.id === released.id ? { ...current, reg: released } : current));
      setSearchResults((current) => current && current.map((row) => (row.id === released.id ? released : row)));
      await print(released);
      return true;
    } catch (err) {
      setError(formatApiError(err));
      return false;
    }
  }, [print]);

  const openPreReg = useCallback(() => { setRegMode("prereg"); }, []);
  const openDoorManual = useCallback(() => { setRegMode("door"); }, []);
  const closeRegistration = useCallback(() => { setRegMode(""); setPreRegPayload(""); }, []);
  const showRegistered = useCallback((reg) => { setFound({ reg, reprint: true }); }, []);

  useWedgeBurst({
    enabled: !printingOpen && !regMode && !noCamp,
    onBurst: (payload) => {
      setPreRegPayload(payload);
      setRegMode("prereg");
    },
  });

  const submitDoorWalkIn = useCallback(async () => {
    if (!scanResult?.card) return;
    if (!operatingDayId) {
      setError("No operating camp day. Use Pre-registration.");
      return;
    }
    const request = ++findSequence.current;
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
        countRegistration(created);
        patientId = created.registration.id;
        walkAttempt.current.patientId = patientId;
      }
      const arrived = await api.post(`/desk/arrive/${patientId}`);
      walkAttempt.current = { key: "", reqId: "", patientId: "" };
      if (request !== findSequence.current) return;
      const reg = arrived.data.registration;
      setScanResult({ outcome: "arrived", registration: reg, prescription: arrived.data.prescription });
      setScanPayload("");
      setBanner(`Registered and arrived: #${reg.reg_no} — ${reg.full_name}`);
      setDoorPhone("");
    } catch (err) {
      if (request !== findSequence.current) return;
      if (errorPayload(err)?.code === REQUEST_CONFLICT) walkAttempt.current = { key, reqId: v4(), patientId: "" };
      setError(registrationError(err));
    } finally { setBusy(false); }
  }, [scanResult, scanPayload, operatingDayId, doorPhone, countRegistration]);

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

      <div className={`grid gap-2 sm:gap-3 mb-5 ${printingOpen ? "grid-cols-3" : "grid-cols-1"}`}>
        <Stat label="Registered" value={kpi?.registered ?? "—"} testid="kpi-registered-count" />
        {printingOpen && <Stat label="Seen" value={kpi?.seen ?? "—"} tone="emerald" testid="kpi-seen-count" />}
        {printingOpen && <PendingStat value={kpi?.pending ?? "—"} />}
      </div>

      {!printingOpen && (
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

      {printingOpen && <DoorScanCard
        noCamp={noCamp}
        resolveDoorScan={resolveDoorScan}
        onPatientCode={lookupCode}
        onManual={openDoorManual}
        error={error}
        banner={banner}
        scanResult={scanResult}
        busy={busy}
        print={printScanned}
        confirmMismatch={confirmMismatch}
        confirmPatient={confirmPatient}
        doorPhone={doorPhone}
        setDoorPhone={setDoorPhone}
        submitDoorWalkIn={submitDoorWalkIn}
        scanning={scanning}
        clearScan={abandonScan}
      />}

      {printNote && <Alert tone="amber" className="mb-5">{printNote}</Alert>}
      {camp && logoState !== "ready" && (
        <p role="status" className="mb-5 text-sm font-semibold text-amber-800" data-testid="logo-status">
          {logoState === "loading"
            ? "Sponsor logos loading…"
            : "Sponsor logos unavailable. Prescriptions print without them."}
        </p>
      )}

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
            <PatientRow p={found.reg} onPrint={print} printingOpen={printingOpen} reprint={found.reprint} onNoCard={noCardPrint} />
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
                <PatientRow key={p.id} p={p} onPrint={print} printingOpen={printingOpen} reprint onNoCard={noCardPrint} />
              ))}
            </div>
          </div>
        )}
      </Card>

      <PaperCheck
        check={paperCheck}
        onConfirm={confirmPaper}
        onPrintAgain={printAgain}
        onProblem={() => dismissPaper("Printer problem. Nothing was recorded. Fix the printer, then press Print again.")}
        onClose={() => dismissPaper("Not recorded as printed. Press Print again when the paper is ready.")}
      />

      <RegisterModal
        open={Boolean(regMode)}
        atDoor={regMode === "door"}
        doorDayId={operatingDayId}
        onClose={closeRegistration}
        initialPayload={preRegPayload}
        days={days}
        onDone={countRegistration}
        setBanner={setBanner}
        onRegistered={showRegistered}
      />
    </Layout>
  );
}

function DoorScanCard({
  noCamp, resolveDoorScan, onPatientCode, onManual, error, banner, scanResult, busy,
  print, confirmMismatch, confirmPatient, doorPhone, setDoorPhone, submitDoorWalkIn, scanning, clearScan,
}) {
  return (
    <Card className="mb-5" data-desk-card="scan" data-testid="desk-card-scan">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-700" />
        <h3 className="font-display font-bold text-slate-900">Scan at the door</h3>
      </div>
      <AadhaarScanner
        resolvePayload={resolveDoorScan}
        onPatientCode={onPatientCode}
        usbFirst
        disabled={noCamp}
        onCaptureStart={clearScan}
      />
      <Button variant="outline" className="mt-3" onClick={onManual} disabled={noCamp} data-testid="door-manual-button">
        <UserPlus className="w-4 h-4" /> Manual entry
      </Button>
      {scanning && (
        <div data-testid="door-scan-status" role="status" aria-live="polite" aria-atomic="true" className="flex items-center gap-2 mt-3 min-h-[44px] text-slate-900 font-semibold">
          <Spinner className="w-5 h-5 text-emerald-700" />
          <span>Reading the QR and finding the patient…</span>
        </div>
      )}
      {error && <Alert className="mt-3">{error}</Alert>}
      {banner && <Alert tone="emerald" className="mt-3">{banner}</Alert>}
      <div className="mt-3" aria-live="polite" data-testid="door-scan-outcome">
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
    </Card>
  );
}

export function PatientRow({ p, onPrint, printingOpen, reprint = false, onNoCard }) {
  const [noCard, setNoCard] = useState(null);
  const [sending, setSending] = useState(false);
  const seen = p.queue_status === "seen";
  const printed = Boolean(p.printed_at) && !seen;
  const needsDoorScan = !p.arrived_at && !p.aadhaar_scanned && !p.no_card_print;
  const windowShut = !printingOpen && !p.printed_at;
  const canPrint = !seen && !needsDoorScan && !windowShut && (!printed || reprint);
  const submitNoCard = async (e) => {
    e.preventDefault();
    setSending(true);
    if (await onNoCard(p, noCard)) setNoCard(null);
    setSending(false);
  };
  return (
    <div
      id={`row-${p.id}`}
      className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-slate-200"
      data-testid={`patient-row-${p.reg_no}`}
    >
      <span className="font-mono font-bold text-emerald-700 w-14 shrink-0">#{p.reg_no}</span>
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
      {!needsDoorScan && !seen && windowShut && (
        <span className="text-xs text-slate-600" data-testid={`print-window-closed-${p.reg_no}`}>
          The print window is closed.
        </span>
      )}
      {printed && reprint && (
        <span className="text-xs text-slate-600" data-testid={`printed-by-${p.reg_no}`}>{printedLine(p)}</span>
      )}
      {printed && !reprint && (
        <span className="text-xs font-semibold text-amber-800" data-testid={`already-printed-${p.reg_no}`}>
          {alreadyPrintedLine(p)}
        </span>
      )}
      <div className="flex gap-1.5 ml-auto">
        {canPrint && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onPrint(p)}
            data-testid={`${printed ? "reprint" : "print"}-button-${p.reg_no}`}
          >
            <Printer className="w-4 h-4" /> {printed ? "Reprint" : "Print"}
          </Button>
        )}
        {needsDoorScan && printingOpen && !noCard && (
          <Button size="sm" variant="outline" onClick={() => setNoCard(EMPTY_REASON)} data-testid={`no-card-${p.reg_no}`}>
            No-card print
          </Button>
        )}
      </div>
      {noCard && (
        <form onSubmit={submitNoCard} className="w-full space-y-2">
          <ManualReason reason={noCard} onChange={setNoCard} testid={`no-card-reason-${p.reg_no}`} />
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={sending || !reasonReady(noCard)} data-testid={`no-card-submit-${p.reg_no}`}>
              <Printer className="w-4 h-4" /> Print
            </Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => setNoCard(null)}>Cancel</Button>
          </div>
        </form>
      )}
    </div>
  );
}

export function RegisterModal({ open, atDoor = false, doorDayId, onClose, initialPayload, days, onDone, setBanner, onRegistered }) {
  const [form, setForm] = useState(EMPTY_REG_FORM);
  const [qrPayload, setQrPayload] = useState("");
  const [manualMode, setManualMode] = useState(false);
  const [dayId, setDayId] = useState("");
  const scanRequest = useRef(0);
  const phoneRef = useRef(null);
  const [reason, setReason] = useState(EMPTY_REASON);
  const [error, setError] = useState("");
  const [review, setReview] = useState(null);
  const [lookalikeRows, setLookalikeRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const [wedgeReading, setWedgeReading] = useState(false);
  const [reqId, setReqId] = useState(v4());
  const prevOpenRef = useRef(false);

  const reset = useCallback(() => {
    setForm(EMPTY_REG_FORM);
    setQrPayload("");
    setManualMode(atDoor);
    setReason(EMPTY_REASON);
    setError("");
    setReview(null);
    setLookalikeRows(null);
    setReqId(v4());
  }, [atDoor]);

  useEffect(() => {
    scanRequest.current += 1;
    setWedgeReading(false);
    return () => { scanRequest.current += 1; };
  }, [open, manualMode]);

  useEffect(() => {
    if (open && !prevOpenRef.current) {
      reset();
      const today = days.find((d) => d.is_today);
      setDayId(today ? today.id : (days[0]?.id || ""));
    } else if (open && !dayId && days.length > 0) {
      const today = days.find((d) => d.is_today);
      setDayId(today ? today.id : (days[0]?.id || ""));
    }
    prevOpenRef.current = open;
  }, [open, days, dayId, reset]);

  useEffect(() => {
    if (qrPayload) phoneRef.current?.focus();
  }, [qrPayload]);

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
    setReview(null);
    setReqId(v4());
  }, []);

  const readCard = useCallback(async (payload) => {
    const request = ++scanRequest.current;
    setError("");
    setWedgeReading(true);
    try {
      const { data } = await api.post("/aadhaar/decode", { payload });
      if (request !== scanRequest.current) return;
      if (data.outcome === "card") onScan(data.data, payload);
      else setError(data.message || "Could not read that card. Scan it again.");
    } catch (err) {
      if (request !== scanRequest.current) return;
      setError(formatApiError(err));
    } finally {
      if (request === scanRequest.current) setWedgeReading(false);
    }
  }, [onScan]);

  useEffect(() => {
    if (open && initialPayload) readCard(initialPayload);
  }, [open, initialPayload, readCard]);

  const { receiving } = useWedgeBurst({
    enabled: open && !atDoor && !manualMode && !busy,
    onBurst: readCard,
    onInterrupted: () => setError("The USB scan was cut off. Scan the card again."),
  });

  const bookedDay = atDoor ? doorDayId : dayId;
  const showForm = scanned || manualMode;
  const dirty = showForm && (Object.values(form).some((value) => String(value ?? "") !== "") || Boolean(reason.code));
  const manualReady = reasonReady(reason) && Boolean(form.gender)
    && (!cardInHand(reason) || String(form.aadhaar_last4 ?? "").length === 4);
  const canSubmit = !busy && Boolean(form.full_name) && hasAge(form.age) && Boolean(normalizePhone(form.phone))
    && Boolean(bookedDay) && (scanned || manualReady);
  const locked = (field) => scanned && form[field] !== "" && form[field] != null;
  const edit = (change) => { setLookalikeRows(null); setForm(change); };
  const setField = (field) => (e) => edit((prev) => ({ ...prev, [field]: e.target.value }));
  const setDigits = (field, max) => (e) => edit((prev) => ({ ...prev, [field]: digitsOnly(e.target.value, max) }));
  const chooseReason = (next) => { setLookalikeRows(null); setReason(next); };
  const openLookalike = (reg) => { onRegistered?.(reg); onClose(); };

  const save = async ({ next = false, reviewConfirmedId = null, differentPerson = false } = {}) => {
    if (!canSubmit) return;
    setBusy(true); setError("");
    try {
      const data = await registerPatient({
        form,
        qrPayload,
        dayId: bookedDay,
        reqId,
        reason,
        atDoor,
        reviewConfirmedId,
        differentPerson,
      });
      const reg = data.registration;
      setBanner(atDoor
        ? `Registered and arrived: #${reg.reg_no} — ${reg.full_name}`
        : `Registered #${reg.reg_no} — ${reg.full_name}. SMS sent.`);
      onRegistered?.(reg);
      onDone(data);
      if (next) reset();
      else onClose();
    } catch (err) {
      const payload = errorPayload(err);
      if (payload?.code === "MISMATCH_REVIEW_REQUIRED") {
        setReview(payload);
        return;
      }
      if (payload?.code === "LOOKALIKES") {
        setLookalikeRows(payload.registrations);
        return;
      }
      if (payload?.code === REQUEST_CONFLICT) setReqId(v4());
      setError(registrationError(err));
    } finally { setBusy(false); }
  };

  const submit = (e) => {
    e.preventDefault();
    save();
  };

  return (
    <Modal open={open} onClose={onClose} dirty={dirty} title={atDoor ? "Manual entry" : "New Registration"} size="lg">
      <div className="space-y-4">
        {!atDoor && (
          <AadhaarScanner onScanned={onScan} disabled={busy || manualMode}
            onCaptureStart={() => { scanRequest.current += 1; setWedgeReading(false); setQrPayload(""); setReview(null); setForm((prev) => ({ ...EMPTY_REG_FORM, phone: prev.phone })); }} />
        )}
        {(receiving || wedgeReading) && (
          <div role="status" aria-live="polite" className="flex items-center gap-2 min-h-[44px] font-semibold text-slate-900" data-testid="reg-wedge-status">
            <Spinner className="w-5 h-5 text-emerald-700" />
            {receiving ? "Receiving from the USB scanner…" : "Reading the card…"}
          </div>
        )}
        {!atDoor && !scanned && (
          <Button type="button" variant="outline" disabled={busy} data-testid="reg-manual-toggle" onClick={() => setManualMode(!manualMode)}>
            {manualMode ? "Use scanner" : <><UserPlus className="w-4 h-4" /> Manual entry</>}
          </Button>
        )}

        {showForm && (
          <form id="register-form" onSubmit={submit} className="space-y-4">
            {!scanned && <ManualReason reason={reason} onChange={chooseReason} />}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Full name" required>
                <Input value={form.full_name} onChange={setField("full_name")} readOnly={locked("full_name")} className={locked("full_name") ? "bg-slate-100" : ""} autoComplete="off" maxLength={100} data-testid="reg-fullname-input" />
              </Field>
              <Field label="Age" required>
                <Input type="text" inputMode="numeric" value={form.age} onChange={setDigits("age", 3)} readOnly={locked("age")} className={locked("age") ? "bg-slate-100" : ""} data-testid="reg-age-input" />
              </Field>
              <Field label="Gender" required={!scanned}>
                <Select value={form.gender ?? ""} onChange={setField("gender")} disabled={locked("gender")} data-testid="reg-gender-select">
                  <option value="">—</option><option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
                </Select>
              </Field>
              <Field label="Phone (household)" required hint="10-digit mobile">
                <PhoneInput ref={phoneRef} value={form.phone} onChange={(phone) => edit((prev) => ({ ...prev, phone }))} data-testid="reg-phone-input" />
              </Field>
              <Field label="Aadhaar last-4" required={!scanned && cardInHand(reason)}>
                <Input value={form.aadhaar_last4 ?? ""} onChange={setDigits("aadhaar_last4", 4)} readOnly={locked("aadhaar_last4")} className={locked("aadhaar_last4") ? "bg-slate-100" : ""} inputMode="numeric" data-testid="reg-last4-input" />
              </Field>
              {!atDoor && (
                <Field label="Camp day">
                  <Select value={dayId} onChange={(e) => setDayId(e.target.value)} data-testid="reg-day-select">
                    {days.map((d) => <option key={d.id} value={d.id}>{displayDate(d.day_date)}{d.is_today ? " (today)" : ""}</option>)}
                  </Select>
                </Field>
              )}
            </div>
            <Field label="Address">
              <Input value={form.address} onChange={setField("address")} readOnly={locked("address")} className={locked("address") ? "bg-slate-100" : ""} maxLength={300} data-testid="reg-address-input" />
            </Field>
          </form>
        )}

        {review && (
          <MismatchReview
            registration={review.registration}
            diff={review.diff}
            busy={busy}
            onConfirm={() => save({ reviewConfirmedId: review.registration.id })}
          />
        )}

        {lookalikeRows && (
          <Lookalikes rows={lookalikeRows} busy={busy} onOpen={openLookalike} onDifferent={() => save({ differentPerson: true })} />
        )}

        <Alert>{error}</Alert>

        {showForm && (
          <div className="flex flex-wrap gap-2 justify-end pt-1">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            {!review && !lookalikeRows && (
              <>
                {!atDoor && (
                  <Button type="button" variant="outline" disabled={!canSubmit} onClick={() => save({ next: true })} data-testid="patient-register-next">
                    Register &amp; next
                  </Button>
                )}
                <Button type="submit" form="register-form" disabled={!canSubmit} data-testid="patient-register-submit">
                  {busy ? "Registering…" : "Register"}
                </Button>
              </>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
