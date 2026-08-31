import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import { Button, Alert, Spinner } from "../components/ui";
import { Printer, ArrowLeft } from "lucide-react";

const TITLES = {
  ot: { hi: "ऑपरेशन", en: "Surgery" },
  specs: { hi: "चश्मा", en: "Spectacles" },
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
    api.get(`/clinical/slip/${id}`)
      .then((r) => {
        setSlip(r.data.slip);
        setReg(r.data.registration);
        setCampName(r.data.camp_name || "");
      })
      .catch((e) => setError(formatApiError(e)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner className="w-8 h-8 text-emerald-500" /></div>;
  if (error) return <div className="max-w-md mx-auto p-6"><Alert className="mb-4">{error}</Alert><Button variant="outline" onClick={() => navigate(-1)}><ArrowLeft className="w-4 h-4" /> Back</Button></div>;

  const title = TITLES[slip.item_type] || TITLES.specs;

  return (
    <div className="bg-slate-100 min-h-screen py-6">
      <style>{`@media print { @page { size: 105mm 148mm; margin: 0; } }`}</style>
      <div className="no-print max-w-[105mm] mx-auto mb-4 flex gap-2">
        <Button size="sm" variant="outline" onClick={() => navigate("/clinical")}><ArrowLeft className="w-4 h-4" /></Button>
        <Button size="sm" onClick={() => window.print()} data-testid="print-a6-token-button"><Printer className="w-4 h-4" /> Print</Button>
      </div>

      <div
        className="print-a6 bg-white mx-auto shadow-lg p-6"
        style={{ width: "105mm", height: "148mm" }}
        data-testid="a6-token"
      >
        <div className="text-center border-b-2 border-slate-900 pb-3 mb-4">
          <p className="font-display font-bold text-lg text-slate-900">{campName || "SNP"}</p>
          <p className="mt-1 text-base font-semibold">{title.hi} / {title.en}</p>
        </div>
        <p className="text-sm mb-1"><span className="text-slate-500">नाम / Name</span> — {reg?.full_name}</p>
        <p className="text-sm mb-1"><span className="text-slate-500">पंजीकरण / Reg no</span> — #{reg?.reg_no}</p>
        <p className="text-sm mb-1"><span className="text-slate-500">संस्करण / Version</span> — v{slip.version}</p>
        <p className="text-sm mb-1"><span className="text-slate-500">तिथि / Date</span> — {slip.collection_date}</p>
        <p className="text-sm mb-3"><span className="text-slate-500">स्थान / Venue</span> — {slip.collection_venue}</p>
        <p className="text-center text-sm font-semibold mt-8">यह टोकन साथ लाएँ / Bring this Token</p>
      </div>
    </div>
  );
}
