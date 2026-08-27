import { useState, useRef, useEffect, useCallback } from "react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";

export function useAadhaarCamera({ readerId = "aadhaar-reader-region", onScanSuccess, onError } = {}) {
  const [cameraState, setCameraState] = useState("idle"); // idle | starting | scanning | error
  const [cameras, setCameras] = useState([]);
  const [currentCameraIndex, setCurrentCameraIndex] = useState(0);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  const scannerRef = useRef(null);
  const mountedRef = useRef(true);
  const isStartingRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (scannerRef.current) {
        try {
          if (scannerRef.current.isScanning) {
            scannerRef.current.stop().catch((e) => {
              console.warn("Error stopping scanner during unmount:", e);
            });
          }
          scannerRef.current.clear().catch((e) => {
            console.warn("Error clearing scanner during unmount:", e);
          });
        } catch (e) {
          console.warn("Error during scanner unmount cleanup:", e);
        }
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
      } catch (e) {
        console.warn("Error stopping camera:", e);
      }
      try {
        await scanner.clear();
      } catch (e) {
        console.warn("Error clearing camera element:", e);
      }
      scannerRef.current = null;
    }
    if (mountedRef.current) {
      setCameraState("idle");
      setTorchAvailable(false);
      setTorchOn(false);
    }
  }, []);

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      if (isStartingRef.current) return;
      isStartingRef.current = true;
      setCameraState("starting");

      await stopCamera();

      try {
        let availableCameras = cameras;
        if (!availableCameras || availableCameras.length === 0) {
          try {
            availableCameras = (await Html5Qrcode.getCameras()) || [];
            if (mountedRef.current) {
              setCameras(availableCameras);
            }
          } catch (e) {
            console.warn("Failed to enumerate cameras:", e);
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
            const minDim = Math.min(viewfinderWidth || 250, viewfinderHeight || 250);
            const size = Math.max(50, Math.floor(minDim * 0.85));
            return {
              width: Math.min(viewfinderWidth || size, size),
              height: Math.min(viewfinderHeight || size, size),
            };
          },
          aspectRatio: 1.0,
          disableFlip: false,
        };

        const handleSuccess = async (decodedText) => {
          await stopCamera();
          if (onScanSuccess) {
            onScanSuccess(decodedText);
          }
        };

        let started = false;

        // Strategy 1: specific camera ID if camera selected from list
        if (availableCameras.length > 0 && availableCameras[idx]?.id) {
          try {
            await scanner.start(
              availableCameras[idx].id,
              scanConfig,
              handleSuccess,
              () => {}
            );
            started = true;
          } catch (e) {
            console.warn("Camera start with device ID failed, trying environment facingMode:", e);
          }
        }

        // Strategy 2: facingMode environment (back camera)
        if (!started) {
          try {
            await scanner.start(
              { facingMode: "environment" },
              scanConfig,
              handleSuccess,
              () => {}
            );
            started = true;
          } catch (e) {
            console.warn("Camera start with environment facingMode failed, trying user facingMode:", e);
          }
        }

        // Strategy 3: facingMode user or first camera
        if (!started) {
          try {
            await scanner.start(
              { facingMode: "user" },
              scanConfig,
              handleSuccess,
              () => {}
            );
            started = true;
          } catch (e) {
            console.warn("Camera start with user facingMode failed, trying fallback camera ID:", e);
            if (availableCameras.length > 0) {
              await scanner.start(
                availableCameras[0].id,
                scanConfig,
                handleSuccess,
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
          } catch (e) {
            console.warn("Error stopping unmounted camera:", e);
          }
          try {
            await scanner.clear();
          } catch (e) {
            console.warn("Error clearing unmounted camera:", e);
          }
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
          } catch (e) {
            console.warn("Failed to refresh camera list after start:", e);
          }
        }

        // Check torch capability
        try {
          const capabilities = scanner.getRunningTrackCapabilities?.();
          if (capabilities && capabilities.torch) {
            setTorchAvailable(true);
          }
        } catch (e) {
          console.warn("Failed to check track capabilities for torch:", e);
        }
      } catch (err) {
        await stopCamera();
        if (mountedRef.current) {
          setCameraState("error");
          const msg = String(err?.message || err || "");
          const name = String(err?.name || "");
          let errorMsg = "Unable to start camera. Use photo upload or USB scanner instead.";
          if (
            typeof window !== "undefined" &&
            window.isSecureContext === false
          ) {
            errorMsg = "Camera access requires HTTPS or localhost. Please use a secure connection, photo upload, or USB scanner.";
          } else if (
            name === "NotAllowedError" ||
            name === "PermissionDeniedError" ||
            /permission|denied|allowed/i.test(msg)
          ) {
            errorMsg = "Camera permission denied. Please allow camera access in your browser or use photo upload / USB scanner.";
          } else if (
            name === "NotFoundError" ||
            name === "DevicesNotFoundError" ||
            /not found|no camera/i.test(msg)
          ) {
            errorMsg = "No camera found on this device. Use photo upload or USB scanner instead.";
          } else if (
            name === "NotReadableError" ||
            name === "TrackStartError" ||
            /in use|busy|started/i.test(msg)
          ) {
            errorMsg = "Camera is currently busy or in use by another app. Close other apps and retry.";
          }
          if (onError) {
            onError(errorMsg);
          }
        }
      } finally {
        isStartingRef.current = false;
      }
    },
    [cameras, currentCameraIndex, onScanSuccess, onError, readerId, stopCamera]
  );

  const switchCamera = useCallback(async () => {
    if (cameras.length <= 1) return;
    const nextIndex = (currentCameraIndex + 1) % cameras.length;
    setCurrentCameraIndex(nextIndex);
    await startCamera(nextIndex);
  }, [cameras, currentCameraIndex, startCamera]);

  const toggleTorch = useCallback(async () => {
    if (!scannerRef.current || !torchAvailable) return;
    try {
      const nextTorch = !torchOn;
      await scannerRef.current.applyVideoConstraints({
        advanced: [{ torch: nextTorch }],
      });
      setTorchOn(nextTorch);
    } catch (e) {
      console.warn("Failed to toggle torch constraints:", e);
    }
  }, [torchAvailable, torchOn]);

  return {
    cameraState,
    setCameraState,
    cameras,
    currentCameraIndex,
    torchAvailable,
    torchOn,
    startCamera,
    stopCamera,
    switchCamera,
    toggleTorch,
    readerId,
    scannerRef,
  };
}
