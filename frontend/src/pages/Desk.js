import React, { useEffect, useState, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import AadhaarScanner from "../components/AadhaarScanner";
import { useWedgeBurst } from "../components/aadhaar";
import { ScanOutcome } from "../components/desk/ScanOutcome";
import { v4 } from "../lib/uuid";
import {
  Button, Card, Input, Field, Alert, Modal, Stat, StatusBadge, Badge, ErrorCard, Spinner,
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
  const [lookupVal, setLookupVal] = useState("");
  const [searchVal, setSearchVal] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [banner, setBanner] = useState("");
  const [error, setError] = useState("");
  const [doorFailures, setDoorFailures] = useState(0);
  const [doorPhone, setDoorPhone] = useState("");
  const [doorForm, setDoorForm] = useState(EMPTY_REG_FORM);
  const [doorReqId, setDoorReqId] = useState(v4());
  const [scanning, setScanning] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const lastBurstRef = useRef({ payload: "", at: 0 });
  const scanSequence = useRef(0);
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
  useEffect(() => () => { scanSequence.current += 1; }, []);

  const onDoorFailure = useCallback((outcome) => {
    if (outcome === "garbage" || outcome === "not-aadhaar") {
      setDoorFailures((n) => n + 1);
    }
  }, []);


  const fillDoorForm = useCallback((card) => {
    if (!card) return;
    setDoorForm({
      full_name: card.full_name || "",
      age: card.age ?? "",
      phone: doorPhone,
      gender: card.gender || "",
      address: card.address || "",
      aadhaar_last4: card.aadhaar_last4 || "",
      dob: card.dob || "",
    });
  }, [doorPhone]);

  const onScanned = useCallback(async (_card, payload) => {
    if (busy) return;
    const request = ++scanSequence.current;
    setManualMode(false);
    setBanner(""); setError(""); setSearchResults(null); setFound(null);
    setScanResult(null);
    fillDoorForm(_card);
    setScanPayload(payload);
    setScanning(true);
    try {
      const { data } = await api.post("/desk/scan", { payload });
      if (request !== scanSequence.current) return;
      setScanResult(data);
      if (data.card) fillDoorForm(data.card);
      if (data.outcome === "arrived") {
        setDoorFailures(0);
        const extra = data.overwritten ? " (card details updated)" : "";
        setBanner(`Checked in #${data.registration.reg_no} — ${data.registration.full_name}${extra}`);
        await load();
      }
    } catch (err) {
      if (request !== scanSequence.current) return;
      if (errorPayload(err)?.code === "NOT_A_CARD") onDoorFailure("garbage");
      setScanResult(null);
      setError(formatApiError(err));
    } finally {
      if (request === scanSequence.current) setScanning(false);
    }
  }, [load, fillDoorForm, onDoorFailure, busy]);

  const { receiving } = useWedgeBurst({
    enabled: campDayMode && !showReg && !noCamp && !busy && !scanning && !manualMode,
    onInterrupted: () => setError("Scan interrupted. Scan the card again and wait for the scanner to finish."),
    onBurst: (payload) => {
      if (payload === lastBurstRef.current.payload && Date.now() - lastBurstRef.current.at < 3000) return;
      lastBurstRef.current = { payload, at: Date.now() };
      onScanned(null, payload);
    },
  });

  const confirmMismatch = useCallback(async () => {
    if (!scanResult?.registration || busy || scanning) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/desk/scan/confirm", {
        patient_id: scanResult.registration.id,
        payload: scanPayload,
      });
      setScanResult(data);
      setBanner(`Checked in #${data.registration.reg_no} — ${data.registration.full_name}`);
      await load();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [scanResult, scanPayload, load, busy, scanning]);

  const doLookup = useCallback(async (e) => {
    e?.preventDefault();
    if (!lookupVal.trim()) return;
    setBanner(""); setError(""); setSearchResults(null);
    try {
      const { data } = await api.post("/desk/lookup", { value: lookupVal.trim() });
      setFound(data.registration);
      setLookupVal("");
    } catch (err) {
      setFound(null);
      setError(formatApiError(err));
    }
  }, [lookupVal]);

  const doSearch = useCallback(async (e) => {
    e?.preventDefault();
    if (!searchVal.trim()) { setSearchResults(null); return; }
    setError("");
    try {
      const { data } = await api.get(`/patients/search?q=${encodeURIComponent(searchVal.trim())}`);
      setSearchResults(data.results);
    } catch (err) {
      setError(formatApiError(err));
    }
  }, [searchVal]);

  const print = useCallback((reg) => navigate(`/print/prescription/${reg.id}`), [navigate]);

  const openPreReg = useCallback(() => { setShowReg(true); }, []);

  const onDoorStall = useCallback(() => {}, []);

  const submitRegister = useCallback(async ({ form, scanned, dayId, reqId, walkIn: asWalkIn }) => {
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
      manual_entry: !scanned,
    });
    let reg = data.registration;
    if (asWalkIn) {
      const arrived = await api.post(`/desk/arrive/${reg.id}`);
      reg = arrived.data.registration;
    }
    return reg;
  }, []);

  const submitDoorWalkIn = useCallback(async () => {
    if (!scanResult?.card) return;
    if (!operatingDayId) {
      setError("No operating camp day. Use Pre-registration.");
      return;
    }
    setBusy(true); setError("");
    try {
      const card = scanResult.card;
      const reg = await submitRegister({
        form: {
          full_name: card.full_name,
          age: card.age ?? "",
          phone: doorPhone,
          gender: card.gender,
          address: card.address,
          aadhaar_last4: card.aadhaar_last4,
          dob: card.dob,
        },
        scanned: true,
        dayId: operatingDayId,
        reqId: v4(),
        walkIn: true,
      });
      setScanResult(null);
      setFound(reg);
      setBanner(`Registered and checked in #${reg.reg_no} — ${reg.full_name}`);
      setDoorPhone("");
      await load();
    } catch (err) {
      const payload = errorPayload(err);
      if (payload && payload.code === "DUPLICATE_IN_CAMP") {
        setError(`Already registered as #${payload.registration.reg_no}. Check them in instead.`);
      } else {
        setError(formatApiError(err));
      }
    } finally { setBusy(false); }
  }, [scanResult, operatingDayId, doorPhone, submitRegister, load]);

  const submitDoorManual = useCallback(async () => {
    const dayId = operatingDayId || todayDay?.id || days[0]?.id;
    if (!dayId) return;
    setBusy(true); setError("");
    try {
      const asWalkIn = Boolean(printingOpen);
      const reg = await submitRegister({
        form: doorForm,
        scanned: false,
        dayId,
        reqId: doorReqId,
        walkIn: asWalkIn,
      });
      setFound(reg);
      setBanner(
        asWalkIn
          ? `Registered and checked in #${reg.reg_no} — ${reg.full_name}`
          : `Registered #${reg.reg_no} — ${reg.full_name}. SMS sent.`
      );
      setDoorFailures(0);
      setDoorForm(EMPTY_REG_FORM);
      setDoorReqId(v4());
      await load();
    } catch (err) {
      const payload = errorPayload(err);
      if (payload && payload.code === "DUPLICATE_IN_CAMP") {
        setError(`Already registered as #${payload.registration.reg_no}. Check them in instead.`);
      } else {
        setError(formatApiError(err));
      }
    } finally { setBusy(false); }
  }, [operatingDayId, printingOpen, todayDay, days, doorForm, doorReqId, submitRegister, load]);

  if (loadErr) return <Layout title="Desk"><ErrorCard message={loadErr} onRetry={load} /></Layout>;

  return (
    <Layout title="Registration Desk">
      {user?.role === "team_lead" && (
        <div className="flex flex-wrap gap-3 mb-5">
          <Link to="/team" className="min-h-[44px] flex items-center px-4 rounded-xl border border-slate-300 font-semibold text-slate-900" data-testid="desk-team-link">Team Management</Link>
          <Link to="/analytics" className="min-h-[44px] flex items-center px-4 rounded-xl border border-slate-300 font-semibold text-slate-900" data-testid="desk-analytics-link">Analytics</Link>
        </div>
      )}
      {noCamp && <Alert tone="amber" className="mb-4">No active camp. Ask an admin to activate one.</Alert>}

      <div className={`grid gap-3 mb-5 ${campDayMode ? "grid-cols-3" : "grid-cols-1"}`}>
        <Stat label="Registered" value={kpi?.registered ?? "—"} testid="kpi-registered-count" />
        {campDayMode && <Stat label="Seen" value={kpi?.seen ?? "—"} tone="emerald" testid="kpi-seen-count" />}
        {campDayMode && <Stat label="Pending" value={kpi?.pending ?? "—"} tone="amber" testid="kpi-pending-count" />}
      </div>

      {!campDayMode && (
        <Card className="mb-5" data-desk-card="prereg" data-testid="desk-card-prereg">
          <h3 className="font-display font-bold text-slate-900 mb-1">Pre-registration</h3>
          <p className="text-sm text-slate-500 mb-3">
            Books a seat and sends the patient their registration number. Nothing prints.
          </p>
          <Button size="lg" onClick={openPreReg} disabled={noCamp} data-testid="new-registration-button">
            <UserPlus className="w-5 h-5" /> New Registration
          </Button>
        </Card>
      )}

      {campDayMode && <DoorScanCard
        noCamp={noCamp}
        onScanned={onScanned}
        onDoorFailure={onDoorFailure}
        onDoorStall={onDoorStall}
        error={error}
        banner={banner}
        scanResult={scanResult}
        busy={busy}
        print={print}
        confirmMismatch={confirmMismatch}
        doorPhone={doorPhone}
        setDoorPhone={setDoorPhone}
        submitDoorWalkIn={submitDoorWalkIn}
        doorFailures={doorFailures}
        doorForm={doorForm}
        setDoorForm={setDoorForm}
        submitDoorManual={submitDoorManual}
        scanning={scanning}
        receiving={receiving}
        manualMode={manualMode}
        setManualMode={setManualMode}
        clearScan={() => setScanResult(null)}
      />}

      <Card className="mb-5" data-desk-card="find" data-testid="desk-card-find">
        <h3 className="font-display font-bold text-slate-900 mb-3">Find one patient</h3>
        <form onSubmit={doLookup} className="flex gap-2">
          <Input value={lookupVal} onChange={(e) => setLookupVal(e.target.value)}
            placeholder="Scan prescription QR or type Reg #" data-testid="desk-lookup-input" />
          <Button type="submit" variant="secondary" data-testid="desk-lookup-button"><ScanLine className="w-5 h-5" /></Button>
        </form>
        <form onSubmit={doSearch} className="flex gap-2 mt-3">
          <Input value={searchVal} onChange={(e) => setSearchVal(e.target.value)}
            placeholder="Name search (lost paper/number)" data-testid="desk-name-search-input" />
          <Button type="submit" variant="outline" data-testid="desk-name-search-button"><Search className="w-5 h-5" /></Button>
        </form>

        {found && (
          <div className="mt-4" data-testid="desk-found-patient">
            <PatientRow p={found} onPrint={print} />
          </div>
        )}

        {searchResults && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-semibold text-slate-700">Search results ({searchResults.length})</p>
              <Button variant="ghost" size="sm" onClick={() => { setSearchResults(null); setSearchVal(""); }}>Clear</Button>
            </div>
            <div className="space-y-2" data-testid="desk-search-results">
              {searchResults.map((p) => (
                <PatientRow key={p.id} p={p} onPrint={print} />
              ))}
            </div>
          </div>
        )}
      </Card>

      {!campDayMode && (
        <details className="mb-5" data-desk-card="scan" data-testid="door-scan-details">
          <summary className="cursor-pointer font-display font-bold text-slate-900 py-2 min-h-[44px]">Scan at the door</summary>
          <DoorScanCard
            noCamp={noCamp}
            onScanned={onScanned}
            onDoorFailure={onDoorFailure}
            onDoorStall={onDoorStall}
            error={error}
            banner={banner}
            scanResult={scanResult}
            busy={busy}
            print={print}
            confirmMismatch={confirmMismatch}
            doorPhone={doorPhone}
            setDoorPhone={setDoorPhone}
            submitDoorWalkIn={submitDoorWalkIn}
            doorFailures={doorFailures}
            doorForm={doorForm}
            setDoorForm={setDoorForm}
            submitDoorManual={submitDoorManual}
            scanning={scanning}
            manualMode={manualMode}
            setManualMode={setManualMode}
            clearScan={() => setScanResult(null)}
            collapsed
          />
        </details>
      )}

      <RegisterModal
        open={showReg}
        walkIn={false}
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
  noCamp, onScanned, onDoorFailure, onDoorStall, error, banner, scanResult, busy,
  print, confirmMismatch, doorPhone, setDoorPhone, submitDoorWalkIn,
  doorFailures, doorForm, setDoorForm, submitDoorManual, collapsed, scanning,
  receiving, manualMode, setManualMode, clearScan,
}) {
  const showManual = manualMode || doorFailures >= 3;
  const scanner = (
    <AadhaarScanner onScanned={onScanned} onFailure={onDoorFailure} onScanStall={onDoorStall} disabled={noCamp || busy || scanning || manualMode}
      onCaptureStart={clearScan}
      onTranscribed={(details) => {
        clearScan();
        setDoorForm({ ...EMPTY_REG_FORM, ...details, phone: doorPhone });
        setManualMode(true);
      }} />
  );
  return (
    <Card className={collapsed ? "mt-2" : "mb-5"} data-desk-card={collapsed ? undefined : "scan"} data-testid="desk-card-scan">
      {!collapsed && (
        <div className="flex items-center gap-2 mb-3">
          <ScanLine className="w-5 h-5 text-emerald-600" />
          <h3 className="font-display font-bold text-slate-900">Scan at the door</h3>
        </div>
      )}
      {collapsed ? scanner : (
        <div data-testid="wedge-panel" role="status" aria-live="polite" aria-atomic="true" className="flex items-center gap-2 min-h-[44px] text-slate-900 font-semibold">
          {(receiving || scanning) && <Spinner className="w-5 h-5 text-emerald-700" />}
          <span>{scanning ? "Decoding Aadhaar and finding patient…" : receiving ? "Receiving Aadhaar… Keep the card in place." : manualMode ? "Manual entry · USB capture paused" : "Ready for USB scan"}</span>
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
        />
      </div>
      {!collapsed && (
        <details className="mt-3" data-testid="camera-fallback">
          <summary className="min-h-[44px] flex items-center cursor-pointer font-semibold">Use phone camera or upload photo / PDF</summary>
          {scanner}
        </details>
      )}
      <Button type="button" variant="outline" className="mt-3" disabled={noCamp || busy || scanning} data-testid="door-manual-toggle" onClick={() => {
        clearScan();
        setManualMode(!manualMode);
      }}>{manualMode ? "Use scanner" : "Enter details manually"}</Button>
      {showManual && (
        <div className="mt-4 space-y-3" data-testid="door-manual-form" onChange={() => setManualMode(true)}>
          <p className="text-sm font-semibold text-amber-800" data-testid="manual-entry-note">Manual entry</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Full name" required>
              <Input value={doorForm.full_name} onChange={(e) => setDoorForm({ ...doorForm, full_name: e.target.value })} data-testid="reg-fullname-input" />
            </Field>
            <Field label="Age" required>
              <Input type="number" value={doorForm.age} onChange={(e) => setDoorForm({ ...doorForm, age: e.target.value })} data-testid="reg-age-input" />
            </Field>
            <Field label="Phone (household)" required>
              <Input value={doorForm.phone} onChange={(e) => setDoorForm({ ...doorForm, phone: e.target.value })} inputMode="numeric" data-testid="reg-phone-input" />
            </Field>
          </div>
          <Button
            onClick={submitDoorManual}
            disabled={busy || scanning || !doorForm.full_name || !doorForm.age || !/^\d{10}$/.test(doorForm.phone || "")}
            data-testid="door-manual-submit"
          >
            Register
          </Button>
        </div>
      )}
    </Card>
  );
}

export function PatientRow({ p, onPrint }) {
  return (
    <div
      id={`row-${p.id}`}
      className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-slate-200"
      data-testid={`patient-row-${p.reg_no}`}
    >
      <span className="font-mono font-bold text-emerald-600 w-14 shrink-0">#{p.reg_no}</span>
      <div className="flex-1 min-w-[140px]">
        <p className="font-semibold text-slate-900">{p.full_name}</p>
        <p className="text-xs text-slate-400">
          {p.gender_label} · {p.age ?? "-"} yrs {p.phone ? `· ${p.phone}` : ""}
        </p>
      </div>
      <StatusBadge status={p.queue_status} />
      {p.printed_at && <Badge tone="indigo">Printed</Badge>}
      {!p.arrived_at && (
        <span className="text-xs text-slate-500" data-testid={`awaiting-scan-${p.reg_no}`}>
          Scan their card at the door to check in
        </span>
      )}
      <div className="flex gap-1.5 ml-auto">
        {p.arrived_at && p.queue_status !== "seen" && (
          <Button size="sm" variant="outline" onClick={() => onPrint(p)} data-testid={`print-button-${p.reg_no}`}>
            <Printer className="w-4 h-4" /> Print
          </Button>
        )}
      </div>
    </div>
  );
}

export function RegisterModal({ open, walkIn, onClose, days, onDone, setBanner, onRegistered }) {
  const [form, setForm] = useState(EMPTY_REG_FORM);
  const [scanned, setScanned] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [dayId, setDayId] = useState("");
  const scanRequest = useRef(0);
  const [failures, setFailures] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reqId, setReqId] = useState(v4());
  const prevOpenRef = useRef(false);

  useEffect(() => {
    scanRequest.current += 1;
    return () => { scanRequest.current += 1; };
  }, [open, manualMode]);

  useEffect(() => {
    if (open && !prevOpenRef.current) {
      setForm(EMPTY_REG_FORM);
      setScanned(false);
      setManualMode(false);
      setFailures(0);
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

  const onScan = useCallback((data) => {
    setForm((prev) => ({
      full_name: data.full_name,
      age: data.age ?? "",
      phone: prev.phone,
      gender: data.gender,
      address: data.address,
      aadhaar_last4: data.aadhaar_last4,
      dob: data.dob,
    }));
    setScanned(true);
    setManualMode(false);
    setReqId(v4());
  }, []);

  const onFailure = useCallback((outcome) => {
    if (outcome === "garbage" || outcome === "not-aadhaar") {
      setFailures((n) => n + 1);
    }
  }, []);

  useWedgeBurst({
    enabled: open && !manualMode && !busy,
    onBurst: async (payload) => {
      const request = ++scanRequest.current;
      try {
        const { data } = await api.post("/aadhaar/decode", { payload });
        if (request !== scanRequest.current) return;
        if (data.outcome === "card") onScan(data.data);
        else onFailure(data.outcome);
      } catch {
        if (request === scanRequest.current) onFailure("garbage");
      }
    },
  });

  const onScanStall = useCallback(() => {}, []);

  const showForm = scanned || manualMode || failures >= 3;

  const submit = useCallback(async () => {
    setBusy(true); setError("");
    try {
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
        manual_entry: !scanned,
      });
      let reg = data.registration;
      if (walkIn) {
        const arrived = await api.post(`/desk/arrive/${reg.id}`);
        reg = arrived.data.registration;
      }
      setBanner(
        walkIn
          ? `Registered and checked in #${reg.reg_no} — ${reg.full_name}`
          : `Registered #${reg.reg_no} — ${reg.full_name}. SMS sent.`
      );
      if (onRegistered) onRegistered(reg);
      onClose(); onDone();
    } catch (err) {
      const payload = errorPayload(err);
      if (payload && payload.code === "DUPLICATE_IN_CAMP") {
        setError(`Already registered as #${payload.registration.reg_no}. Check them in instead.`);
      } else if (payload && payload.code === "AMBIGUOUS_MANUAL_ENTRY") {
        const nos = (payload.registrations || []).map((r) => `#${r.reg_no}`).join(", ");
        setError(`Multiple Manual entries match (${nos}). Check one of them in instead.`);
      } else {
        setError(formatApiError(err));
      }
    } finally { setBusy(false); }
  }, [form, scanned, dayId, reqId, walkIn, onClose, onDone, onRegistered, setBanner]);

  return (
    <Modal open={open} onClose={onClose} title={walkIn ? "Register walk-in" : "New Registration"} size="lg">
      <div className="space-y-4">
        {walkIn && (
          <p className="text-sm text-slate-600" data-testid="walk-in-note">
            This registers the patient and checks them in, in one action.
          </p>
        )}
        <AadhaarScanner onScanned={onScan} onFailure={onFailure} onScanStall={onScanStall} disabled={busy || manualMode}
          onCaptureStart={() => { scanRequest.current += 1; setScanned(false); setFailures(0); setForm((prev) => ({ ...EMPTY_REG_FORM, phone: prev.phone })); }}
          onTranscribed={(details) => {
            setForm((prev) => ({ ...EMPTY_REG_FORM, ...details, phone: prev.phone }));
            setScanned(false);
            setManualMode(true);
            setReqId(v4());
          }} />
        <Button type="button" variant="outline" disabled={busy} data-testid="reg-manual-toggle" onClick={() => {
          setScanned(false);
          setManualMode(!manualMode);
        }}>{manualMode ? "Use scanner" : "Enter details manually"}</Button>

        {showForm && (
          <>
            {!scanned && (
              <p className="text-sm font-semibold text-amber-800" data-testid="manual-entry-note">Manual entry</p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" onChange={() => { if (!scanned) setManualMode(true); }}>
              <Field label="Full name" required>
                <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} readOnly={scanned && Boolean(form.full_name)} className={scanned && form.full_name ? "bg-slate-100" : ""} data-testid="reg-fullname-input" />
              </Field>
              <Field label="Age" required>
                <Input type="number" value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value })} readOnly={scanned && form.age !== "" && form.age !== null && form.age !== undefined} className={scanned && form.age !== "" && form.age !== null && form.age !== undefined ? "bg-slate-100" : ""} data-testid="reg-age-input" />
              </Field>
              <Field label="Gender">
                <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300 disabled:bg-slate-100" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} disabled={scanned && Boolean(form.gender)} data-testid="reg-gender-select">
                  <option value="">—</option><option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
                </select>
              </Field>
              <Field label="Phone (household)" required hint="10-digit mobile">
                <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} inputMode="numeric" data-testid="reg-phone-input" />
              </Field>
              <Field label="Aadhaar last-4">
                <Input value={form.aadhaar_last4} onChange={(e) => setForm({ ...form, aadhaar_last4: e.target.value })} readOnly={scanned && Boolean(form.aadhaar_last4)} className={scanned && form.aadhaar_last4 ? "bg-slate-100" : ""} maxLength={4} data-testid="reg-last4-input" />
              </Field>
              <Field label="Camp day">
                <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={dayId} onChange={(e) => setDayId(e.target.value)} data-testid="reg-day-select">
                  {days.map((d) => <option key={d.id} value={d.id}>{d.day_date}{d.is_today ? " (today)" : ""}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Address">
              <Input value={form.address} onChange={(e) => { setForm({ ...form, address: e.target.value }); if (!scanned) setManualMode(true); }} readOnly={scanned && Boolean(form.address)} className={scanned && form.address ? "bg-slate-100" : ""} data-testid="reg-address-input" />
            </Field>
          </>
        )}

        <Alert>{error}</Alert>

        {showForm && (
          <div className="flex gap-2 justify-end pt-1">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={busy || !form.full_name || !dayId} data-testid="patient-register-submit">
              {busy ? "Registering…" : walkIn ? "Register and check in" : "Register"}
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
