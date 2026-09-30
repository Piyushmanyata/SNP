import api, { errorPayload, formatApiError } from "../../lib/api";
import { normalizePhone } from "../../lib/phone";
import { REQUEST_CONFLICT } from "../../lib/useRegistrationRequest";
import { reasonBody } from "./ManualReason";

export function hasAge(age) {
  return String(age ?? "") !== "";
}

export function registrationError(err) {
  const payload = errorPayload(err);
  if (payload?.code === "DUPLICATE_IN_CAMP") {
    return `Already registered as #${payload.registration.reg_no}. Find them below and print.`;
  }
  if (payload?.code === "AMBIGUOUS_MANUAL_ENTRY") {
    const nos = (payload.registrations || []).map((r) => `#${r.reg_no}`).join(", ");
    return `Multiple Manual entries match (${nos}). Scan the card at the door to pick one.`;
  }
  if (payload?.code === REQUEST_CONFLICT) return "Saved earlier. Search for the patient.";
  return formatApiError(err);
}

export function registrationFailure(err) {
  const payload = errorPayload(err);
  if (payload?.code === "MISMATCH_REVIEW_REQUIRED") return { kind: "review", review: payload };
  if (payload?.code === "LOOKALIKES") return { kind: "lookalikes", lookalikes: payload.registrations };
  return { kind: "error", message: registrationError(err) };
}

export function registrationBody({ form, qrPayload, dayId, reason, atDoor }) {
  const scanned = Boolean(qrPayload);
  const manual = scanned ? { code: null, note: null } : reasonBody(reason);
  return {
    full_name: form.full_name,
    age: hasAge(form.age) ? Number(form.age) : null,
    phone: normalizePhone(form.phone),
    gender: form.gender || null,
    address: form.address || null,
    aadhaar_last4: form.aadhaar_last4 || null,
    dob: form.dob || null,
    aadhaar_scanned: scanned,
    qr_payload: qrPayload || null,
    camp_day_id: dayId,
    manual_reason: manual.code,
    manual_note: manual.note,
    at_door: Boolean(atDoor),
  };
}

export async function registerPatient(request, { reviewConfirmedId, differentPerson, ...registration }) {
  const body = registrationBody(registration);
  const { data } = await request.send(body, (id) => api.post("/register", {
    ...body,
    registration_request_id: id,
    review_confirmed_id: reviewConfirmedId || null,
    different_person: Boolean(differentPerson),
  }));
  return data;
}
