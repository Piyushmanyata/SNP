import React from "react";
import { Card } from "../ui";
import { hasFixedPower, hasMeasurements } from "./FulfilmentStation";
import { formatPower } from "./FixedPowerPicker";
import { hospitalOutcomeLabel } from "./prescriptionRules";

function Row({ k, v, testId }) {
  return (
    <div data-testid={testId}>
      <span className="text-slate-400 mr-2">{k}:</span>
      <span className="font-semibold text-slate-900">{v || "—"}</span>
    </div>
  );
}

export function ReadOnlyPrescription({ transcription, emphasizePowers }) {
  if (!transcription) return null;
  const m = transcription.specs_measurements || {};
  const diagnosis = [
    ...(transcription.diagnosis_options || []),
    transcription.diagnosis_other,
  ].filter(Boolean).join("; ");
  return (
    <Card className="mb-5" data-testid="readonly-prescription">
      <h3 className="font-display font-bold text-slate-900 mb-3">Prescription</h3>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <Row k="Diagnosis" v={diagnosis} />
        <Row k="Blood sugar" v={transcription.blood_sugar} />
        <Row k="BP" v={transcription.bp} />
        <Row k="Remarks" v={transcription.remarks} />
        <Row k="Hospital" v={hospitalOutcomeLabel(transcription)} testId="readonly-hospital" />
        <Row k="Hospital notes" v={transcription.ot_notes} testId="readonly-hospital-notes" />
        <Row
          k="Medicines"
          v={(transcription.prescribed_medicines || []).map((x) => x.name).join(", ")}
        />
      </div>
      {hasFixedPower(transcription) && (
        <div className={`mt-4 ${emphasizePowers ? "text-lg" : "text-sm"}`} data-testid="readonly-fixed-power">
          <p className="text-xs font-semibold text-slate-500 uppercase mb-1">Fixed power</p>
          <p className="font-mono font-bold text-slate-900">
            RE {formatPower(transcription.fixed_power_r)}
            {" · "}
            LE {formatPower(transcription.fixed_power_l)}
          </p>
        </div>
      )}
      <div className={`mt-4 ${emphasizePowers ? "text-lg" : "text-sm"}`} data-testid="readonly-powers">
        <p className="text-xs font-semibold text-slate-500 uppercase mb-1">Powers</p>
        {hasMeasurements(transcription) ? (
          <p className="font-mono font-bold text-slate-900">
            RE {m.r_sph || "—"} / {m.r_cyl || "—"} × {m.r_axis || "—"}
            {" · "}
            LE {m.l_sph || "—"} / {m.l_cyl || "—"} × {m.l_axis || "—"}
            {m.add ? ` · Add ${m.add}` : ""}
          </p>
        ) : (
          <p className="text-amber-800">No powers recorded.</p>
        )}
      </div>
    </Card>
  );
}
