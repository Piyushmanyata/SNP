import React from "react";
import { Input } from "../ui";

const SPECS_FIELDS = ["r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add"];

export function SpecsMeasurementsGrid({ specsMeasurements = {}, onChange, disabled }) {
  return (
    <>
      <p className="text-xs font-mono uppercase tracking-widest text-slate-500 mt-4 mb-2">
        Spectacle Measurements
      </p>
      <div className="grid grid-cols-3 sm:grid-cols-7 gap-2">
        {SPECS_FIELDS.map((k) => (
          <div key={k}>
            <label className="text-[10px] font-mono text-slate-400 uppercase">
              {k.replace("_", " ")}
            </label>
            <Input
              className="text-center px-1"
              value={specsMeasurements?.[k] || ""}
              disabled={disabled}
              inputMode="decimal"
              autoComplete="off"
              onChange={(e) =>
                onChange?.({
                  ...specsMeasurements,
                  [k]: e.target.value,
                })
              }
              data-testid={`specs-${k}`}
            />
          </div>
        ))}
      </div>
    </>
  );
}
