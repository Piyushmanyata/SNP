import React from "react";
import { Button, Field } from "../ui";

export function AadhaarManualInput({
  mode,
  payload,
  setPayload,
  disabled,
  busy,
  decode,
}) {
  if (mode !== "manual") return null;

  return (
    <Field label="Scan with a USB reader or paste Aadhaar QR text">
      <textarea
        className="w-full min-h-[70px] px-3.5 py-2.5 rounded-xl border border-slate-300 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
        value={payload}
        onChange={(e) => setPayload(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && payload.trim()) {
            e.preventDefault();
            decode(payload.trim());
          }
        }}
        placeholder="Scan or paste the Aadhaar QR text, then press Enter"
        autoFocus
        disabled={disabled || busy}
        data-testid="aadhaar-qr-input"
      />
      <div className="flex flex-wrap gap-2 mt-2">
        <Button
          size="sm"
          type="button"
          onClick={() => decode(payload.trim())}
          disabled={disabled || busy || !payload.trim()}
          data-testid="aadhaar-scan-button"
        >
          {busy ? "Decoding…" : "Decode"}
        </Button>
      </div>
    </Field>
  );
}
