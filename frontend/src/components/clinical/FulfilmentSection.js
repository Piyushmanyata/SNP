import React from "react";
import { Card } from "../ui";
import { FulfilmentStation, LINE_ORDER } from "./FulfilmentStation";

export function FulfilmentSection({
  data,
  otDays,
  specsDays,
  onDone,
  navigate,
  setBanner,
  setError,
}) {
  return (
    <Card>
      <h3 className="font-display font-bold text-slate-900 mb-4">Fulfilment lines</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {LINE_ORDER.map((line) => (
          <FulfilmentStation
            key={`${data?.registration?.id || data?.transcription?.id || "none"}-${line}`}
            line={line}
            data={data}
            otDays={otDays}
            specsDays={specsDays}
            onDone={onDone}
            navigate={navigate}
            setBanner={setBanner}
            setError={setError}
          />
        ))}
      </div>
    </Card>
  );
}
