import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import api, { formatApiError } from "../../lib/api";
import { Button, Badge } from "../ui";
import { Pill, Glasses, Scissors, Printer } from "lucide-react";

export const FULFILMENT_LINES = {
  medicine: {
    label: "Medicine",
    icon: Pill,
    itemType: "medicine",
    actions: [
      { status: "fulfilled", label: "Given" },
      { status: "not_available", label: "Out of stock" },
    ],
  },
  specs_fixed: {
    label: "Fixed-power specs",
    icon: Glasses,
    itemType: "specs_fixed",
    needsMeasurements: true,
    actions: [{ status: "fulfilled", label: "Issue" }],
  },
  specs_made: {
    label: "Spectacles to be made",
    icon: Glasses,
    itemType: "specs_made",
    needsMeasurements: true,
    dayField: "specs_collection_day_id",
    dayLabel: "Specs collection day",
    actions: [{ status: "deferred", label: "Defer and print Token" }],
  },
  ot: {
    label: "Hospital surgery",
    icon: Scissors,
    itemType: "ot",
    dayField: "ot_schedule_day_id",
    dayLabel: "Hospital surgery day",
    actions: [{ status: "deferred", label: "Schedule at hospital and print token" }],
  },
};

export function hasMeasurements(transcription) {
  const m = transcription?.specs_measurements || {};
  return Boolean(String(m.r_sph || "").trim() && String(m.l_sph || "").trim());
}

export function earliestFreeDay(days, currentId) {
  if (currentId) return currentId;
  const free = days.filter((d) => d.seats_free > 0);
  return free.length ? free[0].id : "";
}

export function selectableSpecsDays(days) {
  return (days || []).filter((d) => d.start_time && d.end_time && !d.window_required);
}

export function earliestSpecsDay(days, currentId) {
  if (currentId) return currentId;
  const open = selectableSpecsDays(days);
  return open.length ? open[0].id : "";
}

function DayPicker({ line, days, value, onChange }) {
  const specs = line.itemType === "specs_made";
  const visible = specs ? selectableSpecsDays(days) : days;
  const noneFree = specs
    ? visible.length === 0
    : days.every((d) => d.seats_free <= 0);
  return (
    <>
      <select
        aria-label={line.dayLabel}
        className="w-full mt-2 min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`${line.dayField}-select`}
      >
        <option value="">Select {line.dayLabel}…</option>
        {visible.map((d) => (
          <option
            key={d.id}
            value={d.id}
            disabled={!specs && d.seats_free <= 0 && d.id !== value}
          >
            {d.day_date} · {d.venue}
            {specs
              ? ` · ${d.start_time}–${d.end_time}`
              : d.seats_free <= 0 ? " (full)" : ` (${d.seats_free} free)`}
          </option>
        ))}
      </select>
      {noneFree && (
        <p className="text-xs text-rose-700 mt-2" data-testid={`${line.dayField}-none-free`}>
          {specs
            ? "No day is scheduled."
            : `Every ${line.dayLabel} is full. Call the admin to add one.`}
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
  onBusyChange,
}) {
  const line = FULFILMENT_LINES[lineKey];
  const Icon = line.icon;
  const days = line.dayField === "ot_schedule_day_id" ? otDays : specsDays;

  const existing = useMemo(() => {
    return data?.fulfilments?.find((f) => f.item_type === line.itemType) || null;
  }, [data, line]);
  const slip = data?.slips?.find((s) => s.item_type === line.itemType && s.active);
  const [status, setStatus] = useState(existing?.status || line.actions[0].status);
  const [dayId, setDayId] = useState("");
  const [busy, setBusy] = useState(false);
  const [paperReviewed, setPaperReviewed] = useState(false);
  const issueOpRef = useRef(null);

  useEffect(() => {
    setStatus(existing?.status || line.actions[0].status);
    setPaperReviewed(false);
    issueOpRef.current = null;
  }, [existing?.status, line, data?.registration?.id, data?.committed_revision?.id]);

  useEffect(() => {
    if (!line.dayField) return;
    setDayId(
      line.itemType === "specs_made"
        ? earliestSpecsDay(days, existing?.[line.dayField] || "")
        : earliestFreeDay(days, existing?.[line.dayField] || ""),
    );
  }, [days, existing, line.dayField, line.itemType]);

  const needsDay = Boolean(line.dayField) && status === "deferred";
  const recordsPower = line.needsMeasurements;
  const measurementsMissing = recordsPower && !hasMeasurements(data?.transcription);

  const save = useCallback(async (chosen) => {
    if (!data?.transcription?.id) return;
    const nextStatus = chosen || status;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try {
      const { data: res } = await api.post("/clinical/fulfilment", {
        transcription_id: data.transcription.id,
        item_type: line.itemType,
        status: nextStatus,
        ot_schedule_day_id: line.dayField === "ot_schedule_day_id" ? dayId || null : null,
        specs_collection_day_id: line.dayField === "specs_collection_day_id" ? dayId || null : null,
        paper_reviewed: paperReviewed,
        reviewed_revision_id: data.committed_revision?.id,
        reviewed_generation: data.clinical_generation ?? data.registration?.clinical_generation,
        operation_id: issueOpRef.current || (issueOpRef.current = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`),
      });
      issueOpRef.current = null;
      setBanner(`${line.label}: ${nextStatus.replace(/_/g, " ")}`);
      if (res.slip) {
        navigate(`/print/slip/${res.slip.id}`);
      } else {
        onDone();
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  }, [data?.transcription?.id, data?.committed_revision?.id, data?.clinical_generation, data?.registration?.clinical_generation, line, status, dayId, paperReviewed, navigate, onDone, setBanner, setError, onBusyChange]);

  if (existing) {
    return (
      <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${lineKey}`}>
        <div className="flex items-center gap-2 mb-3">
          <Icon className="w-5 h-5 text-emerald-600" />
          <p className="font-semibold text-slate-900 text-sm">{line.label}</p>
        </div>
        <Badge tone={existing.status === "deferred" ? "amber" : "emerald"} data-testid={`station-${lineKey}-recorded`}>
          {existing.status.replace(/_/g, " ")}
        </Badge>
        {slip && (
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

  return (
    <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${lineKey}`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-5 h-5 text-emerald-600" />
        <p className="font-semibold text-slate-900 text-sm">{line.label}</p>
      </div>

      <label className="flex items-center gap-2 min-h-[44px] mb-3 text-sm">
        <input
          type="checkbox"
          checked={paperReviewed}
          onChange={(e) => setPaperReviewed(e.target.checked)}
          data-testid={`station-${lineKey}-paper-review`}
        />
        <span>I compared the paper with this saved prescription</span>
      </label>
      <p className="text-sm font-semibold text-slate-900 mb-2" data-testid={`station-${lineKey}-patient`}>
        #{data?.registration?.reg_no} {data?.registration?.full_name}
      </p>

      {line.actions.length > 1 && (
        <div className="flex flex-col gap-2">
          {line.actions.map((a) => (
            <Button
              key={a.status}
              size="sm"
              variant={status === a.status ? "primary" : "outline"}
              className="w-full"
              disabled={!paperReviewed || busy || measurementsMissing || (a.status === "deferred" && line.dayField && !dayId && status === "deferred")}
              onClick={() => {
                setStatus(a.status);
                if (a.status !== "deferred" || !line.dayField) save(a.status);
              }}
              data-testid={`station-${lineKey}-${a.status}`}
            >
              {a.label}
            </Button>
          ))}
        </div>
      )}

      {needsDay && (
        <DayPicker line={line} days={days} value={dayId} onChange={setDayId} />
      )}

      {line.actions.length === 1 && (
        <Button
          size="sm"
          className="w-full mt-2"
          onClick={() => save(line.actions[0].status)}
          disabled={!paperReviewed || !status || busy || measurementsMissing || (needsDay && !dayId)}
          data-testid={`station-${lineKey}-save`}
        >
          {line.actions[0].label}
        </Button>
      )}

      {line.actions.length > 1 && status === "deferred" && line.dayField && (
        <Button
          size="sm"
          className="w-full mt-2"
          onClick={() => save("deferred")}
          disabled={busy || !dayId}
          data-testid={`station-${lineKey}-save`}
        >
          {line.actions.find((a) => a.status === "deferred")?.label || "Save"}
        </Button>
      )}

      {measurementsMissing && (
        <p className="text-xs text-amber-800 mt-2" data-testid={`station-${lineKey}-needs-power`}>
          Record the prescribed power for both eyes before recording this line.
        </p>
      )}
    </div>
  );
}
