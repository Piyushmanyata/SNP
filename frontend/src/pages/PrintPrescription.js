import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import api, { formatApiError } from "../lib/api";
import { Button, Alert, Spinner } from "../components/ui";
import { Printer, ArrowLeft } from "lucide-react";

export default function PrintPrescription() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [rx, setRx] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.post(`/desk/print/${id}`)
      .then((r) => setRx(r.data.prescription))
      .catch((e) => setError(formatApiError(e)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner className="w-8 h-8 text-emerald-500" /></div>;

  if (error) return (
    <div className="max-w-md mx-auto p-6">
      <Alert className="mb-4">{error}</Alert>
      <Button variant="outline" onClick={() => navigate(-1)}><ArrowLeft className="w-4 h-4" /> Back to desk</Button>
    </div>
  );

  return (
    <div className="bg-slate-100 min-h-screen py-6">
      <div className="no-print max-w-[210mm] mx-auto px-4 mb-4 flex gap-2">
        <Button variant="outline" onClick={() => navigate("/desk")}><ArrowLeft className="w-4 h-4" /> Desk</Button>
        <Button onClick={() => window.print()} data-testid="print-a4-prescription-button"><Printer className="w-4 h-4" /> Print A4</Button>
      </div>

      <div className="print-a4 bg-white mx-auto shadow-lg" style={{ width: "210mm", minHeight: "297mm", padding: "16mm" }} data-testid="a4-prescription-sheet">
        {/* Letterhead */}
        <div className="flex items-start justify-between border-b-2 border-slate-900 pb-4">
          <div>
            <h1 className="font-display text-2xl font-extrabold text-slate-900">{rx.camp_name}</h1>
            <p className="text-sm text-slate-600">{rx.venue}</p>
            <p className="text-xs text-slate-500 mt-1">SNP Free Eye Camp · Prescription</p>
          </div>
          <div className="text-center">
            <QRCodeSVG value={`snp:${rx.patient_qr}`} size={90} />
            <p className="font-mono text-xs mt-1">#{rx.reg_no}</p>
          </div>
        </div>

        {/* Identity block */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 mt-5 text-sm">
          <Line k="Reg No" v={`#${rx.reg_no}`} />
          <Line k="Date" v={rx.date} />
          <Line k="Name" v={rx.full_name} />
          <Line k="Age / Sex" v={`${rx.age ?? "-"} / ${rx.gender || "-"}`} />
          <Line k="Phone" v={rx.phone || "-"} />
          <Line k="Address" v={rx.address || "-"} />
        </div>

        {/* Blank clinical area */}
        <div className="mt-6 border-t border-slate-300 pt-4">
          <p className="font-mono text-xs uppercase tracking-widest text-slate-500 mb-3">Rx / Clinical Findings</p>
          <div className="space-y-6" style={{ minHeight: "150mm" }}>
            <BlankRow label="Diagnosis" />
            <BlankRow label="Vision (R / L)" />
            <BlankRow label="Prescription" />
            <BlankRow label="BP / Blood Sugar" />
            <BlankRow label="Advice" />
          </div>
        </div>

        <div className="flex justify-between items-end border-t border-slate-300 pt-3 mt-4 text-xs text-slate-500">
          <span>Paper prescription is the source of truth.</span>
          <span>Doctor's Signature</span>
        </div>
      </div>
    </div>
  );
}

function Line({ k, v }) {
  return <div><span className="text-slate-400 mr-2">{k}:</span><span className="font-semibold text-slate-900">{v}</span></div>;
}
function BlankRow({ label }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-600 mb-6">{label}</p>
      <div className="border-b border-slate-300" />
    </div>
  );
}
