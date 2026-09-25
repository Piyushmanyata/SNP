import React, { useRef } from "react";
import { Button, Spinner } from "../ui";
import { Camera, Upload, X, Keyboard, Aperture } from "lucide-react";

const UPLOAD_ACCEPT = "image/*,.heic,.heif,application/pdf,.pdf";

function pick(event, scanFile) {
  const file = event.target.files?.[0];
  if (file) scanFile(file);
  event.target.value = "";
}

function Label({ en, hi, withHindi }) {
  if (!withHindi) return en;
  return (
    <span className="flex flex-col items-start leading-tight">
      {en}
      <span className="text-xs font-normal">{hi}</span>
    </span>
  );
}

export function AadhaarModeButtons({
  mode,
  setMode,
  disabled,
  busy,
  cameraState,
  startCamera,
  stopCamera,
  scanFile,
  fileRef,
  cameraOnly = false,
  touchFirst = false,
  forPatient = false,
}) {
  const photoRef = useRef(null);
  const blocked = disabled || busy || cameraState === "starting";
  const leaveCamera = async () => {
    if (mode === "camera") {
      await stopCamera();
      setMode("idle");
    }
  };
  return (
    <div className="flex flex-wrap gap-2 mb-3">
      {mode !== "camera" ? (
        <Button
          variant="secondary"
          size="lg"
          type="button"
          onClick={() => startCamera()}
          disabled={blocked}
          className="w-full sm:w-auto"
          data-testid="aadhaar-camera-button"
        >
          {cameraState === "starting" ? (
            <>
              <Spinner className="w-4 h-4" /> Starting…
            </>
          ) : (
            <>
              <Camera className="w-5 h-5" /> <Label en="Scan with camera" hi="कैमरे से स्कैन करें" withHindi={forPatient} />
            </>
          )}
        </Button>
      ) : (
        <Button
          variant="danger"
          size="lg"
          type="button"
          onClick={async () => {
            await stopCamera();
            setMode("idle");
          }}
          className="w-full sm:w-auto"
          data-testid="aadhaar-camera-stop"
        >
          <X className="w-5 h-5" /> Stop camera
        </Button>
      )}
      {!cameraOnly && (
        <>
          {touchFirst && (
            <>
              <Button
                variant="outline"
                size="md"
                type="button"
                onClick={async () => {
                  await leaveCamera();
                  photoRef.current?.click();
                }}
                disabled={blocked}
                className="flex-auto whitespace-nowrap sm:flex-none"
                data-testid="aadhaar-photo-button"
              >
                <Aperture className="w-4 h-4" /> <Label en="Take photo" hi="फोटो लें" withHindi={forPatient} />
              </Button>
              <input
                ref={photoRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => pick(e, scanFile)}
                data-testid="aadhaar-photo-input"
              />
            </>
          )}
          <Button
            variant="outline"
            size="md"
            type="button"
            onClick={async () => {
              await leaveCamera();
              fileRef.current?.click();
            }}
            disabled={blocked}
            className="flex-auto whitespace-nowrap sm:flex-none"
            data-testid="aadhaar-upload-button"
          >
            <Upload className="w-4 h-4" /> <Label en="Upload photo / PDF" hi="फोटो / PDF अपलोड करें" withHindi={forPatient} />
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept={UPLOAD_ACCEPT}
            className="hidden"
            onChange={(e) => pick(e, scanFile)}
            data-testid="aadhaar-file-input"
          />
          {!forPatient && (
            <Button
              variant="outline"
              size="md"
              type="button"
              onClick={async () => {
                if (mode === "camera") await stopCamera();
                setMode(mode === "manual" ? "idle" : "manual");
              }}
              disabled={disabled || busy}
              className="flex-auto whitespace-nowrap sm:flex-none"
              aria-pressed={mode === "manual"}
              data-testid="aadhaar-manual-toggle"
            >
              <Keyboard className="w-4 h-4" /> USB / paste
            </Button>
          )}
        </>
      )}
    </div>
  );
}
