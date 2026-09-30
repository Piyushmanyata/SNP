import { normalizePhone } from "../../lib/phone";
import { EMPTY_REASON, cardInHand, reasonReady } from "./ManualReason";
import { hasAge } from "./register";

const EMPTY_FORM = Object.freeze({
  full_name: "",
  age: "",
  phone: "",
  gender: "",
  address: "",
  aadhaar_last4: "",
  dob: "",
});

const DIGIT_LIMITS = { age: 3, aadhaar_last4: 4 };

export const initialRegisterForm = Object.freeze({
  seq: 0,
  form: EMPTY_FORM,
  qrPayload: "",
  manualMode: false,
  dayId: "",
  reason: EMPTY_REASON,
  error: "",
  review: null,
  lookalikeRows: null,
  busy: false,
  wedgeReading: false,
});

function fresh(state, atDoor, dayId = "") {
  return {
    ...initialRegisterForm,
    seq: state.seq + 1,
    manualMode: atDoor,
    dayId,
    busy: state.busy,
  };
}

function withCard(state, data, payload) {
  return {
    ...state,
    form: {
      full_name: data.full_name,
      age: data.age ?? "",
      phone: state.form.phone,
      gender: data.gender,
      address: data.address,
      aadhaar_last4: data.aadhaar_last4,
      dob: data.dob,
    },
    qrPayload: payload || "",
    manualMode: false,
    error: "",
    review: null,
  };
}

export function registerForm(state, event) {
  const current = event.seq === undefined || event.seq === state.seq;
  switch (event.type) {
    case "opened":
      return fresh(state, event.atDoor);
    case "contextChanged":
      return { ...state, seq: state.seq + 1, wedgeReading: false };
    case "cardScanned":
      return withCard(state, event.data, event.payload);
    case "captureStarted":
      return {
        ...state,
        seq: state.seq + 1,
        wedgeReading: false,
        qrPayload: "",
        review: null,
        form: { ...EMPTY_FORM, phone: state.form.phone },
      };
    case "readStarted":
      return { ...state, seq: state.seq + 1, error: "", wedgeReading: true };
    case "readResolved":
      if (!current) return state;
      return {
        ...(event.outcome === "card"
          ? withCard(state, event.data, event.payload)
          : { ...state, error: event.message || "Could not read that card. Scan it again." }),
        wedgeReading: false,
      };
    case "readFailed":
      if (!current) return state;
      return { ...state, error: event.message, wedgeReading: false };
    case "usbInterrupted":
      return { ...state, error: "The USB scan was cut off. Scan the card again." };
    case "fieldChanged": {
      const limit = DIGIT_LIMITS[event.field];
      const value = limit ? event.value.replace(/\D/g, "").slice(0, limit) : event.value;
      return { ...state, lookalikeRows: null, form: { ...state.form, [event.field]: value } };
    }
    case "reasonChosen":
      return { ...state, lookalikeRows: null, reason: event.reason };
    case "dayChosen":
      return { ...state, dayId: event.id };
    case "manualToggled":
      return { ...state, manualMode: !state.manualMode };
    case "saveStarted":
      return { ...state, busy: true, error: "" };
    case "saveSucceeded":
      if (event.next) return { ...fresh(state, event.atDoor, state.dayId), busy: false };
      return { ...state, busy: false };
    case "saveFailed": {
      const { failure } = event;
      const next = { ...state, busy: false };
      if (failure.kind === "review") return { ...next, review: failure.review };
      if (failure.kind === "lookalikes") return { ...next, lookalikeRows: failure.lookalikes };
      return { ...next, error: failure.message };
    }
    default:
      throw new Error(`Unknown Register form event: ${event.type}`);
  }
}

export function registrationView(state, { atDoor, doorDayId, days }) {
  const { form, reason, qrPayload, manualMode, busy } = state;
  const scanned = Boolean(qrPayload);
  const dayId = state.dayId || (days.find((d) => d.is_today) ?? days[0])?.id || "";
  const bookedDay = atDoor ? doorDayId : dayId;
  const showForm = scanned || manualMode;
  const dirty = showForm && (Object.values(form).some((value) => String(value ?? "") !== "") || Boolean(reason.code));
  const manualReady = reasonReady(reason) && Boolean(form.gender)
    && (!cardInHand(reason) || String(form.aadhaar_last4 ?? "").length === 4);
  const canSubmit = !busy && Boolean(form.full_name) && hasAge(form.age) && Boolean(normalizePhone(form.phone))
    && Boolean(bookedDay) && (scanned || manualReady);
  const locked = (field) => scanned && form[field] !== "" && form[field] != null;
  return { scanned, showForm, dayId, bookedDay, dirty, canSubmit, locked };
}
