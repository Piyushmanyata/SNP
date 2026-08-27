import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import Layout from "../components/Layout";
import {
  ClinicalLookupForm,
  PatientSummaryCard,
  PrescriptionForm,
  FulfilmentSection,
  CorrectionModal,
  HistoryModal,
} from "../components/clinical";

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
  const [lookup, setLookup] = useState("");
  const [data, setData] = useState(null); // {registration, person, transcription, fulfilments, slips}
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");
  const [diagOpts, setDiagOpts] = useState([]);
  const [otDays, setOtDays] = useState([]);
  const [rx, setRx] = useState(emptyRx);
  const [busy, setBusy] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    api
      .get("/clinical/diagnosis-options")
      .then((r) => setDiagOpts(r.data?.options || []))
      .catch((err) => {
        console.warn("Failed to fetch diagnosis options:", err);
        setDiagOpts([]);
      });

    api
      .get("/clinical/ot-days")
      .then((r) => setOtDays(r.data?.ot_days || []))
      .catch((err) => {
        console.warn("Failed to fetch OT days:", err);
        setOtDays([]);
      });
  }, []);

  const doLookup = async (e) => {
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
  };

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
      console.warn("Failed to reload clinical data:", err);
    }
  }, [lookup]);

  const saveRx = async () => {
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
  };

  const toggleDiag = (opt) => {
    setRx((r) => ({
      ...r,
      diagnosis_options: r.diagnosis_options.includes(opt)
        ? r.diagnosis_options.filter((o) => o !== opt)
        : [...r.diagnosis_options, opt],
    }));
  };

  const openHistory = async () => {
    if (!data?.person) return;
    try {
      const { data: h } = await api.get(`/clinical/history/${data.person.id}`);
      setHistory(h.history);
    } catch (err) {
      setError(formatApiError(err));
    }
  };

  const locked = data?.transcription?.locked;

  return (
    <Layout title="Clinical Desk">
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

          {data.transcription && (
            <FulfilmentSection
              data={data}
              otDays={otDays}
              onDone={reload}
              navigate={navigate}
              setBanner={setBanner}
              setError={setError}
            />
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
