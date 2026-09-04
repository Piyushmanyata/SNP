import React from "react";
import { Card, Button, Input, Field } from "../ui";
import { Save, FileEdit } from "lucide-react";
import { SpecsMeasurementsGrid } from "./SpecsMeasurementsGrid";

export function PrescriptionForm({
  rx,
  setRx,
  diagOpts = [],
  toggleDiag,
  locked,
  busy,
  saveRx,
  hasExistingTranscription,
  setShowCorrection,
  firstFieldRef,
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!locked && !busy) saveRx();
      }}
    >
      <Card className="mb-5" data-testid="clinical-prescription-form">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display font-bold text-slate-900">
            Prescription Transcription
          </h3>
          {locked && (
            <Button
              size="sm"
              variant="outline"
              type="button"
              onClick={() => setShowCorrection(true)}
              data-testid="add-correction-button"
            >
              <FileEdit className="w-4 h-4" /> Correction
            </Button>
          )}
        </div>

        <Field label="Diagnosis">
          <div className="flex flex-wrap gap-2" data-testid="diagnosis-options">
            {diagOpts.map((opt) => (
              <button
                key={opt}
                type="button"
                disabled={locked}
                onClick={() => toggleDiag(opt)}
                className={`min-h-[36px] px-3 rounded-full text-sm font-medium border transition-colors ${
                  rx.diagnosis_options.includes(opt)
                    ? "bg-emerald-500 text-white border-emerald-500"
                    : "bg-white text-slate-600 border-slate-300 hover:border-emerald-400"
                }`}
                data-testid={`diagnosis-opt-${opt.replace(/\s+/g, "-").toLowerCase()}`}
              >
                {opt}
              </button>
            ))}
          </div>
        </Field>

        <div className="mt-3">
          <Field label="Other diagnosis">
            <Input
              value={rx.diagnosis_other || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, diagnosis_other: e.target.value })}
              data-testid="diagnosis-other-input"
            />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Blood Sugar">
            <Input
              ref={firstFieldRef}
              value={rx.blood_sugar || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, blood_sugar: e.target.value })}
              placeholder="mg/dL"
              data-testid="sugar-input"
            />
          </Field>
          <Field label="Blood Pressure">
            <Input
              value={rx.bp || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, bp: e.target.value })}
              placeholder="120/80"
              data-testid="bp-input"
            />
          </Field>
        </div>

        <div className="mt-3">
          <Field label="Remarks">
            <Input
              value={rx.remarks || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, remarks: e.target.value })}
              data-testid="remarks-input"
            />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3 mt-4">
          <Field label="OT Eye">
            <select
              className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300 disabled:bg-slate-100"
              value={rx.ot_eye || ""}
              disabled={locked}
              onChange={(e) => setRx({ ...rx, ot_eye: e.target.value })}
              data-testid="ot-eye-select"
            >
              <option value="">—</option>
              <option value="R">Right</option>
              <option value="L">Left</option>
              <option value="B">Both</option>
            </select>
          </Field>
          <Field label="OT Procedure">
            <Input
              value={rx.ot_procedure || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, ot_procedure: e.target.value })}
              data-testid="ot-procedure-input"
            />
          </Field>
        </div>

        <SpecsMeasurementsGrid
          specsMeasurements={rx.specs_measurements}
          disabled={locked}
          onChange={(specs) => setRx({ ...rx, specs_measurements: specs })}
        />

        {!locked && (
          <Button
            className="mt-4"
            type="submit"
            disabled={busy}
            data-testid="save-transcription-button"
          >
            <Save className="w-4 h-4" /> {hasExistingTranscription ? "Update" : "Save"} Transcription
          </Button>
        )}
      </Card>
    </form>
  );
}
