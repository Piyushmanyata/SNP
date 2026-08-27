import React, { useState } from "react";
import api, { formatApiError } from "../lib/api";
import { Button, Input, Field, Alert, Badge } from "./ui";
import { ScanLine, Sparkles, Lock } from "lucide-react";

const NAMES = ["Ramesh Kumar", "Sita Devi", "Abdul Rahman", "Priya Sharma", "Gopal Das", "Fatima Bibi", "Arjun Reddy", "Lakshmi Nair"];
const ADDRS = ["12 MG Road, Kolkata", "Village Rampur, Dist. Nadia", "45 Station Rd, Howrah", "Ward 7, Barasat"];

function randDemo() {
  const name = NAMES[Math.floor(Math.random() * NAMES.length)];
  const gender = Math.random() > 0.5 ? "M" : "F";
  const year = 1955 + Math.floor(Math.random() * 55);
  const month = String(1 + Math.floor(Math.random() * 12)).padStart(2, "0");
  const day = String(1 + Math.floor(Math.random() * 28)).padStart(2, "0");
  const last4 = String(1000 + Math.floor(Math.random() * 8999));
  const addr = ADDRS[Math.floor(Math.random() * ADDRS.length)];
  return `AADHAAR|${name}|${gender}|${year}-${month}-${day}|${last4}|${addr}`;
}

export default function AadhaarScanner({ onScanned, disabled }) {
  const [payload, setPayload] = useState("");
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);

  const scan = async () => {
    setBusy(true); setError(""); setOutcome("");
    try {
      const { data } = await api.post("/aadhaar/decode", { payload });
      setOutcome(data.outcome);
      if (data.outcome === "card") {
        onScanned(data.data);
      } else {
        setError(data.message);
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <p className="font-display font-bold text-slate-900">Aadhaar Secure QR scan</p>
        <Badge tone="amber" className="ml-auto">Simulated</Badge>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Paste the scanned QR string (camera / USB wedge), or generate a demo card. Offline decode — no data leaves the device beyond parsing.
      </p>
      <Field label="Scanned QR payload">
        <textarea
          className="w-full min-h-[70px] px-3.5 py-2.5 rounded-xl border border-slate-300 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          placeholder="AADHAAR|Name|M|1980-01-01|1234|Address"
          disabled={disabled || busy}
          data-testid="aadhaar-qr-input"
        />
      </Field>
      <div className="flex flex-wrap gap-2 mt-3">
        <Button variant="outline" size="sm" type="button" onClick={() => setPayload(randDemo())} disabled={disabled || busy} data-testid="generate-demo-aadhaar-button">
          <Sparkles className="w-4 h-4" /> Generate demo card
        </Button>
        <Button size="sm" type="button" onClick={scan} disabled={disabled || busy || !payload} data-testid="aadhaar-scan-button">
          {busy ? "Decoding…" : "Scan / Decode"}
        </Button>
      </div>
      {outcome && outcome !== "card" && (
        <Alert tone="amber" className="mt-3">{error}</Alert>
      )}
      {outcome === "card" && (
        <Alert tone="emerald" className="mt-3">
          <span className="inline-flex items-center gap-1"><Lock className="w-3.5 h-3.5" /> Identity locked from card.</span>
        </Alert>
      )}
      {!outcome && error && <Alert className="mt-3">{error}</Alert>}
    </div>
  );
}
