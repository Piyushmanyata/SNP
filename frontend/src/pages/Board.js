import React, { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "../lib/api";
import Layout from "../components/Layout";
import { Card, ErrorCard, Stat } from "../components/ui";
import { OPERATOR_LINES } from "../lib/operatorLines";

export default function Board() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api
      .get("/board")
      .then((r) => {
        setData(r.data);
        setErr("");
      })
      .catch((e) => setErr(formatApiError(e)));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <Layout title="Camp-day board">
      {err && <ErrorCard message={err} />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Arrived today" value={data.arrived_today} />
            <Stat label="Seen today" value={data.seen_today} />
            <Stat
              label="Transcription backlog"
              value={data.transcription_backlog}
              tone={data.transcription_backlog > 0 ? "amber" : "slate"}
              testid="board-backlog"
            />
            <Stat label="SMS failures today" value={data.sms_failed_today} />
          </div>
          <Card>
            <h3 className="font-display font-bold text-slate-900 mb-3">Registration desks</h3>
            <table className="w-full text-sm" data-testid="board-desks">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-2">Desk</th>
                  <th>Last 15 min</th>
                  <th>Last 60 min</th>
                </tr>
              </thead>
              <tbody>
                {(data.desks || []).map((d) => (
                  <tr
                    key={d.account_id}
                    data-quiet={d.quiet ? "true" : "false"}
                    className={d.quiet ? "bg-amber-50" : ""}
                  >
                    <td className="py-2 font-medium">{d.name}</td>
                    <td>{d.last_15m}</td>
                    <td>{d.last_60m}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {OPERATOR_LINES.filter((l) => l.key !== "rx").map((l) => (
              <Stat key={l.key} label={l.label} value={data.lines?.[l.key] ?? 0} />
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Stat
              label="Next OT day seats left"
              value={data.next_ot_day ? data.next_ot_day.seats_left : "No day scheduled"}
            />
            <Stat
              label="Next Specs day seats left"
              value={data.next_specs_day ? data.next_specs_day.seats_left : "No day scheduled"}
            />
          </div>
        </div>
      )}
    </Layout>
  );
}
