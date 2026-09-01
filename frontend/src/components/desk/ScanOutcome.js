import React from "react";
import { Button, Badge, Alert } from "../ui";
import { Printer, CheckCircle2, UserPlus, Search } from "lucide-react";

const FIELD_LABELS = {
  full_name: "Name",
  age: "Age",
  gender: "Gender",
  dob: "Date of birth",
  aadhaar_last4: "Aadhaar last-4",
  address: "Address",
};

export function ArrivedCard({ registration, onPrint, onMarkSeen }) {
  return (
    <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-4" data-testid="scan-arrived">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono font-bold text-emerald-700">#{registration.reg_no}</span>
        <span className="font-semibold text-slate-900">{registration.full_name}</span>
        <Badge tone="emerald">Checked in</Badge>
        {registration.camp_day_changed_from && (
          <span data-testid="scan-day-changed">
            <Badge tone="amber">Moved from {registration.camp_day_changed_from}</Badge>
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500 mt-1">
        {registration.gender_label} · {registration.age ?? "-"} yrs
        {registration.phone ? ` · ${registration.phone}` : ""}
      </p>
      <div className="flex gap-2 mt-3">
        <Button size="sm" onClick={() => onPrint(registration)} data-testid="scan-print-button">
          <Printer className="w-4 h-4" /> Print prescription
        </Button>
        {registration.queue_status !== "seen" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onMarkSeen(registration)}
            disabled={!registration.printed_at}
            data-testid="scan-mark-seen-button"
          >
            <CheckCircle2 className="w-4 h-4" /> Seen
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
        Confirming replaces the stored values and checks the patient in.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-1">Field</th>
            <th className="py-1">Stored</th>
            <th className="py-1">On the card</th>
          </tr>
        </thead>
        <tbody>
          {diff.map((row) => (
            <tr key={row.field} className="border-t border-amber-200" data-testid={`diff-${row.field}`}>
              <td className="py-1 text-slate-500">{FIELD_LABELS[row.field] || row.field}</td>
              <td className="py-1 text-slate-700">{row.stored ?? "—"}</td>
              <td className="py-1 font-semibold text-slate-900">{row.card ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-500 mt-3">
        Household phone, camp day and registration number are kept.
      </p>
      <Button
        size="sm"
        className="mt-3"
        onClick={onConfirm}
        disabled={busy}
        data-testid="mismatch-confirm-button"
      >
        Confirm card and check in
      </Button>
    </div>
  );
}

export function AmbiguousMatch({ registrations }) {
  return (
    <div className="rounded-xl border border-red-300 bg-red-50 p-4" data-testid="scan-ambiguous">
      <p className="font-display font-bold text-slate-900">More than one typed record matches</p>
      <p className="text-xs text-red-900 mt-1 mb-3">
        Find the right registration by name below, then check the patient in from there.
      </p>
      <ul className="space-y-1 text-sm">
        {registrations.map((r) => (
          <li key={r.id} data-testid={`ambiguous-${r.reg_no}`}>
            <span className="font-mono font-bold text-slate-700">#{r.reg_no}</span>{" "}
            {r.full_name} · {r.age ?? "-"} yrs
          </li>
        ))}
      </ul>
    </div>
  );
}

export function NoMatch({ card, onRegisterNew }) {
  return (
    <div className="rounded-xl border border-slate-300 bg-slate-50 p-4" data-testid="scan-no-match">
      <p className="font-display font-bold text-slate-900">No booking found for this card</p>
      <p className="text-xs text-slate-600 mt-1">
        {card?.full_name} · {card?.age ?? "-"} yrs. Search by name or phone first — they may have
        registered under a different spelling.
      </p>
      <div className="flex items-center gap-2 mt-3 text-xs text-slate-500">
        <Search className="w-4 h-4" /> Use the search below before registering anyone.
      </div>
      <Button
        size="sm"
        variant="outline"
        className="mt-3"
        onClick={onRegisterNew}
        data-testid="register-walk-in-button"
      >
        <UserPlus className="w-4 h-4" /> Register as new walk-in
      </Button>
    </div>
  );
}

export function ScanOutcome({ result, busy, onPrint, onMarkSeen, onConfirm, onRegisterNew }) {
  if (!result) return null;
  if (result.outcome === "arrived") {
    return (
      <ArrivedCard registration={result.registration} onPrint={onPrint} onMarkSeen={onMarkSeen} />
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
    return <AmbiguousMatch registrations={result.registrations} />;
  }
  if (result.outcome === "no_match") {
    return <NoMatch card={result.card} onRegisterNew={onRegisterNew} />;
  }
  return <Alert>Unrecognised scan outcome.</Alert>;
}
