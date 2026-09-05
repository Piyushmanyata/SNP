import React from "react";

export function MedicinePicker({
  medicines = [],
  selectedIds = [],
  onChange,
  disabled,
  firstFieldRef,
}) {
  if (!medicines.length) {
    return (
      <p className="text-sm text-amber-800" data-testid="medicine-picker-empty">
        No medicines have been added yet. Ask the admin to add the medicines this camp carries.
      </p>
    );
  }
  const toggle = (id) =>
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2" data-testid="medicine-picker">
      {medicines.map((m, index) => {
        const on = selectedIds.includes(m.id);
        return (
          <button
            key={m.id}
            type="button"
            ref={index === 0 ? firstFieldRef : undefined}
            aria-pressed={on}
            disabled={disabled}
            onClick={() => toggle(m.id)}
            className={`min-h-[56px] px-4 rounded-xl text-left text-sm font-semibold border transition-colors ${
              on
                ? "bg-emerald-700 text-white border-emerald-700"
                : "bg-white text-slate-700 border-slate-300 hover:border-emerald-400"
            }`}
            data-testid={`medicine-opt-${m.id}`}
          >
            {m.name}
          </button>
        );
      })}
    </div>
  );
}
