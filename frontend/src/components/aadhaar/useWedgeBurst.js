import { useEffect, useRef } from "react";

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

export function useWedgeBurst({ enabled, minLength = 20, onBurst }) {
  const onBurstRef = useRef(onBurst);
  onBurstRef.current = onBurst;
  const state = useRef({ buf: "", lastAt: 0, gaps: [] });

  useEffect(() => {
    if (!enabled) return undefined;
    const onKeyDown = (event) => {
      const now = performance.now();
      const s = state.current;
      if (event.key.length === 1) {
        if (now - s.lastAt > 500) {
          s.buf = "";
          s.gaps = [];
        }
        if (s.buf.length > 0) s.gaps.push(now - s.lastAt);
        s.buf += event.key;
        s.lastAt = now;
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        const candidate = s.buf;
        const g = s.gaps;
        s.buf = "";
        s.gaps = [];
        const avg = g.length ? g.reduce((a, b) => a + b, 0) / g.length : Infinity;
        if (!(candidate.length >= minLength && g.length > 0 && avg <= 50)) return;
        event.preventDefault();
        event.stopPropagation();
        scrubActiveInput(candidate);
        onBurstRef.current?.(candidate);
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [enabled, minLength]);
}
