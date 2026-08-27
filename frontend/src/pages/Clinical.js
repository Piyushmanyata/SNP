import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError, errorPayload } from "../lib/api";
import Layout from "../components/Layout";
import {
  Button, Card, Input, Field, Alert, Badge, Modal, StatusBadge,
} from "../components/ui";
import {
  ScanLine, Save, Printer, FileEdit, History, Pill, Glasses, Scissors, Lock,
} from "lucide-react";

const emptyRx = {
  diagnosis_options: [], diagnosis_other: "", blood_sugar: "", bp: "", remarks: "",
  specs_measurements: { r_sph: "", r_cyl: "", r_axis: "", l_sph: "", l_cyl: "", l_axis: "", add: "" },
  ot_eye: "", ot_procedure: "", ot_notes: "",
};

export default function Clinical() {
  const navigate = useNavigate();
  const [lookup, setLookup] = useState("");
  const [data, setData] = useState(null); // {registration, person, transcription, fulfilments, slips}
  const [error, setError] = useState("");
  const [banner, setBanner] = useState("");
  const [diagOpts, setDiagOpts] = useState([]);
  const [otDays, setOtDays] = useState([]);
  const [rx, setRx] = useState(emptyRx);
  const [busy, setBusy] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    api.get("/clinical/diagnosis-options").then((r) => setDiagOpts(r.data.options)).catch(() => {});
    api.get("/clinical/ot-days").then((r) => setOtDays(r.data.ot_days)).catch(() => {});
  }, []);

  const doLookup = async (e) => {
    e?.preventDefault();
    setError(""); setBanner(""); setHistory(null);
    if (!lookup.trim()) return;
    try {
      const { data } = await api.post("/clinical/lookup", { value: lookup.trim() });
      setData(data);
      setRx(data.transcription ? {
        ...emptyRx, ...data.transcription,
        specs_measurements: data.transcription.specs_measurements || emptyRx.specs_measurements,
      } : emptyRx);
    } catch (err) {
      const p = errorPayload(err);
      setData(null);
      setError(p?.message || formatApiError(err));
    }
  };

  const reload = async () => {
    const { data } = await api.post("/clinical/lookup", { value: lookup.trim() });
    setData(data);
    setRx(data.transcription ? {
      ...emptyRx, ...data.transcription,
      specs_measurements: data.transcription.specs_measurements || emptyRx.specs_measurements,
    } : emptyRx);
  };

  const saveRx = async () => {
    setBusy(true); setError("");
    try {
      await api.post("/clinical/transcription", { patient_id: data.registration.id, ...rx });
      setBanner("Transcription saved.");
      await reload();
    } catch (err) { setError(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const toggleDiag = (opt) => {
    setRx((r) => ({
      ...r,
      diagnosis_options: r.diagnosis_options.includes(opt)
        ? r.diagnosis_options.filter((o) => o !== opt)
        : [...r.diagnosis_options, opt],
    }));
  };

  const openHistory = async () => {
    if (!data?.person) return;
    try {
      const { data: h } = await api.get(`/clinical/history/${data.person.id}`);
      setHistory(h.history);
    } catch (err) { setError(formatApiError(err)); }
  };

  const locked = data?.transcription?.locked;

  return (
    <Layout title="Clinical Desk">
      <Card className="mb-5">
        <form onSubmit={doLookup} className="flex gap-2">
          <Input value={lookup} onChange={(e) => setLookup(e.target.value)} placeholder="Type Reg # or scan patient QR (USB wedge)" data-testid="clinical-lookup-input" />
          <Button type="submit" variant="secondary" data-testid="clinical-lookup-button"><ScanLine className="w-5 h-5" /> Find</Button>
        </form>
        <p className="text-xs text-slate-400 mt-2">Only patients marked <b>Seen</b> are eligible.</p>
        {error && <Alert className="mt-3">{error}</Alert>}
        {banner && <Alert tone="emerald" className="mt-3">{banner}</Alert>}
      </Card>

      {data && (
        <>
          <Card className="mb-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono font-bold text-emerald-600 text-lg">#{data.registration.reg_no}</span>
              <div className="flex-1">
                <p className="font-display font-bold text-slate-900">{data.registration.full_name}</p>
                <p className="text-xs text-slate-400">{data.registration.gender_label} · {data.registration.age ?? "-"} yrs</p>
              </div>
              <StatusBadge status={data.registration.queue_status} />
              {locked && <Badge tone="indigo"><Lock className="w-3 h-3 mr-1 inline" />Locked</Badge>}
              {data.person && (
                <Button size="sm" variant="outline" onClick={openHistory} data-testid="clinical-history-button">
                  <History className="w-4 h-4" /> History
                </Button>
              )}
            </div>
          </Card>

          {/* Transcription */}
          <Card className="mb-5" data-testid="clinical-prescription-form">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-bold text-slate-900">Prescription Transcription</h3>
              {locked && <Button size="sm" variant="outline" onClick={() => setShowCorrection(true)} data-testid="add-correction-button"><FileEdit className="w-4 h-4" /> Correction</Button>}
            </div>

            <Field label="Diagnosis">
              <div className="flex flex-wrap gap-2" data-testid="diagnosis-options">
                {diagOpts.map((opt) => (
                  <button key={opt} type="button" disabled={locked} onClick={() => toggleDiag(opt)}
                    className={`min-h-[36px] px-3 rounded-full text-sm font-medium border transition-colors ${rx.diagnosis_options.includes(opt) ? "bg-emerald-500 text-white border-emerald-500" : "bg-white text-slate-600 border-slate-300 hover:border-emerald-400"}`}
                    data-testid={`diagnosis-opt-${opt.replace(/\s+/g, "-").toLowerCase()}`}>
                    {opt}
                  </button>
                ))}
              </div>
            </Field>
            <div className="mt-3">
              <Field label="Other diagnosis"><Input value={rx.diagnosis_other || ""} disabled={locked} onChange={(e) => setRx({ ...rx, diagnosis_other: e.target.value })} data-testid="diagnosis-other-input" /></Field>
            </div>

            <div className="grid grid-cols-2 gap-3 mt-3">
              <Field label="Blood Pressure"><Input value={rx.bp || ""} disabled={locked} onChange={(e) => setRx({ ...rx, bp: e.target.value })} placeholder="120/80" data-testid="bp-input" /></Field>
              <Field label="Blood Sugar"><Input value={rx.blood_sugar || ""} disabled={locked} onChange={(e) => setRx({ ...rx, blood_sugar: e.target.value })} placeholder="mg/dL" data-testid="sugar-input" /></Field>
            </div>

            <p className="text-xs font-mono uppercase tracking-widest text-slate-500 mt-4 mb-2">Spectacle Measurements</p>
            <div className="grid grid-cols-3 sm:grid-cols-7 gap-2">
              {["r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add"].map((k) => (
                <div key={k}>
                  <label className="text-[10px] font-mono text-slate-400 uppercase">{k.replace("_", " ")}</label>
                  <Input className="text-center px-1" value={rx.specs_measurements?.[k] || ""} disabled={locked}
                    onChange={(e) => setRx({ ...rx, specs_measurements: { ...rx.specs_measurements, [k]: e.target.value } })}
                    data-testid={`specs-${k}`} />
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3 mt-4">
              <Field label="OT Eye">
                <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300 disabled:bg-slate-100" value={rx.ot_eye || ""} disabled={locked} onChange={(e) => setRx({ ...rx, ot_eye: e.target.value })} data-testid="ot-eye-select">
                  <option value="">—</option><option value="R">Right</option><option value="L">Left</option><option value="B">Both</option>
                </select>
              </Field>
              <Field label="OT Procedure"><Input value={rx.ot_procedure || ""} disabled={locked} onChange={(e) => setRx({ ...rx, ot_procedure: e.target.value })} data-testid="ot-procedure-input" /></Field>
            </div>
            <div className="mt-3">
              <Field label="Remarks"><Input value={rx.remarks || ""} disabled={locked} onChange={(e) => setRx({ ...rx, remarks: e.target.value })} data-testid="remarks-input" /></Field>
            </div>

            {!locked && (
              <Button className="mt-4" onClick={saveRx} disabled={busy} data-testid="save-transcription-button">
                <Save className="w-4 h-4" /> {data.transcription ? "Update" : "Save"} Transcription
              </Button>
            )}
          </Card>

          {/* Fulfilment stations */}
          {data.transcription && (
            <FulfilmentSection data={data} otDays={otDays} onDone={reload} navigate={navigate} setBanner={setBanner} setError={setError} />
          )}
        </>
      )}

      <Modal open={showCorrection} onClose={() => setShowCorrection(false)} title="Prescription Correction">
        <CorrectionForm transcriptionId={data?.transcription?.id} onDone={() => { setShowCorrection(false); reload(); setBanner("Correction added."); }} />
      </Modal>

      <Modal open={!!history} onClose={() => setHistory(null)} title="Clinical History" size="lg">
        {history?.length === 0 && <p className="text-slate-400 text-sm">No prior clinical records.</p>}
        <div className="space-y-3">
          {history?.map((h) => (
            <Card key={h.transcription.id} className="p-4">
              <div className="flex justify-between text-sm">
                <span className="font-semibold">{h.camp_name || "Camp"} · #{h.reg_no}</span>
                <span className="text-slate-400">{h.transcription.created_at?.slice(0, 10)}</span>
              </div>
              <p className="text-sm text-slate-600 mt-1">Dx: {(h.transcription.diagnosis_options || []).join(", ") || "-"}{h.transcription.diagnosis_other ? `, ${h.transcription.diagnosis_other}` : ""}</p>
            </Card>
          ))}
        </div>
      </Modal>
    </Layout>
  );
}

const STATION_OPTS = {
  medicine: ["fulfilled", "not_available", "not_required"],
  specs: ["fulfilled", "deferred", "not_required"],
  ot: ["fulfilled", "deferred", "not_required"],
};
const STATION_META = {
  medicine: { label: "Medicine", icon: Pill },
  specs: { label: "Spectacles to be made", icon: Glasses },
  ot: { label: "OT / Surgery", icon: Scissors },
};

function FulfilmentSection({ data, otDays, onDone, navigate, setBanner, setError }) {
  return (
    <Card>
      <h3 className="font-display font-bold text-slate-900 mb-4">Clinical Line Stations</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {["medicine", "specs", "ot"].map((type) => (
          <Station key={type} type={type} data={data} otDays={otDays} onDone={onDone} navigate={navigate} setBanner={setBanner} setError={setError} />
        ))}
      </div>
    </Card>
  );
}

function Station({ type, data, otDays, onDone, navigate, setBanner, setError }) {
  const meta = STATION_META[type];
  const Icon = meta.icon;
  const existing = data.fulfilments.find((f) => f.item_type === type);
  const slip = data.slips.find((s) => s.item_type === type && s.active);
  const [status, setStatus] = useState(existing?.status || "");
  const [collDate, setCollDate] = useState(existing?.collection_date || "");
  const [collVenue, setCollVenue] = useState(existing?.collection_venue || "");
  const [otDayId, setOtDayId] = useState(existing?.ot_schedule_day_id || "");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true); setError("");
    try {
      const { data: res } = await api.post("/clinical/fulfilment", {
        transcription_id: data.transcription.id, item_type: type, status,
        collection_date: type === "specs" ? collDate : null,
        collection_venue: type === "specs" ? collVenue : null,
        ot_schedule_day_id: type === "ot" ? otDayId : null,
      });
      setBanner(`${meta.label}: ${status}`);
      if (res.slip) navigate(`/print/slip/${res.slip.id}`);
      else onDone();
    } catch (err) { setError(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <div className="rounded-xl border border-slate-200 p-4" data-testid={`station-${type}`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-5 h-5 text-emerald-600" />
        <p className="font-semibold text-slate-900 text-sm">{meta.label}</p>
      </div>
      <select className="w-full min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm" value={status} onChange={(e) => setStatus(e.target.value)} data-testid={`station-${type}-status`}>
        <option value="">Select…</option>
        {STATION_OPTS[type].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
      </select>

      {status === "deferred" && type === "specs" && (
        <div className="mt-2 space-y-2">
          <Input type="date" value={collDate} onChange={(e) => setCollDate(e.target.value)} data-testid="specs-collection-date" />
          <Input placeholder="Collection venue" value={collVenue} onChange={(e) => setCollVenue(e.target.value)} data-testid="specs-collection-venue" />
        </div>
      )}
      {status === "deferred" && type === "ot" && (
        <select className="w-full mt-2 min-h-[44px] px-3 rounded-xl border border-slate-300 text-sm" value={otDayId} onChange={(e) => setOtDayId(e.target.value)} data-testid="ot-day-select-fulfil">
          <option value="">Select OT day…</option>
          {otDays.map((d) => <option key={d.id} value={d.id} disabled={d.seats_free <= 0}>{d.day_date} · {d.venue} ({d.seats_free} free)</option>)}
        </select>
      )}

      <Button size="sm" className="w-full mt-3" onClick={save} disabled={!status || busy} data-testid={`station-${type}-save`}>Save</Button>

      {existing && <Badge tone={existing.status === "deferred" ? "amber" : "emerald"} className="mt-3">{existing.status.replace(/_/g, " ")}</Badge>}
      {slip && (
        <Button size="sm" variant="outline" className="w-full mt-2" onClick={() => navigate(`/print/slip/${slip.id}`)} data-testid={`station-${type}-print-slip`}>
          <Printer className="w-4 h-4" /> Reprint slip
        </Button>
      )}
    </div>
  );
}

function CorrectionForm({ transcriptionId, onDone }) {
  const [reason, setReason] = useState("");
  const [field, setField] = useState("remarks");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setBusy(true); setError("");
    try {
      await api.post("/clinical/correction", { transcription_id: transcriptionId, reason, changes: { [field]: value } });
      onDone();
    } catch (err) { setError(formatApiError(err)); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <Field label="Field">
        <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={field} onChange={(e) => setField(e.target.value)} data-testid="correction-field-select">
          {["remarks", "diagnosis_other", "bp", "blood_sugar", "ot_procedure"].map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </Field>
      <Field label="New value"><Input value={value} onChange={(e) => setValue(e.target.value)} data-testid="correction-value-input" /></Field>
      <Field label="Reason (audited)" required><Input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="correction-reason-input" /></Field>
      <Alert>{error}</Alert>
      <Button className="w-full" onClick={submit} disabled={busy || !reason} data-testid="correction-submit-button">Add Correction</Button>
    </div>
  );
}
