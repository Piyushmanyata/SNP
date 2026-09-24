import React, { useId } from "react";
import { Input, Field, Alert } from "../ui";
import { OPERATOR_LINES } from "../../lib/operatorLines";
import { lineClash, withLines, withOutcome } from "./prescriptionRules";

const PRESCRIBED_LINES = OPERATOR_LINES.filter(({ key }) => key !== "doctor_rx");

const HOSPITAL_OUTCOMES = [
  { value: "iol_surgery", label: "IOL surgery" },
  { value: "referral", label: "Hospital referral" },
];

export function DiagnosisFields({ rx, setRx, diagOpts = [], toggleDiag, firstFieldRef }) {
  return (
    <>
      <Field.Group label="Diagnosis">
        <div className="flex flex-wrap gap-2" data-testid="diagnosis-options">
          {diagOpts.map((opt, i) => (
            <button
              key={opt}
              type="button"
              ref={i === 0 ? firstFieldRef : undefined}
              aria-pressed={rx.diagnosis_options.includes(opt)}
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
      </Field.Group>
      <div className="mt-3">
        <Field label="Other diagnosis">
          <Input
            value={rx.diagnosis_other || ""}
            ref={!diagOpts.length ? firstFieldRef : undefined}
            autoComplete="off"
            onChange={(e) => setRx({ ...rx, diagnosis_other: e.target.value })}
            data-testid="diagnosis-other-input"
          />
        </Field>
      </div>
    </>
  );
}

export function LineChoices({ rx, setRx, disabled }) {
  const lines = rx.prescribed_lines || [];
  const clash = lineClash(lines, rx.ot_outcome);
  return (
    <>
      {PRESCRIBED_LINES.map(({ key, label }) => {
        const ticked = lines.includes(key);
        const blocked = ticked ? "" : lineClash([...lines, key], rx.ot_outcome);
        return (
          <label key={key} className="flex items-center gap-3 min-h-[52px]">
            <input
              type="checkbox"
              checked={ticked}
              disabled={disabled || Boolean(blocked)}
              onChange={() => setRx(withLines(rx, ticked ? lines.filter((k) => k !== key) : [...lines, key]))}
              data-testid={`prescribed-${key}`}
            />
            <span>
              <span className="block font-medium text-slate-900">{label}</span>
              {blocked && (
                <span className="block text-xs text-amber-800" data-testid={`prescribed-${key}-blocked`}>
                  {blocked}
                </span>
              )}
            </span>
          </label>
        );
      })}
      {clash && <Alert tone="amber" className="mt-2">{clash}</Alert>}
    </>
  );
}

export function OtFields({ rx, setRx }) {
  const name = useId();
  const iolClash = lineClash(rx.prescribed_lines, "iol_surgery");
  return (
    <div className="space-y-3">
      <fieldset>
        <legend className="block text-xs font-mono uppercase tracking-widest text-slate-500 mb-1.5">
          What did the doctor write?
        </legend>
        {HOSPITAL_OUTCOMES.map(({ value, label }) => (
          <label key={value} className="flex items-center gap-3 min-h-[52px]">
            <input
              type="radio"
              name={name}
              value={value}
              checked={rx.ot_outcome === value}
              disabled={value === "iol_surgery" && Boolean(iolClash) && rx.ot_outcome !== value}
              onChange={() => setRx(withOutcome(rx, value))}
              data-testid={`ot-outcome-${value}`}
            />
            <span className="font-medium text-slate-900">{label}</span>
          </label>
        ))}
        {iolClash && (
          <p className="text-xs text-amber-800" data-testid="ot-outcome-blocked">{iolClash}</p>
        )}
      </fieldset>
      {rx.ot_outcome === "iol_surgery" && (
        <Field label="Surgery eye">
          <select
            aria-label="Surgery eye"
            className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300"
            value={rx.ot_eye || ""}
            onChange={(e) => setRx({ ...rx, ot_eye: e.target.value || null })}
            data-testid="ot-eye-select"
          >
            <option value="">—</option>
            <option value="R">Right</option>
            <option value="L">Left</option>
          </select>
        </Field>
      )}
      <Field label="Hospital notes" hint="Note here if the second eye was also prescribed.">
        <Input
          value={rx.ot_notes || ""}
          autoComplete="off"
          onChange={(e) => setRx({ ...rx, ot_notes: e.target.value })}
          data-testid="ot-notes-input"
        />
      </Field>
    </div>
  );
}

export function VitalsInputs({ rx, setRx }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Blood Sugar">
        <Input
          value={rx.blood_sugar || ""}
          autoComplete="off"
          placeholder="mg/dL"
          onChange={(e) => setRx({ ...rx, blood_sugar: e.target.value })}
          data-testid="sugar-input"
        />
      </Field>
      <Field label="Blood Pressure">
        <Input
          value={rx.bp || ""}
          autoComplete="off"
          placeholder="120/80"
          onChange={(e) => setRx({ ...rx, bp: e.target.value })}
          data-testid="bp-input"
        />
      </Field>
    </div>
  );
}

export function RemarksField({ rx, setRx }) {
  return (
    <Field label="Remarks">
      <Input
        value={rx.remarks || ""}
        autoComplete="off"
        onChange={(e) => setRx({ ...rx, remarks: e.target.value })}
        data-testid="remarks-input"
      />
    </Field>
  );
}

export function VitalsFields({ rx, setRx }) {
  return (
    <div className="space-y-3" data-testid="optional-vitals">
      <VitalsInputs rx={rx} setRx={setRx} />
      <RemarksField rx={rx} setRx={setRx} />
    </div>
  );
}
