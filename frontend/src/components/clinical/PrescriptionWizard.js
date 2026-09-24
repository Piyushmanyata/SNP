import React, { useEffect, useRef, useState } from "react";
import { Alert, Card, Button } from "../ui";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { SpecsMeasurementsGrid } from "./SpecsMeasurementsGrid";
import { MedicinePicker } from "./MedicinePicker";
import { FixedPowerPicker, formatPower } from "./FixedPowerPicker";
import {
  DiagnosisFields, LineChoices, OtFields, RemarksField, VitalsFields, VitalsInputs,
} from "./PrescriptionFields";
import { hospitalComplete, hospitalOutcomeLabel, lineClash, withLines } from "./prescriptionRules";
import { lineLabel } from "../../lib/operatorLines";

const ALL_STEPS = [
  { key: "diagnosis", label: "Diagnosis" },
  { key: "lines", label: "What was prescribed" },
  { key: "medicine", label: "Medicines", line: "medicine" },
  { key: "specs_fixed", label: "Fixed power", line: "specs_fixed" },
  { key: "specs_made", label: "Spectacles to be made", line: "specs_made" },
  { key: "ot", label: "Hospital", line: "ot" },
  { key: "review", label: "Review and save" },
];

export function visibleSteps(rx) {
  const lines = rx.prescribed_lines || [];
  return ALL_STEPS.filter((s) => !s.line || lines.includes(s.line));
}

export function stepComplete(key, rx) {
  const m = rx.specs_measurements || {};
  switch (key) {
    case "lines": {
      const none = Boolean(rx.none_prescribed);
      const some = (rx.prescribed_lines || []).length > 0;
      return none ? !some : some && !lineClash(rx.prescribed_lines, rx.ot_outcome);
    }
    case "medicine":
      return (rx.prescribed_medicine_ids || []).length > 0;
    case "specs_fixed":
      return rx.fixed_power_r !== null && rx.fixed_power_l !== null
        && rx.fixed_power_r !== undefined && rx.fixed_power_l !== undefined;
    case "specs_made":
      return Boolean(String(m.r_sph || "").trim() && String(m.l_sph || "").trim());
    case "ot":
      return hospitalComplete(rx);
    case "review":
      return Boolean(rx.full_transcription_confirmed);
    default:
      return true;
  }
}

function Summary({ rx, medicines }) {
  const m = rx.specs_measurements || {};
  const lines = rx.prescribed_lines || [];
  const chosen = (rx.prescribed_medicine_ids || [])
    .map((id) => medicines.find((x) => x.id === id)?.name)
    .filter(Boolean);
  const diagnosis = [...(rx.diagnosis_options || []), rx.diagnosis_other]
    .filter(Boolean)
    .join("; ");
  return (
    <dl className="text-sm space-y-2" data-testid="wizard-summary">
      <div>
        <dt className="text-slate-500">Diagnosis</dt>
        <dd className="font-semibold text-slate-900">{diagnosis || "—"}</dd>
      </div>
      <div>
        <dt className="text-slate-500">Prescribed</dt>
        <dd className="font-semibold text-slate-900">
          {rx.none_prescribed
            ? "No fulfilment prescribed"
            : lines.map(lineLabel).join(", ") || "—"}
        </dd>
      </div>
      {lines.includes("medicine") && (
        <div>
          <dt className="text-slate-500">Medicines</dt>
          <dd className="font-semibold text-slate-900" data-testid="summary-medicines">
            {chosen.join(", ") || "—"}
          </dd>
        </div>
      )}
      {lines.includes("specs_fixed") && (
        <div>
          <dt className="text-slate-500">Fixed power</dt>
          <dd className="font-mono font-semibold text-slate-900" data-testid="summary-fixed-power">
            RE {formatPower(rx.fixed_power_r) || "—"} · LE {formatPower(rx.fixed_power_l) || "—"}
          </dd>
        </div>
      )}
      {lines.includes("specs_made") && (
        <div>
          <dt className="text-slate-500">Spectacles to be made</dt>
          <dd className="font-mono font-semibold text-slate-900">
            RE {m.r_sph || "—"} / {m.r_cyl || "—"} × {m.r_axis || "—"}
            {" · "}
            LE {m.l_sph || "—"} / {m.l_cyl || "—"} × {m.l_axis || "—"}
            {m.add ? ` · Add ${m.add}` : ""}
          </dd>
        </div>
      )}
      {lines.includes("ot") && (
        <div>
          <dt className="text-slate-500">Hospital</dt>
          <dd className="font-semibold text-slate-900" data-testid="summary-hospital">
            {[hospitalOutcomeLabel(rx), rx.ot_notes].filter(Boolean).join(" · ") || "—"}
          </dd>
        </div>
      )}
      {(rx.bp || rx.blood_sugar) && (
        <div>
          <dt className="text-slate-500">Vitals</dt>
          <dd className="font-semibold text-slate-900" data-testid="summary-vitals">
            {[rx.bp && `BP ${rx.bp}`, rx.blood_sugar && `Blood sugar ${rx.blood_sugar}`]
              .filter(Boolean)
              .join(" · ")}
          </dd>
        </div>
      )}
    </dl>
  );
}

function OptionalVitals({ rx, setRx }) {
  const hospital = (rx.prescribed_lines || []).includes("ot");
  const [open, setOpen] = useState(
    Boolean(rx.remarks || (!hospital && (rx.blood_sugar || rx.bp))),
  );
  if (!open) {
    return (
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="mt-4"
        onClick={() => setOpen(true)}
        data-testid={hospital ? "add-remarks-button" : "add-vitals-button"}
      >
        {hospital ? "Add remarks" : "Add vitals & remarks"}
      </Button>
    );
  }
  return (
    <div className="mt-4">
      {hospital
        ? <RemarksField rx={rx} setRx={setRx} />
        : <VitalsFields rx={rx} setRx={setRx} />}
    </div>
  );
}

export function PrescriptionWizard({
  rx,
  setRx,
  diagOpts = [],
  medicines = [],
  powers = [],
  toggleDiag,
  busy,
  error,
  saveStep,
  completeRx,
  firstFieldRef,
  medicineUnavailable = false,
  powerUnavailable = false,
}) {
  const [index, setIndex] = useState(0);
  const steps = visibleSteps(rx);
  const current = steps[Math.min(index, steps.length - 1)];
  const position = Math.min(index, steps.length - 1);
  const canAdvance = stepComplete(current.key, rx);
  const headingRef = useRef(null);
  const bodyRef = useRef(null);
  const shownStep = useRef(position);

  useEffect(() => {
    if (shownStep.current === position) return;
    shownStep.current = position;
    headingRef.current?.focus();
    bodyRef.current?.querySelector("input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])")?.focus();
  }, [position]);

  const goNext = async () => {
    if (await saveStep?.() === false) return;
    setIndex((i) => Math.min(i + 1, steps.length - 1));
  };

  const submit = (e) => {
    e.preventDefault();
    if (busy || !canAdvance) return;
    if (current.key === "review") completeRx?.();
    else goNext();
  };

  return (
    <Card className="mb-5">
      <form onSubmit={submit} data-testid="clinical-prescription-form">
        <h3 ref={headingRef} tabIndex={-1} className="font-display font-bold text-slate-900 mb-1 focus:outline-none">{current.label}</h3>
        <p className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-4" data-testid="wizard-progress">
          Step {position + 1} of {steps.length}
        </p>
        <p className="sr-only" aria-live="polite" data-testid="wizard-announcement">
          Step {position + 1} of {steps.length}: {current.label}
        </p>
        <div ref={bodyRef}>
          {current.key === "diagnosis" && (
            <DiagnosisFields
              rx={rx}
              setRx={setRx}
              diagOpts={diagOpts}
              toggleDiag={toggleDiag}
              firstFieldRef={firstFieldRef}
            />
          )}

          {current.key === "lines" && (
            <fieldset data-testid="prescribed-lines">
              <legend className="text-sm text-slate-700 mb-2">
                Tick every line the doctor wrote on the paper.
              </legend>
              <LineChoices rx={rx} setRx={setRx} disabled={rx.none_prescribed} />
              <label className="flex items-center gap-3 min-h-[52px] border-t border-slate-200 mt-2 pt-2">
                <input
                  type="checkbox"
                  checked={Boolean(rx.none_prescribed)}
                  onChange={(e) =>
                    setRx({
                      ...withLines(rx, e.target.checked ? [] : rx.prescribed_lines || []),
                      none_prescribed: e.target.checked,
                    })
                  }
                  data-testid="none-prescribed"
                />
                <span className="font-medium text-slate-900">No fulfilment prescribed</span>
              </label>
            </fieldset>
          )}

          {current.key === "medicine" && (
            <MedicinePicker
              medicines={medicines}
              selectedIds={rx.prescribed_medicine_ids || []}
              onChange={(ids) => setRx({ ...rx, prescribed_medicine_ids: ids })}
              unavailable={medicineUnavailable}
            />
          )}

          {current.key === "specs_fixed" && (
            <FixedPowerPicker
              powers={powers}
              valueR={rx.fixed_power_r}
              valueL={rx.fixed_power_l}
              onChange={(r, l) => setRx({ ...rx, fixed_power_r: r, fixed_power_l: l })}
              unavailable={powerUnavailable}
            />
          )}

          {current.key === "specs_made" && (
            <SpecsMeasurementsGrid
              specsMeasurements={rx.specs_measurements}
              onChange={(specs) => setRx({ ...rx, specs_measurements: specs })}
            />
          )}

          {current.key === "ot" && (
            <>
              <OtFields rx={rx} setRx={setRx} />
              <div className="mt-4">
                <VitalsInputs rx={rx} setRx={setRx} />
              </div>
            </>
          )}

          {current.key === "review" && (
            <>
              <Summary rx={rx} medicines={medicines} />
              <OptionalVitals rx={rx} setRx={setRx} />
              <label className="flex items-center gap-2 min-h-[52px] mt-4">
                <input
                  type="checkbox"
                  checked={Boolean(rx.full_transcription_confirmed)}
                  onChange={(e) =>
                    setRx({ ...rx, full_transcription_confirmed: e.target.checked })
                  }
                  data-testid="full-transcription-confirmed"
                />
                <span>I copied every instruction on the paper</span>
              </label>
            </>
          )}
        </div>

        <Alert className="mt-5">{error}</Alert>
        <div className="mt-5 flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy || position === 0}
            onClick={() => setIndex((i) => Math.max(i - 1, 0))}
            data-testid="wizard-back"
          >
            <ChevronLeft className="w-4 h-4" /> Back
          </Button>
          {current.key === "review" ? (
            <Button
              type="submit"
              className="flex-1"
              disabled={busy || !canAdvance}
              data-testid="complete-prescription-button"
            >
              Save prescription &amp; mark seen
            </Button>
          ) : (
            <Button
              type="submit"
              className="flex-1"
              disabled={busy || !canAdvance}
              data-testid="wizard-next"
            >
              Next <ChevronRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}
