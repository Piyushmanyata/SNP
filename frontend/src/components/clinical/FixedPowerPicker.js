import React, { useState } from "react";
import { Field } from "../ui";

export function formatPower(value) {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (Number.isNaN(n)) return "";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
}

function PowerRow({ powers, value, onSelect, disabled, testidPrefix, firstFieldRef }) {
  const sorted = [...powers].sort((a, b) => a.value - b.value);
  const minus = sorted.filter((p) => p.value < 0);
  const plus = sorted.filter((p) => p.value >= 0);
  const chip = (p, index) => (
    <button
      key={p.id}
      type="button"
      ref={index === 0 && firstFieldRef ? firstFieldRef : undefined}
      aria-pressed={value === p.value}
      disabled={disabled}
      onClick={() => onSelect(p.value)}
      className={`min-h-[44px] min-w-[72px] px-3 rounded-xl font-mono text-sm font-semibold border transition-colors ${
        value === p.value
          ? "bg-emerald-700 text-white border-emerald-700"
          : "bg-white text-slate-700 border-slate-300 hover:border-emerald-400"
      }`}
      data-testid={`${testidPrefix}-${p.value}`}
    >
      {formatPower(p.value)}
    </button>
  );
  return (
    <div className="space-y-2">
      {minus.length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid={`${testidPrefix}-minus`}>
          {minus.map((p, i) => chip(p, i))}
        </div>
      )}
      {minus.length > 0 && plus.length > 0 && <hr className="border-slate-200" />}
      {plus.length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid={`${testidPrefix}-plus`}>
          {plus.map((p, i) => chip(p, minus.length ? i + 1 : i))}
        </div>
      )}
    </div>
  );
}

export function FixedPowerPicker({
  powers = [],
  valueR = null,
  valueL = null,
  onChange,
  disabled,
  firstFieldRef,
}) {
  const [chosen, setChosen] = useState(null);
  const split = chosen ?? (valueR !== null && valueL !== null && valueR !== valueL);

  if (!powers.length) {
    return (
      <p className="text-sm text-amber-800" data-testid="fixed-power-empty">
        No fixed powers have been added yet. Ask the admin to add the powers this camp carries.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="fixed-power-picker">
      <label className="flex items-center gap-2 min-h-[44px] text-sm">
        <input
          type="checkbox"
          checked={split}
          disabled={disabled}
          onChange={(e) => {
            setChosen(e.target.checked);
            if (!e.target.checked) onChange(valueR, valueR);
          }}
          data-testid="fixed-power-split"
        />
        <span>Different power for each eye</span>
      </label>

      {split ? (
        <>
          <Field label="Right eye">
            <PowerRow
              powers={powers}
              value={valueR}
              onSelect={(v) => onChange(v, valueL)}
              disabled={disabled}
              testidPrefix="fixed-power-r"
              firstFieldRef={firstFieldRef}
            />
          </Field>
          <Field label="Left eye">
            <PowerRow
              powers={powers}
              value={valueL}
              onSelect={(v) => onChange(valueR, v)}
              disabled={disabled}
              testidPrefix="fixed-power-l"
            />
          </Field>
        </>
      ) : (
        <Field label="Power for both eyes">
          <PowerRow
            powers={powers}
            value={valueR}
            onSelect={(v) => onChange(v, v)}
            disabled={disabled}
            testidPrefix="fixed-power-both"
            firstFieldRef={firstFieldRef}
          />
        </Field>
      )}
    </div>
  );
}
