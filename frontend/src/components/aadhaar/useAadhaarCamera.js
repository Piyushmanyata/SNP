import { useState, useRef, useEffect, useCallback } from "react";
import { createLiveScanEngine, MAX_DETECT_INTERVAL_MS } from "./liveScan/liveScanEngine";
import * as grab from "./liveScan/grabFrame";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";
import logger from "../../lib/logger";
import {
  cameraErrorMessage,
  listVideoInputs,
  acquireCameraStream,
  attachStreamToVideo,
  checkTorchCapability,
  applyTorch,
  createStillCapture,
} from "./cameraHelpers";

export function useAadhaarCamera({
  decode,
  onLock,
  onError,
  onHintFallbacks,
  onScanStall,
} = {}) {
  const [cameraState, setCameraState] = useState("idle");
  const [cameras, setCameras] = useState([]);
  const [currentCameraIndex, setCurrentCameraIndex] = useState(0);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;
  const currentCameraIndexRef = useRef(currentCameraIndex);
  currentCameraIndexRef.current = currentCameraIndex;

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const engineRef = useRef(null);
  const loopRef = useRef(null);
  const mountedRef = useRef(true);
  const isStartingRef = useRef(false);
  const stillCaptureRef = useRef(null);

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
    stillCaptureRef.current = null;
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
        logger.warn("Error pausing camera:", e);
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

  const frameFor = useCallback(async (region) => {
    const video = videoRef.current;
    if (region === "full" && stillCaptureRef.current) {
      try {
        const blob = await stillCaptureRef.current.takePhoto();
        const bitmap = await createImageBitmap(blob);
        const imageData = grab.bitmapToImageData(bitmap);
        if (bitmap.close) bitmap.close();
        if (imageData) return imageData;
      } catch (e) {
        logger.warn("Still capture failed, falling back to preview frame:", e);
        stillCaptureRef.current = null;
      }
    }
    return grab.grabFrame(video, region);
  }, []);

  const startLoop = useCallback(() => {
    const video = videoRef.current;
    const engine = createLiveScanEngine({
      hasNativeDetector: nativeDetector.hasNativeBarcodeDetector(),
      decode,
      loadWasm: wasmDetector.loadZxingWorker,
      detectNative: async (_frame, region) => {
        return nativeDetector.detectNativeImageData(await frameFor(region));
      },
      detectWasm: async (_frame, region) => {
        return wasmDetector.detectWasmImageData(await frameFor(region));
      },
      onLock: (result) => {
        stopCamera();
        if (onLock) onLock(result);
      },
      onHintFallbacks: () => {
        if (onHintFallbacks) onHintFallbacks();
      },
      onScanStall: () => {
        if (onScanStall) onScanStall();
      },
    });
    engineRef.current = engine;
    engine.start();
    engine.tick(video);
    loopRef.current = setInterval(() => {
      engine.tick(video);
    }, MAX_DETECT_INTERVAL_MS);
  }, [decode, frameFor, onHintFallbacks, onLock, onScanStall, stopCamera]);

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      if (isStartingRef.current) return;
      isStartingRef.current = true;
      setCameraState("starting");
      await stopCamera();

      try {
        let available = camerasRef.current;
        if (!available || available.length === 0) {
          try {
            available = await listVideoInputs();
            if (mountedRef.current) {
              setCameras(available);
              camerasRef.current = available;
            }
          } catch (e) {
            logger.warn("Failed to enumerate cameras:", e);
            available = [];
          }
        }

        const idx = typeof cameraIndexToUse === "number" ? cameraIndexToUse : currentCameraIndexRef.current;
        const deviceId = available[idx]?.deviceId;

        const stream = await acquireCameraStream(deviceId);
        if (!mountedRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        await attachStreamToVideo(videoRef.current, stream);

        stillCaptureRef.current = createStillCapture(stream);

        if (checkTorchCapability(stream)) {
          setTorchAvailable(true);
        }

        try {
          const refreshed = await listVideoInputs();
          if (mountedRef.current && refreshed.length) {
            setCameras(refreshed);
            camerasRef.current = refreshed;
          }
        } catch (e) {
          logger.warn("Failed to refresh camera list after start:", e);
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
    [onError, startLoop, stopCamera]
  );

  const switchCamera = useCallback(async () => {
    const available = camerasRef.current;
    if (available.length <= 1) return;
    const nextIndex = (currentCameraIndexRef.current + 1) % available.length;
    setCurrentCameraIndex(nextIndex);
    currentCameraIndexRef.current = nextIndex;
    await startCamera(nextIndex);
  }, [startCamera]);

  const toggleTorch = useCallback(async () => {
    if (!torchAvailable) return;
    const nextTorch = !torchOn;
    await applyTorch(streamRef.current, nextTorch);
    setTorchOn(nextTorch);
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


