import React, { useEffect, useState } from "react";
import api, { formatApiError } from "../../lib/api";
import { Alert, Modal, Spinner, Stat } from "../ui";
import { printedLine } from "./printed";

function sincePrint(printedAt) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(printedAt).getTime()) / 60000));
  return minutes < 60 ? `${minutes} min ago` : `${Math.floor(minutes / 60)} h ${minutes % 60} min ago`;
}

export function PendingStat({ value }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Stat label="Pending" value={value} tone="amber" testid="kpi-pending-count" onClick={() => setOpen(true)} />
      <PendingList open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function PendingList({ open, onClose }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return undefined;
    let current = true;
    setRows(null);
    setError("");
    api.get("/pending").then(
      ({ data }) => { if (current) setRows(data.patients); },
      (err) => { if (current) setError(formatApiError(err)); },
    );
    return () => { current = false; };
  }, [open]);

  return (
    <Modal open={open} onClose={onClose} title="Pending" size="lg">
      <p className="text-sm text-slate-600 mb-3">Printed today and not yet seen by the doctor. Longest since print first.</p>
      <Alert>{error}</Alert>
      {!rows && !error && <Spinner className="w-6 h-6 text-emerald-700" />}
      {rows?.length === 0 && <p className="text-slate-700" data-testid="pending-empty">No one is pending. Everyone printed today has seen the doctor.</p>}
      {rows?.length > 0 && (
        <ul className="space-y-2" data-testid="pending-list">
          {rows.map((p) => (
            <li key={p.id} className="p-3 rounded-xl border border-slate-200" data-testid={`pending-row-${p.reg_no}`}>
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-mono font-bold text-emerald-700">#{p.reg_no}</span>
                <span className="font-semibold text-slate-900">{p.full_name}</span>
                <span className="text-xs text-slate-600">{p.gender_label} · {p.age ?? "-"} yrs</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 text-sm text-slate-700">
                {p.phone && (
                  <a href={`tel:${p.phone}`} className="min-h-[44px] inline-flex items-center font-semibold text-emerald-800 underline">
                    {p.phone}
                  </a>
                )}
                <span>{printedLine(p)} · {sincePrint(p.printed_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
