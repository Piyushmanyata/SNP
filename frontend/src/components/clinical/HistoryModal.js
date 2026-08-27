import React from "react";
import { Modal, Card } from "../ui";

export function HistoryModal({ open, onClose, history }) {
  return (
    <Modal open={open} onClose={onClose} title="Clinical History" size="lg">
      {history?.length === 0 && (
        <p className="text-slate-400 text-sm">No prior clinical records.</p>
      )}
      <div className="space-y-3">
        {history?.map((h) => (
          <Card key={h.transcription?.id || h.reg_no} className="p-4">
            <div className="flex justify-between text-sm">
              <span className="font-semibold">
                {h.camp_name || "Camp"} · #{h.reg_no}
              </span>
              <span className="text-slate-400">
                {h.transcription?.created_at?.slice(0, 10)}
              </span>
            </div>
            <p className="text-sm text-slate-600 mt-1">
              Dx: {(h.transcription?.diagnosis_options || []).join(", ") || "-"}
              {h.transcription?.diagnosis_other
                ? `, ${h.transcription.diagnosis_other}`
                : ""}
            </p>
          </Card>
        ))}
      </div>
    </Modal>
  );
}
