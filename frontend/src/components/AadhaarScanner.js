import React, { useState, useRef, useCallback } from "react";
import { Badge } from "./ui";
import { ScanLine } from "lucide-react";
import {
  useAadhaarCamera,
  useAadhaarDecode,
  AadhaarModeButtons,
  AadhaarCameraView,
  AadhaarManualInput,
  AadhaarScannerStatus,
} from "./aadhaar";

export default function AadhaarScanner({ onScanned, disabled }) {
  const [mode, setMode] = useState("idle"); // idle | camera | manual
  const fileRef = useRef(null);

  const {
    payload,
    setPayload,
    error,
    setError,
    outcome,
    setOutcome,
    source,
    busy,
    decode,
    scanFile,
  } = useAadhaarDecode({ onScanned });

  const handleScanSuccess = useCallback(
    (decodedText) => {
      setMode("idle");
      setPayload(decodedText);
      decode(decodedText);
    },
    [decode, setPayload]
  );

  const handleCameraError = useCallback(
    (errorMsg) => {
      setError(errorMsg);
      setMode("idle");
    },
    [setError]
  );

  const {
    cameraState,
    cameras,
    torchAvailable,
    torchOn,
    startCamera: baseStartCamera,
    stopCamera,
    switchCamera,
    toggleTorch,
    readerId,
  } = useAadhaarCamera({
    readerId: "aadhaar-reader-region",
    onScanSuccess: handleScanSuccess,
    onError: handleCameraError,
  });

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      setError("");
      setOutcome("");
      setMode("camera");
      await baseStartCamera(cameraIndexToUse);
    },
    [baseStartCamera, setError, setOutcome]
  );

  return (
    <div className="rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <p className="font-display font-bold text-slate-900">Aadhaar Secure QR scan</p>
        <Badge tone="emerald" className="ml-auto">
          Offline decode
        </Badge>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Scan the QR on the Aadhaar card / e-Aadhaar. Camera, USB scanner, or photo upload — decoded on-device, no UIDAI call, only last-4 stored.
      </p>

      {/* Capture modes */}
      <AadhaarModeButtons
        mode={mode}
        setMode={setMode}
        disabled={disabled}
        busy={busy}
        cameraState={cameraState}
        startCamera={startCamera}
        stopCamera={stopCamera}
        scanFile={(file) => scanFile(file, `${readerId}-file`)}
        fileRef={fileRef}
      />

      {/* Camera viewfinder */}
      <AadhaarCameraView
        mode={mode}
        readerId={readerId}
        cameraState={cameraState}
        torchAvailable={torchAvailable}
        torchOn={torchOn}
        toggleTorch={toggleTorch}
        cameras={cameras}
        switchCamera={switchCamera}
      />

      {/* USB wedge / manual textarea */}
      <AadhaarManualInput
        mode={mode}
        payload={payload}
        setPayload={setPayload}
        disabled={disabled}
        busy={busy}
        decode={decode}
      />

      {/* Status alerts and error handling */}
      <AadhaarScannerStatus
        busy={busy}
        mode={mode}
        outcome={outcome}
        source={source}
        error={error}
        cameraState={cameraState}
        startCamera={startCamera}
      />
    </div>
  );
}
