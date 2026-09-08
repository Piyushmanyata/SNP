import React from "react";
import { Alert, Button, Spinner } from "../ui";
import { Lock, RefreshCw } from "lucide-react";

export function AadhaarScannerStatus({
  busy,
  mode,
  outcome,
  source,
  error,
  cameraState,
  startCamera,
}) {
  return (
    <>
      {busy && mode !== "manual" && (
        <div role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-slate-700 mt-2">
          <Spinner className="w-3.5 h-3.5 text-emerald-600" />
          <span>Reading Aadhaar… Please wait.</span>
        </div>
      )}

      {outcome && outcome !== "card" && outcome !== "review" && (
        <Alert tone="amber" className="mt-3">
          {error}
        </Alert>
      )}
      {outcome === "card" && (
        <Alert tone="emerald" className="mt-3">
          <span className="inline-flex items-center gap-1">
            <Lock className="w-3.5 h-3.5" /> Identity locked from card
            {source === "demo" ? " (demo)" : source ? " (Secure QR)" : ""}.
          </span>
        </Alert>
      )}
      {!outcome && error && (
        <div className="mt-3">
          <Alert tone="rose">{error}</Alert>
          {cameraState === "error" && (
            <div className="mt-2 flex gap-2">
              <Button
                variant="outline"
                size="sm"
                type="button"
                onClick={() => startCamera()}
                data-testid="aadhaar-camera-retry"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Retry Camera
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
