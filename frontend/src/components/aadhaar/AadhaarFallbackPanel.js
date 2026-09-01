import React from "react";
import { Button } from "../ui";
import { Flashlight, Upload, Keyboard } from "lucide-react";

export function AadhaarFallbackPanel({
  revealed,
  torchAvailable,
  torchOn,
  toggleTorch,
  onUpload,
  onManual,
}) {
  if (!revealed) return null;
  return (
    <div
      className="rounded-xl border border-amber-300 bg-amber-50 p-3 mb-3"
      data-testid="aadhaar-fallback-panel"
    >
      <p className="text-sm font-semibold text-amber-900">
        The camera is not reading this card.
      </p>
      <p className="text-xs text-amber-800 mt-1 mb-3">
        Turn on the torch, upload a photo of the QR, or type the details.
      </p>
      <div className="flex flex-wrap gap-2">
        {torchAvailable && (
          <Button
            variant="outline"
            size="md"
            type="button"
            onClick={toggleTorch}
            className="min-h-[44px]"
            data-testid="fallback-torch-button"
          >
            <Flashlight className="w-4 h-4" /> {torchOn ? "Torch off" : "Torch on"}
          </Button>
        )}
        <Button
          variant="outline"
          size="md"
          type="button"
          onClick={onUpload}
          className="min-h-[44px]"
          data-testid="fallback-upload-button"
        >
          <Upload className="w-4 h-4" /> Upload photo
        </Button>
        <Button
          variant="outline"
          size="md"
          type="button"
          onClick={onManual}
          className="min-h-[44px]"
          data-testid="fallback-manual-button"
        >
          <Keyboard className="w-4 h-4" /> Type details
        </Button>
      </div>
    </div>
  );
}
