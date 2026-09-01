import React, { useState, useEffect, useCallback, useMemo } from "react";
import api, { formatApiError } from "../../lib/api";
import { Button, Badge } from "../ui";
import { Pill, Glasses, Scissors, Printer } from "lucide-react";

export const FULFILMENT_LINES = {
  medicine: {
    label: "Medicine",
    icon: Pill,
    itemType: "medicine",
    statuses: ["fulfilled", "not_available", "not_required"],
  },
  specs_fixed: {
    label: "Fixed-power specs",
    icon: Glasses,
    itemType: "specs",
    statuses: ["fulfilled", "not_required"],
    needsMeasurements: true,
  },
  specs_made: {
    label: "Spectacles to be made",
    icon: Glasses,
    itemType: "specs",
    statuses: ["deferred"],
    needsMeasurements: true,
    dayField: "specs_collection_day_id",
    dayLabel: "Specs collection day",
  },
  ot: {
    label: "OT / Surgery",
    icon: Scissors,
    itemType: "ot",
    statuses: ["fulfilled", "deferred", "not_required"],
    dayField: "ot_schedule_day_id",
    dayLabel: "OT Schedule Day",
  },
};

export const LINE_ORDER = ["medicine", "specs_fixed", "specs_made", "ot"];

export function hasMeasurements(transcription) {
  const m = transcription?.specs_measurements || {};
  return Boolean(String(m.r_sph || "").trim() && String(m.l_sph || "").trim());
}

export function earliestFreeDay(days, currentId) {
  if (currentId) return currentId;
  const free = days.filter((d) => d.seats_free > 0);
  return free.length ? free[0].id : "";
}

function DayPicker({ line, days, value, onChange }) {
  const noneFree = days.every((d) => d.seats_free <= 0);
  return (
    <>
      <select
        className="w-full mt-2 min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`${line.dayField}-select`}
      >
        <option value="">Select {line.dayLabel}…</option>
        {days.map((d) => (
          <option key={d.id} value={d.id} disabled={d.seats_free <= 0 && d.id !== value}>
            {d.day_date} · {d.venue}
            {d.seats_free <= 0 ? " (full)" : ` (${d.seats_free} free)`}
          </option>
        ))}
      </select>
      {noneFree && (
        <p className="text-xs text-rose-700 mt-2" data-testid={`${line.dayField}-none-free`}>
          Every {line.dayLabel} is full. Call the admin to add one.
        </p>
      )}
    </>
  );
}

export function FulfilmentStation({
  line: lineKey,
  data,
  otDays = [],
  specsDays = [],
  onDone,
  navigate,
  setBanner,
  setError,
}) {
  const line = FULFILMENT_LINES[lineKey];
  const Icon = line.icon;
  const days = line.dayField === "ot_schedule_day_id" ? otDays : specsDays;

  const existing = useMemo(() => {
    const found = data?.fulfilments?.find((f) => f.item_type === line.itemType);
    return found && line.statuses.includes(found.status) ? found : null;
  }, [data, line]);
  const slip = data?.slips?.find((s) => s.item_type === line.itemType && s.active);
  const measurementsMissing = line.needsMeasurements && !hasMeasurements(data?.transcription);

  const [status, setStatus] = useState(existing?.status || "");
  const [dayId, setDayId] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setStatus(line.statuses.length === 1 ? line.statuses[0] : existing?.status || "");
  }, [existing?.status, line]);

  useEffect(() => {
    if (!line.dayField) return;
    setDayId(earliestFreeDay(days, existing?.[line.dayField] || ""));
  }, [days, existing, line.dayField]);

  const needsDay = Boolean(line.dayField) && status === "deferred";

  const save = useCallback(async () => {
    if (!data?.transcription?.id) return;
    setBusy(true);
    setError("");
    try {
      const { data: res } = await api.post("/clinical/fulfilment", {
        transcription_id: data.transcription.id,
        item_type: line.itemType,
        status,
        ot_schedule_day_id: line.dayField === "ot_schedule_day_id" ? dayId || null : null,
        specs_collection_day_id: line.dayField === "specs_collection_day_id" ? dayId || null : null,
      });
      setBanner(`${line.label}: ${status.replace(/_/g, " ")}`);
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
  }, [data?.transcription?.id, line, status, dayId, navigate, onDone, setBanner, setError]);

  return (
    <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${lineKey}`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-5 h-5 text-emerald-600" />
        <p className="font-semibold text-slate-900 text-sm">{line.label}</p>
      </div>

      {line.statuses.length === 1 ? (
        <p className="text-xs text-slate-500">
          Assign a {line.dayLabel} and print the Token.
        </p>
      ) : (
        <select
          className="w-full min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid={`station-${lineKey}-status`}
        >
          <option value="">Select…</option>
          {line.statuses.map((s) => (
            <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
          ))}
        </select>
      )}

      {needsDay && (
        <DayPicker line={line} days={days} value={dayId} onChange={setDayId} />
      )}

      {measurementsMissing && (
        <p className="text-xs text-amber-800 mt-2" data-testid={`station-${lineKey}-needs-power`}>
          Record the prescribed power for both eyes before recording this line.
        </p>
      )}

      <Button
        size="sm"
        className="w-full mt-3"
        onClick={save}
        disabled={!status || busy || measurementsMissing || (needsDay && !dayId)}
        data-testid={`station-${lineKey}-save`}
      >
        Save
      </Button>

      {existing && (
        <Badge tone={existing.status === "deferred" ? "amber" : "emerald"} className="mt-3">
          {existing.status.replace(/_/g, " ")}
        </Badge>
      )}
      {existing && slip && (
        <Button
          size="sm"
          variant="outline"
          className="w-full mt-2"
          onClick={() => navigate(`/print/slip/${slip.id}`)}
          data-testid={`station-${lineKey}-print-token`}
        >
          <Printer className="w-4 h-4" /> Reprint Token
        </Button>
      )}
    </div>
  );
}
