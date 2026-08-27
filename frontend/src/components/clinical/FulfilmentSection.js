import React from "react";
import { Card } from "../ui";
import { FulfilmentStation } from "./FulfilmentStation";

export function FulfilmentSection({
  data,
  otDays,
  onDone,
  navigate,
  setBanner,
  setError,
}) {
  return (
    <Card>
      <h3 className="font-display font-bold text-slate-900 mb-4">
        Clinical Line Stations
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {["medicine", "specs", "ot"].map((type) => (
          <FulfilmentStation
            key={type}
            type={type}
            data={data}
            otDays={otDays}
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
