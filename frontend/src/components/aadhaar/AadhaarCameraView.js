import React from "react";
import { Spinner } from "../ui";
import { SwitchCamera, Zap, ZapOff, ZoomIn } from "lucide-react";

const OVERLAY_BUTTON = "p-2 rounded-lg backdrop-blur-md transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center gap-1 text-sm font-bold";

export function AadhaarCameraView({
  mode,
  videoRef,
  cameraState,
  torchAvailable,
  torchOn,
  toggleTorch,
  cameras,
  switchCamera,
  zoom,
  toggleZoom,
  focus,
  hint,
}) {
  const zoomLabel = zoom ? `${Math.round((zoom.value / zoom.min) * 10) / 10}×` : "";
  const tapToFocus = (event) => {
    const video = videoRef.current;
    if (!event.detail || !video?.videoWidth) {
      focus(0.5, 0.5);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const scale = Math.max(rect.width / video.videoWidth, rect.height / video.videoHeight);
    const clamp = (value) => Math.min(1, Math.max(0, value));
    focus(
      clamp(0.5 + (event.clientX - rect.left - rect.width / 2) / (video.videoWidth * scale)),
      clamp(0.5 + (event.clientY - rect.top - rect.height / 2) / (video.videoHeight * scale)),
    );
  };
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
          className="block w-full aspect-[3/4] sm:aspect-video max-h-[65vh] object-cover bg-black"
          autoPlay
          playsInline
          muted
          data-testid="aadhaar-camera-region"
        />

        {cameraState === "scanning" && (
          <button
            type="button"
            onClick={tapToFocus}
            className="absolute inset-0 z-10 cursor-crosshair"
            aria-label="Tap to focus the camera"
            data-testid="aadhaar-focus-area"
          />
        )}

        <div className="absolute top-2 right-2 flex items-center gap-1.5 z-20">
          {zoom && (
            <button
              type="button"
              onClick={toggleZoom}
              className={`${OVERLAY_BUTTON} ${zoom.value > zoom.min ? "bg-emerald-400 text-slate-900" : "bg-slate-900/70 text-white hover:bg-slate-900"}`}
              aria-label={`Zoom ${zoomLabel}. Tap to change`}
              data-testid="aadhaar-zoom-toggle"
            >
              <ZoomIn className="w-4 h-4" /> {zoomLabel}
            </button>
          )}
          {torchAvailable && (
            <button
              type="button"
              onClick={toggleTorch}
              className={`${OVERLAY_BUTTON} ${torchOn ? "bg-amber-400 text-slate-900" : "bg-slate-900/70 text-white hover:bg-slate-900"}`}
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
              className={`${OVERLAY_BUTTON} bg-slate-900/70 hover:bg-slate-900 text-white`}
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
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center [container-type:size]">
            <div className="relative w-[min(90cqw,90cqh)] h-[min(90cqw,90cqh)] rounded-2xl border-2 border-dashed border-emerald-400/80 flex items-end justify-center pb-2">
              <div className="absolute top-0 left-0 w-6 h-6 border-t-4 border-l-4 border-emerald-400 rounded-tl-xl" />
              <div className="absolute top-0 right-0 w-6 h-6 border-t-4 border-r-4 border-emerald-400 rounded-tr-xl" />
              <div className="absolute bottom-0 left-0 w-6 h-6 border-b-4 border-l-4 border-emerald-400 rounded-bl-xl" />
              <div className="absolute bottom-0 right-0 w-6 h-6 border-b-4 border-r-4 border-emerald-400 rounded-br-xl" />
              <p className="text-xs font-semibold text-white bg-slate-950/80 px-2.5 py-1 rounded-full text-center" data-testid="aadhaar-camera-tip">
                {hint ? "Move closer or farther until the QR is sharp. Tap to focus." : "Fill the box with the QR"}
              </p>
            </div>
          </div>
        )}

        {cameraState === "starting" && (
          <div className="absolute inset-0 min-h-[200px] bg-slate-900/90 flex flex-col items-center justify-center text-white p-4">
            <Spinner className="w-8 h-8 text-emerald-400 mb-2" />
            <p className="text-sm font-medium">Starting camera…</p>
            <p className="text-xs text-slate-300 mt-1">Allow camera access if asked</p>
          </div>
        )}
      </div>
    </>
  );
}
