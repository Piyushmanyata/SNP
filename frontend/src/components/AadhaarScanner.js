import React, { useState, useRef, useCallback, useEffect } from "react";
import { ScanLine } from "lucide-react";
import { Button, Field, Input } from "./ui";
import { AadhaarReviewForm } from "./aadhaar/AadhaarReviewForm";
import {
  useAadhaarCamera,
  useAadhaarDecode,
  decodePayload,
  AadhaarModeButtons,
  AadhaarCameraView,
  AadhaarManualInput,
  AadhaarScannerStatus,
  AadhaarFallbackPanel,
} from "./aadhaar";
import { primeFeedback, signalSuccess } from "../lib/feedback";

const PATIENT_CODE = /^snp:[a-z0-9-]+$/i;
const PRESCRIPTION_QR_ONLY = "Scan the QR on the prescription.";

function prefersTouch() {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(pointer: coarse)")?.matches);
}

export default function AadhaarScanner({
  onScanned,
  onTranscribed,
  onCaptureStart,
  onFailure,
  onScanStall,
  onPatientCode,
  resolvePayload,
  patientCodeOnly = false,
  usbFirst = false,
  disabled,
}) {
  const [touchFirst] = useState(prefersTouch);
  const [mode, setMode] = useState(() => (usbFirst && !touchFirst ? "manual" : "idle"));
  const [fallbacksRevealed, setFallbacksRevealed] = useState(false);
  const [hint, setHint] = useState(false);
  const fileRef = useRef(null);
  const selectedFile = useRef(null);
  const [password, setPassword] = useState("");

  const classify = useCallback(async (value) => {
    const text = String(value ?? "").trim();
    if (onPatientCode && PATIENT_CODE.test(text)) {
      return await onPatientCode(text)
        ? { outcome: "card", source: "patient_code" }
        : { outcome: "not-aadhaar", source: "patient_code", message: "No patient found for that code." };
    }
    if (patientCodeOnly) return { outcome: "not-aadhaar", message: PRESCRIPTION_QR_ONLY };
    return resolvePayload ? resolvePayload(text) : decodePayload(text);
  }, [onPatientCode, patientCodeOnly, resolvePayload]);

  const {
    error,
    setError,
    outcome,
    source,
    busy,
    decode,
    cancelDecode,
    scanFile,
    reviewData,
    passwordRequired,
  } = useAadhaarDecode({ classify, onScanned, onFailure, canReview: Boolean(onTranscribed) });

  useEffect(() => {
    if (!busy && !passwordRequired) selectedFile.current = null;
  }, [busy, passwordRequired]);

  const handleLock = useCallback(() => {
    setMode("idle");
    setHint(false);
    signalSuccess();
  }, []);

  const handleCameraError = useCallback(
    (message) => {
      setError(message);
      setMode("idle");
      onFailure?.("error");
    },
    [setError, onFailure]
  );

  const handleHint = useCallback(() => setHint(true), []);

  const handleScanStall = useCallback(() => {
    setFallbacksRevealed(true);
    onFailure?.("error");
    onScanStall?.();
  }, [onFailure, onScanStall]);

  const {
    cameraState,
    cameras,
    torchAvailable,
    torchOn,
    zoom,
    startCamera: baseStartCamera,
    stopCamera: baseStopCamera,
    switchCamera: baseSwitchCamera,
    toggleTorch,
    toggleZoom,
    focus,
    videoRef,
  } = useAadhaarCamera({
    decode,
    onLock: handleLock,
    onError: handleCameraError,
    onHint: handleHint,
    onScanStall: handleScanStall,
  });

  useEffect(() => {
    if (!disabled) return;
    cancelDecode();
    selectedFile.current = null;
    setPassword("");
    setMode((current) => (current === "camera" ? "idle" : current));
    baseStopCamera();
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
      primeFeedback();
      cancelDecode();
      onCaptureStart?.();
      setFallbacksRevealed(false);
      setHint(false);
      setMode("camera");
      await baseStartCamera(cameraIndexToUse);
    },
    [baseStartCamera, cancelDecode, onCaptureStart]
  );

  const upload = async (file) => {
    onCaptureStart?.();
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
    <div className={patientCodeOnly ? "mt-3" : "rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5"}>
      {!patientCodeOnly && (
        <>
          <div className="flex items-center gap-2 mb-2">
            <ScanLine className="w-5 h-5 text-emerald-700" />
            <p className="font-display font-bold text-slate-900">Scan Aadhaar QR</p>
          </div>
          <p className="text-xs text-slate-700 mb-3">
            {onPatientCode ? "Scan the patient's Aadhaar QR or the QR on their registration slip." : "Scan the QR or upload a photo or e-Aadhaar PDF."}{onTranscribed ? " If the QR is unreadable, review extracted text." : ""} Uploaded documents and PDF passwords are not retained. Only the last four Aadhaar digits are saved.
          </p>
        </>
      )}

      <AadhaarFallbackPanel
        revealed={fallbacksRevealed && !patientCodeOnly}
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
        cameraOnly={patientCodeOnly}
        touchFirst={touchFirst}
      />

      {busy && mode !== "manual" && (
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

      {!busy && reviewData && (
        <AadhaarReviewForm initial={reviewData} disabled={disabled} onConfirm={(details) => {
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
        zoom={zoom}
        toggleZoom={toggleZoom}
        focus={focus}
        hint={hint}
      />

      <AadhaarManualInput
        mode={mode}
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
