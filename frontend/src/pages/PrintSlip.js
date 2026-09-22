import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import { displayDateRange } from "../lib/dates";
import { Button, Alert, Spinner } from "../components/ui";
import { Printer, ArrowLeft } from "lucide-react";

const TITLES = {
  ot: { hi: "मोतियाबिंद (IOL) ऑपरेशन", en: "IOL Surgery" },
  specs: { hi: "चश्मा", en: "Spectacles" },
};

const EYES = {
  R: "दायीं आँख / Right eye",
  L: "बायीं आँख / Left eye",
};

export default function PrintSlip() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [slip, setSlip] = useState(null);
  const [reg, setReg] = useState(null);
  const [campName, setCampName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.get(`/clinical/slip/${id}`)
      .then((r) => {
        if (!active) return;
        setSlip(r.data.slip);
        setReg(r.data.registration);
        setCampName(r.data.camp_name || "");
      })
      .catch((e) => { if (active) setError(formatApiError(e)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner className="w-8 h-8 text-emerald-500" /></div>;
  if (error) return <div className="max-w-md mx-auto p-6"><Alert className="mb-4">{error}</Alert><Button variant="outline" onClick={() => navigate(-1)}><ArrowLeft className="w-4 h-4" /> Back</Button></div>;

  const title = TITLES[slip.item_type] || TITLES.specs;

  return (
    <div className="bg-slate-100 min-h-screen py-6 print-token-page">
      <style>{`@media print { @page { size: 105mm 148mm; margin: 5mm; } .print-token-page { padding: 0; min-height: 0; background: white; } .print-a6 { break-inside: avoid; padding: 0 !important; } }`}</style>
      <div className="no-print max-w-[105mm] mx-auto mb-4 flex gap-2">
        <Button size="sm" variant="outline" aria-label="Back to clinical desk" onClick={() => navigate("/clinical")}><ArrowLeft className="w-4 h-4" /></Button>
        <Button size="sm" onClick={() => window.print()} data-testid="print-a6-token-button"><Printer className="w-4 h-4" /> Print</Button>
      </div>

      <div
        className="print-a6 bg-white mx-auto shadow-lg p-4 text-slate-950"
        style={{ width: "100%", maxWidth: "95mm", overflowWrap: "anywhere" }}
        data-testid="a6-token"
      >
        <div className="text-center border-b-2 border-slate-900 pb-2 mb-3">
          <p className="font-display font-bold text-lg text-slate-900">{campName || "SNP"}</p>
          <p className="mt-1 text-base font-semibold">{title.hi} / {title.en}</p>
          {EYES[slip.ot_eye] && <p className="text-base font-bold">{EYES[slip.ot_eye]}</p>}
        </div>
        <p className="text-sm mb-1"><span className="text-slate-500">नाम / Name</span> — {reg?.full_name}</p>
        <p className="text-lg font-bold mb-2">क्रमांक / Token — #{reg?.reg_no}</p>
        <p className="text-sm mb-1"><span className="text-slate-500">तिथि / Date</span> — {displayDateRange(slip.collection_date, slip.collection_end_date)}</p>
        {slip.collection_start_time && slip.collection_end_time && (
          <p className="text-sm mb-1" data-testid="token-window">
            <span className="text-slate-500">समय / Time</span> — {slip.collection_start_time}–{slip.collection_end_time}
          </p>
        )}
        <p className="text-sm mb-3"><span className="text-slate-500">स्थान / Venue</span> — {slip.collection_venue}</p>
        {slip.item_type === "ot" ? (
          <div className="text-sm border-t border-slate-300 pt-3">
            {slip.bp && <p className="mb-1"><span className="text-slate-500">बीपी / BP</span> — {slip.bp}</p>}
            {slip.blood_sugar && <p className="mb-1"><span className="text-slate-500">ब्लड शुगर / Blood sugar</span> — {slip.blood_sugar}</p>}
            <p>ऑपरेशन के दिन लाएँ: पर्चा, यह टोकन, आधार कार्ड, राशन कार्ड, मोबाइल फ़ोन।</p>
            <p className="font-semibold mt-2">सहायता / Help: 9835317006</p>
          </div>
        ) : <p className="text-sm font-semibold border-t border-slate-300 pt-3">चश्मा लेने के लिए यह टोकन साथ लाएँ / Bring this token for collection.</p>}
      </div>
    </div>
  );
}
