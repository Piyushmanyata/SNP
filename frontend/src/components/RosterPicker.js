import React, { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "../lib/api";
import { writeRoster } from "../lib/roster";
import { Alert, Button, Input, Modal } from "./ui";

export default function RosterPicker({ open, onPicked }) {
  const [entries, setEntries] = useState([]);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    setErr("");
    api
      .get("/roster")
      .then((r) => setEntries(r.data.entries || []))
      .catch((e) => setErr(formatApiError(e)));
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const filtered = entries.filter((e) =>
    (e.name || "").toLowerCase().includes(q.trim().toLowerCase()),
  );

  return (
    <Modal open={open} onClose={() => {}} title="Who is at this desk?">
      {err && (
        <Alert className="mb-3">
          {err}
          <Button className="mt-2 w-full" onClick={load}>Retry</Button>
        </Alert>
      )}
      {!err && entries.length === 0 && (
        <p className="text-sm text-slate-600 mb-3">No roster for this camp yet. Ask an admin.</p>
      )}
      <Input
        data-testid="roster-search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search names"
        className="mb-3"
      />
      <div className="grid gap-2">
        {filtered.map((e) => (
          <Button
            key={e.id}
            size="lg"
            className="w-full"
            data-testid={`roster-pick-${e.id}`}
            onClick={() => {
              writeRoster({ id: e.id, name: e.name });
              onPicked(e);
            }}
          >
            {e.name}
          </Button>
        ))}
      </div>
    </Modal>
  );
}
