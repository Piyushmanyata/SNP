import { useEffect, useRef, useState } from "react";

export const PATIENT_CODE_PAYLOAD_LENGTH = "SNP:".length + 8;

function restoreField(el, value) {
  if (!el || !el.isConnected || el.value === value) return;
  const proto = el.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function typingField() {
  const el = document.activeElement;
  return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA") ? el : null;
}

export function useWedgeBurst({ enabled, minLength = 20, onBurst, onInterrupted }) {
  const onBurstRef = useRef(onBurst);
  onBurstRef.current = onBurst;
  const onInterruptedRef = useRef(onInterrupted);
  onInterruptedRef.current = onInterrupted;
  const [receiving, setReceiving] = useState(false);

  useEffect(() => {
    if (!enabled) return undefined;
    let buf = "";
    let field = null;
    let before = "";
    let capturing = false;
    let firstAt = 0;
    let lastAt = 0;
    let idleTimer;
    const isBurst = () => buf.length >= minLength && buf.length > 1
      && (lastAt - firstAt) / (buf.length - 1) <= 50;
    const reset = (interrupted = false) => {
      clearTimeout(idleTimer);
      const notify = interrupted && isBurst();
      buf = "";
      field = null;
      capturing = false;
      setReceiving(false);
      if (notify) onInterruptedRef.current?.();
    };
    const onKeyDown = (event) => {
      if (!buf.length && event.target?.hasAttribute?.("data-usb-box")) return;
      const now = performance.now();
      if (now - lastAt >= 500) reset(true);
      if (event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.isComposing) {
        reset(true);
        return;
      }
      if (event.key.length === 1) {
        if (!buf.length) {
          firstAt = now;
          field = typingField();
          before = field ? field.value : "";
        }
        buf += event.key;
        lastAt = now;
        capturing = capturing || isBurst();
        if (capturing) event.preventDefault();
        setReceiving(capturing);
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => reset(true), 500);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        const candidate = buf;
        const target = field;
        const value = before;
        const accepted = isBurst();
        reset();
        if (!accepted) return;
        event.preventDefault();
        event.stopPropagation();
        restoreField(target, value);
        onBurstRef.current?.(candidate);
        return;
      }
      if (event.key !== "Shift") reset(true);
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      reset();
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [enabled, minLength]);
  return { receiving: Boolean(enabled && receiving) };
}
