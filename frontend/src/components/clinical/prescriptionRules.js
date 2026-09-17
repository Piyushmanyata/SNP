const EXCLUSIVE_LINES = {
  specs_fixed: "Fixed-power specs",
  specs_made: "Spectacles to be made",
  iol_surgery: "IOL surgery",
};

const EYES = { R: "Right eye", L: "Left eye" };

export function lineClash(lines, outcome) {
  const chosen = Object.keys(EXCLUSIVE_LINES).filter((key) =>
    key === "iol_surgery"
      ? (lines || []).includes("ot") && outcome === "iol_surgery"
      : (lines || []).includes(key));
  if (chosen.length < 2) return "";
  const names = chosen.map((key) => EXCLUSIVE_LINES[key]);
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]} cannot be on one prescription.`;
}

export function hospitalComplete(rx) {
  if (rx.ot_outcome === "referral") return true;
  return rx.ot_outcome === "iol_surgery"
    && Boolean(EYES[rx.ot_eye])
    && !lineClash(rx.prescribed_lines, "iol_surgery");
}

export function withLines(rx, lines) {
  return lines.includes("ot")
    ? { ...rx, prescribed_lines: lines }
    : { ...rx, prescribed_lines: lines, ot_outcome: null, ot_eye: null };
}

export function withOutcome(rx, outcome) {
  return { ...rx, ot_outcome: outcome, ot_eye: outcome === "iol_surgery" ? rx.ot_eye : null };
}

export function hospitalOutcomeLabel({ ot_outcome, ot_eye }) {
  if (ot_outcome === "referral") return "Hospital referral";
  if (ot_outcome !== "iol_surgery") return "";
  return ["IOL surgery", EYES[ot_eye]].filter(Boolean).join(" · ");
}
