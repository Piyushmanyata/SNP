import { useState, useRef, useEffect, useCallback } from "react";
import api, { formatApiError } from "../../lib/api";
import * as nativeDetector from "./liveScan/nativeDetector";
import * as wasmDetector from "./liveScan/wasmDetector";

export const MAX_UPLOAD_BYTES = 12 * 1024 * 1024;
const SERVER_ONLY_TYPE = /^(application\/pdf|image\/hei[cf])/i;
const SERVER_ONLY_NAME = /\.(pdf|heic|heif)$/i;

async function photoDimensions(file) {
  const header = file.slice(0, 262144);
  const buffer = typeof header.arrayBuffer === "function"
    ? await header.arrayBuffer()
    : await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(header);
    });
  const view = new DataView(buffer);
  if (view.byteLength >= 24 && view.getUint32(0) === 0x89504e47 && view.getUint32(4) === 0x0d0a1a0a
    && view.getUint32(8) === 13 && view.getUint32(12) === 0x49484452) {
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null;
  let offset = 2;
  while (offset + 4 <= view.byteLength) {
    if (view.getUint8(offset++) !== 0xff) return null;
    while (offset < view.byteLength && view.getUint8(offset) === 0xff) offset++;
    if (offset + 3 > view.byteLength) return null;
    const marker = view.getUint8(offset++);
    const length = view.getUint16(offset);
    if (length < 2 || offset + length > view.byteLength) return null;
    if (marker === 0xc0 || marker === 0xc2) {
      if (length < 8) return null;
      return { width: view.getUint16(offset + 5), height: view.getUint16(offset + 3) };
    }
    if (!(marker >= 0xe0 && marker <= 0xef) && ![0xdb, 0xc4, 0xdd, 0xfe].includes(marker)) return null;
    offset += length;
  }
  return null;
}

export const MAX_LOCAL_PHOTO_PIXELS = 16 * 1024 * 1024;

async function readableLocally(file) {
  const size = await photoDimensions(file).catch(() => null);
  return Boolean(size && size.width > 0 && size.height > 0 && size.width * size.height <= MAX_LOCAL_PHOTO_PIXELS);
}

export async function decodePayload(text) {
  const { data } = await api.post("/aadhaar/decode", { payload: text });
  return data;
}

async function readPhotoQr(file, live) {
  if (nativeDetector.hasNativeBarcodeDetector() && typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file).catch(() => null);
    if (bitmap) {
      try {
        const text = await nativeDetector.detectNative(bitmap).catch(() => null);
        if (text) return text;
      } finally {
        bitmap.close?.();
      }
    }
  }
  if (!live()) return null;
  return wasmDetector.detectWasmPhoto(file);
}

export function useAadhaarDecode({ classify, onScanned, onFailure, canReview = true } = {}) {
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewData, setReviewData] = useState(null);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const mountedRef = useRef(true);
  const requestRef = useRef(0);
  const uploadRef = useRef(null);
  const classifyRef = useRef(classify);
  classifyRef.current = classify;

  const cancelDecode = useCallback(() => {
    requestRef.current += 1;
    uploadRef.current?.abort();
    uploadRef.current = null;
    setBusy(false);
    setError("");
    setOutcome("");
    setSource("");
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

  const resolve = useCallback((text) => (classifyRef.current || decodePayload)(text), []);

  const accept = useCallback((data, text = "") => {
    if (data.source === "patient_code") return;
    setOutcome(data.outcome);
    setSource(data.source || "");
    if (data.outcome === "card") {
      if (data.data) onScanned?.(data.data, text);
    } else if (data.outcome === "review" && canReview) {
      setReviewData(data.data);
    } else {
      setError(data.message || "Unable to read Aadhaar details. Try another photo or enter details manually.");
      onFailure?.(data.outcome);
    }
  }, [onScanned, onFailure, canReview]);

  const decode = useCallback(async (text) => {
    if (!text || !mountedRef.current) return null;
    const request = begin();
    try {
      const data = await resolve(text);
      if (!current(request)) return null;
      if (data) accept(data, text);
      return data;
    } catch (err) {
      if (current(request)) {
        setError(formatApiError(err));
        onFailure?.("error");
      }
      return null;
    } finally {
      if (current(request)) setBusy(false);
    }
  }, [accept, begin, current, onFailure, resolve]);

  const scanFile = useCallback(async (file, password = "") => {
    if (!file || !mountedRef.current) return;
    const request = begin();
    const live = () => current(request);
    try {
      if (file.size > MAX_UPLOAD_BYTES) {
        setError("Choose an Aadhaar photo or PDF smaller than 12 MB, or enter details manually.");
        onFailure?.("error");
        return;
      }
      const local = !SERVER_ONLY_TYPE.test(file.type) && !SERVER_ONLY_NAME.test(file.name || "") && await readableLocally(file);
      if (!live()) return;
      if (local) {
        const text = await readPhotoQr(file, live).catch(() => null);
        if (!live()) return;
        if (text) {
          const data = await resolve(text);
          if (!live()) return;
          if (data?.outcome === "card" || data?.source === "patient_code") {
            accept(data, text);
            return;
          }
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
      if (!live()) return;
      if (classifyRef.current && data.outcome === "card" && data.payload) {
        const resolved = await resolve(data.payload);
        if (live()) accept(resolved, data.payload);
        return;
      }
      accept(data, data.payload || "");
    } catch (err) {
      if (!live()) return;
      const detail = err.response?.data?.detail;
      if (detail?.code === "PDF_PASSWORD_REQUIRED") {
        setPasswordRequired(true);
        setError("Enter the e-Aadhaar PDF password and try again.");
      } else {
        setError(detail?.message || "Could not read this Aadhaar file. Check your connection, try another photo, or enter details manually.");
      }
      onFailure?.("error");
    } finally {
      if (live()) {
        uploadRef.current = null;
        setBusy(false);
      }
    }
  }, [accept, begin, current, onFailure, resolve]);

  return {
    error,
    setError,
    outcome,
    source,
    busy,
    reviewData,
    passwordRequired,
    decode,
    cancelDecode,
    scanFile,
  };
}
