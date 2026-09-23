import React from "react";
import { Card } from "../ui";
import { FulfilmentStation, FULFILMENT_LINES } from "./FulfilmentStation";

export function FulfilmentSection({
  line,
  data,
  otDays,
  specsDays,
  powers,
  onDone,
  navigate,
  setBanner,
  onBusyChange,
}) {
  if (!FULFILMENT_LINES[line]) return null;
  return (
    <Card data-testid="fulfilment-section">
      <FulfilmentStation
        key={`${data?.registration?.id || data?.transcription?.id || "none"}-${line}`}
        line={line}
        data={data}
        otDays={otDays}
        specsDays={specsDays}
        powers={powers}
        onDone={onDone}
        navigate={navigate}
        setBanner={setBanner}
        onBusyChange={onBusyChange}
      />
    </Card>
  );
}
