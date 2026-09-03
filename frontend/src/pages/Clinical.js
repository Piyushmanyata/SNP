import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import logger from "../lib/logger";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import { OPERATOR_LINES, effectiveLine, lineLabel, writeSessionLine } from "../lib/operatorLines";
import {
  ClinicalLookupForm,
  PatientSummaryCard,
  PrescriptionForm,
  FulfilmentSection,
  CorrectionModal,
  HistoryModal,
  ReadOnlyPrescription,
  hasMeasurements,
  transcriptionImpliesLine,
} from "../components/clinical";
import { Button, Badge } from "../components/ui";

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
  ot_eye: "",
  ot_procedure: "",
  ot_notes: "",
};

export default function Clinical() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [line, setLine] = useState(() => effectiveLine(user));
  const [picking, setPicking] = useState(() => !effectiveLine(user));
  const [lookup, setLookup] = useState("");
  const [data, setData] = useState(null); // {registration, person, transcription, fulfilments, slips}
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");
  const [diagOpts, setDiagOpts] = useState([]);
  const [otDays, setOtDays] = useState([]);
  const [specsDays, setSpecsDays] = useState([]);
  const [rx, setRx] = useState(emptyRx);
  const [busy, setBusy] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    const next = effectiveLine(user);
    setLine(next);
    setPicking(!next);
  }, [user]);

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

  const doLookup = useCallback(async (e) => {
    e?.preventDefault();
    setError("");
    setBanner("");
    setHistory(null);
    if (!lookup.trim()) return;
    try {
      const { data: resData } = await api.post("/clinical/lookup", {
        value: lookup.trim(),
      });
      setData(resData);
      setRx(
        resData.transcription
          ? {
              ...emptyRx,
              ...resData.transcription,
              specs_measurements:
                resData.transcription.specs_measurements ||
                emptyRx.specs_measurements,
            }
          : emptyRx
      );
    } catch (err) {
      const p = errorPayload(err);
      setData(null);
      setError(p?.message || formatApiError(err));
    }
  }, [lookup]);

  const reload = useCallback(async () => {
    if (!lookup.trim()) return;
    try {
      const { data: resData } = await api.post("/clinical/lookup", {
        value: lookup.trim(),
      });
      setData(resData);
      setRx(
        resData.transcription
          ? {
              ...emptyRx,
              ...resData.transcription,
              specs_measurements:
                resData.transcription.specs_measurements ||
                emptyRx.specs_measurements,
            }
          : emptyRx
      );
    } catch (err) {
      logger.warn("Failed to reload clinical data:", err);
    }
  }, [lookup]);

  const saveRx = useCallback(async () => {
    if (!data?.registration?.id) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/clinical/transcription", {
        patient_id: data.registration.id,
        ...rx,
      });
      setBanner("Transcription saved.");
      await reload();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [data?.registration?.id, rx, reload]);

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
    try {
      const { data: h } = await api.get(`/clinical/history/${data.person.id}`);
      setHistory(h.history);
    } catch (err) {
      setError(formatApiError(err));
    }
  }, [data?.person?.id]);

  const locked = data?.transcription?.locked;
  const isRx = line === "rx";
  const lineDesk = line && !isRx;

  const clearPatient = useCallback(() => {
    setData(null);
    setLookup("");
    setHistory(null);
  }, []);

  if (picking || !line) {
    return (
      <Layout title="Clinical Desk">
        <div className="max-w-md mx-auto" data-testid="line-picker">
          <p className="font-display font-bold text-slate-900 mb-3">Pick a station</p>
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
        <Button size="sm" variant="ghost" onClick={() => setPicking(true)} data-testid="line-change-button">
          Change
        </Button>
      </div>

      <ClinicalLookupForm
        lookup={lookup}
        setLookup={setLookup}
        doLookup={doLookup}
        error={error}
        banner={banner}
      />

      {data && (
        <>
          <PatientSummaryCard
            data={data}
            locked={locked}
            openHistory={openHistory}
          />

          {isRx && (
            <>
              {!hasMeasurements(rx) && (rx.diagnosis_options || []).length > 0 && (
                <p className="text-sm text-amber-800 mb-3" data-testid="rx-missing-powers-warning">
                  No powers recorded — specs desks will be blocked until a correction is filed.
                </p>
              )}
              <PrescriptionForm
                rx={rx}
                setRx={setRx}
                diagOpts={diagOpts}
                toggleDiag={toggleDiag}
                locked={locked}
                busy={busy}
                saveRx={saveRx}
                hasExistingTranscription={!!data.transcription}
                setShowCorrection={setShowCorrection}
              />
            </>
          )}

          {lineDesk && !data.transcription && (
            <p className="text-sm text-slate-700 mb-3" data-testid="send-to-rx">
              Send this patient to the Doctor&apos;s Rx desk.
            </p>
          )}

          {lineDesk && data.transcription && (
            <>
              <ReadOnlyPrescription
                transcription={data.transcription}
                emphasizePowers={line === "specs_fixed" || line === "specs_made"}
              />
              {!transcriptionImpliesLine(data.transcription, line) && (
                <p className="text-sm text-amber-800 mb-3" data-testid="line-mismatch-warning">
                  This prescription does not imply {lineLabel(line)}. Record anyway.
                </p>
              )}
              <FulfilmentSection
                line={line}
                data={data}
                otDays={otDays}
                specsDays={specsDays}
                onDone={clearPatient}
                navigate={navigate}
                setBanner={setBanner}
                setError={setError}
              />
            </>
          )}
        </>
      )}

      <CorrectionModal
        open={showCorrection}
        onClose={() => setShowCorrection(false)}
        transcriptionId={data?.transcription?.id}
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
