import { useState, useRef, useEffect, useCallback } from "react";
import { createLiveScanEngine, TICK_MS } from "./liveScan/liveScanEngine";
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
  zoomRange,
  applyZoom,
  focusAt,
} from "./cameraHelpers";

export function useAadhaarCamera({
  decode,
  onLock,
  onError,
  onHint,
  onScanStall,
} = {}) {
  const [cameraState, setCameraState] = useState("idle");
  const [cameras, setCameras] = useState([]);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [zoom, setZoom] = useState(null);

  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;
  const currentCameraIndexRef = useRef(0);
  const callbacks = useRef({ decode, onLock, onError, onHint, onScanStall });
  callbacks.current = { decode, onLock, onError, onHint, onScanStall };

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const engineRef = useRef(null);
  const loopRef = useRef(null);
  const mountedRef = useRef(true);
  const sessionRef = useRef(0);

  const stopLoop = useCallback(() => {
    if (loopRef.current) {
      clearInterval(loopRef.current);
      loopRef.current = null;
    }
    engineRef.current?.stop();
    engineRef.current = null;
  }, []);

  const stopCamera = useCallback(async () => {
    sessionRef.current += 1;
    stopLoop();
    const stream = streamRef.current;
    streamRef.current = null;
    stream?.getTracks().forEach((t) => t.stop());
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
      setZoom(null);
    }
  }, [stopLoop]);

  useEffect(() => {
    mountedRef.current = true;
    wasmDetector.loadZxingWorker().catch(() => {});
    return () => {
      mountedRef.current = false;
      stopLoop();
      const stream = streamRef.current;
      streamRef.current = null;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [stopLoop]);

  const startLoop = useCallback(() => {
    const lanes = [];
    if (nativeDetector.hasNativeBarcodeDetector()) {
      lanes.push({
        load: nativeDetector.loadNativeDetector,
        detect: () => nativeDetector.detectNative(videoRef.current),
      });
    }
    lanes.push({
      load: wasmDetector.loadZxingWorker,
      regions: ["roi", "roi", "full"],
      detect: (region) => wasmDetector.detectWasmImageData(grab.grabFrame(videoRef.current, region)),
    });
    const engine = createLiveScanEngine({
      lanes,
      decode: (payload) => callbacks.current.decode(payload),
      onLock: (result) => {
        stopCamera();
        callbacks.current.onLock?.(result);
      },
      onHint: () => callbacks.current.onHint?.(),
      onScanStall: () => callbacks.current.onScanStall?.(),
      onError: async (message) => {
        await stopCamera();
        if (!mountedRef.current) return;
        setCameraState("error");
        callbacks.current.onError?.(message);
      },
    });
    engineRef.current = engine;
    engine.start();
    engine.tick();
    loopRef.current = setInterval(() => engine.tick(), TICK_MS);
  }, [stopCamera]);

  const refreshCameras = useCallback(async (session, stream) => {
    try {
      const refreshed = await listVideoInputs();
      if (!mountedRef.current || session !== sessionRef.current || !refreshed.length) return;
      setCameras(refreshed);
      camerasRef.current = refreshed;
      const activeDevice = stream.getVideoTracks()[0]?.getSettings?.().deviceId;
      const activeIndex = refreshed.findIndex((camera) => camera.deviceId === activeDevice);
      if (activeIndex >= 0) currentCameraIndexRef.current = activeIndex;
    } catch (e) {
      logger.warn("Failed to refresh camera list after start:", e);
    }
  }, []);

  const startCamera = useCallback(
    async (cameraIndexToUse) => {
      wasmDetector.loadZxingWorker().catch(() => {});
      await stopCamera();
      const session = sessionRef.current;
      setCameraState("starting");

      try {
        const deviceId = typeof cameraIndexToUse === "number"
          ? camerasRef.current[cameraIndexToUse]?.deviceId
          : undefined;

        const stream = await acquireCameraStream(deviceId);
        if (!mountedRef.current || session !== sessionRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        await attachStreamToVideo(videoRef.current, stream);
        if (!mountedRef.current || session !== sessionRef.current) return;

        setTorchAvailable(checkTorchCapability(stream));
        const range = zoomRange(stream);
        if (range && range.near > range.min && await applyZoom(stream, range.near)) {
          if (session === sessionRef.current) setZoom({ ...range, value: range.near });
        } else if (range && session === sessionRef.current) {
          setZoom({ ...range, value: range.min });
        }
        if (!mountedRef.current || session !== sessionRef.current) return;

        setCameraState("scanning");
        startLoop();
        videoRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
        refreshCameras(session, stream);
      } catch (err) {
        if (!mountedRef.current || session !== sessionRef.current) return;
        await stopCamera();
        if (mountedRef.current) {
          setCameraState("error");
          callbacks.current.onError?.(cameraErrorMessage(err));
        }
      }
    },
    [refreshCameras, startLoop, stopCamera]
  );

  const switchCamera = useCallback(async () => {
    const available = camerasRef.current;
    if (available.length <= 1) return;
    const nextIndex = (currentCameraIndexRef.current + 1) % available.length;
    currentCameraIndexRef.current = nextIndex;
    await startCamera(nextIndex);
  }, [startCamera]);

  const toggleTorch = useCallback(async () => {
    if (!torchAvailable) return;
    const nextTorch = !torchOn;
    await applyTorch(streamRef.current, nextTorch);
    setTorchOn(nextTorch);
  }, [torchAvailable, torchOn]);

  const toggleZoom = useCallback(async () => {
    if (!zoom) return;
    const next = zoom.value > zoom.min ? zoom.min : zoom.near;
    if (await applyZoom(streamRef.current, next)) setZoom((current) => current && { ...current, value: next });
  }, [zoom]);

  const focus = useCallback((x, y) => {
    if (streamRef.current) focusAt(streamRef.current, x, y);
  }, []);

  return {
    cameraState,
    cameras,
    torchAvailable,
    torchOn,
    zoom,
    startCamera,
    stopCamera,
    switchCamera,
    toggleTorch,
    toggleZoom,
    focus,
    videoRef,
  };
}
