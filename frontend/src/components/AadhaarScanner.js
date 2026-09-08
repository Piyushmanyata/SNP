import React, { useState, useRef, useCallback } from "react";
import { ScanLine } from "lucide-react";
import {
  useAadhaarCamera,
  useAadhaarDecode,
  AadhaarModeButtons,
  AadhaarCameraView,
  AadhaarManualInput,
  AadhaarScannerStatus,
  AadhaarFallbackPanel,
} from "./aadhaar";

export default function AadhaarScanner({ onScanned, onFailure, onScanStall, disabled }) {
  const [mode, setMode] = useState("idle");
  const [fallbacksRevealed, setFallbacksRevealed] = useState(false);
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
    cancelDecode,
    scanFile,
  } = useAadhaarDecode({ onScanned, onFailure });

  const handleLock = useCallback(() => {
    setMode("idle");
  }, []);

  const handleCameraError = useCallback(
    (errorMsg) => {
      setError(errorMsg);
      setMode("idle");
    },
    [setError]
  );

  const handleHintFallbacks = useCallback(() => {
    setError("Hold the card steady in bright, even light. Move slightly farther away if the QR looks blurred.");
  }, [setError]);

  const handleScanStall = useCallback(() => {
    setFallbacksRevealed(true);
    if (onScanStall) onScanStall();
  }, [onScanStall]);

  const {
    cameraState,
    cameras,
    torchAvailable,
    torchOn,
    startCamera: baseStartCamera,
    stopCamera: baseStopCamera,
    switchCamera: baseSwitchCamera,
    toggleTorch,
    videoRef,
  } = useAadhaarCamera({
    decode,
    onLock: handleLock,
    onError: handleCameraError,
    onHintFallbacks: handleHintFallbacks,
    onScanStall: handleScanStall,
  });

  const stopCamera = useCallback(async () => {
    cancelDecode();
    await baseStopCamera();
  }, [cancelDecode, baseStopCamera]);

  const switchCamera = useCallback(async () => {
    cancelDecode();
    await baseSwitchCamera();
  }, [cancelDecode, baseSwitchCamera]);

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      cancelDecode();
      setError("");
      setOutcome("");
      setFallbacksRevealed(false);
      setMode("camera");
      await baseStartCamera(cameraIndexToUse);
    },
    [baseStartCamera, cancelDecode, setError, setOutcome]
  );

  return (
    <div className="rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <p className="font-display font-bold text-slate-900">Scan Aadhaar QR</p>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Scan the QR on the card or e-Aadhaar to fill details. Only the last four Aadhaar digits are saved.
      </p>

      <AadhaarFallbackPanel
        revealed={fallbacksRevealed}
        torchAvailable={torchAvailable}
        torchOn={torchOn}
        toggleTorch={toggleTorch}
        onUpload={async () => {
          await stopCamera();
          setMode("idle");
          fileRef.current?.click();
        }}
        onManual={async () => {
          await stopCamera();
          setMode("manual");
        }}
      />

      <AadhaarModeButtons
        mode={mode}
        setMode={setMode}
        disabled={disabled}
        busy={busy}
        cameraState={cameraState}
        startCamera={startCamera}
        stopCamera={stopCamera}
        scanFile={scanFile}
        fileRef={fileRef}
      />

      <AadhaarCameraView
        mode={mode}
        videoRef={videoRef}
        cameraState={cameraState}
        torchAvailable={torchAvailable}
        torchOn={torchOn}
        toggleTorch={toggleTorch}
        cameras={cameras}
        switchCamera={switchCamera}
      />

      <AadhaarManualInput
        mode={mode}
        payload={payload}
        setPayload={setPayload}
        disabled={disabled}
        busy={busy}
        decode={decode}
      />

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
