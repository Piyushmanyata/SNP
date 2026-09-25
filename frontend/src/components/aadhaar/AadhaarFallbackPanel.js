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
  forPatient = false,
}) {
  if (!revealed) return null;
  return (
    <div
      className="rounded-xl border border-amber-300 bg-amber-50 p-3 mb-3"
      data-testid="aadhaar-fallback-panel"
    >
      <p className="text-sm font-semibold text-amber-900">
        The camera is not reading this card.{forPatient && " / कैमरा यह कार्ड नहीं पढ़ पा रहा है।"}
      </p>
      <p className="text-xs text-amber-800 mt-1 mb-3">
        Hold the card a little farther away, tap the picture to focus, turn on the torch, or upload a photo of the QR instead.
        {forPatient && " / कार्ड थोड़ा दूर रखें, फोकस के लिए तस्वीर पर टैप करें, टॉर्च चालू करें, या QR की फोटो अपलोड करें।"}
      </p>
      <div className="flex flex-wrap gap-2">
        {torchAvailable && (
          <Button
            variant="outline"
            size="md"
            type="button"
            onClick={toggleTorch}
            data-testid="fallback-torch-button"
          >
            <Flashlight className="w-4 h-4" /> {torchOn ? "Torch off" : "Torch on"}
            {forPatient && (torchOn ? " / टॉर्च बंद" : " / टॉर्च चालू")}
          </Button>
        )}
        <Button
          variant="outline"
          size="md"
          type="button"
          onClick={onUpload}
          data-testid="fallback-upload-button"
        >
          <Upload className="w-4 h-4" /> Upload photo{forPatient && " / फोटो अपलोड करें"}
        </Button>
        {!forPatient && (
          <Button
            variant="outline"
            size="md"
            type="button"
            onClick={onManual}
            data-testid="fallback-manual-button"
          >
            <Keyboard className="w-4 h-4" /> USB / paste
          </Button>
        )}
      </div>
    </div>
  );
}
