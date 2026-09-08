import React, { useState, useRef, useCallback, useEffect } from "react";
import { ScanLine } from "lucide-react";
import { Button, Field, Input } from "./ui";
import { AadhaarReviewForm } from "./aadhaar/AadhaarReviewForm";
import {
  useAadhaarCamera,
  useAadhaarDecode,
  AadhaarModeButtons,
  AadhaarCameraView,
  AadhaarManualInput,
  AadhaarScannerStatus,
  AadhaarFallbackPanel,
} from "./aadhaar";

export default function AadhaarScanner({ onScanned, onTranscribed, onCaptureStart, onFailure, onScanStall, disabled, allowManualEntry = true }) {
  const [mode, setMode] = useState("idle");
  const [fallbacksRevealed, setFallbacksRevealed] = useState(false);
  const fileRef = useRef(null);
  const selectedFile = useRef(null);
  const [password, setPassword] = useState("");

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
    reviewData,
    passwordRequired,
  } = useAadhaarDecode({ onScanned, onFailure });

  useEffect(() => {
    if (!busy && !passwordRequired) selectedFile.current = null;
  }, [busy, passwordRequired]);

  useEffect(() => () => { selectedFile.current = null; }, []);

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

  useEffect(() => {
    if (disabled) {
      cancelDecode();
      selectedFile.current = null;
      setPassword("");
      baseStopCamera();
    }
  }, [disabled, cancelDecode, baseStopCamera]);

  const stopCamera = useCallback(async () => {
    cancelDecode();
    selectedFile.current = null;
    setPassword("");
    await baseStopCamera();
  }, [cancelDecode, baseStopCamera]);

  const switchCamera = useCallback(async () => {
    cancelDecode();
    await baseSwitchCamera();
  }, [cancelDecode, baseSwitchCamera]);

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      cancelDecode();
      onCaptureStart?.();
      setError("");
      setOutcome("");
      setFallbacksRevealed(false);
      setMode("camera");
      await baseStartCamera(cameraIndexToUse);
    },
    [baseStartCamera, cancelDecode, setError, setOutcome, onCaptureStart]
  );

  const upload = async (file) => {
    onCaptureStart?.();
    setMode("idle");
    setPassword("");
    selectedFile.current = file;
    await scanFile(file);
  };

  const changeMode = (nextMode) => {
    cancelDecode();
    selectedFile.current = null;
    setPassword("");
    onCaptureStart?.();
    setMode(nextMode);
  };

  return (
    <div className="rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <p className="font-display font-bold text-slate-900">Scan Aadhaar QR</p>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Scan the QR or upload a photo or e-Aadhaar PDF. If the QR is unreadable, review extracted text. Uploaded documents and PDF passwords are not retained. Only the last four Aadhaar digits are saved.
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
        setMode={changeMode}
        disabled={disabled}
        busy={busy}
        cameraState={cameraState}
        startCamera={startCamera}
        stopCamera={stopCamera}
        scanFile={upload}
        fileRef={fileRef}
      />

      {onTranscribed && allowManualEntry && (
        <Button type="button" variant="outline" disabled={disabled} onClick={async () => {
          await stopCamera();
          changeMode("entry");
        }} data-testid="aadhaar-enter-details">Enter details manually</Button>
      )}
      {busy && (
        <Button type="button" variant="ghost" onClick={async () => { await stopCamera(); setMode("idle"); }}>Cancel reading</Button>
      )}

      {passwordRequired && (
        <div className="mt-3 space-y-2">
          <Field label="e-Aadhaar PDF password" hint="Used only to open this document; not saved">
            <Input type="password" autoComplete="off" value={password} disabled={busy || disabled} onChange={(e) => setPassword(e.target.value)} data-testid="aadhaar-pdf-password" />
          </Field>
          <Button type="button" disabled={busy || disabled || !password || !selectedFile.current} onClick={async () => {
            const value = password;
            setPassword("");
            await scanFile(selectedFile.current, value);
          }}>Open PDF</Button>
        </div>
      )}

      {!busy && (mode === "entry" || reviewData) && (
        <AadhaarReviewForm key={mode === "entry" ? "entry" : "review"} initial={mode === "entry" ? undefined : reviewData} disabled={disabled} onConfirm={(details) => {
          cancelDecode();
          selectedFile.current = null;
          setMode("idle");
          onTranscribed?.(details);
        }} />
      )}

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
