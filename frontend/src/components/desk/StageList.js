import React, { useEffect, useState } from "react";
import { Search } from "lucide-react";
import api, { formatApiError } from "../../lib/api";
import { Alert, Badge, Button, Input, Modal, Spinner, Stat } from "../ui";
import { printedLine } from "./printed";
import { displayDate, displayTime, istDate } from "../../lib/dates";

const LISTS = {
  registered: {
    label: "Registered", tone: "slate",
    about: "Everyone registered in this camp, on any camp day. Newest first.",
    empty: "No one is registered in this camp yet.",
  },
  seen: {
    label: "Seen", tone: "emerald",
    about: "Seen by the doctor, on any camp day. Most recently seen first.",
    empty: "No one has seen the doctor yet.",
  },
  pending: {
    label: "Pending", tone: "amber",
    about: "Printed and not yet seen by the doctor, on any camp day. Longest since print first.",
    empty: "No one is pending. Everyone printed has seen the doctor.",
  },
};

const STAGE_BADGES = {
  booked: { label: "Booked", tone: "slate" },
  awaiting_print: { label: "Awaiting print", tone: "indigo" },
  pending: { label: "Pending", tone: "amber" },
  seen: { label: "Doctor seen", tone: "emerald" },
};

const SEARCH_PAUSE_MS = 300;

function since(at) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(at).getTime()) / 60000));
  return minutes < 60 ? `${minutes} min ago` : `${Math.floor(minutes / 60)} h ${minutes % 60} min ago`;
}

export function StageStat({ stage, value }) {
  const [open, setOpen] = useState(false);
  const { label, tone } = LISTS[stage];
  return (
    <>
      <Stat label={label} value={value} tone={tone} testid={`kpi-${stage}-count`} onClick={() => setOpen(true)} />
      {open && <StageList stage={stage} onClose={() => setOpen(false)} />}
    </>
  );
}

function StageList({ stage, onClose }) {
  const { label, about, empty } = LISTS[stage];
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [list, setList] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setList(null);
    setError("");
    api.get(`/lists/${stage}`, { params: { q: query } }).then(
      ({ data }) => { if (current) setList(data); },
      (err) => { if (current) setError(formatApiError(err)); },
    );
    return () => { current = false; };
  }, [stage, query, attempt]);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(typed.trim()), SEARCH_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [typed]);

  const search = (e) => {
    e.preventDefault();
    setQuery(typed.trim());
    setAttempt((n) => n + 1);
  };
  const rows = list?.patients;
  const total = list && `${list.total.toLocaleString("en-IN")}${list.total_is_floor ? "+" : ""}`;

  return (
    <Modal open onClose={onClose} title={label} size="lg">
      <p className="text-sm text-slate-600 mb-3">{about}</p>
      <form onSubmit={search} role="search" className="flex gap-2 mb-3">
        <Input value={typed} onChange={(e) => setTyped(e.target.value)}
          aria-label="Name, phone or registration number" placeholder="Name, phone or reg no"
          autoComplete="off" enterKeyHint="search" data-testid="list-search-input" />
        <Button type="submit" variant="secondary" aria-label={`Search ${label}`} data-testid="list-search-button">
          <Search className="w-5 h-5" />
        </Button>
      </form>
      <Alert>{error}</Alert>
      {!list && !error && (
        <span role="status" aria-label={`Loading ${label}`}><Spinner className="w-6 h-6 text-emerald-700" /></span>
      )}
      {rows?.length === 0 && (
        <p className="text-slate-700" data-testid="list-empty">{query ? `No one matches “${query}”.` : empty}</p>
      )}
      {rows?.length > 0 && rows.length < list.total && (
        <p className="text-sm font-semibold text-slate-700 mb-2" data-testid="list-shown">
          {query
            ? `${rows.length} of ${total} match. Type more of the name, or the whole phone number.`
            : `Showing ${rows.length} of ${total}. Search by name, phone or registration number to find anyone else.`}
        </p>
      )}
      {rows?.length > 0 && (
        <ul className="space-y-2" data-testid={`${stage}-list`}>
          {rows.map((p) => (
            <li key={p.id} className="p-3 rounded-xl border border-slate-200" data-testid={`${stage}-row-${p.reg_no}`}>
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-mono font-bold text-emerald-700">#{p.reg_no}</span>
                <span className="font-semibold text-slate-900">{p.full_name}</span>
                <span className="text-xs text-slate-600">{p.gender_label} · {p.age ?? "-"} yrs</span>
                {stage === "registered" && (
                  <Badge tone={STAGE_BADGES[p.stage].tone}>{STAGE_BADGES[p.stage].label}</Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 text-sm text-slate-700">
                {p.phone && (
                  <a href={`tel:${p.phone}`} className="min-h-[44px] inline-flex items-center font-semibold text-emerald-800 underline">
                    {p.phone}
                  </a>
                )}
                {stage === "registered" && p.created_at && (
                  <span>Registered {displayDate(istDate(p.created_at))}, {displayTime(p.created_at)}</span>
                )}
                {stage === "pending" && <span>{printedLine(p)} · {since(p.printed_at)}</span>}
                {stage === "seen" && <span>Seen {displayTime(p.seen_at)} · {since(p.seen_at)}</span>}
                {stage === "pending" && istDate(p.arrived_at) < list.today && (
                  <span className="font-semibold text-amber-800" data-testid={`pending-earlier-${p.reg_no}`}>
                    Arrived {displayDate(istDate(p.arrived_at))}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
