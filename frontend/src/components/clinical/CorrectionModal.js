import React, { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "../../lib/api";
import { Modal, Field, Input, Alert } from "../ui";
import { PrescriptionForm } from "./PrescriptionForm";

const PRESCRIPTION_FIELDS = ["diagnosis_options", "diagnosis_other", "blood_sugar", "bp", "remarks", "medication_instructions", "specs_measurements", "ot_eye", "ot_procedure", "ot_notes"];
const EMPTY_MEASUREMENTS = {
  r_sph: "", r_cyl: "", r_axis: "", l_sph: "", l_cyl: "", l_axis: "", add: "",
};

export function CorrectionForm({ transcription, line = "medicine", diagOpts = [], onDone, expectedGeneration = 0, patientId, prescribedLines = [] }) {
  const [initial] = useState(() => ({
    ...Object.fromEntries(PRESCRIPTION_FIELDS.map((field) => [field, transcription?.[field] ?? ""])),
    diagnosis_options: transcription?.diagnosis_options || [],
    specs_measurements: { ...EMPTY_MEASUREMENTS, ...transcription?.specs_measurements },
  }));
  const [rx, setRx] = useState(initial);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const firstFieldRef = useRef(null);
  const opRef = useRef(null);
  const changes = Object.fromEntries(PRESCRIPTION_FIELDS
    .filter((field) => JSON.stringify(rx[field]) !== JSON.stringify(initial[field]))
    .map((field) => [field, rx[field]]));
  const canSubmit = Boolean(reason.trim()) && Object.keys(changes).length > 0;

  useEffect(() => { firstFieldRef.current?.focus(); }, []);

  const submit = async () => {
    if (busy || !canSubmit) return;
    setBusy(true);
    setError("");
    try {
      if (!opRef.current) {
        opRef.current = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;
      }
      const lines = [...new Set([...(prescribedLines || []), line].filter((key) => key && key !== "doctor_rx"))];
      await api.post("/clinical/correction", {
        transcription_id: transcription.id,
        patient_id: patientId,
        reason: reason.trim(),
        changes,
        expected_generation: expectedGeneration,
        prescribed_lines: lines,
        operation_id: opRef.current,
      });
      opRef.current = null;
      onDone();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <fieldset className="space-y-3" disabled={busy}>
      <p className="text-sm text-slate-700">Complete or correct the doctor's prescription. Only changed fields are saved, with your reason in the audit history.</p>
      <Field label="Reason (audited)" required>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy} data-testid="correction-reason-input" />
      </Field>
      {error && <Alert>{error}</Alert>}
      <PrescriptionForm
        rx={rx}
        setRx={setRx}
        line={line}
        diagOpts={[...new Set([...diagOpts, ...initial.diagnosis_options])]}
        toggleDiag={(option) => setRx((current) => ({
          ...current,
          diagnosis_options: current.diagnosis_options.includes(option)
            ? current.diagnosis_options.filter((value) => value !== option)
            : [...current.diagnosis_options, option],
        }))}
        locked={false}
        busy={busy || !canSubmit}
        saveRx={submit}
        hasExistingTranscription
        firstFieldRef={firstFieldRef}
      />
    </fieldset>
  );
}

export function CorrectionModal({ open, onClose, transcription, line, diagOpts, onDone, expectedGeneration, patientId, prescribedLines }) {
  return (
    <Modal open={open} onClose={onClose} title="Complete or correct prescription" size="lg">
      <CorrectionForm key={transcription?.id} transcription={transcription} line={line} diagOpts={diagOpts} onDone={onDone} expectedGeneration={expectedGeneration} patientId={patientId} prescribedLines={prescribedLines} />
    </Modal>
  );
}
