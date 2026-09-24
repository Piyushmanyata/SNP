import React from "react";
import { Card } from "../ui";
import { PrescriptionSheet } from "../print/PrescriptionSheet";
import { Eye } from "lucide-react";

export function TemplatePreview({ sampleRx, logos }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 mb-3">
        <Eye className="w-5 h-5 text-slate-400" />
        <h3 className="font-display font-bold text-slate-900">A4 Preview</h3>
      </div>
      <div
        className="border border-slate-200 rounded-xl overflow-auto bg-slate-100 p-3"
        style={{ maxHeight: "70vh" }}
      >
        <div
          style={{ transform: "scale(0.55)", transformOrigin: "top left", width: "210mm" }}
          data-testid="tpl-preview"
        >
          <PrescriptionSheet rx={sampleRx} logos={logos} preview />
        </div>
      </div>
    </Card>
  );
}
