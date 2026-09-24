export const MAX_LOGOS = 6;
export const MAX_LOGO_SIZE = 2 * 1024 * 1024;
export const ALLOWED_LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];

export function swapItems(list, index, delta) {
  const targetIndex = index + delta;
  if (targetIndex < 0 || targetIndex >= list.length) {
    return list;
  }
  const next = [...list];
  [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
  return next;
}

export function validateLogoFile(file) {
  if (!file) {
    return { valid: false, error: "" };
  }
  if (file.size > MAX_LOGO_SIZE) {
    return { valid: false, error: "Logo must be 2 MB or smaller." };
  }
  if (!ALLOWED_LOGO_TYPES.includes(file.type)) {
    return { valid: false, error: "Use PNG, JPEG or WebP." };
  }
  return { valid: true, error: "" };
}

export function buildSampleRx(camp) {
  return {
    reg_no: 101,
    full_name: "Sample Patient",
    date: new Date().toISOString().slice(0, 10),
    age: 52,
    gender: "M",
    phone: "9876543210",
    address: "12 MG Road, Kolkata",
    patient_qr: "sample-preview-uuid",
    camp_name: camp?.name,
    venue: camp?.venue,
  };
}
