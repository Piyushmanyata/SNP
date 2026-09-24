import React, { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "../lib/api";
import Layout from "../components/Layout";
import { Alert, Card, Stat } from "../components/ui";
import { displayDate, displayDateRange, displayTimeRange, displayTimestamp } from "../lib/dates";
import { SMS_LABELS } from "../lib/sms";

const POLL_MS = 15000;

export default function Board() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");
  const [err, setErr] = useState("");
  const inFlight = useRef(false);
  const seq = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    async function load() {
      if (inFlight.current || document.hidden) return;
      inFlight.current = true;
      const mine = ++seq.current;
      try {
        const r = await api.get("/board");
        if (!mounted.current || mine !== seq.current) return;
        setData(r.data);
        setErr("");
        setStatus(r.data?.state || "current");
      } catch (e) {
        if (!mounted.current || mine !== seq.current) return;
        setErr(formatApiError(e));
        setStatus((s) => (s === "loading" || s === "error" ? "error" : "stale"));
      } finally {
        inFlight.current = false;
      }
    }
    load();
    const id = setInterval(load, POLL_MS);
    const onVis = () => {
      if (!document.hidden) load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      mounted.current = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const stages = data?.stages || {};
  const fulfilment = data?.fulfilment || {};
  const stale = status === "stale";

  return (
    <Layout title="Analytics">
      <div className="space-y-5" data-testid="board-page">
        {status === "loading" && !data && (
          <p data-testid="board-loading">Loading analytics…</p>
        )}
        {status === "error" && (
          <p role="alert">Unable to load analytics: {err}. Retrying automatically.</p>
        )}
        {data?.state === "no_camp" && (
          <p data-testid="board-no-camp">No active camp.</p>
        )}
        {data?.state === "no_day" && (
          <p data-testid="board-no-day">No camp day for today.</p>
        )}
        {stale && (
          <p data-testid="board-stale">
            Showing last snapshot from {displayTimestamp(data?.as_of)}. Refresh failed{err ? `: ${err}` : "."}
          </p>
        )}
        {data && (
          <>
            {data.backups_failing && (
              <div data-testid="board-backups-failing">
                <Alert>Backups failing — tell the admin</Alert>
              </div>
            )}
            {(data.sms_paused || []).length > 0 && (
              <div data-testid="board-sms-paused">
                <Alert>
                  SMS paused after a DLT failure: {data.sms_paused.map((type) => SMS_LABELS[type] || type).join(", ")}. An admin must resume it.
                </Alert>
              </div>
            )}
            <p className="text-sm text-slate-600" data-testid="board-context">
              {data.camp?.name || "No camp"}
              {data.day?.day_date ? ` · ${displayDate(data.day.day_date)}` : ""}
              {data.as_of ? ` · as of ${displayTimestamp(data.as_of)}` : ""}
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="board-kpis">
              <Stat label="Arrived" value={stages.arrived ?? 0} testid="board-arrived" />
              <Stat label="Awaiting Print" value={stages.awaiting_print ?? 0} testid="board-awaiting-print" />
              <Stat label="Awaiting Seen" value={stages.awaiting_seen ?? 0} testid="board-awaiting-seen" />
              <Stat label="Seen" value={stages.seen ?? 0} testid="board-seen" />
              <Stat
                label="Transcription backlog"
                value={stages.transcription_backlog ?? 0}
                tone={(stages.transcription_backlog ?? 0) > 0 ? "amber" : "slate"}
                testid="board-backlog"
              />
              <Stat label="Quiet volunteers" value={data.quiet_count ?? 0} testid="board-quiet-count" />
              <Stat label="SMS failures" value={data.sms_failures ?? 0} tone={(data.sms_failures ?? 0) > 0 ? "amber" : "slate"} testid="board-sms-failures" />
              <Stat label="SMS held back" value={data.sms_not_sent ?? 0} tone={(data.sms_not_sent ?? 0) > 0 ? "amber" : "slate"} testid="board-sms-not-sent" />
              <Stat
                label="Medicine given"
                value={fulfilment.medicine?.fulfilled ?? 0}
                testid="board-medicine-given"
              />
              <Stat
                label="Medicine out of stock"
                value={fulfilment.medicine?.not_available ?? 0}
                testid="board-medicine-oos"
              />
              <Stat
                label="IOL surgery scheduled"
                value={fulfilment.ot?.deferred ?? 0}
                testid="board-ot-scheduled"
              />
              <Stat
                label="Surgery declined"
                value={fulfilment.ot?.declined ?? 0}
                testid="board-ot-declined"
              />
            </div>
            <Card>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="min-w-0">
                  <dt className="text-xs font-mono uppercase tracking-widest text-slate-600">Next OT</dt>
                  <dd className="mt-1 font-semibold text-slate-900 break-words" data-testid="board-next-ot">
                    {data.next_ot
                      ? `${displayDate(data.next_ot.day_date)} · ${data.next_ot.venue} · ${data.next_ot.seats_left} seats`
                      : "No day scheduled"}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-xs font-mono uppercase tracking-widest text-slate-600">Next Specs</dt>
                  <dd className="mt-1 font-semibold text-slate-900 break-words" data-testid="board-next-specs">
                    {data.next_specs
                      ? `${displayDateRange(data.next_specs.day_date, data.next_specs.end_date)} · ${data.next_specs.venue} · ${displayTimeRange(data.next_specs.start_time, data.next_specs.end_time)}`
                      : "No day scheduled"}
                  </dd>
                </div>
              </dl>
            </Card>
            <Card>
              <h3 className="font-display font-bold text-slate-900 mb-3">Registration activity</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="board-activity">
                  <caption className="sr-only">Registration activity by Volunteer</caption>
                  <thead>
                    <tr className="text-left text-slate-500">
                      <th scope="col" className="py-2 min-h-[44px]">Volunteer</th>
                      <th scope="col">Last arrival</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.activity || []).map((row) => (
                      <tr
                        key={row.id}
                        data-quiet={row.quiet ? "true" : "false"}
                        className={row.quiet ? "bg-amber-50" : ""}
                      >
                        <td className="py-2 font-medium min-h-[44px]">{row.name}</td>
                        <td>{displayTimestamp(row.last_arrival_at) || "—"}</td>
                        <td>
                          <span data-testid={`quiet-text-${row.id}`}>
                            {row.quiet ? "Quiet" : "Active"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}
      </div>
    </Layout>
  );
}
