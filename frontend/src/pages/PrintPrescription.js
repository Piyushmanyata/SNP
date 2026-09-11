import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import api, { formatApiError } from "../lib/api";
import logger from "../lib/logger";
import { Button, Alert, Spinner } from "../components/ui";
import { Printer, ArrowLeft } from "lucide-react";
import rxEmblem from "../assets/rx-emblem.png";
import rxInstrument from "../assets/rx-instrument.png";
import rxEye from "../assets/rx-eye.png";

export default function PrintPrescription() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [rx, setRx] = useState(null);
  const [logos, setLogos] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    (async () => {
      try {
        const r = await api.get(`/desk/print/${id}`);
        if (cancelled) return;
        setRx(r.data.prescription);
        try {
          const t = await api.get(`/templates/logos?camp_id=${r.data.prescription.camp_id}`);
          if (cancelled) return;
          setLogos(t.data.logos || []);
        } catch (e) {
          logger.warn("Failed to fetch sponsor logos, printing without them:", e);
          if (!cancelled) setLogos([]);
        }
      } catch (e) {
        if (!cancelled) setError(formatApiError(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner className="w-8 h-8 text-emerald-500" /></div>;

  if (error || !rx) return (
    <div className="max-w-md mx-auto p-6">
      <Alert className="mb-4">{error || "Prescription not found."}</Alert>
      <Button variant="outline" onClick={() => navigate(-1)}><ArrowLeft className="w-4 h-4" /> Back to desk</Button>
    </div>
  );

  return <PrescriptionSheet rx={rx} logos={logos} navigate={navigate} patientId={id} />;
}

function SexBox({ mark, label }) {
  return (
    <span className="inline-flex items-center gap-1 ml-2">
      <span className="inline-block w-3.5 h-3.5 border border-slate-800 text-center text-[9px] leading-3.5">
        {mark ? "✓" : ""}
      </span>
      {label}
    </span>
  );
}

export function PrescriptionSheet({ rx, logos = [], navigate, preview, patientId }) {
  const [printing, setPrinting] = useState(false);
  const [printError, setPrintError] = useState("");
  const printSession = useRef(0);
  useEffect(() => {
    setPrinting(false);
    setPrintError("");
    return () => { printSession.current += 1; };
  }, [patientId]);
  const sex = String(rx.gender || rx.gender_label || "").toUpperCase();
  const male = sex.startsWith("M");
  const female = sex.startsWith("F");
  return (
    <div className={preview ? "" : "bg-slate-100 min-h-screen py-6"}>
      {!preview && (
        <div className="no-print max-w-[210mm] mx-auto px-4 mb-4 flex gap-2">
          <Button variant="outline" disabled={printing} onClick={() => navigate("/desk")}><ArrowLeft className="w-4 h-4" /> Desk</Button>
          <Button
            disabled={printing}
            onClick={async () => {
              const session = printSession.current;
              setPrinting(true);
              setPrintError("");
              try {
                if (patientId) {
                  await api.post(`/desk/print/${patientId}`);
                }
                if (session === printSession.current) window.print();
              } catch (e) {
                if (session === printSession.current) setPrintError(`Could not record printing. Please retry. ${formatApiError(e)}`);
              } finally {
                if (session === printSession.current) setPrinting(false);
              }
            }}
            data-testid="print-a4-prescription-button"
          >
            <Printer className="w-4 h-4" /> Print Prescription
          </Button>
        </div>
      )}
      {printError && <Alert className="no-print max-w-[210mm] mx-auto mb-4">{printError}</Alert>}

      <div
        className="print-a4 bg-white mx-auto shadow-lg text-slate-900 flex flex-col"
        style={{ width: "210mm", minHeight: preview ? "auto" : "297mm", padding: "10mm 12mm" }}
        data-testid="a4-prescription-sheet"
      >
        <div className="flex items-start justify-between border-b-4 border-slate-900 pb-2">
          <img src={rxEmblem} alt="" className="h-16 w-auto object-contain" data-testid="rx-emblem" />
          <div className="flex-1 text-center px-2">
            <p className="font-display font-extrabold text-base tracking-wide" data-testid="rx-masthead-en-1">
              SIKAR NAGARIK PARISHAD (KOLKATA)
            </p>
            <p className="text-[11px] leading-tight">सीकर नागरिक परिषद (कोलकाता) ॐ সীকর নাগরিক পরিষদ (কোলকাতা)</p>
            <p className="font-display font-extrabold text-base tracking-wide mt-1" data-testid="rx-masthead-en-2">
              SIKAR ZILLA WELFARE TRUST
            </p>
            <p className="text-[11px] leading-tight">सीकर जिला वेलफेयर ट्रस्ट ॐ সীকর জিলা ওয়েল ফেয়ার ট্রাস্ট</p>
          </div>
          <img src={rxInstrument} alt="" className="h-16 w-auto object-contain" data-testid="rx-instrument" />
        </div>

        <div className="border-b border-slate-900 py-1 text-[10px] leading-tight" data-testid="rx-address-band">
          <p>✚ &apos;SIKAR BHAWAN&apos; 1A, ASHUTOSH DEY LANE (Near Girish Park Metro, Opp. Liberty Cinema), KOLKATA-6</p>
          <p>PHONE : 033 4006 4713, 2257 3521, E-mail : sikarkolkata@gmail.com   Whatsapp : 86971 90268</p>
        </div>

        <div className="flex items-center justify-between py-1" data-testid="rx-services-band">
          <div className="flex-1 text-center font-bold text-[11px] leading-tight">
            <p>FREE EYE SCREENING, FREE DISTRIBUTION OF SPECTACLES &amp; MEDICINES</p>
            <p>AND FREE ARRANGMENT OF CATARACT (IOL) OPERATION.</p>
          </div>
          <img src={rxEye} alt="" className="h-8 w-auto object-contain ml-2" data-testid="rx-eye" />
        </div>

        <div className="grid grid-cols-[1fr_70mm] gap-3 mt-2 text-[12px]" data-testid="rx-block-identity">
          <div className="space-y-1">
            <Leader k="Venue" v={rx.venue} />
            <Leader k="Name" v={rx.full_name} />
            <Leader k="Address" v={rx.address} />
            <Leader k="E-mail" v="" />
          </div>
          <div>
            <div className="border border-slate-900 p-2">
              <p>Reg. No. <span className="font-bold">#{rx.reg_no}</span></p>
              <p>Date <span className="font-semibold">{rx.date}</span></p>
              <p>
                Age <span className="font-semibold">{rx.age ?? "—"}</span>
                <SexBox mark={male} label="M" />
                <SexBox mark={female} label="F" />
              </p>
              <p>Contact No. <span className="font-semibold">{rx.phone || "—"}</span></p>
            </div>
            <div className="flex justify-end mt-1">
              <QRCodeSVG value={`snp:${rx.patient_qr}`} size={68} />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 mt-2 text-[11px]" data-testid="rx-diagnosis-row">
          <span className="font-semibold">Diagnosis :</span>
          <div className="flex-1 border border-slate-900 px-2 py-1 flex flex-wrap gap-3">
            {["RE - CATARACT", "LE - CATARACT", "REFRACTION", "MEDICINE"].map((l) => (
              <label key={l} className="inline-flex items-center gap-1">
                <span className="inline-block w-3 h-3 border border-slate-800" />
                {l}
              </label>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mt-2 text-[12px] flex-1" data-testid="rx-write-area">
          <div className="space-y-2">
            <p>Blood Sugar (Random) : <span className="border-b border-slate-400 inline-block min-w-[40mm]">&nbsp;</span></p>
            <p>BP : <span className="border-b border-slate-400 inline-block min-w-[40mm]">&nbsp;</span></p>
            <p>Remaks : <span className="border-b border-slate-400 inline-block min-w-[40mm]">&nbsp;</span></p>
          </div>
          <div className="flex flex-col">
            <p className="font-bold">MEDICINES :</p>
            <div className="border-b border-slate-400 flex-[2] min-h-10 mt-1" data-testid="rx-medicine-line" />
            <div className="border-b border-slate-400 flex-1 min-h-6 mt-1" data-testid="rx-medicine-line" />
            <div className="border-b border-slate-400 flex-1 min-h-6 mt-1" data-testid="rx-medicine-line" />
          </div>
        </div>

        <div className="border border-slate-900 mt-3 p-2" data-testid="rx-glasses-box">
          <p className="text-center font-bold text-[12px] my-1 tracking-wide">PRESCRIPTION FOR GLASSES</p>
          <table className="w-full border-collapse text-[10px] text-center">
            <thead>
              <tr>
                <th className="border border-slate-800 w-16" />
                <th className="border border-slate-800" colSpan={4}>RE</th>
                <th className="border border-slate-800" colSpan={4}>LE</th>
              </tr>
              <tr>
                <th className="border border-slate-800" />
                {["Dsph", "Dcyl", "Axis", "Vision", "Dsph", "Dcyl", "Axis", "Vision"].map((h, i) => (
                  <th key={i} className="border border-slate-800 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="border border-slate-800 text-left px-1">Distance</td>
                {Array.from({ length: 8 }).map((_, i) => (
                  <td key={i} className="border border-slate-800 h-6" />
                ))}
              </tr>
              <tr>
                <td className="border border-slate-800 text-left px-1">Near</td>
                <td className="border border-slate-800" colSpan={2}>Add. Dsph</td>
                <td className="border border-slate-800" colSpan={2} />
                <td className="border border-slate-800" colSpan={2}>Add. Dsph</td>
                <td className="border border-slate-800" colSpan={2} />
              </tr>
            </tbody>
          </table>
          <p className="text-[12px] mt-2">
            Inter Pupillary distance <span className="border-b border-slate-400 inline-block min-w-[30mm]">&nbsp;</span> mm
            <span className="border-b border-slate-400 inline-block min-w-[30mm] ml-2">&nbsp;</span>
          </p>
        </div>

        <div className="border border-slate-900 mt-2 p-2 text-[11px] leading-tight" data-testid="rx-declaration">
          SIKAR NAGARIK PARISHAD(KOLKATA) &amp; SIKAR ZILLA WELFARE TRUST have done Eye Screening, distributed spectacles and Cataract (IOL) Operation will be done by :
          <span className="border-b border-slate-400 inline-block min-w-[50mm] ml-1">&nbsp;</span>
        </div>

        <div className="border border-slate-900 mt-2 p-2 text-[11px] font-semibold leading-tight" data-testid="rx-disclaimer">
          Please carry your Aadhaar card, ration card and mobile phone on the day of the operation.
        </div>

        <div className="flex justify-end mt-3 text-[12px]" data-testid="rx-signature">
          <div className="text-right">
            <p>Signature of</p>
            <p className="border-t border-slate-800 inline-block mt-8 px-4">Optometrist / Eye Surgeon</p>
          </div>
        </div>

        <div className="mt-2 pt-2 border-t border-slate-300" data-testid="rx-footer">
          <p className="font-semibold text-[12px] mb-1">Sponsorer :</p>
          <div className="flex items-center gap-3" data-testid="rx-sponsor-strip">
            {logos.map((lg, i) => (
              <img
                key={lg.id || i}
                src={lg.data_url}
                alt={lg.name}
                className="flex-1 min-w-0 object-contain object-left"
                style={{ height: "18mm" }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Leader({ k, v }) {
  return (
    <p>
      <span className="inline-block w-16">{k}</span>
      <span className="border-b border-dotted border-slate-500 inline-block min-w-[50mm] font-semibold">
        {v || "\u00a0"}
      </span>
    </p>
  );
}
