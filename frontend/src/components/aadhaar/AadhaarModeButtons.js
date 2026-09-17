import React from "react";
import { Button, Spinner } from "../ui";
import { Camera, Upload, X, Keyboard } from "lucide-react";

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
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-3">
      {mode !== "camera" ? (
        <Button
          variant="secondary"
          size="md"
          type="button"
          onClick={() => startCamera()}
          disabled={disabled || busy || cameraState === "starting"}
          className="min-h-[44px]"
          data-testid="aadhaar-camera-button"
        >
          {cameraState === "starting" ? (
            <>
              <Spinner className="w-4 h-4" /> Starting…
            </>
          ) : (
            <>
              <Camera className="w-4 h-4" /> Scan with camera
            </>
          )}
        </Button>
      ) : (
        <Button
          variant="danger"
          size="md"
          type="button"
          onClick={async () => {
            await stopCamera();
            setMode("idle");
          }}
          className="min-h-[44px]"
          data-testid="aadhaar-camera-stop"
        >
          <X className="w-4 h-4" /> Stop camera
        </Button>
      )}
      {!cameraOnly && (
        <>
          <Button
            variant="outline"
            size="md"
            type="button"
            onClick={async () => {
              if (mode === "camera") {
                await stopCamera();
                setMode("idle");
              }
              fileRef.current?.click();
            }}
            disabled={disabled || busy || cameraState === "starting"}
            className="min-h-[44px]"
            data-testid="aadhaar-upload-button"
          >
            <Upload className="w-4 h-4" /> Upload photo / PDF
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.heic,.heif,application/pdf,.pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) scanFile(file);
              e.target.value = "";
            }}
            data-testid="aadhaar-file-input"
          />
          <Button
            variant="outline"
            size="md"
            type="button"
            onClick={async () => {
              if (mode === "camera") await stopCamera();
              setMode(mode === "manual" ? "idle" : "manual");
            }}
            disabled={disabled || busy}
            className="min-h-[44px]"
            data-testid="aadhaar-manual-toggle"
          >
            <Keyboard className="w-4 h-4" /> USB / paste
          </Button>
        </>
      )}
    </div>
  );
}
