import React from "react";
import { Spinner } from "../ui";
import { SwitchCamera, Zap, ZapOff } from "lucide-react";

export function AadhaarCameraView({
  mode,
  videoRef,
  cameraState,
  torchAvailable,
  torchOn,
  toggleTorch,
  cameras,
  switchCamera,
}) {
  return (
    <>
      <div
        className={
          mode === "camera"
            ? "relative mb-3 rounded-xl overflow-hidden border-2 border-emerald-500 bg-black shadow-lg"
            : "hidden"
        }
      >
        <video
          ref={videoRef}
          className="w-full object-contain bg-black"
          autoPlay
          playsInline
          muted
          data-testid="aadhaar-camera-region"
        />

        <div className="absolute top-2 right-2 flex items-center gap-1.5 z-20">
          {torchAvailable && (
            <button
              type="button"
              onClick={toggleTorch}
              className={`p-2 rounded-lg backdrop-blur-md transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center ${
                torchOn
                  ? "bg-amber-400 text-slate-900"
                  : "bg-slate-900/70 text-white hover:bg-slate-900"
              }`}
              title={torchOn ? "Turn off torch" : "Turn on torch"}
              aria-label={torchOn ? "Turn off torch" : "Turn on torch"}
              aria-pressed={torchOn}
              data-testid="aadhaar-torch-toggle"
            >
              {torchOn ? <Zap className="w-4 h-4 fill-current" /> : <ZapOff className="w-4 h-4" />}
            </button>
          )}
          {cameras.length > 1 && (
            <button
              type="button"
              onClick={switchCamera}
              className="p-2 rounded-lg bg-slate-900/70 hover:bg-slate-900 text-white backdrop-blur-md transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
              title="Switch Camera"
              aria-label="Switch camera"
              disabled={cameraState !== "scanning"}
              data-testid="aadhaar-switch-camera"
            >
              <SwitchCamera className="w-4 h-4" />
            </button>
          )}
        </div>

        {cameraState === "scanning" && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-4">
            <div className="relative w-[90%] max-h-[90%] aspect-square border-2 border-dashed border-emerald-400/80 rounded-2xl flex items-center justify-center">
              <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-emerald-400 rounded-tl-lg" />
              <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-emerald-400 rounded-tr-lg" />
              <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-emerald-400 rounded-bl-lg" />
              <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-emerald-400 rounded-br-lg" />
              <p className="text-[11px] font-medium text-emerald-200 bg-slate-950/70 px-2 py-0.5 rounded-full shadow text-center">
                Align Aadhaar QR inside frame
              </p>
            </div>
          </div>
        )}

        {cameraState === "starting" && (
          <div className="absolute inset-0 bg-slate-900/90 flex flex-col items-center justify-center text-white p-4">
            <Spinner className="w-8 h-8 text-emerald-400 mb-2" />
            <p className="text-sm font-medium">Starting camera…</p>
            <p className="text-xs text-slate-400 mt-1">Requesting device access</p>
          </div>
        )}
      </div>
      {mode === "camera" && (
        <p className="mb-3 text-sm text-slate-700">
          Clean the lens. Keep the whole QR in the frame, avoid glare, and hold steady for a moment. Move back slightly if it looks blurred.
        </p>
      )}
    </>
  );
}
