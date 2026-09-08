import { useEffect, useRef, useState } from "react";

export function scrubActiveInput(text) {
  const el = document.activeElement;
  if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA")) return;
  if (typeof el.value !== "string" || !el.value.endsWith(text)) return;
  const proto = el.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(el, el.value.slice(0, -text.length));
  el.dispatchEvent(new Event("input", { bubbles: true }));
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
    let firstAt = 0;
    let lastAt = 0;
    let idleTimer;
    const isBurst = () => buf.length >= minLength && buf.length > 1
      && (lastAt - firstAt) / (buf.length - 1) <= 50;
    const reset = (interrupted = false) => {
      clearTimeout(idleTimer);
      const notify = interrupted && isBurst();
      buf = "";
      setReceiving(false);
      if (notify) onInterruptedRef.current?.();
    };
    const onKeyDown = (event) => {
      const now = performance.now();
      if (now - lastAt >= 500) reset(true);
      if (event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.isComposing) {
        reset(true);
        return;
      }
      if (event.key.length === 1) {
        if (!buf.length) firstAt = now;
        buf += event.key;
        lastAt = now;
        setReceiving(isBurst());
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => reset(true), 500);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        const candidate = buf;
        const accepted = isBurst();
        reset();
        if (!accepted) return;
        event.preventDefault();
        event.stopPropagation();
        scrubActiveInput(candidate);
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
