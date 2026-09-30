import { deskSession, initialDeskSession } from "./deskSession";

const REG = { id: "p-1", reg_no: "101", full_name: "Asha Devi" };
const NEXT = { id: "p-2", reg_no: "102", full_name: "Ravi Kumar" };
const RX = { reg_no: "101", full_name: "Asha Devi" };

function run(events, state = initialDeskSession) {
  return events.reduce(deskSession, state);
}

const onCard = run([
  { type: "scanStarted", payload: "card" },
  { type: "scanResolved", seq: 1, result: { outcome: "arrived", registration: REG, prescription: RX } },
]);

const withPaperCheck = run([{ type: "printReady", seq: 1, reg: REG, rx: RX }], onCard);

const FIND_STARTS = [
  { type: "scanStarted", payload: "next card" },
  { type: "findStarted" },
];

test.each(FIND_STARTS)("$type moves to a new seq and clears the previous patient", (event) => {
  const state = run([
    { type: "failed", seq: 1, message: "Old error" },
    { type: "searchResolved", seq: 1, results: [REG] },
    { type: "lookupResolved", seq: 1, registration: REG, reprint: true },
  ], withPaperCheck);
  const next = deskSession(state, event);
  expect(next.seq).toBe(state.seq + 1);
  expect(next).toEqual(expect.objectContaining({
    banner: "", error: "", searchResults: null, found: null, paperCheck: null,
  }));
  if (event.type !== "scanStarted") expect(next.scanResult).toBeNull();
});

test("a typed find closes an open Paper check without recording", () => {
  expect(withPaperCheck.paperCheck).not.toBeNull();
  expect(deskSession(withPaperCheck, { type: "findStarted" }).paperCheck).toBeNull();
});

test.each([
  { type: "scanResolved", result: { outcome: "arrived", registration: NEXT } },
  { type: "lookupResolved", registration: NEXT, reprint: true },
  { type: "searchResolved", results: [NEXT] },
  { type: "failed", message: "Late failure" },
  { type: "printReady", reg: NEXT, rx: RX },
])("a stale $type reply is ignored", (reply) => {
  const state = run([{ type: "findStarted" }], onCard);
  expect(deskSession(state, { ...reply, seq: state.seq - 1 })).toBe(state);
});

test("an arrival scan puts the patient on the card with a banner", () => {
  expect(onCard.scanResult.registration).toBe(REG);
  expect(onCard.scanning).toBe(false);
  expect(onCard.banner).toBe("Arrived: #101 — Asha Devi");
});

test("a door scan closes an open Manual entry but keeps New Registration open", () => {
  const door = run([{ type: "modalOpened", mode: "door" }, { type: "scanStarted", payload: "x" }]);
  const prereg = run([{ type: "modalOpened", mode: "prereg" }, { type: "scanStarted", payload: "x" }]);
  expect(door.regMode).toBe("");
  expect(prereg.regMode).toBe("prereg");
});

test("Printed — next patient clears the card, shows the next-patient banner and asks for the USB box", () => {
  const next = deskSession(withPaperCheck, { type: "paperConfirmed", request: 1, registration: REG });
  expect(next).toEqual(expect.objectContaining({
    seq: 2, paperCheck: null, scanResult: null, found: null, focusUsbBox: true,
    banner: "Printed #101 — Asha Devi. Next patient.",
  }));
  expect(deskSession(next, { type: "usbFocused" }).focusUsbBox).toBe(false);
});

test("a Paper check confirmation for an older request closes it without moving on", () => {
  const moved = run([{ type: "findStarted" }], withPaperCheck);
  const stale = { ...moved, paperCheck: withPaperCheck.paperCheck };
  const next = deskSession(stale, { type: "paperConfirmed", request: 1 });
  expect(next.paperCheck).toBeNull();
  expect(next.seq).toBe(stale.seq);
  expect(next.banner).toBe("");
  expect(next.focusUsbBox).toBe(false);
});

test("a failed stamp keeps the Paper check open with the error", () => {
  const next = run([
    { type: "paperConfirmStarted", request: 1 },
    { type: "paperConfirmFailed", request: 1, message: "Network Error" },
  ], withPaperCheck);
  expect(next.paperCheck).toEqual(expect.objectContaining({ busy: false, error: "Network Error" }));
});

test("a late reply for an older Paper check never touches the newer one", () => {
  const newer = run([
    { type: "findStarted" },
    { type: "printReady", seq: 2, reg: { id: "p-2" }, rx: RX },
  ], withPaperCheck);
  expect(deskSession(newer, { type: "paperConfirmFailed", request: 1, message: "Network Error" })).toBe(newer);
  expect(deskSession(newer, { type: "paperConfirmed", request: 1, registration: REG })).toBe(newer);
});

test("dismissing the Paper check records nothing, drops the scanned sheet and leaves a note", () => {
  const next = deskSession(withPaperCheck, { type: "paperDismissed", note: "Printer problem." });
  expect(next.paperCheck).toBeNull();
  expect(next.scanResult).toEqual(expect.objectContaining({ registration: REG, prescription: null }));
  expect(next.printNote).toBe("Printer problem.");
  expect(next.seq).toBe(withPaperCheck.seq);
});

test("Reprint follows the lookup that found the row", () => {
  const typed = run([{ type: "findStarted" }, { type: "lookupResolved", seq: 1, registration: REG, reprint: true }]);
  const code = run([{ type: "findStarted" }, { type: "lookupResolved", seq: 1, registration: REG, reprint: false }]);
  expect(typed.found.reprint).toBe(true);
  expect(code.found.reprint).toBe(false);
});

test("a walk-in keeps its request id for the same card and renews it after a request conflict", () => {
  const scanned = { ...initialDeskSession, scanPayload: "card-A" };
  const first = deskSession(scanned, { type: "walkInStarted", key: "card-A", reqId: "req-1" });
  const retry = deskSession({ ...first, busy: false }, { type: "walkInStarted", key: "card-A", reqId: "req-2" });
  expect(retry.walkIn).toEqual({ key: "card-A", reqId: "req-1" });
  const conflict = deskSession(retry, { type: "walkInFailed", seq: retry.seq, reqId: "req-3", message: "Saved earlier." });
  expect(conflict.walkIn).toEqual({ key: "card-A", reqId: "req-3" });
  expect(conflict.error).toBe("Saved earlier.");
});

test("a walk-in that arrives clears its attempt and puts the arrived patient on the card", () => {
  const started = deskSession({ ...initialDeskSession, scanPayload: "card-A", doorPhone: "98765" }, { type: "walkInStarted", key: "card-A", reqId: "req-1" });
  const arrived = { ...REG, arrived_at: "2026-10-05T03:30:00Z" };
  const next = deskSession(started, { type: "walkInResolved", seq: started.seq, registration: arrived });
  expect(next).toEqual(expect.objectContaining({
    scanPayload: "", doorPhone: "", banner: "Registered and arrived: #101 — Asha Devi",
  }));
  expect(next.scanResult).toEqual({ outcome: "arrived", registration: arrived, prescription: null });
  expect(next.walkIn.key).toBe("");
});

test("a walk-in that came back not arrived shows its row instead of claiming arrival", () => {
  const started = deskSession({ ...initialDeskSession, scanPayload: "card-A" }, { type: "walkInStarted", key: "card-A", reqId: "req-1" });
  const booked = { ...REG, arrived_at: null };
  const next = deskSession(started, { type: "walkInResolved", seq: started.seq, registration: booked });
  expect(next.scanResult).toBeNull();
  expect(next.banner).toBe("");
  expect(next.found).toEqual({ reg: booked, reprint: true });
});

test("printingChanged clears the found patient and search results only", () => {
  const state = run([
    { type: "failed", seq: 1, message: "Old error" },
    { type: "searchResolved", seq: 1, results: [REG] },
    { type: "lookupResolved", seq: 1, registration: REG, reprint: true },
    { type: "bannerShown", message: "Registered #101" },
  ], withPaperCheck);
  expect(state.found).not.toBeNull();
  const next = deskSession(state, { type: "printingChanged" });
  expect(next.found).toBeNull();
  expect(next.searchResults).toBeNull();
  expect({ ...next, found: state.found, searchResults: state.searchResults }).toEqual(state);
  expect(next.paperCheck).toBe(state.paperCheck);
  expect(next.seq).toBe(state.seq);
});

test("an unknown event is a programming error", () => {
  expect(() => deskSession(initialDeskSession, { type: "nope" })).toThrow("Unknown Desk session event: nope");
});
