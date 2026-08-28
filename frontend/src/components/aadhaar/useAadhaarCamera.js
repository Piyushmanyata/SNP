import { useState, useRef, useEffect, useCallback } from "react";
import { createLiveScanEngine, MAX_DETECT_INTERVAL_MS } from "./liveScan/liveScanEngine";
import * as grab from "./liveScan/grabFrame";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";

function cameraErrorMessage(err) {
  const msg = String(err?.message || err || "");
  const name = String(err?.name || "");
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    return "Camera access requires HTTPS or localhost. Please use a secure connection, photo upload, or USB scanner.";
  }
  if (name === "NotAllowedError" || name === "PermissionDeniedError" || /permission|denied|allowed/i.test(msg)) {
    return "Camera permission denied. Please allow camera access in your browser or use photo upload / USB scanner.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || /not found|no camera/i.test(msg)) {
    return "No camera found on this device. Use photo upload or USB scanner instead.";
  }
  if (name === "NotReadableError" || name === "TrackStartError" || /in use|busy|started/i.test(msg)) {
    return "Camera is currently busy or in use by another app. Close other apps and retry.";
  }
  return "Unable to start camera. Use photo upload or USB scanner instead.";
}

async function listVideoInputs() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "videoinput");
}

export function useAadhaarCamera({
  decode,
  onLock,
  onError,
  onHintFallbacks,
} = {}) {
  const [cameraState, setCameraState] = useState("idle");
  const [cameras, setCameras] = useState([]);
  const [currentCameraIndex, setCurrentCameraIndex] = useState(0);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const engineRef = useRef(null);
  const loopRef = useRef(null);
  const mountedRef = useRef(true);
  const isStartingRef = useRef(false);

  const stopLoop = useCallback(() => {
    if (loopRef.current) {
      clearInterval(loopRef.current);
      loopRef.current = null;
    }
    if (engineRef.current) {
      engineRef.current.stop();
    }
  }, []);

  const stopCamera = useCallback(async () => {
    stopLoop();
    const stream = streamRef.current;
    streamRef.current = null;
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    const video = videoRef.current;
    if (video) {
      try {
        video.pause();
      } catch (e) {
        console.warn("Error pausing camera:", e);
      }
      video.srcObject = null;
    }
    if (mountedRef.current) {
      setCameraState("idle");
      setTorchAvailable(false);
      setTorchOn(false);
    }
  }, [stopLoop]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopLoop();
      const stream = streamRef.current;
      streamRef.current = null;
      if (stream) stream.getTracks().forEach((t) => t.stop());
    };
  }, [stopLoop]);

  const startLoop = useCallback(() => {
    const video = videoRef.current;
    const engine = createLiveScanEngine({
      hasNativeDetector: nativeDetector.hasNativeBarcodeDetector(),
      decode,
      loadWasm: wasmDetector.loadZxingWorker,
      detectNative: async (_frame, region) => {
        const imageData = grab.grabFrame(video, region);
        return nativeDetector.detectNativeImageData(imageData);
      },
      detectWasm: async (_frame, region) => {
        const imageData = grab.grabFrame(video, region);
        return wasmDetector.detectWasmImageData(imageData);
      },
      onLock: (result) => {
        stopCamera();
        if (onLock) onLock(result);
      },
      onHintFallbacks: () => {
        if (onHintFallbacks) onHintFallbacks();
      },
    });
    engineRef.current = engine;
    engine.start();
    engine.tick(video);
    loopRef.current = setInterval(() => {
      engine.tick(video);
    }, MAX_DETECT_INTERVAL_MS);
  }, [decode, onHintFallbacks, onLock, stopCamera]);

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      if (isStartingRef.current) return;
      isStartingRef.current = true;
      setCameraState("starting");
      await stopCamera();

      try {
        let available = cameras;
        if (!available || available.length === 0) {
          try {
            available = await listVideoInputs();
            if (mountedRef.current) setCameras(available);
          } catch (e) {
            console.warn("Failed to enumerate cameras:", e);
            available = [];
          }
        }

        const idx = typeof cameraIndexToUse === "number" ? cameraIndexToUse : currentCameraIndex;
        const deviceId = available[idx]?.deviceId;

        const attempts = [];
        if (deviceId) {
          attempts.push({
            video: {
              deviceId: { exact: deviceId },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
          });
        }
        attempts.push({
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        });
        attempts.push({ video: { facingMode: "environment" } });
        attempts.push({ video: { facingMode: "user" } });
        attempts.push({ video: true });

        let stream = null;
        let lastErr = null;
        for (const constraints of attempts) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: false, ...constraints });
            break;
          } catch (e) {
            lastErr = e;
          }
        }
        if (!stream) throw lastErr || new Error("Unable to start camera");

        if (!mountedRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        const video = videoRef.current;
        if (!video) throw new Error("Unable to start camera");
        video.srcObject = stream;
        try {
          await video.play();
        } catch (e) {
          console.warn("Error playing camera:", e);
        }
        if (!video.videoWidth) {
          await new Promise((resolve) => {
            const done = () => {
              video.removeEventListener("loadedmetadata", done);
              resolve();
            };
            video.addEventListener("loadedmetadata", done);
            setTimeout(done, 800);
          });
        }

        const track = stream.getVideoTracks()[0];
        try {
          const caps = track.getCapabilities?.() || {};
          if (caps.torch) setTorchAvailable(true);
        } catch (e) {
          console.warn("Failed to check track capabilities for torch:", e);
        }

        try {
          const refreshed = await listVideoInputs();
          if (mountedRef.current && refreshed.length) setCameras(refreshed);
        } catch (e) {
          console.warn("Failed to refresh camera list after start:", e);
        }

        setCameraState("scanning");
        startLoop();
      } catch (err) {
        await stopCamera();
        if (mountedRef.current) {
          setCameraState("error");
          if (onError) onError(cameraErrorMessage(err));
        }
      } finally {
        isStartingRef.current = false;
      }
    },
    [cameras, currentCameraIndex, onError, startLoop, stopCamera]
  );

  const switchCamera = useCallback(async () => {
    if (cameras.length <= 1) return;
    const nextIndex = (currentCameraIndex + 1) % cameras.length;
    setCurrentCameraIndex(nextIndex);
    await startCamera(nextIndex);
  }, [cameras, currentCameraIndex, startCamera]);

  const toggleTorch = useCallback(async () => {
    const track = streamRef.current?.getVideoTracks?.()[0];
    if (!track || !torchAvailable) return;
    try {
      const nextTorch = !torchOn;
      await track.applyConstraints({ advanced: [{ torch: nextTorch }] });
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
    videoRef,
  };
}
