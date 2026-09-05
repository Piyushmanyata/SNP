import React, { useState } from "react";
import { Card, Button } from "../ui";
import { ChevronLeft, ChevronRight, FileEdit } from "lucide-react";
import { SpecsMeasurementsGrid } from "./SpecsMeasurementsGrid";
import { MedicinePicker } from "./MedicinePicker";
import { FixedPowerPicker, formatPower } from "./FixedPowerPicker";
import { DiagnosisFields, OtFields, VitalsFields } from "./PrescriptionFields";

const LINE_LABELS = {
  medicine: "Medicine",
  specs_fixed: "Fixed-power specs",
  specs_made: "Spectacles to be made",
  ot: "Hospital surgery",
};

const ALL_STEPS = [
  { key: "diagnosis", label: "Diagnosis" },
  { key: "lines", label: "What was prescribed" },
  { key: "medicine", label: "Medicines", line: "medicine" },
  { key: "specs_fixed", label: "Fixed power", line: "specs_fixed" },
  { key: "specs_made", label: "Spectacles to be made", line: "specs_made" },
  { key: "ot", label: "Hospital surgery", line: "ot" },
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
      return none ? !some : some;
    }
    case "medicine":
      return (rx.prescribed_medicine_ids || []).length > 0;
    case "specs_fixed":
      return rx.fixed_power_r !== null && rx.fixed_power_l !== null
        && rx.fixed_power_r !== undefined && rx.fixed_power_l !== undefined;
    case "specs_made":
      return Boolean(String(m.r_sph || "").trim() && String(m.l_sph || "").trim());
    case "ot":
      return Boolean(String(rx.ot_eye || "").trim() && String(rx.ot_procedure || "").trim());
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
            : lines.map((l) => LINE_LABELS[l]).join(", ") || "—"}
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
          <dt className="text-slate-500">Hospital surgery</dt>
          <dd className="font-semibold text-slate-900">
            {rx.ot_eye || "—"} · {rx.ot_procedure || "—"}
            {rx.ot_notes ? ` · ${rx.ot_notes}` : ""}
          </dd>
        </div>
      )}
    </dl>
  );
}

function OptionalVitals({ rx, setRx, locked }) {
  const [open, setOpen] = useState(
    Boolean(rx.blood_sugar || rx.bp || rx.remarks),
  );
  if (!open) {
    return (
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="mt-4"
        onClick={() => setOpen(true)}
        data-testid="add-vitals-button"
      >
        Add vitals &amp; remarks
      </Button>
    );
  }
  return (
    <div className="mt-4">
      <VitalsFields rx={rx} setRx={setRx} disabled={locked} />
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
  locked,
  busy,
  saveStep,
  completeRx,
  setShowCorrection,
  firstFieldRef,
}) {
  const [index, setIndex] = useState(0);
  const steps = visibleSteps(rx);
  const current = steps[Math.min(index, steps.length - 1)];
  const position = Math.min(index, steps.length - 1);
  const canAdvance = stepComplete(current.key, rx);

  const goNext = () => {
    saveStep?.();
    setIndex((i) => Math.min(i + 1, steps.length - 1));
  };

  return (
    <Card className="mb-5" data-testid="clinical-prescription-form">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-display font-bold text-slate-900">{current.label}</h3>
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
      <p className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-4" data-testid="wizard-progress">
        Step {position + 1} of {steps.length}
      </p>

      {current.key === "diagnosis" && (
        <DiagnosisFields
          rx={rx}
          setRx={setRx}
          diagOpts={diagOpts}
          toggleDiag={toggleDiag}
          disabled={locked}
          firstFieldRef={firstFieldRef}
        />
      )}

      {current.key === "lines" && (
        <fieldset data-testid="prescribed-lines">
          <legend className="text-sm text-slate-700 mb-2">
            Tick every line the doctor wrote on the paper.
          </legend>
          {Object.keys(LINE_LABELS).map((key) => (
            <label key={key} className="flex items-center gap-3 min-h-[52px]">
              <input
                type="checkbox"
                checked={(rx.prescribed_lines || []).includes(key)}
                disabled={locked || rx.none_prescribed}
                onChange={() => {
                  const cur = rx.prescribed_lines || [];
                  setRx({
                    ...rx,
                    prescribed_lines: cur.includes(key)
                      ? cur.filter((k) => k !== key)
                      : [...cur, key],
                  });
                }}
                data-testid={`prescribed-${key}`}
              />
              <span className="font-medium text-slate-900">{LINE_LABELS[key]}</span>
            </label>
          ))}
          <label className="flex items-center gap-3 min-h-[52px] border-t border-slate-200 mt-2 pt-2">
            <input
              type="checkbox"
              checked={Boolean(rx.none_prescribed)}
              disabled={locked}
              onChange={(e) =>
                setRx({
                  ...rx,
                  none_prescribed: e.target.checked,
                  prescribed_lines: e.target.checked ? [] : rx.prescribed_lines,
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
          disabled={locked}
          onChange={(ids) => setRx({ ...rx, prescribed_medicine_ids: ids })}
        />
      )}

      {current.key === "specs_fixed" && (
        <FixedPowerPicker
          powers={powers}
          valueR={rx.fixed_power_r}
          valueL={rx.fixed_power_l}
          disabled={locked}
          onChange={(r, l) => setRx({ ...rx, fixed_power_r: r, fixed_power_l: l })}
        />
      )}

      {current.key === "specs_made" && (
        <SpecsMeasurementsGrid
          specsMeasurements={rx.specs_measurements}
          disabled={locked}
          onChange={(specs) => setRx({ ...rx, specs_measurements: specs })}
        />
      )}

      {current.key === "ot" && <OtFields rx={rx} setRx={setRx} disabled={locked} />}

      {current.key === "review" && (
        <>
          <Summary rx={rx} medicines={medicines} />
          <OptionalVitals rx={rx} setRx={setRx} locked={locked} />
          <label className="flex items-center gap-2 min-h-[52px] mt-4">
            <input
              type="checkbox"
              checked={Boolean(rx.full_transcription_confirmed)}
              disabled={locked}
              onChange={(e) =>
                setRx({ ...rx, full_transcription_confirmed: e.target.checked })
              }
              data-testid="full-transcription-confirmed"
            />
            <span>I copied every instruction on the paper</span>
          </label>
        </>
      )}

      {!locked && (
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
              type="button"
              className="flex-1"
              disabled={busy || !canAdvance}
              onClick={() => completeRx && completeRx()}
              data-testid="complete-prescription-button"
            >
              Save prescription &amp; mark seen
            </Button>
          ) : (
            <Button
              type="button"
              className="flex-1"
              disabled={busy || !canAdvance}
              onClick={goNext}
              data-testid="wizard-next"
            >
              Next <ChevronRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
