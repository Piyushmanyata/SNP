import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import logger from "../lib/logger";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { OPERATOR_LINES, effectiveLine, lineLabel, writeSessionLine } from "../lib/operatorLines";
import { useWedgeBurst } from "../components/aadhaar";
import {
  ClinicalLookupForm,
  PatientSummaryCard,
  PrescriptionWizard,
  FulfilmentSection,
  CorrectionModal,
  HistoryModal,
  ReadOnlyPrescription,
} from "../components/clinical";
import { Button, Badge } from "../components/ui";

const PATIENT_CODE_PAYLOAD_LENGTH = "SNP:".length + 8;

const emptyRx = {
  diagnosis_options: [],
  diagnosis_other: "",
  blood_sugar: "",
  bp: "",
  remarks: "",
  specs_measurements: {
    r_sph: "",
    r_cyl: "",
    r_axis: "",
    l_sph: "",
    l_cyl: "",
    l_axis: "",
    add: "",
  },
  ot_eye: null,
  ot_outcome: null,
  ot_notes: "",
  prescribed_medicine_ids: [],
  fixed_power_r: null,
  fixed_power_l: null,
  prescribed_lines: [],
  none_prescribed: false,
  full_transcription_confirmed: false,
};

function rxFromTranscription(transcription) {
  if (!transcription) return emptyRx;
  return {
    ...emptyRx,
    ...transcription,
    specs_measurements: transcription.specs_measurements || emptyRx.specs_measurements,
    prescribed_medicine_ids: (transcription.prescribed_medicines || []).map(
      (m) => m.medicine_id,
    ),
  };
}

export default function Clinical() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [line, setLine] = useState(() => effectiveLine(user));
  const [picking, setPicking] = useState(() => !effectiveLine(user));
  const [lookup, setLookup] = useState("");
  const [results, setResults] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");
  const [diagOpts, setDiagOpts] = useState([]);
  const [medicines, setMedicines] = useState([]);
  const [powers, setPowers] = useState([]);
  const [otDays, setOtDays] = useState([]);
  const [specsDays, setSpecsDays] = useState([]);
  const [rx, setRx] = useState(emptyRx);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);
  const [history, setHistory] = useState(null);
  const firstFieldRef = useRef(null);
  const lookupRef = useRef(null);
  const lookupSequence = useRef(0);
  const completeOpRef = useRef(null);
  const patientId = data?.registration?.id;
  const locked = Boolean(data?.transcription?.locked);

  useEffect(() => {
    if (!picking) {
      if (patientId && !locked) firstFieldRef.current?.focus();
      else if (!patientId) lookupRef.current?.focus();
    }
  }, [patientId, locked, line, picking, editing]);

  useEffect(() => () => { lookupSequence.current += 1; }, []);

  useEffect(() => {
    const next = effectiveLine(user);
    setLine(next);
    setPicking(!next);
  }, [user]);

  useEffect(() => { completeOpRef.current = null; }, [patientId]);

  const pickLine = useCallback((key) => {
    writeSessionLine(key);
    setLine(key);
    setPicking(false);
  }, []);

  useEffect(() => {
    api
      .get("/clinical/diagnosis-options")
      .then((r) => setDiagOpts(r.data?.options || []))
      .catch((err) => {
        logger.warn("Failed to fetch diagnosis options:", err);
        setDiagOpts([]);
      });

    api
      .get("/catalogue/medicines")
      .then((r) => setMedicines(r.data?.medicines || []))
      .catch((err) => {
        logger.warn("Failed to fetch medicines:", err);
        setMedicines([]);
      });

    api
      .get("/catalogue/powers")
      .then((r) => setPowers(r.data?.powers || []))
      .catch((err) => {
        logger.warn("Failed to fetch fixed powers:", err);
        setPowers([]);
      });

    api
      .get("/clinical/ot-days")
      .then((r) => setOtDays(r.data?.ot_days || []))
      .catch((err) => {
        logger.warn("Failed to fetch OT days:", err);
        setOtDays([]);
      });

    api
      .get("/clinical/specs-days")
      .then((r) => setSpecsDays(r.data?.specs_days || []))
      .catch((err) => {
        logger.warn("Failed to fetch Specs collection days:", err);
        setSpecsDays([]);
      });
  }, []);

  const find = useCallback(async (value, byName = false) => {
    if (busy || !value) return false;
    const request = ++lookupSequence.current;
    setError("");
    setBanner("");
    setHistory(null);
    setData(null);
    setEditing(false);
    setResults(null);
    try {
      if (byName) {
        const { data: found } = await api.get(`/clinical/search?q=${encodeURIComponent(value)}`);
        if (request === lookupSequence.current) setResults(found.results);
        return false;
      }
      const { data: resData } = await api.post("/clinical/lookup", { value });
      if (request !== lookupSequence.current) return false;
      setData(resData);
      setRx(rxFromTranscription(resData.transcription));
      return true;
    } catch (err) {
      if (request !== lookupSequence.current) return false;
      const p = errorPayload(err);
      setError(p?.message || formatApiError(err));
      return false;
    }
  }, [busy]);

  const openPatient = useCallback((value) => {
    setLookup(value);
    return find(value.trim());
  }, [find]);

  const doLookup = useCallback((e) => {
    e?.preventDefault();
    const value = lookup.trim();
    find(value, !/^\d+$/.test(value) && !/^snp:/i.test(value));
  }, [lookup, find]);

  useWedgeBurst({
    enabled: !picking && !busy && !showCorrection,
    minLength: PATIENT_CODE_PAYLOAD_LENGTH,
    onBurst: openPatient,
  });

  const reload = useCallback(async () => {
    if (!data?.registration?.reg_no) return;
    const request = ++lookupSequence.current;
    try {
      const { data: resData } = await api.post("/clinical/lookup", {
        value: String(data.registration.reg_no),
      });
      if (request !== lookupSequence.current) return;
      setData(resData);
      setRx(rxFromTranscription(resData.transcription));
    } catch (err) {
      logger.warn("Failed to reload clinical data:", err);
    }
  }, [data?.registration?.reg_no]);

  const saveStep = useCallback(async () => {
    if (!data?.registration?.id) return false;
    setBusy(true);
    setError("");
    try {
      await api.post("/clinical/transcription", {
        patient_id: data.registration.id,
        ...rx,
      });
      return true;
    } catch (err) {
      setError(formatApiError(err));
      return false;
    } finally {
      setBusy(false);
    }
  }, [data?.registration?.id, rx]);

  const completeRx = useCallback(async () => {
    if (!data?.registration?.id) return;
    setBusy(true);
    setError("");
    try {
      if (!completeOpRef.current) {
        completeOpRef.current = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;
      }
      const { data: result } = await api.post("/clinical/transcription/complete", {
        patient_id: data.registration.id,
        expected_generation: data.clinical_generation ?? data.registration.clinical_generation ?? 0,
        operation_id: completeOpRef.current,
        ...rx,
      });
      completeOpRef.current = null;
      setData((current) => current?.registration?.id === patientId ? {
        ...current,
        registration: result.registration,
        transcription: result.transcription,
        committed_revision: result.revision,
        clinical_generation: result.registration.clinical_generation,
      } : current);
      setEditing(false);
      setBanner("Prescription completed. Patient is marked seen.");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [data?.registration?.id, data?.registration?.clinical_generation, data?.clinical_generation, patientId, rx]);

  const toggleDiag = useCallback((opt) => {
    setRx((r) => ({
      ...r,
      diagnosis_options: r.diagnosis_options.includes(opt)
        ? r.diagnosis_options.filter((o) => o !== opt)
        : [...r.diagnosis_options, opt],
    }));
  }, []);

  const openHistory = useCallback(async () => {
    if (!data?.person?.id) return;
    const request = lookupSequence.current;
    try {
      const { data: h } = await api.get(`/clinical/history/${data.person.id}`);
      if (request !== lookupSequence.current) return;
      setHistory(h.history);
    } catch (err) {
      if (request !== lookupSequence.current) return;
      setError(formatApiError(err));
    }
  }, [data?.person?.id]);

  const clearPatient = useCallback(() => {
    lookupSequence.current += 1;
    setData(null);
    setLookup("");
    setHistory(null);
    setRx(emptyRx);
    setEditing(false);
  }, []);

  if (picking || !line) {
    return (
      <Layout title="Clinical Desk">
        <div className="max-w-md mx-auto" data-testid="line-picker">
          <p className="font-display font-bold text-slate-900 mb-2">Which line are you monitoring?</p>
          <p className="text-sm text-slate-700 mb-4">Choose your line to start with its prescription fields. You can change lines at any time.</p>
          <div className="grid gap-2">
            {OPERATOR_LINES.map((l) => (
              <Button
                key={l.key}
                className="w-full"
                variant="outline"
                onClick={() => pickLine(l.key)}
                data-testid={`pick-line-${l.key}`}
              >
                {l.label}
              </Button>
            ))}
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Clinical Desk">
      <div className="flex items-center gap-2 mb-4" data-testid="line-chip">
        <Badge tone="emerald">{lineLabel(line)}</Badge>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setPicking(true)} data-testid="line-change-button">
          Change
        </Button>
      </div>

      <ClinicalLookupForm
        lookup={lookup}
        setLookup={setLookup}
        doLookup={doLookup}
        openPatient={openPatient}
        results={results}
        error={error}
        banner={banner}
        inputRef={lookupRef}
        busy={busy}
      />

      {data && (
        <>
          <PatientSummaryCard
            data={data}
            locked={locked}
            openHistory={openHistory}
          />

          {!locked && (!data.transcription || editing) && (
              <PrescriptionWizard
                rx={rx}
                setRx={setRx}
                diagOpts={diagOpts}
                medicines={medicines}
                powers={powers}
                toggleDiag={toggleDiag}
                locked={locked}
                busy={busy}
                saveStep={saveStep}
                completeRx={completeRx}
                setShowCorrection={setShowCorrection}
                firstFieldRef={firstFieldRef}
              />
          )}
          {editing && <p className="text-sm text-amber-800 mb-3">Save the prescription before issuing medicines, spectacles or a surgery token.</p>}

          {data.transcription && !editing && (
            <>
              <ReadOnlyPrescription
                transcription={data.transcription}
                emphasizePowers={line === "specs_fixed" || line === "specs_made"}
              />
              {locked ? <Button variant="outline" className="mb-3" disabled={busy} onClick={() => setShowCorrection(true)} data-testid="add-correction-button">Add correction</Button> : <Button variant="outline" className="mb-3" disabled={busy} onClick={() => setEditing(true)} data-testid="edit-transcription-button">Edit prescription</Button>}
              {!(data.committed_revision?.prescribed_lines || []).includes(line) && (
                <p className="text-sm text-amber-800 mb-3" data-testid="line-mismatch-warning">
                  This prescription does not imply {lineLabel(line)}. Record anyway.
                </p>
              )}
              {(data.committed_revision || data.transcription?.locked) && line !== "doctor_rx" && (
                <FulfilmentSection
                  line={line}
                  data={data}
                  otDays={otDays}
                  specsDays={specsDays}
                  powers={powers}
                  onDone={clearPatient}
                  navigate={navigate}
                  setBanner={setBanner}
                  setError={setError}
                  onBusyChange={setBusy}
                />
              )}
            </>
          )}
        </>
      )}

      <CorrectionModal
        open={showCorrection}
        onClose={() => setShowCorrection(false)}
        transcription={data?.transcription}
        line={line}
        diagOpts={diagOpts}
        medicines={medicines}
        powers={powers}
        expectedGeneration={data?.clinical_generation ?? data?.registration?.clinical_generation ?? 0}
        patientId={data?.registration?.id}
        prescribedLines={data?.committed_revision?.prescribed_lines || []}
        onDone={() => {
          setShowCorrection(false);
          reload();
          setBanner("Correction added.");
        }}
      />

      <HistoryModal
        open={!!history}
        onClose={() => setHistory(null)}
        history={history}
      />
    </Layout>
  );
}
