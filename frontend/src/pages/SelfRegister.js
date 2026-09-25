import React, { useEffect, useState, useCallback } from "react";
import { QRCodeSVG } from "qrcode.react";
import api, { formatApiError, errorPayload } from "../lib/api";
import { Button, Card, Select, Field, Alert } from "../components/ui";
import AadhaarScanner from "../components/AadhaarScanner";
import { Stethoscope, CheckCircle2, Lock } from "lucide-react";
import { v4 } from "../lib/uuid";
import { normalizePhone } from "../lib/phone";
import { PhoneInput } from "../components/PhoneInput";
import { displayDate } from "../lib/dates";

const SEAT_REFUSALS = ["CAMP_DAY_FULL", "DAY_PASSED"];

function dayLabel(d) {
  const today = d.is_today ? " (today / आज)" : "";
  const seats = d.remaining > 0 ? `${d.remaining} seats left / ${d.remaining} सीटें बाकी` : "Full / भरा हुआ";
  return `${displayDate(d.day_date)}${today} · ${seats}`;
}

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
  const [loadingCamp, setLoadingCamp] = useState(true);
  const [reqId, setReqId] = useState("");
  const [readFailed, setReadFailed] = useState(false);
  const [retry, setRetry] = useState(false);
  const canonicalPhone = normalizePhone(phone);
  const upcoming = days.filter((d) => !d.is_past);
  const openDays = upcoming.filter((d) => d.remaining > 0);
  const chosenDay = openDays.some((d) => d.id === dayId) ? dayId : openDays[0]?.id || "";

  const onScanned = useCallback((card, raw) => {
    setScanned({ ...card, qr_payload: raw || card.qr_payload });
    setReqId(v4());
    setRetry(false);
  }, []);

  const onCaptureStart = useCallback(() => {
    setScanned(null);
    setReqId("");
    setReadFailed(false);
    setRetry(false);
  }, []);

  const onFailure = useCallback((outcome) => {
    const unreadable = outcome === "garbage" || outcome === "not-aadhaar";
    setReadFailed(unreadable);
    setRetry(!unreadable);
  }, []);

  const loadCamp = useCallback(() => {
    setLoadingCamp(true);
    setLoadErr("");
    api.get("/camps/active/public")
      .then((r) => {
        setCamp(r.data.camp);
        setDays(r.data.days || []);
      })
      .catch((e) => setLoadErr(formatApiError(e)))
      .finally(() => setLoadingCamp(false));
  }, []);

  useEffect(() => { loadCamp(); }, [loadCamp]);

  const submit = useCallback(async () => {
    if (!scanned || !chosenDay || !reqId || !canonicalPhone) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/self-register", {
        qr_payload: scanned.qr_payload,
        phone: canonicalPhone,
        camp_day_id: chosenDay,
        is_self_registered: true,
        registration_request_id: reqId,
        full_name: scanned.full_name,
      });
      setReceipt(data.receipt);
    } catch (err) {
      setError(formatApiError(err));
      if (SEAT_REFUSALS.includes(errorPayload(err)?.code)) loadCamp();
    } finally {
      setBusy(false);
    }
  }, [scanned, canonicalPhone, chosenDay, reqId, loadCamp]);

  const registerAnother = () => {
    setReceipt(null);
    setScanned(null);
    setReqId("");
    setReadFailed(false);
    setRetry(false);
    loadCamp();
  };

  const missing = [
    !chosenDay && "camp day / कैंप का दिन",
    !scanned && "Aadhaar card scan / आधार कार्ड स्कैन",
    !canonicalPhone && "10-digit mobile / 10 अंकों का मोबाइल",
  ].filter(Boolean);

  const ready = !loadingCamp && !loadErr;
  const booking = ready && !receipt && camp && upcoming.length > 0;
  const dates = upcoming.map((d) => displayDate(d.day_date)).join(", ");

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-slate-900 text-white">
        <div className="max-w-xl mx-auto px-4 h-16 flex items-center justify-between gap-3">
          <a href="/" className="flex items-center gap-3 min-h-[44px] rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400">
            <span className="w-9 h-9 rounded-xl bg-emerald-500 flex items-center justify-center">
              <Stethoscope className="w-5 h-5" />
            </span>
            <span className="leading-tight">
              <span className="block font-display font-extrabold text-lg">SNP Camps</span>
              <span className="block text-xs text-slate-400">Patient registration / मरीज़ रजिस्ट्रेशन</span>
            </span>
          </a>
          <a
            href="/login"
            className="shrink-0 min-h-[44px] px-3 inline-flex items-center text-sm text-slate-400 hover:text-white rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400"
            data-testid="goto-staff-login-link"
          >
            Staff sign in
          </a>
        </div>
      </header>

      <div className="max-w-xl mx-auto px-4 py-6 animate-fade-up">
        {loadingCamp && (
          <p role="status" data-testid="self-camp-loading" className="text-slate-700 font-semibold py-6 text-center">Loading the camp… / कैंप लोड हो रहा है…</p>
        )}
        {loadErr && !loadingCamp && (
          <Alert className="mb-4">
            {loadErr}
            <Button className="mt-3" onClick={loadCamp} data-testid="self-camp-retry">Retry / फिर कोशिश करें</Button>
          </Alert>
        )}
        {ready && !receipt && (!camp || upcoming.length === 0) && (
          <Card><p className="text-slate-500 text-center py-6" data-testid="self-no-camp">No active camp right now. Please check with the desk. अभी कोई कैंप चालू नहीं है। डेस्क से पूछें।</p></Card>
        )}

        {booking && (
          <Card className="mb-4">
            <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Camp / कैंप</p>
            <p className="font-display font-bold text-xl text-slate-900 mt-1">{camp.name}</p>
            <p className="text-sm text-slate-500">{camp.venue}</p>
          </Card>
        )}

        {booking && openDays.length === 0 && (
          <Card data-testid="self-all-full">
            <h2 className="font-display font-bold text-xl text-slate-900">Online booking is full / ऑनलाइन बुकिंग भर गई है</h2>
            <p className="mt-3 text-slate-700">
              You can still come to the camp on {dates} at {camp.venue}. The desk registers everyone who comes.
            </p>
            <p className="mt-2 text-slate-700">
              आप फिर भी {dates} को {camp.venue} में कैंप आ सकते हैं। डेस्क पर आने वाले हर व्यक्ति का रजिस्ट्रेशन होता है।
            </p>
          </Card>
        )}

        {booking && openDays.length > 0 && (
          <Card className="space-y-4">
            <Field label="Camp day / कैंप का दिन">
              <Select value={chosenDay} onChange={(e) => setDayId(e.target.value)} data-testid="self-day-select">
                {upcoming.map((d) => (
                  <option key={d.id} value={d.id} disabled={d.remaining <= 0}>{dayLabel(d)}</option>
                ))}
              </Select>
            </Field>

            <AadhaarScanner onScanned={onScanned} onCaptureStart={onCaptureStart} onFailure={onFailure} disabled={busy} forPatient />

            {readFailed && !scanned && (
              <p className="text-sm font-semibold text-amber-800" data-testid="self-scan-required">
                We could not read the QR code on this Aadhaar card. Please register at the camp desk instead.
                {" / "}इस आधार कार्ड का QR नहीं पढ़ा जा सका। कृपया कैंप डेस्क पर रजिस्टर करें।
              </p>
            )}

            {retry && !scanned && (
              <p role="status" className="text-sm font-semibold text-slate-900" data-testid="self-scan-retry">
                That did not work. Check the connection or camera and try again. / नहीं हो पाया। इंटरनेट या कैमरा जाँचें और फिर कोशिश करें।
              </p>
            )}

            {scanned && (
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-1.5" data-testid="self-scanned-preview">
                <div className="flex items-center gap-1.5 text-emerald-700 text-xs font-semibold mb-1">
                  <Lock className="w-3.5 h-3.5" /> Details from card QR / कार्ड के QR से जानकारी
                </div>
                <Row k="Name / नाम" v={scanned.full_name} />
                <Row k="Gender / लिंग" v={scanned.gender} />
                <Row k="DOB / Age · जन्मतिथि / उम्र" v={`${displayDate(scanned.dob) || "-"} · ${scanned.age ?? "-"}`} />
                <Row k="Aadhaar last-4 / आधार के आखिरी 4 अंक" v={scanned.aadhaar_last4} />
                <Row k="Address / पता" v={scanned.address} />
              </div>
            )}

            <Field label="Mobile / मोबाइल नंबर" required hint="10-digit number for SMS / SMS के लिए 10 अंकों का नंबर">
              <PhoneInput value={phone} onChange={setPhone} placeholder="10-digit mobile" data-testid="self-phone-input" />
            </Field>

            <Alert>{error}</Alert>
            <Button size="lg" className="w-full" disabled={busy || missing.length > 0} aria-describedby={missing.length ? "self-register-missing" : undefined} onClick={submit} data-testid="self-register-submit">
              {busy ? "Registering… / रजिस्टर हो रहा है…" : "Register / रजिस्टर करें"}
            </Button>
            {!busy && missing.length > 0 && (
              <p id="self-register-missing" className="text-sm text-slate-700" data-testid="self-register-missing">Still needed / अभी बाकी: {missing.join(", ")}</p>
            )}
          </Card>
        )}

        {receipt && (
          <Card className="text-center" data-testid="self-receipt">
            <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
            <h2 className="font-display font-extrabold text-2xl text-slate-900 mt-3">You're registered! / आपका रजिस्ट्रेशन हो गया!</h2>
            <p className="text-slate-500 text-sm mt-1">Show this screen (or your number) at the desk. / यह स्क्रीन (या अपना नंबर) डेस्क पर दिखाएँ।</p>
            <div className="my-5 flex justify-center">
              <div className="p-3 bg-white border border-slate-200 rounded-xl">
                <QRCodeSVG value={`SNP:${receipt.patient_qr}`} size={160} level="Q" marginSize={4} />
              </div>
            </div>
            <p className="text-5xl font-display font-extrabold text-emerald-700" data-testid="self-receipt-regno">#{receipt.reg_no}</p>
            <div className="mt-4 text-sm text-slate-600 space-y-1">
              <p><span className="text-slate-600">Camp / कैंप:</span> {receipt.camp_name}</p>
              <p><span className="text-slate-600">Venue / जगह:</span> {receipt.venue}</p>
              <p><span className="text-slate-600">Day / दिन:</span> {displayDate(receipt.day_date)}</p>
            </div>
            <Button variant="outline" className="mt-6 w-full" onClick={registerAnother} data-testid="self-register-another">
              Register another patient / दूसरे मरीज़ का रजिस्ट्रेशन करें
            </Button>
          </Card>
        )}
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <span className="w-2/5 shrink-0 text-slate-600">{k}</span>
      <span className="min-w-0 break-words text-right font-medium text-slate-800">{v || "-"}</span>
    </div>
  );
}
