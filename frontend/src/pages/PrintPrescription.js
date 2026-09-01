import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import api, { formatApiError } from "../lib/api";
import logger from "../lib/logger";
import { Button, Alert, Spinner } from "../components/ui";
import { Printer, ArrowLeft } from "lucide-react";

export const RX_HEADER_LINES = [
  "Sikar Nagarik Parishad (Kolkata) / सीकर नागरिक परिषद (कोलकाता)",
  "Sikar Zilla Welfare Trust / सीकर जिला वेलफेयर ट्रस्ट",
];

export const RX_HEADER_SUBTITLE =
  "'Sikar Bhawan' 1A, Ashutosh Dey Lane (Near Girish Park Metro, Opp. Liberty Cinema), " +
  "KOLKATA-6. PHONE: 033 4006 4713, 2257 3521. E-mail: sikarkolkata@gmail.com. " +
  "Whatsapp: 86971 90268. FREE EYE SCREENING, FREE DISTRIBUTION OF SPECTACLES & MEDICINES " +
  "AND FREE ARRANGMENT OF CATARACT (IOL) OPERATION.";

export const RX_FOOTER = "Sponsorer: Rupa Foundation, Kolkata";

export const RX_BLOCKS = [
  { id: "identity", label: "Patient Identity", type: "identity", height: 0 },
  { id: "diagnosis", label: "Diagnosis", type: "lines", height: 24 },
  { id: "vision", label: "Vision (R / L)", type: "lines", height: 24 },
  { id: "prescription", label: "Prescription (Rx)", type: "lines", height: 48 },
  { id: "vitals", label: "BP / Blood Sugar", type: "lines", height: 18 },
  { id: "advice", label: "Advice", type: "lines", height: 24 },
  { id: "signature", label: "Doctor's Signature", type: "signature", height: 0 },
];

export default function PrintPrescription() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [rx, setRx] = useState(null);
  const [logos, setLogos] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.post(`/desk/print/${id}`);
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

  return <PrescriptionSheet rx={rx} logos={logos} navigate={navigate} />;
}

export function PrescriptionSheet({ rx, logos = [], navigate, preview }) {
  return (
    <div className={preview ? "" : "bg-slate-100 min-h-screen py-6"}>
      {!preview && (
        <div className="no-print max-w-[210mm] mx-auto px-4 mb-4 flex gap-2">
          <Button variant="outline" onClick={() => navigate("/desk")}><ArrowLeft className="w-4 h-4" /> Desk</Button>
          <Button onClick={() => window.print()} data-testid="print-a4-prescription-button"><Printer className="w-4 h-4" /> Print A4</Button>
        </div>
      )}

      <div className="print-a4 bg-white mx-auto shadow-lg" style={{ width: "210mm", minHeight: preview ? "auto" : "297mm", padding: "16mm" }} data-testid="a4-prescription-sheet">
        {/* Letterhead */}
        <div className="flex items-start justify-between border-b-2 border-slate-900 pb-4 gap-4">
          <div className="flex items-center gap-3">
            {logos.map((lg, i) => (
              <img key={lg.id || i} src={lg.data_url} alt={lg.name} className="h-12 w-auto object-contain" />
            ))}
            <div>
              <h1 className="font-display text-lg font-extrabold text-slate-900" data-testid="rx-header-title">
                {RX_HEADER_LINES.map((l) => <span key={l} className="block">{l}</span>)}
              </h1>
              <p className="text-[10px] text-slate-600 mt-1" data-testid="rx-header-subtitle">{RX_HEADER_SUBTITLE}</p>
              <p className="text-xs text-slate-500 mt-1">{rx.camp_name} · {rx.venue}</p>
            </div>
          </div>
          <div className="text-center shrink-0">
            <QRCodeSVG value={`snp:${rx.patient_qr}`} size={90} />
            <p className="font-mono text-xs mt-1">#{rx.reg_no}</p>
          </div>
        </div>

        {/* Dynamic blocks */}
        <div className="mt-5 space-y-5">
          {RX_BLOCKS.map((b) => {
            if (b.type === "identity") {
              return (
                <div key={b.id} className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm" data-testid="rx-block-identity">
                  <Line k="Reg No" v={`#${rx.reg_no}`} />
                  <Line k="Date" v={rx.date} />
                  <Line k="Name" v={rx.full_name} />
                  <Line k="Age / Sex" v={`${rx.age ?? "-"} / ${rx.gender || "-"}`} />
                  <Line k="Phone" v={rx.phone || "-"} />
                  <Line k="Address" v={rx.address || "-"} />
                </div>
              );
            }
            if (b.type === "signature") {
              return (
                <div key={b.id} className="flex justify-end pt-6 text-sm text-slate-500">
                  <span className="border-t border-slate-400 pt-1 px-8">{b.label}</span>
                </div>
              );
            }
            return (
              <div key={b.id} data-testid={`rx-block-${b.id}`}>
                <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">{b.label}</p>
                <div style={{ height: `${b.height || 20}mm` }} className="border-b border-slate-300 mt-1" />
              </div>
            );
          })}
        </div>

        <div className="border-t border-slate-300 pt-3 mt-6 text-xs text-slate-500" data-testid="rx-footer">
          {RX_FOOTER}
        </div>
      </div>
    </div>
  );
}

function Line({ k, v }) {
  return <div><span className="text-slate-400 mr-2">{k}:</span><span className="font-semibold text-slate-900">{v}</span></div>;
}
