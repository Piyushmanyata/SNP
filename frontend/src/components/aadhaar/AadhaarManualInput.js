import React, { useEffect, useRef, useState } from "react";
import { Button, Field } from "../ui";

export function AadhaarManualInput({ mode, disabled, busy, decode }) {
  const ref = useRef(null);
  const [filled, setFilled] = useState(false);
  const locked = disabled || busy;

  useEffect(() => {
    if (mode === "manual" && !locked) ref.current?.focus();
  }, [mode, locked]);

  if (mode !== "manual") return null;

  const submit = async () => {
    const text = ref.current?.value.trim();
    if (!text || locked) return;
    await decode(text);
    if (!ref.current) return;
    ref.current.value = "";
    setFilled(false);
  };

  return (
    <Field label="USB scanner or pasted QR text">
      <textarea
        ref={ref}
        className="w-full min-h-[70px] px-3.5 py-2.5 rounded-xl border-2 border-slate-400 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500 read-only:bg-slate-100"
        onInput={(e) => setFilled(Boolean(e.currentTarget.value.trim()))}
        onKeyDown={(e) => {
          if ((e.key === "Enter" && !e.shiftKey) || (e.key === "Tab" && e.currentTarget.value.trim())) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ready. Scan the QR with the USB scanner, or paste the QR text and press Enter."
        readOnly={locked}
        aria-busy={busy}
        spellCheck={false}
        data-usb-box=""
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        data-testid="aadhaar-qr-input"
      />
      <div className="flex flex-wrap gap-2 mt-2">
        <Button
          size="sm"
          type="button"
          onClick={submit}
          disabled={locked || !filled}
          data-testid="aadhaar-scan-button"
        >
          {busy ? "Decoding…" : "Decode"}
        </Button>
      </div>
    </Field>
  );
}
