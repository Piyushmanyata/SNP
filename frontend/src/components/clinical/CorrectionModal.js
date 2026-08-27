import React, { useState } from "react";
import api, { formatApiError } from "../../lib/api";
import { Modal, Field, Input, Alert, Button } from "../ui";

export function CorrectionForm({ transcriptionId, onDone }) {
  const [reason, setReason] = useState("");
  const [field, setField] = useState("remarks");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await api.post("/clinical/correction", {
        transcription_id: transcriptionId,
        reason,
        changes: { [field]: value },
      });
      onDone();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <Field label="Field">
        <select
          className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300"
          value={field}
          onChange={(e) => setField(e.target.value)}
          data-testid="correction-field-select"
        >
          {["remarks", "diagnosis_other", "bp", "blood_sugar", "ot_procedure"].map(
            (f) => (
              <option key={f} value={f}>
                {f}
              </option>
            )
          )}
        </select>
      </Field>
      <Field label="New value">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          data-testid="correction-value-input"
        />
      </Field>
      <Field label="Reason (audited)" required>
        <Input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          data-testid="correction-reason-input"
        />
      </Field>
      {error && <Alert>{error}</Alert>}
      <Button
        className="w-full"
        onClick={submit}
        disabled={busy || !reason}
        data-testid="correction-submit-button"
      >
        Add Correction
      </Button>
    </div>
  );
}

export function CorrectionModal({ open, onClose, transcriptionId, onDone }) {
  return (
    <Modal open={open} onClose={onClose} title="Prescription Correction">
      <CorrectionForm transcriptionId={transcriptionId} onDone={onDone} />
    </Modal>
  );
}
