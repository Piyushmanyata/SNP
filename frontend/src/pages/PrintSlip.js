import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "../lib/api";
import { Button, Alert, Spinner } from "../components/ui";
import { Printer, ArrowLeft } from "lucide-react";

export default function PrintSlip() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [slip, setSlip] = useState(null);
  const [reg, setReg] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/clinical/slip/${id}`)
      .then((r) => { setSlip(r.data.slip); setReg(r.data.registration); })
      .catch((e) => setError(formatApiError(e)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner className="w-8 h-8 text-emerald-500" /></div>;
  if (error) return <div className="max-w-md mx-auto p-6"><Alert className="mb-4">{error}</Alert><Button variant="outline" onClick={() => navigate(-1)}><ArrowLeft className="w-4 h-4" /> Back</Button></div>;

  const title = slip.item_type === "ot" ? "OT / Surgery Slip" : "Spectacles Collection Slip";

  return (
    <div className="bg-slate-100 min-h-screen py-6">
      <div className="no-print max-w-[220px] mx-auto mb-4 flex gap-2">
        <Button size="sm" variant="outline" onClick={() => navigate("/clinical")}><ArrowLeft className="w-4 h-4" /></Button>
        <Button size="sm" onClick={() => window.print()} data-testid="print-58mm-thermal-slip-button"><Printer className="w-4 h-4" /> Print</Button>
      </div>

      <div className="print-thermal bg-white mx-auto shadow-lg p-3" style={{ width: "58mm", fontFamily: "monospace", fontSize: "11px" }} data-testid="thermal-slip">
        <div className="text-center border-b border-dashed border-black pb-2 mb-2">
          <p className="font-bold text-sm">SNP EYE CAMP</p>
          <p>{title}</p>
        </div>
        <p>Reg No: #{reg?.reg_no}</p>
        <p>Name: {reg?.full_name}</p>
        <p>Version: v{slip.version}</p>
        <div className="border-t border-dashed border-black my-2" />
        <p>Collect on: {slip.collection_date}</p>
        <p>Venue: {slip.collection_venue}</p>
        <div className="border-t border-dashed border-black my-2" />
        <p className="text-[10px]">{slip.instructions}</p>
        <p className="text-center mt-2 text-[10px]">Bring this slip.</p>
      </div>
    </div>
  );
}
