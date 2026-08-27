import React, { useState, useRef, useEffect, useCallback } from "react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import api, { formatApiError } from "../lib/api";
import { Button, Field, Alert, Badge, Spinner } from "./ui";
import {
  ScanLine,
  Sparkles,
  Lock,
  Camera,
  Upload,
  X,
  Keyboard,
  RefreshCw,
  SwitchCamera,
  Zap,
  ZapOff,
} from "lucide-react";

const NAMES = [
  "Ramesh Kumar",
  "Sita Devi",
  "Abdul Rahman",
  "Priya Sharma",
  "Gopal Das",
  "Fatima Bibi",
  "Arjun Reddy",
  "Lakshmi Nair",
];
const ADDRS = [
  "12 MG Road, Kolkata",
  "Village Rampur, Dist. Nadia",
  "45 Station Rd, Howrah",
  "Ward 7, Barasat",
];

function randDemo() {
  const name = NAMES[Math.floor(Math.random() * NAMES.length)];
  const gender = Math.random() > 0.5 ? "M" : "F";
  const year = 1955 + Math.floor(Math.random() * 55);
  const month = String(1 + Math.floor(Math.random() * 12)).padStart(2, "0");
  const day = String(1 + Math.floor(Math.random() * 28)).padStart(2, "0");
  const last4 = String(1000 + Math.floor(Math.random() * 8999));
  const addr = ADDRS[Math.floor(Math.random() * ADDRS.length)];
  return `AADHAAR|${name}|${gender}|${year}-${month}-${day}|${last4}|${addr}`;
}

export default function AadhaarScanner({ onScanned, disabled }) {
  const [payload, setPayload] = useState("");
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("idle"); // idle | camera | manual
  const [source, setSource] = useState("");
  const [cameraState, setCameraState] = useState("idle"); // idle | starting | scanning | error
  const [cameras, setCameras] = useState([]);
  const [currentCameraIndex, setCurrentCameraIndex] = useState(0);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  const scannerRef = useRef(null);
  const fileRef = useRef(null);
  const mountedRef = useRef(true);
  const isStartingRef = useRef(false);
  const readerId = "aadhaar-reader-region";

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (scannerRef.current) {
        try {
          if (scannerRef.current.isScanning) {
            scannerRef.current.stop().catch(() => {});
          }
          scannerRef.current.clear().catch(() => {});
        } catch (e) {}
        scannerRef.current = null;
      }
    };
  }, []);

  const stopCamera = useCallback(async () => {
    if (scannerRef.current) {
      const scanner = scannerRef.current;
      try {
        if (scanner.isScanning) {
          await scanner.stop();
        }
      } catch (e) {}
      try {
        await scanner.clear();
      } catch (e) {}
      scannerRef.current = null;
    }
    if (mountedRef.current) {
      setCameraState("idle");
      setTorchAvailable(false);
      setTorchOn(false);
    }
  }, []);

  const decode = useCallback(
    async (text) => {
      if (!text) return;
      if (mountedRef.current) {
        setBusy(true);
        setError("");
        setOutcome("");
      }
      try {
        const { data } = await api.post("/aadhaar/decode", { payload: text });
        if (mountedRef.current) {
          setOutcome(data.outcome);
          setSource(data.source || "");
          if (data.outcome === "card") {
            if (onScanned) onScanned(data.data);
          } else {
            setError(data.message || "Unable to read Aadhaar QR data.");
          }
        }
      } catch (err) {
        if (mountedRef.current) {
          setError(formatApiError(err));
        }
      } finally {
        if (mountedRef.current) {
          setBusy(false);
        }
      }
    },
    [onScanned]
  );

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      if (isStartingRef.current) return;
      isStartingRef.current = true;
      setError("");
      setOutcome("");
      setMode("camera");
      setCameraState("starting");

      await stopCamera();

      try {
        // Enumerate devices if not already done
        let availableCameras = cameras;
        if (!availableCameras || availableCameras.length === 0) {
          try {
            availableCameras = (await Html5Qrcode.getCameras()) || [];
            if (mountedRef.current) {
              setCameras(availableCameras);
            }
          } catch (e) {
            availableCameras = [];
          }
        }

        const idx =
          typeof cameraIndexToUse === "number"
            ? cameraIndexToUse
            : currentCameraIndex;

        const scanner = new Html5Qrcode(readerId, {
          formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
          verbose: false,
          experimentalFeatures: {
            useBarCodeDetectorIfSupported: true,
          },
        });
        scannerRef.current = scanner;

        const scanConfig = {
          fps: 15,
          qrbox: (viewfinderWidth, viewfinderHeight) => {
            const minDim = Math.min(viewfinderWidth, viewfinderHeight);
            const size = Math.floor(minDim * 0.85);
            return {
              width: Math.max(200, Math.min(size, 340)),
              height: Math.max(200, Math.min(size, 340)),
            };
          },
          aspectRatio: 1.0,
          disableFlip: false,
        };

        const onScanSuccess = async (decodedText) => {
          await stopCamera();
          if (mountedRef.current) {
            setMode("idle");
            setPayload(decodedText);
            decode(decodedText);
          }
        };

        let started = false;

        // Strategy 1: specific camera ID if camera selected from list
        if (availableCameras.length > 0 && availableCameras[idx]?.id) {
          try {
            await scanner.start(
              availableCameras[idx].id,
              scanConfig,
              onScanSuccess,
              () => {}
            );
            started = true;
          } catch (e) {
            // fallback to facingMode if deviceId start failed
          }
        }

        // Strategy 2: facingMode environment (back camera)
        if (!started) {
          try {
            await scanner.start(
              { facingMode: "environment" },
              scanConfig,
              onScanSuccess,
              () => {}
            );
            started = true;
          } catch (e) {
            // fallback to facingMode user (front camera) or generic
          }
        }

        // Strategy 3: facingMode user or first camera
        if (!started) {
          try {
            await scanner.start(
              { facingMode: "user" },
              scanConfig,
              onScanSuccess,
              () => {}
            );
            started = true;
          } catch (e) {
            // Strategy 4: default camera without constraints
            if (availableCameras.length > 0) {
              await scanner.start(
                availableCameras[0].id,
                scanConfig,
                onScanSuccess,
                () => {}
              );
              started = true;
            } else {
              throw e;
            }
          }
        }

        if (!mountedRef.current) {
          try {
            if (scanner.isScanning) await scanner.stop();
          } catch (e) {}
          try {
            await scanner.clear();
          } catch (e) {}
          return;
        }

        setCameraState("scanning");
        // Re-enumerate cameras if labels or extra devices became available after permission grant
        if (availableCameras.length <= 1) {
          try {
            const updatedCameras = (await Html5Qrcode.getCameras()) || [];
            if (mountedRef.current && updatedCameras.length > 0) {
              setCameras(updatedCameras);
            }
          } catch (e) {}
        }
        // Check torch capability
        try {
          const capabilities = scanner.getRunningTrackCapabilities?.();
          if (capabilities && capabilities.torch) {
            setTorchAvailable(true);
          }
        } catch (e) {}
      } catch (err) {
        await stopCamera();
        if (mountedRef.current) {
          setCameraState("error");
          setMode("idle");
          const msg = String(err?.message || err || "");
          const name = String(err?.name || "");
          if (
            typeof window !== "undefined" &&
            window.isSecureContext === false
          ) {
            setError(
              "Camera access requires HTTPS or localhost. Please use a secure connection, photo upload, or USB scanner."
            );
          } else if (
            name === "NotAllowedError" ||
            name === "PermissionDeniedError" ||
            /permission|denied|allowed/i.test(msg)
          ) {
            setError(
              "Camera permission denied. Please allow camera access in your browser or use photo upload / USB scanner."
            );
          } else if (
            name === "NotFoundError" ||
            name === "DevicesNotFoundError" ||
            /not found|no camera/i.test(msg)
          ) {
            setError(
              "No camera found on this device. Use photo upload or USB scanner instead."
            );
          } else if (
            name === "NotReadableError" ||
            name === "TrackStartError" ||
            /in use|busy|started/i.test(msg)
          ) {
            setError(
              "Camera is currently busy or in use by another app. Close other apps and retry."
            );
          } else {
            setError(
              "Unable to start camera. Use photo upload or USB scanner instead."
            );
          }
        }
      } finally {
        isStartingRef.current = false;
      }
    },
    [cameras, currentCameraIndex, decode, stopCamera]
  );

  const switchCamera = async () => {
    if (cameras.length <= 1) return;
    const nextIndex = (currentCameraIndex + 1) % cameras.length;
    setCurrentCameraIndex(nextIndex);
    await startCamera(nextIndex);
  };

  const toggleTorch = async () => {
    if (!scannerRef.current || !torchAvailable) return;
    try {
      const nextTorch = !torchOn;
      await scannerRef.current.applyVideoConstraints({
        advanced: [{ torch: nextTorch }],
      });
      setTorchOn(nextTorch);
    } catch (e) {}
  };

  const scanFile = async (file) => {
    if (!file) return;
    setError("");
    setOutcome("");
    setBusy(true);
    const tempReaderId = `${readerId}-file`;
    const scanner = new Html5Qrcode(tempReaderId, {
      formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
      verbose: false,
      experimentalFeatures: { useBarCodeDetectorIfSupported: true },
    });
    try {
      const text = await scanner.scanFile(file, false);
      setPayload(text);
      await decode(text);
    } catch (e) {
      setError("No Aadhaar QR found in the image. Try a clearer photo.");
    } finally {
      try {
        await scanner.clear();
      } catch (er) {}
      if (mountedRef.current) {
        setBusy(false);
      }
    }
  };

  return (
    <div className="rounded-2xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3">
        <ScanLine className="w-5 h-5 text-emerald-600" />
        <p className="font-display font-bold text-slate-900">Aadhaar Secure QR scan</p>
        <Badge tone="emerald" className="ml-auto">
          Offline decode
        </Badge>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Scan the QR on the Aadhaar card / e-Aadhaar. Camera, USB scanner, or photo upload — decoded on-device, no UIDAI call, only last-4 stored.
      </p>

      {/* Capture modes */}
      <div className="flex flex-wrap gap-2 mb-3">
        {mode !== "camera" ? (
          <Button
            variant="secondary"
            size="sm"
            type="button"
            onClick={() => startCamera()}
            disabled={disabled || busy || cameraState === "starting"}
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
            size="sm"
            type="button"
            onClick={async () => {
              await stopCamera();
              setMode("idle");
            }}
            data-testid="aadhaar-camera-stop"
          >
            <X className="w-4 h-4" /> Stop camera
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={disabled || busy || mode === "camera"}
          data-testid="aadhaar-upload-button"
        >
          <Upload className="w-4 h-4" /> Upload photo
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
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
          size="sm"
          type="button"
          onClick={async () => {
            if (mode === "camera") await stopCamera();
            setMode(mode === "manual" ? "idle" : "manual");
          }}
          disabled={disabled || busy}
          data-testid="aadhaar-manual-toggle"
        >
          <Keyboard className="w-4 h-4" /> USB / paste
        </Button>
      </div>

      <div
        className={
          mode === "camera"
            ? "relative mb-3 rounded-xl overflow-hidden border-2 border-emerald-500 bg-black shadow-lg"
            : "hidden"
        }
      >
        <div
          id={readerId}
          className="w-full min-h-[260px] sm:min-h-[320px]"
          data-testid="aadhaar-camera-region"
        />

        {/* Camera controls toolbar overlay */}
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
              data-testid="aadhaar-switch-camera"
            >
              <SwitchCamera className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Viewfinder guide frame overlay */}
        {cameraState === "scanning" && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center p-6">
            <div className="relative w-56 h-56 sm:w-64 sm:h-64 border-2 border-dashed border-emerald-400/80 rounded-2xl flex items-center justify-center">
              <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-emerald-400 rounded-tl-lg" />
              <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-emerald-400 rounded-tr-lg" />
              <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-emerald-400 rounded-bl-lg" />
              <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-emerald-400 rounded-br-lg" />
              <p className="text-[11px] font-medium text-emerald-200 bg-slate-950/70 px-2 py-0.5 rounded-full shadow">
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
      <div id={`${readerId}-file`} className="hidden" />

      {mode === "manual" && (
        <Field label="Scanned QR payload (USB wedge / paste)">
          <textarea
            className="w-full min-h-[70px] px-3.5 py-2.5 rounded-xl border border-slate-300 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            placeholder="Paste the big-number Secure QR, or a demo AADHAAR|... string"
            disabled={disabled || busy}
            data-testid="aadhaar-qr-input"
          />
          <div className="flex flex-wrap gap-2 mt-2">
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => setPayload(randDemo())}
              disabled={disabled || busy}
              data-testid="generate-demo-aadhaar-button"
            >
              <Sparkles className="w-4 h-4" /> Demo card
            </Button>
            <Button
              size="sm"
              type="button"
              onClick={() => decode(payload)}
              disabled={disabled || busy || !payload}
              data-testid="aadhaar-scan-button"
            >
              {busy ? "Decoding…" : "Decode"}
            </Button>
          </div>
        </Field>
      )}

      {busy && mode !== "manual" && (
        <div className="flex items-center gap-2 text-xs text-slate-600 mt-2">
          <Spinner className="w-3.5 h-3.5 text-emerald-600" />
          <span>Decoding Aadhaar QR payload…</span>
        </div>
      )}

      {outcome && outcome !== "card" && (
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
    </div>
  );
}
