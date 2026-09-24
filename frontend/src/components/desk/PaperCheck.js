import React from "react";
import { Alert, Button, Modal } from "../ui";

function ignoreSpace(event) {
  if (event.key === " ") event.preventDefault();
}

export function PaperCheck({ check, onConfirm, onReprint, onProblem, onClose }) {
  const keys = { onKeyDown: ignoreSpace, onKeyUp: ignoreSpace };
  return (
    <Modal open={Boolean(check)} onClose={onClose} title="Paper check">
      {check && (
        <div className="space-y-4" data-testid="paper-check">
          <p className="text-slate-900">
            Is the prescription for <strong>#{check.rx.reg_no} — {check.rx.full_name}</strong> in your hand?
          </p>
          <Alert>{check.error}</Alert>
          <div className="flex flex-col gap-2">
            <Button size="lg" autoFocus {...keys} onClick={onConfirm} disabled={check.busy} data-testid="paper-check-confirm">
              {check.error ? "Retry" : "Printed — next patient"}
            </Button>
            <Button variant="outline" {...keys} onClick={onReprint} disabled={check.busy} data-testid="paper-check-reprint">
              Reprint
            </Button>
            <Button variant="ghost" {...keys} onClick={onProblem} disabled={check.busy} data-testid="paper-check-problem">
              Printer problem
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
