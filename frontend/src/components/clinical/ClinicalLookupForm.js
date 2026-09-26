import React from "react";
import { Card, Input, Button, Alert } from "../ui";
import { Search } from "lucide-react";
import AadhaarScanner from "../AadhaarScanner";

export function ClinicalLookupForm({
  lookup,
  setLookup,
  doLookup,
  openPatient,
  results,
  more,
  error,
  banner,
  inputRef,
  busy = false,
}) {
  return (
    <Card className="mb-5">
      <form onSubmit={doLookup} className="flex gap-2">
        <Input
          ref={inputRef}
          aria-label="Registration number or name"
          disabled={busy}
          value={lookup}
          onChange={(e) => setLookup(e.target.value)}
          placeholder="Registration number or name"
          data-testid="clinical-lookup-input"
          autoComplete="off"
        />
        <Button type="submit" variant="secondary" disabled={busy} data-testid="clinical-lookup-button">
          <Search className="w-5 h-5" /> Find
        </Button>
      </form>
      <p className="text-xs text-slate-700 mt-2">
        Only patients who have arrived and whose prescription was printed can be opened. Scan the prescription QR with the USB imager at any time.
      </p>
      <AadhaarScanner patientCodeOnly onPatientCode={openPatient} disabled={busy} />
      {error && <Alert className="mt-3">{error}</Alert>}
      {banner && (
        <Alert tone="emerald" className="mt-3">
          {banner}
        </Alert>
      )}
      {results && (
        <div className="mt-3 space-y-2" data-testid="clinical-search-results">
          {results.length === 0 && <p className="text-sm text-slate-700">No arrived and printed patient matches that name.</p>}
          {results.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={busy}
              onClick={() => openPatient(String(p.reg_no))}
              className="w-full min-h-[44px] px-3.5 py-2 rounded-xl border-2 border-slate-300 bg-white text-left hover:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50"
              data-testid={`clinical-search-result-${p.id}`}
            >
              <span className="block font-semibold text-slate-900">#{p.reg_no} {p.full_name}</span>
              <span className="block text-sm text-slate-700">
                {p.age ?? "—"} yrs · {p.gender_label || "—"} · Phone ending {p.phone_last4 || "—"}
              </span>
            </button>
          ))}
          {more && (
            <p className="text-sm font-semibold text-slate-900" data-testid="clinical-search-more">
              More patients match. Type more of the name, or use the registration number on the paper.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
