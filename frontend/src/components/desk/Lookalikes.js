import React from "react";
import { Badge, Button } from "../ui";

function status(r) {
  if (r.queue_status === "seen") return <Badge tone="rose">Doctor seen</Badge>;
  if (r.printed_at) return <Badge tone="indigo">Printed</Badge>;
  if (r.arrived_at) return <Badge tone="emerald">Arrived</Badge>;
  return <Badge tone="amber">Booked</Badge>;
}

export function Lookalikes({ rows, busy, onOpen, onDifferent }) {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4" data-testid="lookalikes">
      <p className="font-display font-bold text-slate-900">Already registered?</p>
      <p className="text-xs text-amber-900 mt-1 mb-3">
        Someone with this name and a similar age is in this camp. Open them if this is the same person.
      </p>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-white p-2" data-testid={`lookalike-${r.reg_no}`}>
            <span className="font-mono font-bold text-emerald-700">#{r.reg_no}</span>
            <span className="font-semibold text-slate-900">{r.full_name}</span>
            <span className="text-xs text-slate-600">
              {r.age ?? "-"} yrs{r.phone ? ` · phone ending ${r.phone.slice(-4)}` : ""}
            </span>
            {status(r)}
            <Button size="sm" variant="outline" className="ml-auto" disabled={busy} onClick={() => onOpen(r)} data-testid={`lookalike-open-${r.reg_no}`}>
              This is them
            </Button>
          </li>
        ))}
      </ul>
      <Button size="sm" className="mt-3" disabled={busy} onClick={onDifferent} data-testid="lookalike-different">
        Different person — register
      </Button>
    </div>
  );
}
