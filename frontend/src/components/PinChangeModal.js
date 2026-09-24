import React, { useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { Alert, Button, Field, Input, Modal } from "./ui";
import { formatApiError } from "../lib/api";

const digits = (value, length) => value.replace(/\D/g, "").slice(0, length);

export default function PinChangeModal({ onClose }) {
  const { user, changePin } = useAuth();
  const required = Boolean(user?.must_change_pin);
  const pinLength = user?.pin_length;
  const [currentPin, setCurrentPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const close = () => { if (!required && !busy) onClose?.(); };

  const onSubmit = useCallback(
    async (e) => {
      e.preventDefault();
      setErr("");
      if (currentPin.length < 4) {
        setErr("Enter your current PIN");
        return;
      }
      if (newPin.length !== pinLength) {
        setErr(`Your new PIN must be ${pinLength} digits`);
        return;
      }
      if (newPin !== confirmPin) {
        setErr("New PIN and confirmation do not match");
        return;
      }
      setBusy(true);
      try {
        await changePin(currentPin, newPin);
        onClose?.();
      } catch (error) {
        setErr(formatApiError(error));
      } finally {
        setBusy(false);
      }
    },
    [currentPin, newPin, confirmPin, pinLength, changePin, onClose]
  );

  if (!user) return null;

  return (
    <Modal open onClose={required ? undefined : close} title={required ? "Choose Your Own PIN" : "Reset Your PIN"} size="sm">
      <p className="text-sm text-slate-600 mb-4">
        {required
          ? `Enter the one-time PIN you were given, then choose your own ${pinLength}-digit PIN.`
          : `Enter your current PIN and choose a new ${pinLength}-digit PIN. If you have forgotten your PIN, ask your team lead or admin to reset it.`}
      </p>
      <form onSubmit={onSubmit} className="space-y-4" data-testid="pin-change-form">
        {err && <Alert tone="rose">{err}</Alert>}
        <Field label={required ? "One-time PIN" : "Current PIN"}>
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="current-password"
            maxLength={6}
            value={currentPin}
            onChange={(e) => setCurrentPin(digits(e.target.value, 6))}
            placeholder="••••"
            autoFocus
            required
            data-testid="current-pin-input"
          />
        </Field>
        <Field label={`New ${pinLength}-digit PIN`}>
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="new-password"
            maxLength={pinLength}
            value={newPin}
            onChange={(e) => setNewPin(digits(e.target.value, pinLength))}
            placeholder="••••"
            required
            data-testid="new-pin-input"
          />
        </Field>
        <Field label="Confirm New PIN">
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="new-password"
            maxLength={pinLength}
            value={confirmPin}
            onChange={(e) => setConfirmPin(digits(e.target.value, pinLength))}
            placeholder="••••"
            required
            data-testid="confirm-pin-input"
          />
        </Field>
        <Button
          type="submit"
          className="w-full"
          size="lg"
          disabled={busy}
          data-testid="pin-change-submit-button"
        >
          {busy ? "Updating PIN…" : "Set New PIN"}
        </Button>
        {!required && <Button type="button" variant="outline" className="w-full" onClick={close} disabled={busy} data-testid="pin-change-cancel">Cancel</Button>}
      </form>
    </Modal>
  );
}
