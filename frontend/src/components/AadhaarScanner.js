import React, { useState, useRef, useEffect } from "react";
import { Html5Qrcode } from "html5-qrcode";
import api, { formatApiError } from "../lib/api";
import { Button, Field, Alert, Badge } from "./ui";
import { ScanLine, Sparkles, Lock, Camera, Upload, X, Keyboard } from "lucide-react";

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
  const [mode, setMode] = useState("idle"); // idle | camera | manual
  const [source, setSource] = useState("");
  const scannerRef = useRef(null);
  const fileRef = useRef(null);
  const readerId = "aadhaar-reader-region";

  const stopCamera = async () => {
    if (scannerRef.current) {
      try { await scannerRef.current.stop(); } catch (e) {}
      try { await scannerRef.current.clear(); } catch (e) {}
      scannerRef.current = null;
    }
  };

  useEffect(() => () => { stopCamera(); }, []);

  const decode = async (text) => {
    setBusy(true); setError(""); setOutcome("");
    try {
      const { data } = await api.post("/aadhaar/decode", { payload: text });
      setOutcome(data.outcome);
      setSource(data.source || "");
      if (data.outcome === "card") onScanned(data.data);
      else setError(data.message);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const startCamera = async () => {
    setError(""); setOutcome(""); setMode("camera");
    setTimeout(async () => {
      try {
        const scanner = new Html5Qrcode(readerId, { verbose: false });
        scannerRef.current = scanner;
        await scanner.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: undefined, aspectRatio: 1.2 },
          async (decodedText) => {
            await stopCamera();
            setMode("idle");
            setPayload(decodedText);
            decode(decodedText);
          },
          () => {}
        );
      } catch (e) {
        setMode("idle");
        setError("Unable to start camera. Use photo upload or USB scanner instead.");
      }
    }, 150);
  };

  const scanFile = async (file) => {
    if (!file) return;
    setError(""); setOutcome(""); setBusy(true);
    const scanner = new Html5Qrcode(readerId + "-file", { verbose: false });
    try {
      const text = await scanner.scanFile(file, false);
      setPayload(text);
      await decode(text);
    } catch (e) {
      setError("No Aadhaar QR found in the image. Try a clearer photo.");
    } finally {
      try { await scanner.clear(); } catch (er) {}
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <p className="font-display font-bold text-slate-900">Aadhaar Secure QR scan</p>
        <Badge tone="emerald" className="ml-auto">Offline decode</Badge>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Scan the QR on the Aadhaar card / e-Aadhaar. Camera, USB scanner, or photo upload — decoded on-device, no UIDAI call, only last-4 stored.
      </p>

      {/* Capture modes */}
      <div className="flex flex-wrap gap-2 mb-3">
        {mode !== "camera" ? (
          <Button variant="secondary" size="sm" type="button" onClick={startCamera} disabled={disabled || busy} data-testid="aadhaar-camera-button">
            <Camera className="w-4 h-4" /> Scan with camera
          </Button>
        ) : (
          <Button variant="danger" size="sm" type="button" onClick={async () => { await stopCamera(); setMode("idle"); }} data-testid="aadhaar-camera-stop">
            <X className="w-4 h-4" /> Stop camera
          </Button>
        )}
        <Button variant="outline" size="sm" type="button" onClick={() => fileRef.current?.click()} disabled={disabled || busy} data-testid="aadhaar-upload-button">
          <Upload className="w-4 h-4" /> Upload photo
        </Button>
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => scanFile(e.target.files?.[0])} data-testid="aadhaar-file-input" />
        <Button variant="outline" size="sm" type="button" onClick={() => setMode(mode === "manual" ? "idle" : "manual")} disabled={disabled} data-testid="aadhaar-manual-toggle">
          <Keyboard className="w-4 h-4" /> USB / paste
        </Button>
      </div>

      {mode === "camera" && (
        <div className="mb-3 rounded-xl overflow-hidden border border-emerald-300 bg-black">
          <div id={readerId} className="w-full" data-testid="aadhaar-camera-region" />
        </div>
      )}
      <div id={readerId + "-file"} className="hidden" />

      {mode === "manual" && (
        <Field label="Scanned QR payload (USB wedge / paste)">
          <textarea
            className="w-full min-h-[70px] px-3.5 py-2.5 rounded-xl border border-slate-300 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            placeholder="Paste the big-number Secure QR, or a demo AADHAAR|... string"
            disabled={disabled || busy}
            data-testid="aadhaar-qr-input"
          />
          <div className="flex flex-wrap gap-2 mt-2">
            <Button variant="ghost" size="sm" type="button" onClick={() => setPayload(randDemo())} disabled={disabled || busy} data-testid="generate-demo-aadhaar-button">
              <Sparkles className="w-4 h-4" /> Demo card
            </Button>
            <Button size="sm" type="button" onClick={() => decode(payload)} disabled={disabled || busy || !payload} data-testid="aadhaar-scan-button">
              {busy ? "Decoding…" : "Decode"}
            </Button>
          </div>
        </Field>
      )}

      {busy && mode !== "manual" && <p className="text-xs text-slate-500 mt-1">Decoding…</p>}

      {outcome && outcome !== "card" && <Alert tone="amber" className="mt-3">{error}</Alert>}
      {outcome === "card" && (
        <Alert tone="emerald" className="mt-3">
          <span className="inline-flex items-center gap-1">
            <Lock className="w-3.5 h-3.5" /> Identity locked from card{source === "demo" ? " (demo)" : source ? " (Secure QR)" : ""}.
          </span>
        </Alert>
      )}
      {!outcome && error && <Alert className="mt-3">{error}</Alert>}
    </div>
  );
}
