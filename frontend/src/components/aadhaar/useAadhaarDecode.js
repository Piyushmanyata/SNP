import { useState, useRef, useEffect, useCallback } from "react";
import api, { formatApiError } from "../../lib/api";
import * as grab from "./liveScan/grabFrame";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";

async function loadBitmap(file) {
  if (typeof createImageBitmap === "function") {
    try {
      return await createImageBitmap(file);
    } catch {
      return loadImage(file);
    }
  }
  return loadImage(file);
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    const finish = (error) => {
      clearTimeout(timer);
      image.onload = null;
      image.onerror = null;
      URL.revokeObjectURL(url);
      if (error) {
        image.src = "";
        reject(new Error("Image could not be loaded"));
      } else {
        resolve(image);
      }
    };
    const timer = setTimeout(() => finish(true), 8000);
    image.onload = () => finish(false);
    image.onerror = () => finish(true);
    image.src = url;
  });
}

export function useAadhaarDecode({ onScanned, onFailure } = {}) {
  const [payload, setPayload] = useState("");
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewData, setReviewData] = useState(null);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const mountedRef = useRef(true);
  const requestRef = useRef(0);
  const uploadRef = useRef(null);

  const cancelDecode = useCallback(() => {
    requestRef.current += 1;
    uploadRef.current?.abort();
    uploadRef.current = null;
    setBusy(false);
    setReviewData(null);
    setPasswordRequired(false);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestRef.current += 1;
      uploadRef.current?.abort();
    };
  }, []);

  const begin = useCallback(() => {
    uploadRef.current?.abort();
    uploadRef.current = null;
    const request = ++requestRef.current;
    setError("");
    setOutcome("");
    setSource("");
    setReviewData(null);
    setPasswordRequired(false);
    setBusy(true);
    return request;
  }, []);

  const current = useCallback((request) => mountedRef.current && request === requestRef.current, []);

  const accept = useCallback((data, text = "") => {
    setOutcome(data.outcome);
    setSource(data.source || "");
    if (data.outcome === "card") {
      setPayload(text);
      onScanned?.(data.data, text);
    } else if (data.outcome === "review") {
      setPayload("");
      setReviewData(data.data);
    } else {
      setError(data.message || "Unable to read Aadhaar details. Try another photo or enter details manually.");
      if (data.outcome === "garbage" || data.outcome === "not-aadhaar") onFailure?.(data.outcome);
    }
  }, [onScanned, onFailure]);

  const decode = useCallback(async (text) => {
    if (!text || !mountedRef.current) return null;
    const request = begin();
    setPayload(text);
    try {
      const { data } = await api.post("/aadhaar/decode", { payload: text });
      if (!current(request)) return null;
      accept(data, text);
      return data;
    } catch (err) {
      if (current(request)) setError(formatApiError(err));
      return null;
    } finally {
      if (current(request)) setBusy(false);
    }
  }, [accept, begin, current]);

  const scanFile = useCallback(async (file, password = "") => {
    if (!file || !mountedRef.current) return;
    const request = begin();
    setPayload("");
    try {
      let text = null;
      if (file.size > 12 * 1024 * 1024) {
        setError("Choose an Aadhaar photo or PDF smaller than 12 MB, or enter details manually.");
        return;
      }
      try {
        const serverFile = file.size > 4 * 1024 * 1024 || /^(application\/pdf|image\/hei[cf])/i.test(file.type) || /\.(pdf|heic|heif)$/i.test(file.name);
        const localPhoto = !serverFile && await grab.canDecodePhoto(file);
        if (!current(request)) return;
        const bitmap = localPhoto ? await loadBitmap(file) : null;
        try {
          if (!current(request)) return;
          const sizes = !bitmap ? [] : Math.max(bitmap.width, bitmap.height) > 1600 ? [1600, 2560] : [1600];
          for (const size of sizes) {
            const imageData = grab.bitmapToImageData(bitmap, size);
            if (nativeDetector.hasNativeBarcodeDetector()) {
              try {
                text = await nativeDetector.detectNativeImageData(imageData);
              } catch {
                text = null;
              }
            }
            if (!current(request)) return;
            if (!text) {
              await wasmDetector.loadZxingWorker();
              if (!current(request)) return;
              text = await wasmDetector.detectWasmImageData(imageData);
            }
            if (!current(request)) return;
            if (text) break;
          }
        } finally {
          bitmap?.close?.();
          if (bitmap?.src) bitmap.src = "";
        }
      } catch {
        text = null;
      }
      if (!current(request)) return;
      if (text) {
        const { data } = await api.post("/aadhaar/decode", { payload: text });
        if (!current(request)) return;
        if (data.outcome === "card") {
          accept(data, text);
          return;
        }
      }
      const controller = new AbortController();
      uploadRef.current = controller;
      const headers = { "Content-Type": file.type || "application/octet-stream" };
      if (password) headers["X-PDF-Password"] = encodeURIComponent(password);
      const { data } = await api.post("/aadhaar/extract", file, {
        headers,
        signal: controller.signal,
        timeout: 35000,
      });
      if (current(request)) accept(data, data.payload || "");
    } catch (err) {
      if (!current(request)) return;
      const detail = err.response?.data?.detail;
      if (detail?.code === "PDF_PASSWORD_REQUIRED") {
        setPasswordRequired(true);
        setError("Enter the e-Aadhaar PDF password and try again.");
      } else {
        setError(detail?.message || "Could not read this Aadhaar file. Check your connection, try another photo, or enter details manually.");
      }
    } finally {
      if (current(request)) {
        uploadRef.current = null;
        setBusy(false);
      }
    }
  }, [accept, begin, current]);

  return {
    payload,
    setPayload,
    error,
    setError,
    outcome,
    setOutcome,
    source,
    busy,
    reviewData,
    passwordRequired,
    decode,
    cancelDecode,
    scanFile,
  };
}
