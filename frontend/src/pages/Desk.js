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
import { EMPTY_REASON, ManualReason, cardInHand, reasonReady } from "../components/desk/ManualReason";
import { REQUEST_CONFLICT, hasAge, registerPatient, registrationError } from "../components/desk/register";
import { useDeskSession } from "../components/desk/useDeskSession";
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

const REFRESH_MS = 30000;

function digitsOnly(value, max) {
  return value.replace(/\D/g, "").slice(0, max);
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

export default function Desk() {
  const { user } = useAuth();
  const [kpi, setKpi] = useState(null);
  const [loadErr, setLoadErr] = useState("");
  const [days, setDays] = useState([]);
  const [camp, setCamp] = useState(null);
  const loadSequence = useRef(0);
  const [logoState, setLogoState] = useState("loading");
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

  const countRegistration = useCallback((data) => {
    if (data.created) setKpi((k) => k && { ...k, registered: k.registered + 1 });
  }, []);

  const [state, actions] = useDeskSession({
    printPrescription, onCreated: countRegistration, printingOpen, operatingDayId,
  });
  const { regMode, found, findVal, searchResults, banner, error, printNote } = state;

  useWedgeBurst({
    enabled: !printingOpen && !regMode && !noCamp,
    onBurst: actions.preRegBurst,
  });

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
            <Button size="lg" onClick={actions.openPreReg} disabled={noCamp} data-testid="new-registration-button">
              <UserPlus className="w-5 h-5" /> New Registration
            </Button>
          </Card>
          {error && <Alert className="mb-5">{error}</Alert>}
          {banner && <Alert tone="emerald" className="mb-5">{banner}</Alert>}
        </>
      )}

      {printingOpen && <DoorScanCard noCamp={noCamp} state={state} actions={actions} />}

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
        <form onSubmit={actions.find} className="flex gap-2">
          <Input value={findVal} onChange={(e) => actions.setFindVal(e.target.value)}
            aria-label="Registration number or name" autoComplete="off" enterKeyHint="search"
            placeholder="Registration number or name" data-testid="desk-find-input" />
          <Button type="submit" variant="secondary" aria-label="Find patient" data-testid="desk-find-button"><Search className="w-5 h-5" /></Button>
        </form>

        {found && (
          <div className="mt-4" data-testid="desk-found-patient">
            <PatientRow p={found.reg} onPrint={actions.print} printingOpen={printingOpen} reprint={found.reprint} onNoCard={actions.noCardPrint} />
          </div>
        )}

        {searchResults && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-semibold text-slate-700">Search results ({searchResults.length})</p>
              <Button variant="ghost" size="sm" onClick={actions.clearSearch}>Clear</Button>
            </div>
            <div className="space-y-2" data-testid="desk-search-results">
              {searchResults.map((p) => (
                <PatientRow key={p.id} p={p} onPrint={actions.print} printingOpen={printingOpen} reprint onNoCard={actions.noCardPrint} />
              ))}
            </div>
          </div>
        )}
      </Card>

      <PaperCheck
        check={state.paperCheck}
        onConfirm={actions.confirmPaper}
        onPrintAgain={actions.printAgain}
        onProblem={actions.printerProblem}
        onClose={actions.closePaper}
      />

      <RegisterModal
        open={Boolean(regMode)}
        atDoor={regMode === "door"}
        doorDayId={operatingDayId}
        onClose={actions.closeRegistration}
        initialPayload={state.preRegPayload}
        days={days}
        onDone={countRegistration}
        setBanner={actions.showBanner}
        onRegistered={actions.showRegistered}
      />
    </Layout>
  );
}

function DoorScanCard({ noCamp, state, actions }) {
  return (
    <Card className="mb-5" data-desk-card="scan" data-testid="desk-card-scan">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-700" />
        <h3 className="font-display font-bold text-slate-900">Scan at the door</h3>
      </div>
      <AadhaarScanner
        resolvePayload={actions.resolveDoorScan}
        onPatientCode={actions.lookupCode}
        usbFirst
        disabled={noCamp}
        onCaptureStart={actions.abandonScan}
      />
      <Button variant="outline" className="mt-3" onClick={actions.openDoorManual} disabled={noCamp} data-testid="door-manual-button">
        <UserPlus className="w-4 h-4" /> Manual entry
      </Button>
      {state.scanning && (
        <div data-testid="door-scan-status" role="status" aria-live="polite" aria-atomic="true" className="flex items-center gap-2 mt-3 min-h-[44px] text-slate-900 font-semibold">
          <Spinner className="w-5 h-5 text-emerald-700" />
          <span>Reading the QR and finding the patient…</span>
        </div>
      )}
      {state.error && <Alert className="mt-3">{state.error}</Alert>}
      {state.banner && <Alert tone="emerald" className="mt-3">{state.banner}</Alert>}
      <div className="mt-3" aria-live="polite" data-testid="door-scan-outcome">
        <ScanOutcome
          result={state.scanResult}
          busy={state.busy || state.scanning}
          onPrint={actions.printScanned}
          onConfirm={actions.confirmMismatch}
          phone={state.doorPhone}
          setPhone={actions.setDoorPhone}
          onWalkIn={actions.submitDoorWalkIn}
          onChoose={actions.confirmPatient}
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
  const needsDoorScan = !p.arrived_at && !p.no_card_print;
  const windowShut = !printingOpen && !p.printed_at;
  const canPrint = !seen && !needsDoorScan && !windowShut && (!printed || reprint);
  const askLast4 = Boolean(noCard) && Boolean(p.aadhaar_scanned || p.person_id) && cardInHand(noCard);
  const noCardReady = Boolean(noCard) && reasonReady(noCard) && (!askLast4 || String(noCard.last4 ?? "").length === 4);
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
          Scan their Aadhaar card, or record a No-card print
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
          <>
            <Button size="sm" variant="outline" onClick={() => document.querySelector("[data-usb-box]")?.focus()} data-testid={`scan-card-${p.reg_no}`}>
              <ScanLine className="w-4 h-4" /> Scan the card
            </Button>
            <Button size="sm" variant="outline" onClick={() => setNoCard(EMPTY_REASON)} data-testid={`no-card-${p.reg_no}`}>
              No-card print
            </Button>
          </>
        )}
      </div>
      {noCard && (
        <form onSubmit={submitNoCard} className="w-full space-y-2">
          <ManualReason reason={noCard} onChange={setNoCard} testid={`no-card-reason-${p.reg_no}`} />
          {askLast4 && (
            <Field label="Last 4 digits on the card" required>
              <Input
                inputMode="numeric"
                value={noCard.last4 ?? ""}
                onChange={(e) => setNoCard({ ...noCard, last4: digitsOnly(e.target.value, 4) })}
                data-testid={`no-card-last4-${p.reg_no}`}
              />
            </Field>
          )}
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={sending || !noCardReady} data-testid={`no-card-submit-${p.reg_no}`}>
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
