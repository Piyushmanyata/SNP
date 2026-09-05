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
  completeRx,
  hasExistingTranscription,
  setShowCorrection,
  firstFieldRef,
  line = "medicine",
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!locked && !busy) saveRx();
      }}
    >
      <Card className="mb-5 flex flex-col" data-testid="clinical-prescription-form">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display font-bold text-slate-900">
            Copy the doctor’s prescription
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

        <div className={line === "medicine" ? "order-1" : "order-2 mt-3"}>
        <Field label="Diagnosis">
          <div className="flex flex-wrap gap-2" data-testid="diagnosis-options">
            {diagOpts.map((opt, index) => (
              <button
                key={opt}
                type="button"
                ref={line === "medicine" && index === 0 ? firstFieldRef : undefined}
                aria-pressed={rx.diagnosis_options.includes(opt)}
                disabled={locked}
                onClick={() => toggleDiag(opt)}
                className={`min-h-[44px] px-3 rounded-full text-sm font-medium border transition-colors ${
                  rx.diagnosis_options.includes(opt)
                    ? "bg-emerald-700 text-white border-emerald-700"
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
              ref={line === "medicine" && !diagOpts.length ? firstFieldRef : undefined}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, diagnosis_other: e.target.value })}
              data-testid="diagnosis-other-input"
            />
          </Field>
        </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mt-3 order-2">
          <Field label="Blood Sugar">
            <Input
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

        <div className="mt-3 order-2">
          <Field label="Medicine instructions">
            <Input
              value={rx.medication_instructions || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, medication_instructions: e.target.value })}
              data-testid="medication-instructions-input"
            />
          </Field>
        </div>
        <div className="mt-3 order-2">
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
        <fieldset className="mt-3 order-2" data-testid="prescribed-lines">
          <legend className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-1.5">Prescribed lines</legend>
          {["medicine", "specs_fixed", "specs_made", "ot"].map((key) => (
            <label key={key} className="flex items-center gap-2 min-h-[44px]">
              <input
                type="checkbox"
                checked={(rx.prescribed_lines || []).includes(key)}
                disabled={locked || rx.none_prescribed}
                onChange={() => {
                  const cur = rx.prescribed_lines || [];
                  setRx({
                    ...rx,
                    prescribed_lines: cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key],
                  });
                }}
                data-testid={`prescribed-${key}`}
              />
              <span>{key.replace("_", " ")}</span>
            </label>
          ))}
          <label className="flex items-center gap-2 min-h-[44px]">
            <input
              type="checkbox"
              checked={Boolean(rx.none_prescribed)}
              disabled={locked}
              onChange={(e) => setRx({ ...rx, none_prescribed: e.target.checked, prescribed_lines: e.target.checked ? [] : rx.prescribed_lines })}
              data-testid="none-prescribed"
            />
            <span>No fulfilment prescribed</span>
          </label>
        </fieldset>
        <label className="flex items-center gap-2 min-h-[44px] mt-2 order-2">
          <input
            type="checkbox"
            checked={Boolean(rx.full_transcription_confirmed)}
            disabled={locked}
            onChange={(e) => setRx({ ...rx, full_transcription_confirmed: e.target.checked })}
            data-testid="full-transcription-confirmed"
          />
          <span>I copied every instruction on the paper</span>
        </label>

        <div className={`grid grid-cols-2 gap-3 mt-4 ${line === "ot" ? "order-1" : "order-2"}`}>
          <Field label="Surgery eye">
            <select
              ref={line === "ot" ? firstFieldRef : undefined}
              aria-label="Surgery eye"
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
          <Field label="Hospital procedure">
            <Input
              value={rx.ot_procedure || ""}
              disabled={locked}
              autoComplete="off"
              onChange={(e) => setRx({ ...rx, ot_procedure: e.target.value })}
              data-testid="ot-procedure-input"
            />
          </Field>
          <div className="col-span-2">
            <Field label="Surgery notes">
              <Input
                value={rx.ot_notes || ""}
                disabled={locked}
                autoComplete="off"
                onChange={(e) => setRx({ ...rx, ot_notes: e.target.value })}
                data-testid="ot-notes-input"
              />
            </Field>
          </div>
        </div>

        <div className={line.startsWith("specs_") ? "order-1" : "order-2"}>
        <SpecsMeasurementsGrid
          firstFieldRef={line.startsWith("specs_") ? firstFieldRef : undefined}
          specsMeasurements={rx.specs_measurements}
          disabled={locked}
          onChange={(specs) => setRx({ ...rx, specs_measurements: specs })}
        />
        </div>

        {!locked && (
          <div className="mt-4 order-3 flex flex-col gap-2">
            <Button
              type="submit"
              variant="outline"
              disabled={busy}
              data-testid="save-transcription-button"
            >
              <Save className="w-4 h-4" /> Save draft
            </Button>
            <Button
              type="button"
              disabled={busy}
              onClick={() => completeRx && completeRx()}
              data-testid="complete-prescription-button"
            >
              Save prescription & mark seen
            </Button>
          </div>
        )}
      </Card>
    </form>
  );
}
