import { useState, useRef, useEffect, useCallback } from "react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import api, { formatApiError } from "../../lib/api";

export function useAadhaarDecode({ onScanned } = {}) {
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

  const scanFile = useCallback(
    async (file, tempReaderId = "aadhaar-reader-region-file") => {
      if (!file) return;
      if (mountedRef.current) {
        setError("");
        setOutcome("");
        setBusy(true);
      }

      const scanner = new Html5Qrcode(tempReaderId, {
        formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
        verbose: false,
        experimentalFeatures: { useBarCodeDetectorIfSupported: true },
      });

      try {
        const text = await scanner.scanFile(file, false);
        if (mountedRef.current) {
          setPayload(text);
        }
        await decode(text);
      } catch (e) {
        console.warn("QR code scanning from file failed:", e);
        if (mountedRef.current) {
          setError("No Aadhaar QR found in the image. Try a clearer photo.");
        }
      } finally {
        try {
          await scanner.clear();
        } catch (er) {
          console.warn("Failed to clear file scanner element:", er);
        }
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
