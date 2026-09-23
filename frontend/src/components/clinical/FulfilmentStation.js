import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import api, { formatApiError } from "../../lib/api";
import { v4 } from "../../lib/uuid";
import { Alert, Button, Badge } from "../ui";
import { Pill, Glasses, Scissors, Printer } from "lucide-react";
import { FixedPowerPicker, formatPower } from "./FixedPowerPicker";
import { displayDateRange, displayTimeRange } from "../../lib/dates";

export const FULFILMENT_LINES = {
  medicine: {
    label: "Medicine",
    icon: Pill,
    itemType: "medicine",
    perMedicine: true,
    actions: [{ status: "fulfilled", label: "Record medicines" }],
  },
  specs_fixed: {
    label: "Fixed-power specs",
    icon: Glasses,
    itemType: "specs_fixed",
    needsFixedPower: true,
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
    label: "Hospital",
    icon: Scissors,
    itemType: "ot",
    dayField: "ot_schedule_day_id",
    dayLabel: "OT Schedule Day",
    actions: [
      { status: "deferred", label: "Schedule and print token" },
      { status: "declined", label: "Patient declined" },
    ],
    statusLabels: { deferred: "IOL surgery scheduled", declined: "Surgery declined" },
  },
};

const STATUS_TONES = { deferred: "amber", declined: "slate" };

function statusLabel(line, status) {
  return line.statusLabels?.[status] || status.replace(/_/g, " ");
}

export function hasMeasurements(transcription) {
  const m = transcription?.specs_measurements || {};
  return Boolean(String(m.r_sph || "").trim() && String(m.l_sph || "").trim());
}

export function hasFixedPower(transcription) {
  return (
    transcription?.fixed_power_r !== null && transcription?.fixed_power_r !== undefined
    && transcription?.fixed_power_l !== null && transcription?.fixed_power_l !== undefined
  );
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
            {displayDateRange(d.day_date, d.end_date)} · {d.venue}
            {specs
              ? ` · ${displayTimeRange(d.start_time, d.end_time)}`
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

function MedicineChecklist({ outcomes, onToggle, disabled }) {
  return (
    <fieldset className="mb-3" data-testid="medicine-checklist">
      <legend className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-2">
        Prescribed medicines
      </legend>
      <div className="space-y-2">
        {outcomes.map((o) => (
          <div
            key={o.medicine_id}
            className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2"
          >
            <span className="text-sm font-semibold text-slate-900">{o.name}</span>
            <div className="flex gap-1">
              {[true, false].map((given) => (
                <button
                  key={String(given)}
                  type="button"
                  disabled={disabled}
                  aria-pressed={o.given === given}
                  onClick={() => onToggle(o.medicine_id, given)}
                  className={`min-h-[44px] px-3 rounded-lg text-xs font-semibold border transition-colors ${
                    o.given === given
                      ? given
                        ? "bg-emerald-700 text-white border-emerald-700"
                        : "bg-amber-600 text-white border-amber-600"
                      : "bg-white text-slate-600 border-slate-300"
                  }`}
                  data-testid={`medicine-${o.medicine_id}-${given ? "given" : "missing"}`}
                >
                  {given ? "Given" : "Not available"}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </fieldset>
  );
}

function PowerSubstitution({ transcription, powers, issued, onChange, disabled }) {
  const prescribed = `RE ${formatPower(transcription?.fixed_power_r)} · LE ${formatPower(transcription?.fixed_power_l)}`;
  const changed =
    issued.r !== transcription?.fixed_power_r || issued.l !== transcription?.fixed_power_l;
  return (
    <div className="mb-3" data-testid="power-substitution">
      <p className="text-xs font-mono uppercase tracking-widest text-slate-500 mb-1">
        Prescribed power
      </p>
      <p className="font-mono font-bold text-slate-900 mb-2">{prescribed}</p>
      <FixedPowerPicker
        powers={powers}
        valueR={issued.r}
        valueL={issued.l}
        disabled={disabled}
        onChange={(r, l) => onChange({ r, l })}
      />
      {changed && (
        <p className="text-xs text-amber-800 mt-2" data-testid="power-substituted">
          Issuing a different power from the one prescribed. Both are recorded.
        </p>
      )}
    </div>
  );
}

export function FulfilmentStation({
  line: lineKey,
  data,
  otDays = [],
  specsDays = [],
  powers = [],
  onDone,
  navigate,
  setBanner,
  onBusyChange,
}) {
  const line = FULFILMENT_LINES[lineKey];
  const Icon = line.icon;
  const days = line.dayField === "ot_schedule_day_id" ? otDays : specsDays;

  const existing = useMemo(() => {
    return data?.fulfilments?.find((f) => f.item_type === line.itemType) || null;
  }, [data, line]);
  const slip = data?.slips?.find((s) => s.item_type === line.itemType && s.active);
  const [dayId, setDayId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [paperReviewed, setPaperReviewed] = useState(false);
  const issueOpRef = useRef(null);
  const prescribedMedicines = useMemo(
    () => data?.transcription?.prescribed_medicines || [],
    [data?.transcription?.prescribed_medicines],
  );
  const [outcomes, setOutcomes] = useState([]);
  const [issued, setIssued] = useState({ r: null, l: null });

  useEffect(() => {
    setPaperReviewed(false);
    issueOpRef.current = null;
  }, [existing?.status, line, data?.registration?.id, data?.committed_revision?.id]);

  useEffect(() => {
    setOutcomes(prescribedMedicines.map((m) => ({ ...m, given: true })));
  }, [prescribedMedicines]);

  useEffect(() => {
    setIssued({
      r: data?.transcription?.fixed_power_r ?? null,
      l: data?.transcription?.fixed_power_l ?? null,
    });
  }, [data?.transcription?.fixed_power_r, data?.transcription?.fixed_power_l]);

  useEffect(() => {
    if (!line.dayField) return;
    setDayId(
      line.itemType === "specs_made"
        ? earliestSpecsDay(days, existing?.[line.dayField] || "")
        : earliestFreeDay(days, existing?.[line.dayField] || ""),
    );
  }, [days, existing, line.dayField, line.itemType]);

  const measurementsMissing =
    (line.needsMeasurements && !hasMeasurements(data?.transcription))
    || (line.needsFixedPower && !hasFixedPower(data?.transcription));

  const save = useCallback(async (nextStatus) => {
    if (!data?.transcription?.id) return;
    const day = nextStatus === "deferred" ? dayId || null : null;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try {
      const { data: res } = await api.post("/clinical/fulfilment", {
        transcription_id: data.transcription.id,
        item_type: line.itemType,
        status: nextStatus,
        medicine_outcomes: line.perMedicine
          ? outcomes.map((o) => ({ medicine_id: o.medicine_id, given: o.given }))
          : [],
        issued_power_r: line.needsFixedPower ? issued.r : null,
        issued_power_l: line.needsFixedPower ? issued.l : null,
        ot_schedule_day_id: line.dayField === "ot_schedule_day_id" ? day : null,
        specs_collection_day_id: line.dayField === "specs_collection_day_id" ? day : null,
        paper_reviewed: paperReviewed,
        reviewed_revision_id: data.committed_revision?.id,
        reviewed_generation: data.clinical_generation ?? data.registration?.clinical_generation,
        operation_id: issueOpRef.current || (issueOpRef.current = v4()),
      });
      issueOpRef.current = null;
      setBanner(`${line.label}: ${statusLabel(line, res.fulfilment?.status || nextStatus)}`);
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
  }, [data?.transcription?.id, data?.committed_revision?.id, data?.clinical_generation, data?.registration?.clinical_generation, line, dayId, paperReviewed, outcomes, issued, navigate, onDone, setBanner, onBusyChange]);

  const header = (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-5 h-5 text-emerald-600" />
      <p className="font-semibold text-slate-900 text-sm">{line.label}</p>
    </div>
  );
  const paperReview = (
    <label className="flex items-center gap-2 min-h-[44px] mb-3 text-sm">
      <input
        type="checkbox"
        checked={paperReviewed}
        onChange={(e) => setPaperReviewed(e.target.checked)}
        data-testid={`station-${lineKey}-paper-review`}
      />
      <span>I compared the paper with this saved prescription</span>
    </label>
  );
  const decline = line.actions.find((a) => a.status === "declined");

  if (line.itemType === "ot" && data?.committed_revision?.ot_outcome === "referral") {
    return (
      <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${lineKey}`}>
        {header}
        <p className="text-sm text-slate-700" data-testid={`station-${lineKey}-referral`}>
          Hospital referral: nothing to record here. The referral was complete when the prescription was saved.
        </p>
      </div>
    );
  }

  if (existing) {
    return (
      <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${lineKey}`}>
        {header}
        <Badge tone={STATUS_TONES[existing.status] || "emerald"} data-testid={`station-${lineKey}-recorded`}>
          {statusLabel(line, existing.status)}
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
        {decline && existing.status === "deferred" && (
          <div className="mt-3">
            {paperReview}
            <Button
              size="sm"
              variant="outline"
              className="w-full"
              onClick={() => save(decline.status)}
              disabled={!paperReviewed || busy}
              data-testid={`station-${lineKey}-${decline.status}`}
            >
              {decline.label}
            </Button>
            <Alert className="mt-2">{error}</Alert>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${lineKey}`}>
      {header}
      {paperReview}
      <p className="text-sm font-semibold text-slate-900 mb-2" data-testid={`station-${lineKey}-patient`}>
        #{data?.registration?.reg_no} {data?.registration?.full_name}
      </p>

      {line.perMedicine && (
        <MedicineChecklist
          outcomes={outcomes}
          disabled={busy}
          onToggle={(id, given) =>
            setOutcomes((cur) =>
              cur.map((o) => (o.medicine_id === id ? { ...o, given } : o)),
            )
          }
        />
      )}

      {line.needsFixedPower && !measurementsMissing && (
        <PowerSubstitution
          transcription={data?.transcription}
          powers={powers}
          issued={issued}
          onChange={setIssued}
          disabled={busy}
        />
      )}

      {line.dayField && (
        <DayPicker line={line} days={days} value={dayId} onChange={setDayId} />
      )}

      {line.actions.map((a, i) => (
        <Button
          key={a.status}
          size="sm"
          variant={i ? "outline" : "primary"}
          className="w-full mt-2"
          onClick={() => save(a.status)}
          disabled={!paperReviewed || busy || measurementsMissing || (a.status === "deferred" && Boolean(line.dayField) && !dayId)}
          data-testid={`station-${lineKey}-${i ? a.status : "save"}`}
        >
          {a.label}
        </Button>
      ))}

      {measurementsMissing && (
        <p className="text-xs text-amber-800 mt-2" data-testid={`station-${lineKey}-needs-power`}>
          {line.needsFixedPower
            ? "Select the fixed power for both eyes before recording this line."
            : "Record the prescribed power for both eyes before recording this line."}
        </p>
      )}
      <Alert className="mt-2">{error}</Alert>
    </div>
  );
}
