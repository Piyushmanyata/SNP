import React from "react";
import { Button, Field } from "../ui";
import { Sparkles } from "lucide-react";

const NAMES = [
  "Ramesh Kumar",
  "Sita Devi",
  "Abdul Rahman",
  "Priya Sharma",
  "Gopal Das",
  "Fatima Bibi",
  "Arjun Reddy",
  "Lakshmi Nair",
];
const ADDRS = [
  "12 MG Road, Kolkata",
  "Village Rampur, Dist. Nadia",
  "45 Station Rd, Howrah",
  "Ward 7, Barasat",
];

export function randDemo() {
  const name = NAMES[Math.floor(Math.random() * NAMES.length)];
  const gender = Math.random() > 0.5 ? "M" : "F";
  const year = 1955 + Math.floor(Math.random() * 55);
  const month = String(1 + Math.floor(Math.random() * 12)).padStart(2, "0");
  const day = String(1 + Math.floor(Math.random() * 28)).padStart(2, "0");
  const last4 = String(1000 + Math.floor(Math.random() * 8999));
  const addr = ADDRS[Math.floor(Math.random() * ADDRS.length)];
  return `AADHAAR|${name}|${gender}|${year}-${month}-${day}|${last4}|${addr}`;
}

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
    <Field label="Scanned QR payload (USB wedge / paste)">
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
        placeholder="Paste the big-number Secure QR, or a demo AADHAAR|... string (Press Enter to decode)"
        disabled={disabled || busy}
        data-testid="aadhaar-qr-input"
      />
      <div className="flex flex-wrap gap-2 mt-2">
        <Button
          variant="ghost"
          size="sm"
          type="button"
          onClick={() => setPayload(randDemo())}
          disabled={disabled || busy}
          data-testid="generate-demo-aadhaar-button"
        >
          <Sparkles className="w-4 h-4" /> Demo card
        </Button>
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
