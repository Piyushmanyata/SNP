import React, { useState } from "react";
import api, { formatApiError } from "../../lib/api";
import { Button, Badge } from "../ui";
import { Pill, Glasses, Scissors, Printer } from "lucide-react";

export const STATION_OPTS = {
  medicine: ["fulfilled", "not_available", "not_required"],
  specs: ["fulfilled", "deferred", "not_required"],
  ot: ["fulfilled", "deferred", "not_required"],
};

export const STATION_META = {
  medicine: { label: "Medicine", icon: Pill },
  specs: { label: "Spectacles to be made", icon: Glasses },
  ot: { label: "OT / Surgery", icon: Scissors },
};

export function FulfilmentStation({
  type,
  data,
  otDays = [],
  specsDays = [],
  onDone,
  navigate,
  setBanner,
  setError,
}) {
  const meta = STATION_META[type] || { label: type, icon: Pill };
  const Icon = meta.icon;
  const existing = data?.fulfilments?.find((f) => f.item_type === type);
  const slip = data?.slips?.find((s) => s.item_type === type && s.active);

  const [status, setStatus] = useState(existing?.status || "");
  const [otDayId, setOtDayId] = useState(existing?.ot_schedule_day_id || "");
  const [specsDayId, setSpecsDayId] = useState(existing?.specs_collection_day_id || "");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const { data: res } = await api.post("/clinical/fulfilment", {
        transcription_id: data.transcription.id,
        item_type: type,
        status,
        ot_schedule_day_id: type === "ot" ? otDayId : null,
        specs_collection_day_id: type === "specs" ? specsDayId : null,
      });
      setBanner(`${meta.label}: ${status}`);
      if (res.slip) {
        navigate(`/print/slip/${res.slip.id}`);
      } else {
        onDone();
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${type}`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-5 h-5 text-emerald-600" />
        <p className="font-semibold text-slate-900 text-sm">{meta.label}</p>
      </div>
      <select
        className="w-full min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        data-testid={`station-${type}-status`}
      >
        <option value="">Select…</option>
        {STATION_OPTS[type]?.map((s) => (
          <option key={s} value={s}>
            {s.replace(/_/g, " ")}
          </option>
        ))}
      </select>

      {status === "deferred" && type === "specs" && (
        <select
          className="w-full mt-2 min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm"
          value={specsDayId}
          onChange={(e) => setSpecsDayId(e.target.value)}
          data-testid="specs-day-select-fulfil"
        >
          <option value="">Select Specs collection day…</option>
          {specsDays.map((d) => (
            <option key={d.id} value={d.id} disabled={d.seats_free <= 0 && d.id !== specsDayId}>
              {d.day_date} · {d.venue} ({d.seats_free} free)
            </option>
          ))}
        </select>
      )}
      {status === "deferred" && type === "ot" && (
        <select
          className="w-full mt-2 min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm"
          value={otDayId}
          onChange={(e) => setOtDayId(e.target.value)}
          data-testid="ot-day-select-fulfil"
        >
          <option value="">Select OT day…</option>
          {otDays.map((d) => (
            <option key={d.id} value={d.id} disabled={d.seats_free <= 0 && d.id !== otDayId}>
              {d.day_date} · {d.venue} ({d.seats_free} free)
            </option>
          ))}
        </select>
      )}

      <Button
        size="sm"
        className="w-full mt-3"
        onClick={save}
        disabled={!status || busy}
        data-testid={`station-${type}-save`}
      >
        Save
      </Button>

      {existing && (
        <Badge
          tone={existing.status === "deferred" ? "amber" : "emerald"}
          className="mt-3"
        >
          {existing.status.replace(/_/g, " ")}
        </Badge>
      )}
      {slip && (
        <Button
          size="sm"
          variant="outline"
          className="w-full mt-2"
          onClick={() => navigate(`/print/slip/${slip.id}`)}
          data-testid={`station-${type}-print-token`}
        >
          <Printer className="w-4 h-4" /> Reprint Token
        </Button>
      )}
    </div>
  );
}
