import React, { useEffect, useState, useCallback } from "react";
import { QRCodeSVG } from "qrcode.react";
import api, { formatApiError } from "../lib/api";
import { Button, Card, Input, Field, Alert } from "../components/ui";
import AadhaarScanner from "../components/AadhaarScanner";
import { Stethoscope, CheckCircle2, Lock } from "lucide-react";
import { v4 } from "../lib/uuid";

export default function SelfRegister() {
  const [camp, setCamp] = useState(null);
  const [days, setDays] = useState([]);
  const [scanned, setScanned] = useState(null);
  const [phone, setPhone] = useState("");
  const [dayId, setDayId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [loadErr, setLoadErr] = useState("");
  const [reqId, setReqId] = useState("");

  const onScanned = useCallback((card, raw) => {
    setScanned({ ...card, qr_payload: raw || card.qr_payload });
    setReqId(v4());
  }, []);

  useEffect(() => {
    api.get("/camps/active/public")
      .then((r) => {
        setCamp(r.data.camp);
        setDays(r.data.days || []);
        const today = (r.data.days || []).find((d) => d.is_today);
        if (today) setDayId(today.id);
        else if (r.data.days?.length) setDayId(r.data.days[0].id);
      })
      .catch((e) => setLoadErr(formatApiError(e)));
  }, []);

  const submit = useCallback(async () => {
    if (!scanned || !dayId || !reqId || !phone) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/self-register", {
        qr_payload: scanned.qr_payload,
        phone,
        camp_day_id: dayId,
        is_self_registered: true,
        registration_request_id: reqId,
        full_name: scanned.full_name,
      });
      setReceipt(data.receipt);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  }, [scanned, phone, dayId, reqId]);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-slate-900 text-white">
        <div className="max-w-xl mx-auto px-4 h-16 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center">
            <Stethoscope className="w-5 h-5" />
          </div>
          <div>
            <p className="font-display font-extrabold text-lg leading-none">SNP Camps</p>
            <p className="text-[11px] text-slate-400 mt-1">Patient Self-Registration</p>
          </div>
        </div>
      </header>

      <div className="max-w-xl mx-auto px-4 py-6 animate-fade-up">
        {loadErr && <Alert className="mb-4">{loadErr}</Alert>}
        {!camp && !loadErr && (
          <Card><p className="text-slate-500 text-center py-6">No active camp right now. Please check with the desk.</p></Card>
        )}

        {camp && !receipt && (
          <>
            <Card className="mb-4">
              <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Active Camp</p>
              <p className="font-display font-bold text-xl text-slate-900 mt-1">{camp.name}</p>
              <p className="text-sm text-slate-500">{camp.venue}</p>
            </Card>

            <Card className="space-y-4">
              <AadhaarScanner onScanned={onScanned} />

              {scanned && (
                <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-1.5" data-testid="self-scanned-preview">
                  <div className="flex items-center gap-1.5 text-emerald-600 text-xs font-semibold mb-1">
                    <Lock className="w-3.5 h-3.5" /> Identity from card (locked)
                  </div>
                  <Row k="Name" v={scanned.full_name} />
                  <Row k="Gender" v={scanned.gender} />
                  <Row k="DOB / Age" v={`${scanned.dob || "-"} · ${scanned.age ?? "-"}`} />
                  <Row k="Aadhaar last-4" v={scanned.aadhaar_last4} />
                  <Row k="Address" v={scanned.address} />
                </div>
              )}

              <Field label="Mobile" required hint="Required 10-digit household contact">
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="10-digit mobile" inputMode="numeric" data-testid="self-phone-input" />
              </Field>

              <Field label="Camp day">
                <select className="w-full min-h-[44px] px-3.5 rounded-xl border border-slate-300" value={dayId} onChange={(e) => setDayId(e.target.value)} data-testid="self-day-select">
                  {days.map((d) => <option key={d.id} value={d.id}>{d.day_date}{d.is_today ? " (today)" : ""}</option>)}
                </select>
              </Field>

              <Alert>{error}</Alert>
              <Button size="lg" className="w-full" disabled={!scanned || !dayId || !phone || busy} onClick={submit} data-testid="self-register-submit">
                {busy ? "Registering…" : "Register"}
              </Button>
            </Card>
          </>
        )}

        {receipt && (
          <Card className="text-center" data-testid="self-receipt">
            <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
            <h2 className="font-display font-extrabold text-2xl text-slate-900 mt-3">You're registered!</h2>
            <p className="text-slate-500 text-sm mt-1">Show this screen (or your number) at the desk.</p>
            <div className="my-5 flex justify-center">
              <div className="p-3 bg-white border border-slate-200 rounded-xl">
                <QRCodeSVG value={`snp:${receipt.patient_qr}`} size={160} />
              </div>
            </div>
            <p className="text-5xl font-display font-extrabold text-emerald-600" data-testid="self-receipt-regno">#{receipt.reg_no}</p>
            <div className="mt-4 text-sm text-slate-600 space-y-1">
              <p><span className="text-slate-400">Camp:</span> {receipt.camp_name}</p>
              <p><span className="text-slate-400">Venue:</span> {receipt.venue}</p>
              <p><span className="text-slate-400">Day:</span> {receipt.day_date}</p>
            </div>
            <Button variant="outline" className="mt-6 w-full" onClick={() => { setReceipt(null); setScanned(null); setReqId(""); }} data-testid="self-register-another">
              Register another patient
            </Button>
          </Card>
        )}
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-slate-400">{k}</span>
      <span className="font-medium text-slate-800">{v || "-"}</span>
    </div>
  );
}
