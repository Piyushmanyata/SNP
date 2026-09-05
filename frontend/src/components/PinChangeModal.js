import React, { useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { Alert, Button, Field, Input, Modal } from "./ui";
import { formatApiError } from "../lib/api";

export default function PinChangeModal({ onClose }) {
  const { user, changePin } = useAuth();
  const required = Boolean(user?.must_change_pin);
  const [currentPin, setCurrentPin] = useState(() => required && user.role !== "admin" ? "1234" : "");
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const close = () => { if (!required && !busy) onClose?.(); };

  const onSubmit = useCallback(
    async (e) => {
      e.preventDefault();
      setErr("");
      if (!/^\d{4}$/.test(currentPin)) {
        setErr("Current PIN must be 4 digits");
        return;
      }
      if (!newPin || newPin.length !== 4 || !/^\d{4}$/.test(newPin)) {
        setErr("New PIN must be exactly 4 digits");
        return;
      }
      if (newPin === "1234") {
        setErr("New PIN cannot be the default 1234");
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
    [currentPin, newPin, confirmPin, changePin, onClose]
  );

  if (!user) return null;

  return (
    <Modal open onClose={required ? undefined : close} title={required ? "Change Your Default PIN" : "Reset Your PIN"} size="sm">
      <p className="text-sm text-slate-600 mb-4">
        {required ? "Choose a new 4-digit PIN before continuing." : "Enter your current PIN and choose a new 4-digit PIN. If you have forgotten your PIN, ask your team lead or admin to reset it."}
      </p>
      <form onSubmit={onSubmit} className="space-y-4" data-testid="pin-change-form">
        {err && <Alert tone="rose">{err}</Alert>}
        <Field label="Current PIN">
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="current-password"
            maxLength={4}
            value={currentPin}
            onChange={(e) => setCurrentPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder="••••"
            autoFocus={!required || user.role === "admin"}
            required
            data-testid="current-pin-input"
          />
        </Field>
        <Field label="New 4-digit PIN">
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="new-password"
            maxLength={4}
            value={newPin}
            onChange={(e) => setNewPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder="••••"
            required
            autoFocus={required && user.role !== "admin"}
            data-testid="new-pin-input"
          />
        </Field>
        <Field label="Confirm New PIN">
          <Input
            type="password"
            inputMode="numeric"
            autoComplete="new-password"
            maxLength={4}
            value={confirmPin}
            onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
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
