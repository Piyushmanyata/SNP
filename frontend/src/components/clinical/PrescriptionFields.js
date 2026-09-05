import React from "react";
import { Input, Field } from "../ui";

export function DiagnosisFields({ rx, setRx, diagOpts = [], toggleDiag, disabled, firstFieldRef }) {
  return (
    <>
      <Field label="Diagnosis">
        <div className="flex flex-wrap gap-2" data-testid="diagnosis-options">
          {diagOpts.map((opt, i) => (
            <button
              key={opt}
              type="button"
              ref={i === 0 ? firstFieldRef : undefined}
              aria-pressed={rx.diagnosis_options.includes(opt)}
              disabled={disabled}
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
            ref={!diagOpts.length ? firstFieldRef : undefined}
            disabled={disabled}
            autoComplete="off"
            onChange={(e) => setRx({ ...rx, diagnosis_other: e.target.value })}
            data-testid="diagnosis-other-input"
          />
        </Field>
      </div>
    </>
  );
}

export function OtFields({ rx, setRx, disabled }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Surgery eye">
        <select
          aria-label="Surgery eye"
          className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300 disabled:bg-slate-100"
          value={rx.ot_eye || ""}
          disabled={disabled}
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
          disabled={disabled}
          autoComplete="off"
          onChange={(e) => setRx({ ...rx, ot_procedure: e.target.value })}
          data-testid="ot-procedure-input"
        />
      </Field>
      <div className="col-span-2">
        <Field label="Surgery notes">
          <Input
            value={rx.ot_notes || ""}
            disabled={disabled}
            autoComplete="off"
            onChange={(e) => setRx({ ...rx, ot_notes: e.target.value })}
            data-testid="ot-notes-input"
          />
        </Field>
      </div>
    </div>
  );
}

export function VitalsFields({ rx, setRx, disabled }) {
  return (
    <div className="space-y-3" data-testid="optional-vitals">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Blood Sugar">
          <Input
            value={rx.blood_sugar || ""}
            disabled={disabled}
            autoComplete="off"
            placeholder="mg/dL"
            onChange={(e) => setRx({ ...rx, blood_sugar: e.target.value })}
            data-testid="sugar-input"
          />
        </Field>
        <Field label="Blood Pressure">
          <Input
            value={rx.bp || ""}
            disabled={disabled}
            autoComplete="off"
            placeholder="120/80"
            onChange={(e) => setRx({ ...rx, bp: e.target.value })}
            data-testid="bp-input"
          />
        </Field>
      </div>
      <Field label="Remarks">
        <Input
          value={rx.remarks || ""}
          disabled={disabled}
          autoComplete="off"
          onChange={(e) => setRx({ ...rx, remarks: e.target.value })}
          data-testid="remarks-input"
        />
      </Field>
    </div>
  );
}
