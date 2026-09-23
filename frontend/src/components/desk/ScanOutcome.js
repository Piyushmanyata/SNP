import React from "react";
import { Button, Badge, Alert, Input, Field } from "../ui";
import { Printer } from "lucide-react";
import { displayDate } from "../../lib/dates";

const FIELD_LABELS = {
  full_name: "Name",
  age: "Age",
  gender: "Gender",
  dob: "Date of birth",
  aadhaar_last4: "Aadhaar last-4",
  address: "Address",
};

export function ArrivedCard({ registration, onPrint }) {
  const seen = registration.queue_status === "seen";
  return (
    <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4" data-testid="scan-arrived">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono font-bold text-emerald-700">#{registration.reg_no}</span>
        <span className="font-semibold text-slate-900">{registration.full_name}</span>
        <Badge tone="emerald">Arrived</Badge>
        {registration.camp_day_changed_from && (
          <span data-testid="scan-day-changed">
            <Badge tone="amber">Moved from {displayDate(registration.camp_day_changed_from)}</Badge>
          </span>
        )}
      </div>
      <p className="text-xs text-slate-600 mt-1">
        {registration.gender_label} · {registration.age ?? "-"} yrs
        {registration.phone ? ` · ${registration.phone}` : ""}
      </p>
      <div className="flex gap-2 mt-3">
        {seen ? (
          <span className="text-xs text-slate-600" data-testid="scan-already-seen">
            The doctor has already seen this patient. There is nothing to print.
          </span>
        ) : (
          <Button size="lg" onClick={() => onPrint(registration)} data-testid="scan-print-button">
            <Printer className="w-4 h-4" /> Print prescription
          </Button>
        )}
      </div>
    </div>
  );
}

export function MismatchReview({ registration, diff, busy, onConfirm }) {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4" data-testid="mismatch-review">
      <p className="font-display font-bold text-slate-900">Mismatch review</p>
      <p className="text-xs text-amber-900 mt-1 mb-3">
        Reg #{registration.reg_no} was typed in. The card is the authority on identity.
        Confirming replaces the stored values and lets the prescription print.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-600">
            <th className="py-1">Field</th>
            <th className="py-1">Stored</th>
            <th className="py-1">On the card</th>
          </tr>
        </thead>
        <tbody>
          {diff.map((row) => {
            const shown = (value) => (row.field === "dob" ? displayDate(value) || "—" : value ?? "—");
            return (
              <tr key={row.field} className="border-t border-amber-200" data-testid={`diff-${row.field}`}>
                <td className="py-1 text-slate-600">{FIELD_LABELS[row.field] || row.field}</td>
                <td className="py-1 text-slate-700">{shown(row.stored)}</td>
                <td className="py-1 font-semibold text-slate-900">{shown(row.card)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs text-slate-600 mt-3">
        Household phone, camp day and registration number are kept.
      </p>
      <Button
        size="sm"
        className="mt-3"
        onClick={onConfirm}
        disabled={busy}
        data-testid="mismatch-confirm-button"
      >
        Confirm card
      </Button>
    </div>
  );
}

export function AmbiguousMatch({ registrations, busy, onSelect }) {
  return (
    <div className="rounded-xl border border-red-300 bg-red-50 p-4" data-testid="scan-ambiguous">
      <p className="font-display font-bold text-slate-900">More than one typed record matches</p>
      <p className="text-xs text-red-900 mt-1 mb-3">
        Choose the registration that is this person. Nothing is checked in until you do.
      </p>
      <ul className="space-y-2 text-sm">
        {registrations.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              className="min-h-[44px] w-full rounded-xl border border-red-200 bg-white px-3 text-left font-semibold text-slate-900"
              data-testid={`ambiguous-${r.reg_no}`}
              disabled={busy}
              onClick={() => onSelect(r.id)}
            >
              <span className="font-mono">#{r.reg_no}</span> {r.full_name} · {r.age ?? "-"} yrs
              {r.phone ? ` · ${r.phone}` : ""}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function NoMatch({ card, phone, setPhone, busy, onSubmit }) {
  const ready = /^\d{10}$/.test(phone || "");
  return (
    <form
      className="rounded-xl border border-slate-300 bg-slate-50 p-4"
      data-testid="scan-no-match"
      onSubmit={(e) => { e.preventDefault(); if (ready && !busy) onSubmit(); }}
    >
      <p className="font-display font-bold text-slate-900">No booking found for this card</p>
      <div className="mt-3 space-y-1 text-sm" data-testid="door-card-readonly">
        <p data-testid="door-card-name"><span className="text-slate-600 mr-2">Name:</span>{card?.full_name}</p>
        <p><span className="text-slate-600 mr-2">Age:</span>{card?.age ?? "—"}</p>
        <p><span className="text-slate-600 mr-2">Gender:</span>{card?.gender || "—"}</p>
        <p><span className="text-slate-600 mr-2">Address:</span>{card?.address || "—"}</p>
      </div>
      <div className="mt-3">
        <Field label="Household mobile" required>
          <Input
            value={phone}
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
            inputMode="numeric"
            autoComplete="tel"
            enterKeyHint="done"
            data-testid="door-phone-input"
          />
        </Field>
      </div>
      <Button
        type="submit"
        size="sm"
        className="mt-3"
        disabled={!ready || busy}
        data-testid="door-register-button"
      >
        Register
      </Button>
    </form>
  );
}

export function ScanOutcome({ result, busy, onPrint, onConfirm, onChoose, phone, setPhone, onWalkIn }) {
  if (!result) return null;
  if (result.outcome === "arrived") {
    return (
      <ArrivedCard registration={result.registration} onPrint={onPrint} />
    );
  }
  if (result.outcome === "mismatch_review") {
    return (
      <MismatchReview
        registration={result.registration}
        diff={result.diff}
        busy={busy}
        onConfirm={onConfirm}
      />
    );
  }
  if (result.outcome === "ambiguous") {
    return <AmbiguousMatch registrations={result.registrations} busy={busy} onSelect={onChoose} />;
  }
  if (result.outcome === "no_match") {
    return (
      <NoMatch
        card={result.card}
        phone={phone}
        setPhone={setPhone}
        busy={busy}
        onSubmit={onWalkIn}
      />
    );
  }
  return <Alert>Unrecognised scan outcome.</Alert>;
}
