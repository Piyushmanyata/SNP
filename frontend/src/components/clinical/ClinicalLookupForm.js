import React from "react";
import { Card, Input, Button, Alert } from "../ui";
import { ScanLine } from "lucide-react";

export function ClinicalLookupForm({
  lookup,
  setLookup,
  doLookup,
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
          aria-label="Patient registration number or prescription QR"
          disabled={busy}
          value={lookup}
          onChange={(e) => setLookup(e.target.value)}
          placeholder="Type Reg # or scan patient QR (USB wedge)"
          data-testid="clinical-lookup-input"
          autoComplete="off"
        />
        <Button type="submit" variant="secondary" disabled={busy} data-testid="clinical-lookup-button">
          <ScanLine className="w-5 h-5" /> Find
        </Button>
      </form>
      <p className="text-xs text-slate-700 mt-2">
        Only patients marked <b>Seen</b> are eligible.
      </p>
      {error && <Alert className="mt-3">{error}</Alert>}
      {banner && (
        <Alert tone="emerald" className="mt-3">
          {banner}
        </Alert>
      )}
    </Card>
  );
}
