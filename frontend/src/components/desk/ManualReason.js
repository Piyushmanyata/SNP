import React from "react";
import { Button, Field, Input } from "../ui";

const REASONS = [
  { code: "no_card", label: "No Aadhaar card" },
  { code: "card_unreadable", label: "Card won't scan" },
  { code: "scanner_down", label: "Scanner not working" },
  { code: "other", label: "Other" },
];

export const EMPTY_REASON = Object.freeze({ code: "", note: "" });

export function cardInHand(reason) {
  return reason.code === "card_unreadable" || reason.code === "scanner_down";
}

export function reasonReady(reason) {
  return Boolean(reason.code) && (reason.code !== "other" || Boolean(reason.note.trim()));
}

export function reasonBody(reason) {
  return { code: reason.code, note: reason.code === "other" ? reason.note.trim() : null };
}

export function ManualReason({ reason, onChange, testid = "manual-reason" }) {
  return (
    <fieldset className="space-y-2" data-testid={testid}>
      <legend className="text-sm font-semibold text-slate-900 mb-2">
        Why is the card not scanned? <span className="text-rose-600">*</span>
      </legend>
      <div className="flex flex-wrap gap-2">
        {REASONS.map((r) => (
          <Button
            key={r.code}
            type="button"
            size="sm"
            variant={reason.code === r.code ? "primary" : "outline"}
            aria-pressed={reason.code === r.code}
            onClick={() => onChange({ ...reason, code: r.code })}
            data-testid={`${testid}-${r.code}`}
          >
            {r.label}
          </Button>
        ))}
      </div>
      {reason.code === "other" && (
        <Field label="Why" required>
          <Input
            value={reason.note}
            onChange={(e) => onChange({ ...reason, note: e.target.value })}
            maxLength={200}
            data-testid={`${testid}-note`}
          />
        </Field>
      )}
    </fieldset>
  );
}
