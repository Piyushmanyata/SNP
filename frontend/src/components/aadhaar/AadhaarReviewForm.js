import React, { useState } from "react";
import { Button, Field, Input, Select } from "../ui";

export function ageFromDob(dob) {
  const match = /^\s*(\d{4})(?:-(\d{2})-(\d{2}))?\s*$/.exec(dob || "");
  if (!match) return "";
  const [year, month, day] = [Number(match[1]), Number(match[2] || 1), Number(match[3] || 1)];
  const birth = new Date(year, month - 1, day);
  if (birth.getFullYear() !== year || birth.getMonth() !== month - 1 || birth.getDate() !== day) return "";
  const now = new Date();
  const before = now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate());
  const age = now.getFullYear() - year - (before ? 1 : 0);
  return age >= 0 && age <= 130 ? String(age) : "";
}

export function AadhaarReviewForm({ initial = {}, onConfirm, disabled }) {
  const [fields, setFields] = useState(() => ({
    full_name: initial.full_name || "",
    age: initial.age == null ? ageFromDob(initial.dob) : String(initial.age),
    dob: initial.dob || "",
    gender: initial.gender || "",
    address: initial.address || "",
    aadhaar_last4: /^\d{4}$/.test(initial.aadhaar_last4 || "") ? initial.aadhaar_last4 : "",
  }));
  const [reviewed, setReviewed] = useState(false);
  const update = (name, value) => {
    const derivedAge = name === "dob" && ageFromDob(value);
    setFields((previous) => ({ ...previous, [name]: value, ...(derivedAge ? { age: derivedAge } : {}) }));
    setReviewed(false);
  };
  const validAge = /^\d{1,3}$/.test(fields.age) && Number(fields.age) <= 130;
  const validLast4 = !fields.aadhaar_last4 || /^\d{4}$/.test(fields.aadhaar_last4);

  return (
    <div className="mt-4 space-y-3" data-testid="aadhaar-review-form">
      <p className="font-semibold text-slate-900">Review patient details</p>
      <p className="text-sm text-slate-700">Check every field against the card. Text extraction can make mistakes. These details will need an identity check at the desk.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Full name" required>
          <Input value={fields.full_name} maxLength={120} disabled={disabled} onChange={(e) => update("full_name", e.target.value)} data-testid="aadhaar-review-full_name" />
        </Field>
        <Field label="Age" required>
          <Input type="number" min="0" max="130" value={fields.age} disabled={disabled} onChange={(e) => update("age", e.target.value)} data-testid="aadhaar-review-age" />
        </Field>
        <Field label="Date / year of birth" hint="Leave blank if unknown">
          <Input value={fields.dob} maxLength={10} placeholder="YYYY-MM-DD or YYYY" disabled={disabled} onChange={(e) => update("dob", e.target.value)} data-testid="aadhaar-review-dob" />
        </Field>
        <Field label="Gender">
          <Select value={fields.gender} disabled={disabled} onChange={(e) => update("gender", e.target.value)}>
            <option value="">Unknown</option><option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
          </Select>
        </Field>
        <Field label="Aadhaar last four digits" hint="Optional; never enter the full number">
          <Input value={fields.aadhaar_last4} maxLength={4} inputMode="numeric" disabled={disabled} onChange={(e) => update("aadhaar_last4", e.target.value)} />
        </Field>
        <Field label="Address">
          <Input value={fields.address} maxLength={500} disabled={disabled} onChange={(e) => update("address", e.target.value)} />
        </Field>
      </div>
      <label className="flex min-h-[44px] items-center gap-3 text-sm font-semibold text-slate-900">
        <input type="checkbox" checked={reviewed} disabled={disabled} className="h-5 w-5" onChange={(e) => setReviewed(e.target.checked)} data-testid="aadhaar-review-check" />
        I have checked and corrected these details.
      </label>
      <Button type="button" disabled={disabled || !reviewed || !fields.full_name.trim() || fields.full_name.length > 120 || fields.address.length > 500 || !validAge || !validLast4} onClick={() => onConfirm({ ...fields, full_name: fields.full_name.trim() })} data-testid="aadhaar-review-confirm">Use reviewed details</Button>
    </div>
  );
}
