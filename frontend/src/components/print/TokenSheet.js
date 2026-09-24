import React from "react";
import { SPECS_HOURS, displayDateRange } from "../../lib/dates";

const TITLES = {
  ot: { hi: "मोतियाबिंद (IOL) ऑपरेशन", en: "IOL Surgery" },
  specs: { hi: "चश्मा", en: "Spectacles" },
};

const EYES = {
  R: "दायीं आँख / Right eye",
  L: "बायीं आँख / Left eye",
};

export function TokenSheet({ slip, registration, campName }) {
  const title = TITLES[slip.item_type] || TITLES.specs;
  return (
    <div
      className="bg-white text-slate-950"
      style={{ width: "105mm", height: "148mm", overflow: "hidden", padding: "6mm", overflowWrap: "anywhere" }}
      data-testid="a6-token"
    >
      {slip.superseded && (
        <p className="border-2 border-rose-700 text-rose-800 font-bold text-center p-1 mb-2" data-testid="token-superseded">
          पुराना टोकन — मान्य नहीं / Replaced — not valid
        </p>
      )}
      <div className="text-center border-b-2 border-slate-900 pb-2 mb-3">
        <p className="font-display font-bold text-lg text-slate-900">{campName || "SNP"}</p>
        <p className="mt-1 text-base font-semibold">{title.hi} / {title.en}</p>
        {EYES[slip.ot_eye] && <p className="text-base font-bold">{EYES[slip.ot_eye]}</p>}
      </div>
      <p className="text-sm mb-1"><span className="text-slate-500">नाम / Name</span> — {registration?.full_name}</p>
      <p className="text-lg font-bold mb-2">क्रमांक / Token — #{registration?.reg_no}</p>
      <p className="text-sm mb-1"><span className="text-slate-500">तिथि / Date</span> — {displayDateRange(slip.collection_date, slip.collection_end_date)}</p>
      {slip.item_type !== "ot" && (
        <p className="text-sm mb-1" data-testid="token-window">
          <span className="text-slate-500">समय / Time</span> — {SPECS_HOURS}
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
  );
}
