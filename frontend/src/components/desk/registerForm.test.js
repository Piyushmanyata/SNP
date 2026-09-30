import { initialRegisterForm, registerForm, registrationView } from "./registerForm";

const CARD = {
  full_name: "Sunita Devi", age: 51, gender: "F", address: "12 Station Road", aadhaar_last4: "1234", dob: "1975-06-14",
};
const DAYS = [
  { id: "day-1", is_today: false },
  { id: "day-2", is_today: true },
];
const DESK = { atDoor: false, doorDayId: "day-9", days: DAYS };
const DOOR = { ...DESK, atDoor: true };

function run(events, state = initialRegisterForm) {
  return events.reduce(registerForm, state);
}

const type = (field, value) => ({ type: "fieldChanged", field, value });
const scanned = [{ type: "cardScanned", data: CARD, payload: "card-A" }];
const manual = [
  { type: "opened", atDoor: false },
  { type: "manualToggled" },
  { type: "reasonChosen", reason: { code: "no_card", note: "" } },
  type("gender", "F"),
];
const filled = [type("full_name", "Kamla Bai"), type("age", "62"), type("phone", "9876500002")];

test("opened resets everything, follows atDoor for manual mode, and moves to a new seq", () => {
  const dirty = run([
    ...scanned, type("phone", "9876500001"), { type: "reasonChosen", reason: { code: "other", note: "x" } },
    { type: "dayChosen", id: "day-1" }, { type: "saveStarted" },
    { type: "saveFailed", failure: { kind: "lookalikes", lookalikes: [{ id: "p-3" }] } },
  ]);
  const desk = registerForm(dirty, { type: "opened", atDoor: false });
  const door = registerForm(dirty, { type: "opened", atDoor: true });
  expect(desk).toEqual({ ...initialRegisterForm, seq: dirty.seq + 1, busy: dirty.busy });
  expect(door).toEqual({ ...desk, manualMode: true });
});

test("opened does not touch a save that is still running", () => {
  const saving = run([{ type: "saveStarted" }]);
  expect(registerForm(saving, { type: "opened", atDoor: false }).busy).toBe(true);
});

test("contextChanged moves to a new seq and stops the reading status", () => {
  const reading = run([{ type: "readStarted" }]);
  const next = registerForm(reading, { type: "contextChanged" });
  expect(next.seq).toBe(reading.seq + 1);
  expect(next.wedgeReading).toBe(false);
});

test("a scanned card fills the form, keeps the typed phone and closes manual mode", () => {
  const state = run([
    { type: "manualToggled" }, type("phone", "9876500001"), type("full_name", "Typed"),
    { type: "readStarted" }, { type: "usbInterrupted" },
    ...scanned,
  ]);
  expect(state.form).toEqual({ ...CARD, phone: "9876500001" });
  expect(state).toEqual(expect.objectContaining({ qrPayload: "card-A", manualMode: false, error: "", review: null }));
});

test("a card without an age leaves it blank", () => {
  expect(run([{ type: "cardScanned", data: { ...CARD, age: undefined }, payload: "card-A" }]).form.age).toBe("");
});

test("starting a new capture drops the card, keeps the phone and stops any read", () => {
  const state = run([...scanned, type("phone", "9876500001"), { type: "readStarted" }]);
  const next = registerForm(state, { type: "captureStarted" });
  expect(next).toEqual(expect.objectContaining({ qrPayload: "", review: null, wedgeReading: false, seq: state.seq + 1 }));
  expect(next.form).toEqual({ ...initialRegisterForm.form, phone: "9876500001" });
});

test("a stale read is ignored, and a current one fills the form and keeps the typed phone", () => {
  const started = run([type("phone", "9876500001"), { type: "readStarted" }]);
  const late = registerForm(started, { type: "contextChanged" });
  const card = { type: "readResolved", seq: started.seq, outcome: "card", data: CARD, payload: "card-A" };
  expect(registerForm(late, card)).toBe(late);
  expect(registerForm(late, { type: "readFailed", seq: started.seq, message: "Late" })).toBe(late);
  const filledCard = registerForm(started, card);
  expect(filledCard.form).toEqual({ ...CARD, phone: "9876500001" });
  expect(filledCard).toEqual(expect.objectContaining({ qrPayload: "card-A", wedgeReading: false }));
});

test("a capture that starts while a read is out drops the read", () => {
  const started = run([{ type: "readStarted" }]);
  const moved = registerForm(started, { type: "captureStarted" });
  expect(registerForm(moved, { type: "readResolved", seq: started.seq, outcome: "card", data: CARD, payload: "p" })).toBe(moved);
});

test.each([
  [{ outcome: "garbage", message: "That is not an Aadhaar QR." }, "That is not an Aadhaar QR."],
  [{ outcome: "garbage" }, "Could not read that card. Scan it again."],
])("a read that decodes as %o shows an error and no form", (reply, message) => {
  const started = run([{ type: "readStarted" }]);
  const next = registerForm(started, { type: "readResolved", seq: started.seq, payload: "p", ...reply });
  expect(next).toEqual(expect.objectContaining({ error: message, wedgeReading: false, qrPayload: "" }));
});

test("a read that fails shows the failure and stops the reading status", () => {
  const started = run([{ type: "readStarted" }]);
  const next = registerForm(started, { type: "readFailed", seq: started.seq, message: "Network Error" });
  expect(next).toEqual(expect.objectContaining({ error: "Network Error", wedgeReading: false }));
});

test("starting a read clears the last error and shows the reading status", () => {
  const next = run([{ type: "usbInterrupted" }, { type: "readStarted" }]);
  expect(next).toEqual(expect.objectContaining({ error: "", wedgeReading: true }));
});

test("a cut-off USB scan says so", () => {
  expect(run([{ type: "usbInterrupted" }]).error).toBe("The USB scan was cut off. Scan the card again.");
});

test("age and last-4 keep only digits and stop at their limits, and any edit clears the Lookalikes", () => {
  const lookalike = { type: "saveFailed", failure: { kind: "lookalikes", lookalikes: [{ id: "p-3" }] } };
  const state = run([lookalike, type("age", "4a0x99"), type("aadhaar_last4", "12a345")]);
  expect(state.form.age).toBe("409");
  expect(state.form.aadhaar_last4).toBe("1234");
  expect(state.lookalikeRows).toBeNull();
  expect(run([type("phone", "+91 98765-0000x")]).form.phone).toBe("+91 98765-0000x");
  expect(run([type("full_name", "Ram K.2")]).form.full_name).toBe("Ram K.2");
});

test("choosing a reason clears the Lookalikes", () => {
  const state = run([
    { type: "saveFailed", failure: { kind: "lookalikes", lookalikes: [{ id: "p-3" }] } },
    { type: "reasonChosen", reason: { code: "no_card", note: "" } },
  ]);
  expect(state.lookalikeRows).toBeNull();
  expect(state.reason).toEqual({ code: "no_card", note: "" });
});

test("choosing a day and toggling manual mode change only themselves", () => {
  expect(run([{ type: "dayChosen", id: "day-1" }]).dayId).toBe("day-1");
  expect(run([{ type: "manualToggled" }]).manualMode).toBe(true);
  expect(run([{ type: "manualToggled" }, { type: "manualToggled" }]).manualMode).toBe(false);
});

test("saveStarted holds the form busy and clears the error", () => {
  const next = run([{ type: "usbInterrupted" }, { type: "saveStarted" }]);
  expect(next).toEqual(expect.objectContaining({ busy: true, error: "" }));
});

test.each([
  [{ kind: "review", review: { registration: { id: "p-3" } } }, { review: { registration: { id: "p-3" } } }],
  [{ kind: "lookalikes", lookalikes: [{ id: "p-3" }] }, { lookalikeRows: [{ id: "p-3" }] }],
  [{ kind: "error", message: "Saved earlier." }, { error: "Saved earlier." }],
])("saveFailed %o sets exactly one of review, lookalikeRows and error and clears busy", (failure, expected) => {
  const next = run([{ type: "saveStarted" }, { type: "saveFailed", failure }]);
  expect({ review: next.review, lookalikeRows: next.lookalikeRows, error: next.error, busy: next.busy })
    .toEqual({ review: null, lookalikeRows: null, error: "", busy: false, ...expected });
});

test("saveSucceeded leaves the form for the next patient but keeps the chosen day and the day's seq", () => {
  const state = run([...scanned, type("phone", "9876500001"), { type: "dayChosen", id: "day-1" }, { type: "saveStarted" }]);
  const next = registerForm(state, { type: "saveSucceeded", next: true, atDoor: false });
  expect(next).toEqual({ ...initialRegisterForm, dayId: "day-1", seq: state.seq + 1 });
});

test("saveSucceeded without next only releases the form", () => {
  const state = run([...scanned, { type: "saveStarted" }]);
  expect(registerForm(state, { type: "saveSucceeded", next: false, atDoor: false })).toEqual({ ...state, busy: false });
});

test.each([
  [{ type: "saveSucceeded", next: true, atDoor: false }],
  [{ type: "saveSucceeded", next: false, atDoor: false }],
  [{ type: "saveFailed", failure: { kind: "lookalikes", lookalikes: [{ id: "p-3" }] } }],
  [{ type: "saveFailed", failure: { kind: "review", review: { registration: { id: "p-3" } } } }],
  [{ type: "saveFailed", failure: { kind: "error", message: "Saved earlier." } }],
])("%o from a save that started before the form was reopened only releases the busy flag", (event) => {
  const saving = run([...scanned, { type: "saveStarted" }]);
  const reopened = registerForm(saving, { type: "opened", atDoor: false });
  expect(reopened.busy).toBe(true);
  expect(registerForm(reopened, { ...event, seq: saving.seq })).toEqual({ ...reopened, busy: false });
});

test("an unknown event is a programming error", () => {
  expect(() => registerForm(initialRegisterForm, { type: "nope" })).toThrow("Unknown Register form event: nope");
});

test("the initial state is frozen", () => {
  expect(Object.isFrozen(initialRegisterForm)).toBe(true);
});

describe("registrationView", () => {
  const view = (events, props = DESK) => registrationView(run(events), props);

  test("the chosen day wins, else today's day, else the first, else none", () => {
    expect(view([{ type: "dayChosen", id: "day-1" }]).dayId).toBe("day-1");
    expect(view([]).dayId).toBe("day-2");
    expect(view([], { ...DESK, days: [{ id: "day-7", is_today: false }] }).dayId).toBe("day-7");
    expect(view([], { ...DESK, days: [] }).dayId).toBe("");
  });

  test("days that arrive after the form opened need no event", () => {
    const opened = run([{ type: "opened", atDoor: false }]);
    expect(registrationView(opened, { ...DESK, days: [] }).dayId).toBe("");
    expect(registrationView(opened, DESK).dayId).toBe("day-2");
  });

  test("the door books the operating day whatever day is chosen", () => {
    expect(view([{ type: "dayChosen", id: "day-1" }], DOOR).bookedDay).toBe("day-9");
    expect(view([{ type: "dayChosen", id: "day-1" }]).bookedDay).toBe("day-1");
  });

  test("the form shows for a scanned card or manual mode only", () => {
    expect(view([]).showForm).toBe(false);
    expect(view(scanned).showForm).toBe(true);
    expect(view([{ type: "manualToggled" }]).showForm).toBe(true);
  });

  test("dirty ignores an unopened form and counts any value or reason", () => {
    expect(view([type("full_name", "x")]).dirty).toBe(false);
    expect(view([{ type: "manualToggled" }]).dirty).toBe(false);
    expect(view([{ type: "manualToggled" }, type("address", "x")]).dirty).toBe(true);
    expect(view([{ type: "manualToggled" }, { type: "reasonChosen", reason: { code: "no_card", note: "" } }]).dirty).toBe(true);
    expect(view(scanned).dirty).toBe(true);
  });

  test("a scanned field is locked only when it has a value", () => {
    const state = run([{ type: "cardScanned", data: { ...CARD, address: "", dob: null }, payload: "card-A" }]);
    const { locked } = registrationView(state, DESK);
    expect(locked("full_name")).toBe(true);
    expect(locked("address")).toBe(false);
    expect(locked("dob")).toBe(false);
    expect(locked("phone")).toBe(false);
    expect(registrationView(run(manual), DESK).locked("full_name")).toBe(false);
  });

  const ready = [...manual, ...filled];
  test.each([
    ["typed with everything", ready, true],
    ["typed without a name", [...ready, type("full_name", "")], false],
    ["typed without an age", [...ready, type("age", "")], false],
    ["typed with an age of zero", [...ready, type("age", "0")], true],
    ["typed with a short phone", [...ready, type("phone", "98765")], false],
    ["typed with a +91 phone", [...ready, type("phone", "+91 98765 00002")], true],
    ["typed with no reason", [...ready, { type: "reasonChosen", reason: { code: "", note: "" } }], false],
    ["typed with no gender", [...ready, type("gender", "")], false],
    ["typed with Other and no note", [...ready, { type: "reasonChosen", reason: { code: "other", note: " " } }], false],
    ["typed with Other and a note", [...ready, { type: "reasonChosen", reason: { code: "other", note: "son" } }], true],
    ["typed, card in hand, no last-4", [...ready, { type: "reasonChosen", reason: { code: "card_unreadable", note: "" } }], false],
    ["typed, card in hand, last-4", [...ready, { type: "reasonChosen", reason: { code: "scanner_down", note: "" } }, type("aadhaar_last4", "4321")], true],
    ["typed, card in hand, three digits", [...ready, { type: "reasonChosen", reason: { code: "scanner_down", note: "" } }, type("aadhaar_last4", "432")], false],
    ["typed and busy", [...ready, { type: "saveStarted" }], false],
    ["scanned needs only the phone", [...scanned, type("phone", "9876500001")], true],
    ["scanned without a phone", scanned, false],
    ["scanned with an age of zero", [{ type: "cardScanned", data: { ...CARD, age: 0 }, payload: "card-A" }, type("phone", "9876500001")], true],
  ])("canSubmit, %s", (_name, events, expected) => {
    expect(view(events).canSubmit).toBe(expected);
  });

  test("canSubmit needs a booked day", () => {
    const events = [...scanned, type("phone", "9876500001")];
    expect(view(events, { ...DESK, days: [] }).canSubmit).toBe(false);
    expect(view(events, { ...DOOR, doorDayId: "" }).canSubmit).toBe(false);
    expect(view(events, DOOR).canSubmit).toBe(true);
  });
});
