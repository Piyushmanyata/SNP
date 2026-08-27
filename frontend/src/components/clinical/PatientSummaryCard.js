import React from "react";
import { Card, Button, Badge, StatusBadge } from "../ui";
import { History, Lock } from "lucide-react";

export function PatientSummaryCard({ data, locked, openHistory }) {
  if (!data) return null;

  return (
    <Card className="mb-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono font-bold text-emerald-600 text-lg">
          #{data.registration.reg_no}
        </span>
        <div className="flex-1">
          <p className="font-display font-bold text-slate-900">
            {data.registration.full_name}
          </p>
          <p className="text-xs text-slate-400">
            {data.registration.gender_label} · {data.registration.age ?? "-"} yrs
          </p>
        </div>
        <StatusBadge status={data.registration.queue_status} />
        {locked && (
          <Badge tone="indigo">
            <Lock className="w-3 h-3 mr-1 inline" />
            Locked
          </Badge>
        )}
        {data.person && (
          <Button
            size="sm"
            variant="outline"
            onClick={openHistory}
            data-testid="clinical-history-button"
          >
            <History className="w-4 h-4" /> History
          </Button>
        )}
      </div>
    </Card>
  );
}
