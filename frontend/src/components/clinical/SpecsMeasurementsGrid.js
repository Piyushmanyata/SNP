import React from "react";
import { Input } from "../ui";

const SIGNED = new Set(["r_sph", "r_cyl", "l_sph", "l_cyl"]);

function flipSign(value) {
  const text = String(value || "").trim();
  if (text.startsWith("-")) return `+${text.slice(1)}`;
  if (text.startsWith("+")) return `-${text.slice(1)}`;
  return `-${text}`;
}

const RIGHT = [
  ["r_sph", "Right SPH"],
  ["r_cyl", "Right CYL"],
  ["r_axis", "Right axis"],
];
const LEFT = [
  ["l_sph", "Left SPH"],
  ["l_cyl", "Left CYL"],
  ["l_axis", "Left axis"],
];

function EyeGroup({ title, fields, specsMeasurements, onChange, disabled, firstFieldRef, testid }) {
  return (
    <fieldset className="min-w-0" data-testid={testid}>
      <legend className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-2">{title}</legend>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {fields.map(([k, label], i) => (
          <div key={k}>
            <label className="text-xs font-mono text-slate-700" htmlFor={`specs-${k}`}>
              {label}
            </label>
            <div className="flex gap-1">
              <Input
                id={`specs-${k}`}
                ref={i === 0 ? firstFieldRef : undefined}
                className="text-center px-1"
                value={specsMeasurements?.[k] || ""}
                disabled={disabled}
                inputMode={SIGNED.has(k) ? "text" : "numeric"}
                autoComplete="off"
                onChange={(e) => onChange?.({ ...specsMeasurements, [k]: e.target.value })}
                data-testid={`specs-${k}`}
              />
              {SIGNED.has(k) && (
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={`Change the sign of ${label}`}
                  className="min-h-[44px] min-w-[44px] rounded-xl border border-slate-300 font-mono font-bold text-slate-900 disabled:opacity-50"
                  onClick={() => onChange?.({ ...specsMeasurements, [k]: flipSign(specsMeasurements?.[k]) })}
                  data-testid={`specs-${k}-sign`}
                >
                  ±
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </fieldset>
  );
}

export function SpecsMeasurementsGrid({ specsMeasurements = {}, onChange, disabled, firstFieldRef }) {
  return (
    <div className="mt-4 space-y-4">
      <p className="text-xs font-mono uppercase tracking-widest text-slate-500">
        Spectacle measurements
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <EyeGroup title="Right eye" fields={RIGHT} specsMeasurements={specsMeasurements} onChange={onChange} disabled={disabled} firstFieldRef={firstFieldRef} testid="specs-right-eye" />
        <EyeGroup title="Left eye" fields={LEFT} specsMeasurements={specsMeasurements} onChange={onChange} disabled={disabled} testid="specs-left-eye" />
      </div>
      <div>
        <label className="text-xs font-mono text-slate-700" htmlFor="specs-add">Add</label>
        <Input
          id="specs-add"
          className="text-center px-1 max-w-[8rem]"
          value={specsMeasurements?.add || ""}
          disabled={disabled}
          inputMode="decimal"
          autoComplete="off"
          onChange={(e) => onChange?.({ ...specsMeasurements, add: e.target.value })}
          data-testid="specs-add"
        />
      </div>
    </div>
  );
}
