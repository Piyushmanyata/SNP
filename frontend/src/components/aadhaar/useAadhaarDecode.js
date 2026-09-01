import { useState, useRef, useEffect, useCallback } from "react";
import api, { formatApiError } from "../../lib/api";
import * as grab from "./liveScan/grabFrame";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";

export function useAadhaarDecode({ onScanned, onFailure } = {}) {
  const [payload, setPayload] = useState("");
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const decode = useCallback(
    async (text) => {
      if (!text) return null;
      if (mountedRef.current) {
        setPayload(text);
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
            if ((data.outcome === "garbage" || data.outcome === "not-aadhaar") && onFailure) {
              onFailure(data.outcome);
            }
          }
        }
        return data;
      } catch (err) {
        if (mountedRef.current) {
          setError(formatApiError(err));
        }
        return null;
      } finally {
        if (mountedRef.current) {
          setBusy(false);
        }
      }
    },
    [onScanned, onFailure]
  );

  const scanFile = useCallback(
    async (file) => {
      if (!file) return;
      if (mountedRef.current) {
        setError("");
        setOutcome("");
        setBusy(true);
      }
      try {
        const bitmap = await createImageBitmap(file);
        const imageData = grab.bitmapToImageData(bitmap);
        if (bitmap.close) bitmap.close();
        let text = null;
        if (nativeDetector.hasNativeBarcodeDetector()) {
          text = await nativeDetector.detectNativeImageData(imageData);
        }
        if (!text) {
          await wasmDetector.loadZxingWorker();
          text = await wasmDetector.detectWasmImageData(imageData);
        }
        if (!text) {
          if (mountedRef.current) {
            setError("No Aadhaar QR found in the image. Try a clearer photo.");
          }
          return;
        }
        await decode(text);
      } catch (e) {
        console.warn("QR code scanning from file failed:", e);
        if (mountedRef.current) {
          setError("No Aadhaar QR found in the image. Try a clearer photo.");
        }
      } finally {
        if (mountedRef.current) {
          setBusy(false);
        }
      }
    },
    [decode]
  );

  return {
    payload,
    setPayload,
    error,
    setError,
    outcome,
    setOutcome,
    source,
    setSource,
    busy,
    setBusy,
    decode,
    scanFile,
  };
}
