import React, { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "../../lib/api";
import { Modal, Field, Input, Alert, Button } from "../ui";
import { SpecsMeasurementsGrid } from "./SpecsMeasurementsGrid";
import { MedicinePicker } from "./MedicinePicker";
import { FixedPowerPicker } from "./FixedPowerPicker";
import { DiagnosisFields, LineChoices, OtFields, VitalsFields } from "./PrescriptionFields";
import { hospitalComplete, lineClash } from "./prescriptionRules";

const PRESCRIPTION_FIELDS = [
  "diagnosis_options", "diagnosis_other", "blood_sugar", "bp", "remarks",
  "prescribed_medicines", "specs_measurements", "fixed_power_r", "fixed_power_l",
  "ot_outcome", "ot_eye", "ot_notes",
];
const EMPTY_MEASUREMENTS = {
  r_sph: "", r_cyl: "", r_axis: "", l_sph: "", l_cyl: "", l_axis: "", add: "",
};

function initialValue(transcription, field) {
  if (field === "diagnosis_options") return transcription?.diagnosis_options || [];
  if (field === "prescribed_medicines") return transcription?.prescribed_medicines || [];
  if (field === "specs_measurements") {
    return { ...EMPTY_MEASUREMENTS, ...transcription?.specs_measurements };
  }
  if (field === "fixed_power_r" || field === "fixed_power_l") {
    return transcription?.[field] ?? null;
  }
  if (field === "ot_outcome" || field === "ot_eye") return transcription?.[field] || null;
  return transcription?.[field] ?? "";
}

export function CorrectionForm({
  transcription,
  line = "medicine",
  diagOpts = [],
  medicines = [],
  powers = [],
  onDone,
  expectedGeneration = 0,
  patientId,
  prescribedLines = [],
}) {
  const [initial] = useState(() => ({
    ...Object.fromEntries(PRESCRIPTION_FIELDS.map((f) => [f, initialValue(transcription, f)])),
    prescribed_lines: [...new Set([...(prescribedLines || []), line].filter((key) => key && key !== "doctor_rx"))],
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
  const hospital = rx.prescribed_lines.includes("ot");
  const canSubmit = Boolean(reason.trim())
    && Object.keys(changes).length > 0
    && !lineClash(rx.prescribed_lines, rx.ot_outcome)
    && (!hospital || hospitalComplete(rx));

  useEffect(() => { firstFieldRef.current?.focus(); }, []);

  const submit = async () => {
    if (busy || !canSubmit) return;
    setBusy(true);
    setError("");
    try {
      if (!opRef.current) {
        opRef.current = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`;
      }
      await api.post("/clinical/correction", {
        transcription_id: transcription.id,
        patient_id: patientId,
        reason: reason.trim(),
        changes,
        expected_generation: expectedGeneration,
        prescribed_lines: rx.prescribed_lines,
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

  const options = [...new Set([...diagOpts, ...initial.diagnosis_options])];
  const toggleDiag = (option) => setRx((current) => ({
    ...current,
    diagnosis_options: current.diagnosis_options.includes(option)
      ? current.diagnosis_options.filter((value) => value !== option)
      : [...current.diagnosis_options, option],
  }));

  return (
    <fieldset className="space-y-3" disabled={busy} data-testid="correction-form">
      <p className="text-sm text-slate-700">
        Complete or correct the doctor&apos;s prescription. Only changed fields are saved, with your
        reason in the audit history.
      </p>
      <Field label="Reason (audited)" required>
        <Input
          value={reason}
          ref={firstFieldRef}
          onChange={(e) => setReason(e.target.value)}
          disabled={busy}
          data-testid="correction-reason-input"
        />
      </Field>
      {error && <Alert>{error}</Alert>}

      <DiagnosisFields rx={rx} setRx={setRx} diagOpts={options} toggleDiag={toggleDiag} />

      <fieldset data-testid="correction-lines">
        <legend className="block text-xs font-mono uppercase tracking-widest text-slate-500 mb-1.5">
          What was prescribed
        </legend>
        <LineChoices rx={rx} setRx={setRx} />
      </fieldset>

      <Field label="Medicines">
        <MedicinePicker
          medicines={medicines}
          selectedIds={(rx.prescribed_medicines || []).map((m) => m.medicine_id)}
          onChange={(ids) => setRx({
            ...rx,
            prescribed_medicines: ids.map((id) => ({
              medicine_id: id,
              name: medicines.find((m) => m.id === id)?.name || "",
            })),
          })}
        />
      </Field>

      <Field label="Fixed power">
        <FixedPowerPicker
          powers={powers}
          valueR={rx.fixed_power_r}
          valueL={rx.fixed_power_l}
          onChange={(r, l) => setRx({ ...rx, fixed_power_r: r, fixed_power_l: l })}
        />
      </Field>

      <SpecsMeasurementsGrid
        specsMeasurements={rx.specs_measurements}
        onChange={(specs) => setRx({ ...rx, specs_measurements: specs })}
      />

      {hospital && <OtFields rx={rx} setRx={setRx} />}
      <VitalsFields rx={rx} setRx={setRx} />

      <Button
        type="button"
        className="w-full"
        disabled={busy || !canSubmit}
        onClick={submit}
        data-testid="save-transcription-button"
      >
        Save correction
      </Button>
    </fieldset>
  );
}

export function CorrectionModal({
  open, onClose, transcription, line, diagOpts, medicines, powers,
  onDone, expectedGeneration, patientId, prescribedLines,
}) {
  return (
    <Modal open={open} onClose={onClose} title="Complete or correct prescription" size="lg">
      <CorrectionForm
        key={transcription?.id}
        transcription={transcription}
        line={line}
        diagOpts={diagOpts}
        medicines={medicines}
        powers={powers}
        onDone={onDone}
        expectedGeneration={expectedGeneration}
        patientId={patientId}
        prescribedLines={prescribedLines}
      />
    </Modal>
  );
}
